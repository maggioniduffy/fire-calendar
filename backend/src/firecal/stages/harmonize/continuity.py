"""SA2.10 post-MODIS continuity: forward holdouts ("MODIS-off simulation"), chain vs direct,
frozen-artifact check.

Everything here follows the pre-registration in `plan/02-harmonization.md` (P1, P2, P5, P8, P9 and Revision 1)
mechanically; no threshold is chosen here. Terms:

- route: how NOAA-20 counts become MODIS-equivalent (Terra + Aqua) counts: `chain` (NOAA-20 -> S-NPP ->
MODIS) or
  `direct` (one NOAA-20 -> MODIS factor); both are in `route.py`.
- cell: one (cut-off, test year, route) forward result, or one (test year, route) leave-one-year-out
result, with
  block-month arrays (months, blocks).
- Scores are on block-year totals (primary) and block-month totals; "pooled" is sum|err| / sum(obs) over
all rows
  of all cells.
"""

import datetime as dt
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from firecal.paths import interim_dir
from firecal.stages.harmonize.evaluate import PAIRS, pair_data
from firecal.stages.harmonize.intervals import conformal_from_residuals
from firecal.stages.harmonize.metrics import relative_bias, wape
from firecal.stages.harmonize.regions import (
    MODIS_SATS,
    Cube,
    build_cube,
    build_monthly_region_table,
    restrict_blocks,
    ym_of,
)
from firecal.stages.harmonize.route import (
    LEGS,
    ROUTE_PAIR,
    ROUTES,
    fit_route,
    inner_residuals_from,
    loyo_predictions,
)

CUTOFFS = (2021, 2022, 2023, 2024)
LAST_FULL_YEAR = 2025
TRAIN_END_FINAL = ym_of(2025, 12)  # fitted period of the published route in `.2`
PARTIAL_YEAR = 2026
PARTIAL_LAST_YM = ym_of(
    2026, 7
)  # last 2026 standard-processing month of the data (complete months only inside)
GATE_FROM_YM = ym_of(2026, 1)  # P8 gates months from here; earlier flags are a diagnostic
SEED = 20261114
N_BOOT = 1000
CI = (2.5, 97.5)
BIAS_TOLERANCE = 0.005  # P5: the chain's |national bias| may be worse than the direct factor's by 0.5 points
COVERAGE_OK = (0.75, 0.85)  # P1: acceptable range around the nominal 80 %
LOYO_SPLIT = ((2018, 2021), (2022, 2025))  # Revision 1: a fixed split, not the P3 epoch
FLAG_SATS = (
    "noaa20",
    *MODIS_SATS,
)  # satellites whose historically flagged months are left out of the secondary

ROUTE_LABEL = {"chain": "chain NOAA-20 -> S-NPP -> MODIS", "direct": "direct NOAA-20 -> MODIS"}


# --------------------------------------------------------------------------- inputs


@dataclass(eq=False)
class Inputs:
    cube: (
        Cube  # on the blocks of the base calibration; partial / in-progress / NRT months of 2026 are invalid
    )
    flagged: dict[
        str, set[int]
    ]  # historical partial satellite-months (before 2026): diagnostic, not excluded
    gated_out: pd.DataFrame  # 2026 satellite-months left out and why
    dropped_counts: float  # detections (cube total) in blocks outside the base calibration


def completeness_sets(comp: pd.DataFrame) -> tuple[dict[str, set[int]], dict[str, set[int]], pd.DataFrame]:
    """(cube exclusions, historical flags, 2026 table of excluded months) from the completeness table (P8).

    Excluded from the cube: every NRT satellite-month and every month from 2026-01 whose status is not
    `complete`. Earlier `partial` months only go to the flags (the `.1` fits and the primary results keep
    them).
    """
    c = comp.copy()
    gated = c["ym"] >= GATE_FROM_YM
    bad = (c["level"] == "nrt") | (gated & (c["status"] != "complete"))
    exclude = {s: set(g["ym"].astype(int)) for s, g in c[bad].groupby("satellite")}
    old = c[(~gated) & (c["status"] == "partial")]
    flagged = {s: set(g["ym"].astype(int)) for s, g in old.groupby("satellite")}
    out = c[bad & gated][["satellite", "month", "level", "status", "days_with_detections", "threshold_days"]]
    out = out.assign(threshold_days=out["threshold_days"].round(1))
    return exclude, flagged, out.reset_index(drop=True)


