"""SA2.3 empirical quantile mapping on block-month totals.

Per block, the positive source totals and the positive target totals (all calendar months pooled) are matched
quantile to quantile. Zero maps to zero (the curve starts at the origin), only positives are fitted, and above
the largest training source value the curve continues with the constant ratio y_max / x_max. The map is
monotone and finite. It is not additive, so it is applied to totals, never cell by cell. Blocks with too few
positive months in either series use one map fitted on all blocks pooled ("national" fallback).
"""

from dataclasses import dataclass

import numpy as np

N_KNOTS = 200
MIN_POSITIVE = 12  # positive months required in both series for a block-specific map


@dataclass(frozen=True, eq=False)
class QMap:
    xk: np.ndarray  # strictly increasing, xk[0] == 0
    yk: np.ndarray  # non-decreasing, yk[0] == 0
    tail_ratio: float

    def __call__(self, x) -> np.ndarray:
        x = np.asarray(x, dtype="float64")
        inside = np.interp(x, self.xk, self.yk)
        out = np.where(x > self.xk[-1], x * self.tail_ratio, inside)
        return np.where(x > 0, out, 0.0)


def fit_qmap(x, y, n_knots: int = N_KNOTS) -> QMap | None:
    """Fit on the positive values of x (source) and y (target); None when either has no positives."""
    xp = np.asarray(x, dtype="float64").ravel()
    yp = np.asarray(y, dtype="float64").ravel()
    xp, yp = xp[xp > 0], yp[yp > 0]
    if xp.size == 0 or yp.size == 0:
        return None
    n = min(max(xp.size, yp.size), n_knots)
    p = (np.arange(n) + 0.5) / n
    xk, yk = np.quantile(xp, p), np.quantile(yp, p)
    xu, inv = np.unique(xk, return_inverse=True)
    yu = np.zeros(xu.size)
    np.maximum.at(yu, inv, yk)
    xu, yu = np.concatenate([[0.0], xu]), np.concatenate([[0.0], yu])
    return QMap(xu, yu, float(yu[-1] / xu[-1]))


@dataclass(frozen=True, eq=False)
class BlockQMaps:
    maps: list[QMap | None]  # per block; None = zero predictions
    fallback: np.ndarray  # bool per block: the national map was used

    def apply(self, x: np.ndarray) -> np.ndarray:
        """x: (rows, blocks) block-month totals -> mapped totals."""
        out = np.zeros_like(x, dtype="float64")
        for b, m in enumerate(self.maps):
            if m is not None:
                out[:, b] = m(x[:, b])
        return out


def fit_block_qmaps(
    src: np.ndarray, tgt: np.ndarray, train: np.ndarray, min_positive: int = MIN_POSITIVE
) -> BlockQMaps:
    """src, tgt: (rows, blocks) block-month totals; fit on rows in `train`."""
    xs, ys = src[train], tgt[train]
    national = fit_qmap(xs, ys)
    maps: list[QMap | None] = []
    fallback = np.zeros(src.shape[1], dtype=bool)
    for b in range(src.shape[1]):
        if (xs[:, b] > 0).sum() >= min_positive and (ys[:, b] > 0).sum() >= min_positive:
            maps.append(fit_qmap(xs[:, b], ys[:, b]))
        else:
            maps.append(national)
            fallback[b] = True
    return BlockQMaps(maps, fallback)
