"""Static export of the calendar (SA7.2 contract v1): the API's payloads precomputed per area as JSON.

Every file is the result of the same service functions the API calls (`calendar_payload_from`,
`stats_shared`/`stats_for_ref`, `calendar_csv`, `cell_centers_in`), so a static file equals the API answer for
the same polygon. The expensive parts are shared: one national read of the series, one area matrix per area
and scale, one climatology per reference year. JSON is compact, written atomically and in a stable order.
"""

import json
import multiprocessing
import os
import shutil
import time
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from pydantic import ValidationError

from firecal.stages.calendar.area import ARG_BBOX, PolygonArea, describe
from firecal.stages.calendar.cells import _outline
from firecal.stages.calendar.climatology import climatology, last_available
from firecal.stages.calendar.export import DETECTIONS_NOTE, _detections, calendar_csv
from firecal.stages.calendar.service import (
    CalendarRequest,
    area_matrix,
    calendar_payload_from,
    climatology_block,
    fmt_ym,
    resolve,
    stats_for_ref,
    stats_shared,
)
from firecal.stages.calendar.store import YM, SeriesStore, _empty_rows, month_index
from firecal.stages.publish.areas import SIMPLIFY_TOL_DEG, AreaDef

VERSION = 1
SCALES = ("viirs_eq", "modis_eq")
DEFAULT_AREA = "p-cordoba"
SUBTREES = ("calendar", "stats", "export", "areas", "cells")
DETECTION_SOURCE = "NASA FIRMS (MODIS, VIIRS S-NPP, VIIRS NOAA-20)"


class PreloadedStore(SeriesStore):
    """`SeriesStore` that reads the national series and bands once and filters them in memory.

    Same rows, same order and same filters as the parent (bbox, mask, month range), so payloads are equal.
    """

    def __init__(self, root: Path | None = None):
        super().__init__(root)
        self._series: pd.DataFrame | None = None
        self._bands: dict[str, pd.DataFrame] = {}

    def national(self) -> pd.DataFrame:
        if self._series is None:
            parts = [pq.read_table(p).to_pandas() for p in self._years("series", (0, 1), (9999, 12))]
            self._series = pd.concat(parts, ignore_index=True) if parts else _empty_rows()
        return self._series

    def load_area(self, bbox, mask, start: YM, end: YM) -> pd.DataFrame:
        df = self.national()
        lat_min, lat_max, lon_min, lon_max = bbox
        lat, lon = df["cell_lat"].to_numpy(), df["cell_lon"].to_numpy()
        keep = (lat >= lat_min) & (lat <= lat_max) & (lon >= lon_min) & (lon <= lon_max)
        keep &= (df["year"].to_numpy() >= start[0]) & (df["year"].to_numpy() <= end[0])
        df = df[keep]
        if mask is not None and len(df):
            df = df[np.asarray(mask(df["cell_lat"].to_numpy(), df["cell_lon"].to_numpy()), dtype=bool)]
        idx = df["year"].astype("int64") * 12 + df["month"].astype("int64") - 1
        df = df[(idx >= month_index(start)) & (idx <= month_index(end))]
        return df.reset_index(drop=True)

    def load_bands(self, blocks, start: YM, end: YM, which: str = "month") -> pd.DataFrame:
        if which not in ("month", "year"):
            raise ValueError("which must be 'month' or 'year'")
        if which not in self._bands:
            parts = [
                pq.read_table(p).to_pandas() for p in self._years(f"band_block_{which}", (0, 1), (9999, 12))
            ]
            parts = [p for p in parts if len(p)]
            self._bands[which] = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
        df = self._bands[which]
        if df.empty:
            return pd.DataFrame()
        df = df[(df["year"] >= start[0]) & (df["year"] <= end[0])]
        df = df[df["block"].isin(np.asarray(list(blocks)))]
        if which == "month":
            idx = df["year"].astype("int64") * 12 + df["month"].astype("int64") - 1
            df = df[(idx >= month_index(start)) & (idx <= month_index(end))]
        return df.reset_index(drop=True)