def load_inputs(blocks: np.ndarray, grid_dir=None, completeness_path=None) -> Inputs:
    """The cube of every standard-processing month (2000-2026-07) on `blocks`, never with an NRT row."""
    comp = pd.read_parquet(completeness_path or interim_dir() / "firms" / "completeness.parquet")
    exclude, flagged, gated_out = completeness_sets(comp)
    raw = build_cube(build_monthly_region_table(grid_dir, through=None), exclude)
    cube = restrict_blocks(raw, blocks)
    dropped = float(sum(a.sum() for a in raw.data.values()) - sum(a.sum() for a in cube.data.values()))
    return Inputs(cube, flagged, gated_out, dropped)


# --------------------------------------------------------------------------- results containers


@dataclass(eq=False)
class Cell:
    cutoff: int | None  # None: leave-one-year-out
    test_year: int
    route: str
    ym: np.ndarray
    obs: np.ndarray  # (months, blocks) observed MODIS (Terra + Aqua)
    pred: np.ndarray  # MODIS-eq from NOAA-20
    src: np.ndarray  # NOAA-20 counts
    lo_m: np.ndarray | None = None  # conformal block-month bounds (months, blocks)
    hi_m: np.ndarray | None = None
    lo_y: np.ndarray | None = None  # conformal block-year bounds (blocks,)
    hi_y: np.ndarray | None = None

    @property
    def horizon(self) -> int | None:
        return None if self.cutoff is None else self.test_year - self.cutoff


@dataclass(eq=False)
class Forward:
    cells: list[Cell]  # full test years 2022-2025 and the 2026 partial block, every cut-off x route
    ks: dict[tuple[int, str], dict[str, float]]  # (cut-off, route) -> k per leg
    train_months: dict[int, dict[str, int]]  # cut-off -> months per leg


# --------------------------------------------------------------------------- forward holdouts (P2)


def run_forward(cube: Cube, cutoffs=CUTOFFS, log=None) -> Forward:
    """P2: for each cut-off refit every leg and `k` on months <= end of the cut-off year, no gap, and score
    the
    full years after it up to 2025 plus the 2026 block of complete months (reported apart, never in P5)."""
    cells: list[Cell] = []
    ks: dict[tuple[int, str], dict[str, float]] = {}
    months: dict[int, dict[str, int]] = {}
    dall = pair_data(cube, PAIRS[ROUTE_PAIR], PARTIAL_LAST_YM)
    src_tot, obs_tot = dall.src, dall.tgt.sum(axis=-1)
    for c in cutoffs:
        end = ym_of(c, 12)
        months[c] = {n: len(pair_data(cube, PAIRS[n], end).ym) for n in (*LEGS, ROUTE_PAIR)}
        dtr = pair_data(cube, PAIRS[ROUTE_PAIR], end)
        for route in ROUTES:
            fit = fit_route(cube, route, end)
            ks[c, route] = fit.k
            res = inner_residuals_from(dtr, loyo_predictions(cube, route, end))
            for y in (*range(c + 1, LAST_FULL_YEAR + 1), PARTIAL_YEAR):
                te = (dall.year_idx == y) & (dall.ym > end)
                if not te.any():
                    continue
                pred = fit.predict(src_tot[te], dall.month_idx[te])
                s_bm = src_tot[te].sum(axis=-1)
                cf = conformal_from_residuals(res, pred, s_bm)
                cells.append(
                    Cell(
                        c,
                        y,
                        route,
                        dall.ym[te],
                        obs_tot[te],
                        pred,
                        s_bm,
                        cf.month[0],
                        cf.month[1],
                        cf.year[0],
                        cf.year[1],
                    )  # fmt: skip
                )
            if log:
                log(f"cut-off {c} {route}: k {fit.k}")
    return Forward(cells, ks, months)


def run_loyo(cube: Cube, end: int = TRAIN_END_FINAL) -> list[Cell]:
    """Leave-one-year-out with a 6-month gap over 2018-05..2025-12 for both routes, alongside the forward
    runs."""
    d = pair_data(cube, PAIRS[ROUTE_PAIR], end)
    obs_tot, src_tot = d.tgt.sum(axis=-1), d.src.sum(axis=-1)
    cells = []
    for route in ROUTES:
        for y, te, pred in loyo_predictions(cube, route, end):
            cells.append(Cell(None, y, route, d.ym[te], obs_tot[te], pred, src_tot[te]))
    return cells


