"""Glue between the API and the calendar modules (SA3.5): request model, area resolution, payloads.

No FastAPI here: errors are plain `ValueError`s (the API maps them to 422).
"""

import math
import re
from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from firecal.stages.calendar.area import (
    ARG_BBOX,
    PRESETS,
    AreaSpec,
    CircleArea,
    PolygonArea,
    bbox,
    contains,
    describe,
)
from firecal.stages.calendar.climatology import anomaly, climatology, last_available
from firecal.stages.calendar.enso_split import enso_block
from firecal.stages.calendar.matrix import BAND_METHOD, annual, area_band, calendar_matrix
from firecal.stages.calendar.stats import key_figures
from firecal.stages.calendar.store import BLOCK_DEG, YM, SeriesStore
from firecal.stages.harmonize.regions import block_ids

CELL_DEG = 0.1
_YM = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")

BAND_NOTE_ES = (
    "Banda aproximada: la banda de cada bloque de 2,5° se escala por la fracción del área y se suma entre "
    "bloques. Sin verificar para áreas arbitrarias (cobertura no validada)."
)
BAND_NOTE_EN = (
    "Approximate band: the band of each 2.5 degree block is scaled by the area's share and summed across "
    "blocks. Unverified for arbitrary areas (coverage not validated)."
)
ESTIMATED_NOTE_ES = (
    "VIIRS-eq 2000-2011 es 'estimado' a partir de MODIS: no fue detectado por VIIRS (no existían focos "
    "VIIRS en esos meses)."
)
ESTIMATED_NOTE_EN = (
    "VIIRS-eq 2000-2011 is 'estimated' from MODIS: it was not detected by VIIRS (no VIIRS detections "
    "existed in those months)."
)
REF_LABEL_ES = "último mes disponible (retrospectivo)"
REF_LABEL_EN = "latest available month (retrospective)"
REF_LABEL_CHOSEN_ES = "mes de referencia elegido (retrospectivo)"
REF_LABEL_CHOSEN_EN = "chosen reference month (retrospective)"


class AreaTooSmallError(ValueError):
    """The area contains no 0.1 degree cell center."""

    def __init__(self) -> None:
        super().__init__("area too small for the 0.1 degree grid")


def parse_ym(text: str) -> YM:
    m = _YM.match(text)
    if not m:
        raise ValueError(f"invalid month {text!r}, expected YYYY-MM")
    return int(m.group(1)), int(m.group(2))


def fmt_ym(ym: YM) -> str:
    return f"{ym[0]:04d}-{ym[1]:02d}"


class CalendarRequest(BaseModel):
    """Area (explicit or preset), month range and scale."""

    model_config = ConfigDict(extra="forbid")

    area: AreaSpec | None = None
    preset: str | None = None
    start: str | None = None
    end: str | None = None
    scale: Literal["viirs_eq", "modis_eq"] = "viirs_eq"

    @field_validator("start", "end")
    @classmethod
    def _check_month(cls, v: str | None) -> str | None:
        if v is not None:
            parse_ym(v)
        return v

    @model_validator(mode="after")
    def _check(self) -> "CalendarRequest":
        if (self.area is None) == (self.preset is None):
            raise ValueError("give exactly one of 'area' or 'preset'")
        if self.preset is not None and self.preset not in PRESETS:
            raise ValueError(f"unknown preset {self.preset!r}; available: {sorted(PRESETS)}")
        if self.start and self.end and parse_ym(self.start) > parse_ym(self.end):
            raise ValueError("start must not be after end")
        return self

    def resolved_area(self) -> CircleArea | PolygonArea:
        return self.area if self.area is not None else PRESETS[self.preset]  # type: ignore[index]


class StatsRequest(CalendarRequest):
    """Request of /stats: optional reference month and baseline years [y0, y1]."""

    ref: str | None = None
    baseline: list[int] | None = None

    @field_validator("ref")
    @classmethod
    def _check_ref(cls, v: str | None) -> str | None:
        if v is not None:
            parse_ym(v)
        return v

    @field_validator("baseline")
    @classmethod
    def _check_baseline(cls, v: list[int] | None) -> list[int] | None:
        if v is not None and (len(v) != 2 or v[0] > v[1]):
            raise ValueError("baseline must be [y0, y1] with y0 <= y1")
        return v


@dataclass
class Resolved:
    area: CircleArea | PolygonArea
    start: YM
    end: YM
    scale: str
    cell_lat: np.ndarray  # centers of 0.1 degree cells inside the area
    cell_lon: np.ndarray

    @property
    def blocks(self) -> np.ndarray:
        return np.unique(block_ids(self.cell_lat, self.cell_lon, BLOCK_DEG))


def _axis(a: float, b: float) -> np.ndarray:
    k0 = math.ceil((a - CELL_DEG / 2) / CELL_DEG - 1e-9)
    k1 = math.floor((b - CELL_DEG / 2) / CELL_DEG + 1e-9)
    return np.round(np.arange(k0, k1 + 1) * CELL_DEG + CELL_DEG / 2, 4)


def cell_centers_in(area: CircleArea | PolygonArea) -> tuple[np.ndarray, np.ndarray]:
    """Centers (k*0.1 + 0.05) of the 0.1 degree cells whose center is inside the area.

    The candidate grid is clipped to the data domain (ARG_BBOX): no series cell exists outside it, and it caps
    the work for polygons with a very large bounding box.
    """
    la0, la1, lo0, lo1 = bbox(area)
    la0, la1 = max(la0, ARG_BBOX[0]), min(la1, ARG_BBOX[1])
    lo0, lo1 = max(lo0, ARG_BBOX[2]), min(lo1, ARG_BBOX[3])
    lat, lon = np.meshgrid(_axis(la0, la1), _axis(lo0, lo1), indexing="ij")
    lat, lon = lat.ravel(), lon.ravel()
    keep = contains(area, lat, lon) if len(lat) else np.zeros(0, dtype=bool)
    return lat[keep], lon[keep]


