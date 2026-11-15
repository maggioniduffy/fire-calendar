"""SA2.11 final harmonized series: MODIS-equivalent and VIIRS-equivalent counts per 0.1 degree cell x month.

A `Calibration` freezes the SA2.2 scale factors (one `Factors` per direction, fitted on the whole overlap with
the shrinkage `k` selected by the inner leave-one-year-out of `evaluate`) and the conformal residual
calibration of `intervals` (block-month and block-year), under a version string. Applying it to any year of
0.1 degree grid counts needs no refit, so adding a year never changes earlier rows.

Rules per (month, cell), day and night handled separately and then summed:

- MODIS-eq = observed MODIS (Terra + Aqua) where MODIS exists, else factor x VIIRS.
- VIIRS-eq = observed S-NPP where it exists, else factor x MODIS (Terra-only factor while Aqua is absent).
  After S-NPP ends, NOAA-20 is first transferred to S-NPP-equivalent (`noaa20_to_snpp`).
- The uncertainty band exists only where a value is estimated, and only at block (2.5 degree) level:
  block-month and block-year tables. A smaller area inherits an approximate band (sin verificar).

`method` is pluggable; only "scale_factor" is implemented. A future "lightgbm" would add its own branch in
`fit_calibration` / `build_series` if and only if it passes its fixed criterion (reports/02).
"""

import dataclasses
import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from firecal.layers.manifest import LayerManifest
from firecal.paths import REPO_ROOT, interim_dir, processed_dir
from firecal.stages.grid.filters import FilterConfig
from firecal.stages.harmonize.evaluate import (
    NOMINAL,
    OVERLAP_END,
    PAIRS,
    pair_data,
)
from firecal.stages.harmonize.intervals import (
    MIN_PER_BIN,
    N_BINS,
    SMALL_MONTH,
    SMALL_YEAR,
    BinnedConformal,
    fit_binned,
    inner_residuals,
)
from firecal.stages.harmonize.regions import (
    BLOCK_DEG,
    PARTIAL_MONTHS,
    Cube,
    block_ids,
    block_origin,
    restrict_blocks,
    ym_of,
)
from firecal.stages.harmonize.route import (
    LEGS,
    ROUTE_PAIR,
    fit_route,
    route_inner_residuals,
)
from firecal.stages.harmonize.scale_factor import Factors, fit_factors, select_k

LAYER_ID = "harmonized"
CALIBRATION_VERSION = "sf-2026.11.1"
METHODS = ("scale_factor",)
# Pairs the frozen calibration carries: both directions, the Terra-only inverse, and the NOAA-20 transfer.
CAL_PAIRS = ("viirs_to_modis", "modis_to_viirs", "terra_to_viirs", "noaa20_to_snpp")
# Pairs `extend_calibration` appends to a frozen calibration (SA2.10): NOAA-21 on its SP overlap, and the
# post-MODIS route `ROUTE_PAIR` (chain or direct, by the P5 decision).
EXTEND_PAIRS = ("noaa21_to_snpp", "noaa21_to_noaa20")
EXTEND_END = ym_of(2026, 7)  # last NOAA-21 standard-processing month (complete months only inside the cube)
# S-NPP ends 2026-11-02 (as stated for this task); its last complete month is 2026-10. NOAA-20 takes over.
SNPP_LAST_FULL_YM = ym_of(2026, 10)
SATS = ("terra", "aqua", "snpp", "noaa20", "noaa21")
FIRST_SERIES_YM = ym_of(2000, 11)

_GRID_COLUMNS = ["acq_date", "satellite", "daynight", "cell_id", "cell_lat", "cell_lon", "count"]
_LEVEL_COLUMN = "level"  # processing level of the grid rows (country-sp / api-sp / nrt); older grids lack it
# Months from 2026-01 are gated by the completeness table (P8); earlier months keep the PARTIAL_MONTHS rule.
GATE_FROM_YM = ym_of(2026, 1)
# Observed MODIS from 2022 is flagged: Terra/Aqua orbit drift, cause unverified (SA2.6).
DRIFT_FROM_YM = ym_of(2022, 1)
LEVEL_ORDER = ("country-sp", "api-sp", "nrt")
DRIFT_LABEL = "orbit drift (unverified cause)"


# --------------------------------------------------------------------------- calibration


@dataclass(eq=False)
class PairCal:
    name: str
    k: float
    k_fallback: bool
    f: np.ndarray  # (12, blocks, 2)
    f_nat: np.ndarray  # (12, 2)
    start: str  # first / last fitted month, YYYY-MM
    end: str
    n_months: int
    conf_month: BinnedConformal
    conf_year: BinnedConformal
    # Only for the post-MODIS route pair: "chain" (factor = product of the `legs` pairs of the same
    # calibration; `k` is nan because each leg has its own) or "direct". Serialized only when set, so
    # older pairs are byte-identical.
    route: str | None = None
    legs: tuple[str, ...] = ()

    @property
    def factors(self) -> Factors:
        return Factors(self.f, self.f_nat, self.k)


@dataclass(eq=False)
class Calibration:
    version: str
    method: str
    created: str  # ISO date
    fitted_start: str
    fitted_end: str
    filter_config: dict
    block_deg: float
    blocks: np.ndarray
    pairs: dict[str, PairCal]

    def factor(self, pair: str, month_idx: np.ndarray, block: np.ndarray, dn: np.ndarray) -> np.ndarray:
        """Factor per row; a block unseen at calibration time uses the national factor of its month."""
        pc = self.pairs.get(pair)
        if pc is None:
            raise ValueError(f"calibration {self.version} has no pair {pair!r}")
        bi = np.clip(np.searchsorted(self.blocks, block), 0, max(len(self.blocks) - 1, 0))
        known = (self.blocks[bi] == block) if len(self.blocks) else np.zeros(len(block), dtype=bool)
        return np.where(known, pc.f[month_idx, bi, dn], pc.f_nat[month_idx, dn])


def _num(x):
    """JSON-safe numbers: non-finite values become strings ('inf', '-inf', 'nan')."""
    if isinstance(x, np.ndarray):
        return _num(x.tolist())
    if isinstance(x, list):
        return [_num(v) for v in x]
    if isinstance(x, float) and not np.isfinite(x):
        return str(x)
    return x


def _binned_to_dict(b: BinnedConformal) -> dict:
    return {
        "edges": _num(b.edges),
        "lo": _num(b.lo),
        "hi": _num(b.hi),
        "n": _num(b.n),
        "capped": _num(b.capped),
        "small": _num(float(b.small)),
        "add_lo": _num(float(b.add_lo)),
        "add_hi": _num(float(b.add_hi)),
        "n_small": int(b.n_small),
    }


