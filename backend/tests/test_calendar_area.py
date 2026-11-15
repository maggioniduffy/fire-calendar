import json
import math

import numpy as np
import pytest
from pydantic import ValidationError

from firecal.stages.calendar import area as A


def box(lon0, lat0, lon1, lat1):
    return [[lon0, lat0], [lon1, lat0], [lon1, lat1], [lon0, lat1], [lon0, lat0]]


def poly_geom(*rings):
    return {"type": "Polygon", "coordinates": list(rings)}


BIG = box(-65.0, -35.0, -62.0, -32.0)


def test_valid_circle():
    c = A.parse_area({"type": "circle", "lat": -31.4, "lon": -64.2, "radius_km": 50})
    assert isinstance(c, A.CircleArea)
    assert A.area_km2(c) == pytest.approx(math.pi * 50**2, rel=0.01)
    lat_min, lat_max, lon_min, lon_max = A.bbox(c)
    assert lat_max - lat_min == pytest.approx(2 * 50 / 111.195)
    assert lon_min < -64.2 < lon_max


def test_circle_contains():
    c = A.parse_area({"type": "circle", "lat": -31.4, "lon": -64.2, "radius_km": 50})
    lat = np.array([-31.4, -31.4, -31.4 + 0.3, -31.4 + 0.6])
    lon = np.array([-64.2, -64.2 + 0.2, -64.2, -64.2])
    assert A.contains(c, lat, lon).tolist() == [True, True, True, False]


@pytest.mark.parametrize("r", [4.9, 500.1])
def test_circle_radius_invalid(r):
    with pytest.raises(ValidationError):
        A.parse_area({"type": "circle", "lat": -31.4, "lon": -64.2, "radius_km": r})


def test_circle_lat_lon_range_and_outside():
    with pytest.raises(ValidationError):
        A.parse_area({"type": "circle", "lat": 95, "lon": -64, "radius_km": 50})
    with pytest.raises(ValidationError):
        A.parse_area({"type": "circle", "lat": -31, "lon": -200, "radius_km": 50})
    with pytest.raises(ValidationError, match="Argentina"):
        A.parse_area({"type": "circle", "lat": 40.0, "lon": 10.0, "radius_km": 50})


def test_polygon_forms():
    geom = poly_geom(BIG)
    for gj in (
        geom,
        {"type": "Feature", "properties": {}, "geometry": geom},
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": geom}]},
    ):
        p = A.parse_area({"type": "polygon", "geojson": gj})
        assert len(p.polygons) == 1 and p.polygons[0][0].shape == (5, 2)
        assert A.bbox(p) == (-35.0, -32.0, -65.0, -62.0)


def test_multipolygon():
    gj = {
        "type": "MultiPolygon",
        "coordinates": [[box(-65, -35, -63, -33)], [box(-62, -35, -60, -33)]],
    }
    p = A.parse_area({"type": "polygon", "geojson": gj})
    assert len(p.polygons) == 2
    mask = A.contains(p, np.array([-34.0, -34.0, -34.0]), np.array([-64.0, -61.0, -62.5]))
    assert mask.tolist() == [True, True, False]


def test_polygon_hole():
    hole = box(-64.0, -34.0, -63.0, -33.0)
    p = A.parse_area({"type": "polygon", "geojson": poly_geom(BIG, hole)})
    mask = A.contains(p, np.array([-33.5, -32.5]), np.array([-63.5, -63.5]))
    assert mask.tolist() == [False, True]
    full = A.parse_area({"type": "polygon", "geojson": poly_geom(BIG)})
    assert A.area_km2(p) < A.area_km2(full)


def test_area_box_equator():
    # 1x1 degree box near the equator, ~12,364 km2 (placed outside Argentina; check the formula)
    p = A.PolygonArea.model_construct(type="polygon", geojson={})
    p._polygons = [[np.array(box(0, 0, 1, 1), dtype=float)]]
    assert A.area_km2(p) == pytest.approx(12364, rel=0.01)


def test_unclosed_ring():
    ring = BIG[:-1]
    with pytest.raises(ValidationError, match="closed"):
        A.parse_area({"type": "polygon", "geojson": poly_geom(ring)})


def test_too_few_positions():
    ring = [[-65, -35], [-64, -34], [-65, -35]]
    with pytest.raises(ValidationError, match="4 positions"):
        A.parse_area({"type": "polygon", "geojson": poly_geom(ring)})


def test_too_many_vertices():
    n = A.MAX_VERTICES + 10
    t = np.linspace(0, 2 * math.pi, n)
    ring = np.column_stack([-64 + 3 * np.cos(t), -33 + 3 * np.sin(t)]).tolist()
    ring[-1] = ring[0]
    with pytest.raises(ValidationError, match="too many vertices"):
        A.parse_area({"type": "polygon", "geojson": poly_geom(ring)})


def test_area_too_small_and_large():
    with pytest.raises(ValidationError, match="area must be"):
        A.parse_area({"type": "polygon", "geojson": poly_geom(box(-64, -33, -63.99, -32.99))})
    with pytest.raises(ValidationError, match="area must be"):
        A.parse_area({"type": "polygon", "geojson": poly_geom(box(-74, -56, -50, -10))})


def test_outside_argentina():
    with pytest.raises(ValidationError, match="Argentina"):
        A.parse_area({"type": "polygon", "geojson": poly_geom(box(0, 40, 3, 43))})


def test_wrong_type():
    with pytest.raises(ValidationError):
        A.parse_area({"type": "square", "lat": 0})
    with pytest.raises(ValidationError, match="Polygon or MultiPolygon"):
        A.parse_area({"type": "polygon", "geojson": {"type": "Point", "coordinates": [-64, -33]}})


def test_feature_collection_two_features():
    geom = poly_geom(BIG)
    gj = {
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "geometry": geom}] * 2,
    }
    with pytest.raises(ValidationError, match="exactly one"):
        A.parse_area({"type": "polygon", "geojson": gj})


def test_describe_json_safe():
    c = A.parse_area({"type": "circle", "lat": -31.4, "lon": -64.2, "radius_km": 50})
    p = A.parse_area({"type": "polygon", "geojson": poly_geom(BIG)})
    for a, t in ((c, "circle"), (p, "polygon")):
        d = A.describe(a)
        assert d["type"] == t
        json.dumps(d)
    assert A.describe(p)["n_vertices"] == 5


def test_preset_cordoba():
    p = A.PRESETS["cordoba"]
    assert 150_000 < A.area_km2(p) < 300_000
    assert A.contains(p, np.array([-31.4]), np.array([-64.2])).all()