# --------------------------------------------------------------------------- scoring


def _month_keep(cell: Cell, flagged: dict[str, set[int]] | None) -> np.ndarray:
    if not flagged:
        return np.ones(len(cell.ym), dtype=bool)
    bad = set().union(*(flagged.get(s, set()) for s in FLAG_SATS))
    return ~np.isin(cell.ym, list(bad))


def _rows(cell: Cell, level: str, flagged=None):
    """(obs, pred, src, lo, hi) flat arrays of one cell at a level; bounds None when the cell has none."""
    keep = _month_keep(cell, flagged)
    if level == "block-month":
        o, p, s = cell.obs[keep], cell.pred[keep], cell.src[keep]
        lo, hi = (cell.lo_m[keep], cell.hi_m[keep]) if cell.lo_m is not None and keep.all() else (None, None)
    else:
        o, p, s = cell.obs[keep].sum(axis=0), cell.pred[keep].sum(axis=0), cell.src[keep].sum(axis=0)
        lo, hi = (cell.lo_y, cell.hi_y) if cell.lo_y is not None and keep.all() else (None, None)
    return (
        o.ravel(),
        p.ravel(),
        s.ravel(),
        None if lo is None else np.asarray(lo).ravel(),
        None if hi is None else np.asarray(hi).ravel(),
    )


def score(cells: list[Cell], level: str = "block-year", flagged=None) -> dict:
    """Pooled WAPE and national bias; coverage and relative width on rows with source > 0 (P1, Revision 1)."""
    parts = [_rows(c, level, flagged) for c in cells]
    if not parts:
        return {"wape": np.nan, "bias": np.nan, "n": 0, "coverage": np.nan, "width": np.nan, "n_cov": 0}
    o = np.concatenate([p[0] for p in parts])
    pr = np.concatenate([p[1] for p in parts])
    out = {"wape": wape(o, pr), "bias": relative_bias(o, pr), "n": len(o), "obs": float(o.sum())}
    if all(p[3] is not None for p in parts):
        s = np.concatenate([p[2] for p in parts])
        lo = np.concatenate([p[3] for p in parts])
        hi = np.concatenate([p[4] for p in parts])
        act = s > 0
        cov = (o >= lo - 1e-9) & (o <= hi + 1e-9)
        out["coverage"] = float(cov[act].mean()) if act.any() else np.nan
        out["width"] = float((hi - lo)[act].sum() / pr[act].sum()) if pr[act].sum() > 0 else np.nan
        out["n_cov"] = int(act.sum())
    else:
        out |= {"coverage": np.nan, "width": np.nan, "n_cov": 0}
    return out


def select(cells: list[Cell], **kw) -> list[Cell]:
    def ok(c: Cell) -> bool:
        for k, v in kw.items():
            if k == "years":
                if c.test_year not in v:
                    return False
            elif getattr(c, k) != v:
                return False
        return True

    return [c for c in cells if ok(c)]


def coverage_label(cov: float) -> str:
    """Revision 1: outside 75-85 % the band is published unchanged and labelled as unverified."""
    if not np.isfinite(cov):
        return "n/a"
    return (
        "within 75-85 %"
        if COVERAGE_OK[0] <= cov <= COVERAGE_OK[1]
        else "cobertura sin verificar / coverage unverified"
    )


# --------------------------------------------------------------------------- P5 decision and bootstrap


def _matrices(fw: Forward, cut: tuple[int, ...] | None = None):
    """(rows, blocks) block-year obs and predictions of the two routes over the full-year cells."""
    keys = sorted({(c.cutoff, c.test_year) for c in fw.cells if c.test_year <= LAST_FULL_YEAR})
    if cut is not None:
        keys = [k for k in keys if k[0] in cut]
    by = {}
    for c in fw.cells:
        by[c.cutoff, c.test_year, c.route] = c
    obs = np.stack([by[k[0], k[1], "chain"].obs.sum(axis=0) for k in keys])
    pc = np.stack([by[k[0], k[1], "chain"].pred.sum(axis=0) for k in keys])
    pd_ = np.stack([by[k[0], k[1], "direct"].pred.sum(axis=0) for k in keys])
    return keys, obs, pc, pd_


