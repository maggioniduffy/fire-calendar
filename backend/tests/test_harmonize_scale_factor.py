import numpy as np
import pandas as pd
import pytest

from firecal.stages.harmonize.evaluate import run_cv, score_table
from firecal.stages.harmonize.regions import Cube, build_cube, ym_of
from firecal.stages.harmonize.scale_factor import (
    fit_factors,
    inner_folds,
    predict_total,
    select_k,
)

YEARS = range(2013, 2019)


def synthetic(blocks=(10, 11, 12), f_day=0.4, f_night=0.2) -> Cube:
    """S-NPP counts follow a seasonal pattern; Terra + Aqua are exact multiples (day and night differ)."""
    rows = []
    for y in YEARS:
        for m in range(1, 13):
            for i, b in enumerate(blocks):
                base = 20 + 7 * m + 3 * i + (y % 3)
                for dn, f in (("D", f_day), ("N", f_night)):
                    snpp = base if dn == "D" else base // 2
                    rows.append((b, ym_of(y, m), dn, "snpp", snpp))
                    rows.append((b, ym_of(y, m), dn, "terra", f * snpp * 0.25))
                    rows.append((b, ym_of(y, m), dn, "aqua", f * snpp * 0.75))
    return build_cube(pd.DataFrame(rows, columns=["block", "ym", "daynight", "satellite", "count"]))


def arrays(cube: Cube):
    sel = cube.select(("snpp", "terra", "aqua"))
    src = cube.total(("snpp",))[sel]
    tgt = cube.total(("terra", "aqua"))[sel]
    return src, tgt, cube.month_idx[sel], cube.dates[sel]


def test_recovers_known_factor_per_daynight():
    src, tgt, month, _ = arrays(synthetic())
    fac = fit_factors(src, tgt, month, np.ones(len(month), dtype=bool), k=0.0)
    assert np.allclose(fac.f[..., 0], 0.4)
    assert np.allclose(fac.f[..., 1], 0.2)
    pred = predict_total(fac, src, month)
    assert np.allclose(pred, tgt.sum(axis=-1))


def test_shrinkage_pulls_sparse_block_toward_national():
    # Calendar month 0, day only. Block 0 is large (ratio 0.5), block 1 is sparse (S=2, T=2, ratio 1.0).
    src = np.zeros((1, 2, 2))
    tgt = np.zeros((1, 2, 2))
    src[0, :, 0], tgt[0, :, 0] = [1000.0, 2.0], [500.0, 2.0]
    month, train = np.array([0]), np.array([True])
    f_nat = 502 / 1002
    raw = fit_factors(src, tgt, month, train, k=0.0)
    shrunk = fit_factors(src, tgt, month, train, k=100.0)
    assert raw.f[0, 1, 0] == pytest.approx(1.0)
    assert shrunk.f[0, 1, 0] == pytest.approx((2 + 100 * f_nat) / (2 + 100))
    assert abs(shrunk.f[0, 1, 0] - f_nat) < abs(raw.f[0, 1, 0] - f_nat)
    assert shrunk.f[0, 0, 0] == pytest.approx(0.5, abs=0.01)  # the large block barely moves


def test_zero_count_cells_do_not_break_it():
    src = np.zeros((2, 3, 2))
    tgt = np.zeros((2, 3, 2))
    src[:, 0, 0], tgt[:, 0, 0] = 10.0, 5.0  # only one block/daynight has data; the rest is all zeros
    month, train = np.array([0, 1]), np.array([True, True])
    for k in (0.0, 5.0):
        fac = fit_factors(src, tgt, month, train, k)
        assert np.isfinite(fac.f).all() and np.isfinite(fac.f_nat).all()
        pred = predict_total(fac, src, month)
        assert np.isfinite(pred).all()
        assert (pred[:, 1:] == 0).all()  # zero source -> zero prediction
    # night has no data anywhere: falls back to a finite ratio (1.0) and never to nan
    assert np.isfinite(fit_factors(src, tgt, month, train, 0.0).f[..., 1]).all()


def test_inner_folds_never_train_on_test_or_gap():
    cube = synthetic()
    src, tgt, month, dates = arrays(cube)
    train = np.asarray(dates.year != 2015)
    folds = inner_folds(dates, train, gap_months=6)
    assert folds
    for tr, te in folds:
        assert not (tr & te).any()
        assert not tr[~train].any() and not te[~train].any()
        y = dates[te][0].year
        near = (dates >= pd.Timestamp(y - 1, 7, 1)) & (dates <= pd.Timestamp(y + 1, 6, 30))
        assert not tr[near].any()


def test_select_k_returns_grid_value_and_flags_fallback():
    cube = synthetic()
    src, tgt, month, dates = arrays(cube)
    k, fb = select_k(src, tgt, dates, month, np.ones(len(month), dtype=bool), (0.0, 10.0))
    assert k in (0.0, 10.0) and not fb
    one_year = np.asarray(dates.year == 2013)
    k, fb = select_k(src, tgt, dates, month, one_year, (0.0, 10.0))
    assert fb  # one year cannot be split with a gap


def test_run_cv_on_exact_data_has_no_error_and_excludes_test_year():
    cube = synthetic()
    folds = run_cv(cube, "viirs_to_modis", "loyo")
    sf = [f for f in folds if f.method == "sf"]
    assert [f.test_year for f in sf] == list(YEARS)
    for f in sf:
        assert np.allclose(f.pred, f.obs)
    s = score_table(folds)
    row = s[(s.method == "sf") & (s.test_year == "all") & (s.level == "block-month")].iloc[0]
    assert row["wape"] == pytest.approx(0, abs=1e-9)
    rolling = run_cv(cube, "viirs_to_modis", "rolling")
    assert min(f.test_year for f in rolling) == 2014  # needs one prior year
