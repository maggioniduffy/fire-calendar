"""SA2.4 / SA2.7 LightGBM: synthetic, no network. Small configurations keep each test to a few seconds."""

import numpy as np
import pandas as pd
import pytest

from firecal.stages.grid.grid import cell_center, cell_ids
from firecal.stages.harmonize.evaluate import FoldOut, run_cv
from firecal.stages.harmonize.metrics import wape
from firecal.stages.harmonize.ml import (
    GBMConfig,
    fit_final,
    fitted_factors,
    oof_factors,
    prepare,
    run_ml_cv,
)
from firecal.stages.harmonize.ml_criterion import bootstrap_diff, evaluate_criterion
from firecal.stages.harmonize.ml_features import BASE_FEATURES, build_cell_rows, monthly_cell_table
from firecal.stages.harmonize.regions import build_cube, monthly_region_table
from firecal.stages.harmonize.scale_factor import fit_factors, select_k
from firecal.stages.harmonize.validation import leave_one_year_out

SMALL = (GBMConfig("t", num_leaves=7, min_data=20, lr=0.2, l2=1.0, iters=(20, 40)),)
YEARS = range(2013, 2019)
R_LOW, R_HIGH = 0.1, 0.6


def synth_grid(seed=0, ratio_by_frp=True, poison_year=None, poison_gap=6, thin=1.0, modis_night=1.0):
    """Two 2.5 degree blocks of 6x6 cells. S-NPP is the source; Terra + Aqua the target.

    The target mean is `mu * ratio`, where the ratio is high for high FRP-per-detection cells. The share of
    high-FRP cells changes at random from block-month to block-month, so no per-block, per-calendar-month
    constant factor can follow it. With `poison_year`, test-year targets and every gap-month detection are
    multiplied by 50 (the model must not notice).
    """
    rng = np.random.default_rng(seed)
    cells = []
    for lat0, lon0 in ((-29.95, -64.95), (-29.95, -62.45)):
        for i in range(6):
            for j in range(6):
                cells.append((lat0 + 0.1 * i, lon0 + 0.1 * j))
    lat = np.array([c[0] for c in cells])
    lon = np.array([c[1] for c in cells])
    cid = cell_ids(lat, lon, 0.1)
    clat, clon = cell_center(cid, 0.1)
    blk = (lon > -63.5).astype(int)
    rows = []
    for y in YEARS:
        for m in range(1, 13):
            ym = y * 12 + m - 1
            p_high = rng.uniform(0.1, 0.9, size=2)
            high = rng.random(len(cid)) < p_high[blk]
            mu = np.exp(rng.normal(1.8, 0.4, len(cid)))
            ratio = np.where(high, R_HIGH, R_LOW) if ratio_by_frp else np.full(len(cid), 0.3)
            frp_mean = np.where(high, 50.0, 5.0)
            in_year = poison_year is not None and y == poison_year
            gap = (
                poison_year is not None
                and y != poison_year
                and (poison_year * 12 - poison_gap <= ym <= poison_year * 12 + 11 + poison_gap)
            )
            for dn, share in (("D", 1.0), ("N", 0.5)):
                s = rng.poisson(mu * share)
                t_terra = rng.poisson(mu * share * ratio * 0.5)
                t_aqua = rng.poisson(mu * share * ratio * 0.5)
                if dn == "N" and modis_night < 1.0:
                    t_terra, t_aqua = rng.binomial(t_terra, modis_night), rng.binomial(t_aqua, modis_night)
                if thin < 1.0:
                    t_terra, t_aqua = rng.binomial(t_terra, thin), rng.binomial(t_aqua, thin)
                if gap:
                    s, t_terra, t_aqua = s * 50, t_terra * 50, t_aqua * 50
                if in_year:
                    t_terra, t_aqua = t_terra * 50, t_aqua * 50
                date = f"{y}-{m:02d}-15"
                for sat, cnt in (("snpp", s), ("terra", t_terra), ("aqua", t_aqua)):
                    for c in np.flatnonzero(cnt > 0):
                        rows.append(
                            (
                                date,
                                sat,
                                dn,
                                int(cid[c]),
                                int(cnt[c]),
                                float(cnt[c] * frp_mean[c]),
                                clat[c],
                                clon[c],
                            )
                        )
    return pd.DataFrame(
        rows,
        columns=["acq_date", "satellite", "daynight", "cell_id", "count", "frp_sum", "cell_lat", "cell_lon"],
    )


