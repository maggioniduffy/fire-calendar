import numpy as np
import pandas as pd

from firecal.stages.harmonize.intervals import (
    conformal_bounds,
    conformal_intervals,
    fit_binned,
    inner_residuals,
)
from firecal.stages.harmonize.scale_factor import fit_factors, predict_total
from firecal.stages.harmonize.validation import leave_one_year_out

F_DAY, F_NIGHT = 0.4, 0.2


def poisson_data(seed=0, years=range(2012, 2022), n_blocks=30):
    """Latent mean mu per block-month; source ~ Poisson(mu), target ~ Poisson(f * mu): known factor."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range(f"{years[0]}-01-01", f"{years[-1]}-12-01", freq="MS")
    mu = np.exp(rng.normal(3.0, 1.5, size=(len(dates), n_blocks, 1))) * np.array([[[1.0, 0.5]]])
    src = rng.poisson(mu).astype(float)
    tgt = rng.poisson(mu * np.array([F_DAY, F_NIGHT])).astype(float)
    return dates, dates.month.to_numpy() - 1, src, tgt


def outer_cover(dates, month_idx, src, tgt, k=20.0, **kw):
    cov, tot = 0, 0
    for fold in leave_one_year_out(dates, 6):
        tr, te = fold.train, fold.test
        fac = fit_factors(src, tgt, month_idx, tr, k)
        pred = predict_total(fac, src[te], month_idx[te])
        out = conformal_intervals(src, tgt, dates, month_idx, tr, k, pred, src[te].sum(axis=-1), **kw)
        obs = tgt[te].sum(axis=-1)
        active = src[te].sum(axis=-1) > 0  # rows defined by the source, known at prediction time
        lo, hi = out.month
        cov += int(((obs >= lo - 1e-9) & (obs <= hi + 1e-9) & active).sum())
        tot += int(active.sum())
    return cov / tot


def test_conformal_bounds_rank_correction():
    r = np.arange(1, 100, dtype=float)  # n = 99
    lo, hi, capped = conformal_bounds(r, 0.2)
    assert (lo, hi, capped) == (10.0, 90.0, False)
    lo, hi, capped = conformal_bounds(np.array([1.0, 2.0, 3.0]), 0.2)  # too few for the level
    assert (lo, hi, capped) == (0.0, 3.0, True)


def test_coverage_on_held_out_years_near_nominal():
    dates, month_idx, src, tgt = poisson_data()
    assert 0.74 <= outer_cover(dates, month_idx, src, tgt) <= 0.87


def test_calibration_uses_no_outer_test_year_rows():
    dates, month_idx, src, tgt = poisson_data()
    for fold in leave_one_year_out(dates, 6):
        res = inner_residuals(src, tgt, dates, month_idx, fold.train, 20.0)
        assert res.used.any()
        assert not (res.used & fold.test).any()
        assert not (res.used & ~fold.train).any()  # nor the 6-month gap on each side


def test_changing_outer_test_target_does_not_move_intervals():
    dates, month_idx, src, tgt = poisson_data()
    fold = leave_one_year_out(dates, 6)[3]
    fac = fit_factors(src, tgt, month_idx, fold.train, 20.0)
    pred = predict_total(fac, src[fold.test], month_idx[fold.test])
    a = conformal_intervals(src, tgt, dates, month_idx, fold.train, 20.0, pred)
    tgt2 = tgt.copy()
    tgt2[fold.test | ~fold.train] *= 7  # test year and gap rows are not training data
    b = conformal_intervals(src, tgt2, dates, month_idx, fold.train, 20.0, pred)
    assert np.array_equal(a.month[0], b.month[0]) and np.array_equal(a.month[1], b.month[1])
    assert np.array_equal(a.year[0], b.year[0]) and np.array_equal(a.year[1], b.year[1])


def test_bins_with_few_residuals_are_merged():
    rng = np.random.default_rng(1)
    pred = np.concatenate([rng.uniform(1, 2, 40), rng.uniform(50, 60, 10), rng.uniform(100, 200, 40)])
    obs = pred * rng.uniform(0.5, 1.5, len(pred))
    cal = fit_binned(pred, obs, n_bins=5, min_n=30)
    assert cal.n.min() >= 30
    assert len(cal.n) < 5
    assert cal.n.sum() == len(pred)
    one = fit_binned(pred[:20], obs[:20], n_bins=5, min_n=30)  # fewer than min_n in total: a single bin
    assert len(one.n) == 1


def test_zero_observed_gives_zero_residual_and_no_nan():
    pred = np.linspace(1, 10, 200)
    obs = np.zeros_like(pred)
    cal = fit_binned(pred, obs, n_bins=3, min_n=20)
    assert np.all(cal.lo == 0) and np.all(cal.hi == 0)
    lo, hi = cal.apply(np.array([0.0, 3.0, 50.0]))
    assert np.all(np.isfinite(lo)) and np.all(np.isfinite(hi))
    assert np.all(lo == 0) and np.all(hi == 0)
    # mixed: zeros are part of the residual sample, so the lower bound reaches 0
    obs2 = np.where(np.arange(200) % 2 == 0, 0.0, pred)
    cal2 = fit_binned(pred, obs2, n_bins=1, min_n=20)
    assert cal2.lo[0] == 0.0 and cal2.hi[0] == 1.0
    lo, hi = cal2.apply(np.array([0.0, 4.0]))
    assert (lo[0], hi[0]) == (0.0, 0.0) and lo[1] == 0.0 and hi[1] == 4.0


def test_block_year_calibrated_separately():
    dates, month_idx, src, tgt = poisson_data()
    fold = leave_one_year_out(dates, 6)[4]
    fac = fit_factors(src, tgt, month_idx, fold.train, 20.0)
    pred = predict_total(fac, src[fold.test], month_idx[fold.test])
    out = conformal_intervals(src, tgt, dates, month_idx, fold.train, 20.0, pred)
    lo_y, hi_y = out.year
    assert lo_y.shape == hi_y.shape == (pred.shape[1],)
    assert (lo_y <= hi_y).all()
    assert out.calib_year.n.sum() != out.calib_month.n.sum()  # its own residual set, not the month bounds


def test_zero_prediction_gets_positive_upper_bound_when_inner_rows_had_observed():
    rng = np.random.default_rng(3)
    pred = np.concatenate([np.zeros(80), rng.uniform(20, 200, 300)])
    obs = np.concatenate([rng.poisson(2.0, 80).astype(float), pred[80:] * rng.uniform(0.7, 1.3, 300)])
    cal = fit_binned(pred, obs, small=5.0)
    assert cal.n_small == 80 and cal.add_hi > 0
    lo, hi = cal.apply(np.array([0.0, 100.0]))
    assert lo[0] == 0.0 and hi[0] > 0
    assert lo[1] > 0 and hi[1] > lo[1]  # multiplicative bin above the threshold
    lo, hi = cal.apply(np.array([0.0]), active=np.array([False]))  # no source count: out of reach, [0, 0]
    assert (lo[0], hi[0]) == (0.0, 0.0)


def test_inner_rows_without_source_are_not_calibration_data():
    dates, month_idx, src, tgt = poisson_data()
    src = src.copy()
    src[::3] = 0.0  # every third month has no source count anywhere
    fold = leave_one_year_out(dates, 6)[2]
    res = inner_residuals(src, tgt, dates, month_idx, fold.train, 20.0)
    n_active = int(((src.sum(axis=-1) > 0) & res.used[:, None]).sum())
    assert len(res.pred_month) == n_active
    fac = fit_factors(src, tgt, month_idx, fold.train, 20.0)
    pred = predict_total(fac, src[fold.test], month_idx[fold.test])
    ts = src[fold.test].sum(axis=-1)
    out = conformal_intervals(src, tgt, dates, month_idx, fold.train, 20.0, pred, ts)
    assert (out.month[0][ts == 0] == 0).all() and (out.month[1][ts == 0] == 0).all()
