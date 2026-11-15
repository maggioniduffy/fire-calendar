import json

import pytest
from shapely.geometry import box, mapping

from firecal.stages.calendar.area import MAX_VERTICES, PolygonArea
from firecal.stages.publish.areas import AssignmentError, build_areas, slug


def feature(name, geom, sid=None):
    return {
        "type": "Feature",
        "properties": {"shapeName": name, "shapeID": sid or name},
        "geometry": mapping(geom),
    }


def write(path, feats):
    path.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    return path


def files(tmp_path, adm1, adm2):
    return (
        write(tmp_path / "a1.geojson", [feature(n, g) for n, g in adm1]),
        write(tmp_path / "a2.geojson", [feature(n, g, f"{n}-{i}") for i, (n, g) in enumerate(adm2)]),
    )


def test_slug_is_ascii_and_dashed():
    assert slug("Río Negro") == "rio-negro"
    assert slug("Ciudad Autónoma de Buenos Aires") == "ciudad-autonoma-de-buenos-aires"
    assert slug("General José de San Martín") == "general-jose-de-san-martin"


def test_assignment_names_ids_and_province_dissolve(tmp_path):
    a1, a2 = files(
        tmp_path,
        [("Córdoba", box(-66, -35, -62, -30)), ("La Roja", box(-70, -31, -66.5, -28))],
        [
            ("Capital", box(-65, -33, -64, -32)),
            ("Capital", box(-64, -33, -63, -32)),  # same name, same province: "-2"
            ("Capital", box(-69, -30, -68, -29)),  # La Rioja
            ("Punta", box(-80, -30, -79, -29)),  # outside the data domain
        ],
    )
    b = build_areas(a1, a2)
    ids = [a.id for a in b.areas]
    assert ids == [
        "p-cordoba", "d-cordoba-capital", "d-cordoba-capital-2",
        "p-la-rioja", "d-la-rioja-capital",
    ]  # fmt: skip
    prov = next(a for a in b.areas if a.id == "p-cordoba")
    assert prov.kind == "province" and prov.province_id is None
    assert prov.geometry.bounds == (-65.0, -33.0, -63.0, -32.0)  # dissolve of its departments
    dept = next(a for a in b.areas if a.id == "d-cordoba-capital-2")
    assert dept.province_id == "p-cordoba" and dept.name == "Capital"
    assert b.skipped == [{"name": "Punta", "reason": "outside the data domain"}]
    assert next(a.name for a in b.areas if a.id == "p-la-rioja") == "La Rioja"


def test_entre_rios_departments_go_to_entre_rios_even_inside_another_polygon(tmp_path):
    big = box(-64, -36, -57, -29)  # an ADM1 Buenos Aires that extends over Entre Rios
    a1, a2 = files(
        tmp_path,
        [("Buenos Aires", big)],
        [
            ("Paraná", box(-60.6, -32.0, -59.8, -31.4)),
            ("Pergamino", box(-61.0, -34.0, -60.4, -33.4)),
        ],
    )
    b = build_areas(a1, a2)
    assert {a.id for a in b.areas if a.kind == "department"} == {
        "d-entre-rios-parana", "d-buenos-aires-pergamino",
    }  # fmt: skip
    assert "p-entre-rios" in [a.id for a in b.areas]


def test_unassigned_inside_entre_rios_bbox_goes_there_and_far_ones_are_an_error(tmp_path):
    a1, a2 = files(tmp_path, [("Córdoba", box(-66, -35, -62, -30))], [("Algo", box(-60.5, -32, -59.5, -31))])
    b = build_areas(a1, a2)
    assert [a.id for a in b.areas] == ["p-entre-rios", "d-entre-rios-algo"]
    assert b.assigned_by_fallback == ["Algo"]
    a1, a2 = files(tmp_path, [("Córdoba", box(-66, -35, -62, -30))], [("Lejos", box(-70, -45, -69, -44))])
    with pytest.raises(AssignmentError, match="Lejos"):
        build_areas(a1, a2)


def test_close_unassigned_department_joins_the_neighbour_province(tmp_path):
    a1, a2 = files(
        tmp_path,
        [("Córdoba", box(-66, -35, -62, -30))],
        [("Dentro", box(-63, -33, -62.01, -32)), ("Costa", box(-61.98, -33, -61.9, -32))],  # 0.03 off
    )
    b = build_areas(a1, a2)
    assert b.assigned_by_neighbour == ["Costa -> Córdoba"]
    assert next(a for a in b.areas if a.name == "Costa").province_id == "p-cordoba"


def test_geometry_is_simplified_clipped_rounded_and_accepted_by_the_api_model(tmp_path):
    from shapely.geometry import Point

    disc = Point(-64.123456789, -33.123456789).buffer(0.5, quad_segs=64)
    a1, a2 = files(tmp_path, [("Córdoba", box(-66, -35, -62, -30))], [("D", disc)])
    area = build_areas(a1, a2, tol=0.005).areas[0]
    assert len(area.geometry.exterior.coords) < len(disc.exterior.coords)
    coords = [c for ring in area.geojson["coordinates"] for c in ring]
    assert all(round(v, 5) == v for c in coords for v in c)
    assert PolygonArea(geojson=area.geojson)  # valid for the API
    assert len(coords) < MAX_VERTICES


def test_geometry_is_clipped_to_the_data_domain(tmp_path):
    a1, a2 = files(
        tmp_path, [("Santa Cruz", box(-74, -56, -66, -50))], [("Sur", box(-73, -58, -68, -52))]
    )  # the department's centre is inside, its southern part is below -56
    area = build_areas(a1, a2).areas[0]
    assert area.geometry.bounds[1] == -56.0
