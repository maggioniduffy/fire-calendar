"""SA2.6 drift diagnostics (rules fixed in plan/02-harmonization.md, P3, P4 and P8, Revision 1).

Pure functions on tables, plus one pass over the detections (mean acquisition time after the default filter
and days with detections before any filter). Nothing here changes a calibration: the outputs are descriptive
and feed the SA2.6 report and the SA2.8 gate.
"""

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from firecal.paths import interim_dir
from firecal.stages.grid.filters import apply_filters
from firecal.stages.grid.grid import detection_files
from firecal.stages.harmonize.evaluate import (
    GAP_MONTHS,
    OVERLAP_END,
    OVERLAP_START,
    PAIRS,
    Pair,
    pair_data,
)
from firecal.stages.harmonize.metrics import summarize
from firecal.stages.harmonize.regions import MODIS_SATS, PARTIAL_MONTHS, Cube, ym_of
from firecal.stages.harmonize.scale_factor import K_GRID, Factors, fit_factors, predict_dn, select_k
from firecal.stages.harmonize.stability import _COLUMNS, _hours

# P3 (with Revision 1): reference years, first evaluated year and threshold.
REF_FIRST, REF_LAST = 2003, 2020
FIRST_EVAL_YEAR = 2021
THRESHOLD_MIN = 15.0
SENSITIVITY_START = 2022  # Terra 2022+ window (Revision 1, P3/P4 sensitivity)
DRIFT_SATS = ("terra", "aqua")
LAST_YEAR = OVERLAP_END // 12
# P8: reference years of the calendar-month median of days with detections, per sensor family.
P8_REF = {"terra": (2003, 2025), "aqua": (2003, 2025), "snpp": (2012, 2025), "noaa20": (2012, 2025)}
P8_RATIO = 0.9

# Pairs of the P4 gate and the satellites whose epochs define their drift years.
GATE_PAIRS = {
    "viirs_to_modis": DRIFT_SATS,
    "modis_to_viirs": DRIFT_SATS,
    "terra_to_viirs": ("terra",),
}


@dataclass
class Epoch:
    sat: str
    reference_hour: float  # unweighted mean of the yearly day means over REF_FIRST..REF_LAST
    offset_min: dict[int, float]  # year -> signed offset in minutes (all years with data)
    start: int | None  # first year >= FIRST_EVAL_YEAR more than THRESHOLD_MIN from the reference


@dataclass
class DetectionStats:
    hours: pd.DataFrame  # year, satellite, daynight, hour (UTC, unrounded)
    days: pd.DataFrame  # satellite, ym, days (days with at least one detection, before filters)


def detection_stats(detections: Path | None = None) -> DetectionStats:
    """One pass over the detection parquets, one year at a time."""
    detections = detections or interim_dir() / "firms" / "detections"
    hour_rows, day_parts = [], []
    for year, files in sorted(detection_files(detections).items()):
        df = pd.concat([pq.read_table(f, columns=_COLUMNS).to_pandas() for f in files], ignore_index=True)
        d = pd.to_datetime(df["acq_date"])
        ym = (d.dt.year * 12 + d.dt.month - 1).to_numpy()
        tmp = pd.DataFrame({"satellite": df["satellite"].to_numpy(), "ym": ym, "acq_date": df["acq_date"]})
        day_parts.append(tmp.groupby(["satellite", "ym"])["acq_date"].nunique().rename("days").reset_index())
        kept = apply_filters(df, None)[0]
        h = _hours(kept)
        for (sat, dn), g in h.groupby([kept["satellite"], kept["daynight"]]):
            hour_rows.append({"year": year, "satellite": sat, "daynight": dn, "hour": float(g.mean()) % 24})
    days = pd.concat(day_parts, ignore_index=True).groupby(["satellite", "ym"], as_index=False)["days"].sum()
    return DetectionStats(pd.DataFrame(hour_rows), days)


