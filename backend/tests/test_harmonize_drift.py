import numpy as np
import pandas as pd

from firecal.stages.harmonize.backward import (
    TEST_YEARS,
    TRAIN_FIRST,
    TRAIN_LAST,
    backward_run,
    gate,
    paired_bootstrap,
    run_pair,
)
from firecal.stages.harmonize.drift import (
    completeness_table,
    drift_epochs,
    pair_windows,
    placebo_table,
    train_mask,
)
from firecal.stages.harmonize.regions import build_cube, ym_of


def hours_table(day_hours: dict[int, float], sat="terra") -> pd.DataFrame:
    return pd.DataFrame(
        [{"year": y, "satellite": sat, "daynight": "D", "hour": h} for y, h in day_hours.items()]
    )


def test_drift_epoch_ignores_2000_outlier_and_starts_at_first_year_over_threshold():
    hrs = {y: 14.0 for y in range(2003, 2021)}
    hrs[2000] = 15.5  # 90 minutes off but before 2021: must neither start the epoch nor enter the reference
    hrs[2021] = 14.0 - 10 / 60  # 10 min: below the threshold
    hrs[2022] = 14.0 - 14.9 / 60  # just under 15 min
    hrs[2023] = 14.0 - 16 / 60  # first year over
    hrs[2024] = 14.0 - 5 / 60  # back near the reference: still in the epoch
    hrs[2025] = 14.0 - 40 / 60
    e = drift_epochs(hours_table(hrs), sats=("terra",))["terra"]
    assert e.reference_hour == 14.0  # 2000 is out of the 2003-2020 reference
    assert e.start == 2023
    assert round(e.offset_min[2000]) == 90  # reported, never tested


def test_drift_epoch_none_when_nothing_exceeds_threshold():
    hrs = {y: 14.0 for y in range(2000, 2026)}
    hrs[2025] = 14.0 + 15 / 60  # exactly 15 min is not "more than 15"
    assert drift_epochs(hours_table(hrs), sats=("terra",))["terra"].start is None


def test_pair_windows_union_and_terra_only():
    hrs = {y: 14.0 for y in range(2003, 2026)}
    hrs.update({2023: 13.5, 2024: 13.5, 2025: 13.5})
    aqua = {y: 18.0 for y in range(2003, 2026)}
    aqua.update({2024: 18.6, 2025: 18.6})
    h = pd.concat([hours_table(hrs), hours_table(aqua, "aqua")])
    w = pair_windows(drift_epochs(h))
    assert w["viirs_to_modis"]["main"] == (2023, 2024, 2025)
    assert w["terra_to_viirs"]["main"] == (2023, 2024, 2025)
    assert w["viirs_to_modis"]["sensitivity"] == (2022, 2023, 2024, 2025)


def synth_cube(years=range(2012, 2026)):
    rows = []
    for y in years:
        for m in range(1, 13):
            if (y, m) == (2012, 1):
                continue
            for b in (10, 11, 12):
                for dn in ("D", "N"):
                    base = 30 + 3 * m + b + (y % 4)
                    rows.append((b, ym_of(y, m), dn, "snpp", base))
                    rows.append((b, ym_of(y, m), dn, "terra", 0.1 * base))
                    rows.append((b, ym_of(y, m), dn, "aqua", 0.2 * base))
    return build_cube(pd.DataFrame(rows, columns=["block", "ym", "daynight", "satellite", "count"]))


def test_backward_no_test_year_in_training_and_drift_years_dropped():
    cube = synth_cube()
    run = backward_run(cube, "viirs_to_modis")
    ty = run.train_ym // 12
    assert ty.min() >= 2016
    assert not set(TEST_YEARS) & set(ty.tolist())
    assert run.train_ym.min() == TRAIN_FIRST and run.train_ym.max() == TRAIN_LAST
    assert [f.test_year for f in run.folds] == list(TEST_YEARS)
    for f in run.folds:
        assert not set(f.ym.tolist()) & set(run.train_ym.tolist())
    run2 = backward_run(cube, "viirs_to_modis", drop_years=(2023, 2024, 2025))
    assert not {2023, 2024, 2025} & set((run2.train_ym // 12).tolist())
    assert len(run2.train_ym) == len(run.train_ym) - 36


def test_train_mask_drops_years():
    ym = np.arange(ym_of(2015, 1), ym_of(2026, 1))
    m = train_mask(ym // 12, ym, TRAIN_FIRST, TRAIN_LAST, (2024, 2025))
    assert set((ym[m] // 12).tolist()) == set(range(2016, 2024))


def test_run_pair_exact_factor_gives_no_gain_and_bootstrap_is_reproducible():
    cube = synth_cube()
    r = run_pair(cube, "viirs_to_modis", (2023, 2024, 2025))
    assert r["wape_with"] < 1e-9 and r["wape_without"] < 1e-9
    again = paired_bootstrap(r["obs_by"], r["pred_with_by"], r["pred_without_by"])
    assert again == r["boot"]
    assert r["verdict"] == "report only"  # nothing strictly better: the gate cannot be met


def test_gate_rule():
    base = {
        "wape_diff": -0.01,
        "wape_lo": -0.02,
        "wape_hi": -0.005,
        "bias_diff": 0.0,
        "bias_lo": -0.1,
        "bias_hi": 0.1,
    }
    assert gate(base)[0] is True
    assert gate({**base, "bias_diff": 0.001})[0] is False  # one metric worse
    assert gate({**base, "wape_hi": 0.01})[0] is False  # no interval below zero


def test_placebo_excludes_overlapping_windows():
    cube = synth_cube()
    tab, base = placebo_table(cube, (2023, 2024, 2025))
    assert tab.iloc[0]["kind"] == "drift"
    for w in tab[tab["kind"] == "placebo"]["window"]:
        a, b = (int(x) for x in w.split("-"))
        assert b < 2023 and b - a == 2
    assert base["total"] > 0


def test_completeness_flags_below_90_percent_of_median():
    rows = []
    for y in range(2003, 2026):
        for m in range(1, 13):
            rows.append(("aqua", ym_of(y, m), 30))
    d = pd.DataFrame(rows, columns=["satellite", "ym", "days"])
    d.loc[(d["ym"] == ym_of(2020, 5)), "days"] = 26  # 86.7 %
    d.loc[(d["ym"] == ym_of(2021, 5)), "days"] = 27  # exactly 90 %: not flagged
    t = completeness_table(d)
    flagged = t[t["flagged"]]
    assert list(flagged["ym"]) == [ym_of(2020, 5)]
