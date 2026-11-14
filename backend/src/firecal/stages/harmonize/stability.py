"""Stability tables for the harmonization (design in plan/02-harmonization.md).

Ratios of national sums by year from the monthly cube (default filters), plus, from the detections, the mean
acquisition hour (UTC) per satellite and year and the MODIS/S-NPP ratio with and without the `type` filter.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from firecal.paths import interim_dir
from firecal.stages.grid.filters import FilterConfig, apply_filters
from firecal.stages.grid.grid import detection_files
from firecal.stages.harmonize.regions import MODIS_SATS, Cube

NO_TYPE_FILTER = FilterConfig(types=(0, 1, 2, 3), keep_missing_type=True)
_COLUMNS = [
    "sensor",
    "satellite",
    "acq_datetime",
    "acq_date",
    "daynight",
    "confidence_pct",
    "confidence_class",
    "type",
]


def ratio_by_year(
    cube: Cube,
    num: tuple[str, ...],
    den: tuple[str, ...],
    first_year: int,
    last_year: int | None = None,
) -> pd.DataFrame:
    """National ratio of sums num / den by year (total, day, night) over months valid for both."""
    sel = cube.select(num + den)
    years = cube.year
    rows = []
    for y in np.unique(years[sel & (years >= first_year)]):
        if last_year is not None and y > last_year:
            continue
        m = sel & (years == y)
        n, d = cube.total(num)[m].sum(axis=(0, 1)), cube.total(den)[m].sum(axis=(0, 1))  # (2,)
        rows.append(
            {
                "year": int(y),
                "months": int(m.sum()),
                "num": float(n.sum()),
                "den": float(d.sum()),
                "ratio": float(n.sum() / d.sum()) if d.sum() > 0 else float("nan"),
                "ratio_day": float(n[0] / d[0]) if d[0] > 0 else float("nan"),
                "ratio_night": float(n[1] / d[1]) if d[1] > 0 else float("nan"),
            }
        )
    return pd.DataFrame(rows)


def grid_tables(cube: Cube) -> dict[str, pd.DataFrame]:
    modis = ratio_by_year(cube, MODIS_SATS, ("snpp",), 2012)
    terra = ratio_by_year(cube, ("terra",), ("snpp",), 2012).set_index("year")["ratio"]
    aqua = ratio_by_year(cube, ("aqua",), ("snpp",), 2012).set_index("year")["ratio"]
    modis["terra_snpp"] = modis["year"].map(terra)
    modis["aqua_snpp"] = modis["year"].map(aqua)
    return {
        "modis_snpp": modis,
        "noaa20_snpp": ratio_by_year(cube, ("noaa20",), ("snpp",), 2018),
        "terra_aqua": ratio_by_year(cube, ("terra",), ("aqua",), 2003),
    }


def _hours(df: pd.DataFrame) -> pd.Series:
    t = pd.to_datetime(df["acq_datetime"], utc=True)
    h = (t.dt.hour + t.dt.minute / 60).to_numpy(dtype="float64")
    # Night passes straddle no more than midnight UTC: shift evening hours to negative before averaging.
    h = np.where((df["daynight"] == "N").to_numpy() & (h >= 12), h - 24, h)
    return pd.Series(h, index=df.index)


def detections_tables(detections: Path | None = None) -> dict[str, pd.DataFrame]:
    """Mean UTC hour per satellite/year/day-night; MODIS and S-NPP counts with and without the type filter."""
    detections = detections or interim_dir() / "firms" / "detections"
    default = FilterConfig()
    hour_rows, type_rows = [], []
    for year, files in sorted(detection_files(detections).items()):
        df = pd.concat([pq.read_table(f, columns=_COLUMNS).to_pandas() for f in files], ignore_index=True)
        kept = apply_filters(df, default)[0]
        h = _hours(kept)
        for (sat, dn), g in h.groupby([kept["satellite"], kept["daynight"]]):
            hour_rows.append({"year": year, "satellite": sat, "daynight": dn, "hour": float(g.mean()) % 24})
        # Counts for the type comparison; the partial month 2012-01 is out of both sides.
        d = pd.to_datetime(df["acq_date"])
        df = df[~((d.dt.year == 2012) & (d.dt.month == 1)).to_numpy()]
        kept_all = apply_filters(df, NO_TYPE_FILTER)[0]
        kept_def = apply_filters(df, default)[0]
        rec: dict = {"year": year}
        for tag, k in (("def", kept_def), ("all", kept_all)):
            rec[f"modis_{tag}"] = int(k["satellite"].isin(MODIS_SATS).sum())
            rec[f"snpp_{tag}"] = int((k["satellite"] == "snpp").sum())
        type_rows.append(rec)
    hours = pd.DataFrame(hour_rows)
    types = pd.DataFrame(type_rows)
    if not types.empty:
        has = types["snpp_def"] > 0
        types["ratio_def"] = np.where(has, types["modis_def"] / types["snpp_def"].where(has, 1), np.nan)
        types["ratio_all"] = np.where(has, types["modis_all"] / types["snpp_all"].where(has, 1), np.nan)
        types["modis_type_share"] = 1 - types["modis_def"] / types["modis_all"].where(types["modis_all"] > 0)
        types["snpp_type_share"] = 1 - types["snpp_def"] / types["snpp_all"].where(types["snpp_all"] > 0)
    return {"hours": hours, "types": types}


def step_summary(ratio: pd.DataFrame, col: str, groups: dict[str, tuple[int, int]]) -> dict[str, float]:
    """Mean of the yearly ratios `col` within each (first, last) year range."""
    out = {}
    for name, (a, b) in groups.items():
        v = ratio.loc[(ratio["year"] >= a) & (ratio["year"] <= b), col].dropna()
        out[name] = float(v.mean()) if len(v) else float("nan")
    return out
