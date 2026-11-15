"""SA2.11 harmonized series: synthetic checks of the frozen-calibration rules, manifest and API listing."""

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from fastapi.testclient import TestClient

from firecal.api.app import create_app
from firecal.layers.manifest import discover_layers
from firecal.stages.harmonize.intervals import BinnedConformal
from firecal.stages.harmonize.regions import block_ids, build_cube, ym_of
from firecal.stages.harmonize.series import (
    Calibration,
    PairCal,
    build_series,
    calibration_from_dict,
    calibration_to_dict,
    fit_calibration,
    freeze_calibration,
    publish,
    sensor_months,
    wide_counts,
)

F_V2M, F_M2V, F_T2V, F_N2S = 0.5, 3.0, 8.0, 1.1
LAT, LON = -31.45, -64.25  # one cell inside one 2.5 degree block
CELL = 1000


def _conf() -> BinnedConformal:
    return BinnedConformal(
        edges=np.empty(0),
        lo=np.array([0.5]),
        hi=np.array([1.5]),
        n=np.array([100]),
        capped=np.array([False]),
        small=0.0,
        add_lo=0.0,
        add_hi=1.0,
        n_small=10,
    )


def const_cal(version: str = "sf-test") -> Calibration:
    blocks = np.asarray(block_ids([LAT], [LON]))
    pairs = {}
    for name, f in (
        ("viirs_to_modis", F_V2M),
        ("modis_to_viirs", F_M2V),
        ("terra_to_viirs", F_T2V),
        ("noaa20_to_snpp", F_N2S),
    ):
        pairs[name] = PairCal(
            name, 20.0, False, np.full((12, 1, 2), f), np.full((12, 2), f), "2012-02", "2025-12", 100,
            _conf(), _conf(),
        )  # fmt: skip
    return Calibration(version, "scale_factor", "2026-11-15", "2012-02", "2025-12", {}, 2.5, blocks, pairs)


def grid_rows(ym_counts: dict[tuple[int, int], dict[str, int]], daynight: str = "D") -> pd.DataFrame:
    """Daily grid rows (one day per month, one cell) from {(year, month): {satellite: count}}."""
    rows = []
    for (y, m), sats in ym_counts.items():
        for sat, n in sats.items():
            rows.append(
                {
                    "acq_date": pd.Timestamp(y, m, 10).date(),
                    "satellite": sat,
                    "daynight": daynight,
                    "cell_id": CELL,
                    "cell_lat": LAT,
                    "cell_lon": LON,
                    "count": n,
                }
            )
    return pd.DataFrame(rows)


def run(grid: pd.DataFrame, cal: Calibration | None = None):
    cal = cal or const_cal()
    return build_series(wide_counts(grid), sensor_months(grid), cal)


def row(out, y, m):
    s = out.series
    return s[(s["year"] == y) & (s["month"] == m)].iloc[0]


def test_observed_values_pass_through():
    g = grid_rows(
        {(2015, 6): {"terra": 4, "aqua": 6, "snpp": 40}, (2015, 7): {"terra": 1, "aqua": 1, "snpp": 7}}
    )
    # earlier months make both sensors "exist" in 2015 data; sensor presence is per month
    out = run(g)
    r = row(out, 2015, 6)
    assert r["modis_reported"] == 10 and r["modis_eq"] == 10
    assert r["viirs_reported"] == 40 and r["viirs_eq"] == 40
    assert not r["modis_eq_estimated"] and not r["viirs_eq_estimated"]
    assert out.band_month.empty and out.band_year.empty  # nothing estimated, no band


def test_estimated_equals_factor_times_source_and_flag_by_date():
    g = grid_rows(
        {
            (2005, 3): {"terra": 5, "aqua": 7},  # MODIS only
            (2011, 12): {"terra": 1, "aqua": 2},
            (2012, 1): {"terra": 2, "aqua": 2, "snpp": 99},  # S-NPP first month is partial: ignored
            (2012, 2): {"terra": 3, "aqua": 3, "snpp": 40},
        }
    )
    out = run(g)
    r = row(out, 2005, 3)
    assert r["viirs_eq"] == pytest.approx(F_M2V * 12)
    assert r["viirs_eq_estimated"] and np.isnan(r["viirs_reported"]) and r["viirs_source"] == "none"
    assert r["modis_eq"] == 12 and not r["modis_eq_estimated"]
    assert row(out, 2012, 1)["viirs_eq_estimated"]
    assert row(out, 2012, 1)["viirs_eq"] == pytest.approx(F_M2V * 4)
    assert not row(out, 2012, 2)["viirs_eq_estimated"]
    assert row(out, 2012, 2)["viirs_eq"] == 40


