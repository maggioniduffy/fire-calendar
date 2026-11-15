"""SA2.10: NOAA-21 in the cube, routes (chain vs direct), P5 decision, calibration extension, frozen
artifact."""

import json

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from typer.testing import CliRunner

from firecal.stages.harmonize import continuity as C
from firecal.stages.harmonize.evaluate import BASELINE_PAIRS, PAIRS, pair_data
from firecal.stages.harmonize.regions import (
    SATELLITES,
    Cube,
    build_cube,
    build_monthly_region_table,
    restrict_blocks,
    ym_of,
)
from firecal.stages.harmonize.route import (
    ROUTE_PAIR,
    fit_route,
    loyo_predictions,
    route_inner_residuals,
)
from firecal.stages.harmonize.series import (
    FROZEN_DIR,
    CalibrationExtensionError,
    PairCal,
    _pair_to_dict,
    calibration_from_dict,
    calibration_to_dict,
    extend_calibration,
    fit_calibration,
    load_frozen,
)
from firecal.stages.harmonize.series_cli import series_app

BLOCKS = (10, 11, 12)
LAST = ym_of(2026, 7)


def synth_table(last: int = LAST, noaa20_scale: float = 0.5) -> pd.DataFrame:
    """Noise-free counts with exact ratios: S-NPP = base, NOAA-20 = base/2, Terra + Aqua = base/2, NOAA-21
    = base/4."""
    rows = []
    starts = {
        "terra": ym_of(2012, 1),
        "aqua": ym_of(2012, 1),
        "snpp": ym_of(2012, 1),
        "noaa20": ym_of(2018, 4),
        "noaa21": ym_of(2023, 3),
    }
    mult = {"terra": 0.25, "aqua": 0.25, "snpp": 1.0, "noaa20": noaa20_scale, "noaa21": 0.25}
    for sat, first in starts.items():
        for ym in range(first, last + 1):
            for bi, b in enumerate(BLOCKS):
                for dn in range(2):
                    base = (
                        200 * (1 + 0.5 * np.sin(2 * np.pi * (ym % 12) / 12)) * (1 + 0.2 * bi) * (1 + 0.3 * dn)
                    )
                    rows.append((b, ym, "DN"[dn], sat, base * mult[sat]))
    return pd.DataFrame(rows, columns=["block", "ym", "daynight", "satellite", "count"])


def synth_cube(**kw) -> Cube:
    return build_cube(synth_table(**kw))


# --------------------------------------------------------------------------- cube and NOAA-21


def test_noaa21_is_in_the_cube_and_pairs():
    assert "noaa21" in SATELLITES
    cube = synth_cube()
    assert cube.valid["noaa21"].sum() == LAST - ym_of(2023, 3) + 1
    assert not cube.valid["noaa21"][cube.ym < ym_of(2023, 3)].any()
    assert set(PAIRS) >= {"noaa21_to_snpp", "noaa21_to_noaa20", "noaa20_to_modis"}
    d = pair_data(cube, PAIRS["noaa21_to_snpp"], LAST)
    assert d.ym[0] == ym_of(2023, 3)
    assert np.allclose(d.tgt.sum() / d.src.sum(), 4.0)


def test_cube_exclusions_invalidate_months_but_keep_counts():
    cube = build_cube(synth_table(), {"snpp": [ym_of(2026, 7)], "terra": [ym_of(2026, 5)]})
    assert not cube.valid["snpp"][cube.ym == ym_of(2026, 7)][0]
    assert not cube.valid["terra"][cube.ym == ym_of(2026, 5)][0]
    assert cube.data["snpp"][cube.ym == ym_of(2026, 7)].sum() > 0
    assert cube.valid["snpp"][cube.ym == ym_of(2026, 6)][0]


def _write_grid(root, year, rows):
    df = pd.DataFrame(rows)
    dest = root / f"year={year}" / "part-0.parquet"
    dest.parent.mkdir(parents=True)
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), dest)


def _grid_row(date, sat, lat, lon, n, level=None):
    r = {"acq_date": date, "satellite": sat, "daynight": "D", "cell_lat": lat, "cell_lon": lon, "count": n}
    if level is not None:
        r["level"] = level
    return r


