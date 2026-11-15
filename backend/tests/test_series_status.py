"""SA2.10 series rules: NOAA-21 column, completeness gating, P8, post-MODIS route, status columns,
partial year, stability of earlier rows, manifest source and notes, calendar exposure."""

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from firecal.stages.calendar.service import CalendarRequest, calendar_payload, meta
from firecal.stages.calendar.store import SeriesStore
from firecal.stages.harmonize.regions import ym_of
from firecal.stages.harmonize.series import (
    Calibration,
    PairCal,
    build_series,
    freeze_calibration,
    manifest_notes,
    month_levels,
    publish,
    sensor_months,
    wide_counts,
)
from tests.test_harmonize_series import CELL, LAT, LON, _conf, const_cal  # noqa: F401

F_N21, F_N20M = 0.9, 0.05


def cal_with(*extra: tuple[str, float]) -> Calibration:
    cal = const_cal()
    for name, f in extra:
        cal.pairs[name] = PairCal(
            name, 20.0, False, np.full((12, 1, 2), f), np.full((12, 2), f), "2023-03", "2025-12", 100,
            _conf(), _conf(),
        )  # fmt: skip
    return cal


def grid(ym_counts: dict[tuple[int, int], dict[str, int]], levels: dict | None = None) -> pd.DataFrame:
    """One cell, one day per month; `levels` maps (satellite, year, month) -> level (default country-sp)."""
    rows = []
    for (y, m), sats in ym_counts.items():
        for sat, n in sats.items():
            rows.append(
                {
                    "acq_date": pd.Timestamp(y, m, 10).date(), "satellite": sat, "daynight": "D",
                    "cell_id": CELL, "cell_lat": LAT, "cell_lon": LON, "count": n,
                    "level": (levels or {}).get((sat, y, m), "country-sp"),
                }
            )  # fmt: skip
    return pd.DataFrame(rows)


def comp(rows: dict[tuple[str, int, int], str]) -> pd.DataFrame:
    return pd.DataFrame([{"satellite": s, "ym": ym_of(y, m), "status": st} for (s, y, m), st in rows.items()])


def run(g, cal=None, completeness=None):
    from firecal.stages.harmonize.series import GATE_FROM_YM

    return build_series(
        wide_counts(g),
        sensor_months(g, completeness=completeness),
        cal or const_cal(),
        levels=month_levels(g),
        gate_from=GATE_FROM_YM if completeness is not None else None,
    )


def row(out, y, m):
    s = out.series
    return s[(s["year"] == y) & (s["month"] == m)].iloc[0]


def test_noaa21_is_its_own_column_never_summed():
    g = grid({(2025, 6): {"noaa20": 7, "noaa21": 5, "snpp": 3, "terra": 1, "aqua": 2}})
    w = wide_counts(g).iloc[0]
    assert (w["noaa20"], w["noaa21"], w["snpp"], w["terra"], w["aqua"]) == (7, 5, 3, 1, 2)


def test_sensor_months_gate_only_from_2026_and_only_complete():
    g = grid(
        {
            (2025, 12): {"terra": 1, "aqua": 1},
            (2026, 1): {"terra": 1, "aqua": 1},
            (2026, 2): {"terra": 1, "aqua": 1},
            (2026, 3): {"terra": 1, "aqua": 1},
        }
    )
    c = comp(
        {
            ("terra", 2026, 1): "complete", ("aqua", 2026, 1): "complete",
            ("terra", 2026, 2): "partial", ("aqua", 2026, 2): "complete",
            ("terra", 2026, 3): "in_progress", ("aqua", 2026, 3): "in_progress",
        }
    )  # fmt: skip
    m = sensor_months(g, completeness=c)
    assert m["terra"].tolist() == [ym_of(2025, 12), ym_of(2026, 1)]  # 2025 not gated, not in the table
    assert m["aqua"].tolist() == [ym_of(2025, 12), ym_of(2026, 1), ym_of(2026, 2)]
    assert sensor_months(g)["terra"].tolist() == sorted(
        ym_of(2025 + (i > 0), 12 if i == 0 else i) for i in range(4)
    )


def test_p8_partial_terra_makes_modis_undefined_and_estimated_from_viirs():
    g = grid({(2026, 5): {"terra": 3, "aqua": 40, "snpp": 100, "noaa20": 90}})
    c = comp(
        {(s, 2026, 5): "partial" if s == "terra" else "complete" for s in ("terra", "aqua", "snpp", "noaa20")}
    )
    r = row(run(g, completeness=c), 2026, 5)
    assert np.isnan(r["modis_reported"])  # Aqua alone is not reported as MODIS
    assert r["modis_eq"] == pytest.approx(0.5 * 100) and r["modis_eq_estimated"]
    assert r["modis_sats"] == "none" and not r["modis_drift"]
    # without the gate (2000-2025 behaviour) Aqua alone still counts
    r0 = row(run(grid({(2026, 5): {"aqua": 40, "snpp": 100}})), 2026, 5)
    assert r0["modis_reported"] == 40 and not r0["modis_eq_estimated"]