def _binned_from_dict(d: dict) -> BinnedConformal:
    return BinnedConformal(
        edges=np.asarray(d["edges"], dtype="float64"),
        lo=np.asarray(d["lo"], dtype="float64"),
        hi=np.asarray(d["hi"], dtype="float64"),
        n=np.asarray(d["n"], dtype=int),
        capped=np.asarray(d["capped"], dtype=bool),
        small=float(d["small"]),
        add_lo=float(d["add_lo"]),
        add_hi=float(d["add_hi"]),
        n_small=int(d["n_small"]),
    )


def _pair_to_dict(name: str, pc: PairCal) -> dict:
    out = {
        "label": PAIRS[name].label,
        "k": _num(pc.k),
        "k_fallback": pc.k_fallback,
        "fitted_start": pc.start,
        "fitted_end": pc.end,
        "n_months": pc.n_months,
        "f": _num(np.round(pc.f, 8)),
        "f_nat": _num(np.round(pc.f_nat, 8)),
        "conformal_block_month": _binned_to_dict(pc.conf_month),
        "conformal_block_year": _binned_to_dict(pc.conf_year),
    }
    if pc.route is not None:
        out["route"] = pc.route
        out["legs"] = list(pc.legs)
    return out


def calibration_to_dict(cal: Calibration) -> dict:
    return {
        "calibration_version": cal.version,
        "method": cal.method,
        "created": cal.created,
        "fitted_period": {"start": cal.fitted_start, "end": cal.fitted_end},
        "filter_config": cal.filter_config,
        "block_deg": cal.block_deg,
        "nominal_coverage": NOMINAL,
        "factor_axes": ["calendar month (1..12)", "block (index into `blocks`)", "day/night (D, N)"],
        "blocks": [int(b) for b in cal.blocks],
        "pairs": {name: _pair_to_dict(name, pc) for name, pc in cal.pairs.items()},
    }


def calibration_from_dict(d: dict) -> Calibration:
    pairs = {
        name: PairCal(
            name=name,
            k=float(p["k"]),
            k_fallback=bool(p["k_fallback"]),
            f=np.asarray(p["f"], dtype="float64"),
            f_nat=np.asarray(p["f_nat"], dtype="float64"),
            start=p["fitted_start"],
            end=p["fitted_end"],
            n_months=int(p["n_months"]),
            conf_month=_binned_from_dict(p["conformal_block_month"]),
            conf_year=_binned_from_dict(p["conformal_block_year"]),
            route=p.get("route"),
            legs=tuple(p.get("legs", ())),
        )
        for name, p in d["pairs"].items()
    }
    return Calibration(
        version=d["calibration_version"],
        method=d["method"],
        created=d["created"],
        fitted_start=d["fitted_period"]["start"],
        fitted_end=d["fitted_period"]["end"],
        filter_config=d["filter_config"],
        block_deg=float(d["block_deg"]),
        blocks=np.asarray(d["blocks"], dtype=np.int64),
        pairs=pairs,
    )


def calibration_path(version: str, root: Path | None = None) -> Path:
    return (root or processed_dir() / LAYER_ID) / "calibration" / f"{version}.json"


FROZEN_DIR = REPO_ROOT / "backend" / "calibrations"


class CalibrationIntegrityError(ValueError):
    """A frozen calibration is missing its checksum or does not match it."""


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _calibration_bytes(cal: Calibration) -> bytes:
    return json.dumps(calibration_to_dict(cal), indent=1).encode("utf-8")


def save_calibration(cal: Calibration, root: Path | None = None) -> Path:
    """Write the calibration of a new version; an existing version is never overwritten."""
    dest = calibration_path(cal.version, root)
    if dest.exists():
        raise FileExistsError(f"calibration {cal.version} already exists at {dest}; versions are frozen")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    tmp.write_bytes(_calibration_bytes(cal))
    tmp.replace(dest)
    return dest


def frozen_paths(version: str, frozen_dir: Path | None = None) -> tuple[Path, Path]:
    d = frozen_dir or FROZEN_DIR
    return d / f"{version}.json", d / f"{version}.json.sha256"


def freeze_calibration(cal: Calibration, frozen_dir: Path | None = None) -> Path:
    """Write `{version}.json` and its `.sha256` sidecar ("<hex>  <name>") into the frozen dir."""
    path, sidecar = frozen_paths(cal.version, frozen_dir)
    for p in (path, sidecar):
        if p.exists():
            raise FileExistsError(f"frozen calibration {cal.version} already has {p}")
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _calibration_bytes(cal)
    path.write_bytes(data)
    sidecar.write_text(f"{_sha256_hex(data)}  {path.name}\n", encoding="utf-8")
    return path


def verified_frozen_sha(version: str, frozen_dir: Path | None = None) -> str:
    """sha256 of the frozen file, checked against its sidecar; raises CalibrationIntegrityError."""
    path, sidecar = frozen_paths(version, frozen_dir)
    if not path.is_file():
        raise CalibrationIntegrityError(f"frozen calibration {version} not found at {path}")
    if not sidecar.is_file():
        raise CalibrationIntegrityError(f"frozen calibration {version} has no checksum sidecar {sidecar}")
    parts = sidecar.read_text(encoding="utf-8").split()
    if not parts:
        raise CalibrationIntegrityError(f"checksum sidecar {sidecar} is empty")
    actual = _sha256_hex(path.read_bytes())
    if parts[0].lower() != actual:
        raise CalibrationIntegrityError(
            f"frozen calibration {version} fails its checksum: sidecar {parts[0]}, file {actual}"
        )
    return actual


def load_frozen(version: str, frozen_dir: Path | None = None) -> Calibration:
    """Load a frozen calibration after verifying its sha256 against the sidecar."""
    verified_frozen_sha(version, frozen_dir)
    path, _ = frozen_paths(version, frozen_dir)
    return calibration_from_dict(json.loads(path.read_text(encoding="utf-8")))


def install_frozen(version: str, root: Path, frozen_dir: Path | None = None) -> Path:
    """Copy the verified frozen file byte for byte into `root/calibration/`; never replace a different one."""
    sha = verified_frozen_sha(version, frozen_dir)
    src, _ = frozen_paths(version, frozen_dir)
    dest = calibration_path(version, root)
    if dest.exists():
        if _sha256_hex(dest.read_bytes()) != sha:
            raise CalibrationIntegrityError(
                f"{dest} differs from frozen calibration {version}; not overwriting"
            )
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    shutil.copyfile(src, tmp)
    tmp.replace(dest)
    return dest


def load_calibration(version: str, root: Path | None = None) -> Calibration:
    return calibration_from_dict(json.loads(calibration_path(version, root).read_text(encoding="utf-8")))


