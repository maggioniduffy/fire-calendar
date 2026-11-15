"""The static files equal what the API answers for the same polygon (SA7.2 contract v1)."""

import importlib.util
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import box

from firecal.api.app import create_app
from firecal.io import enso
from firecal.stages.calendar.area import PolygonArea, contains
from firecal.stages.calendar.cells import _outline
from firecal.stages.calendar.export import _detections
from firecal.stages.calendar.service import CalendarRequest, resolve
from firecal.stages.publish.areas import AreaDef
from firecal.stages.publish.export import PreloadedStore, export_static, national_detections

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
GENERATED = datetime(2026, 1, 1, tzinfo=UTC)
YEARS = range(2009, 2015)  # 2009-2011 VIIRS-eq estimated, 2012-2014 observed
AREAS = [
    AreaDef("p-test", "province", "Test", None, box(-65.5, -34.5, -61.5, -29.5)),
    AreaDef("d-test-norte", "department", "Norte", "p-test", box(-65.5, -32.0, -61.5, -29.5)),
    AreaDef("d-test-sur", "department", "Sur", "p-test", box(-65.5, -34.5, -61.5, -32.0)),
    AreaDef("d-test-chica", "department", "Chica", "p-test", box(-64.0, -31.0, -63.95, -30.95)),
]


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(name, mod)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("world")
    wf = load_script("web_fixtures")
    wf.build_layer(tmp, YEARS)
    oni = tmp / "enso" / "oni_monthly.parquet"
    wf.build_enso(oni)
    store = PreloadedStore(tmp / "harmonized")
    out = tmp / "static"
    summary = export_static(
        out,
        store,
        AREAS,
        enso.read_enso(oni),
        {"source": "test"},
        workers=1,
        generated_at=GENERATED,
        detections_dir=tmp / "no-raw-detections",
    )
    client = TestClient(create_app(processed_dir=tmp, detections_dir=tmp / "none", enso_path=oni))
    return out, client, summary, store


def read(out: Path, *parts: str):
    return json.loads(out.joinpath(*parts).read_text(encoding="utf-8"))


def body(area: AreaDef, scale: str, **extra) -> dict:
    return {"area": {"type": "polygon", "geojson": area.geojson}, "scale": scale, **extra}


@pytest.mark.parametrize("area", AREAS[:3], ids=lambda a: a.id)
@pytest.mark.parametrize("scale", ["viirs_eq", "modis_eq"])
def test_calendar_and_csv_equal_the_api(world, area, scale):
    out, client, _, _ = world
    r = client.post("/calendar", json=body(area, scale))
    assert r.status_code == 200
    assert read(out, "calendar", area.id, f"{scale}.json") == r.json()
    c = client.post("/export.csv", json=body(area, scale, kind="calendar"))
    assert (out / "export" / area.id / f"{scale}.csv").read_bytes().decode() == c.text
    assert f'filename="firecal_calendar_{scale}_2009-01_2014-12.csv"' in c.headers["content-disposition"]


@pytest.mark.parametrize("area", AREAS[:3], ids=lambda a: a.id)
@pytest.mark.parametrize("scale", ["viirs_eq", "modis_eq"])
def test_stats_equal_the_api_for_every_reference_month(world, area, scale):
    out, client, _, _ = world
    st = read(out, "stats", area.id, f"{scale}.json")
    shared = {k: st[k] for k in ("meta", "area", "n_cells", "period", "scale")}
    assert len(st["by_ref"]) == 72  # every month of 2009-2014
    for ref, block in st["by_ref"].items():
        r = client.post("/stats", json=body(area, scale, ref=ref))
        assert r.status_code == 200, r.text
        expected = {**shared, "climatology": st["climatology_by_year"][ref[:4]], **block}
        assert r.json() == expected, ref
    # without `ref` the API answers the default month (labels of "latest available")
    d = client.post("/stats", json=body(area, scale)).json()
    last = st["by_ref"][st["default_ref"]]
    assert d["key_figures"] == last["key_figures"]
    assert d["climatology"] == st["climatology_by_year"][st["default_ref"][:4]]
    assert {k: v for k, v in d["anomaly"].items() if not k.startswith("ref_label")} == {
        k: v for k, v in last["anomaly"].items() if not k.startswith("ref_label")
    }


