"""SA1.4 regular global-style grid (origin -90, -180) with daily counts per cell."""

from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from firecal.paths import interim_dir
from firecal.stages.grid.filters import FilterConfig, apply_filters

_SCALE = 1_000_000  # integer micro-degrees: avoids floating error at cell edges
GROUP = ["year", "acq_date", "sensor", "satellite", "daynight", "cell_id"]


def grid_shape(res: float) -> tuple[int, int]:
    return round(180 / res), round(360 / res)


def cell_ids(lat: np.ndarray, lon: np.ndarray, res: float) -> np.ndarray:
    nrows, ncols = grid_shape(res)
    r = round(res * _SCALE)
    row = (np.round(np.asarray(lat) * _SCALE).astype(np.int64) + 90 * _SCALE) // r
    col = (np.round(np.asarray(lon) * _SCALE).astype(np.int64) + 180 * _SCALE) // r
    return np.clip(row, 0, nrows - 1) * ncols + np.clip(col, 0, ncols - 1)


def cell_center(cell_id: np.ndarray, res: float) -> tuple[np.ndarray, np.ndarray]:
    _, ncols = grid_shape(res)
    row, col = np.divmod(np.asarray(cell_id), ncols)
    return np.round((row + 0.5) * res - 90, 6), np.round((col + 0.5) * res - 180, 6)


def grid_counts(df: pd.DataFrame, res: float = 0.1) -> pd.DataFrame:
    d = pd.DataFrame(
        {
            "year": df["year"].to_numpy(),
            "acq_date": df["acq_date"].to_numpy(),
            "sensor": df["sensor"].to_numpy(),
            "satellite": df["satellite"].to_numpy(),
            "daynight": df["daynight"].to_numpy(),
            "cell_id": cell_ids(df["latitude"].to_numpy(), df["longitude"].to_numpy(), res),
            "frp": df["frp"].to_numpy(dtype="float64"),
        }
    )
    out = d.groupby(GROUP, sort=True).agg(count=("frp", "size"), frp_sum=("frp", "sum")).reset_index()
    out["count"] = out["count"].astype("int32")
    out["frp_sum"] = out["frp_sum"].astype("float64")
    out["cell_lat"], out["cell_lon"] = cell_center(out["cell_id"].to_numpy(), res)
    out["res"] = res
    return out


def detection_files(detections: Path) -> dict[int, list[Path]]:
    """Group detection parquet files by year across products."""
    by_year: dict[int, list[Path]] = {}
    for p in sorted(detections.glob("product=*/year=*/part-0.parquet")):
        by_year.setdefault(int(p.parent.name.split("=")[1]), []).append(p)
    return by_year


def build_grid(
    detections: Path | None = None,
    out: Path | None = None,
    res: float = 0.1,
    cfg: FilterConfig | None = None,
) -> list[Path]:
    cfg = cfg or FilterConfig()
    detections = detections or interim_dir() / "firms" / "detections"
    out = out or interim_dir() / "firms" / f"grid_{res}"
    written = []
    for year, files in sorted(detection_files(detections).items()):
        df = pd.concat([pq.read_table(f).to_pandas() for f in files], ignore_index=True)
        counts = grid_counts(apply_filters(df, cfg)[0], res)
        dest = out / f"year={year}" / "part-0.parquet"
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".tmp")
        # `year` lives in the hive partition path only, so `pq.read_table(out)` reads the whole grid.
        table = pa.Table.from_pandas(counts.drop(columns="year"), preserve_index=False)
        pq.write_table(table, tmp)
        tmp.replace(dest)
        written.append(dest)
    return written