def test_history_unchanged_by_the_new_rules():
    g = grid({(2015, 6): {"aqua": 8, "snpp": 40, "noaa20": 5, "noaa21": 4}})  # Terra absent
    r = row(run(g, cal_with(("noaa21_to_snpp", F_N21), ("noaa20_to_modis", F_N20M))), 2015, 6)
    assert r["modis_reported"] == 8 and r["viirs_reported"] == 40 and r["viirs_source"] == "snpp"


def test_noaa21_whole_month_fallback_only_when_noaa20_missing_and_pair_present():
    g = grid({(2026, 7): {"noaa20": 50, "noaa21": 40}, (2026, 8): {"noaa21": 40}})
    c = comp({(s, 2026, m): "complete" for s in ("noaa20", "noaa21") for m in (7,)})
    c = pd.concat([c, comp({("noaa21", 2026, 8): "complete", ("noaa20", 2026, 8): "partial"})])
    cal = cal_with(("noaa21_to_snpp", F_N21))
    out = run(g, cal, c)
    jul, aug = row(out, 2026, 7), row(out, 2026, 8)
    assert jul["viirs_source"] == "noaa20_transferred" and jul["viirs_reported"] == pytest.approx(1.1 * 50)
    assert aug["viirs_source"] == "noaa21_transferred" and aug["viirs_reported"] == pytest.approx(F_N21 * 40)
    assert ("viirs_eq", "noaa21_to_snpp") in set(
        zip(out.band_month["target"], out.band_month["route"], strict=True)
    )
    # a calibration without the pair does not use NOAA-21 at all
    assert (run(g, const_cal(), c).series["month"] == 7).all()


def test_post_modis_route_with_its_band_and_snpp_precedence():
    g = grid({(2026, 7): {"snpp": 60, "noaa20": 100}, (2026, 9): {"noaa20": 100}})
    c = comp({(s, 2026, m): "complete" for s in ("snpp", "noaa20") for m in (7, 9)})
    cal = cal_with(("noaa20_to_modis", F_N20M))
    out = run(g, cal, c)
    jul, sep = row(out, 2026, 7), row(out, 2026, 9)
    assert jul["modis_eq"] == pytest.approx(0.5 * 60)  # S-NPP exists: viirs_to_modis kept
    assert (
        sep["modis_eq"] == pytest.approx(F_N20M * 100) and sep["modis_eq_estimated"]
    )  # direct NOAA-20 count
    bm = out.band_month
    routes = {(int(r.month), r.target, r.route) for r in bm.itertuples()}
    assert (7, "modis_eq", "viirs_to_modis") in routes and (9, "modis_eq", "noaa20_to_modis") in routes
    assert {r for r in out.band_year["route"]} >= {"noaa20_to_modis", "viirs_to_modis"}
    # no pair (calibration .1): today's chain, no band for that modis_eq
    old = run(g, const_cal(), c)
    assert row(old, 2026, 9)["modis_eq"] == pytest.approx(0.5 * 1.1 * 100)
    assert (9, "modis_eq", "noaa20_to_modis") not in {
        (int(r.month), r.target, r.route) for r in old.band_month.itertuples()
    }


def test_status_columns_provisional_source_level_and_drift():
    g = grid(
        {
            (2021, 5): {"terra": 5, "aqua": 5, "snpp": 50},
            (2022, 5): {"terra": 5, "aqua": 5, "snpp": 50},
            (2026, 8): {"terra": 4, "aqua": 6, "snpp": 40},
            (2026, 9): {"terra": 4, "aqua": 6, "snpp": 40},
            (2026, 10): {"noaa20": 30},
        },
        levels={
            **{(s, 2026, 8): "api-sp" for s in ("terra", "aqua")}, ("snpp", 2026, 8): "nrt",
            **{(s, 2026, 9): "nrt" for s in ("terra", "aqua", "snpp")}, ("noaa20", 2026, 10): "nrt",
        },
    )  # fmt: skip
    c = comp({(s, 2026, m): "complete" for s in ("terra", "aqua", "snpp", "noaa20") for m in (8, 9, 10)})
    out = run(g, completeness=c)
    s21, s22 = row(out, 2021, 5), row(out, 2022, 5)
    assert not s21["provisional"] and s21["source_level"] == "country-sp" and not s21["modis_drift"]
    assert s22["modis_drift"] and not s22["provisional"]
    aug, sep, octo = row(out, 2026, 8), row(out, 2026, 9), row(out, 2026, 10)
    assert aug["provisional"] and aug["source_level"] == "mixed" and aug["source_levels"] == "api-sp+nrt"
    assert sep["provisional"] and sep["source_level"] == "nrt" and sep["modis_drift"]
    assert octo["provisional"] and octo["source_level"] == "nrt" and not octo["modis_drift"]  # MODIS gone


