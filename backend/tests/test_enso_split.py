from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from test_calendar_api import A, make_layer, row

from firecal.api.app import create_app
from firecal.io import enso
from firecal.stages.calendar.enso_split import NOTE_EN, NOTE_ES, phase_by_month, split_by_phase


def oni_table(start: str, values) -> pd.DataFrame:
    idx = pd.date_range(start, periods=len(values), freq="MS")
    s = pd.Series(values, index=idx, dtype=float)
    return pd.DataFrame({"date": idx, "oni": s.to_numpy(), "phase": enso.classify_phase(s).to_numpy()})


# 2010 neutral, 2011 La Nina (-1.0 all year), 2012 neutral, 2013 El Nino (+1.0), 2014 neutral
ONI = oni_table("2010-01-01", [0.0] * 12 + [-1.0] * 12 + [0.0] * 12 + [1.0] * 12 + [0.0] * 12)
PHASE_OF = {2010: "neutral", 2011: "nina", 2012: "neutral", 2013: "nino", 2014: "neutral"}


def matrix(counts: dict[int, float]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"year": y, "month": m, "viirs_eq": c} for y, c in counts.items() for m in range(1, 13)]
    )


def test_phase_by_month_keeps_only_months_inside_the_period_and_the_oni():
    p = phase_by_month(ONI, (2011, 11), (2013, 2))
    assert list(zip(p["year"], p["month"], strict=True))[0] == (2011, 11)
    assert list(zip(p["year"], p["month"], strict=True))[-1] == (2013, 2)
    assert len(p) == 16
    assert set(p["phase"]) == {"nina", "neutral", "nino"}
    # period wider than the ONI file: only the ONI months survive
    wide = phase_by_month(ONI, (2005, 1), (2020, 12))
    assert (wide["year"].min(), wide["year"].max()) == (2010, 2014) and len(wide) == 60
    assert phase_by_month(ONI, (2030, 1), (2031, 1)).empty


def test_phase_by_month_drops_missing_oni():
    df = oni_table("2010-01-01", [0.0, np.nan, 0.0])
    assert list(phase_by_month(df, (2010, 1), (2010, 3))["month"]) == [1, 3]


def test_split_by_phase_medians_with_nina_double():
    counts = {2010: 10.0, 2011: 20.0, 2012: 14.0, 2013: 30.0, 2014: 6.0}
    phases = phase_by_month(ONI, (2010, 1), (2014, 12))
    out = split_by_phase(matrix(counts), "viirs_eq", phases)
    assert len(out) == 12 * 3
    one = out[out["month"] == 1].set_index("phase")
    assert one.loc["nina", "median"] == 20.0 and one.loc["nina", "n_years"] == 1
    assert one.loc["nina", "years"] == [2011]
    assert one.loc["nino", "median"] == 30.0
    assert one.loc["neutral", "n_years"] == 3
    assert one.loc["neutral", "years"] == [2010, 2012, 2014]
    assert one.loc["neutral", "median"] == 10.0  # median of 10, 14, 6
    assert one.loc["neutral", "p25"] == 8.0 and one.loc["neutral", "p75"] == 12.0  # linear interpolation
    assert list(out["phase"][:3]) == ["nino", "nina", "neutral"]


def test_split_by_phase_nina_years_have_twice_the_counts():
    counts = {y: (20.0 if PHASE_OF[y] == "nina" else 10.0) for y in PHASE_OF}
    out = split_by_phase(matrix(counts), "viirs_eq", phase_by_month(ONI, (2010, 1), (2014, 12)))
    med = out.groupby("phase")["median"].median()
    assert med["nina"] == 2 * med["neutral"] == 2 * med["nino"]


def test_split_by_phase_leaves_out_empty_groups():
    m = matrix({2010: 10.0, 2011: 20.0})
    m.loc[(m["year"] == 2011) & (m["month"] == 3), "viirs_eq"] = np.nan  # no value in Niña March
    out = split_by_phase(m, "viirs_eq", phase_by_month(ONI, (2010, 1), (2011, 12)))
    assert not ((out["month"] == 3) & (out["phase"] == "nina")).any()
    assert not (out["phase"] == "nino").any()  # no El Niño year in the matrix
    assert len(out) == 12 + 11


@pytest.fixture
def enso_path(tmp_path):
    return enso.write_enso(ONI, tmp_path / "enso" / "oni.parquet")


def api_client(tmp_path: Path, enso_file: Path) -> TestClient:
    rows = [
        row(y, m, A, mr=10, me=20.0 if y == 2011 else 10.0) for y in (2010, 2011, 2012) for m in range(1, 13)
    ]
    make_layer(tmp_path / "harmonized", rows, "2010-01-01/2012-12-31")
    return TestClient(create_app(tmp_path, enso_path=enso_file))


def test_api_returns_the_enso_block(tmp_path, enso_path):
    client = api_client(tmp_path, enso_path)
    r = client.post("/calendar", json={"preset": "cordoba", "scale": "modis_eq"})
    assert r.status_code == 200, r.text
    block = r.json()["enso"]
    assert block["source"] == enso.SOURCE and block["url"] == enso.ONI_URL
    assert block["definition"] == enso.DEFINITION
    assert block["period"] == {"start": "2010-01", "end": "2014-12"}
    assert block["note_es"] == NOTE_ES and block["note_en"] == NOTE_EN
    assert "np.quantile" in block["quantile_method"]
    assert len(block["months"]) == 36  # only the calendar period 2010-2012
    assert block["months"][12] == {"ym": "2011-01", "oni": -1.0, "phase": "nina"}
    by = {(b["month"], b["phase"]): b for b in block["by_phase"]}
    assert by[(1, "nina")] == {
        "month": 1, "phase": "nina", "n_years": 1, "median": 20.0, "p25": 20.0, "p75": 20.0, "years": [2011],
    }  # fmt: skip
    assert by[(1, "neutral")]["years"] == [2010, 2012] and by[(1, "neutral")]["median"] == 10.0
    assert (1, "nino") not in by  # no El Niño year in the calendar period


def test_api_enso_is_null_when_the_file_is_missing(tmp_path):
    client = api_client(tmp_path, tmp_path / "nope.parquet")
    r = client.post("/calendar", json={"preset": "cordoba", "scale": "modis_eq"})
    assert r.status_code == 200 and r.json()["enso"] is None


def test_api_enso_is_cached_and_follows_file_changes(tmp_path, enso_path, monkeypatch):
    client = api_client(tmp_path, enso_path)
    calls = []
    real = enso.read_enso
    monkeypatch.setattr(enso, "read_enso", lambda p=None: calls.append(p) or real(p))
    body = {"preset": "cordoba", "scale": "modis_eq"}
    for _ in range(3):
        assert client.post("/calendar", json=body).json()["enso"] is not None
    assert len(calls) == 1
