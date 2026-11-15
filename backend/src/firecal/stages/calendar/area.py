"""Area model for per-area calendar queries (circle or GeoJSON polygon).

Notes and limits:

- Self-intersection of polygon rings is NOT checked.
- Antimeridian crossing is not handled (Argentina does not cross it); polygon
  tests are planar in lon/lat.
- Polygon area uses a cylindrical equal-area (Lambert) projection on a sphere
  of radius R = 6371.0088 km: x = R*lon, y = R*sin(lat), then the shoelace
  formula. It is exact for edges that are straight in that projection and an
  approximation for geodesic edges (fine for the size validation it serves).
- Circle area is the spherical cap area.
"""

from __future__ import annotations

import math
from typing import Annotated, Any, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, TypeAdapter, model_validator

EARTH_RADIUS_KM = 6371.0088
KM_PER_DEG_LAT = 111.195  # ~ R * pi / 180

MAX_VERTICES = 10_000
MIN_RADIUS_KM = 5.0
MAX_RADIUS_KM = 500.0
MIN_AREA_KM2 = 100.0
# Approximate figures for reference: Argentina ~2.78 million km2, Cordoba ~165,000 km2.
MAX_AREA_KM2 = 3_000_000.0

# Argentina data box: (lat_min, lat_max, lon_min, lon_max)
ARG_BBOX = (-56.0, -21.0, -74.0, -53.0)

Ring = np.ndarray  # (N, 2) float array of [lon, lat]
_OUTSIDE = "area outside the data domain (Argentina)"


def _intersects_arg(lat_min: float, lat_max: float, lon_min: float, lon_max: float) -> bool:
    a = ARG_BBOX
    return not (lat_max < a[0] or lat_min > a[1] or lon_max < a[2] or lon_min > a[3])


def _ring_area_km2(ring: Ring) -> float:
    lon = np.radians(ring[:, 0])
    y = np.sin(np.radians(ring[:, 1]))
    shoelace = np.sum(lon[:-1] * y[1:] - lon[1:] * y[:-1])
    return abs(float(shoelace)) / 2.0 * EARTH_RADIUS_KM**2


def _parse_ring(raw: Any) -> Ring:
    try:
        arr = np.array([[float(p[0]), float(p[1])] for p in raw], dtype=float)
    except (TypeError, ValueError, IndexError, KeyError) as exc:
        raise ValueError("invalid ring coordinates") from exc
    if arr.ndim != 2 or len(arr) < 4:
        raise ValueError("ring needs at least 4 positions")
    if not np.all(np.isfinite(arr)):
        raise ValueError("coordinates must be finite")
    if np.any(np.abs(arr[:, 1]) > 90) or np.any(np.abs(arr[:, 0]) > 180):
        raise ValueError("coordinates out of range (lat +-90, lon +-180)")
    if not np.array_equal(arr[0], arr[-1]):
        raise ValueError("ring is not closed")
    return arr


def _parse_polygon(coords: Any) -> list[Ring]:
    if not isinstance(coords, (list, tuple)) or len(coords) == 0:
        raise ValueError("polygon needs at least one ring")
    return [_parse_ring(r) for r in coords]


def _extract_geometry(obj: Any) -> dict:
    if not isinstance(obj, dict):
        raise ValueError("geojson must be an object")
    t = obj.get("type")
    if t == "FeatureCollection":
        feats = obj.get("features")
        if not isinstance(feats, list) or len(feats) != 1:
            raise ValueError("FeatureCollection must have exactly one feature")
        return _extract_geometry(feats[0])
    if t == "Feature":
        geom = obj.get("geometry")
        if not isinstance(geom, dict):
            raise ValueError("Feature has no geometry")
        return geom
    return obj


def _normalize(geojson: Any) -> list[list[Ring]]:
    geom = _extract_geometry(geojson)
    t = geom.get("type")
    coords = geom.get("coordinates")
    if t == "Polygon":
        polys = [_parse_polygon(coords)]
    elif t == "MultiPolygon":
        if not isinstance(coords, (list, tuple)) or len(coords) == 0:
            raise ValueError("MultiPolygon is empty")
        polys = [_parse_polygon(p) for p in coords]
    else:
        raise ValueError("geometry must be Polygon or MultiPolygon")
    if sum(len(r) for p in polys for r in p) > MAX_VERTICES:
        raise ValueError(f"too many vertices (max {MAX_VERTICES})")
    return polys


