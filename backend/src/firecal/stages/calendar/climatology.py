"""Monthly climatology and anomaly of the last available month (SA3.3). Retrospective, not an alert."""

import numpy as np
import pandas as pd

from firecal.stages.calendar.store import YM

QUANTILE_METHOD = "numpy linear interpolation (np.quantile, method='linear')"


def complete_years(matrix: pd.DataFrame, column: str) -> list[int]:
    """Years with a non-NaN value in all 12 months of the matrix."""
    n = matrix[matrix[column].notna()].groupby("year").size()
    return sorted(int(y) for y, c in n.items() if c == 12)


def _baseline(matrix: pd.DataFrame, column: str, baseline_years, exclude) -> list[int]:
    years = complete_years(matrix, column) if baseline_years is None else [int(y) for y in baseline_years]
    ex = {int(y) for y in exclude or ()}
    return sorted(y for y in years if y not in ex)


def _values(matrix: pd.DataFrame, column: str, month: int, years: list[int]) -> np.ndarray:
    d = matrix[(matrix["month"] == month) & matrix["year"].isin(years) & matrix[column].notna()]
    return d[column].to_numpy(dtype=float)


def climatology(matrix: pd.DataFrame, column: str, baseline_years=None, exclude_years=None) -> pd.DataFrame:
    """Per calendar month 1..12: n_years, median, p10, p90 over the baseline years.

    Quantiles use numpy linear interpolation (np.quantile, method='linear'). Only months with a non-NaN
    value count. Default baseline: complete years of the matrix, minus `exclude_years`. Baseline years are
    kept in `df.attrs["baseline_years"]`.
    """
    years = _baseline(matrix, column, baseline_years, exclude_years)
    rows = []
    for m in range(1, 13):
        v = _values(matrix, column, m, years)
        if len(v):
            q = np.quantile(v, [0.5, 0.1, 0.9], method="linear")
            rows.append({"month": m, "n_years": len(v), "median": q[0], "p10": q[1], "p90": q[2]})
        else:
            rows.append({"month": m, "n_years": 0, "median": np.nan, "p10": np.nan, "p90": np.nan})
    out = pd.DataFrame(rows)
    out.attrs["baseline_years"] = years
    out.attrs["quantile_method"] = QUANTILE_METHOD
    return out


def last_available(matrix: pd.DataFrame, column: str) -> YM | None:
    d = matrix[matrix[column].notna()]
    if d.empty:
        return None
    r = d.sort_values(["year", "month"]).iloc[-1]
    return int(r["year"]), int(r["month"])


def anomaly(
    matrix: pd.DataFrame, column: str, ref: YM | None = None, clim: pd.DataFrame | None = None
) -> dict:
    """Anomaly of `ref` (default: "ultimo mes disponible", the last month with a value; retrospective).

    The reference year is never in its own baseline: if `clim` was built with it, it is rebuilt without it.
    Returns value, median, p10, p90, abs_anomaly = value - median, pct_anomaly = (value - median) / median
    (None when the median is 0), percentile = empirical rank of value among the baseline values of that
    calendar month ((#below + 0.5 * #ties) / n * 100) and n.
    """
    ref = ref or last_available(matrix, column)
    empty = {
        "ref": None, "value": None, "median": None, "p10": None, "p90": None,
        "abs_anomaly": None, "pct_anomaly": None, "percentile": None, "n": 0,
    }  # fmt: skip
    if ref is None:
        return empty
    y, m = ref
    cell = matrix[(matrix["year"] == y) & (matrix["month"] == m)]
    if cell.empty or pd.isna(cell[column].iloc[0]):
        return {**empty, "ref": {"year": y, "month": m}}
    value = float(cell[column].iloc[0])
    given = None if clim is None else clim.attrs.get("baseline_years")
    if clim is None or given is None or y in given:
        base = given
        clim = climatology(matrix, column, baseline_years=base, exclude_years=[y])
    years = clim.attrs["baseline_years"]
    v = _values(matrix, column, m, years)
    n = len(v)
    row = clim[clim["month"] == m].iloc[0]
    med = None if n == 0 else float(row["median"])
    pct = None
    if n:
        pct = float((np.sum(v < value) + 0.5 * np.sum(v == value)) / n * 100)
    return {
        "ref": {"year": y, "month": m},
        "value": value,
        "median": med,
        "p10": None if n == 0 else float(row["p10"]),
        "p90": None if n == 0 else float(row["p90"]),
        "abs_anomaly": None if med is None else value - med,
        "pct_anomaly": None if not med else (value - med) / med,
        "percentile": pct,
        "n": n,
    }
