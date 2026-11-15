"""SA2.5 temporal validation splitters (docs/validation.md): leave-one-year-out with gap, rolling origin.

Pure pandas/numpy. Splitters take one date per row and return boolean masks aligned with the input rows.
"""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True, eq=False)
class Fold:
    test_year: int
    train: np.ndarray  # boolean mask over the input rows
    test: np.ndarray  # boolean mask over the input rows


def _year_month(dates: Sequence | pd.Series | pd.Index) -> tuple[np.ndarray, np.ndarray]:
    idx = pd.DatetimeIndex(
        pd.to_datetime(pd.Series(list(dates)) if not isinstance(dates, pd.Series) else dates)
    )
    if idx.tz is not None:
        idx = idx.tz_convert("UTC").tz_localize(None)
    year = idx.year.to_numpy().astype(np.int64)
    return year, year * 12 + idx.month.to_numpy().astype(np.int64) - 1


def leave_one_year_out(dates, gap_months: int = 6) -> list[Fold]:
    """Each year is the test once; training drops the test year and `gap_months` months on each side."""
    year, ym = _year_month(dates)
    folds = []
    for y in np.unique(year):
        lo, hi = int(y) * 12 - gap_months, int(y) * 12 + 11 + gap_months
        folds.append(Fold(int(y), (ym < lo) | (ym > hi), year == y))
    return folds


def rolling_origin(dates, min_train_years: int = 1) -> list[Fold]:
    """Train on every year <= t, test on t+1. Years with too few prior years are skipped."""
    year, _ = _year_month(dates)
    years = np.unique(year)
    folds = []
    for y in years:
        if int((years < y).sum()) < min_train_years:
            continue
        folds.append(Fold(int(y), year < y, year == y))
    return folds