class CircleArea(BaseModel):
    """Circle given by center and radius in km."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["circle"] = "circle"
    lat: float
    lon: float
    radius_km: float

    @model_validator(mode="after")
    def _check(self) -> CircleArea:
        if not (math.isfinite(self.lat) and -90 <= self.lat <= 90):
            raise ValueError("lat must be in [-90, 90]")
        if not (math.isfinite(self.lon) and -180 <= self.lon <= 180):
            raise ValueError("lon must be in [-180, 180]")
        if not (math.isfinite(self.radius_km) and MIN_RADIUS_KM <= self.radius_km <= MAX_RADIUS_KM):
            raise ValueError(f"radius_km must be in [{MIN_RADIUS_KM:g}, {MAX_RADIUS_KM:g}]")
        if not _intersects_arg(*bbox(self)):
            raise ValueError(_OUTSIDE)
        return self


class PolygonArea(BaseModel):
    """Polygon from GeoJSON (Polygon, MultiPolygon, Feature or 1-feature collection)."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["polygon"] = "polygon"
    geojson: dict

    _polygons: list[list[Ring]] = PrivateAttr(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> PolygonArea:
        self._polygons = _normalize(self.geojson)
        area = area_km2(self)
        if not (MIN_AREA_KM2 <= area <= MAX_AREA_KM2):
            raise ValueError(f"area must be in [{MIN_AREA_KM2:g}, {MAX_AREA_KM2:g}] km2")
        if not _intersects_arg(*bbox(self)):
            raise ValueError(_OUTSIDE)
        return self

    @property
    def polygons(self) -> list[list[Ring]]:
        """Polygons as lists of rings (outer + holes), each an (N, 2) [lon, lat] array."""
        return self._polygons


AreaSpec = Annotated[CircleArea | PolygonArea, Field(discriminator="type")]
_ADAPTER: TypeAdapter[CircleArea | PolygonArea] = TypeAdapter(AreaSpec)


def parse_area(obj: Any) -> CircleArea | PolygonArea:
    """Validate a dict (or model) into an area; raises pydantic ValidationError (a ValueError)."""
    return _ADAPTER.validate_python(obj)


def bbox(area: CircleArea | PolygonArea) -> tuple[float, float, float, float]:
    """Return (lat_min, lat_max, lon_min, lon_max)."""
    if isinstance(area, CircleArea):
        dlat = area.radius_km / KM_PER_DEG_LAT
        coslat = max(math.cos(math.radians(area.lat)), 1e-6)
        dlon = area.radius_km / (KM_PER_DEG_LAT * coslat)
        return (
            max(area.lat - dlat, -90.0),
            min(area.lat + dlat, 90.0),
            max(area.lon - dlon, -180.0),
            min(area.lon + dlon, 180.0),
        )
    pts = np.vstack([r for p in area.polygons for r in p])
    return (
        float(pts[:, 1].min()),
        float(pts[:, 1].max()),
        float(pts[:, 0].min()),
        float(pts[:, 0].max()),
    )


def _in_ring(lat: np.ndarray, lon: np.ndarray, ring: Ring) -> np.ndarray:
    inside = np.zeros(lat.shape, dtype=bool)
    x = ring[:, 0]
    y = ring[:, 1]
    for i in range(len(ring) - 1):
        x1, y1, x2, y2 = x[i], y[i], x[i + 1], y[i + 1]
        if y1 == y2:
            continue
        cond = (y1 > lat) != (y2 > lat)
        xint = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
        inside ^= cond & (lon < xint)
    return inside


def contains(area: CircleArea | PolygonArea, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """Boolean mask of points inside the area (vectorized).

    Circle: haversine distance <= radius. Polygon: even-odd ray casting over all
    rings of all polygons (holes excluded), planar in lon/lat; no antimeridian handling.
    """
    lat = np.asarray(lat, dtype=float)
    lon = np.asarray(lon, dtype=float)
    if isinstance(area, CircleArea):
        p1, p2 = math.radians(area.lat), np.radians(lat)
        dphi = p2 - p1
        dlmb = np.radians(lon) - math.radians(area.lon)
        a = np.sin(dphi / 2) ** 2 + math.cos(p1) * np.cos(p2) * np.sin(dlmb / 2) ** 2
        dist = 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))
        return dist <= area.radius_km
    inside = np.zeros(lat.shape, dtype=bool)
    for poly in area.polygons:
        for ring in poly:
            inside ^= _in_ring(lat, lon, ring)
    return inside


def area_km2(area: CircleArea | PolygonArea) -> float:
    """Area in km2 (circle: spherical cap; polygon: equal-area projection, outer minus holes)."""
    if isinstance(area, CircleArea):
        ang = area.radius_km / EARTH_RADIUS_KM
        return 2 * math.pi * EARTH_RADIUS_KM**2 * (1 - math.cos(ang))
    total = 0.0
    for poly in area.polygons:
        total += _ring_area_km2(poly[0]) - sum(_ring_area_km2(h) for h in poly[1:])
    return total


def describe(area: CircleArea | PolygonArea) -> dict:
    """JSON-safe summary for response metadata."""
    box = [round(v, 4) for v in bbox(area)]
    if isinstance(area, CircleArea):
        return {
            "type": "circle",
            "lat": area.lat,
            "lon": area.lon,
            "radius_km": area.radius_km,
            "area_km2": round(area_km2(area), 1),
            "bbox": box,
        }
    return {
        "type": "polygon",
        "n_polygons": len(area.polygons),
        "n_vertices": sum(len(r) for p in area.polygons for r in p),
        "area_km2": round(area_km2(area), 1),
        "bbox": box,
    }


# Approximate rectangle, not the official boundary (sin verificar).
PRESETS: dict[str, CircleArea | PolygonArea] = {
    "cordoba": PolygonArea(
        geojson={
            "type": "Polygon",
            "coordinates": [[[-65.8, -35.0], [-61.8, -35.0], [-61.8, -29.5], [-65.8, -29.5], [-65.8, -35.0]]],
        }
    ),
}