def test_partial_year_band_label():
    g = grid({(2005, 3): {"terra": 5, "aqua": 7}, (2005, 12): {"terra": 5, "aqua": 7}})
    assert not run(g).band_year["partial_year"].any()
    g2 = grid({(2005, 3): {"terra": 5, "aqua": 7}, (2005, 11): {"terra": 5, "aqua": 7}})
    assert run(g2).band_year["partial_year"].all()


def test_in_progress_month_is_never_in_the_series():
    g = grid({(2026, 10): {"snpp": 5, "terra": 2, "aqua": 2}, (2026, 11): {"snpp": 5, "terra": 2, "aqua": 2}})
    c = comp({(s, 2026, 10): "complete" for s in ("snpp", "terra", "aqua")})
    c = pd.concat([c, comp({(s, 2026, 11): "in_progress" for s in ("snpp", "terra", "aqua")})])
    assert run(g, completeness=c).series["month"].unique().tolist() == [10]


def _write_grid(root, years: dict[int, pd.DataFrame]):
    for y, df in years.items():
        dest = root / f"year={y}" / "part-0.parquet"
        dest.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.Table.from_pandas(df, preserve_index=False), dest)


def _read(root, kind, y):
    return pq.read_table(root / kind / f"{y}.parquet").to_pandas()


def test_adding_a_month_or_year_never_changes_earlier_sp_rows(tmp_path):
    cal = cal_with(("noaa20_to_modis", F_N20M))
    frozen, root, when = tmp_path / "frozen", tmp_path / "out", datetime(2026, 11, 15, tzinfo=UTC)
    freeze_calibration(cal, frozen)
    sats = ("terra", "aqua", "snpp", "noaa20")
    base = {(2026, m): {"terra": 3 + m, "aqua": 4, "snpp": 40 + m, "noaa20": 44 + m} for m in range(1, 5)}
    lv = {(s, 2026, m): "api-sp" for s in sats for m in range(1, 7)}
    c = comp({(s, 2026, m): "complete" for s in sats for m in range(1, 7)})
    g2025 = grid({(2025, 5): {"terra": 3, "aqua": 3, "snpp": 30, "noaa20": 33}})

    def build(months):
        _write_grid(tmp_path / "grid", {2025: g2025, 2026: grid({k: base[k] for k in months}, lv)})
        publish(cal, tmp_path / "grid", root, now=when, frozen_dir=frozen, completeness=c)

    build([(2026, 1), (2026, 2)])
    s1, bm1 = _read(root, "series", 2026), _read(root, "band_block_month", 2026)
    y25 = _read(root, "series", 2025)
    build([(2026, 1), (2026, 2), (2026, 3), (2026, 4)])
    s2, bm2 = _read(root, "series", 2026), _read(root, "band_block_month", 2026)
    pd.testing.assert_frame_equal(s1, s2[s2["month"] <= 2].reset_index(drop=True))
    pd.testing.assert_frame_equal(bm1, bm2[bm2["month"] <= 2].reset_index(drop=True))
    pd.testing.assert_frame_equal(y25, _read(root, "series", 2025))
    assert _read(root, "band_block_year", 2026)["partial_year"].all()  # the year totals do change: labelled


