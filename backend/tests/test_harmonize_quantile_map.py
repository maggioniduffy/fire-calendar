import numpy as np

from firecal.stages.harmonize.quantile_map import fit_block_qmaps, fit_qmap

RNG = np.random.default_rng(0)


def test_recovers_target_distribution():
    x = RNG.gamma(2.0, 50.0, 4000)
    y = RNG.gamma(3.0, 40.0, 4000) + 10
    m = fit_qmap(x, y)
    x_new = RNG.gamma(2.0, 50.0, 4000)
    qs = [0.1, 0.25, 0.5, 0.75, 0.9]
    mapped, target = np.quantile(m(x_new), qs), np.quantile(y, qs)
    assert np.allclose(mapped, target, rtol=0.08)


def test_zero_maps_to_zero_and_positives_only_are_fitted():
    x = np.concatenate([np.zeros(300), RNG.gamma(2.0, 20.0, 300)])
    y = np.concatenate([np.zeros(100), RNG.gamma(2.0, 60.0, 500)])
    m = fit_qmap(x, y)
    assert m(0.0) == 0.0
    assert (m(np.array([0.0, 0.0, 5.0])) == np.array([0.0, 0.0, m(5.0)])).all()
    assert m(1e-9) > 0  # any positive source is positive after mapping


def test_extrapolation_is_finite_monotone_with_constant_ratio():
    x = RNG.gamma(2.0, 20.0, 500)
    y = 3 * RNG.gamma(2.0, 20.0, 500)
    m = fit_qmap(x, y)
    grid = np.linspace(0, x.max() * 10, 2000)
    out = m(grid)
    assert np.isfinite(out).all()
    assert (np.diff(out) >= 0).all()
    top = grid[grid > x.max() * 1.0001]
    ratios = m(top) / top
    assert np.allclose(ratios, ratios[0])


def test_no_positives_returns_none_and_blocks_fall_back_to_national():
    assert fit_qmap(np.zeros(10), np.ones(10)) is None
    # block 0 has plenty of positive months, block 1 almost none -> national map for block 1
    src = np.zeros((60, 2))
    tgt = np.zeros((60, 2))
    src[:, 0], tgt[:, 0] = RNG.gamma(2, 20, 60) + 1, RNG.gamma(2, 50, 60) + 1
    src[:3, 1], tgt[:3, 1] = [5.0, 8.0, 9.0], [10.0, 15.0, 20.0]
    maps = fit_block_qmaps(src, tgt, np.ones(60, dtype=bool))
    assert list(maps.fallback) == [False, True]
    out = maps.apply(src)
    assert out.shape == src.shape and np.isfinite(out).all()
    assert (out[3:, 1] == 0).all()  # zero stays zero in the fallback block too
