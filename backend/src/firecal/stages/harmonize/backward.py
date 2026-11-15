"""SA2.8 backward validation and the P4 condition 2 gate (plan/02-harmonization.md, P4 and Revision 1).

Train 2016-01..2025-12 (no gap) and test each of 2012..2015, per pair, once with every training month and once
without the drift years of that pair. The estimator, `k` selection and metrics are those of `evaluate.py`.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from firecal.stages.harmonize.drift import train_mask
from firecal.stages.harmonize.evaluate import (
    GAP_MONTHS,
    PAIRS,
    FoldOut,
    PairData,
    pair_data,
    score_table,
)
from firecal.stages.harmonize.metrics import relative_bias, wape
from firecal.stages.harmonize.regions import Cube, ym_of
from firecal.stages.harmonize.scale_factor import K_GRID, fit_factors, predict_total, select_k

TRAIN_FIRST = ym_of(2016, 1)
TRAIN_LAST = ym_of(2025, 12)
TEST_YEARS = (2012, 2013, 2014, 2015)
N_BOOT = 1000
SEED = 20261114
CI = (2.5, 97.5)


@dataclass(eq=False)
class BackwardRun:
    pair: str
    variant: str  # "with" | "without"
    drop_years: tuple[int, ...]
    train_ym: np.ndarray
    k: float
    k_fallback: bool
    folds: list[FoldOut]


def backward_run(cube: Cube, pair_name: str, drop_years=(), d: PairData | None = None) -> BackwardRun:
    """One variant; training starts in 2016 and the test years end in 2015, so they never overlap."""
    d = d or pair_data(cube, PAIRS[pair_name])
    tr = train_mask(d.year_idx, d.ym, TRAIN_FIRST, TRAIN_LAST, drop_years)
    k, fb = select_k(d.src, d.tgt, d.dates, d.month_idx, tr, K_GRID, GAP_MONTHS)
    fac = fit_factors(d.src, d.tgt, d.month_idx, tr, k)
    src_tot, tgt_tot = d.src.sum(axis=-1), d.tgt.sum(axis=-1)
    variant = "without" if len(drop_years) else "with"
    folds = []
    for y in TEST_YEARS:
        te = d.year_idx == y
        if not te.any():
            continue
        folds.append(
            FoldOut(
                pair=pair_name,
                scheme=f"backward_{variant}",
                method="sf",
                test_year=y,
                ym=d.ym[te],
                obs=tgt_tot[te],
                pred=predict_total(fac, d.src[te], d.month_idx[te]),
                src=src_tot[te],
                k=k,
                k_fallback=fb,
            )
        )
    return BackwardRun(pair_name, variant, tuple(drop_years), d.ym[tr], k, fb, folds)


def block_year_matrices(run: BackwardRun) -> tuple[np.ndarray, np.ndarray, list[int]]:
    """(years, blocks) observed and predicted block-year totals."""
    obs = np.stack([f.obs.sum(axis=0) for f in run.folds])
    pred = np.stack([f.pred.sum(axis=0) for f in run.folds])
    return obs, pred, [f.test_year for f in run.folds]


def _pooled(obs: np.ndarray, pred: np.ndarray) -> tuple[float, float]:
    return wape(obs, pred), abs(relative_bias(obs, pred))


def paired_bootstrap(
    obs: np.ndarray,
    pred_with: np.ndarray,
    pred_without: np.ndarray,
    n_boot: int = N_BOOT,
    seed: int = SEED,
) -> dict[str, float]:
    """Paired bootstrap of the pooled block-year differences (without - with).

    Years and blocks are resampled separately.

    Inputs are (years, blocks) matrices. Differences are for WAPE and for |relative bias| (negative = the
    run without drift years is better). Percentile interval 95 %.
    """
    rng = np.random.default_rng(seed)
    ny, nb = obs.shape
    dw, db = [], []
    for _ in range(n_boot):
        iy = rng.integers(0, ny, ny)
        ib = rng.integers(0, nb, nb)
        o = obs[np.ix_(iy, ib)]
        if o.sum() <= 0:
            continue
        w1, b1 = _pooled(o, pred_with[np.ix_(iy, ib)])
        w0, b0 = _pooled(o, pred_without[np.ix_(iy, ib)])
        dw.append(w0 - w1)
        db.append(b0 - b1)
    w_pt = _pooled(obs, pred_without)[0] - _pooled(obs, pred_with)[0]
    b_pt = _pooled(obs, pred_without)[1] - _pooled(obs, pred_with)[1]
    lw, hw = np.percentile(dw, CI)
    lb, hb = np.percentile(db, CI)
    return {
        "wape_diff": float(w_pt),
        "wape_lo": float(lw),
        "wape_hi": float(hw),
        "bias_diff": float(b_pt),
        "bias_lo": float(lb),
        "bias_hi": float(hb),
        "n_boot": len(dw),
    }


def gate(boot: dict[str, float]) -> tuple[bool, str]:
    """P4 condition 2: neither metric worse (point difference <= 0) and at least one with its interval < 0."""
    not_worse = boot["wape_diff"] <= 0 and boot["bias_diff"] <= 0
    better = boot["wape_hi"] < 0 or boot["bias_hi"] < 0
    ok = bool(not_worse and better)
    return ok, "recalibration warranted in a later version" if ok else "report only"


def run_pair(cube: Cube, pair_name: str, drop_years: tuple[int, ...]) -> dict:
    """Both variants, scores and the bootstrap for one pair and drift window."""
    d = pair_data(cube, PAIRS[pair_name])
    r_with = backward_run(cube, pair_name, (), d)
    r_without = backward_run(cube, pair_name, drop_years, d)
    o, p1, years = block_year_matrices(r_with)
    _, p0, _ = block_year_matrices(r_without)
    boot = paired_bootstrap(o, p1, p0)
    ok, verdict = gate(boot)
    scores = score_table(r_with.folds + r_without.folds)
    w1, b1 = _pooled(o, p1)
    w0, b0 = _pooled(o, p0)
    return {
        "wape_with": w1,
        "wape_without": w0,
        "bias_with": b1,
        "bias_without": b0,
        "pair": pair_name,
        "drop_years": drop_years,
        "with": r_with,
        "without": r_without,
        "boot": boot,
        "gate": ok,
        "verdict": verdict,
        "scores": scores,
        "blocks": cube.blocks,
        "years": years,
        "obs_by": o,
        "pred_with_by": p1,
        "pred_without_by": p0,
    }


def block_detail(res: dict) -> pd.DataFrame:
    """Per-block block-year scores pooled over the test years, with and without."""
    rows = []
    for b, blk in enumerate(res["blocks"]):
        o = res["obs_by"][:, b]
        p1, p0 = res["pred_with_by"][:, b], res["pred_without_by"][:, b]
        if o.sum() == 0 and p1.sum() == 0 and p0.sum() == 0:
            continue
        rows.append(
            {
                "pair": res["pair"],
                "block": int(blk),
                "obs_total": float(o.sum()),
                "pred_with": float(p1.sum()),
                "pred_without": float(p0.sum()),
                "bias_with": relative_bias(o, p1),
                "bias_without": relative_bias(o, p0),
                "wape_with": wape(o, p1),
                "wape_without": wape(o, p0),
            }
        )
    return pd.DataFrame(rows)


def run_backward() -> tuple[dict[str, dict], dict[str, str], pd.DataFrame]:
    """All gate pairs for the P3 epoch window and the Terra 2022+ sensitivity window (real data)."""
    from firecal.stages.harmonize.drift import detection_stats, drift_epochs, pair_windows, window_keys
    from firecal.stages.harmonize.regions import build_cube, build_monthly_region_table

    cube = build_cube(build_monthly_region_table())
    epochs = drift_epochs(detection_stats().hours)
    keys = window_keys(pair_windows(epochs))
    results, windows, blocks = {}, {}, []
    for key, (pair, years) in keys.items():
        res = run_pair(cube, pair, years)
        results[key] = res
        windows[key] = f"{years[0]}-{years[-1]}" if years else "none"
        blocks.append(block_detail(res).assign(case=key))
    return results, windows, pd.concat(blocks, ignore_index=True)
