import numpy as np
import pandas as pd

from firecal.stages.enso_lite import core


def test_circular_window_picks_dec_to_mar():
    med = np.array([10, 8, 6, 1, 0, 0, 0, 0, 0, 1, 2, 12], dtype=float)  # peak around Dec-Mar
    w = core.season_window(med)
    assert (w["start_month"], w["length"], w["fallback"]) == (12, 4, False)
    assert abs(w["share"] - 36 / 40) < 1e-12


def test_flat_climatology_falls_back_to_jul_jun():
    w = core.season_window(np.ones(12))
    assert (w["start_month"], w["length"], w["fallback"]) == (7, 12, True)
    assert abs(w["best_share"] - 4 / 12) < 1e-12


def test_season_totals_wrap_and_drop_incomplete():
    idx = [core.month_index(2000 + i // 12, i % 12 + 1) for i in range(36)]
    vals = np.ones(36)
    vals[20] = np.nan  # Sep 2001
    s = pd.Series(vals, index=idx)
    t = core.season_totals(s, 12, 4)  # Dec-Mar
    assert t["season_year"].tolist() == [2000, 2001]  # 2002 has no following months
    assert t["total"].tolist() == [4.0, 4.0]
    t2 = core.season_totals(s, 8, 4)  # Aug-Nov: 2001 contains the NaN
    assert 2001 not in t2["season_year"].tolist()


def test_lag_indexing_reads_oni_at_start_minus_k():
    idx = np.arange(core.month_index(2000, 1), core.month_index(2004, 1))
    oni = pd.Series(idx.astype(float), index=idx)  # value = month index
    x = core.lagged_oni(oni, [2002], start_month=12)
    start = core.month_index(2002, 12)
    assert np.array_equal(x[0], start - np.arange(13))
    assert x.shape == (1, 13)


def test_planted_monotone_relation_gives_rho_one():
    rng = np.random.default_rng(0)
    x = rng.normal(size=(25, 13))
    y = np.exp(x[:, 4])  # monotone in lag 4
    rho = core.spearman(y, x)
    assert abs(rho[4] - 1.0) < 1e-12
    assert np.all(np.abs(rho[np.arange(13) != 4]) < 1.0)


def test_permutation_null_independent_data_is_not_significant():
    rng = np.random.default_rng(1)
    n, b = 25, 1000
    years = np.arange(n)
    perms = core.induce(core.shared_permutations(n, b, np.random.default_rng(2)), years)
    ps = []
    for _ in range(40):
        y, x = rng.normal(size=n), rng.normal(size=(n, 13))
        rho = core.spearman(y, x)
        _, fw = core.perm_pvalues(rho, core.permutation_rhos(y, x, perms))
        ps.append(fw)
    # under the null the family-wise p is roughly uniform: few rejections, mean near 0.5
    assert np.mean(np.array(ps) <= 0.05) <= 0.15
    assert 0.3 < np.mean(ps) < 0.7
    # fixed-seed single case
    y, x = np.random.default_rng(3).normal(size=n), np.random.default_rng(4).normal(size=(n, 13))
    _, fw = core.perm_pvalues(core.spearman(y, x), core.permutation_rhos(y, x, perms))
    assert fw > 0.05


def test_whole_year_permutation_keeps_each_row_lag_vector():
    x = np.arange(6 * 13, dtype=float).reshape(6, 13)
    perms = core.induce(
        core.shared_permutations(10, 5, np.random.default_rng(0)), np.array([0, 2, 3, 5, 7, 9])
    )
    for p in perms:
        assert sorted(p.tolist()) == list(range(6))
        out = core.permute_rows(x, p)
        assert {tuple(r) for r in out} == {tuple(r) for r in x}
        for i, r in enumerate(out):
            assert np.array_equal(r, x[p[i]])


def test_block_bootstrap_ci_in_range_and_deterministic():
    rng = np.random.default_rng(5)
    y, x = rng.normal(size=25), rng.normal(size=(25, 13))

    def ci(seed):
        idx = core.block_indices(25, 300, 3, np.random.default_rng(seed))
        return core.bootstrap_ci(y, x, idx)

    lo, hi = ci(7)
    assert np.all(lo >= -1) and np.all(hi <= 1) and np.all(lo <= hi)
    lo2, hi2 = ci(7)
    assert np.array_equal(lo, lo2) and np.array_equal(hi, hi2)
    idx = core.block_indices(25, 50, 3, np.random.default_rng(7))
    assert idx.shape == (50, 25) and idx.min() >= 0 and idx.max() <= 24
    # blocks are consecutive runs
    assert np.all(np.diff(idx[:, :3], axis=1) == 1)


def test_lag1_autocorr_and_within_era_ranks():
    yrs = np.arange(10)
    assert core.lag1_autocorr(np.arange(10.0), yrs) > 0.99
    r = core.within_era_ranks(
        np.array([5.0, 1.0, 3.0, 9.0, 2.0, 4.0]), np.array([2010, 2011, 2012, 2013, 2014, 2015]), 2012
    )
    assert np.allclose(r[:2], [2 / 3, 1 / 3]) and np.allclose(r[2:], [2 / 5, 4 / 5, 1 / 5, 3 / 5])
