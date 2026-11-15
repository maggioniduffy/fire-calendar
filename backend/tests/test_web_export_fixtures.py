"""The export fixtures of the web (SA4.6) carry exactly the columns of `firecal.stages.calendar.export`."""

import csv
import json
from pathlib import Path

from firecal.stages.calendar import export

FIXTURES = Path(__file__).resolve().parents[2] / "web" / "e2e" / "fixtures" / "api"
# Literal lists repeated in web/e2e/download.spec.ts; this test keeps them equal to the backend.
CALENDAR_HEADER = [
    "year", "month", "modis_reported", "viirs_reported", "modis_eq", "viirs_eq", "cells", "modis_eq_status",
    "viirs_eq_status", "source", "period", "method", "calibration_version",
]  # fmt: skip


def header(name: str) -> list[str]:
    with (FIXTURES / name).open(newline="") as f:
        return next(csv.reader(f))


def test_detections_fixture_header_is_export_py_columns_plus_source():
    assert header("export-detections-available.csv") == [*export.DETECTION_COLUMNS, "source"]
    spec = (Path(__file__).resolve().parents[2] / "web" / "e2e" / "download.spec.ts").read_text()
    for col in [*export.DETECTION_COLUMNS, "source"]:
        assert f'"{col}"' in spec


def test_calendar_fixture_header_is_the_matrix_plus_provenance():
    assert header("export-calendar-cordoba-viirs_eq.csv") == CALENDAR_HEADER
    spec = (Path(__file__).resolve().parents[2] / "web" / "e2e" / "download.spec.ts").read_text()
    for col in CALENDAR_HEADER:
        assert f'"{col}"' in spec


def test_export_fixture_headers_are_the_real_ones_and_detections_404_is_recorded():
    index = json.loads((FIXTURES / "index-inspector.json").read_text())
    cal = index["responses"]["export-calendar-cordoba-viirs_eq.csv"]
    assert cal["status"] == 200
    assert cal["headers"]["content-disposition"] == (
        'attachment; filename="firecal_calendar_viirs_eq_2005-01_2016-12.csv"'
    )
    assert index["responses"]["export-detections-cordoba-viirs_eq.json"]["status"] == 404
    assert index["synthetic"] is True
