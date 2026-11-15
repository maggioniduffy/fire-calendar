"""Feature tables for the SA2.4 / SA2.7 LightGBM models (cell model and block-month model).

Cell model unit: 0.1 degree cell x month x day/night. Candidate rows are those where the *source* is active in
the cell-month or in its 3x3 neighbourhood (known at prediction time); this is deliberately not "either sensor
active" as in the first design text: a row set that depends on the observed target would leak the test target
into the prediction (and zero-source rows kept only when the target fired would bias training upward). Target
detections in cell-months with no source nearby are out of reach, like SA2.2's source = 0 (their share is
reported by `CellRows.unreachable`).

Features (all from the source sensor(s), known at prediction time):
    src_cnt, src_frp, frp_per_det, src_cnt_other (other day/night, same cell-month), dn_share, is_night,
    n3 (source count in the 3x3 cells, same month and day/night, centre included), block_src (source total of
    the 2.5 degree block-month, both day/night), month (calendar, 1-12);
    Terra/Aqua variant (MODIS source only): terra_cnt, aqua_cnt, terra_frp, aqua_frp, terra_share;
    lat/lon ablation: cell_lat, cell_lon;
    SA2.9 (only when `burned` is given): ba_cell, ba_n3 = MCD64A1 burned km2 in the cell and in the 3x3 cells,
    same calendar month (independent of the sensors; cell-months without a granule count as 0).
The offset base `s_off` is the source count of the row, or the 3x3 mean (n3 / 9) when the row has no source.
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from firecal.paths import interim_dir
from firecal.stages.grid.grid import cell_center, grid_shape
from firecal.stages.harmonize.regions import block_ids

BASE_FEATURES = (
    "src_cnt",
    "src_frp",
    "frp_per_det",
    "src_cnt_other",
    "dn_share",
    "is_night",
    "n3",
    "block_src",
    "month",
)
TA_FEATURES = ("terra_cnt", "aqua_cnt", "terra_frp", "aqua_frp", "terra_share")
LATLON_FEATURES = ("cell_lat", "cell_lon")
# SA2.9, off by default: MCD64A1 burned area (km2) in the cell and in its 3x3 neighbourhood, same month.
BURNED_FEATURES = ("ba_cell", "ba_n3")
BLOCK_FEATURES = (
    "src_cnt",
    "src_frp",
    "frp_per_det",
    "src_cnt_other",
    "dn_share",
    "is_night",
    "n_src_cells",
    "month",
)


@dataclass(eq=False)
class RowSet:
    """Rows of a model: feature matrix, target, and the (month, block, day/night) position of every row."""

    X: np.ndarray  # float32 (n, p)
    names: tuple[str, ...]
    y: np.ndarray  # float64 target counts
    mi: np.ndarray  # month position (index into the pair's months)
    bi: np.ndarray  # block position (index into cube.blocks)
    dn: np.ndarray  # 0 day, 1 night
    s_off: np.ndarray  # smoothed source count used by the offset
    n_months: int
    n_blocks: int
    unreachable: float = 0.0  # target detections outside the candidate rows
    target_total: float = 0.0

    def cols(self, names) -> np.ndarray:
        return np.array([self.names.index(n) for n in names])


def monthly_cell_table(grid: pd.DataFrame) -> pd.DataFrame:
    """Sum a 0.1 degree grid frame into cell x ym x daynight x satellite (count, frp_sum)."""
    cols = ["cell_id", "ym", "dn", "satellite", "count", "frp_sum"]
    if grid.empty:
        return pd.DataFrame({c: pd.Series(dtype="float64") for c in cols})
    dates = pd.to_datetime(grid["acq_date"])
    d = pd.DataFrame(
        {
            "cell_id": grid["cell_id"].to_numpy().astype(np.int64),
            "ym": (dates.dt.year * 12 + dates.dt.month - 1).to_numpy().astype(np.int64),
            "dn": (grid["daynight"].to_numpy() == "N").astype(np.int8),
            "satellite": grid["satellite"].to_numpy().astype(str),
            "count": grid["count"].to_numpy().astype(np.float64),
            "frp_sum": grid["frp_sum"].to_numpy().astype(np.float64),
        }
    )
    return d.groupby(["cell_id", "ym", "dn", "satellite"], sort=True, as_index=False)[
        ["count", "frp_sum"]
    ].sum()


def build_monthly_cell_table(grid_dir: Path | None = None) -> pd.DataFrame:
    """Read the 0.1 degree grid one year at a time (columns needed only)."""
    grid_dir = grid_dir or interim_dir() / "firms" / "grid_0.1"
    parts = []
    for f in sorted(grid_dir.glob("year=*/part-0.parquet")):
        t = pq.read_table(f, columns=["acq_date", "satellite", "daynight", "cell_id", "count", "frp_sum"])
        parts.append(monthly_cell_table(t.to_pandas()))
    if not parts:
        return monthly_cell_table(pd.DataFrame())
    return (
        pd.concat(parts, ignore_index=True)
        .groupby(["cell_id", "ym", "dn", "satellite"], sort=True, as_index=False)[["count", "frp_sum"]]
        .sum()
    )


def _lookup(sorted_keys: np.ndarray, values: np.ndarray, query: np.ndarray) -> np.ndarray:
    """values at `query` keys (0 where absent); `sorted_keys` ascending and unique."""
    if len(sorted_keys) == 0:
        return np.zeros(len(query))
    pos = np.clip(np.searchsorted(sorted_keys, query), 0, len(sorted_keys) - 1)
    return np.where(sorted_keys[pos] == query, values[pos], 0.0)


def _safe_div(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    out = np.full(len(a), np.nan)
    np.divide(a, b, out=out, where=b > 0)
    return out


def _burned_columns(
    burned: pd.DataFrame, pos_of: dict, mi: np.ndarray, cr: np.ndarray, cc: np.ndarray, nrows: int, ncols: int
) -> dict[str, np.ndarray]:
    """Burned km2 in each row's cell and 3x3 neighbourhood for the row's month (0 where nothing is burned)."""
    b = burned[burned["ym"].isin(list(pos_of))]
    pos = np.array([pos_of[int(v)] for v in b["ym"].to_numpy()], dtype=np.int64)
    r, c = np.divmod(b["cell_id"].to_numpy().astype(np.int64), ncols)
    key = (pos * nrows + r) * ncols + c
    w = pd.Series(b["burned_km2"].to_numpy(dtype=float)).groupby(key).sum().sort_index()
    bk, bv = w.index.to_numpy(), w.to_numpy()
    own = _lookup(bk, bv, (mi * nrows + cr) * ncols + cc)
    n3 = np.zeros(len(mi))
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            r2, c2 = cr + dr, cc + dc
            ok = (r2 >= 0) & (r2 < nrows) & (c2 >= 0) & (c2 < ncols)
            q = (mi * nrows + r2) * ncols + c2
            n3 += np.where(ok, _lookup(bk, bv, np.where(ok, q, -1)), 0.0)
    return {"ba_cell": own, "ba_n3": n3}


def build_cell_rows(
    long: pd.DataFrame,
    ym: np.ndarray,
    blocks: np.ndarray,
    src_sats: tuple[str, ...],
    tgt_sats: tuple[str, ...],
    src_dense: np.ndarray,
    res: float = 0.1,
    burned: pd.DataFrame | None = None,
) -> RowSet:
    """Candidate cell rows with every feature column (base, Terra/Aqua, lat/lon) and the target.

    `ym` are the pair's months (sorted); `src_dense` is the (months, blocks, 2) source count. Months of `long`
    outside `ym` are dropped. `burned` (SA2.9, columns cell_id, ym, burned_km2) adds the `BURNED_FEATURES`
    columns at the end; without it the output is exactly what it was before SA2.9. The candidate rows do not
    change with it.
    """
    nrows, ncols = grid_shape(res)
    pos_of = {int(v): i for i, v in enumerate(ym)}
    lg = long[long["ym"].isin(list(pos_of))].copy()
    pos = np.array([pos_of[int(v)] for v in lg["ym"].to_numpy()], dtype=np.int64)
    r, c = np.divmod(lg["cell_id"].to_numpy().astype(np.int64), ncols)
    lg["key"] = ((pos * 2 + lg["dn"].to_numpy().astype(np.int64)) * nrows + r) * ncols + c
    sat = lg["satellite"].to_numpy()
    cnt, frp = lg["count"].to_numpy(), lg["frp_sum"].to_numpy()
    is_src, is_tgt = np.isin(sat, src_sats), np.isin(sat, tgt_sats)
    w = pd.DataFrame(
        {
            "key": lg["key"].to_numpy(),
            "src_cnt": np.where(is_src, cnt, 0.0),
            "src_frp": np.where(is_src, frp, 0.0),
            "tgt_cnt": np.where(is_tgt, cnt, 0.0),
            "terra_cnt": np.where(sat == "terra", cnt, 0.0),
            "aqua_cnt": np.where(sat == "aqua", cnt, 0.0),
            "terra_frp": np.where(sat == "terra", frp, 0.0),
            "aqua_frp": np.where(sat == "aqua", frp, 0.0),
        }
    )
    w = w.groupby("key", sort=True).sum()
    wk = w.index.to_numpy()
    wv = {col: w[col].to_numpy() for col in w.columns}

    # Candidate cell-months: source active in the cell (either day/night) or in any of its 8 neighbours.
    kk = wk[wv["src_cnt"] > 0]
    kcell = kk % (nrows * ncols)  # drops (month, dn): back to row * ncols + col
    pm = (kk // (nrows * ncols)) // 2
    rr, cc = np.divmod(kcell, ncols)
    cand = []
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            r2, c2 = rr + dr, cc + dc
            ok = (r2 >= 0) & (r2 < nrows) & (c2 >= 0) & (c2 < ncols)
            cand.append((pm[ok] * nrows + r2[ok]) * ncols + c2[ok])
    cand = np.unique(np.concatenate(cand)) if cand else np.empty(0, np.int64)
    cm_pos, rem = np.divmod(cand, nrows * ncols)
    cr, cc_ = np.divmod(rem, ncols)
    cell_id = cr * ncols + cc_
    lat, lon = cell_center(cell_id, res)
    bid = block_ids(lat, lon)
    bpos = np.clip(np.searchsorted(blocks, bid), 0, len(blocks) - 1)
    keep = blocks[bpos] == bid
    cm_pos, cr, cc_, lat, lon, bpos = (a[keep] for a in (cm_pos, cr, cc_, lat, lon, bpos))
    n = len(cm_pos)
    # Two rows (day, night) per candidate cell-month.
    mi = np.repeat(cm_pos, 2)
    cr2, cc2 = np.repeat(cr, 2), np.repeat(cc_, 2)
    bi = np.repeat(bpos, 2)
    dn = np.tile(np.array([0, 1], dtype=np.int64), n)
    lat2, lon2 = np.repeat(lat, 2), np.repeat(lon, 2)
    key = ((mi * 2 + dn) * nrows + cr2) * ncols + cc2
    key_other = ((mi * 2 + (1 - dn)) * nrows + cr2) * ncols + cc2

    g = {col: _lookup(wk, wv[col], key) for col in wv}
    other = _lookup(wk, wv["src_cnt"], key_other)
    n3 = np.zeros(len(key))
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            r2, c2 = cr2 + dr, cc2 + dc
            ok = (r2 >= 0) & (r2 < nrows) & (c2 >= 0) & (c2 < ncols)
            q = ((mi * 2 + dn) * nrows + r2) * ncols + c2
            n3 += np.where(ok, _lookup(wk, wv["src_cnt"], np.where(ok, q, -1)), 0.0)

    src_cnt = g["src_cnt"]
    cols = {
        "src_cnt": src_cnt,
        "src_frp": g["src_frp"],
        "frp_per_det": _safe_div(g["src_frp"], src_cnt),
        "src_cnt_other": other,
        "dn_share": _safe_div(src_cnt, src_cnt + other),
        "is_night": dn.astype(float),
        "n3": n3,
        "block_src": src_dense.sum(axis=-1)[mi, bi],
        "month": (ym[mi] % 12 + 1).astype(float),
        "terra_cnt": g["terra_cnt"],
        "aqua_cnt": g["aqua_cnt"],
        "terra_frp": g["terra_frp"],
        "aqua_frp": g["aqua_frp"],
        "terra_share": _safe_div(g["terra_cnt"], g["terra_cnt"] + g["aqua_cnt"]),
        "cell_lat": lat2,
        "cell_lon": lon2,
    }
    if burned is not None:
        cols.update(_burned_columns(burned, pos_of, mi, cr2, cc2, nrows, ncols))
    names = tuple(cols)
    X = np.column_stack([cols[k] for k in names]).astype(np.float32)
    # Smoothed source: own count, or the 3x3 mean for rows without source; rescaled inside each block-month x
    # day/night so that it keeps the source total (otherwise the smoothing adds mass and the zero-tree model
    # would not reproduce the SA2.2 block totals).
    s_raw = np.where(src_cnt > 0, src_cnt, n3 / 9.0)
    size = len(ym) * len(blocks) * 2
    grp = (mi * len(blocks) + bi) * 2 + dn
    tot_raw = np.bincount(grp, weights=s_raw, minlength=size)
    scale = np.where(tot_raw > 0, src_dense.reshape(-1) / np.where(tot_raw > 0, tot_raw, 1.0), 1.0)
    s_off = s_raw * scale[grp]
    tgt_all = float(wv["tgt_cnt"].sum())
    tgt_in = float(g["tgt_cnt"].sum())
    return RowSet(
        X=X,
        names=names,
        y=g["tgt_cnt"],
        mi=mi.astype(np.int64),
        bi=bi.astype(np.int64),
        dn=dn,
        s_off=s_off,
        n_months=len(ym),
        n_blocks=len(blocks),
        unreachable=tgt_all - tgt_in,
        target_total=tgt_all,
    )


def build_block_rows(src: np.ndarray, tgt: np.ndarray, month_idx: np.ndarray, cells: RowSet) -> RowSet:
    """Block-month x day/night rows (dense, every month and block of the pair) for the block model.

    `src`/`tgt` are (months, blocks, 2). The frp and active-cell features are aggregated from the cell rows.
    """
    nm, nb, _ = src.shape
    flat = (cells.mi * nb + cells.bi) * 2 + cells.dn
    size = nm * nb * 2
    ic = cells.names.index
    frp = np.bincount(flat, weights=cells.X[:, ic("src_frp")].astype(float), minlength=size).reshape(
        nm, nb, 2
    )
    ncell = np.bincount(flat, weights=(cells.X[:, ic("src_cnt")] > 0).astype(float), minlength=size).reshape(
        nm, nb, 2
    )
    mi, bi, dn = (a.ravel() for a in np.meshgrid(np.arange(nm), np.arange(nb), np.arange(2), indexing="ij"))
    s = src[mi, bi, dn]
    other = src[mi, bi, 1 - dn]
    cols = {
        "src_cnt": s,
        "src_frp": frp[mi, bi, dn],
        "frp_per_det": _safe_div(frp[mi, bi, dn], s),
        "src_cnt_other": other,
        "dn_share": _safe_div(s, s + other),
        "is_night": dn.astype(float),
        "n_src_cells": ncell[mi, bi, dn],
        "month": (month_idx[mi] + 1).astype(float),
    }
    names = tuple(cols)
    return RowSet(
        X=np.column_stack([cols[k] for k in names]).astype(np.float32),
        names=names,
        y=tgt[mi, bi, dn],
        mi=mi.astype(np.int64),
        bi=bi.astype(np.int64),
        dn=dn.astype(np.int64),
        s_off=s,
        n_months=nm,
        n_blocks=nb,
    )
