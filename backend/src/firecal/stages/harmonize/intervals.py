"""Nested conformal intervals on relative residuals for the SA2.2 scale-factor baseline.

Inside one outer training set, the inner leave-one-year-out (same gap, same `k` as the outer fold) gives
out-of-fold predictions on rows that never include the outer test year or its gap. The relative residual
`r = obs / pred` (pred > 0; `obs = 0` gives `r = 0`) is stratified by predicted-count bin, because the
relative noise of a count shrinks with its size. The interval for a test prediction is
`pred * [q_lo(r), q_hi(r)]` of its bin, with the finite-sample conformal quantile correction. Block-month and
block-year totals are calibrated separately (block-year bounds are not sums of block-month bounds).
"""

from dataclasses import dataclass

import numpy as np

from firecal.stages.harmonize.scale_factor import fit_factors, inner_folds, predict_total

NOMINAL = 0.8
N_BINS = 5
MIN_PER_BIN = 30


def conformal_bounds(r: np.ndarray, alpha: float = 1 - NOMINAL) -> tuple[float, float, bool]:
    """Two-sided split-conformal quantiles of `r` with the (n + 1) correction.

    Upper = the ceil((1 - alpha / 2) (n + 1))-th smallest residual, lower = the floor(alpha / 2 (n + 1))-th.
    When the rank falls outside 1..n the sample cannot support the level: the upper bound becomes the maximum
    and the lower bound 0 (residuals are non-negative); the third value flags that the upper bound is capped.
    """
    n = len(r)
    if n == 0:
        return 1.0, 1.0, True
    s = np.sort(r)
    hi_rank = int(np.ceil((1 - alpha / 2) * (n + 1) - 1e-12))
    lo_rank = int(np.floor(alpha / 2 * (n + 1) + 1e-12))
    capped = hi_rank > n
    hi = float(s[min(hi_rank, n) - 1])
    lo = float(s[lo_rank - 1]) if lo_rank >= 1 else 0.0
    return lo, hi, capped


def _bin_of(pred: np.ndarray, edges: np.ndarray) -> np.ndarray:
    return np.searchsorted(edges, pred, side="right")


def merge_small_bins(pred: np.ndarray, edges: np.ndarray, min_n: int) -> np.ndarray:
    """Drop interior edges (merging the smallest bin into its smaller neighbour) until every bin has min_n."""
    edges = np.asarray(edges, dtype="float64")
    while len(edges) > 0:
        counts = np.bincount(_bin_of(pred, edges), minlength=len(edges) + 1)
        if counts.min() >= min_n:
            break
        i = int(np.argmin(counts))
        if i == 0:
            drop = 0
        elif i == len(counts) - 1:
            drop = len(edges) - 1
        else:
            drop = i - 1 if counts[i - 1] <= counts[i + 1] else i
        edges = np.delete(edges, drop)
    return edges


@dataclass(frozen=True, eq=False)
class BinnedConformal:
    edges: np.ndarray  # interior bin edges on the predicted count, ascending
    lo: np.ndarray  # per-bin lower multiplier
    hi: np.ndarray  # per-bin upper multiplier
    n: np.ndarray  # residuals per bin
    capped: np.ndarray  # per-bin: upper rank above n (bound is the sample maximum)

    def apply(self, pred: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        b = _bin_of(pred, self.edges)
        pos = pred > 0
        return np.where(pos, pred * self.lo[b], 0.0), np.where(pos, pred * self.hi[b], 0.0)


def fit_binned(
    pred: np.ndarray,
    obs: np.ndarray,
    n_bins: int = N_BINS,
    min_n: int = MIN_PER_BIN,
    alpha: float = 1 - NOMINAL,
) -> BinnedConformal:
    """Calibrate on out-of-fold (pred, obs); only pred > 0 is used. Bin edges are quantiles of `pred`."""
    keep = pred > 0
    p, r = pred[keep], obs[keep] / pred[keep]
    if len(p) and n_bins > 1:
        edges = np.unique(np.quantile(p, np.linspace(0, 1, n_bins + 1)[1:-1]))
        edges = merge_small_bins(p, edges, min_n)
    else:
        edges = np.empty(0)
    b = _bin_of(p, edges)
    k = len(edges) + 1
    lo, hi, n, cap = np.ones(k), np.ones(k), np.zeros(k, dtype=int), np.zeros(k, dtype=bool)
    for i in range(k):
        ri = r[b == i]
        lo[i], hi[i], cap[i] = conformal_bounds(ri, alpha)
        n[i] = len(ri)
    return BinnedConformal(edges, lo, hi, n, cap)


@dataclass(frozen=True, eq=False)
class InnerResiduals:
    pred_month: np.ndarray  # block-month out-of-fold predictions (all inner test rows x blocks, flat)
    obs_month: np.ndarray
    pred_year: np.ndarray  # block-year totals per inner test year (flat over years x blocks)
    obs_year: np.ndarray
    used: np.ndarray  # boolean mask over all rows: rows that served as an inner test fold


def inner_residuals(
    src: np.ndarray,
    tgt: np.ndarray,
    dates,
    month_idx: np.ndarray,
    train: np.ndarray,
    k: float,
    gap_months: int = 6,
) -> InnerResiduals:
    """Out-of-fold predictions of the inner leave-one-year-out inside `train`, with the outer fold's `k`."""
    pm, om, py, oy = [], [], [], []
    used = np.zeros(len(train), dtype=bool)
    for tr, te in inner_folds(dates, train, gap_months):
        fac = fit_factors(src, tgt, month_idx, tr, k)
        p = predict_total(fac, src[te], month_idx[te])
        o = tgt[te].sum(axis=-1)
        pm.append(p.ravel())
        om.append(o.ravel())
        py.append(p.sum(axis=0))
        oy.append(o.sum(axis=0))
        used |= te
    cat = lambda xs: np.concatenate(xs) if xs else np.empty(0)  # noqa: E731
    return InnerResiduals(cat(pm), cat(om), cat(py), cat(oy), used)


@dataclass(frozen=True, eq=False)
class ConformalOut:
    month: tuple[np.ndarray, np.ndarray]  # bounds on block-month totals (rows, blocks)
    year: tuple[np.ndarray, np.ndarray]  # bounds on block-year totals (blocks,)
    calib_month: BinnedConformal
    calib_year: BinnedConformal
    used: np.ndarray


def conformal_intervals(
    src: np.ndarray,
    tgt: np.ndarray,
    dates,
    month_idx: np.ndarray,
    train: np.ndarray,
    k: float,
    test_pred: np.ndarray,
    gap_months: int = 6,
    n_bins: int = N_BINS,
    min_n: int = MIN_PER_BIN,
    alpha: float = 1 - NOMINAL,
) -> ConformalOut:
    """Intervals for `test_pred` (rows, blocks), calibrated only on residuals inside `train`."""
    res = inner_residuals(src, tgt, dates, month_idx, train, k, gap_months)
    cm = fit_binned(res.pred_month, res.obs_month, n_bins, min_n, alpha)
    cy = fit_binned(res.pred_year, res.obs_year, n_bins, min_n, alpha)
    return ConformalOut(
        month=cm.apply(test_pred),
        year=cy.apply(test_pred.sum(axis=0)),
        calib_month=cm,
        calib_year=cy,
        used=res.used,
    )