def dumps(obj) -> str:
    """Compact JSON (no indent), insertion order, no NaN."""
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def write_atomic(path: Path, text: str) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        f.write(text)
    os.replace(tmp, path)
    return len(text.encode("utf-8"))


def stats_static(store: SeriesStore, r, matrix: pd.DataFrame) -> dict:
    """`/stats` of every reference month of the period: shared fields plus `by_ref` and the climatologies."""
    col = r.scale
    default = last_available(matrix, col)
    clims: dict[int, pd.DataFrame] = {}
    by_ref: dict[str, dict] = {}
    for y, m in sorted({(int(a), int(b)) for a, b in zip(matrix["year"], matrix["month"], strict=True)}):
        if y not in clims:
            clims[y] = climatology(matrix, col, exclude_years=[y])
        by_ref[fmt_ym((y, m))] = stats_for_ref(matrix, col, (y, m), clims[y], chosen=True)
    return {
        **stats_shared(store, r),
        "default_ref": fmt_ym(default) if default else None,
        "climatology_by_year": {str(y): climatology_block(c) for y, c in sorted(clims.items())},
        "by_ref": by_ref,
    }


@dataclass
class _State:
    store: PreloadedStore
    enso: pd.DataFrame | None
    out: Path


_STATE: _State | None = None


def _error_text(exc: ValueError) -> str:
    if isinstance(exc, ValidationError):
        msg = exc.errors()[0]["msg"]
        return msg.removeprefix("Value error, ")
    return str(exc)


def process_area(a: AreaDef) -> dict:
    """Write every file of one area. Returns its summary row, or `{"id", "skipped": reason}`."""
    st = _STATE
    assert st is not None
    try:
        area = PolygonArea(geojson=a.geojson)
        rs = {s: resolve(st.store, CalendarRequest(area=area, scale=s)) for s in SCALES}
    except ValueError as exc:
        return {"id": a.id, "name": a.name, "skipped": _error_text(exc)}
    r0 = rs[SCALES[0]]
    cells = [[float(la), float(lo)] for la, lo in zip(r0.cell_lat, r0.cell_lon, strict=True)]
    write_atomic(
        st.out / "areas" / f"{a.id}.json",
        dumps({"id": a.id, "name": a.name, "kind": a.kind, "outline": _outline(area), "cells": cells}),
    )
    for scale, r in rs.items():
        rows, matrix = area_matrix(st.store, r)
        write_atomic(
            st.out / "calendar" / a.id / f"{scale}.json",
            dumps(calendar_payload_from(st.store, r, rows, matrix, st.enso)),
        )
        write_atomic(st.out / "stats" / a.id / f"{scale}.json", dumps(stats_static(st.store, r, matrix)))
        text, _ = calendar_csv(st.store, r, matrix)
        write_atomic(st.out / "export" / a.id / f"{scale}.csv", text)
    desc = describe(area)
    return {
        "id": a.id,
        "name": a.name,
        "kind": a.kind,
        "province_id": a.province_id,
        "bbox": desc["bbox"],
        "area_km2": desc["area_km2"],
        "n_cells": len(cells),
    }


def national_cells(store: PreloadedStore, out: Path) -> int:
    """`cells/{scale}/{YYYY-MM}.json` for every month of the layer period; returns the number of files."""
    m = store.manifest
    df = store.national()
    groups = {k: g for k, g in df.groupby(["year", "month"])}
    cov = store.coverage().set_index(["year", "month"])
    n = 0
    for y, mo in _months(
        (m.period_start.year, m.period_start.month), (m.period_end.year, m.period_end.month)
    ):
        g = groups.get((y, mo))
        for scale in SCALES:
            cells: list[list] = []
            if g is not None:
                value = g[scale].fillna(0.0)
                est = g[f"{scale}_estimated"].fillna(False).astype(bool)
                d = pd.DataFrame(
                    {
                        "la": g["cell_lat"].round(4), "lo": g["cell_lon"].round(4),
                        "v": value, "e": est.astype(int),
                    }
                )[value > 0].sort_values(["la", "lo"])  # fmt: skip
                cells = [
                    [float(la), float(lo), float(v), int(e)]
                    for la, lo, v, e in zip(d["la"], d["lo"], d["v"], d["e"], strict=True)
                ]
            write_atomic(
                out / "cells" / scale / f"{fmt_ym((y, mo))}.json",
                dumps(
                    {"month": fmt_ym((y, mo)), "scale": scale, "cells": cells, **_month_status(cov, y, mo)}
                ),
            )
            n += 1
    return n


