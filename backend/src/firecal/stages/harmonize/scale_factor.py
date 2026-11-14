"""SA2.2 scale factor baseline: ratio of sums per block x calendar month x day/night, shrunk to national.

All arrays are (months, blocks, 2) with day/night on the last axis; `month_idx` (0..11) is the calendar month
of each row and `train` a boolean mask over rows. The factor maps source counts to target counts:

    f = (T + k * f_nat) / (S + k)

with T and S the training sums of target and source in a block x calendar month x day/night cell and f_nat the
national ratio of the same calendar month and day/night. The same estimator serves both directions (VIIRS to
MODIS-equivalent and back), the Terra-only variant and the NOAA-20 to S-NPP transfer: only `src` and `tgt`
change.
Prediction is `f * source`, day and night separately, then summed.
"""

from dataclasses import dataclass

import numpy as np

from firecal.stages.harmonize.metrics import wape
from firecal.stages.harmonize.validation import leave_one_year_out

K_GRID = (0.0, 5.0, 20.0, 100.0, 500.0, 2000.0, 10000.0)
DEFAULT_K = 20.0  # used only when the inner folds cannot score any k (very short training)
Z80 = 1.2815515655446004  # standard normal quantile for a nominal 80 % two-sided interval


@dataclass(frozen=True, eq=False)
class Factors:
    f: np.ndarray  # (12, blocks, 2)
    f_nat: np.ndarray  # (12, 2)
    k: float


def month_sums(x: np.ndarray, month_idx: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Sum rows of `x` over `mask` by calendar month -> (12, blocks, 2)."""
    out = np.zeros((12,) + x.shape[1:])
    for m in range(12):
        sel = mask & (month_idx == m)
        if sel.any():
            out[m] = x[sel].sum(axis=0)
    return out


def fit_factors(
    src: np.ndarray, tgt: np.ndarray, month_idx: np.ndarray, train: np.ndarray, k: float
) -> Factors:
    s = month_sums(src, month_idx, train)
    t = month_sums(tgt, month_idx, train)
    s_nat, t_nat = s.sum(axis=1), t.sum(axis=1)  # (12, 2)
    # Fallbacks when a national cell is empty: the day/night ratio over all months, then 1.
    s_dn, t_dn = s_nat.sum(axis=0), t_nat.sum(axis=0)
    dn_ratio = np.where(s_dn > 0, t_dn / np.where(s_dn > 0, s_dn, 1.0), 1.0)
    f_nat = np.where(s_nat > 0, t_nat / np.where(s_nat > 0, s_nat, 1.0), dn_ratio[None, :])
    denom = s + k
    f = np.where(
        denom > 0,
        (t + k * f_nat[:, None, :]) / np.where(denom > 0, denom, 1.0),
        f_nat[:, None, :],
    )
    return Factors(f, f_nat, float(k))


def predict_dn(factors: Factors, src: np.ndarray, month_idx: np.ndarray) -> np.ndarray:
    """Per day/night prediction (rows, blocks, 2)."""
    return factors.f[month_idx] * src


def predict_total(factors: Factors, src: np.ndarray, month_idx: np.ndarray) -> np.ndarray:
    """Day and night predicted separately, then summed -> (rows, blocks)."""
    return predict_dn(factors, src, month_idx).sum(axis=-1)


def inner_folds(dates, train: np.ndarray, gap_months: int = 6) -> list[tuple[np.ndarray, np.ndarray]]:
    """Leave-one-year-out (with gap) restricted to the rows in `train`; masks are over all rows."""
    idx = np.flatnonzero(train)
    out = []
    for fold in leave_one_year_out(dates[idx], gap_months):
        tr = np.zeros(len(train), dtype=bool)
        te = np.zeros(len(train), dtype=bool)
        tr[idx[fold.train]] = True
        te[idx[fold.test]] = True
        if tr.any() and te.any():
            out.append((tr, te))
    return out


def select_k(
    src: np.ndarray,
    tgt: np.ndarray,
    dates,
    month_idx: np.ndarray,
    train: np.ndarray,
    k_grid=K_GRID,
    gap_months: int = 6,
) -> tuple[float, bool]:
    """Pick k by inner leave-one-year-out inside `train` (pooled WAPE on block-month totals).

    Returns (k, fallback). `fallback` is True when no inner fold could be scored and DEFAULT_K was used.
    """
    folds = inner_folds(dates, train, gap_months)
    best, best_err = None, np.inf
    for k in k_grid:
        obs, pred = [], []
        for tr, te in folds:
            fac = fit_factors(src, tgt, month_idx, tr, k)
            pred.append(predict_total(fac, src[te], month_idx[te]))
            obs.append(tgt[te].sum(axis=-1))
        if not obs:
            break
        err = wape(np.concatenate(obs), np.concatenate(pred))
        if np.isfinite(err) and err < best_err:
            best, best_err = float(k), err
    if best is None:
        return DEFAULT_K, True
    return best, False


def loyo_factor_stack(
    src: np.ndarray,
    tgt: np.ndarray,
    dates,
    month_idx: np.ndarray,
    train: np.ndarray,
    k: float,
    gap_months: int = 6,
) -> np.ndarray:
    """Factors refit with each training year left out (with gap): (folds, 12, blocks, 2)."""
    folds = inner_folds(dates, train, gap_months)
    return (
        np.stack([fit_factors(src, tgt, month_idx, tr, k).f for tr, _ in folds]) if folds else np.empty((0,))
    )


def jackknife_interval(
    stack: np.ndarray, factors: Factors, src: np.ndarray, month_idx: np.ndarray, z: float = Z80
) -> tuple[np.ndarray, np.ndarray]:
    """Interval on block-month totals from the leave-one-year-out spread of factors (jackknife).

    se(f) = sqrt((n - 1) / n * sum_i (f_i - mean f)^2); interval f +/- z * se, applied to source counts.
    Reflects only the uncertainty of the factor, not the count noise of the test month.
    """
    n = stack.shape[0]
    if n < 2:
        p = predict_total(factors, src, month_idx)
        return p, p
    se = np.sqrt((n - 1) / n * ((stack - stack.mean(axis=0)) ** 2).sum(axis=0))
    lo = np.clip(factors.f - z * se, 0, None)[month_idx] * src
    hi = (factors.f + z * se)[month_idx] * src
    return lo.sum(axis=-1), hi.sum(axis=-1)


def yearly_spread_interval(
    src: np.ndarray,
    tgt: np.ndarray,
    year_idx: np.ndarray,
    month_idx: np.ndarray,
    train: np.ndarray,
    factors: Factors,
    test_src: np.ndarray,
    test_month_idx: np.ndarray,
    q: float = 0.1,
    k_year: float = 0.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Interval from the spread of single-year factors: q and 1-q quantiles over the training years.

    Each training year gets its own factor (`k_year`, default 0 = raw ratio of that year; a year with no
    source counts in a cell falls back to that year's national ratio);
    this includes year-to-year variation of the ratio, which the jackknife interval does not.
    """
    years = np.unique(year_idx[train])
    fs = np.stack([fit_factors(src, tgt, month_idx, train & (year_idx == y), k_year).f for y in years])
    lo_f, hi_f = np.quantile(fs, [q, 1 - q], axis=0)
    return (lo_f[test_month_idx] * test_src).sum(axis=-1), (hi_f[test_month_idx] * test_src).sum(axis=-1)
