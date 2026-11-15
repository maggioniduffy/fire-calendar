"""SA2.1 cell-day presence and paired MODIS/VIIRS table on a 0.01 degree (~1 km) grid.

`present` is 1 whenever a (day, satellite, day/night, cell) has at least one detection, so N detections in
a cell count as 1. The raw count stays in `n_detections`. Cell ids use the grid stage's layout
(origin -90/-180; `cell_center(cell_id, RES)` gives the center).
"""

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from firecal.paths import interim_dir, processed_dir
from firecal.stages.grid.filters import FilterConfig, apply_filters
from firecal.stages.grid.grid import cell_ids, detection_files

RES = 0.01
KEY = ["acq_date", "daynight", "cell_id"]
_READ_COLUMNS = [
    "sensor",
    "satellite",
    "acq_date",
    "daynight",
    "latitude",
    "longitude",
    "confidence_pct",
    "confidence_class",
    "frp",
    "type",
]


def cell_day_presence(df: pd.DataFrame, res: float = RES) -> pd.DataFrame:
    """One row per (acq_date, satellite, daynight, cell_id): n_detections, frp_sum, present (=1)."""
    cols = ["acq_date", "satellite", "daynight", "cell_id", "n_detections", "frp_sum", "present"]
    if df.empty:
        return pd.DataFrame({c: pd.Series(dtype="object") for c in cols})
    d = pd.DataFrame(
        {
            "acq_date": df["acq_date"].to_numpy(),
            "satellite": df["satellite"].to_numpy(),
            "daynight": df["daynight"].to_numpy(),
            "cell_id": cell_ids(df["latitude"].to_numpy(), df["longitude"].to_numpy(), res),
            "frp": df["frp"].to_numpy(dtype="float64"),
        }
    )
    out = (
        d.groupby(["acq_date", "satellite", "daynight", "cell_id"], sort=True)
        .agg(n_detections=("frp", "size"), frp_sum=("frp", "sum"))
        .reset_index()
    )
    out["n_detections"] = out["n_detections"].astype("int32")
    out["present"] = 1
    out["present"] = out["present"].astype("int8")
    return out


def pair_table(cells: pd.DataFrame, modis_sat: str = "aqua", viirs_sat: str = "snpp") -> pd.DataFrame:
    """Outer join of two satellites by (acq_date, daynight, cell_id); the missing side is 0."""

    def side(sat: str, prefix: str) -> pd.DataFrame:
        s = cells[cells["satellite"] == sat]
        return s[KEY + ["n_detections", "frp_sum", "present"]].rename(
            columns={
                "n_detections": f"{prefix}_n",
                "frp_sum": f"{prefix}_frp",
                "present": f"{prefix}_present",
            }
        )

    out = side(modis_sat, "modis").merge(side(viirs_sat, "viirs"), on=KEY, how="outer")
    for p in ("modis", "viirs"):
        out[f"{p}_n"] = out[f"{p}_n"].fillna(0).astype("int32")
        out[f"{p}_present"] = out[f"{p}_present"].fillna(0).astype("int8")
        out[f"{p}_frp"] = out[f"{p}_frp"].fillna(0.0).astype("float64")
    cols = KEY + ["modis_n", "viirs_n", "modis_present", "viirs_present", "modis_frp", "viirs_frp"]
    return out[cols].sort_values(KEY, kind="stable").reset_index(drop=True)


def build_pairs(
    year: int,
    detections: Path | None = None,
    out: Path | None = None,
    cfg: FilterConfig | None = None,
    res: float = RES,
    modis_sat: str = "aqua",
    viirs_sat: str = "snpp",
) -> Path | None:
    """Filter one year of detections and write its pair table; None if the year has no data."""
    detections = detections or interim_dir() / "firms" / "detections"
    out = out or processed_dir() / "harmonize" / "pairs"
    files = detection_files(detections).get(year)
    if not files:
        return None
    df = pd.concat([pq.read_table(f, columns=_READ_COLUMNS).to_pandas() for f in files], ignore_index=True)
    df = apply_filters(df, cfg or FilterConfig())[0]
    df = df[df["satellite"].isin([modis_sat, viirs_sat])]
    pairs = pair_table(cell_day_presence(df, res), modis_sat, viirs_sat)
    dest = out / f"year={year}" / "part-0.parquet"
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    pq.write_table(pa.Table.from_pandas(pairs, preserve_index=False), tmp)
    tmp.replace(dest)
    return dest
