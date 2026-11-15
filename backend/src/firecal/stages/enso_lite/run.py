"""SA5.5 orchestration: read the harmonized layer and the ONI table, run the pre-registered design.

Reuses `firecal.stages.calendar` (SeriesStore, presets, service.resolve / area_matrix, calendar_matrix,
climatology) and `firecal.io.enso.read_enso`. The design is fixed in `plan/05-enso-drought.md`
("SA5.5 pre-registered design"); any change must be reported as a deviation there.
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from firecal.io.enso import SOURCE as ONI_SOURCE
from firecal.io.enso import read_enso
from firecal.stages.calendar.area import ARG_BBOX, PRESETS, bbox
from firecal.stages.calendar.climatology import climatology
from firecal.stages.calendar.matrix import calendar_matrix
from firecal.stages.calendar.service import CalendarRequest, area_matrix, resolve
from firecal.stages.calendar.store import BBox, SeriesStore
from firecal.stages.enso_lite import core

SEED = 20261115
N_PERM = 5000
N_BOOT = 2000
SPLIT_YEAR = 2012  # estimated 2000-2011 vs observed 2012-2025 (VIIRS-eq)
YEAR_AXIS = (2000, 2025)  # shared year axis of the permutations
MODIS_RANGE = (2003, 2023)  # Aqua full years; Terra drift in 2024-2025

# Approximate boxes (lat_min, lat_max, lon_min, lon_max); edges on 0.1 degree cell borders. Not official
# boundaries (sin verificar).
REGION_BOXES: dict[str, BBox] = {
    "argentina": ARG_BBOX,
    "noa": (-30.0, -21.8, -69.0, -62.5),
    "nea": (-30.0, -22.0, -62.5, -53.5),
    "pampas": (-39.5, -31.0, -65.0, -57.5),
    "patagonia": (-56.0, -39.5, -73.6, -62.0),
}
AREA_LABELS = {
    "cordoba": "Cordoba preset (approximate rectangle)",
    "argentina": "All of Argentina (data box)",
    "noa": "NOA (approximate box)",
    "nea": "NEA (approximate box)",
    "pampas": "Pampas (approximate box)",
    "patagonia": "Patagonia (approximate box)",
}


@dataclass(frozen=True)
class Config:
    key: str
    area: str
    scale: str  # viirs_eq | modis_eq
    transform: str  # raw | detrend
    primary: bool = False

    @property
    def label(self) -> str:
        t = "raw" if self.transform == "raw" else "log1p-detrended"
        return f"{self.area} / {self.scale.replace('_', '-').upper()} / {t}"


def configs() -> list[Config]:
    out = [Config("primary", "cordoba", "viirs_eq", "raw", True)]
    for a in ("argentina", "noa", "nea", "pampas", "patagonia"):
        out.append(Config(f"{a}_viirs_raw", a, "viirs_eq", "raw"))
    for a in ("cordoba", "argentina", "noa", "nea", "pampas", "patagonia"):
        out.append(Config(f"{a}_modis_raw", a, "modis_eq", "raw"))
    for a in ("cordoba", "argentina", "noa", "nea", "pampas", "patagonia"):
        out.append(Config(f"{a}_viirs_detrend", a, "viirs_eq", "detrend"))
    return out


def area_monthly_matrix(store: SeriesStore, area: str) -> pd.DataFrame:
    """Year x month matrix of an area (preset through `service`, boxes through `SeriesStore.load_area`)."""
    m = store.manifest
    start = (m.period_start.year, m.period_start.month)
    end = (m.period_end.year, m.period_end.month)
    if area == "cordoba":
        r = resolve(store, CalendarRequest(preset="cordoba", scale="viirs_eq"))
        return area_matrix(store, r)[1]
    rows = store.load_area(REGION_BOXES[area], None, start, end)
    return calendar_matrix(rows, store.coverage(), start, end)


def oni_by_month(oni: pd.DataFrame) -> pd.Series:
    d = pd.DatetimeIndex(oni["date"])
    idx = d.year.to_numpy() * 12 + d.month.to_numpy() - 1
    return pd.Series(oni["oni"].to_numpy(dtype=float), index=idx).dropna()


def _column(matrix: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Matrix with the config's value column (`v`), NaN outside the period of use."""
    m = matrix[["year", "month", cfg.scale]].rename(columns={cfg.scale: "v"}).copy()
    if cfg.scale == "modis_eq":
        m.loc[(m["year"] < MODIS_RANGE[0]) | (m["year"] > MODIS_RANGE[1]), "v"] = np.nan
    return m