def national_detections(
    store: PreloadedStore,
    out: Path,
    detections_dir: Path | None = None,
    years_only: Sequence[int] | None = None,
    tile_deg: float = 5,
) -> int:
    """Write compact, filtered national detections in configurable tiles, one parquet year at a time."""
    if tile_deg <= 0:
        raise ValueError("tile_deg must be positive")
    from firecal.stages.calendar.area import PolygonArea, _normalize
    from firecal.stages.calendar.export import default_detections_dir
    from firecal.stages.calendar.service import resolve

    root = Path(detections_dir) if detections_dir is not None else default_detections_dir()
    files = sorted(root.glob("product=*/year=*/part-0.parquet")) if root.is_dir() else []
    if not files:
        return 0
    # ARG bbox selects national points; `_detections` applies shared FIRMS filters.
    la0, la1, lo0, lo1 = ARG_BBOX
    geojson = {
        "type": "Polygon",
        "coordinates": [[[lo0, la0], [lo1, la0], [lo1, la1], [lo0, la1], [lo0, la0]]],
    }
    area = PolygonArea.model_construct(geojson=geojson)
    area._polygons = _normalize(geojson)
    period_start, period_end = store.manifest.period_start.year, store.manifest.period_end.year
    years = sorted(
        {
            int(f.parent.name.split("=")[1])
            for f in files
            if period_start <= int(f.parent.name.split("=")[1]) <= period_end
            and (years_only is None or int(f.parent.name.split("=")[1]) in years_only)
        }
    )
    written = 0
    for year in years:
        r = resolve(
            store, CalendarRequest.model_construct(area=area, start=f"{year:04d}-01", end=f"{year:04d}-12")
        )
        df = _detections(r, root)
        for month, group in df.groupby(pd.to_datetime(df["acq_date"]).dt.strftime("%Y-%m"), sort=True):
            points: dict[str, list[list]] = {}
            d = group.copy()
            d["lat0"] = np.floor(d["latitude"] / tile_deg) * tile_deg
            d["lon0"] = np.floor(d["longitude"] / tile_deg) * tile_deg
            d = d.sort_values(["acq_datetime", "sensor", "latitude", "longitude"])
            for row in d.itertuples(index=False):
                key = f"{row.lat0:g}_{row.lon0:g}"
                points.setdefault(key, []).append(
                    [
                        round(float(row.latitude), 4),
                        round(float(row.longitude), 4),
                        str(row.acq_date),
                        row.acq_datetime.strftime("%H%M"),
                        str(row.sensor),
                        None if pd.isna(row.frp) else float(row.frp),
                        None if pd.isna(row.daynight) else str(row.daynight),
                        (
                            str(row.confidence_class)
                            if not pd.isna(row.confidence_class)
                            else None
                            if pd.isna(row.confidence_pct)
                            else float(row.confidence_pct)
                        ),
                    ]
                )
            tiles = {k: len(v) for k, v in sorted(points.items())}
            for key, rows in points.items():
                write_atomic(out / "detections" / month / f"{key}.json", dumps(rows))
            write_atomic(
                out / "detections" / month / "index.json",
                dumps({"month": month, "tile_deg": tile_deg, "tiles": tiles}),
            )
            written += 1
    return written


def _month_status(cov: pd.DataFrame, y: int, mo: int) -> dict:
    """Additive status of a month (see `SeriesStore.coverage`): provisional, source_level, modis_drift."""
    if (y, mo) not in cov.index:
        return {"provisional": False, "source_level": None, "modis_drift": False}
    r = cov.loc[(y, mo)]
    return {
        "provisional": bool(r["provisional"]),
        "source_level": None if r["source_level"] is None else str(r["source_level"]),
        "modis_drift": bool(r["modis_drift"]),
    }


def _months(start: YM, end: YM):
    i, j = month_index(start), month_index(end)
    for k in range(i, j + 1):
        yield k // 12, k % 12 + 1


