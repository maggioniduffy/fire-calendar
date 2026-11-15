import numpy as np
import pandas as pd
import pytest

from firecal.stages.calendar.matrix import annual, area_band, calendar_matrix
from firecal.stages.harmonize.regions import block_ids


def cov(*items):
    return pd.DataFrame(
        [dict(year=y, month=m, modis_available=ma, viirs_available=va,
              modis_eq_estimated=me, viirs_eq_estimated=ve)
         for y, m, ma, va, me, ve in items]
    )  # fmt: skip


def rows(*items):
    return pd.DataFrame(
        [dict(year=y, month=m, cell_id=c, cell_lat=la, cell_lon=lo, modis_reported=mr, viirs_reported=vr,
              modis_eq=me, viirs_eq=ve, modis_eq_estimated=False, viirs_eq_estimated=ve_est)
         for y, m, c, la, lo, mr, vr, me, ve, ve_est in items]
    )  # fmt: skip


def test_zero_fill_nan_and_status():
    c = cov(
        (2011, 12, True, False, False, True),
        (2012, 1, True, True, False, False),
        (2012, 2, True, True, False, False),
    )
    r = rows(
        (2011, 12, 1, -31, -64, 3, np.nan, 3, 1.5, True),
        (2011, 12, 2, -31.1, -64, 2, np.nan, 2, 1.0, True),
        (2012, 1, 1, -31, -64, 1, 2, 1, 2, False),
    )
    m = calendar_matrix(r, c, (2011, 11), (2012, 2)).set_index(["year", "month"])
    assert len(m) == 4
    assert m.loc[(2011, 12), "modis_reported"] == 5 and m.loc[(2011, 12), "cells"] == 2
    assert np.isnan(m.loc[(2011, 12), "viirs_reported"])
    assert m.loc[(2011, 12), "viirs_eq"] == 2.5 and m.loc[(2011, 12), "viirs_eq_status"] == "estimated"
    assert m.loc[(2011, 12), "modis_eq_status"] == "observed"
    assert m.loc[(2012, 2), "modis_reported"] == 0 and m.loc[(2012, 2), "viirs_eq"] == 0
    assert m.loc[(2012, 2), "viirs_eq_status"] == "observed"
    # Nov 2011 not in coverage: nothing known
    assert np.isnan(m.loc[(2011, 11), "modis_eq"]) and m.loc[(2011, 11), "modis_eq_status"] == "none"


def test_empty_rows():
    c = cov((2012, 1, True, True, False, False))
    m = calendar_matrix(rows(), c, (2012, 1), (2012, 1))
    assert m.loc[0, "modis_reported"] == 0 and m.loc[0, "cells"] == 0


def test_annual_complete_flag():
    items = [(2012, mo, True, True, False, False) for mo in range(1, 13)]
    items += [(2013, mo, True, mo > 6, False, False) for mo in range(1, 13)]
    m = calendar_matrix(rows(), cov(*items), (2012, 1), (2013, 12))
    a = annual(m).set_index("year")
    assert a.loc[2012, "modis_eq_complete"] and a.loc[2012, "viirs_eq_complete"]
    assert not a.loc[2013, "viirs_reported_complete"] and a.loc[2013, "viirs_reported_n_months"] == 6
    sub = calendar_matrix(rows(), cov(*items), (2012, 1), (2012, 6))
    assert not annual(sub).set_index("year").loc[2012, "modis_eq_complete"]


def test_area_band_proportional():
    # two cells in two different 2.5 degree blocks
    la1, lo1, la2, lo2 = -31.0, -64.0, -36.0, -64.0
    b1, b2 = (int(x) for x in block_ids([la1, la2], [lo1, lo2]))
    assert b1 != b2
    # area: full cell 1 (value 4 of block est 4) and half of block 2 (value 1 of block est 2)
    r = rows((2011, 12, 1, la1, lo1, 0, 0, 0, 4.0, True), (2011, 12, 2, la2, lo2, 0, 0, 0, 1.0, True))
    bm = pd.DataFrame(
        {"year": 2011, "month": 12, "block": [b1, b2], "target": "viirs_eq", "estimate": [4.0, 2.0],
         "lo": [3.0, 1.0], "hi": [6.0, 4.0], "nominal": 0.8}
    )  # fmt: skip
    by = pd.DataFrame(
        {"year": 2011, "block": [b1, b2], "target": "viirs_eq", "estimate": [4.0, 2.0],
         "lo": [3.0, 1.0], "hi": [6.0, 4.0], "nominal": 0.8, "months_estimated": 1}
    )  # fmt: skip
    out = area_band(r, bm, by, "viirs_eq")
    mo = out["month"].iloc[0]
    assert mo["estimate"] == pytest.approx(5.0)
    assert mo["lo"] == pytest.approx(1.0 * 3.0 + 0.5 * 1.0)  # 3.5
    assert mo["hi"] == pytest.approx(1.0 * 6.0 + 0.5 * 4.0)  # 8.0
    assert mo["band_method"] == "block_proportional" and not mo["verified"]
    assert out["year"].iloc[0]["lo"] == pytest.approx(3.5)
    assert area_band(r, bm, by, "modis_eq")["month"].empty