def test_area_file_outline_and_cells_match_the_membership_rule(world):
    out, client, _, _ = world
    a = AREAS[1]
    f = read(out, "areas", f"{a.id}.json")
    area = PolygonArea(geojson=a.geojson)
    assert f["outline"] == _outline(area) and f["kind"] == "department" and f["name"] == "Norte"
    cal = read(out, "calendar", a.id, "viirs_eq.json")
    assert len(f["cells"]) == cal["n_cells"] > 0
    # the cells of the area are exactly the cells the API's /cells endpoint answers for (every row of 2012-09)
    r = client.post("/cells", json=body(a, "viirs_eq", month="2012-09")).json()
    national = read(out, "cells", "viirs_eq", "2012-09.json")["cells"]
    inside = {tuple(c) for c in f["cells"]}
    assert {(c[0], c[1]) for c in r["cells"] and [[x["cell_lat"], x["cell_lon"]] for x in r["cells"]]} == {
        (c[0], c[1]) for c in national if (c[0], c[1]) in inside
    }
    assert sum(x["value"] for x in r["cells"]) == pytest.approx(
        sum(c[2] for c in national if (c[0], c[1]) in inside)
    )


def test_national_cells_cover_every_month_and_only_positive_values(world):
    out, _, _, _ = world
    for scale in ("viirs_eq", "modis_eq"):
        files = sorted((out / "cells" / scale).glob("*.json"))
        assert len(files) == 72
        sample = read(out, "cells", scale, "2010-09.json")
        assert sample["month"] == "2010-09" and sample["scale"] == scale
        assert sample["cells"] and all(c[2] > 0 and c[3] in (0, 1) for c in sample["cells"])
    est = read(out, "cells", "viirs_eq", "2010-09.json")["cells"]
    obs = read(out, "cells", "viirs_eq", "2013-09.json")["cells"]
    assert {c[3] for c in est} == {1} and {c[3] for c in obs} == {0}


def test_manifest_areas_and_skipped(world):
    out, _, summary, _ = world
    m = read(out, "manifest.json")
    assert m["version"] == 1 and m["period"] == {"start": "2009-01", "end": "2014-12"}
    assert m["scales"] == ["viirs_eq", "modis_eq"] and m["default_area"] == "p-cordoba"
    assert m["generated_at"] == "2026-01-01T00:00:00Z" and m["calibration_version"] == "synthetic-1"
    assert m["boundaries"] == {"source": "test"} and m["enso"] is True
    assert m["skipped"] == [
        {"name": "Chica", "reason": "area must be in [100, 3e+06] km2", "id": "d-test-chica"}
    ]
    ids = [a["id"] for a in read(out, "areas.json")["areas"]]
    assert ids == ["p-test", "d-test-norte", "d-test-sur"]  # provinces first; skipped areas are absent
    first = read(out, "areas.json")["areas"][0]
    assert set(first) == {"id", "kind", "name", "province_id", "bbox", "area_km2", "n_cells"}
    assert first["province_id"] is None and first["kind"] == "province" and first["n_cells"] > 0
    assert not (out / "calendar" / "d-test-chica").exists()
    assert summary.n_areas == 3 and summary.n_files == len([p for p in out.rglob("*") if p.is_file()])


def test_files_are_compact_and_a_parallel_run_is_identical(world, tmp_path):
    out, _, _, store = world
    text = (out / "calendar" / "p-test" / "viirs_eq.json").read_text()
    assert text == json.dumps(json.loads(text), separators=(",", ":"), ensure_ascii=False)  # no indent
    other = tmp_path / "again"
    export_static(
        other,
        store,
        AREAS,
        None,
        {"source": "test"},
        workers=2,
        generated_at=GENERATED,
        detections_dir=other.parent / "no-raw-detections",
    )
    for p in sorted(out.rglob("*")):
        if p.is_file() and p.relative_to(out).parts[0] in ("areas", "stats", "export", "cells"):
            assert p.read_bytes() == (other / p.relative_to(out)).read_bytes(), p
    assert read(other, "calendar", "p-test", "viirs_eq.json")["enso"] is None  # no ONI table: `enso: null`
    assert not list(other.rglob("*.tmp"))