def setup(grid, pair="viirs_to_modis"):
    cube = build_cube(monthly_region_table(grid))
    return cube, prepare(cube, monthly_cell_table(grid), pair)


@pytest.fixture(scope="module")
def world():
    grid = synth_grid()
    cube, prep = setup(grid)
    return grid, cube, prep


def test_model_beats_constant_factor_when_ratio_depends_on_a_feature(world):
    _, cube, prep = world
    folds, _ = run_ml_cv(prep, "loyo", SMALL, SMALL, ablations=False, with_intervals=False)
    sf = [f for f in run_cv(cube, "viirs_to_modis", "loyo") if f.method == "sf"]
    obs_sf = np.concatenate([f.obs.ravel() for f in sf])
    pred_sf = np.concatenate([f.pred.ravel() for f in sf])
    cell = [f for f in folds if f.method == "lgb_cell"]
    assert len(cell) == len(YEARS)
    obs = np.concatenate([f.obs.ravel() for f in cell])
    pred = np.concatenate([f.pred.ravel() for f in cell])
    assert np.allclose(obs, obs_sf)  # same folds, same rows
    assert wape(obs, pred) < wape(obs_sf, pred_sf) - 0.02
    assert 0.5 < pred.sum() / obs.sum() < 2.0  # no divergence on rows at the offset floor


def test_zero_tree_reproduces_scale_factor_block_totals(world):
    _, _, prep = world
    d = prep.d
    fold = leave_one_year_out(d.dates, 6)[3]
    tr, te = fold.train, fold.test
    k, _ = select_k(d.src, d.tgt, d.dates, d.month_idx, tr)
    fac = fit_factors(d.src, d.tgt, d.month_idx, tr, k)
    sf = (fac.f[d.month_idx[te]] * d.src[te]).sum(axis=-1)
    for rs, names in ((prep.cells, BASE_FEATURES), (prep.block, prep.block.names)):
        model, zero, _ = fit_final(rs, names, GBMConfig("z", lr=1e-12, iters=(5,)), 5, d, k, tr, te)
        # a zero-learning-rate model is exactly the offset...
        assert np.allclose(model, zero, rtol=1e-6)
        # ...and the offset keeps the SA2.2 block totals (smoothing is rescaled; eps is tiny)
        assert np.all(np.abs(zero.sum(axis=0) - sf.sum(axis=0)) <= 0.01 * np.maximum(sf.sum(axis=0), 1.0))
        assert abs(zero.sum() / sf.sum() - 1) < 0.01


def test_smoothed_source_keeps_totals_and_rows_depend_only_on_source(world):
    grid, cube, prep = world
    cells, d = prep.cells, prep.d
    flat = (cells.mi * cells.n_blocks + cells.bi) * 2 + cells.dn
    tot = np.bincount(flat, weights=cells.s_off, minlength=d.src.size)
    assert np.allclose(tot, d.src.reshape(-1))
    # candidate rows: source in the cell or its 3x3; target detections elsewhere are unreachable
    assert cells.y.sum() + cells.unreachable == pytest.approx(cells.target_total)
    zero_src = cells.X[:, BASE_FEATURES.index("src_cnt")] == 0
    n3 = cells.X[:, BASE_FEATURES.index("n3")]
    assert zero_src.any()
    assert np.all((cells.s_off[zero_src] > 0) == (n3[zero_src] > 0))


def test_offset_factors_never_read_the_test_year_or_gap(world):
    _, _, prep = world
    d = prep.d
    fold = leave_one_year_out(d.dates, 6)[2]
    tr = fold.train
    k = 20.0
    f0, ok0 = oof_factors(d, tr, k)
    # corrupt target and source outside `train` (test year and gap): factors of training months cannot change
    d2 = type(d)(d.ym, d.dates, d.month_idx, d.year_idx, d.src.copy(), d.tgt.copy())
    d2.src[~tr] *= 50
    d2.tgt[~tr] *= 50
    f1, ok1 = oof_factors(d2, tr, k)
    assert np.array_equal(ok0, ok1) and not ok0[~tr].any()
    assert np.allclose(f0[ok0], f1[ok1])
    assert np.allclose(fitted_factors(d, tr, k)[tr], fitted_factors(d2, tr, k)[tr])
    # each month's out-of-fold factor equals the factor fitted without that month's year (and gap)
    m = np.flatnonzero(ok0)[0]
    year = d.year_idx[m]
    ym = d.ym
    keep = tr & ((ym < year * 12 - 6) | (ym > year * 12 + 11 + 6))
    assert np.allclose(f0[m], fit_factors(d.src, d.tgt, d.month_idx, keep, k).f[d.month_idx[m]])


