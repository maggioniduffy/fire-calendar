"""Key figures of an area series (SA3.4). JSON-safe plain dict."""

import numpy as np
import pandas as pd

from firecal.stages.calendar.climatology import complete_years


def _f(x):
    if x is None:
        return None
    x = float(x)
    return None if np.isnan(x) else x


def key_figures(matrix: pd.DataFrame, column: str, clim: pd.DataFrame | None, anomaly: dict | None) -> dict:
    """Most active month/year, total, peak calendar month, current month vs median, covered period.

    Most active year only among complete years (12 months with a value); `partial_year_exceeds` flags a
    partial year with a larger total. `estimated_months` counts months with a value flagged estimated.
    """
    d = matrix[matrix[column].notna()]
    out: dict = {"column": column}
    if d.empty:
        return {
            **out, "most_active_month": None, "most_active_year": None, "partial_year_exceeds": None,
            "total": None, "peak_calendar_month": None, "current_vs_median": anomaly and _anom(anomaly),
            "period_covered": None, "estimated_months": 0, "includes_estimated": False,
        }  # fmt: skip
    r = d.loc[d[column].idxmax()]
    out["most_active_month"] = {"year": int(r["year"]), "month": int(r["month"]), "value": _f(r[column])}
    sums = d.groupby("year")[column].sum()
    full = complete_years(matrix, column)
    best = None
    if full:
        y = max(full, key=lambda k: sums[k])
        best = {"year": int(y), "value": _f(sums[y])}
    out["most_active_year"] = best
    partial = None
    for y, v in sums.items():
        beats_best = best is None or v > best["value"]
        if int(y) not in full and beats_best and (partial is None or v > partial["value"]):
            partial = {"year": int(y), "value": _f(v)}
    out["partial_year_exceeds"] = partial
    out["total"] = _f(d[column].sum())
    peak = None
    if clim is not None and clim["median"].notna().any():
        pm = clim.loc[clim["median"].idxmax()]
        peak = {"month": int(pm["month"]), "median": _f(pm["median"])}
    out["peak_calendar_month"] = peak
    out["current_vs_median"] = _anom(anomaly) if anomaly else None
    s = d.sort_values(["year", "month"])
    out["period_covered"] = {
        "first": {"year": int(s.iloc[0]["year"]), "month": int(s.iloc[0]["month"])},
        "last": {"year": int(s.iloc[-1]["year"]), "month": int(s.iloc[-1]["month"])},
    }
    sc = f"{column}_status"
    n_est = int((d[sc] == "estimated").sum()) if sc in d else 0
    out["estimated_months"] = n_est
    out["includes_estimated"] = n_est > 0
    return out


def _anom(a: dict) -> dict:
    out = {}
    for k, v in a.items():
        if isinstance(v, dict):
            out[k] = {kk: int(vv) for kk, vv in v.items()}
        elif v is None:
            out[k] = None
        elif k == "n":
            out[k] = int(v)
        else:
            out[k] = _f(v)
    return out