def test_terra_only_factor_before_aqua():
    g = grid_rows(
        {
            (2001, 5): {"terra": 5},  # Aqua does not exist yet
            (2002, 8): {"terra": 5, "aqua": 5},
            (2002, 7): {"terra": 5, "aqua": 2},  # first Aqua month is partial: Terra scale
        }
    )
    out = run(g)
    assert row(out, 2001, 5)["viirs_eq"] == pytest.approx(F_T2V * 5)
    assert row(out, 2001, 5)["modis_sats"] == "terra"
    assert row(out, 2002, 7)["viirs_eq"] == pytest.approx(F_T2V * 5)
    assert row(out, 2002, 8)["viirs_eq"] == pytest.approx(F_M2V * 10)
    routes = set(out.band_month["route"])
    assert routes == {"terra_to_viirs", "modis_to_viirs"}


def test_modis_eq_after_modis_and_noaa20_transfer():
    # S-NPP last complete month is 2026-10; MODIS gone; NOAA-20 transferred, then S-NPP-eq -> MODIS-eq.
    g = grid_rows(
        {
            (2026, 9): {"snpp": 100, "noaa20": 110},
            (2026, 12): {"snpp": 5, "noaa20": 20},
        }
    )
    out = run(g)
    r = row(out, 2026, 12)
    assert r["viirs_source"] == "noaa20_transferred"
    assert r["viirs_reported"] == pytest.approx(F_N2S * 20)
    assert r["viirs_eq"] == pytest.approx(F_N2S * 20) and r["viirs_eq_estimated"]
    assert r["modis_eq"] == pytest.approx(F_V2M * F_N2S * 20) and r["modis_eq_estimated"]
    assert np.isnan(r["modis_reported"])
    # band only where calibrated: NOAA-20 -> S-NPP for viirs_eq; none for the chained modis_eq
    dec = out.band_month[out.band_month["month"] == 12]
    assert set(zip(dec["target"], dec["route"], strict=True)) == {("viirs_eq", "noaa20_to_snpp")}
    sep = out.band_month[out.band_month["month"] == 9]
    assert set(zip(sep["target"], sep["route"], strict=True)) == {("modis_eq", "viirs_to_modis")}


def test_day_night_factors_applied_separately():
    cal = const_cal()
    cal.pairs["modis_to_viirs"].f[:, :, 1] = 6.0  # night factor differs
    g = pd.concat(
        [
            grid_rows({(2005, 3): {"terra": 1, "aqua": 1}}, "D"),
            grid_rows({(2005, 3): {"terra": 1, "aqua": 2}}, "N"),
        ]
    )
    r = row(run(g, cal), 2005, 3)
    assert r["viirs_eq"] == pytest.approx(3.0 * 2 + 6.0 * 3)


def test_band_only_on_estimated_and_ordered():
    g = grid_rows({(2005, 3): {"terra": 5, "aqua": 7}, (2005, 4): {"terra": 40, "aqua": 60}})
    out = run(g)
    bm = out.band_month
    assert len(bm) == 2 and (bm["lo"] <= bm["estimate"]).all() and (bm["estimate"] <= bm["hi"]).all()
    assert (bm["target"] == "viirs_eq").all() and (bm["nominal"] == 0.8).all()
    by = out.band_year
    assert len(by) == 1 and by["months_estimated"].iloc[0] == 2
    assert by["estimate"].iloc[0] == pytest.approx(bm["estimate"].sum())


def test_calibration_json_roundtrip():
    cal = const_cal()
    cal.pairs["modis_to_viirs"].conf_month = BinnedConformal(
        np.empty(0), np.array([0.0]), np.array([2.0]), np.array([3]), np.array([True]), 5.0, -np.inf, 2.0, 1
    )
    back = calibration_from_dict(calibration_to_dict(cal))
    assert back.version == cal.version and back.blocks.tolist() == cal.blocks.tolist()
    assert np.array_equal(back.pairs["viirs_to_modis"].f, cal.pairs["viirs_to_modis"].f)
    assert back.pairs["modis_to_viirs"].conf_month.add_lo == -np.inf


def test_unimplemented_method_rejected():
    with pytest.raises(NotImplementedError):
        fit_calibration(None, method="lightgbm")  # type: ignore[arg-type]


