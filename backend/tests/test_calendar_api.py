import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from firecal.api.app import create_app
from firecal.layers.manifest import LayerManifest
from firecal.stages.harmonize.regions import block_ids

A = (-31.05, -64.05)  # cell centers are k*0.1 + 0.05
B = (-31.25, -64.25)
FAR = (-40.05, -60.05)
CIRCLE = {"type": "circle", "lat": -31.15, "lon": -64.15, "radius_km": 40}
EMPTY_CIRCLE = {"type": "circle", "lat": -33.05, "lon": -64.05, "radius_km": 20}


def row(year, month, pos, mr=np.nan, vr=np.nan, me=0.0, ve=0.0, mest=False, vest=False):
    return {
        "year": year, "month": month, "cell_id": int(abs(pos[0]) * 1000 + abs(pos[1]) * 10),
        "cell_lat": pos[0], "cell_lon": pos[1], "modis_reported": mr, "viirs_reported": vr,
        "modis_eq": me, "viirs_eq": ve, "modis_eq_estimated": mest, "viirs_eq_estimated": vest,
        "modis_sats": "terra", "viirs_source": "snpp", "method": "scale_factor",
        "calibration_version": "t1",
    }  # fmt: skip


ROWS = [
    row(2011, 11, A, mr=2, me=2, ve=1.0, vest=True),
    row(2011, 12, A, mr=3, me=3, ve=1.5, vest=True),
    row(2011, 12, FAR, mr=5, me=5, ve=2.5, vest=True),
    row(2012, 1, A, mr=1, vr=2, me=1, ve=2),
    row(2012, 1, B, mr=4, vr=1, me=4, ve=1),
]


def make_layer(root: Path, rows: list[dict], period: str, bands: bool = False) -> Path:
    df = pd.DataFrame(rows)
    (root / "series").mkdir(parents=True)
    for y, g in df.groupby("year"):
        g.to_parquet(root / "series" / f"{y}.parquet")
    if bands:
        blk = int(block_ids(np.array([A[0]]), np.array([A[1]]))[0])
        (root / "band_block_month").mkdir()
        (root / "band_block_year").mkdir()
        month = pd.DataFrame(
            {"year": [2011], "month": [12], "block": [blk], "target": "viirs_eq", "estimate": [1.5],
             "lo": [1.0], "hi": [3.0], "nominal": [0.8]}
        )  # fmt: skip
        year = pd.DataFrame(
            {"year": [2011], "block": [blk], "target": "viirs_eq", "estimate": [2.5], "lo": [2.0],
             "hi": [4.0], "nominal": [0.8]}
        )  # fmt: skip
        month.to_parquet(root / "band_block_month" / "2011.parquet")
        year.to_parquet(root / "band_block_year" / "2011.parquet")
    (root / "manifest.json").write_text(
        LayerManifest(
            id="harmonized", title="t", kind="series", source="src FIRMS", period=period, license="x",
            updated_at=datetime(2026, 1, 1, tzinfo=UTC),
            files=[f"series/{y}.parquet" for y in sorted(df["year"].unique())],
            method="scale_factor", calibration_version="t1", notes={"es": ["a"], "en": ["b"]},
        ).model_dump_json()
    )  # fmt: skip
    return root


@pytest.fixture
def client(tmp_path):
    make_layer(tmp_path / "harmonized", ROWS, "2011-11-01/2012-02-29", bands=True)
    return TestClient(create_app(tmp_path))


@pytest.fixture
def full_client(tmp_path):
    rows = [
        row(y, m, A, mr=y - 2000, me=y - 2000)
        for y in (2010, 2011, 2012)
        for m in range(1, 13)
    ]  # fmt: skip
    make_layer(tmp_path / "harmonized", rows, "2010-01-01/2012-12-31")
    return TestClient(create_app(tmp_path))


def test_calendar_circle(client):
    r = client.post("/calendar", json={"area": CIRCLE})
    assert r.status_code == 200, r.text
    b = r.json()
    meta = b["meta"]
    assert meta["source"] == "src FIRMS" and meta["period"] == "2011-11-01/2012-02-29"
    assert meta["method"] == "scale_factor" and meta["calibration_version"] == "t1"
    assert meta["retrospective"] is True and meta["alert_system"] is False
    assert meta["estimated_note_es"] and meta["estimated_note_en"]
    assert b["scale"] == "viirs_eq" and b["n_cells"] > 0
    assert b["period"] == {"start": "2011-11", "end": "2012-02"}
    assert b["area"]["type"] == "circle"
    months = {(m["year"], m["month"]): m for m in b["months"]}
    assert len(months) == 4
    assert months[(2011, 12)]["viirs_eq_status"] == "estimated"
    assert months[(2011, 12)]["viirs_eq"] == 1.5 and months[(2011, 12)]["modis_eq_status"] == "observed"
    assert months[(2011, 12)]["viirs_reported"] is None  # FAR cell excluded; sensor not available
    assert months[(2012, 1)]["viirs_eq"] == 3.0 and months[(2012, 1)]["cells"] == 2
    assert months[(2012, 2)]["modis_eq"] is None  # month without data in the layer
    assert {y["year"] for y in b["years"]} == {2011, 2012}
    band = b["band"]
    assert band["verified"] is False and band["target"] == "viirs_eq"
    assert band["band_method"] == "block_proportional"
    assert "Sin verificar" in band["note_es"] and "nverified" in band["note_en"]
    (m,) = band["month"]
    assert (m["year"], m["month"]) == (2011, 12) and m["lo"] == 1.0 and m["hi"] == 3.0
    assert m["verified"] is False
    assert band["year"][0]["hi"] > 0
    json.dumps(b, allow_nan=False)


