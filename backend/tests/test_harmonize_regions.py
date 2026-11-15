import numpy as np
import pandas as pd

from firecal.stages.harmonize.regions import (
    block_ids,
    block_origin,
    build_cube,
    monthly_region_table,
    ym_of,
)


def test_block_ids_origin_and_corners():
    assert block_ids(-89.95, -179.95) == 0
    assert block_ids(89.95, 179.95) == 71 * 144 + 143
    # Cells of the 0.1 grid nest: every center inside one 2.5 degree block maps to it.
    assert block_ids(-35.75, -69.85) == block_ids(-35.05, -68.05) == block_ids(-36.25 + 0.05, -70.0 + 0.05)


def test_block_origin_inverts_ids():
    lat, lon = np.array([-35.75, -22.05]), np.array([-69.85, -54.0])
    lat0, lon0 = block_origin(block_ids(lat, lon))
    assert (lat0 <= lat).all() and (lat < lat0 + 2.5).all()
    assert (lon0 <= lon).all() and (lon < lon0 + 2.5).all()


def grid_rows():
    rows = []
    for d, sat, dn, lat, lon, n in [
        ("2020-01-05", "snpp", "D", -35.75, -69.85, 3),
        ("2020-01-20", "snpp", "D", -35.15, -69.55, 4),  # same block as above
        ("2020-01-20", "snpp", "N", -35.15, -69.55, 1),
        ("2020-02-01", "aqua", "D", -22.05, -54.05, 2),
    ]:
        rows.append(
            {
                "acq_date": pd.Timestamp(d).date(),
                "satellite": sat,
                "daynight": dn,
                "cell_lat": lat,
                "cell_lon": lon,
                "count": n,
            }
        )
    return pd.DataFrame(rows)


def test_monthly_region_table_sums_by_block_month_daynight_satellite():
    t = monthly_region_table(grid_rows())
    b0 = int(block_ids(-35.75, -69.85))
    got = t[(t.block == b0) & (t.satellite == "snpp") & (t.ym == ym_of(2020, 1))].set_index("daynight")[
        "count"
    ]
    assert got["D"] == 7 and got["N"] == 1
    assert t["count"].sum() == 10


def test_cube_fills_zeros_and_marks_partial_months_invalid():
    rows = []
    for ym in range(ym_of(2012, 1), ym_of(2012, 4)):
        rows.append({"block": 5, "ym": ym, "daynight": "D", "satellite": "snpp", "count": 10})
    rows.append({"block": 6, "ym": ym_of(2012, 3), "daynight": "N", "satellite": "snpp", "count": 2})
    cube = build_cube(pd.DataFrame(rows))
    assert list(cube.blocks) == [5, 6]
    assert cube.data["snpp"].shape == (3, 2, 2)
    assert cube.data["snpp"][0, 1].sum() == 0  # missing rows are zeros
    assert list(cube.valid["snpp"]) == [False, True, True]  # 2012-01 is partial
    assert not cube.valid["terra"].any()  # no data at all
    assert cube.select(("snpp",), start=ym_of(2012, 3)).tolist() == [False, False, True]
