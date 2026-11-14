"""Nested conformal intervals on relative residuals for the SA2.2 scale-factor baseline.

Inside one outer training set, the inner leave-one-year-out (same gap, same `k` as the outer fold) gives
out-of-fold predictions on rows that never include the outer test year or its gap. The relative residual
`r = obs / pred` (pred above a small count; `obs = 0` gives `r = 0`) is stratified by predicted-count bin,
because the relative noise of a count shrinks with its size. The interval for a test prediction is
`pred * [q_lo(r), q_hi(r)]` of its bin, with the finite-sample conformal quantile correction. Block-month and
block-year totals are calibrated separately (block-year bounds are not sums of block-month bounds).
Predictions at or below a small count use an additive interval on `obs - pred` instead. Calibration and
coverage use rows with a source count above zero; rows without one get [0, 0] (out of the factor's reach).
"""

from dataclasses import dataclass

import numpy as np

from firecal.stages.harmonize.scale_factor import fit_factors, inner_folds, predict_total

NOMINAL = 0.8
N_BINS = 5
MIN_PER_BIN = 30
# Predictions at or below these counts use an additive interval (absolute residuals): relative noise of such
# small counts is large (Poisson sd / mean >= ~30 % below 10) and `obs / pred` is undefined at pred = 0.
# Fixed a priori, not tuned on any test year.
SMALL_MONTH = 5.0
SMALL_YEAR = 10.0


def conformal_bounds(
    r: np.ndarray, alpha: float = 1 - NOMINAL, lo_floor: float = 0.0
) -> tuple[float, float, bool]:
    """Two-sided split-conformal quantiles of `r` with the (n + 1) correction.

    Upper = the ceil((1 - alpha / 2) (n + 1))-th smallest residual, lower = the floor(alpha / 2 (n + 1))-th.
    When the rank falls outside 1..n the sample cannot support the level: the upper bound becomes the maximum
    and the lower bound `lo_floor` (0 for non-negative ratios, -inf for signed residuals); the third value
    flags that the upper bound is capped.
    """
    n = len(r)
    if n == 0:
        return 1.0, 1.0, True
    s = np.sort(r)
    hi_rank = int(np.ceil((1 - alpha / 2) * (n + 1) - 1e-12))
    lo_rank = int(np.floor(alpha / 2 * (n + 1) + 1e-12))
    capped = hi_rank > n
    hi = float(s[min(hi_rank, n) - 1])
    lo = float(s[lo_rank - 1]) if lo_rank >= 1 else lo_floor
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
    edges: np.ndarray  # interior bin edges on the predicted count (above `small`), ascending
    lo: np.ndarray  # per-bin lower multiplier
    hi: np.ndarray  # per-bin upper multiplier
    n: np.ndarray  # residuals per bin
    capped: np.ndarray  # per-bin: upper rank above n (bound is the sample maximum)
    small: float = 0.0  # pred <= small uses the additive interval
    add_lo: float = 0.0  # lower quantile of obs - pred (signed) for small predictions
    add_hi: float = 0.0
    n_small: int = 0

    def apply(self, pred: np.ndarray, active: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
        """Bounds for `pred`; `active` (source known above zero) marks rows that get an interval at all.

        Rows that are not active (no source count) get [0, 0]: the factor predicts 0 there.
        """
        act = np.ones(pred.shape, dtype=bool) if active is None else active
        b = _bin_of(pred, self.edges)
        small = pred <= self.small
        lo = np.where(small, np.maximum(0.0, pred + self.add_lo), pred * self.lo[b])
        hi = np.where(small, pred + self.add_hi, pred * self.hi[b])
        return np.where(act, lo, 0.0), np.where(act, hi, 0.0)


def fit_binned(
    pred: np.ndarray,
    obs: np.ndarray,
    n_bins: int = N_BINS,
    min_n: int = MIN_PER_BIN,
    alpha: float = 1 - NOMINAL,
    small: float = 0.0,
) -> BinnedConformal:
    """Calibrate on out-of-fold (pred, obs) pairs.

    pred <= `small` (including 0): one additive bin on `obs - pred`. Above it: relative residuals `obs / pred`
    in bins whose edges are quantiles of `pred` (training only), merged until each has `min_n` residuals.
    """
    sm = pred <= small
    d = obs[sm] - pred[sm]
    add_lo, add_hi, _ = conformal_bounds(d, alpha, lo_floor=-np.inf) if len(d) else (0.0, 0.0, True)
    p, r = pred[~sm], obs[~sm] / pred[~sm]
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
    return BinnedConformal(edges, lo, hi, n, cap, float(small), float(add_lo), float(add_hi), int(sm.sum()))


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
        s_tot = src[te].sum(axis=-1)
        keep = s_tot > 0  # only rows with a source count: what is known at prediction time
        pm.append(p[keep])
        om.append(o[keep])
        py_, oy_, sy_ = p.sum(axis=0), o.sum(axis=0), s_tot.sum(axis=0)
        py.append(py_[sy_ > 0])
        oy.append(oy_[sy_ > 0])
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
    test_src: np.ndarray | None = None,
    gap_months: int = 6,
    n_bins: int = N_BINS,
    min_n: int = MIN_PER_BIN,
    alpha: float = 1 - NOMINAL,
    small_month: float = SMALL_MONTH,
    small_year: float = SMALL_YEAR,
) -> ConformalOut:
    """Intervals for `test_pred` (rows, blocks), calibrated only on residuals inside `train`.

    `test_src` (rows, blocks) are the source totals of the test rows; rows without source get [0, 0].
    Omitted: every row counts as active.
    """
    res = inner_residuals(src, tgt, dates, month_idx, train, k, gap_months)
    cm = fit_binned(res.pred_month, res.obs_month, n_bins, min_n, alpha, small_month)
    cy = fit_binned(res.pred_year, res.obs_year, n_bins, min_n, alpha, small_year)
    act_m = None if test_src is None else test_src > 0
    act_y = None if test_src is None else test_src.sum(axis=0) > 0
    return ConformalOut(
        month=cm.apply(test_pred, act_m),
        year=cy.apply(test_pred.sum(axis=0), act_y),
        calib_month=cm,
        calib_year=cy,
        used=res.used,
    )