def test_existing_pairs_are_identical_with_noaa21_2026_and_nrt_rows(tmp_path):
    old = [
        _grid_row("2019-03-05", s, -31.45, -64.25, n)
        for s, n in (("terra", 3), ("aqua", 4), ("snpp", 20), ("noaa20", 18))
    ] + [_grid_row("2019-04-05", s, -31.45, -64.25, n) for s, n in (("terra", 1), ("aqua", 2), ("snpp", 9))]
    plain = tmp_path / "plain"
    _write_grid(plain, 2019, old)
    extra = tmp_path / "extra"
    _write_grid(extra, 2019, [{**r, "level": "country-sp"} for r in old])
    _write_grid(
        extra,
        2026,
        [
            _grid_row("2026-02-02", "noaa21", -31.45, -64.25, 7, "api-sp"),
            _grid_row("2026-02-02", "snpp", -31.45, -64.25, 7, "api-sp"),
            _grid_row("2026-09-02", "snpp", -31.45, -64.25, 99, "nrt"),
        ],
    )
    t_plain = build_monthly_region_table(plain)
    t_extra = build_monthly_region_table(extra)  # default: up to 2025-12, no NRT
    pd.testing.assert_frame_equal(t_plain.reset_index(drop=True), t_extra.reset_index(drop=True))
    t_all = build_monthly_region_table(extra, through=None)
    assert set(t_all["satellite"]) == {"terra", "aqua", "snpp", "noaa20", "noaa21"}
    assert t_all["count"].sum() == t_plain["count"].sum() + 14  # NRT 99 never enters
    c0, c1 = build_cube(t_plain), build_cube(t_all)
    end = int(t_plain["ym"].max())  # the pairs cap their months at OVERLAP_END (2025-12) on the real grid
    for pair in BASELINE_PAIRS:
        a, b = pair_data(c0, PAIRS[pair], end), pair_data(c1, PAIRS[pair], end)
        np.testing.assert_array_equal(a.ym, b.ym)
        np.testing.assert_array_equal(a.src, b.src)
        np.testing.assert_array_equal(a.tgt, b.tgt)


def test_restrict_blocks_keeps_order_and_zero_fills():
    cube = synth_cube()
    sub = restrict_blocks(cube, np.array([10, 12, 99]))
    assert list(sub.blocks) == [10, 12, 99]
    np.testing.assert_array_equal(sub.data["snpp"][:, 0], cube.data["snpp"][:, 0])
    np.testing.assert_array_equal(sub.data["snpp"][:, 1], cube.data["snpp"][:, 2])
    assert sub.data["snpp"][:, 2].sum() == 0


def test_completeness_sets_gate_only_2026_and_drop_nrt():
    comp = pd.DataFrame(
        {
            "satellite": ["terra", "terra", "snpp", "aqua", "terra"],
            "month": ["2022-10", "2026-05", "2026-07", "2026-09", "2026-02"],
            "ym": [ym_of(2022, 10), ym_of(2026, 5), ym_of(2026, 7), ym_of(2026, 9), ym_of(2026, 2)],
            "level": ["country-sp", "api-sp", "api-sp", "nrt", "api-sp"],
            "status": ["partial", "partial", "partial", "complete", "complete"],
            "days_with_detections": [18, 25, 25, 30, 28],
            "threshold_days": [27.9, 26.1, 27.9, 27.0, 25.2],
        }
    )
    exclude, flagged, out = C.completeness_sets(comp)
    assert exclude["terra"] == {ym_of(2026, 5)} and exclude["snpp"] == {ym_of(2026, 7)}
    assert exclude["aqua"] == {ym_of(2026, 9)}  # NRT, though complete
    assert flagged == {"terra": {ym_of(2022, 10)}}  # diagnostic only, not excluded
    assert len(out) == 3


# --------------------------------------------------------------------------- routes


