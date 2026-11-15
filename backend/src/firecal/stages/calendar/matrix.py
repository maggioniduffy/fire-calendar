"""Year x month matrix of an area (SA3.2) and approximate block-based band for estimated months."""

import numpy as np
import pandas as pd

from firecal.stages.calendar.store import BLOCK_DEG, YM, month_index
from firecal.stages.harmonize.regions import block_ids

VALUE_COLS = ["modis_reported", "viirs_reported", "modis_eq", "viirs_eq"]
BAND_METHOD = "block_proportional"


def months_between(start: YM, end: YM) -> pd.DataFrame:
    a, b = month_index(start), month_index(end)
    idx = np.arange(a, b + 1, dtype="int64")
    return pd.DataFrame({"year": idx // 12, "month": idx % 12 + 1})


def calendar_matrix(rows: pd.DataFrame, coverage: pd.DataFrame, start: YM, end: YM) -> pd.DataFrame:
    """One row per (year, month) in [start, end].

    Columns: modis_reported, viirs_reported, modis_eq, viirs_eq (sums over the area's cells), cells (cells
    with a row, i.e. any detection), modis_eq_status / viirs_eq_status in {"observed", "estimated", "none"}.
    A month where the sensor is available and the area has no rows is 0; where the sensor is not available
    the value is NaN. An eq value is available when the sensor is available or the month is estimated.
    """
    out = months_between(start, end)
    cov = coverage.copy()
    out = out.merge(cov, on=["year", "month"], how="left")
    for f in ("modis_available", "viirs_available", "modis_eq_estimated", "viirs_eq_estimated"):
        out[f] = out[f].fillna(False).astype(bool) if f in out else False
    if len(rows):
        g = rows.groupby(["year", "month"]).agg(
            **{c: (c, "sum") for c in VALUE_COLS}, cells=("cell_id", "nunique")
        )
        g = g.reset_index()
        g[["year", "month"]] = g[["year", "month"]].astype("int64")
        out = out.merge(g, on=["year", "month"], how="left")
    else:
        for c in VALUE_COLS:
            out[c] = np.nan
        out["cells"] = np.nan
    out["cells"] = out["cells"].fillna(0).astype("int64")
    for s in ("modis", "viirs"):
        avail = out[f"{s}_available"]
        est = out[f"{s}_eq_estimated"]
        out[f"{s}_eq_status"] = np.where(est, "estimated", np.where(avail, "observed", "none"))
        rep_ok = avail.to_numpy()
        eq_ok = (avail | est).to_numpy()
        out[f"{s}_reported"] = np.where(rep_ok, out[f"{s}_reported"].fillna(0.0), np.nan)
        out[f"{s}_eq"] = np.where(eq_ok, out[f"{s}_eq"].fillna(0.0), np.nan)
    cols = ["year", "month", *VALUE_COLS, "cells", "modis_eq_status", "viirs_eq_status"]
    return out[cols].reset_index(drop=True)


def annual(matrix: pd.DataFrame) -> pd.DataFrame:
    """Per-year totals of the matrix.

    Per value column `c`: `c` (total; NaN if no month has the sensor), `c_n_months` (months with a value),
    `c_complete` (12 months with a value, within the request) and, for eq columns, `c_estimated_months`.
    `n_months` is the number of months of that year in the request.
    """
    rows = []
    for year, g in matrix.groupby("year", sort=True):
        r: dict = {"year": int(year), "n_months": int(len(g))}
        for c in VALUE_COLS:
            v = g[c]
            n = int(v.notna().sum())
            r[c] = float(v.sum()) if n else np.nan
            r[f"{c}_n_months"] = n
            r[f"{c}_complete"] = bool(n == 12)
            if c.endswith("_eq"):
                st = g[f"{c}_status"]
                r[f"{c}_estimated_months"] = int(((st == "estimated") & v.notna()).sum())
        rows.append(r)
    return pd.DataFrame(rows)


def _share_frame(rows: pd.DataFrame, target: str, by_month: bool) -> pd.DataFrame:
    est_col = f"{target}_estimated"
    d = rows[rows[est_col].astype(bool)].copy()
    d["block"] = block_ids(d["cell_lat"].to_numpy(), d["cell_lon"].to_numpy(), BLOCK_DEG)
    keys = ["year", "month", "block"] if by_month else ["year", "block"]
    return d.groupby(keys, as_index=False)[target].sum().rename(columns={target: "area_estimate"})


def area_band(rows: pd.DataFrame, bands_month: pd.DataFrame, bands_year: pd.DataFrame, target: str) -> dict:
    """Approximate band of the area for estimated months/years, scaled from the block bands.

    For each block b and month: share_b = (area estimate of `target` in the area's cells of b) /
    (block estimate in the band table); area lo/hi = sum_b share_b * lo_b / hi_b. The same is done per year
    with `band_block_year`. Returns {"month": df, "year": df} with year, [month,] estimate, lo, hi, nominal,
    band_method="block_proportional", verified=False.

    Assumptions (all "sin verificar" for arbitrary areas): the relative error is uniform within a block;
    summing interval bounds across blocks is not a calibrated combination (it is conservative if errors
    are independent, optimistic if correlated); coverage of the interval for arbitrary areas has not been
    verified. Several routes in the same block-month are summed. Share is clipped to [0, 1]. Block-year
    bands are not the sum of block-month bands, so the two frames are not additive.
    """
    return {
        "month": _scaled(rows, bands_month, target, True),
        "year": _scaled(rows, bands_year, target, False),
    }


def _scaled(rows: pd.DataFrame, bands: pd.DataFrame, target: str, by_month: bool) -> pd.DataFrame:
    keys = ["year", "month"] if by_month else ["year"]
    cols = [*keys, "estimate", "lo", "hi", "nominal", "band_method", "verified"]
    if rows.empty or bands.empty:
        return pd.DataFrame({c: pd.Series(dtype="object") for c in cols})
    b = bands[bands["target"] == target]
    if b.empty:
        return pd.DataFrame({c: pd.Series(dtype="object") for c in cols})
    bk = [*keys, "block"]
    blk = b.groupby(bk, as_index=False).agg(
        block_estimate=("estimate", "sum"), lo=("lo", "sum"), hi=("hi", "sum"), nominal=("nominal", "first")
    )
    area = _share_frame(rows, target, by_month)
    m = blk.merge(area, on=bk, how="inner")
    if m.empty:
        return pd.DataFrame({c: pd.Series(dtype="object") for c in cols})
    be = m["block_estimate"].to_numpy(dtype=float)
    share = np.divide(m["area_estimate"].to_numpy(dtype=float), be, out=np.zeros(len(m)), where=be > 0)
    share = np.clip(share, 0.0, 1.0)
    m["estimate"] = share * be
    m["lo"] = share * m["lo"]
    m["hi"] = share * m["hi"]
    out = m.groupby(keys, as_index=False).agg(
        estimate=("estimate", "sum"), lo=("lo", "sum"), hi=("hi", "sum"), nominal=("nominal", "first")
    )
    out["band_method"] = BAND_METHOD
    out["verified"] = False
    return out[cols]