def test_calendar_preset_and_range(client):
    r = client.post("/calendar", json={"preset": "cordoba", "start": "2011-12", "end": "2012-01"})
    assert r.status_code == 200, r.text
    b = r.json()
    assert [(m["year"], m["month"]) for m in b["months"]] == [(2011, 12), (2012, 1)]
    assert b["n_cells"] > 1000
    # scale modis_eq: band is for that target, no estimated modis rows -> empty
    r = client.post("/calendar", json={"preset": "cordoba", "scale": "modis_eq"})
    assert r.json()["band"]["target"] == "modis_eq" and r.json()["band"]["month"] == []


def test_range_clipped_to_layer_period(client):
    b = client.post("/calendar", json={"area": CIRCLE, "start": "2000-01", "end": "2030-01"}).json()
    assert b["period"] == {"start": "2011-11", "end": "2012-02"}


def test_empty_area_gives_zeros_not_nan(client):
    b = client.post("/calendar", json={"area": EMPTY_CIRCLE, "start": "2012-01", "end": "2012-01"}).json()
    (m,) = b["months"]
    assert b["n_cells"] > 0 and m["cells"] == 0
    assert m["modis_reported"] == 0 and m["viirs_reported"] == 0 and m["modis_eq"] == 0 and m["viirs_eq"] == 0


def test_stats(full_client):
    r = full_client.post("/stats", json={"preset": "cordoba", "scale": "modis_eq"})
    assert r.status_code == 200, r.text
    b = r.json()
    assert {"meta", "area", "period", "scale", "climatology", "anomaly", "key_figures"} <= set(b)
    an = b["anomaly"]
    assert an["ref"] == {"year": 2012, "month": 12}
    assert an["ref_label_es"] == "último mes disponible (retrospectivo)"
    assert an["ref_label_en"] == "latest available month (retrospective)"
    # the reference year (2012, value 12) is not part of its own baseline
    assert b["climatology"]["baseline_years"] == [2010, 2011]
    assert "linear" in b["climatology"]["quantile_method"]
    assert an["value"] == 12 and an["median"] == 10.5 and an["n"] == 2
    assert len(b["climatology"]["months"]) == 12
    first = b["climatology"]["months"][0]
    assert {"median", "p10", "p25", "p75", "p90"} <= set(first)
    assert first["p10"] <= first["p25"] <= first["median"] <= first["p75"] <= first["p90"]
    assert an["p25"] <= an["median"] <= an["p75"]
    assert b["key_figures"]["most_active_month"]["value"] == 12
    json.dumps(b, allow_nan=False)


def test_stats_ref_and_baseline(full_client):
    body = {"area": CIRCLE, "scale": "modis_eq", "ref": "2011-06", "baseline": [2010, 2010]}
    b = full_client.post("/stats", json=body).json()
    assert b["anomaly"]["ref"] == {"year": 2011, "month": 6}
    assert b["climatology"]["baseline_years"] == [2010]
    assert (
        b["anomaly"]["median"] == 10
        and b["anomaly"]["ref_label_en"] != "latest available month (retrospective)"
    )
    assert full_client.post("/stats", json={"area": CIRCLE, "baseline": [2012, 2010]}).status_code == 422
    assert full_client.post("/stats", json={"area": CIRCLE, "ref": "2011-13"}).status_code == 422


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"area": CIRCLE, "preset": "cordoba"},
        {"preset": "nowhere"},
        {"area": {"type": "circle", "lat": -31, "lon": -64, "radius_km": 1}},
        {"area": CIRCLE, "start": "2012-02", "end": "2011-12"},
        {"area": CIRCLE, "start": "2012/02"},
        {"area": CIRCLE, "start": "2020-01", "end": "2020-06"},  # outside the layer period
        {"area": CIRCLE, "scale": "bogus"},
        # ~126 km2 polygon between cell centers (-31.05 and -30.95): valid area, no cell center inside
        {"area": {"type": "polygon", "geojson": {"type": "Polygon", "coordinates": [
            [[-64.08, -31.04], [-63.93, -31.04], [-63.93, -30.96], [-64.08, -30.96], [-64.08, -31.04]]]}}},
    ],
)  # fmt: skip
@pytest.mark.parametrize("path", ["/calendar", "/stats", "/export.csv"])
def test_validation_errors_422(client, path, body):
    assert client.post(path, json=body).status_code == 422


def test_too_small_area_message(client):
    ring = [[-64.08, -31.04], [-63.93, -31.04], [-63.93, -30.96], [-64.08, -30.96], [-64.08, -31.04]]
    poly = {"type": "Polygon", "coordinates": [ring]}
    r = client.post("/calendar", json={"area": {"type": "polygon", "geojson": poly}})
    assert r.status_code == 422 and r.json()["detail"] == "area too small for the 0.1 degree grid"


def test_503_without_layer(tmp_path):
    c = TestClient(create_app(tmp_path))
    for path in ("/calendar", "/stats", "/export.csv"):
        r = c.post(path, json={"preset": "cordoba"})
        assert r.status_code == 503 and r.json()["detail"] == "harmonized layer not built"


def test_existing_endpoints_unchanged(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert [m["id"] for m in client.get("/layers").json()] == ["harmonized"]