def test_chain_factor_is_the_product_and_matches_direct_on_exact_ratios():
    cube = restrict_blocks(synth_cube(), np.array(BLOCKS))
    end = ym_of(2025, 12)
    chain, direct = fit_route(cube, "chain", end), fit_route(cube, "direct", end)
    np.testing.assert_allclose(chain.f, 1.0)  # NOAA-20 -> S-NPP = 2, S-NPP -> MODIS = 0.5
    np.testing.assert_allclose(chain.f_nat, 1.0)
    np.testing.assert_allclose(direct.f, 1.0)
    assert set(chain.k) == {"noaa20_to_snpp", "viirs_to_modis"} and set(direct.k) == {ROUTE_PAIR}


def test_loyo_prediction_never_sees_its_test_year_or_gap():
    cube = restrict_blocks(synth_cube(), np.array(BLOCKS))
    end = ym_of(2025, 12)
    base = {y: p for y, _, p in loyo_predictions(cube, "chain", end)}
    poisoned = cube.data["terra"].copy()
    sel = (cube.ym >= ym_of(2021, 7)) & (cube.ym <= ym_of(2022, 6))  # inside the window of test year 2022
    poisoned[sel] *= 50
    alt = Cube(cube.ym, cube.blocks, {**cube.data, "terra": poisoned}, cube.valid)
    other = {y: p for y, _, p in loyo_predictions(alt, "chain", end)}
    # Test year 2022: its window (2021-07..2023-06) covers the poisoned months, so its predictions do not
    # move.
    np.testing.assert_allclose(base[2022], other[2022])
    # Test year 2025 trains on the poisoned months, so its predictions do move.
    assert not np.allclose(base[2025], other[2025])


def test_inner_residuals_exist_for_both_routes():
    cube = restrict_blocks(synth_cube(), np.array(BLOCKS))
    for route in ("chain", "direct"):
        res = route_inner_residuals(cube, route, ym_of(2025, 12))
        assert len(res.pred_month) > 0 and res.used.any()
        np.testing.assert_allclose(res.pred_month, res.obs_month)  # exact ratios


# --------------------------------------------------------------------------- P5 decision


def _cell(cutoff, year, route, scale_by_block, n_blocks=6):
    rng = np.random.default_rng(cutoff * 10 + year)
    obs = rng.integers(50, 100, (12, n_blocks)).astype(float)
    return C.Cell(cutoff, year, route, np.arange(12) + ym_of(year, 1), obs, obs * scale_by_block, obs.copy())


def _forward(chain_scale, direct_scale):
    cells = []
    for c in C.CUTOFFS:
        for y in range(c + 1, 2026):
            cells.append(_cell(c, y, "chain", chain_scale))
            cells.append(_cell(c, y, "direct", direct_scale))
    return C.Forward(cells, {}, {})


def test_decide_chain_when_lower_wape_and_bias_within_half_point():
    d = C.decide(_forward(np.full(6, 1.02), np.full(6, 1.05)))
    assert d.route == "chain"
    assert d.chain["wape"] < d.direct["wape"]


def test_decide_direct_when_chain_wape_lower_but_bias_worse_by_more_than_half_point():
    direct = np.array([1.06, 0.94, 1.06, 0.94, 1.06, 0.94])  # WAPE 6 %, bias about 0
    d = C.decide(_forward(np.full(6, 1.04), direct))
    assert d.chain["wape"] < d.direct["wape"]
    assert abs(d.chain["bias"]) - abs(d.direct["bias"]) > 0.005
    assert d.route == "direct"


def test_decide_tie_goes_to_direct():
    d = C.decide(_forward(np.full(6, 1.03), np.full(6, 1.03)))
    assert d.route == "direct"


def test_not_robust_note_when_2023_and_2024_disagree_with_pooled():
    cells = []
    pooled_chain_better = {2021: 0.30, 2022: 0.30, 2023: 1.0, 2024: 1.0}  # chain scale error by cut-off
    for c in C.CUTOFFS:
        for y in range(c + 1, 2026):
            cells.append(
                _cell(c, y, "chain", np.full(6, 1 + 0.01 * pooled_chain_better[c] * (1 if c > 2022 else 0.1)))
            )
            cells.append(_cell(c, y, "direct", np.full(6, 1.0 + (0.03 if c <= 2022 else 0.0))))
    d = C.decide(C.Forward(cells, {}, {}))
    assert not d.robust and "not robust" in d.robust_note


