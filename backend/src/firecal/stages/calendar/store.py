"""Data access to the published layer `harmonized` (series and block bands).

Only the published schema is used (see `harmonize/series.py`): never the scale-factor method itself, so the
method can be replaced later (same schema).
"""

from collections.abc import Callable
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from firecal.layers.manifest import LayerManifest, load_manifest
from firecal.paths import processed_dir

LAYER_ID = "harmonized"
# Block size (degrees) of the published band tables (`block` id = row * ncols + col, see regions.block_ids).
BLOCK_DEG = 2.5

BBox = tuple[float, float, float, float]  # lat_min, lat_max, lon_min, lon_max
Mask = Callable[[np.ndarray, np.ndarray], np.ndarray]
YM = tuple[int, int]


def month_index(ym: YM) -> int:
    return ym[0] * 12 + ym[1] - 1


class SeriesStore:
    """Read-only access to `data/processed/harmonized/`."""

    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root is not None else processed_dir() / LAYER_ID
        self._manifest: LayerManifest | None = None
        self._coverage: pd.DataFrame | None = None

    @property
    def manifest(self) -> LayerManifest:
        if self._manifest is None:
            self._manifest = load_manifest(self.root / "manifest.json")
        return self._manifest

    def _years(self, sub: str, start: YM, end: YM) -> list[Path]:
        out = []
        for p in sorted((self.root / sub).glob("*.parquet")):
            if p.stem.isdigit() and start[0] <= int(p.stem) <= end[0]:
                out.append(p)
        return out

    def load_area(self, bbox: BBox, mask: Mask | None, start: YM, end: YM) -> pd.DataFrame:
        """Series rows whose cell center is in `bbox` and `mask`, for months in [start, end]."""
        lat_min, lat_max, lon_min, lon_max = bbox
        flt = (
            (ds.field("cell_lat") >= lat_min)
            & (ds.field("cell_lat") <= lat_max)
            & (ds.field("cell_lon") >= lon_min)
            & (ds.field("cell_lon") <= lon_max)
        )
        parts = [pq.read_table(p, filters=flt).to_pandas() for p in self._years("series", start, end)]
        if not parts:
            return _empty_rows()
        df = pd.concat(parts, ignore_index=True)
        if mask is not None and len(df):
            keep = np.asarray(mask(df["cell_lat"].to_numpy(), df["cell_lon"].to_numpy()), dtype=bool)
            df = df[keep]
        idx = df["year"].astype("int64") * 12 + df["month"].astype("int64") - 1
        df = df[(idx >= month_index(start)) & (idx <= month_index(end))]
        return df.reset_index(drop=True)

    def coverage(self) -> pd.DataFrame:
        """One row per (year, month) of the layer period with national sensor/estimation flags.

        Estimation is decided by sensor availability per month, so a national flag is the right per-month
        flag (a cell without fires has no row). A month in the period with no rows is all False.
        """
        if self._coverage is not None:
            return self._coverage
        m = self.manifest
        a, b = m.period_start, m.period_end
        idx = pd.period_range(f"{a.year}-{a.month:02d}", f"{b.year}-{b.month:02d}", freq="M")
        base = pd.DataFrame({"year": idx.year.astype("int64"), "month": idx.month.astype("int64")})
        flags = ["modis_available", "viirs_available", "modis_eq_estimated", "viirs_eq_estimated"]
        parts = []
        cols = [
            "year",
            "month",
            "modis_reported",
            "viirs_reported",
            "modis_eq_estimated",
            "viirs_eq_estimated",
        ]
        for p in sorted((self.root / "series").glob("*.parquet")):
            d = pq.read_table(p, columns=cols).to_pandas()
            if d.empty:
                continue
            g = (
                d.assign(
                    modis_available=d["modis_reported"].notna(),
                    viirs_available=d["viirs_reported"].notna(),
                    modis_eq_estimated=d["modis_eq_estimated"].astype(bool),
                    viirs_eq_estimated=d["viirs_eq_estimated"].astype(bool),
                )
                .groupby(["year", "month"], as_index=False)[flags]
                .max()
            )
            parts.append(g)
        if parts:
            got = pd.concat(parts, ignore_index=True)
            got[["year", "month"]] = got[["year", "month"]].astype("int64")
            out = base.merge(got, on=["year", "month"], how="left")
        else:
            out = base.copy()
            for f in flags:
                out[f] = False
        for f in flags:
            out[f] = out[f].fillna(False).astype(bool)
        self._coverage = out
        return out

    def load_bands(self, blocks, start: YM, end: YM, which: str = "month") -> pd.DataFrame:
        """Block bands (`band_block_month` or `band_block_year`) for `blocks` in [start, end]."""
        if which not in ("month", "year"):
            raise ValueError("which must be 'month' or 'year'")
        parts = [pq.read_table(p).to_pandas() for p in self._years(f"band_block_{which}", start, end)]
        parts = [p for p in parts if len(p)]
        if not parts:
            return pd.DataFrame()
        df = pd.concat(parts, ignore_index=True)
        df = df[df["block"].isin(np.asarray(list(blocks)))]
        if which == "month":
            idx = df["year"].astype("int64") * 12 + df["month"].astype("int64") - 1
            df = df[(idx >= month_index(start)) & (idx <= month_index(end))]
        return df.reset_index(drop=True)

    def meta(self) -> dict:
        m = self.manifest
        notes = m.notes or {}
        return {
            "layer": m.id,
            "source": m.source,
            "period": m.period,
            "method": m.method,
            "calibration_version": m.calibration_version,
            "notes": {"es": list(notes.get("es", [])), "en": list(notes.get("en", []))},
        }


def _empty_rows() -> pd.DataFrame:
    from firecal.stages.harmonize.series import _empty_series

    return _empty_series()
