"""Map data for one month (SA4.2): 0.1 degree cells with counts and capped raw detections.

No FastAPI here: errors are plain `ValueError`s (the API maps them to 422; no raw detections is a 404).
"""

from pathlib import Path

import pandas as pd
from pydantic import field_validator, model_validator

from firecal.stages.calendar.area import ARG_BBOX, CircleArea, PolygonArea, bbox, describe
from firecal.stages.calendar.export import DETECTIONS_NOTE, _detections
from firecal.stages.calendar.matrix import calendar_matrix
from firecal.stages.calendar.service import (
    CalendarRequest,
    clean,
    fmt_ym,
    load_rows,
    meta,
    parse_ym,
    resolve,
)
from firecal.stages.calendar.store import SeriesStore

MAX_DETECTIONS = 5000
DETECTION_FIELDS = ["latitude", "longitude", "frp", "sensor", "acq_date", "daynight"]


def _check_bbox(v: list[float] | None) -> list[float] | None:
    if v is None:
        return v
    if len(v) != 4 or not all(x == x and abs(x) != float("inf") for x in v):
        raise ValueError("bbox must be [lat_min, lat_max, lon_min, lon_max]")
    if v[0] > v[1] or v[2] > v[3]:
        raise ValueError("bbox minimum must not exceed maximum")
    return v


class CellsRequest(CalendarRequest):
    """Area (or preset), scale, one month and an optional view window [lat_min, lat_max, lon_min, lon_max]."""

    month: str
    bbox: list[float] | None = None

    @field_validator("month")
    @classmethod
    def _month(cls, v: str) -> str:
        parse_ym(v)
        return v

    @field_validator("bbox")
    @classmethod
    def _bbox(cls, v: list[float] | None) -> list[float] | None:
        return _check_bbox(v)

    @model_validator(mode="after")
    def _no_range(self) -> "CellsRequest":
        if self.start or self.end:
            raise ValueError("'start' and 'end' are not accepted; use 'month'")
        return self


class DetectionsRequest(CellsRequest):
    """Same as CellsRequest, but the view window is required."""

    @model_validator(mode="after")
    def _need_bbox(self) -> "DetectionsRequest":
        if self.bbox is None:
            raise ValueError("bbox is required")
        return self


def _month_request(req: CellsRequest) -> CalendarRequest:
    return req.model_copy(update={"start": req.month, "end": req.month})


def _outline(area: CircleArea | PolygonArea) -> list[list[list[float]]] | None:
    """Exterior rings [lon, lat] of a polygon area (None for a circle, which the client draws)."""
    if isinstance(area, CircleArea):
        return None
    return [poly[0].tolist() for poly in area.polygons]


def _window(req: CellsRequest, area: CircleArea | PolygonArea) -> tuple[float, float, float, float] | None:
    """The request bbox clipped to the area bbox and the data domain; None when they do not overlap."""
    if req.bbox is None:
        return None
    a = bbox(area)
    w = (
        max(req.bbox[0], a[0], ARG_BBOX[0]), min(req.bbox[1], a[1], ARG_BBOX[1]),
        max(req.bbox[2], a[2], ARG_BBOX[2]), min(req.bbox[3], a[3], ARG_BBOX[3]),
    )  # fmt: skip
    return None if w[0] > w[1] or w[2] > w[3] else w


def cells_payload(store: SeriesStore, req: CellsRequest) -> dict:
    """Cells with value > 0 of the month inside the area (and the optional window) plus the area total.

    `total` is the area's value for the month and scale, equal to the /calendar month value (null when the
    sensor does not cover the month), whatever the window.
    """
    r = resolve(store, _month_request(req))
    rows = load_rows(store, r)
    month = r.start
    mrow = calendar_matrix(rows, store.coverage(), month, month).iloc[0]
    total = mrow[r.scale]
    value = rows[r.scale].fillna(0.0)
    keep = value > 0
    win = _window(req, r.area)
    if req.bbox is not None:
        if win is None:
            keep &= False
        else:
            keep &= rows["cell_lat"].between(win[0], win[1]) & rows["cell_lon"].between(win[2], win[3])
    est = rows[f"{r.scale}_estimated"].fillna(False).astype(bool)
    cells = pd.DataFrame(
        {
            "cell_lat": rows["cell_lat"], "cell_lon": rows["cell_lon"],
            "value": value, "estimated": est,
        }
    )[keep].sort_values(["cell_lat", "cell_lon"])  # fmt: skip
    return clean(
        {
            "meta": meta(store),
            "area": describe(r.area),
            "outline": _outline(r.area),
            "period": {"start": fmt_ym(r.start), "end": fmt_ym(r.end)},
            "month": fmt_ym(month),
            "scale": r.scale,
            "bbox": list(win) if win else None,
            "cells": cells,
            "total": total,
            "provisional": mrow["provisional"],
            "source_level": mrow["source_level"],
            "modis_drift": mrow["modis_drift"],
        }
    )


def detections_payload(store: SeriesStore, req: DetectionsRequest, detections_dir: Path | None) -> dict:
    """Raw detections of the month in the area and window, capped at MAX_DETECTIONS.

    Raises `DetectionsUnavailableError` (a 404) when the server has no raw detections. Months where the
    scale is estimated have no raw points.
    """
    r = resolve(store, _month_request(req))
    df = _detections(r, detections_dir)
    win = _window(req, r.area)
    if win is None:
        df = df.iloc[0:0]
    else:
        df = df[df["latitude"].between(win[0], win[1]) & df["longitude"].between(win[2], win[3])]
    n = len(df)
    pts = df.head(MAX_DETECTIONS)[DETECTION_FIELDS].rename(columns={"latitude": "lat", "longitude": "lon"})
    pts["acq_date"] = pts["acq_date"].astype(str)
    return clean(
        {
            "meta": {**meta(store), "source": "NASA FIRMS (MODIS, VIIRS S-NPP, VIIRS NOAA-20)"},
            "month": fmt_ym(r.start),
            "bbox": list(win) if win else None,
            "points": pts,
            "total": n,
            "truncated": n > MAX_DETECTIONS,
            "max_points": MAX_DETECTIONS,
            "note": DETECTIONS_NOTE,
        }
    )