def test_nrt_rows_change_only_when_their_level_changes(tmp_path):
    cal = const_cal()
    frozen, root, when = tmp_path / "frozen", tmp_path / "out", datetime(2026, 11, 15, tzinfo=UTC)
    freeze_calibration(cal, frozen)
    sats = ("terra", "aqua", "snpp", "noaa20")
    c = comp({(s, 2026, m): "complete" for s in sats for m in (8, 9, 10)})
    nrt = {(s, 2026, 9): "nrt" for s in sats}
    base = {(2026, 9): {"terra": 5, "aqua": 5, "snpp": 50, "noaa20": 55}}

    def build(counts, levels):
        _write_grid(tmp_path / "grid", {2026: grid(counts, levels)})
        publish(cal, tmp_path / "grid", root, now=when, frozen_dir=frozen, completeness=c)
        return _read(root, "series", 2026)

    first = build(base, nrt)
    later = build({**base, (2026, 10): {"snpp": 9, "noaa20": 9}}, {**nrt, ("snpp", 2026, 10): "nrt"})
    pd.testing.assert_frame_equal(first, later[later["month"] == 9].reset_index(drop=True))
    assert first["provisional"].all() and (first["source_level"] == "nrt").all()
    # the same month reprocessed to standard processing (new counts, new level): the row changes
    sp = build(
        {(2026, 9): {"terra": 5, "aqua": 5, "snpp": 52, "noaa20": 55}}, {(s, 2026, 9): "api-sp" for s in sats}
    )
    assert not sp["provisional"].any() and (sp["source_level"] == "api-sp").all()
    assert sp["viirs_eq"].iloc[0] != first["viirs_eq"].iloc[0]


def test_manifest_source_from_levels_present_and_notes(tmp_path):
    cal = cal_with(("noaa20_to_modis", F_N20M), ("noaa21_to_snpp", F_N21))
    frozen, root = tmp_path / "frozen", tmp_path / "out"
    freeze_calibration(cal, frozen)
    sats = ("terra", "aqua", "snpp", "noaa20")
    lv = {(s, 2026, 1): "api-sp" for s in sats} | {(s, 2026, 9): "nrt" for s in sats}
    c = comp({(s, 2026, m): "complete" for s in sats for m in (1, 9)})
    one = {s: 5 for s in sats}
    _write_grid(
        tmp_path / "grid",
        {2005: grid({(2005, 3): {"terra": 5, "aqua": 7}}), 2026: grid({(2026, 1): one, (2026, 9): one}, lv)},
    )
    m = publish(
        cal,
        tmp_path / "grid",
        root,
        now=datetime(2026, 11, 15, tzinfo=UTC),
        frozen_dir=frozen,
        completeness=c,
    )
    assert "per-country standard-processing files (Argentina) 2005-03" in m.source
    assert "area API standard processing 2026-01" in m.source and "NRT, provisional) 2026-09" in m.source
    assert m.period == "2005-03-01/2026-09-30"
    es, en = " ".join(m.notes["es"]), " ".join(m.notes["en"])
    assert "provisional" in es and "NOAA-21" in es and "NOAA-20 a MODIS" in es and "deriva orbital" in es
    assert "MODIS como en el período de calibración" in es
    assert "provisional" in en and "NOAA-21" in en and "NOAA-20 to MODIS" in en and "orbit drift" in en
    assert "MODIS as in the calibration period" in en


def test_manifest_notes_depend_on_the_calibration():
    old = manifest_notes(const_cal(), {"country-sp"})
    assert any("No hay banda para MODIS-eq" in n for n in old["es"])
    assert not any("provisionales" in n for n in old["es"])  # no NRT in the series: no NRT note
    new = manifest_notes(cal_with(("noaa20_to_modis", F_N20M)), {"nrt"})
    assert not any("No hay banda para MODIS-eq" in n for n in new["es"])
    assert len(new["es"]) == len(new["en"])


def test_calendar_exposes_status_per_month_and_meta(tmp_path):
    cal = const_cal()
    frozen, root = tmp_path / "frozen", tmp_path / "processed" / "harmonized"
    freeze_calibration(cal, frozen)
    sats = ("terra", "aqua", "snpp", "noaa20")
    lv = {(s, 2026, 9): "nrt" for s in sats}
    c = comp({(s, 2026, m): "complete" for s in sats for m in (8, 9)})
    one = {s: 5 for s in sats}
    _write_grid(tmp_path / "grid", {2026: grid({(2026, 8): one, (2026, 9): one}, lv)})
    publish(
        cal,
        tmp_path / "grid",
        root,
        now=datetime(2026, 11, 15, tzinfo=UTC),
        frozen_dir=frozen,
        completeness=c,
    )
    store = SeriesStore(root)
    payload = calendar_payload(store, CalendarRequest(preset="cordoba", scale="viirs_eq"))
    months = {(m["year"], m["month"]): m for m in payload["months"]}
    assert months[(2026, 8)]["provisional"] is False and months[(2026, 8)]["source_level"] == "country-sp"
    assert months[(2026, 9)]["provisional"] is True and months[(2026, 9)]["source_level"] == "nrt"
    assert months[(2026, 9)]["modis_drift"] is True
    assert payload["years"][0]["provisional_months"] == 1
    assert {
        "provisional_note_es",
        "provisional_note_en",
        "modis_drift_note_es",
        "modis_drift_note_en",
    } <= set(meta(store))