def test_paired_bootstrap_is_seeded_and_zero_for_identical_predictions():
    rng = np.random.default_rng(1)
    obs = rng.integers(10, 100, (10, 20)).astype(float)
    a, b = obs * 1.05, obs * 0.9
    r1, r2 = C.paired_bootstrap(obs, a, b, n_boot=200), C.paired_bootstrap(obs, a, b, n_boot=200)
    assert r1 == r2
    assert r1["wape_diff"] < 0 and r1["wape_hi"] < 0  # 5 % error beats 10 %
    same = C.paired_bootstrap(obs, a, a, n_boot=50)
    assert same["wape_diff"] == 0 and same["wape_lo"] == 0 == same["wape_hi"]
    assert C.SEED == 20261114 and C.N_BOOT == 1000


def test_coverage_label_follows_the_75_85_range():
    assert C.coverage_label(0.80) == "within 75-85 %"
    assert "unverified" in C.coverage_label(0.70)
    assert "unverified" in C.coverage_label(0.90)


def test_forward_holdout_trains_only_up_to_the_cutoff():
    cube = restrict_blocks(synth_cube(last=ym_of(2026, 4)), np.array(BLOCKS))
    fw = C.run_forward(cube, cutoffs=(2022, 2023))
    years = {(c.cutoff, c.test_year) for c in fw.cells}
    assert years == {
        (2022, 2023),
        (2022, 2024),
        (2022, 2025),
        (2022, 2026),
        (2023, 2024),
        (2023, 2025),
        (2023, 2026),
    }
    p26 = [c for c in fw.cells if c.test_year == 2026]
    assert all(len(c.ym) == 4 for c in p26)  # the months available in 2026, never padded
    assert fw.train_months[2022][ROUTE_PAIR] == ym_of(2022, 12) - ym_of(2018, 5) + 1
    for c in fw.cells:
        np.testing.assert_allclose(c.pred, c.obs)  # exact ratios: factors recover them out of sample


# --------------------------------------------------------------------------- calibration extension


def _base_cal(cube):
    return fit_calibration(cube, "sf-test.1", end=ym_of(2025, 12))


def test_extend_keeps_base_pairs_and_adds_route_and_noaa21(tmp_path):
    cube = restrict_blocks(synth_cube(), np.array(BLOCKS))
    base = _base_cal(cube)
    base_dicts = {n: json.dumps(_pair_to_dict(n, p)) for n, p in base.pairs.items()}
    for route in ("direct", "chain"):
        ext = extend_calibration(base, cube, "sf-test.2", route)
        assert {n: json.dumps(_pair_to_dict(n, ext.pairs[n])) for n in base.pairs} == base_dicts
        assert {"noaa21_to_snpp", "noaa21_to_noaa20", ROUTE_PAIR} <= set(ext.pairs)
        pc = ext.pairs[ROUTE_PAIR]
        assert pc.route == route and pc.end == "2025-12" and pc.start == "2018-05"
        np.testing.assert_allclose(pc.f, 1.0, atol=1e-7)
        assert ext.pairs["noaa21_to_snpp"].end == "2026-07" and ext.fitted_end == "2026-07"
        np.testing.assert_array_equal(ext.blocks, base.blocks)
        # JSON round trip (the chain's k is nan)
        back = calibration_from_dict(json.loads(json.dumps(calibration_to_dict(ext), indent=1)))
        assert back.pairs[ROUTE_PAIR].route == route
        assert back.pairs[ROUTE_PAIR].legs == (
            ("noaa20_to_snpp", "viirs_to_modis") if route == "chain" else ()
        )
        assert json.dumps(calibration_to_dict(back)) == json.dumps(calibration_to_dict(ext))
    chain = extend_calibration(base, cube, "sf-test.2", "chain").pairs[ROUTE_PAIR]
    assert np.isnan(chain.k)


