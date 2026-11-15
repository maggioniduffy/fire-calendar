"""Provinces and departments of Argentina from the geoBoundaries files (SA7.2 contract v1).

ADM2 (departments) has no province field: each department goes to the ADM1 province polygon that contains its
point on surface. ADM1 is used for that lookup only and is never published. Its defects (see
`docs/research/data-sources.md`): "La Roja" is La Rioja, and Entre Rios is missing (departments that fall in
no ADM1 polygon but inside the Entre Rios bbox go to it; any other unassigned department is an error).
A province geometry is the dissolve of its departments. Every geometry is simplified once, clipped to the data
domain and rounded; the same geometry is used to compute the series and to draw the outline.
"""

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import shapely
from shapely.geometry import MultiPolygon, Polygon, box, mapping, shape
from shapely.ops import unary_union

from firecal.stages.calendar.area import ARG_BBOX, MAX_VERTICES

SIMPLIFY_TOL_DEG = 0.005  # ~550 m, far below the 0.1 degree grid
PRECISION = 1e-5  # coordinates rounded to 5 decimals (~1 m)
NAME_FIXES = {"La Roja": "La Rioja"}
ENTRE_RIOS = "Entre Ríos"
# Approximate Entre Rios bbox (lon_min, lat_min, lon_max, lat_max), unverified: only used for departments that
# no ADM1 polygon contains.
ENTRE_RIOS_BBOX = (-60.8, -34.1, -57.7, -30.0)
DOMAIN = box(ARG_BBOX[2], ARG_BBOX[0], ARG_BBOX[3], ARG_BBOX[1])  # lon_min, lat_min, lon_max, lat_max


CABA = "Ciudad Autónoma de Buenos Aires"
# Entre Rios has 17 departments (official division, unverified against a primary source here). The ADM1 file
# has no Entre Rios polygon and its Buenos Aires polygon extends over it, so a point-in-polygon lookup puts
# them in Buenos Aires (or Santa Fe or Corrientes at the edges).
ENTRE_RIOS_DEPARTMENTS = frozenset(
    {
        "colon", "concordia", "diamante", "federacion", "federal", "feliciano", "gualeguay", "gualeguaychu",
        "islas-del-ibicuy", "la-paz", "nogoya", "parana", "san-salvador", "tala", "uruguay", "victoria",
        "villaguay",
    }
)  # fmt: skip
# Departments whose ADM1 lookup is wrong (coarse ADM1 polygons), by geoBoundaries shapeID; found by comparing
# department counts per province (Cordoba has 26): name, province the data gives, province it belongs to.
OVERRIDES = {
    "61730980B21057051979490": "Santiago del Estero",  # Rivadavia (cabecera Selva), ADM1 gives Cordoba
    "61730980B13889034691247": "Tucumán",  # Tafi del Valle, ADM1 gives Catamarca
    "61730980B38664240857483": "Tucumán",  # Juan B. Alberdi, ADM1 gives Catamarca
    "61730980B63550758975873": "Salta",  # Molinos, ADM1 gives Catamarca
}


class AssignmentError(ValueError):
    """Departments that could not be assigned to a province."""


def slug(text: str) -> str:
    s = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


@dataclass
class AreaDef:
    id: str
    kind: str  # province | department
    name: str
    province_id: str | None
    geometry: Polygon | MultiPolygon
    tolerance: float = SIMPLIFY_TOL_DEG

    @property
    def geojson(self) -> dict:
        return _plain(mapping(self.geometry))


@dataclass
class Built:
    areas: list[AreaDef] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)  # {name, reason}
    assigned_by_fallback: list[str] = field(default_factory=list)  # Entre Rios bbox
    assigned_by_neighbour: list[str] = field(default_factory=list)  # closest assigned department
    corrected: list[str] = field(default_factory=list)  # "name -> province (reason)"