def build_series(matrix: pd.DataFrame, cfg: Config, oni: pd.Series) -> dict:
    """Season window, season totals and ONI lag matrix of one configuration (complete rows only)."""
    m = _column(matrix, cfg)
    clim = climatology(m, "v")
    win = core.season_window(clim["median"].to_numpy(dtype=float))
    monthly = pd.Series(
        m["v"].to_numpy(dtype=float), index=(m["year"] * 12 + m["month"] - 1).to_numpy(dtype="int64")
    )
    tot = core.season_totals(monthly, win["start_month"], win["length"])
    x = core.lagged_oni(oni, tot["season_year"], win["start_month"])
    ok = np.isfinite(x).all(axis=1)
    tot, x = tot[ok].reset_index(drop=True), x[ok]
    years = tot["season_year"].to_numpy()
    raw = tot["total"].to_numpy()
    y = core.detrend_log1p(raw, years) if cfg.transform == "detrend" else raw
    return {
        "window": win,
        "clim": clim,
        "years": years,
        "raw": raw,
        "y": y,
        "x": x,
        "n_dropped_oni": int((~ok).sum()),
    }


def _pos(years: np.ndarray) -> np.ndarray:
    return years - YEAR_AXIS[0]


def analyze(cfg: Config, s: dict, perms: np.ndarray, rng_block, rng_iid, n_boot: int) -> dict:
    years, y, x = s["years"], s["y"], s["x"]
    n = len(y)
    rho = core.spearman(y, x)
    ip = core.induce(perms, _pos(years))
    rho_perm = core.permutation_rhos(y, x, ip)
    p_lag, p_fw = core.perm_pvalues(rho, rho_perm)
    lo_b, hi_b = core.bootstrap_ci(y, x, core.block_indices(n, n_boot, core.BLOCK_LEN, rng_block))
    lo_i, hi_i = core.bootstrap_ci(y, x, core.iid_indices(n, n_boot, rng_iid))
    best = int(np.nanargmax(np.abs(rho)))
    return {
        "key": cfg.key,
        "label": cfg.label,
        "area": cfg.area,
        "scale": cfg.scale,
        "transform": cfg.transform,
        "primary": cfg.primary,
        "n": n,
        "first_year": int(years.min()),
        "last_year": int(years.max()),
        "window": s["window"],
        "rho": rho,
        "ci_block": (lo_b, hi_b),
        "ci_iid": (lo_i, hi_i),
        "p_lag": p_lag,
        "p_fw": p_fw,
        "best_lag": best,
        "perm_max": np.nanmax(np.abs(rho_perm), axis=1),
        "perm_abs": np.abs(rho_perm),
        "ac_y": core.lag1_autocorr(y, years),
        "ac_oni0": core.lag1_autocorr(x[:, 0], years),
        "years": years,
        "totals": s["raw"],
    }


