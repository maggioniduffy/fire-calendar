"""Map data for one month (SA4.2): 0.1 degree cells with counts and capped raw detections.

No FastAPI here: errors are plain `ValueError`s (the API maps them to 422; no raw detections is a 404).
"""

from pathlib import Path

import numpy as np
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
    """Area (or preset), one month, a contiguous range, or months across years."""

    month: str | None = None
    months: list[int] | None = None
    years: list[int] | None = None
    bbox: list[float] | None = None

    @field_validator("month")
    @classmethod
    def _month(cls, v: str | None) -> str | None:
        if v is not None:
            parse_ym(v)
        return v

    @field_validator("months")
    @classmethod
    def _months(cls, v: list[int] | None) -> list[int] | None:
        if v is not None and (not v or any(m < 1 or m > 12 for m in v) or len(set(v)) != len(v)):
            raise ValueError("months must be a non-empty list of distinct integers from 1 to 12")
        return v

    @field_validator("years")
    @classmethod
    def _years(cls, v: list[int] | None) -> list[int] | None:
        if v is not None and (len(v) != 2 or v[0] > v[1]):
            raise ValueError("years must be [y0, y1] with y0 <= y1")
        return v

    @field_validator("bbox")
    @classmethod
    def _bbox(cls, v: list[float] | None) -> list[float] | None:
        return _check_bbox(v)

    @model_validator(mode="after")
    def _period(self) -> "CellsRequest":
        is_month = self.month is not None
        is_range = self.start is not None or self.end is not None
        is_season = self.months is not None or self.years is not None
        if sum((is_month, is_range, is_season)) != 1:
            raise ValueError(
                "give exactly one period: 'month', both 'start' and 'end', or both 'months' and 'years'"
            )
        if is_range and (self.start is None or self.end is None):
            raise ValueError("a range requires both 'start' and 'end'")
        if is_season and (self.months is None or self.years is None):
            raise ValueError("a season requires both 'months' and 'years'")
        return self


class DetectionsRequest(CellsRequest):
    """Same as CellsRequest, but the view window is required."""

    @model_validator(mode="after")
    def _need_bbox(self) -> "DetectionsRequest":
        if self.bbox is None:
            raise ValueError("bbox is required")
        return self


def _selection(req: CellsRequest) -> tuple[CalendarRequest, str, dict]:
    if req.month is not None:
        return (
            req.model_copy(update={"start": req.month, "end": req.month}),
            "month",
            {
                "kind": "month",
                "month": req.month,
            },
        )
    if req.start is not None:
        return req.model_copy(), "range", {"kind": "range", "start": req.start, "end": req.end}
    start = f"{req.years[0]:04d}-01"
    end = f"{req.years[1]:04d}-12"
    return (
        req.model_copy(update={"start": start, "end": end}),
        "season",
        {
            "kind": "season",
            "months": req.months,
            "years": req.years,
        },
    )