def _wrap_min(delta_hours: float) -> float:
    """Signed difference in minutes wrapped to (-12 h, 12 h]."""
    return float(((delta_hours + 12) % 24 - 12) * 60)


def drift_epochs(
    hours: pd.DataFrame,
    sats=DRIFT_SATS,
    ref: tuple[int, int] = (REF_FIRST, REF_LAST),
    first_eval: int = FIRST_EVAL_YEAR,
    threshold_min: float = THRESHOLD_MIN,
) -> dict[str, Epoch]:
    """P3 per satellite on the daytime mean acquisition time.

    Reference = unweighted mean of the yearly means over `ref`. Only years >= `first_eval` are tested (an
    earlier outlier, e.g. 2000, can never start the epoch); the epoch starts at the first tested year more
    than `threshold_min` minutes from the reference and includes every later year.
    """
    out = {}
    day = hours[hours["daynight"] == "D"]
    for sat in sats:
        s = day[day["satellite"] == sat].set_index("year")["hour"].sort_index()
        r = s[(s.index >= ref[0]) & (s.index <= ref[1])]
        if r.empty:
            out[sat] = Epoch(sat, float("nan"), {}, None)
            continue
        ref_h = float(r.mean())
        offs = {int(y): _wrap_min(float(h) - ref_h) for y, h in s.items()}
        flagged = [y for y, m in sorted(offs.items()) if y >= first_eval and abs(m) > threshold_min]
        out[sat] = Epoch(sat, ref_h, offs, flagged[0] if flagged else None)
    return out


def drift_start(epochs: dict[str, Epoch], sats) -> int | None:
    """First drift year of a pair: the earliest start among the satellites involved (union of the epochs)."""
    starts = [epochs[s].start for s in sats if s in epochs and epochs[s].start is not None]
    return min(starts) if starts else None


def window_years(start: int | None, last: int = LAST_YEAR) -> tuple[int, ...]:
    return tuple(range(start, last + 1)) if start is not None else ()


def pair_windows(epochs: dict[str, Epoch]) -> dict[str, dict[str, tuple[int, ...]]]:
    """Per gate pair: the main drift window (P3) and the Terra 2022+ sensitivity window."""
    out = {}
    for pair, sats in GATE_PAIRS.items():
        main = drift_start(epochs, sats)
        sens_starts = [SENSITIVITY_START] + (
            [epochs["aqua"].start] if "aqua" in sats and epochs["aqua"].start else []
        )
        out[pair] = {
            "main": window_years(main),
            "sensitivity": window_years(min(sens_starts)),
        }
    return out


def train_mask(
    year_idx: np.ndarray, ym: np.ndarray, first_ym: int, last_ym: int, drop_years=()
) -> np.ndarray:
    """Training rows: months in [first_ym, last_ym] whose year is not in `drop_years`."""
    m = (ym >= first_ym) & (ym <= last_ym)
    if len(drop_years):
        m &= ~np.isin(year_idx, list(drop_years))
    return m


# ---------------------------------------------------------------------------------------------------- ratios


def ratio_tables(cube: Cube) -> dict[str, pd.DataFrame]:
    """Yearly national ratios over S-NPP (Terra, Aqua, MODIS) and the NOAA-20 control."""
    from firecal.stages.harmonize.stability import ratio_by_year

    out = {}
    for name, num in (("terra", ("terra",)), ("aqua", ("aqua",)), ("modis", MODIS_SATS)):
        out[name] = ratio_by_year(cube, num, ("snpp",), 2012)
    out["noaa20"] = ratio_by_year(cube, ("noaa20",), ("snpp",), 2018)
    return out


# ---------------------------------------------------------------------------------------------------- placebo

PLACEBO_COMPONENTS = ("total", "day", "night", "terra", "aqua")


