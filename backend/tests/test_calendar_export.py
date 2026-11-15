import csv
import io
from datetime import UTC, date, datetime

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from test_calendar_api import CIRCLE, EMPTY_CIRCLE, FAR, ROWS, A, B, make_layer

from firecal.api.app import create_app
from firecal.stages.calendar.export import CELL_COLUMNS, DETECTION_COLUMNS, DETECTIONS_NOTE


def det(sensor, lat, lon, day, **kw):
    base = {
        "sensor": sensor, "satellite": "terra" if sensor == "modis" else "snpp",
        "product": sensor, "acq_datetime": datetime(day.year, day.month, day.day, 12, 0, tzinfo=UTC),
        "acq_date": day, "year": day.year, "daynight": "D", "latitude": lat, "longitude": lon,
        "confidence_raw": "80", "confidence_pct": 80, "confidence_class": None, "frp": 5.0,
        "brightness": 330.0, "type": 0, "version": "6.1",
    }  # fmt: skip
    return {**base, **kw}


@pytest.fixture
def dets(tmp_path):
    d = tmp_path / "detections"
    modis = pd.DataFrame(
        [
            det("modis", -31.05, -64.05, date(2012, 1, 10)),  # kept
            det("modis", -31.06, -64.06, date(2012, 1, 11), confidence_pct=10),  # dropped by filter
            det("modis", -31.06, -64.07, date(2012, 1, 12), type=2),  # dropped by filter (type)
            det("modis", -40.05, -60.05, date(2012, 1, 10)),  # outside the area
            det("modis", -31.05, -64.05, date(2012, 2, 3)),  # outside the date range
            det("modis", -31.07, -64.07, date(2011, 12, 31)),  # outside the date range
        ]
    )
    viirs = pd.DataFrame(
        [
            det("viirs", -31.2, -64.2, date(2012, 1, 20), confidence_pct=None, confidence_class="nominal"),
            det("viirs", -31.2, -64.2, date(2012, 1, 21), confidence_pct=None, confidence_class="low"),
        ]
    )
    for name, df in (("modis", modis), ("viirs-snpp", viirs)):
        p = d / f"product={name}" / "year=2012"
        p.mkdir(parents=True)
        df.to_parquet(p / "part-0.parquet")
    p = d / "product=modis" / "year=2011"
    p.mkdir(parents=True)
    modis[modis["acq_date"] == date(2011, 12, 31)].to_parquet(p / "part-0.parquet")
    return d


@pytest.fixture
def client(tmp_path, dets):
    make_layer(tmp_path / "harmonized", ROWS, "2011-11-01/2012-02-29", bands=True)
    return TestClient(create_app(tmp_path, detections_dir=dets))


def read(resp):
    return list(csv.DictReader(io.StringIO(resp.text)))


def test_calendar_csv(client):
    r = client.post("/export.csv", json={"area": CIRCLE})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert r.headers["content-disposition"].startswith('attachment; filename="')
    assert r.headers["x-firecal-source"] == "src FIRMS"
    assert r.headers["x-firecal-period"] == "2011-11-01/2012-02-29"
    assert r.headers["x-firecal-method"] == "scale_factor"
    assert r.headers["x-firecal-calibration"] == "t1"
    rows = read(r)
    assert len(rows) == 4
    assert list(rows[0]) == [
        "year", "month", "modis_reported", "viirs_reported", "modis_eq", "viirs_eq", "cells",
        "modis_eq_status", "viirs_eq_status", "source", "period", "method", "calibration_version",
    ]  # fmt: skip
    dec = next(x for x in rows if x["month"] == "12")
    assert (
        dec["viirs_eq"] == "1.5" and dec["viirs_eq_status"] == "estimated" and dec["method"] == "scale_factor"
    )
    assert dec["source"] == "src FIRMS" and dec["calibration_version"] == "t1"


