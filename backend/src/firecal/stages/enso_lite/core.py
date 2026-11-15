"""Pure functions of SA5.5 (ENSO-lite): season window, season totals, lagged ONI, Spearman, bootstraps,
whole-year permutation and within-era ranks. No I/O, no network. Association statistics only.
"""

import math

import numpy as np
import pandas as pd
from scipy.stats import rankdata

MAX_LAG = 12
SEASON_LENGTH = 4
MIN_SHARE = 0.40
BLOCK_LEN = 3


def month_index(year: int, month: int) -> int:
    return year * 12 + month - 1


# --- season window and totals -------------------------------------------------------------------------


def season_window(medians: np.ndarray, length: int = SEASON_LENGTH, min_share: float = MIN_SHARE) -> dict:
    """Circular window of `length` consecutive calendar months with the highest sum of monthly medians.

    `medians`: 12 values (months 1..12) of the climatological median monthly total. Ties go to the earliest
    start month. `share` = window sum / sum of the 12 medians. If the best window holds less than `min_share`
    (flat or bimodal climatology) or the medians are degenerate, the fallback is the Jul-Jun year
    (start 7, length 12) and `fallback` is True. Returns start_month, length, share, best_start, best_share,
    fallback.
    """
    med = np.asarray(medians, dtype=float)
    if med.shape != (12,):
        raise ValueError("medians must have 12 values")
    total = float(np.nansum(med))
    filled = np.nan_to_num(med, nan=0.0)
    sums = np.array([sum(filled[(s + j) % 12] for j in range(length)) for s in range(12)])
    best = int(np.argmax(sums))
    share = float(sums[best] / total) if total > 0 else float("nan")
    fallback = not (math.isfinite(share) and share >= min_share)
    return {
        "start_month": 7 if fallback else best + 1,
        "length": 12 if fallback else length,
        "share": share,
        "best_start": best + 1,
        "best_share": share,
        "fallback": fallback,
    }