def paired_bootstrap(
    obs: np.ndarray, pred_a: np.ndarray, pred_b: np.ndarray, n_boot: int = N_BOOT, seed: int = SEED
) -> dict:
    """Paired bootstrap of the pooled block-year difference a - b (negative: a is better).

    Rows (cut-off x test-year cells) and blocks are resampled separately; 95 % percentile interval.
    """
    rng = np.random.default_rng(seed)
    nr, nb = obs.shape
    dw, db = [], []
    for _ in range(n_boot):
        ir, ib = rng.integers(0, nr, nr), rng.integers(0, nb, nb)
        ix = np.ix_(ir, ib)
        o = obs[ix]
        if o.sum() <= 0:
            continue
        dw.append(wape(o, pred_a[ix]) - wape(o, pred_b[ix]))
        db.append(abs(relative_bias(o, pred_a[ix])) - abs(relative_bias(o, pred_b[ix])))
    lw, hw = np.percentile(dw, CI)
    lb, hb = np.percentile(db, CI)
    return {
        "wape_diff": wape(obs, pred_a) - wape(obs, pred_b),
        "wape_lo": float(lw),
        "wape_hi": float(hw),
        "bias_diff": abs(relative_bias(obs, pred_a)) - abs(relative_bias(obs, pred_b)),
        "bias_lo": float(lb),
        "bias_hi": float(hb),
        "n_boot": len(dw),
    }


@dataclass(eq=False)
class Decision:
    route: str
    chain: dict
    direct: dict
    reason: str
    per_cutoff: pd.DataFrame
    robust: bool
    robust_note: str
    boot: dict = field(default_factory=dict)


def _sign(x: float) -> int:
    return int(np.sign(x))


def decide(fw: Forward) -> Decision:
    """P5, applied mechanically on the pooled forward holdouts (test years <= 2025).

    The chain is published only if its pooled block-year WAPE is lower than the direct factor's and its
    |national bias| is not worse by more than 0.5 points; ties and anything else go to the direct factor.
    """
    full = [c for c in fw.cells if c.test_year <= LAST_FULL_YEAR]
    ch = score(select(full, route="chain"))
    di = score(select(full, route="direct"))
    better = ch["wape"] < di["wape"]
    bias_ok = abs(ch["bias"]) - abs(di["bias"]) <= BIAS_TOLERANCE + 1e-12
    route = "chain" if better and bias_ok else "direct"
    if route == "chain":
        reason = (
            f"chain pooled block-year WAPE {ch['wape']:.4f} < direct {di['wape']:.4f} and |bias| "
            f"{abs(ch['bias']):.4f} is within 0.005 of direct {abs(di['bias']):.4f}"
        )
    elif not better:
        reason = (
            f"the chain does not beat the direct factor: pooled block-year WAPE chain {ch['wape']:.4f} >= "
            f"direct {di['wape']:.4f}"
        )
    else:
        reason = (
            f"chain WAPE {ch['wape']:.4f} < direct {di['wape']:.4f} but its |bias| {abs(ch['bias']):.4f} "
            "is more "
            f"than 0.005 worse than direct {abs(di['bias']):.4f}"
        )
    rows = []
    for c in CUTOFFS:
        a, b = (score(select(full, route=r, cutoff=c)) for r in ROUTES)
        rows.append(
            {
                "cutoff": c,
                "chain_wape": a["wape"],
                "direct_wape": b["wape"],
                "diff": a["wape"] - b["wape"],
                "chain_bias": a["bias"],
                "direct_bias": b["bias"],
                "better": "chain" if a["wape"] < b["wape"] else "direct",
            }
        )
    pc = pd.DataFrame(rows)
    pooled_sign = _sign(ch["wape"] - di["wape"])
    d23, d24 = (float(pc.loc[pc["cutoff"] == c, "diff"].iloc[0]) for c in (2023, 2024))
    disagree = _sign(d23) != pooled_sign and _sign(d24) != pooled_sign
    note = (
        "cut-offs 2023 and 2024 both disagree in sign with the pooled result: the choice is not robust "
        "(the pooled rule still decides)"
        if disagree
        else "at least one of the cut-offs 2023 and 2024 agrees in sign with the pooled result"
    )
    _, obs, mc, md = _matrices(fw)
    return Decision(route, ch, di, reason, pc, not disagree, note, paired_bootstrap(obs, mc, md))


