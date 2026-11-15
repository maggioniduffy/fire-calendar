import json

import numpy as np
import pandas as pd

from firecal.stages.calendar.climatology import anomaly, climatology
from firecal.stages.calendar.stats import key_figures


def build():
    rows = []
    for y, base in ((2001, 1), (2002, 2)):
        for m in range(1, 13):
            rows.append({"year": y, "month": m, "viirs_eq": base + (10 if (y, m) == (2002, 8) else 0),
                         "viirs_eq_status": "estimated" if y == 2001 else "observed"})  # fmt: skip
    # partial 2003: first 3 months, huge
    for m in range(1, 4):
        rows.append({"year": 2003, "month": m, "viirs_eq": 100.0, "viirs_eq_status": "observed"})
    rows.append({"year": 2003, "month": 4, "viirs_eq": np.nan, "viirs_eq_status": "none"})
    return pd.DataFrame(rows)


def test_key_figures():
    m = build()
    a = anomaly(m, "viirs_eq")
    clim = climatology(m, "viirs_eq", exclude_years=[a["ref"]["year"]])
    k = key_figures(m, "viirs_eq", clim, a)
    assert k["most_active_month"] == {"year": 2003, "month": 1, "value": 100.0}
    assert k["most_active_year"] == {"year": 2002, "value": 2 * 12 + 10.0}
    assert k["partial_year_exceeds"] == {"year": 2003, "value": 300.0}
    assert k["total"] == 12 + 34 + 300
    assert k["peak_calendar_month"]["month"] == 8
    assert k["period_covered"]["first"] == {"year": 2001, "month": 1}
    assert k["period_covered"]["last"] == {"year": 2003, "month": 3}
    assert k["estimated_months"] == 12 and k["includes_estimated"]
    assert k["current_vs_median"]["value"] == 100.0
    json.dumps(k, allow_nan=False)


def test_key_figures_empty():
    m = pd.DataFrame({"year": [2001], "month": [1], "viirs_eq": [np.nan], "viirs_eq_status": ["none"]})
    k = key_figures(m, "viirs_eq", None, anomaly(m, "viirs_eq"))
    assert k["total"] is None and k["most_active_month"] is None
    json.dumps(k, allow_nan=False)