def _component_ratio(cube: Cube, sel: np.ndarray) -> dict[str, float]:
    s = cube.total(("snpp",))[sel]
    m = cube.total(MODIS_SATS)[sel]
    t = cube.data["terra"][sel]
    a = cube.data["aqua"][sel]
    sd, sn = s[..., 0].sum(), s[..., 1].sum()
    return {
        "total": float(m.sum() / s.sum()) if s.sum() > 0 else float("nan"),
        "day": float(m[..., 0].sum() / sd) if sd > 0 else float("nan"),
        "night": float(m[..., 1].sum() / sn) if sn > 0 else float("nan"),
        "terra": float(t.sum() / s.sum()) if s.sum() > 0 else float("nan"),
        "aqua": float(a.sum() / s.sum()) if s.sum() > 0 else float("nan"),
    }


def placebo_table(
    cube: Cube, drift_years: tuple[int, ...], first_year: int = 2012, last_year: int = LAST_YEAR
):
    """National factor (MODIS-type target / S-NPP, ratio of sums) moved by dropping a window of years.

    Rows: the drift window and every other contiguous window of the same length inside first_year..last_year
    whose years do not overlap the drift window. Months: 2012-02..2025-12 valid for S-NPP, Terra and Aqua.
    Returns (table, baseline) where the table has `shift_<component>` = factor without the window / factor
    with all months - 1.
    """
    if not drift_years:
        return pd.DataFrame(), {}
    sel = cube.select(("snpp", "terra", "aqua"), OVERLAP_START, OVERLAP_END)
    years = cube.year
    base = _component_ratio(cube, sel)
    length = len(drift_years)
    wins = [("drift", tuple(drift_years))]
    for y in range(first_year, last_year - length + 2):
        w = tuple(range(y, y + length))
        if set(w) & set(drift_years):
            continue
        wins.append(("placebo", w))
    rows = []
    for kind, w in wins:
        keep = sel & ~np.isin(years, list(w))
        f = _component_ratio(cube, keep)
        rec = {
            "kind": kind,
            "window": f"{w[0]}-{w[-1]}",
            "months_dropped": int((sel & np.isin(years, list(w))).sum()),
        }
        for c in PLACEBO_COMPONENTS:
            rec[f"shift_{c}"] = f[c] / base[c] - 1 if np.isfinite(base[c]) and base[c] != 0 else float("nan")
        rows.append(rec)
    return pd.DataFrame(rows), base


# ------------------------------------------------------------------------------------- factors with / without


@dataclass
class VariantFit:
    label: str
    k: float
    k_fallback: bool
    factors: Factors
    n_train_months: int


@dataclass
class FactorComparison:
    pair: str
    drop_years: tuple[int, ...]
    with_: VariantFit
    without: VariantFit
    national: dict[str, dict[str, float]]  # variant -> {total, day, night} effective factor
    blocks: pd.DataFrame = field(default_factory=pd.DataFrame)


def fit_variant(d, train: np.ndarray, label: str) -> VariantFit:
    k, fb = select_k(d.src, d.tgt, d.dates, d.month_idx, train, K_GRID, GAP_MONTHS)
    fac = fit_factors(d.src, d.tgt, d.month_idx, train, k)
    return VariantFit(label, k, fb, fac, int(train.sum()))