# --------------------------------------------------------------------------- tables over the cells


def cutoff_year_table(fw: Forward, flagged=None) -> pd.DataFrame:
    rows = []
    for c in sorted({x.cutoff for x in fw.cells}):
        for y in sorted({x.test_year for x in fw.cells if x.cutoff == c}):
            r = {"cutoff": c, "test_year": y}
            for route in ROUTES:
                s = score(select(fw.cells, cutoff=c, test_year=y, route=route), flagged=flagged)
                r |= {f"{route}_wape": s["wape"], f"{route}_bias": s["bias"]}
            rows.append(r)
    return pd.DataFrame(rows)


def horizon_table(fw: Forward) -> pd.DataFrame:
    """Pooled over cut-offs by years since the cut-off (full years only); confounded with calendar year."""
    full = [c for c in fw.cells if c.test_year <= LAST_FULL_YEAR]
    rows = []
    for h in sorted({c.horizon for c in full}):
        r = {"horizon": h, "n_cells": len({(c.cutoff, c.test_year) for c in full if c.horizon == h})}
        for route in ROUTES:
            s = score([c for c in full if c.horizon == h and c.route == route])
            r |= {f"{route}_wape": s["wape"], f"{route}_bias": s["bias"]}
        rows.append(r)
    return pd.DataFrame(rows)


def horizon_within_year(fw: Forward) -> pd.DataFrame:
    """For each test year with several cut-offs: does the error grow with the horizon (same calendar year)?"""
    rows = []
    full = [c for c in fw.cells if c.test_year <= LAST_FULL_YEAR]
    for y in sorted({c.test_year for c in full}):
        for route in ROUTES:
            by_c = {
                c.cutoff: score(
                    [x for x in full if x.test_year == y and x.route == route and x.cutoff == c.cutoff]
                )["wape"]
                for c in full
                if c.test_year == y and c.route == route
            }
            if len(by_c) < 2:
                continue
            cs = sorted(by_c)
            w = [by_c[c] for c in cs]
            rows.append(
                {
                    "test_year": y,
                    "route": route,
                    "cutoffs": " / ".join(str(c) for c in cs),
                    "wape_by_cutoff": " / ".join(f"{v:.3f}" for v in w),
                    "grows_with_horizon": all(a >= b for a, b in zip(w[:-1], w[1:], strict=True)),
                }
            )
    return pd.DataFrame(rows)


def loyo_table(cells: list[Cell]) -> pd.DataFrame:
    rows = []
    for label, years in (
        *[(f"{a}-{b}", range(a, b + 1)) for a, b in LOYO_SPLIT],
        ("2018-2025", range(2018, 2026)),
    ):
        r = {"years": label}
        for route in ROUTES:
            sel = select(cells, route=route, years=set(years))
            s_y, s_m = score(sel, "block-year"), score(sel, "block-month")
            r |= {
                f"{route}_by_wape": s_y["wape"],
                f"{route}_by_bias": s_y["bias"],
                f"{route}_bm_wape": s_m["wape"],
            }
        rows.append(r)
    return pd.DataFrame(rows)


def loyo_year_table(cells: list[Cell]) -> pd.DataFrame:
    rows = []
    for y in sorted({c.test_year for c in cells}):
        r = {"test_year": y}
        for route in ROUTES:
            s = score(select(cells, route=route, test_year=y))
            r |= {f"{route}_wape": s["wape"], f"{route}_bias": s["bias"]}
        rows.append(r)
    return pd.DataFrame(rows)


def secondary_flagged(fw: Forward, loyo: list[Cell], flagged: dict[str, set[int]]) -> pd.DataFrame:
    """P2 pooled and LOYO scores with the historically flagged satellite-months left out of the test
    months."""
    full = [c for c in fw.cells if c.test_year <= LAST_FULL_YEAR]
    rows = []
    for name, cells in (("forward pooled", full), ("leave-one-year-out 2018-2025", loyo)):
        for route in ROUTES:
            sel = select(cells, route=route)
            a, b = score(sel), score(sel, flagged=flagged)
            rows.append(
                {
                    "scope": name,
                    "route": route,
                    "wape_all": a["wape"],
                    "bias_all": a["bias"],
                    "wape_excl": b["wape"],
                    "bias_excl": b["bias"],
                }
            )
    return pd.DataFrame(rows)


