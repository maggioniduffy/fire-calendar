"""Regions for the harmonization baselines: 2.5 degree blocks and the monthly region table.

Blocks use the grid stage's origin (-90/-180), so they nest the 0.1 and 0.25 degree grids exactly. The monthly
table sums the 0.1 degree grid counts (after the default `FilterConfig`) by block x year-month x day/night x
satellite. `Cube` is the dense (month, block, day/night) view that the baselines work on.
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from firecal.paths import interim_dir

BLOCK_DEG = 2.5
SATELLITES = ("terra", "aqua", "snpp", "noaa20")
DAYNIGHT = ("D", "N")
MODIS_SATS = ("terra", "aqua")
# Months with only part of the month observed (first month of a record that starts mid-month).
PARTIAL_MONTHS: dict[str, tuple[tuple[int, int], ...]] = {
    "aqua": ((2002, 7),),
    "snpp": ((2012, 1),),
    "noaa20": ((2018, 4),),
}
_SCALE = 1_000_000


def ym_of(year: int, month: int) -> int:
    """Month index: year * 12 + (month - 1)."""
    return year * 12 + month - 1


def n_block_cols(size: float = BLOCK_DEG) -> int:
    return round(360 / size)


def block_ids(lat, lon, size: float = BLOCK_DEG) -> np.ndarray:
    """Block id (row * ncols + col) of each point; origin -90/-180."""
    nrows, ncols = round(180 / size), n_block_cols(size)
    s = round(size * _SCALE)
    row = (np.round(np.asarray(lat, dtype="float64") * _SCALE).astype(np.int64) + 90 * _SCALE) // s
    col = (np.round(np.asarray(lon, dtype="float64") * _SCALE).astype(np.int64) + 180 * _SCALE) // s
    return np.clip(row, 0, nrows - 1) * ncols + np.clip(col, 0, ncols - 1)


def block_origin(block, size: float = BLOCK_DEG) -> tuple[np.ndarray, np.ndarray]:
    """South-west corner (lat, lon) of each block."""
    row, col = np.divmod(np.asarray(block), n_block_cols(size))
    return row * size - 90, col * size - 180


def monthly_region_table(grid: pd.DataFrame, size: float = BLOCK_DEG) -> pd.DataFrame:
    """Sum 0.1 degree grid rows into block x ym x daynight x satellite counts (long format)."""
    cols = ["block", "ym", "daynight", "satellite", "count"]
    if grid.empty:
        return pd.DataFrame({c: pd.Series(dtype="int64" if c != "daynight" else "object") for c in cols})
    dates = pd.to_datetime(grid["acq_date"])
    d = pd.DataFrame(
        {
            "block": block_ids(grid["cell_lat"].to_numpy(), grid["cell_lon"].to_numpy(), size),
            "ym": (dates.dt.year * 12 + dates.dt.month - 1).to_numpy().astype(np.int64),
            "daynight": grid["daynight"].to_numpy(),
            "satellite": grid["satellite"].to_numpy(),
            "count": grid["count"].to_numpy().astype(np.int64),
        }
    )
    return d.groupby(["block", "ym", "daynight", "satellite"], sort=True, as_index=False)["count"].sum()


def build_monthly_region_table(grid_dir: Path | None = None, size: float = BLOCK_DEG) -> pd.DataFrame:
    """Read the 0.1 degree grid one year at a time and return the long monthly region table."""
    grid_dir = grid_dir or interim_dir() / "firms" / "grid_0.1"
    parts = []
    for f in sorted(grid_dir.glob("year=*/part-0.parquet")):
        df = pq.read_table(f, columns=["acq_date", "satellite", "daynight", "cell_lat", "cell_lon", "count"])
        parts.append(monthly_region_table(df.to_pandas(), size))
    if not parts:
        return monthly_region_table(pd.DataFrame())
    return (
        pd.concat(parts, ignore_index=True)
        .groupby(["block", "ym", "daynight", "satellite"], sort=True, as_index=False)["count"]
        .sum()
    )


@dataclass(eq=False)
class Cube:
    """Dense counts: `data[satellite]` has shape (months, blocks, 2) with day/night on the last axis.

    A satellite-month is `valid` when the satellite has data in the table at or after its first month and the
    month is not a known partial month. Missing rows inside valid months are true zeros.
    """

    ym: np.ndarray
    blocks: np.ndarray
    data: dict[str, np.ndarray]
    valid: dict[str, np.ndarray]

    @property
    def year(self) -> np.ndarray:
        return self.ym // 12

    @property
    def month_idx(self) -> np.ndarray:
        return self.ym % 12

    @property
    def dates(self) -> pd.DatetimeIndex:
        return pd.DatetimeIndex([pd.Timestamp(int(y) // 12, int(y) % 12 + 1, 1) for y in self.ym])

    def total(self, sats) -> np.ndarray:
        return sum(self.data[s] for s in sats)

    def select(self, sats, start: int | None = None, end: int | None = None) -> np.ndarray:
        """Boolean mask over months valid for every satellite in `sats` within [start, end] (ym)."""
        m = np.ones(len(self.ym), dtype=bool)
        for s in sats:
            m &= self.valid[s]
        if start is not None:
            m &= self.ym >= start
        if end is not None:
            m &= self.ym <= end
        return m


def build_cube(table: pd.DataFrame) -> Cube:
    ym_all = np.arange(int(table["ym"].min()), int(table["ym"].max()) + 1)
    blocks = np.sort(table["block"].unique())
    data = {s: np.zeros((len(ym_all), len(blocks), 2)) for s in SATELLITES}
    valid: dict[str, np.ndarray] = {}
    ti = table["ym"].to_numpy() - ym_all[0]
    bi = np.searchsorted(blocks, table["block"].to_numpy())
    di = (table["daynight"].to_numpy() == "N").astype(int)
    for s in SATELLITES:
        sel = (table["satellite"] == s).to_numpy()
        np.add.at(data[s], (ti[sel], bi[sel], di[sel]), table["count"].to_numpy()[sel])
        v = np.zeros(len(ym_all), dtype=bool)
        if sel.any():
            v = ym_all >= int(table.loc[sel, "ym"].min())
        for y, m in PARTIAL_MONTHS.get(s, ()):
            v &= ym_all != ym_of(y, m)
        valid[s] = v
    return Cube(ym_all, blocks, data, valid)