def _effective(fac: Factors, d, rows: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Effective factor per (block) and national (total, day, night): sum(f * S) / sum(S) over `rows`."""
    sel = np.ones(len(d.ym), dtype=bool) if rows is None else rows
    pred = predict_dn(fac, d.src[sel], d.month_idx[sel])  # (rows, blocks, 2)
    src = d.src[sel]
    return pred, src


def compare_factors(cube: Cube, pair_name: str, drop_years: tuple[int, ...]) -> FactorComparison:
    """SA2.2 factors fitted on all overlap months vs without the drift years (k selected inside training)."""
    d = pair_data(cube, PAIRS[pair_name])
    all_rows = np.ones(len(d.ym), dtype=bool)
    tr_with = all_rows
    tr_without = ~np.isin(d.year_idx, list(drop_years))
    a = fit_variant(d, tr_with, "with drift years")
    b = fit_variant(d, tr_without, "without drift years")
    nat: dict[str, dict[str, float]] = {}
    per_block = {}
    for v in (a, b):
        pred, src = _effective(v.factors, d)
        p_dn, s_dn = pred.sum(axis=(0, 1)), src.sum(axis=(0, 1))
        nat[v.label] = {
            "total": float(p_dn.sum() / s_dn.sum()),
            "day": float(p_dn[0] / s_dn[0]),
            "night": float(p_dn[1] / s_dn[1]),
        }
        per_block[v.label] = (pred.sum(axis=(0, 2)), src.sum(axis=(0, 2)))
    s_b = per_block[a.label][1]
    f_a = np.where(s_b > 0, per_block[a.label][0] / np.where(s_b > 0, s_b, 1), np.nan)
    f_b = np.where(s_b > 0, per_block[b.label][0] / np.where(s_b > 0, s_b, 1), np.nan)
    blocks = pd.DataFrame(
        {
            "block": cube.blocks,
            "source_total": s_b,
            "factor_with": f_a,
            "factor_without": f_b,
            "rel_change": np.where(f_a > 0, f_b / np.where(f_a > 0, f_a, 1) - 1, np.nan),
        }
    )
    blocks = blocks[blocks["source_total"] > 0].reset_index(drop=True)
    return FactorComparison(pair_name, tuple(drop_years), a, b, nat, blocks)


# ---------------------------------------------------------------- observed MODIS vs VIIRS-derived MODIS-eq

HOLDOUT_FIT_END = ym_of(2021, 12)
HOLDOUT_YEARS = (2022, 2023, 2024, 2025)
HOLDOUT_TARGETS = {
    "MODIS (Terra + Aqua)": MODIS_SATS,
    "Terra": ("terra",),
    "Aqua": ("aqua",),
}


def holdout_compare(cube: Cube, tgt: tuple[str, ...]) -> dict:
    """Factor fitted on 2012-02..2021-12 (S-NPP -> target) applied to S-NPP 2022-2025, vs observed."""
    pair = Pair(("snpp",), tgt, OVERLAP_START)
    d = pair_data(cube, pair)
    tr = d.ym <= HOLDOUT_FIT_END
    k, fb = select_k(d.src, d.tgt, d.dates, d.month_idx, tr, K_GRID, GAP_MONTHS)
    fac = fit_factors(d.src, d.tgt, d.month_idx, tr, k)
    te = d.year_idx >= HOLDOUT_YEARS[0]
    pred = predict_dn(fac, d.src[te], d.month_idx[te]).sum(axis=-1)  # (months, blocks)
    obs = d.tgt[te].sum(axis=-1)
    yrs = d.year_idx[te]
    rows, block_rows = [], []
    for y in HOLDOUT_YEARS:
        m = yrs == y
        if not m.any():
            continue
        o, p = obs[m], pred[m]
        sbm, sby = summarize(o, p), summarize(o.sum(axis=0), p.sum(axis=0))
        rows.append(
            {
                "year": y,
                "months": int(m.sum()),
                "obs": float(o.sum()),
                "pred": float(p.sum()),
                "bias": sbm["bias"],
                "wape_block_month": sbm["wape"],
                "wape_block_year": sby["wape"],
            }
        )
        for b, blk in enumerate(cube.blocks):
            ob, pb = o[:, b].sum(), p[:, b].sum()
            if ob > 0 or pb > 0:
                block_rows.append({"year": y, "block": int(blk), "obs": float(ob), "pred": float(pb)})
    return {
        "k": k,
        "k_fallback": fb,
        "fit_months": int(tr.sum()),
        "years": pd.DataFrame(rows),
        "blocks": pd.DataFrame(block_rows),
    }


# ---------------------------------------------------------------------------------------------------- P8


def completeness_table(
    days: pd.DataFrame, first_year: int = 2000, last_year: int = LAST_YEAR
) -> pd.DataFrame:
    """Satellite-months with days-with-detections below 90 % of the calendar-month median (diagnostic only).

    Median per satellite and calendar month over the sensor's P8 reference years; the first partial month of a
    record (`PARTIAL_MONTHS`) is out of the median. Months inside a satellite's record with no detection
    at all count as 0 days.
    """
    rows = []
    for sat in P8_REF:
        d = days[days["satellite"] == sat]
        if d.empty:
            continue
        full = pd.DataFrame({"ym": np.arange(int(d["ym"].min()), int(d["ym"].max()) + 1)})
        full = full.merge(d[["ym", "days"]], on="ym", how="left").fillna({"days": 0})
        full["year"] = full["ym"] // 12
        full["month"] = full["ym"] % 12 + 1
        partial = {ym_of(y, m) for y, m in PARTIAL_MONTHS.get(sat, ())}
        r0, r1 = P8_REF[sat]
        ref = full[(full["year"] >= r0) & (full["year"] <= r1) & ~full["ym"].isin(partial)]
        med = ref.groupby("month")["days"].median()
        full["median"] = full["month"].map(med)
        full["ratio"] = full["days"] / full["median"]
        full["satellite"] = sat
        full["known_partial_first_month"] = full["ym"].isin(partial)
        rows.append(full[(full["year"] >= first_year) & (full["year"] <= last_year)])
    allm = pd.concat(rows, ignore_index=True)
    allm["flagged"] = allm["days"] < P8_RATIO * allm["median"]
    return allm


# ------------------------------------------------------------------------------------- orchestration

WINDOW_KINDS = {"main": "P3 epoch", "sensitivity": "Terra 2022+ sensitivity"}


def window_keys(wins: dict[str, dict[str, tuple[int, ...]]]) -> dict[str, tuple[str, tuple[int, ...]]]:
    """key -> (pair, drift years) for every gate pair and window kind."""
    return {
        f"{pair} ({WINDOW_KINDS[kind]})": (pair, years)
        for pair, kinds in wins.items()
        for kind, years in kinds.items()
    }


def _label(years: tuple[int, ...]) -> str:
    return f"{years[0]}-{years[-1]}" if years else "none"


def run_drift() -> dict:
    """Everything the SA2.6 report needs (real data under data/)."""
    from firecal.stages.harmonize.regions import build_cube, build_monthly_region_table

    cube = build_cube(build_monthly_region_table())
    stats = detection_stats()
    epochs = drift_epochs(stats.hours)
    wins = pair_windows(epochs)
    keys = window_keys(wins)
    # One placebo table per distinct drift window (modis_to_viirs is the reciprocal of viirs_to_modis;
    # the Terra window equals the MODIS-union window when Aqua starts later than Terra).
    by_years: dict[tuple[int, ...], list[str]] = {}
    for key, (_, years) in keys.items():
        by_years.setdefault(years, []).append(key)
    placebo: dict = {}
    for years, ks in by_years.items():
        tab, base = placebo_table(cube, years)
        placebo[f"window {_label(years)} (used by: {'; '.join(ks)})"] = (tab, base, years)
    comps = {key: compare_factors(cube, pair, years) for key, (pair, years) in keys.items() if years}
    window_label = {key: _label(years) for key, (_, years) in keys.items()}
    hold = {label: holdout_compare(cube, tgt) for label, tgt in HOLDOUT_TARGETS.items()}
    p8 = completeness_table(stats.days)
    blocks = pd.concat(
        [c.blocks.assign(case=key, drop_years=_label(c.drop_years)) for key, c in comps.items()],
        ignore_index=True,
    )
    report_args = {
        "stats": stats,
        "epochs": epochs,
        "ratios": ratio_tables(cube),
        "placebo": placebo,
        "comps": comps,
        "window_label": window_label,
        "hold": hold,
        "cube": cube,
        "p8": p8,
        "p8_note": "detection parquets (country files) before any filter",
    }
    return {"report_args": report_args, "epochs": epochs, "blocks_csv": blocks}