def test_older_pairs_serialize_without_route_fields():
    cube = restrict_blocks(synth_cube(), np.array(BLOCKS))
    base = _base_cal(cube)
    d = calibration_to_dict(base)
    assert all("route" not in p and "legs" not in p for p in d["pairs"].values())
    assert isinstance(base.pairs["viirs_to_modis"], PairCal) and base.pairs["viirs_to_modis"].route is None


def test_extend_refuses_a_cube_that_does_not_reproduce_the_base():
    cube = restrict_blocks(synth_cube(), np.array(BLOCKS))
    base = _base_cal(cube)
    changed = restrict_blocks(synth_cube(noaa20_scale=0.4), np.array(BLOCKS))  # NOAA-20 counts changed
    bad = Cube(
        changed.ym, changed.blocks, {**changed.data, "snpp": changed.data["snpp"] * 1.1}, changed.valid
    )
    with pytest.raises(CalibrationExtensionError):
        extend_calibration(base, bad, "sf-test.2", "direct")
    with pytest.raises(CalibrationExtensionError):
        extend_calibration(base, cube, "sf-test.1", "direct")


def test_frozen_check_scores_three_legs_on_2026_complete_months():
    cube = restrict_blocks(
        build_cube(synth_table(), {"snpp": [LAST], "terra": [ym_of(2026, 5), ym_of(2026, 6), LAST]}),
        np.array(BLOCKS),
    )
    base = _base_cal(cube)
    ext = extend_calibration(base, cube, "sf-test.2", "direct")
    fw = C.run_forward(cube, cutoffs=(2023,))
    p9 = C.frozen_check(cube, base, ext, fw)
    legs = set(p9["leg"])
    assert len(legs) == 3 and any("published route: direct" in x for x in legs)
    route26 = p9[p9["leg"].str.startswith("NOAA-20 -> MODIS") & p9["scope"].str.startswith("2026")].iloc[0]
    assert "(4 months)" in route26["scope"]  # Terra partial in 2026-05..07
    s26 = p9[p9["leg"].str.startswith("NOAA-20 -> S-NPP") & p9["scope"].str.startswith("2026")].iloc[0]
    assert "(6 months)" in s26["scope"]  # S-NPP partial in 2026-07
    assert route26["wape_by"] == pytest.approx(0.0, abs=1e-6)  # exact ratios
    assert (p9["scope"] == "2022-2025 forward holdouts pooled").sum() == 1


# --------------------------------------------------------------------------- frozen files and CLI


def test_frozen_sf_2026_11_1_serializes_byte_for_byte():
    cal = load_frozen("sf-2026.11.1")
    data = json.dumps(calibration_to_dict(cal), indent=1).encode("utf-8")
    assert data == (FROZEN_DIR / "sf-2026.11.1.json").read_bytes()


def test_series_extend_refuses_an_existing_version():
    r = CliRunner().invoke(series_app, ["extend", "--from", "sf-2026.11.1", "--to", "sf-2026.11.1"])
    assert r.exit_code != 0 and "already exists" in r.output


@pytest.mark.slow
def test_sf_2026_11_2_keeps_the_sf_2026_11_1_pairs_byte_for_byte():
    base, ext = load_frozen("sf-2026.11.1"), load_frozen("sf-2026.11.2")
    for name, pc in base.pairs.items():
        assert json.dumps(_pair_to_dict(name, ext.pairs[name]), indent=1) == json.dumps(
            _pair_to_dict(name, pc), indent=1
        )
    assert set(ext.pairs) - set(base.pairs) == {"noaa21_to_snpp", "noaa21_to_noaa20", ROUTE_PAIR}
    np.testing.assert_array_equal(ext.blocks, base.blocks)


@pytest.mark.slow
def test_refit_of_sf_2026_11_1_on_the_current_grid_reproduces_the_frozen_file():
    base = load_frozen("sf-2026.11.1")
    cube = build_cube(build_monthly_region_table())
    cal = fit_calibration(cube, "sf-2026.11.1", created=pd.Timestamp(base.created).date())
    assert (
        json.dumps(calibration_to_dict(cal), indent=1).encode()
        == (FROZEN_DIR / "sf-2026.11.1.json").read_bytes()
    )