def test_predictions_unchanged_when_test_year_target_and_gap_are_corrupted():
    year = 2015
    clean = setup(synth_grid(seed=1))[1]
    dirty = setup(synth_grid(seed=1, poison_year=year))[1]
    a, _ = run_ml_cv(clean, "loyo", SMALL, SMALL, ablations=False, only_years={year})
    b, _ = run_ml_cv(dirty, "loyo", SMALL, SMALL, ablations=False, only_years={year})
    assert {f.method for f in a} == {f.method for f in b} and len(a) == 4  # cell, block, two zero-tree
    for fa, fb in zip(sorted(a, key=lambda f: f.method), sorted(b, key=lambda f: f.method), strict=True):
        assert fa.method == fb.method
        assert not np.allclose(fa.obs, fb.obs)  # the corruption is real for the observed target...
        assert np.allclose(fa.pred, fb.pred)  # ...and invisible to every prediction and to the selection
        for key in fa.intervals:
            assert np.allclose(fa.intervals[key][0], fb.intervals[key][0])
            assert np.allclose(fa.intervals[key][1], fb.intervals[key][1])


def test_rows_dropped_when_source_is_far_from_a_cell():
    # one source cell far from everything else: its cell-month plus 8 neighbours, two day/night rows each
    grid = pd.DataFrame(
        {
            "acq_date": ["2013-03-10"] * 2,
            "satellite": ["snpp", "terra"],
            "daynight": ["D", "D"],
            "cell_id": cell_ids(np.array([-30.45, -45.05]), np.array([-64.55, -60.05]), 0.1),
            "count": [4, 7],
            "frp_sum": [40.0, 70.0],
            "cell_lat": [-30.45, -45.05],
            "cell_lon": [-64.55, -60.05],
        }
    )
    cube = build_cube(monthly_region_table(grid))
    rows = build_cell_rows(
        monthly_cell_table(grid), cube.ym, cube.blocks, ("snpp",), ("terra",), cube.total(("snpp",))
    )
    assert len(rows.y) == 18  # 9 cells x 2 day/night
    assert rows.unreachable == 7.0  # the Terra detection has no S-NPP nearby


def _fold(method, pred, obs, year):
    return FoldOut(
        pair="viirs_to_modis",
        scheme="loyo",
        method=method,
        test_year=year,
        ym=np.arange(len(obs)),
        obs=obs,
        pred=pred,
        src=obs,
    )


def test_bootstrap_is_seeded_and_excludes_zero_only_for_a_real_gap():
    rng = np.random.default_rng(3)
    obs = {y: rng.poisson(50, size=(12, 20)).astype(float) for y in range(2012, 2026)}
    base = {y: _fold("sf", o * (1 + rng.normal(0, 0.2, o.shape)), o, y) for y, o in obs.items()}
    better = {y: _fold("lgb_cell", o * (1 + rng.normal(0, 0.1, o.shape)), o, y) for y, o in obs.items()}
    same = {y: _fold("lgb_cell", f.pred.copy(), f.obs, y) for y, f in base.items()}
    p1, lo1, hi1 = bootstrap_diff(better, base)
    assert (p1, lo1, hi1) == bootstrap_diff(better, base)  # fixed seed
    assert hi1 < 0
    p0, lo0, hi0 = bootstrap_diff(same, base)
    assert p0 == 0 and lo0 <= 0 <= hi0


def test_verdict_lists_failed_conditions_for_an_equal_model():
    rng = np.random.default_rng(4)
    sf, ml = [], []
    for scheme in ("loyo", "rolling"):
        for y in range(2012, 2026):
            o = rng.poisson(50, size=(12, 10)).astype(float)
            p = o * (1 + rng.normal(0, 0.2, o.shape))
            for lst, name in ((sf, "sf"), (ml, "lgb_cell")):
                f = _fold(name, p.copy(), o, y)
                f.scheme = scheme
                lst.append(f)
    v = evaluate_criterion(sf, ml, "viirs_to_modis", "lgb_cell")
    assert v.text == "no supera al factor"
    failed = [c.name for c in v.conditions if not c.passed]
    assert any(c.startswith("1.") for c in failed) and any(c.startswith("7.") for c in failed)


