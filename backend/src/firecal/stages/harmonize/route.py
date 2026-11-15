"""SA2.10 routes from NOAA-20 to MODIS-equivalent counts: the chain and the direct factor (P5).

- chain: NOAA-20 -> S-NPP (`noaa20_to_snpp`, months from 2018-05) then S-NPP -> MODIS (`viirs_to_modis`,
months
  from 2012-02), each leg fitted with the SA2.2 estimator and its own `k`; the route factor is the product
  of the
  two leg factors per calendar month x block x day/night (and of the national ones).
- direct: one NOAA-20 -> MODIS factor (pair `noaa20_to_modis`, months from 2018-05), same estimator, same `k`
  selection.

Every function works on a `Cube` already restricted to the blocks of the calibration. `exclude` is an
inclusive
(first, last) `ym` window that is removed from the training months of every leg: the inner leave-one-year-out
folds (year +- 6 months, as in `validation.leave_one_year_out`) use it, so a leg never sees the months it
predicts.
"""

from dataclasses import dataclass

import numpy as np

from firecal.stages.harmonize.evaluate import GAP_MONTHS, PAIRS, PairData, pair_data
from firecal.stages.harmonize.intervals import InnerResiduals, collect_residuals
from firecal.stages.harmonize.regions import Cube
from firecal.stages.harmonize.scale_factor import Factors, fit_factors, select_k

ROUTE_PAIR = "noaa20_to_modis"
LEGS = ("noaa20_to_snpp", "viirs_to_modis")
ROUTES = ("chain", "direct")


@dataclass(eq=False)
class RouteFit:
    route: str
    f: np.ndarray  # (12, blocks, 2)
    f_nat: np.ndarray  # (12, 2)
    k: dict[str, float]  # k of each leg (chain) or {ROUTE_PAIR: k} (direct)
    k_fallback: bool

    def predict(self, src: np.ndarray, month_idx: np.ndarray) -> np.ndarray:
        """NOAA-20 counts (rows, blocks, 2) -> MODIS-eq per block (day and night predicted, then summed)."""
        return (self.f[month_idx] * src).sum(axis=-1)


def year_window(year: int, gap: int = GAP_MONTHS) -> tuple[int, int]:
    """Months removed from training around a test year: the year and `gap` months on each side."""
    return year * 12 - gap, year * 12 + 11 + gap


def fit_leg(
    cube: Cube, pair: str, end: int, exclude: tuple[int, int] | None = None, d: PairData | None = None
) -> tuple[Factors, float, bool]:
    """SA2.2 factors of one pair on its overlap months up to `end`, minus `exclude`; `k` by inner LOYO."""
    d = d or pair_data(cube, PAIRS[pair], end)
    train = np.ones(len(d.ym), dtype=bool)
    if exclude is not None:
        train &= ~((d.ym >= exclude[0]) & (d.ym <= exclude[1]))
    k, fb = select_k(d.src, d.tgt, d.dates, d.month_idx, train, gap_months=GAP_MONTHS)
    return fit_factors(d.src, d.tgt, d.month_idx, train, k), k, fb


def fit_route(cube: Cube, route: str, end: int, exclude: tuple[int, int] | None = None) -> RouteFit:
    if route == "direct":
        fac, k, fb = fit_leg(cube, ROUTE_PAIR, end, exclude)
        return RouteFit("direct", fac.f, fac.f_nat, {ROUTE_PAIR: k}, fb)
    if route == "chain":
        (a, ka, fa), (b, kb, fb) = (fit_leg(cube, leg, end, exclude) for leg in LEGS)
        return RouteFit("chain", a.f * b.f, a.f_nat * b.f_nat, {LEGS[0]: ka, LEGS[1]: kb}, fa or fb)
    raise ValueError(f"route must be one of {ROUTES}, not {route!r}")


def loyo_predictions(cube: Cube, route: str, end: int) -> list[tuple[int, np.ndarray, np.ndarray]]:
    """Out-of-fold predictions of the route over its own months up to `end`, one fold per year.

    Each fold refits every leg (and its `k`) without the test year and the 6 months on each side. Returns
    (year, row mask over the route months, predictions (rows, blocks)).
    """
    d = pair_data(cube, PAIRS[ROUTE_PAIR], end)
    out = []
    for y in np.unique(d.year_idx):
        te = d.year_idx == y
        fit = fit_route(cube, route, end, year_window(int(y)))
        out.append((int(y), te, fit.predict(d.src[te], d.month_idx[te])))
    return out


def inner_residuals_from(d: PairData, folds: list[tuple[int, np.ndarray, np.ndarray]]) -> InnerResiduals:
    parts = [(p, d.tgt[te].sum(axis=-1), d.src[te].sum(axis=-1)) for _, te, p in folds]
    used = np.zeros(len(d.ym), dtype=bool)
    for _, te, _ in folds:
        used |= te
    return collect_residuals(parts, used)


def route_inner_residuals(cube: Cube, route: str, end: int) -> InnerResiduals:
    """Residuals for the conformal bands of the route: the out-of-fold predictions of `loyo_predictions`."""
    d = pair_data(cube, PAIRS[ROUTE_PAIR], end)
    return inner_residuals_from(d, loyo_predictions(cube, route, end))