def era_check(s: dict, perms: np.ndarray) -> dict:
    """Primary only: within-era ranks (split 2012) and observed-only 2012-2025."""
    years, y, x = s["years"], s["y"], s["x"]
    out: dict = {"split_year": SPLIT_YEAR}
    yr = core.within_era_ranks(y, years, SPLIT_YEAR)
    rho = core.spearman(yr, x)
    p_lag, p_fw = core.perm_pvalues(rho, core.permutation_rhos(yr, x, core.induce(perms, _pos(years))))
    out["within_era"] = {
        "n": len(y),
        "n_est": int((years < SPLIT_YEAR).sum()),
        "n_obs": int((years >= SPLIT_YEAR).sum()),
        "rho": rho,
        "p_lag": p_lag,
        "p_fw": p_fw,
    }
    sel = years >= SPLIT_YEAR
    ys, xs, ysel = y[sel], x[sel], years[sel]
    rho = core.spearman(ys, xs)
    p_lag, p_fw = core.perm_pvalues(rho, core.permutation_rhos(ys, xs, core.induce(perms, _pos(ysel))))
    out["observed_only"] = {"n": int(sel.sum()), "rho": rho, "p_lag": p_lag, "p_fw": p_fw}
    return out


def run_analysis(
    store: SeriesStore | None = None,
    oni_path: Path | str | None = None,
    seed: int = SEED,
    n_perm: int = N_PERM,
    n_boot: int = N_BOOT,
) -> dict:
    store = store or SeriesStore()
    oni_df = read_enso(oni_path)
    oni = oni_by_month(oni_df)
    ss = np.random.SeedSequence(seed)
    s_perm, s_block, s_iid = ss.spawn(3)
    rng_block, rng_iid = np.random.default_rng(s_block), np.random.default_rng(s_iid)
    n_years = YEAR_AXIS[1] - YEAR_AXIS[0] + 1
    perms = core.shared_permutations(n_years, n_perm, np.random.default_rng(s_perm))

    matrices: dict[str, pd.DataFrame] = {}
    results, primary_series = [], None
    for cfg in configs():
        if cfg.area not in matrices:
            matrices[cfg.area] = area_monthly_matrix(store, cfg.area)
        s = build_series(matrices[cfg.area], cfg, oni)
        if cfg.primary:
            primary_series = s
        results.append(analyze(cfg, s, perms, rng_block, rng_iid, n_boot))

    primary = results[0]
    expl = results[1:]
    obs_max = max(float(np.nanmax(np.abs(r["rho"]))) for r in expl)
    perm_max = np.max(np.vstack([r["perm_max"] for r in expl]), axis=0)
    expl_fw = float((1 + np.sum(perm_max >= obs_max)) / (len(perm_max) + 1))
    # power note: null quantiles of the primary family
    crit_lag = float(np.quantile(primary["perm_abs"], 0.95))
    crit_fw = float(np.quantile(primary["perm_max"], 0.95))
    m = store.manifest
    ok_dates = pd.DatetimeIndex(oni_df.loc[oni_df["oni"].notna(), "date"])
    return {
        "seed": seed,
        "n_perm": n_perm,
        "n_boot": n_boot,
        "block_len": core.BLOCK_LEN,
        "year_axis": list(YEAR_AXIS),
        "primary": primary,
        "era": era_check(primary_series, perms),
        "primary_clim": primary_series["clim"],
        "exploratory": expl,
        "exploratory_fw": {"observed_max_abs_rho": obs_max, "p": expl_fw, "n_configs": len(expl)},
        "power": {"crit_abs_rho_per_lag_95": crit_lag, "crit_abs_rho_familywise_95": crit_fw},
        "boxes": {k: list(v) for k, v in REGION_BOXES.items()} | {"cordoba": list(bbox(PRESETS["cordoba"]))},
        "provenance": {
            "fire_layer": m.id,
            "fire_source": m.source,
            "fire_period": m.period,
            "fire_method": m.method,
            "calibration_version": m.calibration_version,
            "fire_license": m.license,
            "oni_source": ONI_SOURCE,
            "oni_url": oni_df.attrs.get("url"),
            "oni_period": f"{ok_dates.min():%Y-%m} / {ok_dates.max():%Y-%m}",
        },
    }
