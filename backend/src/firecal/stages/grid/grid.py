"""SA1.4 regular global-style grid (origin -90, -180) with daily counts per cell."""

import logging
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from firecal.paths import interim_dir
from firecal.stages.grid.filters import FilterConfig, apply_filters

log = logging.getLogger(__name__)

_SCALE = 1_000_000  # integer micro-degrees: avoids floating error at cell edges
# `level` is constant within a satellite-month (one source per satellite x month), so it never splits a group.
GROUP = ["year", "acq_date", "sensor", "satellite", "daynight", "cell_id", "level"]
# Source precedence per satellite x month: per-country SP files > area API SP > area API NRT. Never summed.
LEVELS = ("country-sp", "api-sp", "nrt")


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
            "level": df["level"].to_numpy() if "level" in df.columns else LEVELS[0],
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


def level_files(detections: Path) -> dict[int, list[tuple[str, Path]]]:
    """Detection parquet files per year with their processing level.

    Country files live at `product=P/year=Y`, area API files at `product=P/level=L/year=Y`.
    """
    by_year: dict[int, list[tuple[str, Path]]] = {}
    for p in sorted(detections.glob("product=*/year=*/part-0.parquet")):
        by_year.setdefault(int(p.parent.name.split("=")[1]), []).append((LEVELS[0], p))
    for p in sorted(detections.glob("product=*/level=*/year=*/part-0.parquet")):
        level = p.parent.parent.name.split("=")[1]
        if level not in LEVELS:
            raise ValueError(f"unknown detection level {level!r} in {p}")
        by_year.setdefault(int(p.parent.name.split("=")[1]), []).append((level, p))
    return by_year


def read_year(files: list[tuple[str, Path]], columns: list[str] | None = None) -> pd.DataFrame:
    """All files of a year in one frame with a `level` column."""
    frames = []
    for level, f in files:
        d = pq.read_table(f, columns=columns).to_pandas()
        d["level"] = level
        frames.append(d)
    return pd.concat(frames, ignore_index=True)


def choose_levels(df: pd.DataFrame) -> pd.DataFrame:
    """Keep, per satellite x calendar month, only the rows of the best level present (LEVELS order)."""
    if df.empty:
        return df
    rank = df["level"].map({lv: i for i, lv in enumerate(LEVELS)}).to_numpy()
    month = pd.to_datetime(df["acq_date"]).dt.month.to_numpy()
    key = pd.DataFrame({"s": df["satellite"].to_numpy(), "m": month, "r": rank})
    best = key.groupby(["s", "m"])["r"].transform("min").to_numpy()
    return df[rank == best]


def build_grid(
    detections: Path | None = None,
    out: Path | None = None,
    res: float = 0.1,
    cfg: FilterConfig | None = None,
    nrt_mask=None,
) -> list[Path]:
    """Grid per year. One source per satellite x month (country-sp > api-sp > nrt).

    NRT rows are filtered by confidence as usual; the type filter is replaced by the accepted NRT mask of
    their sensor family. A family without an accepted mask (or no mask file at all) keeps its NRT rows out.
    """
    from firecal.stages.grid.nrt_mask import load_nrt_mask

    cfg = cfg or FilterConfig()
    detections = detections or interim_dir() / "firms" / "detections"
    out = out or interim_dir() / "firms" / f"grid_{res}"
    if nrt_mask is None:
        nrt_mask = load_nrt_mask()
    written = []
    for year, files in sorted(level_files(detections).items()):
        df = choose_levels(read_year(files))
        is_nrt = (df["level"] == "nrt").to_numpy()
        kept = apply_filters(df[~is_nrt], cfg)[0]
        nrt = df[is_nrt]
        if len(nrt):
            nrt = apply_filters(nrt, cfg, skip_type=True)[0]
            nrt = nrt_mask.apply(nrt) if nrt_mask is not None else nrt.iloc[0:0]
            if nrt_mask is None:
                log.warning("year %s: NRT rows left out of the grid (no NRT mask file)", year)
        counts = grid_counts(pd.concat([kept, nrt], ignore_index=True), res)
        dest = out / f"year={year}" / "part-0.parquet"
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".tmp")
        # `year` lives in the hive partition path only, so `pq.read_table(out)` reads the whole grid.
        table = pa.Table.from_pandas(counts.drop(columns="year"), preserve_index=False)
        pq.write_table(table, tmp)
        tmp.replace(dest)
        written.append(dest)
    return written