def _ym_str(ym: int) -> str:
    return f"{int(ym) // 12:04d}-{int(ym) % 12 + 1:02d}"


def _fit_pair(cube: Cube, name: str, end: int) -> PairCal | None:
    """Factors and conformal calibration of one pair on its overlap months up to `end` (None: no month)."""
    d = pair_data(cube, PAIRS[name], end)
    if len(d.ym) == 0:
        return None
    train = np.ones(len(d.ym), dtype=bool)
    k, fb = select_k(d.src, d.tgt, d.dates, d.month_idx, train)
    fac = fit_factors(d.src, d.tgt, d.month_idx, train, k)
    res = inner_residuals(d.src, d.tgt, d.dates, d.month_idx, train, k)
    return _paircal(name, d, fac.f, fac.f_nat, k, fb, res)


def _paircal(name, d, f, f_nat, k, fb, res, route: str | None = None, legs: tuple[str, ...] = ()) -> PairCal:
    return PairCal(
        name=name,
        k=k,
        k_fallback=fb,
        f=f,
        f_nat=f_nat,
        start=_ym_str(d.ym[0]),
        end=_ym_str(d.ym[-1]),
        n_months=len(d.ym),
        conf_month=fit_binned(res.pred_month, res.obs_month, N_BINS, MIN_PER_BIN, 1 - NOMINAL, SMALL_MONTH),
        conf_year=fit_binned(res.pred_year, res.obs_year, N_BINS, MIN_PER_BIN, 1 - NOMINAL, SMALL_YEAR),
        route=route,
        legs=legs,
    )


def fit_calibration(
    cube: Cube,
    version: str = CALIBRATION_VERSION,
    method: str = "scale_factor",
    cfg: FilterConfig | None = None,
    created: date | None = None,
    end: int = OVERLAP_END,
) -> Calibration:
    """Fit factors and conformal calibration of every pair in `CAL_PAIRS` on the full overlap."""
    if method not in METHODS:
        raise NotImplementedError(f"method {method!r} not implemented (only {METHODS})")
    cfg = cfg or FilterConfig()
    pairs: dict[str, PairCal] = {}
    for name in CAL_PAIRS:
        pc = _fit_pair(cube, name, end)
        if pc is not None:
            pairs[name] = pc
    if not pairs:
        raise ValueError("no overlap months to calibrate on")
    starts = [pc.start for pc in pairs.values()]
    ends = [pc.end for pc in pairs.values()]
    return Calibration(
        version=version,
        method=method,
        created=(created or date.today()).isoformat(),
        fitted_start=min(starts),
        fitted_end=max(ends),
        filter_config=dataclasses.asdict(cfg),
        block_deg=BLOCK_DEG,
        blocks=np.asarray(cube.blocks, dtype=np.int64),
        pairs=pairs,
    )


class CalibrationExtensionError(ValueError):
    """The cube does not reproduce the base calibration, or the extension would change it."""


def fit_route_pair(cube: Cube, route: str, base: Calibration, end: int = OVERLAP_END) -> PairCal:
    """The post-MODIS route pair (`ROUTE_PAIR`), fitted on months <= `end` (later months stay out of sample).

    chain: factors = product of the base calibration's leg factors; conformal residuals from the inner
    leave-one-year-out in which every leg is refitted without the test year (own `k` per leg).
    direct: one NOAA-20 -> MODIS factor, same estimator; residuals the same way, `k` re-selected per fold.
    """
    d = pair_data(cube, PAIRS[ROUTE_PAIR], end)
    if len(d.ym) == 0:
        raise ValueError("no NOAA-20 / MODIS overlap months to fit the route on")
    res = route_inner_residuals(cube, route, end)
    if route == "direct":
        fit = fit_route(cube, "direct", end)
        return _paircal(ROUTE_PAIR, d, fit.f, fit.f_nat, fit.k[ROUTE_PAIR], fit.k_fallback, res, "direct", ())
    legs = [base.pairs[name] for name in LEGS]
    f = legs[0].f * legs[1].f
    f_nat = legs[0].f_nat * legs[1].f_nat
    return _paircal(ROUTE_PAIR, d, f, f_nat, float("nan"), False, res, "chain", LEGS)


def check_base_reproduced(base: Calibration, cube: Cube, end: int = OVERLAP_END) -> dict[str, float]:
    """Refit the route legs of `base` on `cube` (already on the base blocks) and compare them with the frozen
    ones: the 2000-2025 counts must be those `base` was fitted on. Returns the largest |diff| per leg."""
    out = {}
    for name in LEGS:
        pc = _fit_pair(cube, name, end)
        old = base.pairs[name]
        diff = float(np.max(np.abs(np.round(pc.f, 8) - old.f)))
        if pc.k != old.k or diff > 1e-7:
            raise CalibrationExtensionError(
                f"refit of {name} on this cube (k={pc.k}, max |df|={diff:.2e}) does not reproduce "
                f"{base.version} (k={old.k}); the 2000-2025 counts changed"
            )
        out[name] = diff
    return out


def extend_calibration(
    base: Calibration,
    cube: Cube,
    version: str,
    route: str,
    created: date | None = None,
) -> Calibration:
    """New calibration `version` = `base` untouched + NOAA-21 pairs + the post-MODIS route pair (SA2.10).

    `cube` must hold NOAA-21 and 2026 standard-processing months with partial/NRT months invalid (never an NRT
    row). It is restricted to the base blocks, so every factor is indexed on them. The base pairs are the same
    objects, so they serialize byte for byte as in `base`.
    """
    if version == base.version:
        raise CalibrationExtensionError("the new version must differ from the base version")
    new_names = (*EXTEND_PAIRS, ROUTE_PAIR)
    clash = [n for n in new_names if n in base.pairs]
    if clash:
        raise CalibrationExtensionError(f"{base.version} already has {clash}")
    cb = restrict_blocks(cube, base.blocks)
    check_base_reproduced(base, cb)
    pairs = dict(base.pairs)
    for name in EXTEND_PAIRS:
        pc = _fit_pair(cb, name, EXTEND_END)
        if pc is None:
            raise ValueError(f"no overlap months for {name}")
        pairs[name] = pc
    pairs[ROUTE_PAIR] = fit_route_pair(cb, route, base)
    return Calibration(
        version=version,
        method=base.method,
        created=(created or date.today()).isoformat(),
        fitted_start=min(pc.start for pc in pairs.values()),
        fitted_end=max(pc.end for pc in pairs.values()),
        filter_config=base.filter_config,
        block_deg=base.block_deg,
        blocks=base.blocks,
        pairs=pairs,
    )


# --------------------------------------------------------------------------- series


