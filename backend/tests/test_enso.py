from pathlib import Path

import httpx
import numpy as np
import pandas as pd
import pytest

from firecal.io import enso

FIXTURE = Path(__file__).parent / "fixtures" / "oni_sample.txt"


def _series(values, start="2000-01-01"):
    idx = pd.date_range(start, periods=len(values), freq="MS")
    return pd.Series(values, index=idx, dtype=float)


def test_parse_fixture():
    df = enso.parse_oni(FIXTURE.read_text())
    assert list(df.columns) == ["date", "season", "oni"]
    assert len(df) == 24
    assert df["date"].is_monotonic_increasing
    assert df.loc[0, "season"] == "DJF"
    assert df.loc[0, "date"] == pd.Timestamp("1950-01-01")
    assert df.loc[0, "oni"] == pytest.approx(-1.53)
    assert df.loc[23, "date"] == pd.Timestamp("1951-12-01")


def test_parse_unknown_season_raises():
    with pytest.raises(ValueError, match="unknown season"):
        enso.parse_oni("SEAS  YR   TOTAL   ANOM\n XYZ 1950 24.72 -1.53\n")


def test_parse_sentinel_is_nan():
    df = enso.parse_oni("SEAS  YR   TOTAL   ANOM\n DJF 1950 24.72 -99.90\n JFM 1950 25.0 0.1\n")
    assert np.isnan(df.loc[0, "oni"])
    assert df.loc[1, "oni"] == pytest.approx(0.1)


def test_run_of_five_is_nino():
    phase = enso.classify_phase(_series([0.0, 0.6, 0.7, 0.8, 0.9, 1.0, 0.0]))
    assert list(phase) == ["neutral"] + ["nino"] * 5 + ["neutral"]


def test_run_of_four_is_neutral():
    phase = enso.classify_phase(_series([0.0, 0.6, 0.7, 0.8, 0.9, 0.0]))
    assert set(phase) == {"neutral"}


def test_thresholds_are_inclusive():
    assert set(enso.classify_phase(_series([0.5] * 5))) == {"nino"}
    assert set(enso.classify_phase(_series([-0.5] * 5))) == {"nina"}


def test_run_of_five_is_nina():
    phase = enso.classify_phase(_series([-0.1, -0.6, -0.9, -1.2, -0.8, -0.5]))
    assert list(phase) == ["neutral"] + ["nina"] * 5


def test_gap_splits_run():
    s = _series([0.8] * 6)
    s = s.drop(s.index[3])  # 3 months + gap + 2 months
    assert set(enso.classify_phase(s)) == {"neutral"}
    s2 = _series([0.8] * 7).drop(pd.Timestamp("2000-04-01"))  # 3 + 3
    assert set(enso.classify_phase(s2)) == {"neutral"}


def test_nan_breaks_run():
    assert set(enso.classify_phase(_series([0.8, 0.8, 0.8, np.nan, 0.8, 0.8, 0.8]))) == {"neutral"}


def test_sign_change_breaks_run():
    phase = enso.classify_phase(_series([0.8, 0.8, 0.8, -0.8, -0.8, -0.8]))
    assert set(phase) == {"neutral"}


def test_overrides_and_dataframe_input():
    s = _series([0.8, 0.8, 0.8])
    assert set(enso.classify_phase(s, min_run=3)) == {"nino"}
    assert set(enso.classify_phase(_series([0.4] * 5), nino_threshold=0.3)) == {"nino"}
    df = pd.DataFrame({"date": s.index, "oni": s.to_numpy()})
    assert set(enso.classify_phase(df, min_run=3)) == {"nino"}


def test_build_enso_columns_and_attrs():
    df = enso.build_enso(FIXTURE.read_text())
    assert list(df.columns) == ["date", "season", "oni", "above_threshold", "phase"]
    assert df.attrs["source"] == "NOAA CPC ONI"
    assert df.attrs["url"] == enso.ONI_URL
    assert "consecutive" in df.attrs["definition"]
    # 1950 Jan-Jul: 7-month La Nina run; Nov 1950-Feb 1951 is only 4 months -> neutral.
    assert list(df["phase"][:7]) == ["nina"] * 7
    assert df.loc[10, "above_threshold"] == "nina"
    assert df.loc[10, "phase"] == "neutral"
    assert list(df["phase"][17:]) == ["nino"] * 7


def test_write_read_round_trip(tmp_path):
    df = enso.build_enso(FIXTURE.read_text())
    out = enso.write_enso(df, tmp_path / "sub" / "oni.parquet")
    back = enso.read_enso(out)
    pd.testing.assert_frame_equal(df, back, check_dtype=False)
    assert back.attrs["source"] == "NOAA CPC ONI"
    assert back.attrs["url"] == enso.ONI_URL


def test_run_with_mock_transport(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=FIXTURE.read_text())

    client = httpx.Client(transport=httpx.MockTransport(handler))
    target = tmp_path / "oni.parquet"
    assert enso.run(target, client=client) == target
    assert enso.run(target, client=client) == target  # idempotent
    assert len(enso.read_enso(target)) == 24


def test_default_path_uses_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("FIRECAL_DATA_DIR", str(tmp_path))
    assert enso.default_path() == tmp_path / "interim" / "enso" / "oni_monthly.parquet"
