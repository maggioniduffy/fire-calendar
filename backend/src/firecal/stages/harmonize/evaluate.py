"""SA2.2 / SA2.3 evaluation: leave-one-year-out with gap (and rolling origin) over the overlap period.

Every score is on block-month totals (day and night summed) and on block-year totals, per test year and
pooled.
The rolling-origin control trains on every year before the test year.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from firecal.stages.harmonize.intervals import conformal_intervals
from firecal.stages.harmonize.metrics import summarize
from firecal.stages.harmonize.quantile_map import fit_block_qmaps
from firecal.stages.harmonize.regions import MODIS_SATS, Cube, block_origin, ym_of
from firecal.stages.harmonize.scale_factor import (
    K_GRID,
    fit_factors,
    jackknife_interval,
    loyo_factor_stack,
    predict_total,
    select_k,
    yearly_spread_interval,
)
from firecal.stages.harmonize.validation import leave_one_year_out, rolling_origin

OVERLAP_START = ym_of(2012, 2)
OVERLAP_END = ym_of(2025, 12)
NOAA20_START = ym_of(2018, 5)
GAP_MONTHS = 6
NOMINAL = 0.8


@dataclass(frozen=True)
class Pair:
    src: tuple[str, ...]
    tgt: tuple[str, ...]
    start: int = OVERLAP_START
    label: str = ""


PAIRS: dict[str, Pair] = {
    "viirs_to_modis": Pair(("snpp",), MODIS_SATS, label="S-NPP -> MODIS (Terra+Aqua)"),
    "modis_to_viirs": Pair(MODIS_SATS, ("snpp",), label="MODIS (Terra+Aqua) -> S-NPP"),
    "viirs_to_terra": Pair(("snpp",), ("terra",), label="S-NPP -> Terra"),
    "terra_to_viirs": Pair(("terra",), ("snpp",), label="Terra -> S-NPP"),
    "noaa20_to_snpp": Pair(("noaa20",), ("snpp",), NOAA20_START, label="NOAA-20 -> S-NPP"),
}
MAIN_PAIRS = ("viirs_to_modis", "modis_to_viirs")
METHODS = {"sf": "SA2.2 factor", "qm": "SA2.3 cuantiles"}
INTERVALS = {
    "jackknife": "jackknife (factor)",
    "yearly": "dispersion interanual",
    "conformal": "conformal (residuos relativos)",
}
# Fixed predicted-size bins for the pooled coverage-by-size table (reporting only, nothing is tuned on them).
SIZE_EDGES = {
    "block-month": (0.0, 1.0, 5.0, 20.0, 100.0, 500.0, np.inf),
    "block-year": (0.0, 10.0, 50.0, 200.0, 1000.0, 5000.0, np.inf),
}


@dataclass(eq=False)
class FoldOut:
    pair: str
    scheme: str
    method: str
    test_year: int
    ym: np.ndarray
    obs: np.ndarray  # (months, blocks)
    pred: np.ndarray
    src: np.ndarray
    k: float | None = None
    k_fallback: bool = False
    intervals: dict[str, tuple[np.ndarray, np.ndarray]] = field(default_factory=dict)  # block-month
    year_intervals: dict[str, tuple[np.ndarray, np.ndarray]] = field(default_factory=dict)  # block-year


@dataclass(eq=False)
class PairData:
    ym: np.ndarray
    dates: pd.DatetimeIndex
    month_idx: np.ndarray
    year_idx: np.ndarray
    src: np.ndarray  # (months, blocks, 2)
    tgt: np.ndarray


def pair_data(cube: Cube, pair: Pair, end: int = OVERLAP_END) -> PairData:
    sel = cube.select(pair.src + pair.tgt, pair.start, end)
    return PairData(
        cube.ym[sel],
        cube.dates[sel],
        cube.month_idx[sel],
        cube.year[sel],
        cube.total(pair.src)[sel],
        cube.total(pair.tgt)[sel],
    )


def _folds(scheme: str, dates):
    if scheme == "loyo":
        return leave_one_year_out(dates, GAP_MONTHS)
    if scheme == "rolling":
        return rolling_origin(dates, 1)
    raise ValueError(scheme)


def run_cv(
    cube: Cube,
    pair_name: str,
    scheme: str = "loyo",
    k_grid=K_GRID,
    with_intervals: bool = False,
    with_conformal: bool = False,
    end: int = OVERLAP_END,
) -> list[FoldOut]:
    """Both methods, one fold per test year. Training never includes the test year (nor the gap in `loyo`)."""
    d = pair_data(cube, PAIRS[pair_name], end)
    out: list[FoldOut] = []
    if len(d.ym) == 0:
        return out
    src_tot, tgt_tot = d.src.sum(axis=-1), d.tgt.sum(axis=-1)
    for fold in _folds(scheme, d.dates):
        tr, te = fold.train, fold.test
        if not tr.any() or not te.any():
            continue
        k, fb = select_k(d.src, d.tgt, d.dates, d.month_idx, tr, k_grid, GAP_MONTHS)
        fac = fit_factors(d.src, d.tgt, d.month_idx, tr, k)
        common = dict(pair=pair_name, scheme=scheme, test_year=fold.test_year, ym=d.ym[te], obs=tgt_tot[te])
        sf = FoldOut(
            method="sf",
            pred=predict_total(fac, d.src[te], d.month_idx[te]),
            src=src_tot[te],
            k=k,
            k_fallback=fb,
            **common,
        )
        if with_intervals:
            stack = loyo_factor_stack(d.src, d.tgt, d.dates, d.month_idx, tr, k, GAP_MONTHS)
            sf.intervals["jackknife"] = jackknife_interval(stack, fac, d.src[te], d.month_idx[te])
            sf.intervals["yearly"] = yearly_spread_interval(
                d.src, d.tgt, d.year_idx, d.month_idx, tr, fac, d.src[te], d.month_idx[te]
            )
        if with_conformal:
            cf = conformal_intervals(d.src, d.tgt, d.dates, d.month_idx, tr, k, sf.pred, GAP_MONTHS)
            sf.intervals["conformal"] = cf.month
            sf.year_intervals["conformal"] = cf.year
        out.append(sf)
        qm = fit_block_qmaps(src_tot, tgt_tot, tr)
        out.append(FoldOut(method="qm", pred=qm.apply(src_tot[te]), src=src_tot[te], **common))
    return out


def _block_year_totals(f: FoldOut) -> tuple[np.ndarray, np.ndarray]:
    return f.obs.sum(axis=0), f.pred.sum(axis=0)


def score_table(folds: list[FoldOut]) -> pd.DataFrame:
    """One row per (pair, scheme, method, test_year or 'all', level) with the four metrics."""
    rows = []
    keys = sorted({(f.pair, f.scheme, f.method) for f in folds})
    for pair, scheme, method in keys:
        fs = [f for f in folds if (f.pair, f.scheme, f.method) == (pair, scheme, method)]
        groups = [(f.test_year, [f]) for f in sorted(fs, key=lambda f: f.test_year)] + [("all", fs)]
        for year, group in groups:
            bm_o = np.concatenate([f.obs.ravel() for f in group])
            bm_p = np.concatenate([f.pred.ravel() for f in group])
            by = [_block_year_totals(f) for f in group]
            by_o = np.concatenate([o for o, _ in by])
            by_p = np.concatenate([p for _, p in by])
            for level, o, p in (("block-month", bm_o, bm_p), ("block-year", by_o, by_p)):
                rows.append(
                    {"pair": pair, "scheme": scheme, "method": method, "test_year": year, "level": level}
                    | summarize(o, p)
                    | {"obs_total": float(o.sum()), "n": len(o)}
                )
    return pd.DataFrame(rows)


def _level_arrays(f: FoldOut, name: str, level: str):
    """(lo, hi, obs, pred, active) flat arrays of one fold at a level; None when the interval is absent."""
    if level == "block-month":
        if name not in f.intervals:
            return None
        lo, hi = f.intervals[name]
        obs, pred, src = f.obs, f.pred, f.src
    else:
        if name not in f.year_intervals:
            return None
        lo, hi = f.year_intervals[name]
        obs, pred, src = f.obs.sum(axis=0), f.pred.sum(axis=0), f.src.sum(axis=0)
    active = (obs > 0) | (src > 0)
    return [np.asarray(x).ravel() for x in (lo, hi, obs, pred, active)]


def coverage_table(folds: list[FoldOut], nominal: float = NOMINAL) -> pd.DataFrame:
    """Empirical coverage on active block-months / block-years (source or observed count above zero)."""
    rows = []
    sf = [f for f in folds if f.method == "sf"]
    for level in ("block-month", "block-year"):
        for name in INTERVALS:
            for pair, scheme in sorted({(f.pair, f.scheme) for f in sf if _level_arrays(f, name, level)}):
                fs = sorted(
                    (f for f in sf if (f.pair, f.scheme) == (pair, scheme)), key=lambda f: f.test_year
                )
                fs = [f for f in fs if _level_arrays(f, name, level) is not None]
                tot = {"n": 0, "cov": 0, "width": 0.0, "pred": 0.0, "n0": 0, "cpos": 0, "npos": 0}
                for f in fs:
                    lo, hi, obs, pred, active = _level_arrays(f, name, level)
                    cov = (obs >= lo - 1e-9) & (obs <= hi + 1e-9) & active
                    w, p = float((hi - lo)[active].sum()), float(pred[active].sum())
                    pos = active & (pred > 0)
                    rows.append(
                        {
                            "pair": pair,
                            "scheme": scheme,
                            "interval": name,
                            "level": level,
                            "test_year": f.test_year,
                            "n": int(active.sum()),
                            "coverage": float(cov.sum() / active.sum()) if active.any() else float("nan"),
                            "rel_width": w / p if p > 0 else float("nan"),
                            "n_pred0": int((active & (pred == 0)).sum()),
                            "coverage_pos": float(cov[pos].sum() / pos.sum()) if pos.any() else float("nan"),
                            "nominal": nominal,
                        }
                    )
                    tot["n0"] += int((active & (pred == 0)).sum())
                    tot["cpos"] += int(cov[pos].sum())
                    tot["npos"] += int(pos.sum())
                    tot["n"] += int(active.sum())
                    tot["cov"] += int(cov.sum())
                    tot["width"] += w
                    tot["pred"] += p
                rows.append(
                    {
                        "pair": pair,
                        "scheme": scheme,
                        "interval": name,
                        "level": level,
                        "test_year": "all",
                        "n": tot["n"],
                        "coverage": tot["cov"] / tot["n"] if tot["n"] else float("nan"),
                        "rel_width": tot["width"] / tot["pred"] if tot["pred"] > 0 else float("nan"),
                        "n_pred0": tot["n0"],
                        "coverage_pos": tot["cpos"] / tot["npos"] if tot["npos"] else float("nan"),
                        "nominal": nominal,
                    }
                )
    return pd.DataFrame(rows)


def coverage_by_size(folds: list[FoldOut], name: str = "conformal", scheme: str = "loyo") -> pd.DataFrame:
    """Pooled (all test years) coverage and relative width by predicted-size bin on active rows."""
    rows = []
    for pair in MAIN_PAIRS:
        for level, edges in SIZE_EDGES.items():
            parts = [
                _level_arrays(f, name, level)
                for f in folds
                if f.method == "sf" and (f.pair, f.scheme) == (pair, scheme)
            ]
            parts = [p for p in parts if p is not None]
            if not parts:
                continue
            lo, hi, obs, pred, active = (np.concatenate([p[i] for p in parts]) for i in range(5))
            act = active.astype(bool)
            for a, b in [(-1.0, 0.0)] + list(zip(edges[:-1], edges[1:], strict=True)):
                sel = act & (pred == 0) if b == 0 else act & (pred > a) & (pred <= b)
                n = int(sel.sum())
                cov = (obs >= lo - 1e-9) & (obs <= hi + 1e-9)
                rows.append(
                    {
                        "pair": pair,
                        "level": level,
                        "lo": a,
                        "hi": b,
                        "n": n,
                        "coverage": float(cov[sel].mean()) if n else float("nan"),
                        "rel_width": float((hi - lo)[sel].sum() / pred[sel].sum())
                        if n and pred[sel].sum() > 0
                        else float("nan"),
                    }
                )
    return pd.DataFrame(rows)


def block_detail(folds: list[FoldOut], cube: Cube) -> pd.DataFrame:
    """Per-block scores pooled over the test years (leave-one-year-out, main directions)."""
    lat0, lon0 = block_origin(cube.blocks)
    rows = []
    for pair in MAIN_PAIRS:
        for method in METHODS:
            fs = [f for f in folds if (f.pair, f.scheme, f.method) == (pair, "loyo", method)]
            if not fs:
                continue
            obs = np.concatenate([f.obs for f in fs])
            pred = np.concatenate([f.pred for f in fs])
            by_o = np.stack([f.obs.sum(axis=0) for f in fs])
            by_p = np.stack([f.pred.sum(axis=0) for f in fs])
            for b, blk in enumerate(cube.blocks):
                o, p = obs[:, b], pred[:, b]
                if o.sum() == 0 and p.sum() == 0:
                    continue
                rows.append(
                    {
                        "pair": pair,
                        "method": method,
                        "block": int(blk),
                        "lat_sw": float(lat0[b]),
                        "lon_sw": float(lon0[b]),
                        "obs_total": float(o.sum()),
                        "pred_total": round(float(p.sum()), 1),
                        "rel_bias": round(summarize(o, p)["bias"], 4),
                        "wape_block_month": round(summarize(o, p)["wape"], 4),
                        "wape_block_year": round(summarize(by_o[:, b], by_p[:, b])["wape"], 4),
                    }
                )
    return pd.DataFrame(rows)


def national_factors(cube: Cube) -> pd.DataFrame:
    """In-sample national ratio of sums (target / source) over each pair's valid months."""
    rows = []
    for name, pair in PAIRS.items():
        d = pair_data(cube, pair)
        if len(d.ym) == 0:
            continue
        s, t = d.src.sum(axis=1), d.tgt.sum(axis=1)  # (months, 2)
        rec = {
            "pair": name,
            "from": d.dates[0].strftime("%Y-%m"),
            "to": d.dates[-1].strftime("%Y-%m"),
            "months": len(d.ym),
            "factor": float(t.sum() / s.sum()) if s.sum() > 0 else float("nan"),
            "factor_day": float(t[:, 0].sum() / s[:, 0].sum()) if s[:, 0].sum() > 0 else float("nan"),
            "factor_night": float(t[:, 1].sum() / s[:, 1].sum()) if s[:, 1].sum() > 0 else float("nan"),
        }
        for m in range(12):
            sm = s[d.month_idx == m].sum()
            rec[f"m{m + 1:02d}"] = float(t[d.month_idx == m].sum() / sm) if sm > 0 else float("nan")
        rows.append(rec)
    return pd.DataFrame(rows)
