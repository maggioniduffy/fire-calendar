"""CSV export of the calendar matrix, per-cell series and raw detections (SA3.6)."""

import calendar
import datetime as dt
import unicodedata
from pathlib import Path
from typing import Literal

import pandas as pd
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from firecal import paths
from firecal.stages.calendar.area import bbox, contains
from firecal.stages.calendar.service import (
    CalendarRequest,
    Resolved,
    area_matrix,
    fmt_ym,
    load_rows,
    resolve,
)
from firecal.stages.calendar.store import SeriesStore
from firecal.stages.grid.filters import FilterConfig, apply_filters

Kind = Literal["calendar", "cells", "detections"]

CELL_COLUMNS = [
    "year", "month", "cell_id", "cell_lat", "cell_lon", "modis_reported", "viirs_reported", "modis_eq",
    "viirs_eq", "modis_eq_estimated", "viirs_eq_estimated", "method", "calibration_version",
]  # fmt: skip
# Status columns of newer series (absent in older layers); appended after CELL_COLUMNS when present.
CELL_STATUS_COLUMNS = ["provisional", "source_level", "source_levels", "modis_drift"]
DETECTION_COLUMNS = [
    "acq_datetime", "acq_date", "sensor", "satellite", "product", "daynight", "latitude", "longitude",
    "confidence_pct", "confidence_class", "frp", "type", "version",
]  # fmt: skip
DETECTIONS_SOURCE = "NASA FIRMS (MODIS, VIIRS S-NPP, VIIRS NOAA-20); phase-1 filters applied"
DETECTIONS_NOTE = (
    "Raw detections exist only where the sensor observed. Months where the requested scale is "
    "estimated (e.g. VIIRS-eq before 2012) have no raw points: use kind=cells to get their counts "
    "per cell. Points are selected by their own location, cells by their center, so totals can "
    "differ slightly at the area edge; the series counts S-NPP only as viirs_reported, while raw "
    "VIIRS rows include NOAA-20."
)


class ExportRequest(CalendarRequest):
    kind: Kind = "calendar"


class DetectionsUnavailableError(FileNotFoundError):
    """No raw detections on this server."""


def default_detections_dir() -> Path:
    return paths.interim_dir() / "firms" / "detections"


def _ascii(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def provenance(store: SeriesStore, kind: str) -> dict[str, str]:
    """source, period, method and calibration_version of an export (ASCII-safe)."""
    m = store.meta()
    if kind == "detections":
        return {
            "source": DETECTIONS_SOURCE,
            "period": m["period"],
            "method": "raw detections",
            "calibration_version": "n/a",
        }
    return {
        "source": _ascii(m["source"]),
        "period": m["period"],
        "method": m["method"] or "unknown",
        "calibration_version": m["calibration_version"] or "unknown",
    }


def _detections(r: Resolved, detections_dir: Path | None, months: list[int] | None = None) -> pd.DataFrame:
    root = Path(detections_dir) if detections_dir is not None else default_detections_dir()
    files = sorted(root.glob("product=*/year=*/part-0.parquet")) if root.is_dir() else []
    if not files:
        raise DetectionsUnavailableError(f"raw detections not available: {root}")
    la0, la1, lo0, lo1 = bbox(r.area)
    d0 = dt.date(r.start[0], r.start[1], 1)
    d1 = dt.date(r.end[0], r.end[1], calendar.monthrange(*r.end)[1])
    flt = (
        (ds.field("latitude") >= la0) & (ds.field("latitude") <= la1)
        & (ds.field("longitude") >= lo0) & (ds.field("longitude") <= lo1)
        & (ds.field("acq_date") >= d0) & (ds.field("acq_date") <= d1)
    )  # fmt: skip
    parts = []
    for f in files:
        year = int(f.parent.name.split("=")[1])
        if r.start[0] <= year <= r.end[0]:
            parts.append(pq.read_table(f, filters=flt).to_pandas())
    parts = [p for p in parts if len(p)]
    if not parts:
        return pd.DataFrame(columns=DETECTION_COLUMNS)
    df = pd.concat(parts, ignore_index=True)
    if months is not None:
        df = df[pd.to_datetime(df["acq_date"]).dt.month.isin(months)]
    df = df[contains(r.area, df["latitude"].to_numpy(), df["longitude"].to_numpy())]
    df, _ = apply_filters(df, FilterConfig())
    return df.sort_values(["acq_datetime", "sensor", "latitude", "longitude"])[DETECTION_COLUMNS]


def export_csv(
    store: SeriesStore, req: CalendarRequest, kind: Kind, detections_dir: Path | None = None
) -> tuple[str, str]:
    """CSV text and file name for `kind` in {"calendar", "cells", "detections"}."""
    if kind not in ("calendar", "cells", "detections"):
        raise ValueError(f"unknown kind {kind!r}")
    r = resolve(store, req)
    if kind == "calendar":
        return calendar_csv(store, r, area_matrix(store, r)[1])
    prov = provenance(store, kind)
    if kind == "detections":
        df = _detections(r, detections_dir)
        df["source"] = prov["source"]
    elif kind == "cells":
        rows = load_rows(store, r).sort_values(["year", "month", "cell_id"])
        df = rows[CELL_COLUMNS + [c for c in CELL_STATUS_COLUMNS if c in rows]]
        for k in ("source", "period"):
            df[k] = prov[k]
    name = f"firecal_{kind}_{r.scale}_{fmt_ym(r.start)}_{fmt_ym(r.end)}.csv"
    return df.to_csv(index=False), name


def calendar_csv(store: SeriesStore, r: Resolved, matrix: pd.DataFrame) -> tuple[str, str]:
    """CSV text and file name of `kind=calendar` for an already resolved area and its matrix."""
    prov = provenance(store, "calendar")
    df = matrix.copy()
    for k in ("source", "period", "method", "calibration_version"):
        df[k] = prov[k]
    return df.to_csv(index=False), f"firecal_calendar_{r.scale}_{fmt_ym(r.start)}_{fmt_ym(r.end)}.csv"