def wide_counts(grid: pd.DataFrame) -> pd.DataFrame:
    """Daily grid rows -> one row per (ym, cell_id, daynight) with one count column per satellite."""
    cols = ["ym", "cell_id", "cell_lat", "cell_lon", "daynight", *SATS]
    if grid.empty:
        return pd.DataFrame({c: pd.Series(dtype="float64") for c in cols})
    dates = pd.to_datetime(grid["acq_date"])
    d = pd.DataFrame(
        {
            "ym": (dates.dt.year * 12 + dates.dt.month - 1).to_numpy().astype(np.int64),
            "cell_id": grid["cell_id"].to_numpy(),
            "cell_lat": grid["cell_lat"].to_numpy(),
            "cell_lon": grid["cell_lon"].to_numpy(),
            "daynight": grid["daynight"].to_numpy(),
            "satellite": grid["satellite"].to_numpy(),
            "count": grid["count"].to_numpy().astype("float64"),
        }
    )
    w = (
        d.pivot_table(
            index=["ym", "cell_id", "cell_lat", "cell_lon", "daynight"],
            columns="satellite",
            values="count",
            aggfunc="sum",
            fill_value=0.0,
        )
        .reindex(columns=list(SATS), fill_value=0.0)
        .reset_index()
    )
    w.columns.name = None
    return w


def _grid_ym(grid: pd.DataFrame) -> np.ndarray:
    dates = pd.to_datetime(grid["acq_date"])
    return (dates.dt.year * 12 + dates.dt.month - 1).to_numpy().astype(np.int64)


def default_completeness_path() -> Path:
    from firecal.stages.grid.completeness import COMPLETENESS_FILE

    return interim_dir() / "firms" / COMPLETENESS_FILE


def load_completeness(path: Path | None = None) -> pd.DataFrame | None:
    """Completeness table (satellite, ym, status) of `grid.completeness`, or None when it is not built."""
    path = path or default_completeness_path()
    if not Path(path).is_file():
        return None
    return pd.read_parquet(path, columns=["satellite", "ym", "status"])


def sensor_months(
    grid: pd.DataFrame,
    snpp_last_ym: int = SNPP_LAST_FULL_YM,
    completeness: pd.DataFrame | None = None,
) -> dict[str, np.ndarray]:
    """Months with complete data per satellite: present in `grid`, not partial, S-NPP not after its end.

    With a `completeness` table (P8), months from 2026-01 enter only when their status is `complete`
    (in-progress and partial never); earlier months follow `PARTIAL_MONTHS` as before.
    """
    out: dict[str, np.ndarray] = {}
    if grid.empty:
        return {s: np.empty(0, dtype=np.int64) for s in SATS}
    ym = _grid_ym(grid)
    sat = grid["satellite"].to_numpy()
    for s in SATS:
        months = np.unique(ym[sat == s])
        for y, m in PARTIAL_MONTHS.get(s, ()):
            months = months[months != ym_of(y, m)]
        if s == "snpp":
            months = months[months <= snpp_last_ym]
        if completeness is not None:
            c = completeness[completeness["satellite"] == s]
            done = c.loc[c["status"] == "complete", "ym"].to_numpy(dtype=np.int64)
            months = months[(months < GATE_FROM_YM) | np.isin(months, done)]
        out[s] = months
    return out


def month_levels(grid: pd.DataFrame) -> dict[str, dict[int, str]]:
    """Processing level per satellite and month (`ym` -> country-sp / api-sp / nrt).

    The grid keeps one source per satellite-month, so the level is constant within one; if a grid ever mixed
    two, the worse level (later in `LEVEL_ORDER`) is reported. Grids without a `level` column are country SP.
    """
    out: dict[str, dict[int, str]] = {s: {} for s in SATS}
    if grid.empty:
        return out
    level = grid[_LEVEL_COLUMN].astype(str).to_numpy() if _LEVEL_COLUMN in grid.columns else LEVEL_ORDER[0]
    d = pd.DataFrame({"s": grid["satellite"].to_numpy(), "ym": _grid_ym(grid), "lv": level})
    for s, y, lv in d.drop_duplicates().itertuples(index=False):
        if s not in out:
            continue
        if lv not in LEVEL_ORDER:
            raise ValueError(f"unknown processing level {lv!r}")
        cur = out[s].get(int(y))
        if cur is None or LEVEL_ORDER.index(lv) > LEVEL_ORDER.index(cur):
            out[s][int(y)] = lv
    return out


@dataclass(eq=False)
class SeriesOut:
    series: pd.DataFrame
    band_month: pd.DataFrame
    band_year: pd.DataFrame


def _nan_sum(a: pd.Series) -> float:
    return a.sum(min_count=1)


def _level_rank(ym: np.ndarray, levels: dict[int, str] | None) -> np.ndarray:
    """Per row, index into `LEVEL_ORDER` of the satellite-month (unknown: country SP)."""
    r = np.zeros(len(ym), dtype=np.int8)
    for y, lv in (levels or {}).items():
        r[ym == y] = LEVEL_ORDER.index(lv)
    return r