def _prune(out: Path, ids: set[str]) -> None:
    """Remove files of areas that are no longer published (full runs only)."""
    for sub in ("calendar", "stats", "export"):
        for child in (out / sub).glob("*") if (out / sub).is_dir() else []:
            if child.name not in ids:
                shutil.rmtree(child)
    for f in (out / "areas").glob("*.json") if (out / "areas").is_dir() else []:
        if f.stem not in ids:
            f.unlink()


def _tree_stats(out: Path) -> tuple[int, int]:
    files = [p for p in out.rglob("*") if p.is_file()]
    return len(files), sum(p.stat().st_size for p in files)


@dataclass
class Summary:
    n_areas: int
    skipped: list[dict]
    n_files: int
    total_bytes: int
    seconds: float


def export_static(
    out: Path,
    store: PreloadedStore,
    areas: Sequence[AreaDef],
    enso: pd.DataFrame | None,
    boundaries: dict,
    only: Sequence[str] | None = None,
    workers: int = 1,
    pre_skipped: Sequence[dict] = (),
    notes: dict | None = None,
    generated_at: datetime | None = None,
    include_detections: bool = True,
    detections_dir: Path | None = None,
    detections_tile_deg: float = 5,
) -> Summary:
    """Write the static tree under `out`. `only` restricts the areas (manifest and areas.json list those)."""
    global _STATE
    t0 = time.time()
    out = Path(out)
    todo = [a for a in areas if only is None or a.id in set(only)]
    if only is not None and (missing := set(only) - {a.id for a in todo}):
        raise ValueError(f"unknown area ids: {sorted(missing)}")
    store.national()
    store.coverage()  # read once, before forking the workers
    _STATE = _State(store, enso, out)
    if workers > 1:
        with ProcessPoolExecutor(workers, mp_context=multiprocessing.get_context("fork")) as pool:
            rows = list(pool.map(process_area, todo, chunksize=4))
    else:
        rows = [process_area(a) for a in todo]
    done = [r for r in rows if "skipped" not in r]
    skipped = [
        *pre_skipped,
        *({"name": r["name"], "reason": r["skipped"], "id": r["id"]} for r in rows if "skipped" in r),
    ]
    order = {"province": 0, "department": 1}
    names = {r["id"]: r["name"] for r in done if r["kind"] == "province"}
    done.sort(
        key=lambda r: (order[r["kind"]], names.get(r["province_id"] or r["id"], ""), r["name"], r["id"])
    )
    write_atomic(out / "areas.json", dumps({"areas": done}))
    n_cells_files = national_cells(store, out)
    n_detection_months = (
        national_detections(store, out, detections_dir, tile_deg=detections_tile_deg)
        if include_detections
        else 0
    )
    if only is None:
        _prune(out, {r["id"] for r in done})
    meta = store.meta()
    m = store.manifest
    manifest = {
        "version": VERSION,
        "generated_at": (generated_at or datetime.now(UTC)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "layer": meta["layer"],
        "calibration_version": meta["calibration_version"],
        "period": {"start": fmt_ym((m.period_start.year, m.period_start.month)),
                   "end": fmt_ym((m.period_end.year, m.period_end.month))},
        "scales": list(SCALES),
        "default_area": DEFAULT_AREA,
        "boundaries": boundaries,
        "skipped": skipped,
        "simplify_tolerance_deg": SIMPLIFY_TOL_DEG,
        "enso": enso is not None,
        "n_areas": len(done),
        "n_cells_files": n_cells_files,
        "detections": {
            "available": n_detection_months > 0,
            "fields": ["lat", "lon", "acq_date", "acq_time", "sensor", "frp", "daynight", "confidence"],
            "tile_deg": detections_tile_deg,
            "months": n_detection_months,
            "source": DETECTION_SOURCE,
            "note": DETECTIONS_NOTE,
        },
        "partial": only is not None,
        **(notes or {}),
    }  # fmt: skip
    write_atomic(out / "manifest.json", dumps(manifest))
    n_files, size = _tree_stats(out)
    return Summary(len(done), skipped, n_files, size, time.time() - t0)
