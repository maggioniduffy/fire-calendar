from datetime import date

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from firecal.stages.grid import FilterConfig, build_grid, cell_ids, grid_counts
from firecal.stages.grid.grid import cell_center


def det(lat, lon, d="2020-01-01", sensor="modis", sat="terra", dn="D", frp=1.0, **kw):
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


def test_cell_ids_and_edges():
    ncols = 3600
    assert cell_ids(np.array([-90.0]), np.array([-180.0]), 0.1)[0] == 0
    # point exactly on an edge belongs to the cell above/right of it (floating error safe)
    assert cell_ids(np.array([-31.4]), np.array([-64.3]), 0.1)[0] == 586 * ncols + 1157
    assert cell_ids(np.array([-31.4001]), np.array([-64.3]), 0.1)[0] == 585 * ncols + 1157
    assert cell_ids(np.array([0.3]), np.array([0.3]), 0.1)[0] == 903 * ncols + 1803
    assert cell_ids(np.array([90.0]), np.array([180.0]), 0.25)[0] == 719 * 1440 + 1439
    lat, lon = cell_center(np.array([585 * ncols + 1157]), 0.1)
    assert (lat[0], lon[0]) == (-31.45, -64.25)


def test_grid_counts_hand_computed():
    df = pd.DataFrame(
        [
            det(-31.42, -64.32, frp=2.0),  # cell A
            det(-31.43, -64.31, frp=3.0),  # cell A, same group
            det(-31.43, -64.31, frp=5.0, dn="N"),  # cell A, night
            det(-31.43, -64.31, frp=7.0, sensor="viirs", sat="snpp"),  # cell A, viirs
            det(-31.43, -64.31, d="2020-01-02", frp=11.0),  # cell A, next day
            det(-31.5, -64.2, frp=13.0),  # cell B
        ]
    )
    out = grid_counts(df, 0.1)
    assert len(out) == 5
    a = 585 * 3600 + 1156
    row = out[
        (out.cell_id == a)
        & (out.sensor == "modis")
        & (out.daynight == "D")
        & (out.acq_date == date(2020, 1, 1))
    ]
    assert row["count"].iloc[0] == 2 and row["frp_sum"].iloc[0] == 5.0
    assert out["count"].dtype == "int32" and out["frp_sum"].dtype == "float64"
    assert out["count"].sum() == 6 and out["frp_sum"].sum() == 41.0
    b = out[out.cell_id != a]
    assert len(b) == 1 and b["cell_lat"].iloc[0] == -31.45 and b["cell_lon"].iloc[0] == -64.15
    assert set(out["res"]) == {0.1}


def test_grid_025():
    out = grid_counts(pd.DataFrame([det(-31.42, -64.32), det(-31.30, -64.30)]), 0.25)
    assert len(out) == 1 and out["count"].iloc[0] == 2
    assert (out["cell_lat"].iloc[0], out["cell_lon"].iloc[0]) == (-31.375, -64.375)


def read_all(out):
    files = sorted(out.glob("year=*/part-0.parquet"))
    return pd.concat([pq.read_table(f).to_pandas() for f in files])


def write_det(root, product, year, rows):
    d = root / f"product={product}" / f"year={year}"
    d.mkdir(parents=True)
    pd.DataFrame(rows).to_parquet(d / "part-0.parquet")


def test_build_grid_partitions_filters_and_idempotent(tmp_path):
    src, out = tmp_path / "det", tmp_path / "grid"
    write_det(
        src, "modis", 2019, [det(-31.4, -64.3, d="2019-05-01"), det(-31.4, -64.3, d="2019-05-01", type=1)]
    )
    write_det(
        src,
        "modis",
        2020,
        [det(-31.4, -64.3), det(-31.4, -64.3, confidence_pct=10, confidence_class="low")],
    )
    write_det(src, "viirs-snpp", 2020, [det(-31.4, -64.3, sensor="viirs", sat="snpp")])
    build_grid(src, out, 0.1, FilterConfig())
    assert sorted(p.name for p in out.iterdir()) == ["year=2019", "year=2020"]
    first = read_all(out).sort_values(["acq_date", "sensor"]).reset_index(drop=True)
    assert first["count"].sum() == 3
    build_grid(src, out, 0.1, FilterConfig())
    second = read_all(out).sort_values(["acq_date", "sensor"]).reset_index(drop=True)
    pd.testing.assert_frame_equal(first, second)
    assert not list(out.rglob("*.tmp"))


def test_build_grid_reads_as_one_hive_dataset(tmp_path):
    src, out = tmp_path / "det", tmp_path / "grid"
    write_det(src, "modis", 2019, [det(-31.4, -64.3, d="2019-05-01")])
    write_det(src, "modis", 2020, [det(-31.4, -64.3)])
    build_grid(src, out, 0.1, FilterConfig())
    table = pq.read_table(out).to_pandas()
    assert sorted(table["year"].astype(int).tolist()) == [2019, 2020]