def build_series(
    wide: pd.DataFrame,
    months: dict[str, np.ndarray],
    cal: Calibration,
    levels: dict[str, dict[int, str]] | None = None,
    gate_from: int | None = None,
) -> SeriesOut:
    """Apply a frozen calibration to wide counts (see `wide_counts`) -> series and band tables.

    `levels` (see `month_levels`) feeds the status columns `provisional` / `source_level`. From the month
    index `gate_from` on (P8, months gated by completeness) observed MODIS needs both Terra and Aqua
    complete: otherwise it is undefined and MODIS-eq is estimated from VIIRS. Without `gate_from` Terra
    or Aqua alone counts, as for 2000-2025.
    """
    if wide.empty:
        return SeriesOut(_empty_series(), _empty_band(False), _empty_band(True))
    ym = wide["ym"].to_numpy()
    mi = ym % 12
    blk = block_ids(wide["cell_lat"].to_numpy(), wide["cell_lon"].to_numpy(), cal.block_deg)
    dn = (wide["daynight"].to_numpy() == "N").astype(int)
    ok = {s: np.isin(ym, months.get(s, np.empty(0, dtype=np.int64))) for s in SATS}
    terra, aqua = wide["terra"].to_numpy(), wide["aqua"].to_numpy()
    snpp, n20, n21 = wide["snpp"].to_numpy(), wide["noaa20"].to_numpy(), wide["noaa21"].to_numpy()

    gated = (ym >= gate_from) if gate_from is not None else np.zeros(len(ym), dtype=bool)
    modis_exists = np.where(gated, ok["terra"] & ok["aqua"], ok["terra"] | ok["aqua"])
    t_use, a_use = modis_exists & ok["terra"], modis_exists & ok["aqua"]
    modis_rep = np.where(modis_exists, terra * t_use + aqua * a_use, np.nan)
    from_snpp = ok["snpp"]
    from_n20 = ~ok["snpp"] & ok["noaa20"]
    from_n21 = ~ok["snpp"] & ~ok["noaa20"] & ok["noaa21"] & ("noaa21_to_snpp" in cal.pairs)
    viirs_exists = from_snpp | from_n20 | from_n21
    viirs_rep = np.full(len(ym), np.nan)
    viirs_rep[from_snpp] = snpp[from_snpp]
    if from_n20.any():
        f_t = cal.factor("noaa20_to_snpp", mi[from_n20], blk[from_n20], dn[from_n20])
        viirs_rep[from_n20] = f_t * n20[from_n20]
    if from_n21.any():
        f_t = cal.factor("noaa21_to_snpp", mi[from_n21], blk[from_n21], dn[from_n21])
        viirs_rep[from_n21] = f_t * n21[from_n21]

    modis_eq = modis_rep.copy()
    est_m = ~modis_exists & viirs_exists
    # After MODIS: NOAA-20 -> MODIS has its own pair and band; while S-NPP exists `viirs_to_modis` is kept.
    # Without that pair (older calibration) or with NOAA-21 the transferred VIIRS is chained, no band.
    direct_m = est_m & from_n20 & ("noaa20_to_modis" in cal.pairs)
    chain_m = est_m & ~direct_m
    if chain_m.any():
        modis_eq[chain_m] = (
            cal.factor("viirs_to_modis", mi[chain_m], blk[chain_m], dn[chain_m]) * viirs_rep[chain_m]
        )
    if direct_m.any():
        modis_eq[direct_m] = (
            cal.factor("noaa20_to_modis", mi[direct_m], blk[direct_m], dn[direct_m]) * n20[direct_m]
        )
    viirs_eq = viirs_rep.copy()
    est_v = ~viirs_exists & modis_exists
    terra_only = est_v & ~ok["aqua"]
    full_modis = est_v & ok["aqua"]
    if full_modis.any():
        viirs_eq[full_modis] = (
            cal.factor("modis_to_viirs", mi[full_modis], blk[full_modis], dn[full_modis])
            * modis_rep[full_modis]
        )
    if terra_only.any():
        viirs_eq[terra_only] = (
            cal.factor("terra_to_viirs", mi[terra_only], blk[terra_only], dn[terra_only])
            * modis_rep[terra_only]
        )

    # Status: levels of every satellite contributing to the row (observed or as the source of an estimate).
    used = {"terra": t_use, "aqua": a_use, "snpp": from_snpp, "noaa20": from_n20, "noaa21": from_n21}
    bits = np.zeros(len(ym), dtype=np.int8)
    for s, u in used.items():
        bits |= np.where(u, np.int8(1) << _level_rank(ym, (levels or {}).get(s)), np.int8(0)).astype(np.int8)
    level_names = np.array(["+".join(lv for i, lv in enumerate(LEVEL_ORDER) if b >> i & 1) for b in range(8)])
    one = np.array([bin(b).count("1") == 1 for b in range(8)])
    source_levels = level_names[bits]
    source_level = np.where(one[bits], source_levels, "mixed")
    provisional = (bits & (1 << LEVEL_ORDER.index("nrt"))) != 0

    keep = modis_exists | viirs_exists
    d = pd.DataFrame(
        {
            "ym": ym,
            "cell_id": wide["cell_id"].to_numpy(),
            "cell_lat": wide["cell_lat"].to_numpy(),
            "cell_lon": wide["cell_lon"].to_numpy(),
            "block": blk,
            "modis_reported": modis_rep,
            "viirs_reported": viirs_rep,
            "modis_eq": modis_eq,
            "viirs_eq": viirs_eq,
            "modis_eq_estimated": est_m,
            "viirs_eq_estimated": ~from_snpp,
            "modis_sats": np.where(a_use, "terra+aqua", np.where(t_use, "terra", "none")),
            "viirs_source": np.where(
                from_snpp,
                "snpp",
                np.where(from_n20, "noaa20_transferred", np.where(from_n21, "noaa21_transferred", "none")),
            ),
            "provisional": provisional,
            "source_level": source_level,
            "source_levels": source_levels,
            "modis_drift": modis_exists & (ym >= DRIFT_FROM_YM),
        }
    )[keep]
    series = _collapse(d, cal)
    return SeriesOut(
        series,
        *_bands(
            d,
            cal,
            {
                "route_v": np.where(terra_only, "terra_to_viirs", np.where(full_modis, "modis_to_viirs", "")),
                "src_v": modis_rep,
                "est_v": est_v,
                "from_n20": from_n20,
                "from_n21": from_n21,
                "from_snpp_est_m": est_m & from_snpp,
                "direct_m": direct_m,
                "src_m": viirs_rep,
                "n20_src": n20,
                "n21_src": n21,
            },
            keep,
        ),
    )


