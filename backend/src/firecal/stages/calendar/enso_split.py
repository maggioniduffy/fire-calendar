"""Hot-spot calendar split by ENSO phase (SA5.2). Association, not cause; retrospective, not an alert."""

import numpy as np
import pandas as pd

from firecal.io import enso as enso_io
from firecal.stages.calendar.climatology import QUANTILE_METHOD
from firecal.stages.calendar.store import YM

PHASES = ("nino", "nina", "neutral")
NOTE_ES = "Asociación, no causa. Retrospectivo; no es un sistema de alerta."
NOTE_EN = "Association, not cause. Retrospective; not an alert system."


def phase_by_month(enso_df: pd.DataFrame, start: YM, end: YM) -> pd.DataFrame:
    """ONI and phase per (year, month) inside [start, end]; months outside the ONI range or without ONI drop.

    `enso_df` has the columns date (month start), oni and phase (see `firecal.io.enso`).
    """
    d = pd.DatetimeIndex(enso_df["date"])
    out = pd.DataFrame(
        {
            "year": d.year.astype("int64"),
            "month": d.month.astype("int64"),
            "oni": enso_df["oni"].to_numpy(dtype=float),
            "phase": enso_df["phase"].astype(str).to_numpy(),
        }
    )
    ym = out["year"] * 12 + out["month"] - 1
    keep = (ym >= start[0] * 12 + start[1] - 1) & (ym <= end[0] * 12 + end[1] - 1) & out["oni"].notna()
    return out[keep].sort_values(["year", "month"]).reset_index(drop=True)


def split_by_phase(matrix: pd.DataFrame, column: str, phases: pd.DataFrame) -> pd.DataFrame:
    """Per (calendar month, phase): n_years, median, p25, p75 and the years, over months with a value.

    `phases` is the output of `phase_by_month`. Quantiles use numpy linear interpolation (`QUANTILE_METHOD`).
    Groups with no values are left out; `n_years < 3` stays (the UI marks it as "few years").
    """
    merged = matrix[["year", "month", column]].merge(phases[["year", "month", "phase"]], on=["year", "month"])
    merged = merged[merged[column].notna()]
    rows = []
    for (month, phase), g in merged.groupby(["month", "phase"]):
        v = g[column].to_numpy(dtype=float)
        q = np.quantile(v, [0.5, 0.25, 0.75], method="linear")
        rows.append(
            {
                "month": int(month),
                "phase": str(phase),
                "n_years": len(v),
                "median": float(q[0]),
                "p25": float(q[1]),
                "p75": float(q[2]),
                "years": sorted(int(y) for y in g["year"]),
            }
        )
    cols = ["month", "phase", "n_years", "median", "p25", "p75", "years"]
    out = pd.DataFrame(rows, columns=cols)
    if len(out):
        out["_p"] = out["phase"].map({p: i for i, p in enumerate(PHASES)})
        out = out.sort_values(["month", "_p"]).drop(columns="_p").reset_index(drop=True)
    return out


def enso_block(enso_df: pd.DataFrame, matrix: pd.DataFrame, column: str, start: YM, end: YM) -> dict:
    """The `enso` block of the /calendar payload (rows are still pandas; the caller cleans them)."""
    phases = phase_by_month(enso_df, start, end)
    dates = pd.DatetimeIndex(enso_df["date"])
    months = phases.assign(ym=phases["year"].astype(str) + "-" + phases["month"].astype(str).str.zfill(2))
    return {
        "source": enso_io.SOURCE,
        "url": enso_io.ONI_URL,
        "definition": enso_io.DEFINITION,
        "period": {
            "start": f"{dates.min():%Y-%m}" if len(dates) else None,
            "end": f"{dates.max():%Y-%m}" if len(dates) else None,
        },
        "months": months[["ym", "oni", "phase"]],
        "by_phase": split_by_phase(matrix, column, phases),
        "quantile_method": QUANTILE_METHOD,
        "note_es": NOTE_ES,
        "note_en": NOTE_EN,
    }
