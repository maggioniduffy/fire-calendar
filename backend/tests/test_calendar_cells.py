import pytest
from fastapi.testclient import TestClient
from test_calendar_api import CIRCLE, EMPTY_CIRCLE, FAR, ROWS, A, B, make_layer
from test_calendar_export import dets  # noqa: F401  (fixture)

from firecal.api.app import create_app


@pytest.fixture
def client(tmp_path):
    make_layer(tmp_path / "harmonized", ROWS, "2011-11-01/2012-02-29", bands=True)
    return TestClient(create_app(tmp_path, detections_dir=tmp_path / "none"))


@pytest.fixture
def dclient(tmp_path, dets):  # noqa: F811
    make_layer(tmp_path / "harmonized", ROWS, "2011-11-01/2012-02-29", bands=True)
    return TestClient(create_app(tmp_path, detections_dir=dets))


def cells(client, month, area=CIRCLE, **kw):
    r = client.post("/cells", json={"area": area, "month": month, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def test_month_filter_and_values(client):
    b = cells(client, "2012-01", scale="viirs_eq")
    assert b["month"] == "2012-01"
    assert b["period"] == {"start": "2012-01", "end": "2012-01"}
    assert {(c["cell_lat"], c["cell_lon"]): c["value"] for c in b["cells"]} == {A: 2.0, B: 1.0}
    assert all(c["estimated"] is False for c in b["cells"])
    assert b["total"] == 3.0
    nov = cells(client, "2011-11")
    got = [(c["cell_lat"], c["cell_lon"], c["value"], c["estimated"]) for c in nov["cells"]]
    assert got == [(*A, 1.0, True)]


def test_month_response_keeps_legacy_shape(client):
    b = cells(client, "2012-01")
    assert list(b) == [
        "meta",
        "area",
        "outline",
        "period",
        "month",
        "scale",
        "bbox",
        "cells",
        "total",
        "provisional",
        "source_level",
        "modis_drift",
    ]


def test_range_sums_month_cells_and_totals(client):
    r = client.post("/cells", json={"area": CIRCLE, "start": "2011-11", "end": "2012-01"})
    assert r.status_code == 200, r.text
    b = r.json()
    month_cells = [cells(client, month) for month in ("2011-11", "2011-12", "2012-01")]
    expected = {}
    estimated = {}
    for one in month_cells:
        for cell in one["cells"]:
            key = (cell["cell_lat"], cell["cell_lon"])
            expected[key] = expected.get(key, 0) + cell["value"]
            estimated[key] = estimated.get(key, False) or cell["estimated"]
    got = {(c["cell_lat"], c["cell_lon"]): c for c in b["cells"]}
    assert len(b["cells"]) == len(got)
    assert {key: c["value"] for key, c in got.items()} == expected
    assert {key: c["estimated"] for key, c in got.items()} == estimated
    assert b["total"] == sum(one["total"] for one in month_cells)
    assert b["months"] == 3
    assert b["period"] == {"start": "2011-11", "end": "2012-01"}
    assert b["selection"] == {"kind": "range", "start": "2011-11", "end": "2012-01"}


def test_season_selects_calendar_months_in_each_year(client):
    r = client.post("/cells", json={"area": CIRCLE, "months": [11, 1], "years": [2011, 2012]})
    assert r.status_code == 200, r.text
    b = r.json()
    assert len(b["cells"]) == 2
    assert {(c["cell_lat"], c["cell_lon"]): (c["value"], c["estimated"]) for c in b["cells"]} == {
        A: (3.0, True),
        B: (1.0, False),
    }
    assert b["total"] == 4.0
    assert b["months"] == 2
    assert b["period"] == {"start": "2011-11", "end": "2012-01"}
    assert b["selection"] == {"kind": "season", "months": [11, 1], "years": [2011, 2012]}


def test_range_total_is_null_if_a_selected_month_is_uncovered(client):
    r = client.post("/cells", json={"area": CIRCLE, "start": "2012-01", "end": "2012-02"})
    assert r.status_code == 200, r.text
    assert r.json()["total"] is None


def test_area_filter_excludes_far_cell(client):
    big = {"type": "circle", "lat": -36.0, "lon": -62.0, "radius_km": 500}
    inside = cells(client, "2011-12")
    assert [(c["cell_lat"], c["cell_lon"]) for c in inside["cells"]] == [A]  # FAR is outside CIRCLE
    wide = cells(client, "2011-12", area=big)
    assert [(c["cell_lat"], c["cell_lon"]) for c in wide["cells"]] == [FAR]  # A is outside the big circle
    assert wide["total"] == 2.5


def test_scale_changes_values(client):
    b = cells(client, "2012-01", scale="modis_eq")
    assert {(c["cell_lat"], c["cell_lon"]): c["value"] for c in b["cells"]} == {A: 1.0, B: 4.0}
    assert b["total"] == 5.0


@pytest.mark.parametrize("scale", ["viirs_eq", "modis_eq"])
@pytest.mark.parametrize("month", ["2011-11", "2011-12", "2012-01", "2012-02"])
def test_total_equals_calendar_month_value(client, scale, month):
    b = cells(client, month, scale=scale)
    cal = client.post("/calendar", json={"area": CIRCLE, "scale": scale}).json()
    row = next(m for m in cal["months"] if f"{m['year']:04d}-{m['month']:02d}" == month)
    assert b["total"] == row[scale]
    if b["total"] is not None:
        assert sum(c["value"] for c in b["cells"]) == pytest.approx(b["total"])


def test_cells_value_positive_only_and_empty_month(client):
    b = cells(client, "2012-01", area=EMPTY_CIRCLE)
    assert b["cells"] == []
    assert b["total"] == 0.0
    assert cells(client, "2012-02")["cells"] == []


def test_bbox_clips_cells_not_total(client):
    full = cells(client, "2012-01")
    win = cells(client, "2012-01", bbox=[-31.1, -31.0, -64.1, -64.0])
    assert [(c["cell_lat"], c["cell_lon"]) for c in win["cells"]] == [A]
    assert win["total"] == full["total"]
    away = cells(client, "2012-01", bbox=[-20.0, -19.0, -60.0, -59.0])
    assert away["cells"] == [] and away["bbox"] is None


def test_preset_returns_outline(client):
    r = client.post("/cells", json={"preset": "cordoba", "month": "2012-01"})
    assert r.status_code == 200
    ring = r.json()["outline"][0]
    assert ring[0] == ring[-1] and len(ring) == 5
    assert cells(client, "2012-01")["outline"] is None  # circles are drawn by the client


@pytest.mark.parametrize(
    "body",
    [
        {"area": CIRCLE, "month": "2012-13"},
        {"area": CIRCLE, "month": "jan"},
        {"area": CIRCLE},
        {"area": CIRCLE, "month": "2012-01", "start": "2012-01"},
        {"area": CIRCLE, "month": "2012-01", "bbox": [1, 0, 0, 1]},
        {"area": CIRCLE, "month": "2012-01", "bbox": [0, 1, 2]},
        {"area": CIRCLE, "preset": "cordoba", "month": "2012-01"},
        {"area": CIRCLE, "month": "2020-01"},  # outside the layer period
        {"area": EMPTY_CIRCLE, "month": "2012-01"},  # no cell centers... see below
    ],
)
def test_bad_requests_are_422(client, body):
    r = client.post("/cells", json=body)
    if body.get("area") == EMPTY_CIRCLE:
        assert r.status_code == 200  # a valid area without data is not an error: no cells, total 0
        return
    assert r.status_code == 422, r.text


def test_detections_window_and_cap(dclient, monkeypatch):
    body = {"area": CIRCLE, "month": "2012-01", "bbox": [-32, -30, -65, -63]}
    r = dclient.post("/detections", json=body)
    assert r.status_code == 200, r.text
    b = r.json()
    assert list(b) == ["meta", "month", "bbox", "points", "total", "truncated", "max_points", "note"]
    assert b["total"] == 2 and not b["truncated"]
    assert {p["sensor"] for p in b["points"]} == {"modis", "viirs"}
    assert set(b["points"][0]) == {"lat", "lon", "frp", "sensor", "acq_date", "daynight"}
    assert all(p["acq_date"].startswith("2012-01") for p in b["points"])
    # window excluding the modis point
    small = dclient.post("/detections", json={**body, "bbox": [-31.3, -31.1, -64.3, -64.1]}).json()
    assert {p["sensor"] for p in small["points"]} == {"viirs"}
    from firecal.stages.calendar import cells as mod

    monkeypatch.setattr(mod, "MAX_DETECTIONS", 1)
    capped = dclient.post("/detections", json=body).json()
    assert len(capped["points"]) == 1 and capped["truncated"] and capped["total"] == 2
    assert capped["points"] == b["points"][:1]
    assert "sampled" not in capped


def test_detections_season_includes_only_selected_months(dclient):
    body = {"area": CIRCLE, "bbox": [-32, -30, -65, -63], "months": [12, 1], "years": [2011, 2012]}
    r = dclient.post("/detections", json=body)
    assert r.status_code == 200, r.text
    b = r.json()
    assert {p["acq_date"] for p in b["points"]} == {"2011-12-31", "2012-01-10", "2012-01-20"}, b["points"]
    assert b["total"] == 4
    assert b["period"] == {"start": "2011-12", "end": "2012-01"}
    assert b["selection"] == {"kind": "season", "months": [12, 1], "years": [2011, 2012]}


def test_detections_range_has_range_metadata(dclient):
    body = {"area": CIRCLE, "bbox": [-32, -30, -65, -63], "start": "2011-12", "end": "2012-01"}
    r = dclient.post("/detections", json=body)
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["total"] == 4
    assert b["period"] == {"start": "2011-12", "end": "2012-01"}
    assert b["selection"] == {"kind": "range", "start": "2011-12", "end": "2012-01"}


def test_detections_range_samples_across_period(dclient, monkeypatch):
    from firecal.stages.calendar import cells as mod

    monkeypatch.setattr(mod, "MAX_DETECTIONS", 2)
    body = {"area": CIRCLE, "bbox": [-32, -30, -65, -63], "start": "2011-12", "end": "2012-01"}
    b = dclient.post("/detections", json=body).json()
    assert len(b["points"]) == 2
    assert b["points"][0]["acq_date"] == "2011-12-31"
    assert b["points"][-1]["acq_date"] == "2012-01-20"
    assert b["total"] == 4
    assert b["truncated"] is True
    assert b["sampled"] is True


@pytest.mark.parametrize(
    "selection",
    [
        {},
        {"month": "2012-01", "start": "2012-01", "end": "2012-02"},
        {"start": "2012-01"},
        {"start": "2012-01", "end": "2012-02", "month": "2012-01"},
        {"months": [1]},
        {"years": [2011, 2012]},
        {"months": [], "years": [2011, 2012]},
        {"months": [1, 1], "years": [2011, 2012]},
        {"months": [13], "years": [2011, 2012]},
        {"months": [1], "years": [2012, 2011]},
        {"months": [1], "years": [2011, 2012], "start": "2011-01", "end": "2012-01"},
    ],
)
def test_invalid_period_combinations_are_422(client, selection):
    r = client.post("/cells", json={"area": CIRCLE, **selection})
    assert r.status_code == 422, r.text


def test_detections_requires_bbox_and_month(dclient):
    assert dclient.post("/detections", json={"area": CIRCLE, "month": "2012-01"}).status_code == 422
    assert dclient.post("/detections", json={"area": CIRCLE, "bbox": [-32, -30, -65, -63]}).status_code == 422


def test_detections_404_when_unavailable(client):
    r = client.post("/detections", json={"area": CIRCLE, "month": "2012-01", "bbox": [-32, -30, -65, -63]})
    assert r.status_code == 404
    assert "not available" in r.json()["detail"]