def resolve(store: SeriesStore, req: CalendarRequest) -> Resolved:
    m = store.manifest
    lo = (m.period_start.year, m.period_start.month)
    hi = (m.period_end.year, m.period_end.month)
    start = parse_ym(req.start) if req.start else lo
    end = parse_ym(req.end) if req.end else hi
    if start > end:
        raise ValueError("start must not be after end")
    start, end = max(start, lo), min(end, hi)
    if start > end:
        raise ValueError(f"requested range is outside the layer period {fmt_ym(lo)}..{fmt_ym(hi)}")
    area = req.resolved_area()
    lat, lon = cell_centers_in(area)
    if len(lat) == 0:
        raise AreaTooSmallError
    return Resolved(area, start, end, req.scale, lat, lon)


def load_rows(store: SeriesStore, r: Resolved) -> pd.DataFrame:
    return store.load_area(bbox(r.area), lambda la, lo: contains(r.area, la, lo), r.start, r.end)


def clean(obj):
    """JSON-safe copy: numpy to python, NaN/inf to None, DataFrames to records."""
    if isinstance(obj, pd.DataFrame):
        return clean(obj.astype(object).to_dict("records"))
    if isinstance(obj, dict):
        return {str(k): clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return clean(obj.tolist())
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, (np.integer, int)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        f = float(obj)
        return f if math.isfinite(f) else None
    if obj is None or isinstance(obj, str):
        return obj
    if obj is pd.NA or obj is pd.NaT:
        return None
    if isinstance(obj, (pd.Timestamp,)):
        return obj.isoformat()
    return obj


def meta(store: SeriesStore) -> dict:
    return {
        **store.meta(),
        "retrospective": True,
        "alert_system": False,
        "estimated_note_es": ESTIMATED_NOTE_ES,
        "estimated_note_en": ESTIMATED_NOTE_EN,
    }


def area_matrix(store: SeriesStore, r: Resolved) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = load_rows(store, r)
    return rows, calendar_matrix(rows, store.coverage(), r.start, r.end)


def calendar_payload(store: SeriesStore, req: CalendarRequest, enso: pd.DataFrame | None = None) -> dict:
    """`enso`: the ONI table (`firecal.io.enso.read_enso`), or None when it is not built (`enso: null`)."""
    r = resolve(store, req)
    rows, matrix = area_matrix(store, r)
    return calendar_payload_from(store, r, rows, matrix, enso)


def calendar_payload_from(
    store: SeriesStore, r: Resolved, rows: pd.DataFrame, matrix: pd.DataFrame, enso: pd.DataFrame | None
) -> dict:
    """The /calendar payload of an already resolved area (same result as `calendar_payload`)."""
    blocks = r.blocks
    bands = {
        w: store.load_bands(blocks, r.start, r.end, w)  # type: ignore[arg-type]
        for w in ("month", "year")
    }
    band = area_band(rows, bands["month"], bands["year"], r.scale)
    return clean(
        {
            "meta": meta(store),
            "area": describe(r.area),
            "n_cells": len(r.cell_lat),
            "period": {"start": fmt_ym(r.start), "end": fmt_ym(r.end)},
            "scale": r.scale,
            "months": matrix,
            "years": annual(matrix),
            "band": {
                "month": band["month"],
                "year": band["year"],
                "target": r.scale,
                "band_method": BAND_METHOD,
                "verified": False,
                "note_es": BAND_NOTE_ES,
                "note_en": BAND_NOTE_EN,
            },
            "enso": None if enso is None else enso_block(enso, matrix, r.scale, r.start, r.end),
        }
    )


def stats_shared(store: SeriesStore, r: Resolved) -> dict:
    """The /stats fields that do not depend on the reference month."""
    return clean(
        {
            "meta": meta(store),
            "area": describe(r.area),
            "n_cells": len(r.cell_lat),
            "period": {"start": fmt_ym(r.start), "end": fmt_ym(r.end)},
            "scale": r.scale,
        }
    )


def climatology_block(clim: pd.DataFrame) -> dict:
    return clean(
        {
            "months": clim,
            "baseline_years": clim.attrs["baseline_years"],
            "quantile_method": clim.attrs["quantile_method"],
        }
    )


def stats_for_ref(matrix: pd.DataFrame, col: str, ref: YM | None, clim: pd.DataFrame, chosen: bool) -> dict:
    """`anomaly` and `key_figures` of a reference month, given its climatology (`chosen`: labels)."""
    raw = anomaly(matrix, col, ref, clim)
    anom = {
        **raw,
        "ref_label_es": REF_LABEL_CHOSEN_ES if chosen else REF_LABEL_ES,
        "ref_label_en": REF_LABEL_CHOSEN_EN if chosen else REF_LABEL_EN,
    }
    return clean({"anomaly": anom, "key_figures": key_figures(matrix, col, clim, raw)})


def stats_payload(store: SeriesStore, req: StatsRequest) -> dict:
    r = resolve(store, req)
    _, matrix = area_matrix(store, r)
    col = r.scale
    ref = parse_ym(req.ref) if req.ref else last_available(matrix, col)
    base = list(range(req.baseline[0], req.baseline[1] + 1)) if req.baseline else None
    clim = climatology(matrix, col, baseline_years=base, exclude_years=[ref[0]] if ref else None)
    return {
        **stats_shared(store, r),
        "climatology": climatology_block(clim),
        **stats_for_ref(matrix, col, ref, clim, chosen=req.ref is not None),
    }