def synthetic_cube() -> pd.DataFrame:
    """Overlap 2012-02..2019-12 with exact ratios: S-NPP = 10 x MODIS(Terra+Aqua), one block, day only."""
    rows = []
    blk = int(block_ids([LAT], [LON])[0])
    for ym in range(ym_of(2012, 1), ym_of(2020, 1)):
        base = 5 + (ym % 7)
        for sat, n in (("terra", base), ("aqua", base), ("snpp", 20 * base), ("noaa20", 22 * base)):
            rows.append({"block": blk, "ym": ym, "daynight": "D", "satellite": sat, "count": n})
    return pd.DataFrame(rows)


def test_fit_calibration_recovers_known_factors():
    cube = build_cube(synthetic_cube())
    cal = fit_calibration(cube, "sf-syn")
    # fits are on valid overlap months: S-NPP from 2012-02; NOAA-20 from 2018-05
    f_v2m = cal.pairs["viirs_to_modis"].f[:, 0, 0]
    assert np.allclose(f_v2m, 0.1)
    assert np.allclose(cal.pairs["modis_to_viirs"].f[:, 0, 0], 10.0)
    assert np.allclose(cal.pairs["noaa20_to_snpp"].f[:, 0, 0], 20 / 22)
    assert cal.pairs["viirs_to_modis"].start == "2012-02"
    assert cal.fitted_end == "2019-12"


def test_adding_a_year_leaves_earlier_rows_unchanged(tmp_path):
    cal = const_cal()
    grid_dir = tmp_path / "grid"
    data = {
        2005: {(2005, 3): {"terra": 5, "aqua": 7}},
        2020: {(2020, 3): {"terra": 3, "aqua": 3, "snpp": 30}},
        2021: {(2021, 3): {"terra": 3, "aqua": 3, "snpp": 33}},
    }
    for y, d in data.items():
        dest = grid_dir / f"year={y}" / "part-0.parquet"
        dest.parent.mkdir(parents=True)
        pq.write_table(pa.Table.from_pandas(grid_rows(d), preserve_index=False), dest)
    root = tmp_path / "out" / "harmonized"
    when = datetime(2026, 11, 15, tzinfo=UTC)
    freeze_calibration(cal, tmp_path / "frozen")
    publish(cal, grid_dir, root, years=[2005, 2020], now=when, frozen_dir=tmp_path / "frozen")
    before = {y: pq.read_table(root / "series" / f"{y}.parquet").to_pandas() for y in (2005, 2020)}
    m1 = publish(cal, grid_dir, root, years=[2021], now=when, frozen_dir=tmp_path / "frozen")
    for y, df in before.items():
        pd.testing.assert_frame_equal(df, pq.read_table(root / "series" / f"{y}.parquet").to_pandas())
    assert m1.period == "2005-03-01/2021-03-31"
    assert "series/2021.parquet" in m1.files


def test_manifest_validates_and_api_lists_layer(tmp_path):
    cal = const_cal()
    grid_dir = tmp_path / "grid"
    dest = grid_dir / "year=2005" / "part-0.parquet"
    dest.parent.mkdir(parents=True)
    pq.write_table(
        pa.Table.from_pandas(grid_rows({(2005, 3): {"terra": 5, "aqua": 7}}), preserve_index=False), dest
    )
    processed = tmp_path / "processed"
    freeze_calibration(cal, tmp_path / "frozen")
    publish(
        cal, grid_dir, processed / "harmonized", now=datetime(2026, 11, 15, tzinfo=UTC),
        frozen_dir=tmp_path / "frozen",
    )  # fmt: skip

    layers = discover_layers(processed)
    assert [m.id for m in layers] == ["harmonized"]
    m = layers[0]
    assert m.kind == "series" and not m.experimental
    assert m.method == "scale_factor" and m.calibration_version == "sf-test"
    assert "NASA FIRMS" in m.source and m.period.startswith("2005-03-01")
    assert any("estimado" in n for n in m.notes["es"]) and any("estimated" in n for n in m.notes["en"])
    assert all((processed / "harmonized" / f).is_file() for f in m.files)

    client = TestClient(create_app(processed))
    listed = client.get("/layers").json()
    assert [x["id"] for x in listed] == ["harmonized"]
    assert client.get("/layers/harmonized").json()["calibration_version"] == "sf-test"
    r = client.get("/layers/harmonized/data", params={"file": m.files[0]})
    assert r.status_code == 200
    got = pd.read_parquet(pa.BufferReader(r.content))
    assert {"modis_eq", "viirs_eq", "viirs_eq_estimated", "calibration_version"} <= set(got.columns)
    assert got["viirs_eq_estimated"].all()