def test_only_exports_those_areas_and_a_full_run_prunes_stale_ones(world, tmp_path):
    _, _, _, store = world
    out = tmp_path / "o"
    export_static(
        out,
        store,
        AREAS,
        None,
        {},
        only=["d-test-sur"],
        generated_at=GENERATED,
        detections_dir=tmp_path / "none",
    )
    assert [a["id"] for a in read(out, "areas.json")["areas"]] == ["d-test-sur"]
    assert read(out, "manifest.json")["partial"] is True
    export_static(out, store, AREAS, None, {}, generated_at=GENERATED, detections_dir=tmp_path / "none")
    assert (out / "calendar" / "p-test").is_dir() and read(out, "manifest.json")["partial"] is False
    stale = out / "calendar" / "d-gone"
    stale.mkdir()
    (stale / "x.json").write_text("{}")
    export_static(out, store, AREAS, None, {}, generated_at=GENERATED, detections_dir=tmp_path / "none")
    assert not stale.exists()
    with pytest.raises(ValueError, match="unknown area ids"):
        export_static(out, store, AREAS, None, {}, only=["nope"], generated_at=GENERATED)


@pytest.mark.parametrize(("tile_deg", "expected_key"), [(1, "-32_-65"), (5, "-35_-65")])
def test_detection_tiles_partition_counts_and_use_shared_area_filters(
    world, tmp_path, tile_deg, expected_key
):
    out, _, _, store = world
    root = tmp_path / "raw"
    folder = root / "product=modis" / "year=2012"
    folder.mkdir(parents=True)
    rows = [
        {
            "sensor": "modis",
            "satellite": "terra",
            "product": "modis",
            "acq_datetime": datetime(2012, 1, 10, 12, tzinfo=UTC),
            "acq_date": date(2012, 1, 10),
            "year": 2012,
            "daynight": "D",
            "latitude": -31.05,
            "longitude": -64.05,
            "confidence_pct": 80,
            "confidence_class": None,
            "frp": 5.0,
            "type": 0,
            "version": "6.1",
            "confidence_raw": "80",
        },
        {
            "sensor": "modis",
            "satellite": "terra",
            "product": "modis",
            "acq_datetime": datetime(2012, 1, 13, 12, tzinfo=UTC),
            "acq_date": date(2012, 1, 13),
            "year": 2012,
            "daynight": "D",
            "latitude": -40.05,
            "longitude": -60.05,
            "confidence_pct": 80,
            "confidence_class": None,
            "frp": 3.0,
            "type": 0,
            "version": "6.1",
            "confidence_raw": "80",
        },
        {
            "sensor": "modis",
            "satellite": "terra",
            "product": "modis",
            "acq_datetime": datetime(2012, 1, 11, 12, tzinfo=UTC),
            "acq_date": date(2012, 1, 11),
            "year": 2012,
            "daynight": "N",
            "latitude": -31.06,
            "longitude": -64.06,
            "confidence_pct": 10,
            "confidence_class": None,
            "frp": 2.0,
            "type": 0,
            "version": "6.1",
            "confidence_raw": "10",
        },
        {
            "sensor": "modis",
            "satellite": "terra",
            "product": "modis",
            "acq_datetime": datetime(2012, 1, 12, 12, tzinfo=UTC),
            "acq_date": date(2012, 1, 12),
            "year": 2012,
            "daynight": "D",
            "latitude": -31.07,
            "longitude": -64.07,
            "confidence_pct": 80,
            "confidence_class": None,
            "frp": 2.0,
            "type": 2,
            "version": "6.1",
            "confidence_raw": "80",
        },
    ]
    pd.DataFrame(rows).to_parquet(folder / "part-0.parquet")
    n = national_detections(store, out, root, tile_deg=tile_deg)
    assert n == 1
    idx = read(out, "detections", "2012-01", "index.json")
    assert idx["tile_deg"] == tile_deg
    assert expected_key in idx["tiles"]
    tiles = {k: read(out, "detections", "2012-01", f"{k}.json") for k in idx["tiles"]}
    assert sum(map(len, tiles.values())) == sum(idx["tiles"].values()) == 2
    a = AREAS[1]
    expected = _detections(
        resolve(store, CalendarRequest(area=PolygonArea(geojson=a.geojson), start="2012-01", end="2012-01")),
        root,
    )
    tile_rows = [p for bucket in tiles.values() for p in bucket]
    area_rows = [
        row
        for row in tile_rows
        if contains(PolygonArea(geojson=a.geojson), np.array([row[0]]), np.array([row[1]]))[0]
    ]
    assert len(tile_rows) == 2 and len(area_rows) == len(expected) == 1
    assert area_rows[0][:3] == [
        round(expected.iloc[0].latitude, 4),
        round(expected.iloc[0].longitude, 4),
        "2012-01-10",
    ]
    assert read(world[0], "manifest.json")["detections"]["tile_deg"] == 5