def partial_block_table(fw: Forward) -> pd.DataFrame:
    """2026 complete months per cut-off, with the same calendar months of 2022-2025 as like-for-like
    reference."""
    p26 = [c for c in fw.cells if c.test_year == PARTIAL_YEAR]
    cal_months = sorted({int(m) % 12 for c in p26 for m in c.ym})
    rows = []
    for c in sorted({x.cutoff for x in p26}):
        for route in ROUTES:
            cell = select(p26, cutoff=c, route=route)[0]
            s = score([cell])
            refs = []
            for ref in select(fw.cells, cutoff=c, route=route):
                if ref.test_year > LAST_FULL_YEAR:
                    continue
                keep = np.isin(ref.ym % 12, cal_months)
                refs.append(
                    Cell(
                        ref.cutoff,
                        ref.test_year,
                        route,
                        ref.ym[keep],
                        ref.obs[keep],
                        ref.pred[keep],
                        ref.src[keep],
                    )
                )
            r = score(refs)
            rows.append(
                {
                    "cutoff": c,
                    "route": route,
                    "months_2026": ", ".join(f"{int(m) // 12}-{int(m) % 12 + 1:02d}" for m in cell.ym),
                    "wape_2026": s["wape"],
                    "bias_2026": s["bias"],
                    "wape_ref": r["wape"],
                    "bias_ref": r["bias"],
                }
            )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- P9 frozen-artifact check


@dataclass(frozen=True)
class FrozenLeg:
    label: str
    pair: str  # pair name inside the calibration that carries it
    cal_version: str
    src: tuple[str, ...]
    tgt: tuple[str, ...]


def frozen_legs(cal_base, cal_ext) -> list[tuple[FrozenLeg, object]]:
    return [
        (FrozenLeg("S-NPP -> MODIS", "viirs_to_modis", cal_base.version, ("snpp",), MODIS_SATS), cal_base),
        (FrozenLeg("NOAA-20 -> S-NPP", "noaa20_to_snpp", cal_base.version, ("noaa20",), ("snpp",)), cal_base),
        (
            FrozenLeg(
                f"NOAA-20 -> MODIS (published route: {cal_ext.pairs[ROUTE_PAIR].route})",
                ROUTE_PAIR,
                cal_ext.version,
                ("noaa20",),
                MODIS_SATS,
            ),
            cal_ext,
        ),
    ]


def _frozen_arrays(cube: Cube, cal, pair: str, src, tgt, sel: np.ndarray):
    """Predictions of a frozen pair on the months `sel`: (obs, pred, src) block-month arrays and the
    bounds."""
    if not np.array_equal(cube.blocks, cal.blocks):
        raise ValueError("the cube is not indexed on the calibration blocks")
    pc = cal.pairs[pair]
    mi = cube.month_idx[sel]
    s = cube.total(src)[sel]
    pred = (pc.f[mi] * s).sum(axis=-1)
    s_bm = s.sum(axis=-1)
    lo, hi = pc.conf_month.apply(pred, s_bm > 0)
    lo_y, hi_y = pc.conf_year.apply(pred.sum(axis=0), s_bm.sum(axis=0) > 0)
    return cube.total(tgt)[sel].sum(axis=-1), pred, s_bm, lo, hi, lo_y, hi_y