def test_report_section_renders_with_verdicts_and_ablations():
    from firecal.stages.harmonize.ml import MLResult
    from firecal.stages.harmonize.ml_report import ml_section

    grid = synth_grid(seed=2)
    cube = build_cube(monthly_region_table(grid))
    long = monthly_cell_table(grid)
    folds, diags, meta, sf = {}, [], {}, []
    for pair in ("viirs_to_modis", "modis_to_viirs"):
        prep = prepare(cube, long, pair)
        for scheme in ("loyo", "rolling"):
            f, dg = run_ml_cv(prep, scheme, SMALL, SMALL, ablations=scheme == "loyo", with_intervals=True)
            folds[pair, scheme] = f
            diags += dg
            sf += [x for x in run_cv(cube, pair, scheme, with_conformal=scheme == "loyo") if x.method == "sf"]
        meta[pair] = {
            "cell_rows": len(prep.cells.y),
            "block_rows": len(prep.block.y),
            "unreachable_share": 0.01,
        }
    text = "\n".join(ml_section(MLResult(folds, diags, meta, SMALL, SMALL, 1.0, 100.0), sf))
    assert "SA2.4 y SA2.7 vs. baseline" in text
    assert (
        text.count("supera al factor") >= 4
    )  # one verdict line per direction and candidate (and the summary)
    assert "Importancia de variables" in text and "LightGBM celda + proporción Terra/Aqua" in text
    assert "Cobertura" in text


def test_inverse_direction_rows_at_the_offset_floor_stay_bounded(monkeypatch):
    """Regression: rows with no MODIS (offset at eps) but VIIRS detections once gave raw ~ +45 (SA2.7)."""
    import firecal.stages.harmonize.ml as ml

    grid = synth_grid(seed=3, thin=0.15, ratio_by_frp=False)
    cube, prep = setup(grid, "modis_to_viirs")
    cfg = GBMConfig("d", num_leaves=15, min_data=20, lr=0.1, l2=1.0, iters=(100,))
    d, rs = prep.d, prep.cells
    assert (rs.s_off == 0).mean() > 0.1  # many rows at the floor
    assert rs.y[rs.s_off == 0].sum() > 0  # and with target detections

    folds, _ = run_ml_cv(
        prep, "loyo", (cfg,), (cfg,), ablations=False, with_intervals=False, only_years={2015}
    )
    by = {f.method: f for f in folds}
    ratio = by["lgb_cell"].pred.sum() / by["lgb_cell"].obs.sum()
    assert 0.5 <= ratio <= 2.0
    assert wape(by["lgb_cell"].obs, by["lgb_cell"].pred) <= 1.5 * wape(
        by["zero_cell"].obs, by["zero_cell"].pred
    )

    # rows that are not at the floor stay close to the zero-tree (offset-only) prediction
    fold = [f for f in leave_one_year_out(d.dates, 6) if f.test_year == 2015][0]
    tr, te = fold.train, fold.test
    k, _ = select_k(d.src, d.tgt, d.dates, d.month_idx, tr)
    f_tr, ok = oof_factors(d, tr, k)
    itr, ite = np.flatnonzero((tr & ok)[rs.mi]), np.flatnonzero(te[rs.mi])
    off_te = ml.offsets(rs, ite, fitted_factors(d, tr, k))
    pred, _ = ml.fit_predict(
        rs, rs.cols(BASE_FEATURES), cfg, itr, ml.offsets(rs, itr, f_tr), ite, off_te, (100,)
    )
    nf = rs.s_off[ite] > 0
    assert abs(pred[100][nf].sum() / np.exp(off_te)[nf].sum() - 1) < 0.10

    # MODIS blind at night: without the leaf cap the same code diverges and the guard raises
    _, prep2 = setup(synth_grid(seed=3, ratio_by_frp=False, modis_night=0.0), "modis_to_viirs")
    capped, _ = run_ml_cv(
        prep2, "loyo", (cfg,), (cfg,), ablations=False, with_intervals=False, only_years={2015}
    )
    cell = next(f for f in capped if f.method == "lgb_cell")
    assert 0.5 <= cell.pred.sum() / cell.obs.sum() <= 2.0
    real = ml.lgb_params
    monkeypatch.setattr(ml, "lgb_params", lambda *a, **kw: real(*a, **kw) | {"max_delta_step": 0.0})
    with pytest.raises(FloatingPointError):
        run_ml_cv(prep2, "loyo", (cfg,), (cfg,), ablations=False, with_intervals=False, only_years={2015})