def _collapse(d: pd.DataFrame, cal: Calibration) -> pd.DataFrame:
    """Sum day and night -> one row per (ym, cell)."""
    g = d.groupby(["ym", "cell_id", "cell_lat", "cell_lon"], sort=True, as_index=False)
    out = g.agg(
        modis_reported=("modis_reported", _nan_sum),
        viirs_reported=("viirs_reported", _nan_sum),
        modis_eq=("modis_eq", _nan_sum),
        viirs_eq=("viirs_eq", _nan_sum),
        modis_eq_estimated=("modis_eq_estimated", "max"),
        viirs_eq_estimated=("viirs_eq_estimated", "max"),
        modis_sats=("modis_sats", "first"),
        viirs_source=("viirs_source", "first"),
        provisional=("provisional", "max"),
        source_level=("source_level", "first"),
        source_levels=("source_levels", "first"),
        modis_drift=("modis_drift", "max"),
    )
    out.insert(0, "year", (out["ym"] // 12).astype("int16"))
    out.insert(1, "month", (out["ym"] % 12 + 1).astype("int8"))
    out = out.drop(columns="ym")
    out["method"] = cal.method
    out["calibration_version"] = cal.version
    out["cell_id"] = out["cell_id"].astype("int64")
    return out


BAND_MONTH_COLS = [
    "year",
    "month",
    "block",
    "block_lat_sw",
    "block_lon_sw",
    "target",
    "route",
    "estimate",
    "lo",
    "hi",
    "nominal",
    "calibration_version",
]
# `partial_year`: the year of the band is not complete in the series (e.g. the current year), so its total
# and band cover only the months present (`months_estimated` counts the estimated ones).
BAND_YEAR_COLS = [c for c in BAND_MONTH_COLS if c != "month"] + ["months_estimated", "partial_year"]


def _empty_series() -> pd.DataFrame:
    return pd.DataFrame(
        {
            c: pd.Series(dtype=t)
            for c, t in {
                "year": "int16",
                "month": "int8",
                "cell_id": "int64",
                "cell_lat": "float64",
                "cell_lon": "float64",
                "modis_reported": "float64",
                "viirs_reported": "float64",
                "modis_eq": "float64",
                "viirs_eq": "float64",
                "modis_eq_estimated": "bool",
                "viirs_eq_estimated": "bool",
                "modis_sats": "object",
                "viirs_source": "object",
                "provisional": "bool",
                "source_level": "object",
                "source_levels": "object",
                "modis_drift": "bool",
                "method": "object",
                "calibration_version": "object",
            }.items()
        }
    )


def _empty_band(year: bool) -> pd.DataFrame:
    return pd.DataFrame(
        {c: pd.Series(dtype="float64") for c in (BAND_YEAR_COLS if year else BAND_MONTH_COLS)}
    )


def _bands(
    d: pd.DataFrame, cal: Calibration, aux: dict, keep: np.ndarray
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Block-month and block-year bands of the estimated values.

    Estimated components and their calibrated route:
      viirs_eq from MODIS -> `modis_to_viirs` (Terra only: `terra_to_viirs`); viirs_eq from NOAA-20 ->
      `noaa20_to_snpp` (from NOAA-21: `noaa21_to_snpp`); modis_eq from S-NPP -> `viirs_to_modis`; modis_eq
      from NOAA-20 after MODIS -> `noaa20_to_modis` when the calibration has that pair.
    modis_eq chained from transferred NOAA-20 / NOAA-21 (no `noaa20_to_modis` pair) chains two factors and
    has no calibrated band: it is left out (the band is not defined there).
    """
    k = np.asarray(keep)
    ymk, blkk = d["ym"].to_numpy(), d["block"].to_numpy()

    def piece(mask, target, route, pred, src):
        return pd.DataFrame(
            {"ym": ymk[mask], "block": blkk[mask], "target": target, "route": route, "pred": pred[mask],
             "src": src[k][mask]}
        )  # fmt: skip

    est_v = aux["est_v"][k]
    vrep, meq = d["viirs_reported"].to_numpy(), d["modis_eq"].to_numpy()
    pieces = [
        pd.DataFrame(
            {
                "ym": ymk[est_v],
                "block": blkk[est_v],
                "target": "viirs_eq",
                "route": aux["route_v"][k][est_v],
                "pred": d["viirs_eq"].to_numpy()[est_v],
                "src": aux["src_v"][k][est_v],
            }
        ),
        piece(aux["from_n20"][k], "viirs_eq", "noaa20_to_snpp", vrep, aux["n20_src"]),
        piece(aux["from_n21"][k], "viirs_eq", "noaa21_to_snpp", vrep, aux["n21_src"]),
        piece(aux["from_snpp_est_m"][k], "modis_eq", "viirs_to_modis", meq, aux["src_m"]),
        piece(aux["direct_m"][k], "modis_eq", "noaa20_to_modis", meq, aux["n20_src"]),
    ]  # fmt: skip
    e = pd.concat([p for p in pieces if len(p)], ignore_index=True) if any(len(p) for p in pieces) else None
    if e is None:
        return _empty_band(False), _empty_band(True)
    bm = e.groupby(["ym", "block", "target", "route"], sort=True, as_index=False)[["pred", "src"]].sum()
    lo = np.zeros(len(bm))
    hi = np.zeros(len(bm))
    for route, idx in bm.groupby("route").groups.items():
        sel = bm.index.get_indexer(idx)
        pred, src = bm["pred"].to_numpy()[sel], bm["src"].to_numpy()[sel]
        lo[sel], hi[sel] = cal.pairs[route].conf_month.apply(pred, src > 0)
    band_month = _band_frame(bm, lo, hi, cal, year=False)

    by = bm.assign(year=bm["ym"] // 12)
    by = by.groupby(["year", "block", "target", "route"], sort=True, as_index=False).agg(
        pred=("pred", "sum"), src=("src", "sum"), months_estimated=("ym", "nunique")
    )
    last_ym = pd.Series(ymk).groupby(ymk // 12).max()
    by["partial_year"] = (by["year"].map(last_ym) < by["year"] * 12 + 11).to_numpy()
    lo_y = np.zeros(len(by))
    hi_y = np.zeros(len(by))
    for route, idx in by.groupby("route").groups.items():
        sel = by.index.get_indexer(idx)
        pred, src = by["pred"].to_numpy()[sel], by["src"].to_numpy()[sel]
        lo_y[sel], hi_y[sel] = cal.pairs[route].conf_year.apply(pred, src > 0)
    band_year = _band_frame(by, lo_y, hi_y, cal, year=True)
    return band_month, band_year


def _band_frame(
    t: pd.DataFrame, lo: np.ndarray, hi: np.ndarray, cal: Calibration, year: bool
) -> pd.DataFrame:
    lat0, lon0 = block_origin(t["block"].to_numpy(), cal.block_deg)
    out = pd.DataFrame(
        {
            "year": (t["year"] if year else t["ym"] // 12).astype("int16").to_numpy(),
            "block": t["block"].astype("int64").to_numpy(),
            "block_lat_sw": lat0.astype("float64"),
            "block_lon_sw": lon0.astype("float64"),
            "target": t["target"].to_numpy(),
            "route": t["route"].to_numpy(),
            "estimate": t["pred"].to_numpy(),
            "lo": lo,
            "hi": hi,
            "nominal": NOMINAL,
            "calibration_version": cal.version,
        }
    )
    if year:
        out["months_estimated"] = t["months_estimated"].astype("int8").to_numpy()
        out["partial_year"] = t["partial_year"].astype(bool).to_numpy()
        return out[BAND_YEAR_COLS]
    out.insert(1, "month", (t["ym"] % 12 + 1).astype("int8").to_numpy())
    return out[BAND_MONTH_COLS]


# --------------------------------------------------------------------------- publishing


def grid_year_files(grid_dir: Path) -> dict[int, Path]:
    return {int(p.parent.name.split("=")[1]): p for p in sorted(grid_dir.glob("year=*/part-0.parquet"))}


def _write(df: pd.DataFrame, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), tmp)
    tmp.replace(dest)


def build_year(
    year: int, grid_file: Path, cal: Calibration, root: Path, completeness: pd.DataFrame | None = None
) -> SeriesOut:
    cols = list(_GRID_COLUMNS)
    if _LEVEL_COLUMN in pq.read_schema(grid_file).names:
        cols.append(_LEVEL_COLUMN)
    grid = pq.read_table(grid_file, columns=cols).to_pandas()
    out = build_series(
        wide_counts(grid),
        sensor_months(grid, completeness=completeness),
        cal,
        levels=month_levels(grid),
        gate_from=GATE_FROM_YM if completeness is not None else None,
    )
    _write(out.series, root / "series" / f"{year}.parquet")
    _write(out.band_month, root / "band_block_month" / f"{year}.parquet")
    _write(out.band_year, root / "band_block_year" / f"{year}.parquet")
    return out


NOTES_ES = [
    "VIIRS-eq 2000-2011 (y enero de 2012) es 'estimado' desde MODIS, nunca 'detectado': no ubica "
    "focos individuales.",
    "Banda de incertidumbre (conforme, 80 % nominal) solo donde el valor es estimado y solo a nivel "
    "de bloque de 2,5 grados (bloque-mes y bloque-año); el bloque-año no es la suma de bloques-mes. Un "
    "área menor que un bloque hereda una banda aproximada (sin verificar para áreas arbitrarias).",
    "Antes de 2002-08 (Aqua ausente o incompleto) VIIRS-eq usa el factor de solo Terra (extrapolación sin "
    "verificar de la relación Terra-VIIRS de 2012 en adelante a 2000-2002).",
    "Retrospectivo: no es un sistema de alerta. Calibración congelada: un año nuevo no cambia filas previas.",
    "MODIS-eq significa 'MODIS como en el período de calibración'; no es el MODIS observado hoy.",
    "Solo entran meses completos; el mes en curso nunca. En 2026 un mes con Terra o Aqua parcial no tiene "
    "MODIS observado: su MODIS-eq se estima desde VIIRS (marcado como estimado).",
    "Un año incompleto (el año en curso) tiene banda de bloque-año parcial (partial_year): cubre solo los "
    "meses presentes y se actualiza al sumar meses; las filas mensuales ya publicadas no cambian.",
]
NOTES_EN = [
    "VIIRS-eq 2000-2011 (and January 2012) is 'estimated' from MODIS, never 'detected': it does not locate "
    "individual fires.",
    "Uncertainty band (conformal, 80 % nominal) only where the value is estimated and only at "
    "2.5 degree block level (block-month and block-year); block-year is not the sum of block-months. An "
    "area smaller than a block inherits an approximate band (unverified for arbitrary areas).",
    "Before 2002-08 (Aqua absent or incomplete) VIIRS-eq uses the Terra-only factor "
    "(unverified extrapolation of the post-2012 Terra-VIIRS relation to 2000-2002).",
    "Retrospective: not an alert system. Frozen calibration: a new year does not change earlier rows.",
    "MODIS-eq means 'MODIS as in the calibration period'; it is not the MODIS observed today.",
    "Only complete months enter; the month in progress never does. In 2026 a month with a partial Terra or "
    "Aqua has no observed MODIS: its MODIS-eq is estimated from VIIRS (flagged as estimated).",
    "An incomplete year (the current one) has a partial block-year band (partial_year): it covers only the "
    "months present and is updated as months are added; monthly rows already published do not change.",
]
# Notes that depend on what the calibration carries / what the series contains.
NOTE_NO_N20_MODIS_ES = (
    "No hay banda para MODIS-eq calculado desde NOAA-20 transferido (dos factores encadenados, sin calibrar)."
)
NOTE_NO_N20_MODIS_EN = (
    "No band for MODIS-eq computed from transferred NOAA-20 (two chained factors, uncalibrated)."
)
NOTE_N20_MODIS_ES = (
    "Después del fin de MODIS (y de S-NPP), MODIS-eq = factor NOAA-20 a MODIS x conteo NOAA-20, con su "
    "propia banda conforme (bloque-mes y bloque-año) de esa ruta; mientras exista S-NPP se mantiene VIIRS a "
    "MODIS. El MODIS de referencia es el del período de calibración (sin verificar contra el MODIS actual)."
)
NOTE_N20_MODIS_EN = (
    "After MODIS (and S-NPP) end, MODIS-eq = NOAA-20 to MODIS factor x NOAA-20 count, with that route's own "
    "conformal band (block-month and block-year); while S-NPP exists VIIRS to MODIS is kept. The reference "
    "MODIS is the one of the calibration period (unverified against current MODIS)."
)
NOTE_N21_ES = (
    "NOAA-21 solo se usa como respaldo de mes completo a nivel nacional cuando NOAA-20 no está completo "
    "(factor NOAA-21 a S-NPP); nunca se promedia ni se suma con otro satélite."
)
NOTE_N21_EN = (
    "NOAA-21 is used only as a whole-month, national fallback when NOAA-20 is not complete "
    "(NOAA-21 to S-NPP factor); it is never averaged or summed with another satellite."
)
NOTE_NRT_ES = (
    "Meses provisionales: los meses con algún satélite usado en procesamiento casi en tiempo real (NRT) "
    "están marcados provisional y su fuente figura en source_level; pueden cambiar cuando se reprocesen con "
    "procesamiento estándar. La diferencia NRT frente a estándar no está verificada."
)
NOTE_NRT_EN = (
    "Provisional months: months where any satellite used comes from near-real-time (NRT) processing are "
    "flagged provisional and their source is in source_level; they may change when reprocessed with "
    "standard processing. The NRT versus standard difference is unverified."
)
NOTE_DRIFT_ES = (
    "MODIS observado desde 2022 está marcado modis_drift: deriva orbital de Terra/Aqua (causa sin verificar)."
)
NOTE_DRIFT_EN = "Observed MODIS from 2022 is flagged modis_drift: Terra/Aqua orbit drift (unverified cause)."


def manifest_notes(cal: Calibration, source_levels: set[str] | None = None):
    """Notes of the manifest (Spanish first, full English), depending on the calibration and the series."""
    es, en = list(NOTES_ES), list(NOTES_EN)
    if "noaa20_to_modis" in cal.pairs:
        es.append(NOTE_N20_MODIS_ES)
        en.append(NOTE_N20_MODIS_EN)
    else:
        es.append(NOTE_NO_N20_MODIS_ES)
        en.append(NOTE_NO_N20_MODIS_EN)
    if "noaa21_to_snpp" in cal.pairs:
        es.append(NOTE_N21_ES)
        en.append(NOTE_N21_EN)
    if source_levels is None or "nrt" in source_levels:
        es.append(NOTE_NRT_ES)
        en.append(NOTE_NRT_EN)
    es.append(NOTE_DRIFT_ES)
    en.append(NOTE_DRIFT_EN)
    return {"es": es, "en": en}


_LEVEL_TEXT = {
    "country-sp": "per-country standard-processing files (Argentina)",
    "api-sp": "area API standard processing",
    "nrt": "area API near-real-time (NRT, provisional)",
}


def _month_runs(yms: list[int]) -> str:
    """'2000-11..2025-12, 2026-03..2026-05' from month indexes."""
    runs: list[list[int]] = []
    for v in sorted(set(yms)):
        if runs and v == runs[-1][1] + 1:
            runs[-1][1] = v
        else:
            runs.append([v, v])
    return ", ".join(_ym_str(a) if a == b else f"{_ym_str(a)}..{_ym_str(b)}" for a, b in runs)


def source_text(months_by_level: dict[str, list[int]], satellites: str) -> str:
    """Manifest source from the levels actually present in the series, with their months."""
    parts = [
        f"{_LEVEL_TEXT[lv]} {_month_runs(months_by_level[lv])}" for lv in LEVEL_ORDER if lv in months_by_level
    ]
    return f"NASA FIRMS ({satellites}); " + "; ".join(parts or [_LEVEL_TEXT[LEVEL_ORDER[0]]])


def write_manifest(root: Path, cal: Calibration, now: datetime | None = None) -> LayerManifest:
    """Manifest from the files present under `root`; period from the first and last series month
    (the series holds only complete months, so the period ends at the last complete month)."""
    years = sorted(int(p.stem) for p in (root / "series").glob("*.parquet"))
    if not years:
        raise ValueError("no series files to describe")
    by_level: dict[str, set[int]] = {}
    vsrc: set[str] = set()
    first_ym = last_ym = None
    for y in years:
        t = pq.read_table(root / "series" / f"{y}.parquet")
        have = set(t.column_names)
        d = t.select([c for c in ("month", "source_levels", "viirs_source") if c in have]).to_pandas()
        if d.empty:
            continue
        d["ym"] = y * 12 + d["month"].astype("int64") - 1
        first_ym = int(d["ym"].min()) if first_ym is None else first_ym
        last_ym = int(d["ym"].max())
        vsrc |= set(d["viirs_source"].unique()) if "viirs_source" in d else set()
        # older series files carry no level columns: they were built from the per-country files
        lv = d["source_levels"] if "source_levels" in d else pd.Series(LEVEL_ORDER[0], index=d.index)
        for text, yms in d.groupby(lv)["ym"].unique().items():
            for level in str(text).split("+"):
                by_level.setdefault(level, set()).update(int(v) for v in yms)
    if first_ym is None or last_ym is None:
        raise ValueError("no series rows to describe")
    m0 = first_ym % 12 + 1
    end = (pd.Timestamp(last_ym // 12, last_ym % 12 + 1, 1) + pd.offsets.MonthEnd(0)).date()
    sats = "MODIS Terra/Aqua, VIIRS 375 m S-NPP/NOAA-20" + (
        "/NOAA-21" if any("noaa21" in v for v in vsrc) else ""
    )
    files = [
        f"{sub}/{y}.parquet" for sub in ("series", "band_block_month", "band_block_year") for y in years
    ] + [f"calibration/{cal.version}.json"]
    manifest = LayerManifest(
        id=LAYER_ID,
        title="Serie armonizada MODIS-eq / VIIRS-eq (celdas de 0,1 grados por mes) / Harmonized MODIS-eq and "
        "VIIRS-eq series",
        kind="series",
        source=source_text({k: sorted(v) for k, v in by_level.items()}, sats),
        period=f"{first_ym // 12}-{m0:02d}-01/{end.isoformat()}",
        license="NASA open data",
        updated_at=now or datetime.now(UTC),
        experimental=False,
        files=files,
        method=cal.method,
        calibration_version=cal.version,
        notes=manifest_notes(cal, set(by_level)),
    )
    (root / "manifest.json").write_text(manifest.model_dump_json(indent=1), encoding="utf-8")
    return manifest


def publish(
    cal: Calibration,
    grid_dir: Path | None = None,
    root: Path | None = None,
    years: list[int] | None = None,
    now: datetime | None = None,
    frozen_dir: Path | None = None,
    completeness: pd.DataFrame | Path | None = None,
) -> LayerManifest:
    """Build the series of `years` (default: all in `grid_dir`) with a frozen calibration;
    write the manifest. `cal` must be the frozen version (sha-verified); its file is installed
    byte for byte under `root/calibration/`.

    `completeness` (table or file) gates months from 2026-01 (P8). With the default grid it is read from
    `data/interim/firms/completeness.parquet`, and its absence is an error when the grid has 2026 data.
    """
    if _sha256_hex(_calibration_bytes(cal)) != verified_frozen_sha(cal.version, frozen_dir):
        raise CalibrationIntegrityError(f"calibration {cal.version} does not match its frozen file")
    default_grid = grid_dir is None
    grid_dir = grid_dir or interim_dir() / "firms" / "grid_0.1"
    root = root or processed_dir() / LAYER_ID
    files = grid_year_files(grid_dir)
    if completeness is None or isinstance(completeness, Path):
        completeness = load_completeness(completeness) if (default_grid or completeness) else None
        if completeness is None and default_grid and any(y * 12 >= GATE_FROM_YM for y in files):
            raise FileNotFoundError(f"completeness table not found: {default_completeness_path()}")
    for y in sorted(files):
        if years is None or y in years:
            build_year(y, files[y], cal, root, completeness)
    install_frozen(cal.version, root, frozen_dir)
    return write_manifest(root, cal, now)


def national_summary(root: Path) -> pd.DataFrame:
    """National yearly totals of the series columns (sanity check)."""
    rows = []
    for f in sorted((root / "series").glob("*.parquet")):
        d = pq.read_table(
            f, columns=["year", "modis_reported", "viirs_reported", "modis_eq", "viirs_eq"]
        ).to_pandas()
        rows.append(
            d.groupby("year")[["modis_reported", "viirs_reported", "modis_eq", "viirs_eq"]]
            .sum()
            .reset_index()
        )
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def national_monthly(root: Path, year: int) -> pd.DataFrame:
    """National monthly totals of one year with the status columns (provisional, source, drift)."""
    f = root / "series" / f"{year}.parquet"
    if not f.is_file():
        return pd.DataFrame()
    d = pq.read_table(f).to_pandas()
    g = d.groupby("month")
    out = g[["modis_reported", "viirs_reported", "modis_eq", "viirs_eq"]].sum(min_count=1)
    for c in ("modis_eq_estimated", "viirs_eq_estimated", "provisional", "modis_drift"):
        out[c] = g[c].max()
    for c in ("source_level", "source_levels", "viirs_source", "modis_sats"):
        if c in d:
            out[c] = g[c].first()
    return out.reset_index()