def frozen_check(cube: Cube, cal_base, cal_ext, fw: Forward | None = None) -> pd.DataFrame:
    """P9: the frozen pairs applied unchanged to the 2026 standard-processing months with complete satellites.

    One row per leg and scope: the 2026 block, and the same calendar months of 2022-2025 as like-for-like
    reference (in-sample: those years are inside the fitted period; for the route also the out-of-sample
    forward
    holdouts of the same months).
    """
    rows = []
    for leg, cal in frozen_legs(cal_base, cal_ext):
        sats = leg.src + leg.tgt
        sel26 = cube.select(sats, GATE_FROM_YM, PARTIAL_LAST_YM)
        if not sel26.any():
            continue
        cal_months = sorted({int(m) % 12 for m in cube.ym[sel26]})
        months = ", ".join(f"{int(m) // 12}-{int(m) % 12 + 1:02d}" for m in cube.ym[sel26])
        o, p, s, lo, hi, lo_y, hi_y = _frozen_arrays(cube, cal, leg.pair, leg.src, leg.tgt, sel26)
        cell = Cell(None, PARTIAL_YEAR, "frozen", cube.ym[sel26], o, p, s, lo, hi, lo_y, hi_y)
        scopes = [(f"2026 ({int(sel26.sum())} months)", months, [cell])]
        for y in range(2022, 2026):
            sel = cube.select(sats, ym_of(y, 1), ym_of(y, 12)) & np.isin(cube.month_idx, cal_months)
            if not sel.any():
                continue
            o, p, s, lo, hi, lo_y, hi_y = _frozen_arrays(cube, cal, leg.pair, leg.src, leg.tgt, sel)
            scopes.append(
                (
                    str(y),
                    "same calendar months, in-sample",
                    [Cell(None, y, "frozen", cube.ym[sel], o, p, s, lo, hi, lo_y, hi_y)],
                )
            )
        ref = [c for _, _, cs in scopes[1:] for c in cs]
        scopes.append(("2022-2025 pooled", "same calendar months, in-sample", ref))
        if leg.pair == ROUTE_PAIR and fw is not None:
            route = cal.pairs[ROUTE_PAIR].route
            oos = []
            for c in select(fw.cells, route=route):
                if c.test_year > LAST_FULL_YEAR:
                    continue
                keep = np.isin(c.ym % 12, cal_months)
                oos.append(
                    Cell(
                        c.cutoff, c.test_year, route, c.ym[keep], c.obs[keep], c.pred[keep], c.src[keep], None
                    )
                )
            scopes.append(("2022-2025 forward holdouts pooled", "same calendar months, out of sample", oos))
        for name, note, cells in scopes:
            sm, sy = score(cells, "block-month"), score(cells, "block-year")
            rows.append(
                {
                    "leg": leg.label,
                    "calibration": leg.cal_version,
                    "scope": name,
                    "note": note,
                    "wape_bm": sm["wape"],
                    "wape_by": sy["wape"],
                    "bias": sy["bias"],
                    "cov_bm": sm["coverage"],
                    "cov_by": sy["coverage"],
                    "n_by": sy["n"],
                }
            )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- NOAA-21 pairs


def noaa21_summary(cube: Cube, cal_ext, pairs=("noaa21_to_snpp", "noaa21_to_noaa20")) -> pd.DataFrame:
    """Per NOAA-21 pair of the extension: fit facts, national ratio and leave-one-year-out error
    (informative).

    The leave-one-year-out has only the 2023-03..2026 SP months (3 test years plus partial years), so its `k`
    inner selection may fall back; no decision depends on it.
    """
    from firecal.stages.harmonize.evaluate import run_cv, score_table
    from firecal.stages.harmonize.series import EXTEND_END

    rows = []
    for name in pairs:
        pc = cal_ext.pairs[name]
        d = pair_data(cube, PAIRS[name], EXTEND_END)
        s_, t_ = d.src.sum(), d.tgt.sum()
        folds = run_cv(cube, name, "loyo", end=EXTEND_END)
        sc = score_table(folds)
        a = sc[(sc["test_year"] == "all") & (sc["method"] == "sf")]
        by = a[a["level"] == "block-year"].iloc[0] if len(a) else None
        bm = a[a["level"] == "block-month"].iloc[0] if len(a) else None
        rows.append(
            {
                "pair": name,
                "label": PAIRS[name].label,
                "k": pc.k,
                "k_fallback": pc.k_fallback,
                "months": pc.n_months,
                "period": f"{pc.start}..{pc.end}",
                "national_ratio": float(t_ / s_) if s_ > 0 else np.nan,
                "loyo_wape_bm": float(bm["wape"]) if bm is not None else np.nan,
                "loyo_wape_by": float(by["wape"]) if by is not None else np.nan,
                "loyo_bias": float(by["bias"]) if by is not None else np.nan,
            }
        )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- everything


@dataclass(eq=False)
class Continuity:
    run_date: dt.date
    forward: Forward
    loyo: list[Cell]
    decision: Decision
    inputs: Inputs
    extra: dict = field(default_factory=dict)


def run_continuity(blocks: np.ndarray, grid_dir=None, completeness_path=None, log=None) -> Continuity:
    inp = load_inputs(blocks, grid_dir, completeness_path)
    fw = run_forward(inp.cube, log=log)
    loyo = run_loyo(inp.cube)
    return Continuity(dt.date.today(), fw, loyo, decide(fw), inp)
