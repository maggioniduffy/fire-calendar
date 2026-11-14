from datetime import date

import numpy as np
import pandas as pd

from firecal.stages.harmonize.validation import Fold, leave_one_year_out, rolling_origin

DATES = pd.Series(pd.date_range("2012-01-01", "2020-12-31", freq="D"))


def _months(d: pd.Series) -> pd.Series:
    return d.dt.year * 12 + d.dt.month - 1


def test_every_year_is_test_once_and_masks_cover_it():
    folds = leave_one_year_out(DATES)
    assert [f.test_year for f in folds] == list(range(2012, 2021))
    for f in folds:
        assert isinstance(f, Fold)
        assert f.test.sum() == (DATES.dt.year == f.test_year).sum()
        assert (DATES[f.test].dt.year == f.test_year).all()
        assert not (f.train & f.test).any()


def test_gap_excluded_from_training():
    for f in leave_one_year_out(DATES, gap_months=6):
        y = f.test_year
        tr = DATES[f.train]
        assert not ((tr >= pd.Timestamp(y - 1, 7, 1)) & (tr <= pd.Timestamp(y + 1, 6, 30))).any()
        # the day just outside the gap is still trained on (when it exists)
        before = pd.Timestamp(y - 1, 6, 30)
        after = pd.Timestamp(y + 1, 7, 1)
        for d in (before, after):
            if d in set(DATES):
                assert f.train[DATES[d == DATES].index[0]]


def test_no_test_or_gap_date_in_training_with_other_gaps():
    for gap in (0, 3, 12):
        for f in leave_one_year_out(DATES, gap_months=gap):
            m = _months(DATES)
            lo, hi = f.test_year * 12 - gap, f.test_year * 12 + 11 + gap
            assert not ((m[f.train] >= lo) & (m[f.train] <= hi)).any()


def test_edge_years_and_accepts_date_objects():
    dates = [date(2012, 1, 5), date(2013, 6, 1), date(2014, 12, 31), date(2016, 3, 3)]
    folds = leave_one_year_out(dates)
    assert [f.test_year for f in folds] == [2012, 2013, 2014, 2016]
    first, last = folds[0], folds[-1]
    assert first.test.tolist() == [True, False, False, False]
    assert last.test.tolist() == [False, False, False, True]
    # 2016-03 is 15 months after 2014-12, outside the gap; 2013-06 is inside 2012's gap
    assert last.train.tolist() == [True, True, True, False]
    assert first.train.tolist() == [False, False, True, True]


def test_rolling_origin_never_trains_on_test_or_later():
    folds = rolling_origin(DATES)
    assert [f.test_year for f in folds] == list(range(2013, 2021))
    for f in folds:
        assert DATES[f.train].dt.year.max() == f.test_year - 1
        assert (DATES[f.test].dt.year == f.test_year).all()
        assert f.test.sum() == (DATES.dt.year == f.test_year).sum()
        assert not (f.train & f.test).any()


def test_rolling_origin_min_train_years_and_single_year():
    folds = rolling_origin(DATES, min_train_years=3)
    assert folds[0].test_year == 2015
    assert rolling_origin(pd.Series(pd.date_range("2020-01-01", periods=10))) == []


def test_empty_input():
    assert leave_one_year_out([]) == []
    assert isinstance(leave_one_year_out(DATES)[0].train, np.ndarray)
