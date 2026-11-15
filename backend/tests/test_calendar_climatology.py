import numpy as np
import pandas as pd
import pytest

from firecal.stages.calendar.climatology import anomaly, climatology


def mat(values: dict[int, list], months=12):
    rows = [{"year": y, "month": m + 1, "modis_eq": v} for y, vs in values.items() for m, v in enumerate(vs)]
    return pd.DataFrame(rows)


def test_climatology_known_values():
    base = {2001: [1] * 12, 2002: [2] * 12, 2003: [3] * 12, 2004: [4] * 12, 2005: [10] * 12}
    m = mat(base)
    # a partial year is not part of the default baseline
    m = pd.concat([m, pd.DataFrame([{"year": 2006, "month": 1, "modis_eq": 1000.0}])], ignore_index=True)
    c = climatology(m, "modis_eq")
    r = c.iloc[0]
    assert r["n_years"] == 5 and r["median"] == 3
    assert r["p10"] == pytest.approx(np.quantile([1, 2, 3, 4, 10], 0.1))
    assert r["p90"] == pytest.approx(np.quantile([1, 2, 3, 4, 10], 0.9))
    assert c.attrs["baseline_years"] == [2001, 2002, 2003, 2004, 2005]
    c2 = climatology(m, "modis_eq", baseline_years=[2001, 2002])
    assert c2.iloc[0]["median"] == 1.5


def test_anomaly_percentile_ties_and_exclusion():
    base = {2001: [1] * 12, 2002: [2] * 12, 2003: [2] * 12, 2004: [5] * 12, 2005: [2] * 12}
    cur = [3] * 5 + [2]  # reference year 2006 has data up to June -> ref = (2006, 6)
    m = pd.concat(
        [mat(base), pd.DataFrame([{"year": 2006, "month": i + 1, "modis_eq": v} for i, v in enumerate(cur)])]
    )
    a = anomaly(m, "modis_eq")
    assert a["ref"] == {"year": 2006, "month": 6}
    # baseline excludes 2006: [1,2,2,5,2]; value 2 -> below 1, ties 3 -> (1 + 1.5)/5*100 = 50
    assert a["n"] == 5 and a["median"] == 2 and a["percentile"] == pytest.approx(50.0)
    assert a["abs_anomaly"] == 0 and a["pct_anomaly"] == 0
    # a clim built with the reference year must not leak it
    leaky = climatology(m, "modis_eq", baseline_years=[2001, 2002, 2003, 2004, 2005, 2006])
    b = anomaly(m, "modis_eq", ref=(2006, 1), clim=leaky)
    assert b["n"] == 5 and b["value"] == 3
    assert b["pct_anomaly"] == pytest.approx(0.5) and b["percentile"] == pytest.approx(80.0)


def test_pct_none_when_median_zero_and_nan_ref():
    base = {y: [0] * 12 for y in range(2001, 2005)}
    m = pd.concat([mat(base), pd.DataFrame([{"year": 2005, "month": 1, "modis_eq": 4.0}])])
    a = anomaly(m, "modis_eq")
    assert a["median"] == 0 and a["pct_anomaly"] is None and a["abs_anomaly"] == 4
    assert a["percentile"] == 100.0
    m2 = pd.concat([m, pd.DataFrame([{"year": 2005, "month": 2, "modis_eq": np.nan}])])
    assert anomaly(m2, "modis_eq", ref=(2005, 2))["value"] is None