def test_cells_csv(client):
    r = client.post("/export.csv", json={"area": CIRCLE, "kind": "cells"})
    assert r.status_code == 200
    rows = read(r)
    assert len(rows) == 4  # FAR cell excluded; A: 3 months, B: 1
    assert list(rows[0])[: len(CELL_COLUMNS)] == CELL_COLUMNS
    assert {"source", "period"} <= set(rows[0])
    assert {(float(x["cell_lat"]), float(x["cell_lon"])) for x in rows} == {A, B}
    est = [x for x in rows if x["year"] == "2011"]
    assert all(x["viirs_eq_estimated"] == "True" for x in est)
    assert [(x["year"], x["month"]) for x in rows] == sorted((x["year"], x["month"]) for x in rows)
    assert all(x["method"] == "scale_factor" and x["calibration_version"] == "t1" for x in rows)


def test_detections_csv(client):
    r = client.post(
        "/export.csv", json={"area": CIRCLE, "kind": "detections", "start": "2012-01", "end": "2012-01"}
    )
    assert r.status_code == 200
    assert r.headers["x-firecal-note"] == DETECTIONS_NOTE and "kind=cells" in DETECTIONS_NOTE
    assert "FIRMS" in r.headers["x-firecal-source"]
    rows = read(r)
    assert list(rows[0])[: len(DETECTION_COLUMNS)] == DETECTION_COLUMNS and "source" in rows[0]
    # in area and dates, passing the phase-1 filters: 1 MODIS + 1 VIIRS nominal
    assert sorted((x["sensor"], x["acq_date"]) for x in rows) == [
        ("modis", "2012-01-10"),
        ("viirs", "2012-01-20"),
    ]
    assert all(float(x["latitude"]) != FAR[0] for x in rows)


def test_detections_range_spans_files(client):
    rows = read(client.post("/export.csv", json={"area": CIRCLE, "kind": "detections"}))
    assert {x["acq_date"] for x in rows} == {"2011-12-31", "2012-01-10", "2012-01-20", "2012-02-03"}


def test_detections_missing_404(tmp_path):
    make_layer(tmp_path / "harmonized", ROWS, "2011-11-01/2012-02-29")
    for c in (
        TestClient(create_app(tmp_path)),  # default dir (data/interim) is absent in tests
        TestClient(create_app(tmp_path, detections_dir=tmp_path / "nope")),
    ):
        r = c.post("/export.csv", json={"area": CIRCLE, "kind": "detections"})
        if r.status_code == 200:  # a real dataset exists at the default location
            continue
        assert r.status_code == 404
        assert r.json()["detail"] == "raw detections not available on this server; use kind=cells"
    r = TestClient(create_app(tmp_path, detections_dir=tmp_path / "nope")).post(
        "/export.csv", json={"area": CIRCLE, "kind": "detections"}
    )
    assert r.status_code == 404


def test_cells_and_calendar_need_no_detections(tmp_path):
    make_layer(tmp_path / "harmonized", ROWS, "2011-11-01/2012-02-29")
    c = TestClient(create_app(tmp_path, detections_dir=tmp_path / "nope"))
    assert c.post("/export.csv", json={"area": CIRCLE, "kind": "cells"}).status_code == 200


def test_empty_area_csv_zeros(client):
    r = client.post("/export.csv", json={"area": EMPTY_CIRCLE, "start": "2012-01", "end": "2012-01"})
    (row,) = read(r)
    assert row["modis_reported"] == "0.0" and row["viirs_eq"] == "0.0" and row["cells"] == "0"
    r = client.post("/export.csv", json={"area": EMPTY_CIRCLE, "kind": "cells"})
    assert read(r) == []
    assert r.text.strip().split(",")[:3] == ["year", "month", "cell_id"]


def test_export_errors(client):
    assert client.post("/export.csv", json={"area": CIRCLE, "kind": "bogus"}).status_code == 422
    r = client.post("/export.csv", json={"area": CIRCLE, "start": "2012-02", "end": "2011-12"})
    assert r.status_code == 422