def _selected_months(req: CellsRequest, r) -> list[tuple[int, int]]:
    if req.month is not None:
        return [r.start]
    if req.months is None:
        y0, m0 = r.start
        y1, m1 = r.end
        return [
            (y, m)
            for y in range(y0, y1 + 1)
            for m in range(1, 13)
            if (y, m) >= (y0, m0) and (y, m) <= (y1, m1)
        ]
    selected = [
        (year, month)
        for year in range(req.years[0], req.years[1] + 1)
        for month in req.months
        if r.start <= (year, month) <= r.end
    ]
    if not selected:
        raise ValueError("requested season is outside the layer period")
    return sorted(selected)


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
    calendar_req, kind, selection = _selection(req)
    r = resolve(store, calendar_req)
    rows = load_rows(store, r)
    selected = _selected_months(req, r)
    matrix = calendar_matrix(rows, store.coverage(), r.start, r.end)
    mrows = matrix.set_index(["year", "month"]).loc[selected]
    if isinstance(mrows, pd.Series):
        mrows = mrows.to_frame().T
    if kind == "month":
        mrow = mrows.iloc[0]
        total = mrow[r.scale]
    else:
        total = None if mrows[r.scale].isna().any() else mrows[r.scale].sum()
    selected_rows = rows[pd.MultiIndex.from_frame(rows[["year", "month"]]).isin(selected)]
    if kind == "month":
        cell_frame = pd.DataFrame(
            {
                "cell_lat": rows["cell_lat"],
                "cell_lon": rows["cell_lon"],
                "value": rows[r.scale].fillna(0.0),
                "estimated": rows[f"{r.scale}_estimated"].fillna(False).astype(bool),
            }
        )
    else:
        cell_frame = selected_rows.groupby(["cell_lat", "cell_lon"], as_index=False).agg(
            value=(r.scale, lambda s: s.fillna(0.0).sum()),
            estimated=(f"{r.scale}_estimated", "any"),
        )
    keep = cell_frame["value"] > 0
    win = _window(req, r.area)
    if req.bbox is not None:
        if win is None:
            keep &= False
        else:
            keep &= cell_frame["cell_lat"].between(win[0], win[1]) & cell_frame["cell_lon"].between(
                win[2], win[3]
            )
    cells = cell_frame[keep].sort_values(["cell_lat", "cell_lon"])  # fmt: skip
    payload = {
        "meta": meta(store),
        "area": describe(r.area),
        "outline": _outline(r.area),
        "scale": r.scale,
        "bbox": list(win) if win else None,
        "cells": cells,
        "total": total,
    }
    if kind == "month":
        return clean(
            {
                "meta": meta(store),
                "area": describe(r.area),
                "outline": _outline(r.area),
                "period": {"start": fmt_ym(r.start), "end": fmt_ym(r.end)},
                "month": fmt_ym(r.start),
                "scale": r.scale,
                "bbox": list(win) if win else None,
                "cells": cells,
                "total": total,
                "provisional": mrow["provisional"],
                "source_level": mrow["source_level"],
                "modis_drift": mrow["modis_drift"],
            }
        )
    else:
        start, end = selected[0], selected[-1]
        levels = [level for level in mrows["source_level"].dropna().unique()]
        payload.update(
            {
                "period": {"start": fmt_ym(start), "end": fmt_ym(end)},
                "months": len(selected),
                "selection": selection,
                "provisional": bool(mrows["provisional"].fillna(False).any()),
                "source_level": levels[0] if len(levels) == 1 else ("mixed" if levels else None),
                "modis_drift": bool(mrows["modis_drift"].fillna(False).any()),
            }
        )
    return clean(payload)


def detections_payload(store: SeriesStore, req: DetectionsRequest, detections_dir: Path | None) -> dict:
    """Raw detections in the selected period, area and window, capped at MAX_DETECTIONS.

    Raises `DetectionsUnavailableError` (a 404) when the server has no raw detections. Months where the
    scale is estimated have no raw points.
    """
    calendar_req, kind, selection = _selection(req)
    r = resolve(store, calendar_req)
    selected = _selected_months(req, r)
    df = _detections(r, detections_dir, months=req.months if kind == "season" else None)
    win = _window(req, r.area)
    if win is None:
        df = df.iloc[0:0]
    else:
        df = df[df["latitude"].between(win[0], win[1]) & df["longitude"].between(win[2], win[3])]
    n = len(df)
    if kind != "month" and n > MAX_DETECTIONS:
        indices = np.rint(np.linspace(0, n - 1, MAX_DETECTIONS)).astype(int)
        points = df.iloc[indices]
    else:
        points = df.head(MAX_DETECTIONS)
    pts = points[DETECTION_FIELDS].rename(columns={"latitude": "lat", "longitude": "lon"})
    pts["acq_date"] = pts["acq_date"].astype(str)
    if kind == "month":
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
    return clean(
        {
            "meta": {**meta(store), "source": "NASA FIRMS (MODIS, VIIRS S-NPP, VIIRS NOAA-20)"},
            "bbox": list(win) if win else None,
            "points": pts,
            "total": n,
            "truncated": n > MAX_DETECTIONS,
            "max_points": MAX_DETECTIONS,
            "note": DETECTIONS_NOTE,
            "period": {"start": fmt_ym(selected[0]), "end": fmt_ym(selected[-1])},
            "selection": selection,
            **({"sampled": True} if n > MAX_DETECTIONS else {}),
        }
    )
