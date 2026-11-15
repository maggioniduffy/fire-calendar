from datetime import date

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from firecal.stages.grid.grid import cell_center, cell_ids
from firecal.stages.harmonize.pairs import build_pairs, cell_day_presence, pair_table


def det(lat, lon, d="2020-01-01", sensor="viirs", sat="snpp", dn="D", frp=1.0, **kw):
    row = {
        "sensor": sensor,
        "satellite": sat,
        "product": "modis" if sensor == "modis" else "viirs-snpp",
        "acq_date": date.fromisoformat(d),
        "year": int(d[:4]),
        "daynight": dn,
        "latitude": lat,
        "longitude": lon,
        "confidence_pct": 80 if sensor == "modis" else pd.NA,
        "confidence_class": "high",
        "frp": frp,
        "type": 0,
    }
    row.update(kw)
    return row


def test_cell_ids_at_001_degrees():
    ids = cell_ids(np.array([-31.4001, -31.4099, -31.4101]), np.array([-64.3, -64.3, -64.3]), 0.01)
    assert ids[0] == ids[1] != ids[2]
    lat, lon = cell_center(ids[:1], 0.01)
    assert (lat[0], lon[0]) == (-31.405, -64.295)
    # largest id fits comfortably in int64 and is unique to its corner
    assert cell_ids(np.array([90.0]), np.array([180.0]), 0.01)[0] == 18000 * 36000 - 1


def test_n_detections_in_one_cell_day_count_as_one():
    df = pd.DataFrame(
        [det(-31.4001, -64.3001, frp=2.0), det(-31.4005, -64.3009, frp=3.0), det(-31.4002, -64.3002, frp=5.0)]
    )
    out = cell_day_presence(df)
    assert len(out) == 1
    r = out.iloc[0]
    assert (r.n_detections, r.frp_sum, r.present) == (3, 10.0, 1)
    assert r.satellite == "snpp" and r.daynight == "D"


def test_days_daynight_and_cells_do_not_merge():
    df = pd.DataFrame(
        [
            det(-31.4001, -64.3001),
            det(-31.4001, -64.3001, d="2020-01-02"),
            det(-31.4001, -64.3001, dn="N"),
            det(-31.4001, -64.3001, sat="noaa20"),
            det(-31.5001, -64.3001),
        ]
    )
    out = cell_day_presence(df)
    assert len(out) == 5
    assert (out.present == 1).all() and (out.n_detections == 1).all()


def test_pair_table_zero_for_missing_side_and_only_requested_satellites():
    df = pd.DataFrame(
        [
            # both sensors see cell A (aqua x2, snpp x3)
            det(-31.4001, -64.3001, sensor="modis", sat="aqua", frp=4.0),
            det(-31.4002, -64.3002, sensor="modis", sat="aqua", frp=6.0),
            det(-31.4003, -64.3003, frp=1.0),
            det(-31.4004, -64.3004, frp=1.0),
            det(-31.4005, -64.3005, frp=1.0),
            # only aqua sees cell B
            det(-31.6001, -64.3001, sensor="modis", sat="aqua", frp=7.0),
            # only snpp sees cell C
            det(-31.8001, -64.3001, frp=2.0),
            # not requested: terra and noaa20 in cell A
            det(-31.4001, -64.3001, sensor="modis", sat="terra"),
            det(-31.4001, -64.3001, sat="noaa20"),
        ]
    )
    pairs = pair_table(cell_day_presence(df))
    assert len(pairs) == 3
    by_lat = {
        round(float(cell_center(np.array([c]), 0.01)[0][0]), 3): r
        for c, r in zip(pairs.cell_id, pairs.itertuples(), strict=True)
    }
    a, b, c = by_lat[-31.405], by_lat[-31.605], by_lat[-31.805]
    assert (a.modis_n, a.viirs_n, a.modis_present, a.viirs_present, a.modis_frp, a.viirs_frp) == (
        2,
        3,
        1,
        1,
        10.0,
        3.0,
    )
    assert (b.modis_n, b.viirs_n, b.modis_present, b.viirs_present, b.modis_frp, b.viirs_frp) == (
        1,
        0,
        1,
        0,
        7.0,
        0.0,
    )
    assert (c.modis_n, c.viirs_n, c.modis_present, c.viirs_present, c.modis_frp, c.viirs_frp) == (
        0,
        1,
        0,
        1,
        0.0,
        2.0,
    )
    assert not pairs.isna().any().any()


def test_pair_table_other_satellites_and_empty():
    df = pd.DataFrame([det(-31.4, -64.3, sensor="modis", sat="terra"), det(-31.4, -64.3, sat="noaa20")])
    pairs = pair_table(cell_day_presence(df), modis_sat="terra", viirs_sat="noaa20")
    assert len(pairs) == 1 and pairs.modis_present.iloc[0] == 1 and pairs.viirs_present.iloc[0] == 1
    assert len(pair_table(cell_day_presence(df))) == 0


def test_build_pairs_filters_and_writes(tmp_path):
    dets = tmp_path / "detections"
    rows_v = [det(-31.4001, -64.3001), det(-31.4002, -64.3002, confidence_class="low")]
    rows_m = [
        det(-31.4001, -64.3001, sensor="modis", sat="aqua"),
        det(-31.4001, -64.3001, sensor="modis", sat="aqua", confidence_pct=10),
        det(-31.4001, -64.3001, sensor="modis", sat="aqua", type=2),
    ]
    for product, rows in (("viirs-snpp", rows_v), ("modis", rows_m)):
        p = dets / f"product={product}" / "year=2020" / "part-0.parquet"
        p.parent.mkdir(parents=True)
        pq.write_table(pa.Table.from_pandas(pd.DataFrame(rows), preserve_index=False), p)
    out = tmp_path / "pairs"
    dest = build_pairs(2020, detections=dets, out=out)
    assert dest == out / "year=2020" / "part-0.parquet"
    got = pq.read_table(dest).to_pandas()
    assert len(got) == 1
    r = got.iloc[0]
    assert (r.modis_n, r.viirs_n, r.modis_present, r.viirs_present) == (1, 1, 1, 1)
    assert build_pairs(2019, detections=dets, out=out) is None