def _plain(obj):
    """Tuples to lists (JSON-style GeoJSON)."""
    if isinstance(obj, (list, tuple)):
        return [_plain(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _plain(v) for k, v in obj.items()}
    return obj


def _load(path: Path) -> list[tuple[str, str, object]]:
    """(shapeName, shapeID, valid geometry) of every feature, in file order."""
    data = json.loads(Path(path).read_text())
    out = []
    for f in data["features"]:
        g = shape(f["geometry"])
        if not g.is_valid:
            g = shapely.make_valid(g)
        out.append((f["properties"]["shapeName"], f["properties"].get("shapeID", ""), g))
    return out


def _polygonal(g) -> Polygon | MultiPolygon | None:
    """Only the polygonal part of a geometry (clipping can leave lines or points)."""
    if g.is_empty:
        return None
    if g.geom_type in ("Polygon", "MultiPolygon"):
        return g
    polys: list[Polygon] = []
    for part in getattr(g, "geoms", []):
        sub = _polygonal(part)
        if sub is not None:
            polys.extend(sub.geoms if sub.geom_type == "MultiPolygon" else [sub])
    return MultiPolygon(polys) if polys else None


def finish(geom, tol: float) -> Polygon | MultiPolygon | None:
    """Simplify (topology preserving), clip to the data domain, round, keep polygons only."""
    g = geom.simplify(tol, preserve_topology=True) if tol > 0 else geom
    g = g.intersection(DOMAIN)
    g = shapely.set_precision(g, PRECISION)
    if not g.is_valid:
        g = shapely.make_valid(g)
    return _polygonal(g)


def _simplified(geom, tol: float) -> tuple[Polygon | MultiPolygon | None, float]:
    """`finish` with a wider tolerance (x1.5 steps) until the area fits the API vertex limit."""
    t = tol
    while True:
        g = finish(geom, t)
        if g is None or shapely.get_num_coordinates(g) <= MAX_VERTICES or t > 0.05:
            return g, t
        t *= 1.5


NEIGHBOUR_MAX_DEG = 0.1  # a department in no ADM1 polygon joins the province of a department this close


def _assign_by_neighbour(pending: list, groups: dict, out: Built) -> list:
    """Assign leftovers to the province of the closest assigned department (closest first, then names).

    The geoBoundaries ADM1 polygons are coarse (and CABA's is displaced), so a few coastal or border
    departments fall in no polygon. Returns what stays unassigned (farther than NEIGHBOUR_MAX_DEG).
    """
    pending = list(pending)
    while pending:
        best = None
        for item in pending:
            for label, members in groups.items():
                d = min(item[2].distance(m[2]) for m in members)
                key = (d, item[0], item[1], label)
                if best is None or key < best[0]:
                    best = (key, item, label)
        if best is None or best[0][0] > NEIGHBOUR_MAX_DEG:
            break
        _, item, label = best
        groups[label].append(item)
        pending.remove(item)
        out.assigned_by_neighbour.append(f"{item[0]} -> {label}")
    return pending


def build_areas(adm1: Path, adm2: Path, tol: float = SIMPLIFY_TOL_DEG) -> Built:
    provinces = sorted(((NAME_FIXES.get(n, n), g) for n, _, g in _load(adm1)), key=lambda p: p[0])
    depts = sorted(_load(adm2), key=lambda d: (d[0], d[1]))
    out = Built()
    er_box = box(*ENTRE_RIOS_BBOX)
    groups: dict[str, list] = {}  # province name -> [(name, shapeID, geometry)]
    pending = []
    for item in depts:
        name, sid, geom = item
        pt = geom.point_on_surface()
        if not DOMAIN.covers(pt):
            out.skipped.append({"name": name, "reason": "outside the data domain"})
            continue
        lookup = next((pn for pn, pg in provinces if pg.covers(pt)), None)
        prov, why = lookup, ""
        if sid in OVERRIDES:
            prov, why = OVERRIDES[sid], "ADM1 lookup is wrong"
        elif name.startswith("Comuna "):
            prov, why = CABA, "comuna of the city"
        elif slug(name) in ENTRE_RIOS_DEPARTMENTS and er_box.covers(pt):
            prov, why = ENTRE_RIOS, "Entre Rios department, no ADM1 polygon"
        elif lookup == CABA:
            prov, why = "Buenos Aires", "ADM1 city polygon is displaced over Gran Buenos Aires"
        elif lookup is None and er_box.covers(pt):
            prov, why = ENTRE_RIOS, "no ADM1 polygon, inside the Entre Rios bbox"
            out.assigned_by_fallback.append(name)
        if why and prov != lookup:
            out.corrected.append(f"{name} -> {prov} ({why})")
        if prov is None:
            pending.append(item)
        else:
            groups.setdefault(prov, []).append(item)
    pending = _assign_by_neighbour(pending, groups, out)
    if pending:
        names = "; ".join(
            f"{n} ({g.point_on_surface().x:.3f}, {g.point_on_surface().y:.3f})" for n, _, g in pending
        )
        raise AssignmentError(f"{len(pending)} departments in no province: {names}")
    for pname in sorted(groups):
        members = sorted(groups[pname], key=lambda m: (m[0], m[1]))
        pid = f"p-{slug(pname)}"
        g, t = _simplified(unary_union([m[2] for m in members]), tol)
        if g is None:
            out.skipped.append({"name": pname, "reason": "empty after clipping"})
        else:
            out.areas.append(AreaDef(pid, "province", pname, None, g, t))
        used: set[str] = set()
        for dname, _, dg in members:
            did = base = f"d-{slug(pname)}-{slug(dname)}"
            n = 2
            while did in used:
                did = f"{base}-{n}"
                n += 1
            used.add(did)
            sg, st = _simplified(dg, tol)
            if sg is None:
                out.skipped.append({"name": f"{dname} ({pname})", "reason": "empty after clipping"})
            else:
                out.areas.append(AreaDef(did, "department", dname, pid, sg, st))
    return out