def season_totals(monthly: pd.Series, start_month: int, length: int) -> pd.DataFrame:
    """Season totals from a monthly series indexed by month index (year*12 + month - 1).

    A season is labelled by the year of its first month and holds months start_month .. start_month+length-1
    (wrapping into the next year). Seasons with any missing or NaN month are dropped (incomplete).
    Returns columns season_year, total, sorted by year.
    """
    years = sorted({int(i) // 12 for i in monthly.index})
    out = []
    for y in years:
        first = month_index(y, start_month)
        idx = range(first, first + length)
        if all(i in monthly.index for i in idx):
            vals = monthly.loc[list(idx)].to_numpy(dtype=float)
            if np.all(np.isfinite(vals)):
                out.append({"season_year": y, "total": float(vals.sum())})
    return pd.DataFrame(out, columns=["season_year", "total"], dtype=float).astype({"season_year": "int64"})


def lagged_oni(oni: pd.Series, season_years, start_month: int, max_lag: int = MAX_LAG) -> np.ndarray:
    """ONI lag matrix (n_seasons x max_lag+1). Column k = ONI at (season start month - k), no averaging.

    `oni` is indexed by month index (the ONI value is dated at its central month). Missing -> NaN.
    """
    years = np.asarray(list(season_years), dtype="int64")
    out = np.full((len(years), max_lag + 1), np.nan)
    for i, y in enumerate(years):
        start = month_index(int(y), start_month)
        for k in range(max_lag + 1):
            out[i, k] = oni.get(start - k, np.nan)
    return out


# --- Spearman ---------------------------------------------------------------------------------------


def _standardize(r: np.ndarray, axis: int) -> np.ndarray:
    c = r - r.mean(axis=axis, keepdims=True)
    norm = np.sqrt((c**2).sum(axis=axis, keepdims=True))
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(norm > 0, c / np.where(norm > 0, norm, 1.0), np.nan)


def spearman(y: np.ndarray, x: np.ndarray) -> np.ndarray:
    """Spearman rho between y (n,) and each column of x (n, K); average ranks for ties. NaN if constant."""
    y = np.asarray(y, dtype=float)
    x = np.asarray(x, dtype=float)
    if x.ndim == 1:
        x = x[:, None]
    ry = _standardize(rankdata(y), 0)
    rx = _standardize(rankdata(x, axis=0), 0)
    return np.einsum("i,ik->k", ry, rx)


def _spearman_batch(y_b: np.ndarray, x_b: np.ndarray) -> np.ndarray:
    """Spearman per resample: y_b (B, n), x_b (B, n, K) -> (B, K)."""
    ry = _standardize(rankdata(y_b, axis=1), 1)
    rx = _standardize(rankdata(x_b, axis=1), 1)
    return np.einsum("bi,bik->bk", ry, rx)


# --- bootstraps ---------------------------------------------------------------------------------------


def block_indices(n: int, n_boot: int, block: int, rng: np.random.Generator) -> np.ndarray:
    """Moving-block bootstrap indices (n_boot, n): overlapping blocks of `block` consecutive positions."""
    block = max(1, min(block, n))
    n_blocks = math.ceil(n / block)
    starts = rng.integers(0, n - block + 1, size=(n_boot, n_blocks))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(n_boot, -1)
    return idx[:, :n]


def iid_indices(n: int, n_boot: int, rng: np.random.Generator) -> np.ndarray:
    return rng.integers(0, n, size=(n_boot, n))


def bootstrap_ci(
    y: np.ndarray, x: np.ndarray, idx: np.ndarray, level: float = 0.95
) -> tuple[np.ndarray, np.ndarray]:
    """Percentile CI of Spearman rho per column of x over resampled pairs `idx` (B, n). In [-1, 1]."""
    y = np.asarray(y, dtype=float)
    x = np.asarray(x, dtype=float)
    rho = _spearman_batch(y[idx], x[idx])
    a = (1 - level) / 2
    with np.errstate(all="ignore"):
        lo = np.nanquantile(rho, a, axis=0)
        hi = np.nanquantile(rho, 1 - a, axis=0)
    return lo, hi


# --- whole-year permutation ---------------------------------------------------------------------------


def shared_permutations(n_years: int, n_perm: int, rng: np.random.Generator) -> np.ndarray:
    """`n_perm` uniform permutations of the years 0..n_years-1, shared by every area."""
    return np.argsort(rng.random((n_perm, n_years)), axis=1)


def induce(perms: np.ndarray, positions: np.ndarray) -> np.ndarray:
    """Permutations of an area's seasons induced by the shared year permutations.

    `positions`: indices (into the shared year axis) of the area's valid seasons. The relative order of the
    shared image restricted to those years is a uniform permutation of the area's m seasons.
    """
    sub = perms[:, np.asarray(positions, dtype="int64")]
    return np.argsort(np.argsort(sub, axis=1), axis=1)


def permute_rows(x: np.ndarray, perm: np.ndarray) -> np.ndarray:
    """Whole-year permutation: row i of the output is row perm[i] of x (each row keeps its lag vector)."""
    return np.asarray(x)[np.asarray(perm)]


def permutation_rhos(y: np.ndarray, x: np.ndarray, perms: np.ndarray) -> np.ndarray:
    """Spearman rho (n_perm, K) between y and the whole-year-permuted rows of x."""
    ry = _standardize(rankdata(np.asarray(y, dtype=float)), 0)
    rx = _standardize(rankdata(np.asarray(x, dtype=float), axis=0), 0)
    return np.einsum("i,bik->bk", ry, rx[perms])


def perm_pvalues(rho_obs: np.ndarray, rho_perm: np.ndarray) -> tuple[np.ndarray, float]:
    """Two-sided per-lag p and family-wise p (max |rho| over lags), both with the +1 correction."""
    b = rho_perm.shape[0]
    obs = np.abs(rho_obs)
    with np.errstate(invalid="ignore"):
        per_lag = (1 + np.sum(np.abs(rho_perm) >= obs[None, :], axis=0)) / (b + 1)
        fam_max = np.nanmax(np.abs(rho_perm), axis=1)
        fam = (1 + np.sum(fam_max >= np.nanmax(obs))) / (b + 1)
    return per_lag, float(fam)


# --- other diagnostics ----------------------------------------------------------------------------------


def lag1_autocorr(values: np.ndarray, years: np.ndarray) -> float:
    """Pearson lag-1 autocorrelation using only pairs of consecutive years; NaN with fewer than 3 pairs."""
    v = np.asarray(values, dtype=float)
    yr = np.asarray(years)
    order = np.argsort(yr)
    v, yr = v[order], yr[order]
    ok = np.diff(yr) == 1
    a, b = v[:-1][ok], v[1:][ok]
    if len(a) < 3 or np.std(a) == 0 or np.std(b) == 0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def within_era_ranks(values: np.ndarray, years: np.ndarray, split_year: int) -> np.ndarray:
    """Percentile rank rank/(n+1) of each value within its era (year < split_year vs >= split_year)."""
    v = np.asarray(values, dtype=float)
    yr = np.asarray(years)
    out = np.empty(len(v))
    for mask in (yr < split_year, yr >= split_year):
        if mask.any():
            out[mask] = rankdata(v[mask]) / (mask.sum() + 1)
    return out


def detrend_log1p(total: np.ndarray, years: np.ndarray) -> np.ndarray:
    """Residuals of log1p(total) after an OLS linear trend on the year."""
    z = np.log1p(np.asarray(total, dtype=float))
    t = np.asarray(years, dtype=float)
    slope, intercept = np.polyfit(t, z, 1)
    return z - (slope * t + intercept)
