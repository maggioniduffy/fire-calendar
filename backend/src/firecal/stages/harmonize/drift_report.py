# ruff: noqa: E501
"""Markdown report SA2.6 (Terra/Aqua orbital drift diagnostics); every number comes from code."""

import datetime as dt

import numpy as np
import pandas as pd

from firecal.stages.harmonize.drift import (
    P8_RATIO,
    P8_REF,
    PLACEBO_COMPONENTS,
    THRESHOLD_MIN,
    DetectionStats,
    Epoch,
    FactorComparison,
)
from firecal.stages.harmonize.regions import Cube, block_origin
from firecal.stages.harmonize.report import hhmm, md_table, num, pct

SATS = ("terra", "aqua", "snpp", "noaa20")
SAT_NAME = {"terra": "Terra", "aqua": "Aqua", "snpp": "S-NPP", "noaa20": "NOAA-20"}
SRC = "FIRMS per-country files (Argentina) 2000-2025, default `FilterConfig`, 0.1 degree grid; code `harmonize/drift.py`"
FLAG = "orbit drift (unverified cause)"


def _yrs(w: tuple[int, ...]) -> str:
    return f"{w[0]}-{w[-1]}" if w else "none"


def _hours_section(stats: DetectionStats, epochs: dict[str, Epoch]) -> list[str]:
    h = stats.hours
    years = sorted(h["year"].unique())
    out = [
        "## 1. Mean acquisition time (UTC) and the drift epoch (P3)",
        "",
        f"Source: {SRC}. Period 2000-2025. Detections after the default filter; night hours after 12:00 averaged as negative hours.",
        "",
        "P3 rule (Revision 1): per satellite, the daytime mean acquisition time per year; reference = unweighted mean of the yearly means 2003-2020; "
        f"only years >= 2021 are tested; the epoch starts at the first tested year more than {THRESHOLD_MIN:g} minutes from the reference and includes every later year. "
        "Offsets of S-NPP and NOAA-20 are not defined by P3 (no reference): their times are a control.",
        "",
    ]
    ref_rows = [
        [SAT_NAME[s], hhmm(e.reference_hour), e.start if e.start else "none"] for s, e in epochs.items()
    ]
    out += md_table(["Satellite", "P3 reference (day, UTC)", "Drift epoch starts"], ref_rows)
    out += [
        "",
        "Per year, mean time (UTC) and, for Terra and Aqua daytime, the offset from the P3 reference in minutes (`*` = in the drift epoch, `>` = more than 15 min).",
        "",
    ]
    rows = []
    idx = h.set_index(["year", "satellite", "daynight"])["hour"]
    for y in years:
        r: list = [y]
        for s in SATS:
            for dn in ("D", "N"):
                v = idx.get((y, s, dn), np.nan)
                cell = hhmm(v)
                if dn == "D" and s in epochs and y in epochs[s].offset_min:
                    off = epochs[s].offset_min[y]
                    mark = "*" if epochs[s].start and y >= epochs[s].start else ""
                    cell += f" ({off:+.1f}{'>' if abs(off) > THRESHOLD_MIN and y >= 2021 else ''}){mark}"
                r.append(cell)
        rows.append(r)
    out += md_table(["Year"] + [f"{SAT_NAME[s]} {dn}" for s in SATS for dn in ("D", "N")], rows)
    out += [
        "",
        "Terra 2022+ sensitivity window (Revision 1): Terra 2022 is on the edge of the rule. Offsets in minutes (unrounded):",
        "",
    ]
    t = epochs["terra"].offset_min
    out += md_table(
        ["Year", "Terra D offset (min)", "Aqua D offset (min)"],
        [
            [y, f"{t.get(y, np.nan):+.2f}", f"{epochs['aqua'].offset_min.get(y, np.nan):+.2f}"]
            for y in range(2019, 2026)
        ],
    )
    return out


def _ratio_section(ratios: dict[str, pd.DataFrame]) -> list[str]:
    out = [
        "",
        "## 2. Yearly ratios over S-NPP",
        "",
        f'Source: monthly region cube from the 0.1 degree grid, national sums over months valid for both sensors. Period 2012-02..2025-12 (NOAA-20 control 2018-05..2025-12). Observed MODIS in 2022+ is flagged "{FLAG}".',
        "",
    ]
    names = {
        "terra": "Terra / S-NPP",
        "aqua": "Aqua / S-NPP",
        "modis": "MODIS (Terra+Aqua) / S-NPP",
        "noaa20": "NOAA-20 / S-NPP (control, no MODIS)",
    }
    years = sorted({int(y) for df in ratios.values() for y in df["year"]})
    rows = []
    for y in years:
        r: list = [y]
        for k in names:
            df = ratios[k]
            m = df[df["year"] == y]
            for c in ("ratio", "ratio_day", "ratio_night"):
                r.append(num(float(m[c].iloc[0]), 3) if len(m) else "-")
        r.append(FLAG if y >= 2022 else "")
        rows.append(r)
    hdr = (
        ["Year"]
        + [f"{n} {c}" for n in names.values() for c in ("total", "day", "night")]
        + ["Note (observed MODIS)"]
    )
    out += md_table(hdr, rows)
    return out


def _placebo_section(placebo: dict[str, tuple[pd.DataFrame, dict, tuple[int, ...]]]) -> list[str]:
    out = [
        "",
        "## 3. P4 condition 1, placebo windows (descriptive only, it does not gate)",
        "",
        "Source: monthly region cube, national ratio of sums (MODIS-type target / S-NPP, day and night summed), months 2012-02..2025-12 valid for S-NPP, Terra and Aqua. "
        "Cells: relative change of the national factor when the window's months are dropped, `factor_without / factor_all - 1`. Windows overlapping the drift window are excluded from the placebos.",
        "",
    ]
    for label, (tab, base, years) in placebo.items():
        out += [f"### {label}: drift window {_yrs(years)}", ""]
        if tab.empty:
            out += ["No drift window under P3: nothing to compare.", ""]
            continue
        out += [
            "National factor with all months: "
            + ", ".join(f"{c} {num(base[c], 4)}" for c in PLACEBO_COMPONENTS)
            + ".",
            "",
        ]
        rows = []
        for _, r in tab.iterrows():
            rows.append(
                [("**drift** " if r["kind"] == "drift" else "") + r["window"], r["months_dropped"]]
                + [pct(r[f"shift_{c}"], True) for c in PLACEBO_COMPONENTS]
            )
        out += md_table(["Window dropped", "Months"] + list(PLACEBO_COMPONENTS), rows)
        pl = tab[tab["kind"] == "placebo"]
        dr = tab[tab["kind"] == "drift"].iloc[0]
        out += [""]
        for c in PLACEBO_COMPONENTS:
            n_more = int((pl[f"shift_{c}"].abs() > abs(dr[f"shift_{c}"])).sum())
            out.append(
                f"- {c}: the drift window moves the factor by {pct(dr[f'shift_{c}'], True)}; {n_more} of {len(pl)} placebo windows move it more in absolute value."
            )
        out += [""]
    return out


def _factors_section(comps: dict[str, FactorComparison], window_label: dict[str, str]) -> list[str]:
    out = [
        "",
        "## 4. Block factors fitted with vs without the drift years",
        "",
        "Source: SA2.2 estimator (`scale_factor.fit_factors`, `k` selected inside the training set by `select_k` with the inner leave-one-year-out and a 6-month gap). "
        "Period: overlap months 2012-02..2025-12; the 'without' fit drops the months of the drift years of the pair. "
        "The effective factor is `sum(f * S) / sum(S)` over the same source months for both fits, so any difference comes from the factors only. "
        "Block rows: blocks with source detections > 0 over the overlap; the relative change is of the block's effective factor. Descriptive; nothing is recalibrated.",
        "",
    ]
    for key, c in comps.items():
        out += [f"### {key}: drift window {window_label[key]}", ""]
        if not c.drop_years:
            out += ["No drift window: not fitted.", ""]
            continue
        a, b = c.with_, c.without
        rows = []
        for comp in ("total", "day", "night"):
            fa, fb = c.national[a.label][comp], c.national[b.label][comp]
            rows.append([comp, num(fa, 4), num(fb, 4), pct(fb / fa - 1, True)])
        out += [
            f"Fitted months: with {a.n_train_months}, without {b.n_train_months}. `k`: with {a.k:g}{' (fallback)' if a.k_fallback else ''}, without {b.k:g}{' (fallback)' if b.k_fallback else ''}.",
            "",
        ]
        out += md_table(["National effective factor", "With drift years", "Without", "Change"], rows)
        bl = c.blocks.dropna(subset=["rel_change"])
        w = bl["source_total"].to_numpy()
        rc = bl["rel_change"].to_numpy()
        q = np.percentile(rc, [10, 50, 90]) if len(rc) else [np.nan] * 3
        wm = float(np.average(rc, weights=w)) if len(rc) and w.sum() > 0 else float("nan")
        out += [
            "",
            f"Blocks: {len(bl)}. Relative change of the block effective factor: unweighted p10 {pct(q[0], True)}, median {pct(q[1], True)}, p90 {pct(q[2], True)}, "
            f"min {pct(rc.min(), True) if len(rc) else '-'}, max {pct(rc.max(), True) if len(rc) else '-'}; weighted by source detections {pct(wm, True)}.",
            "",
        ]
        top = bl.sort_values("source_total", ascending=False).head(10)
        lat, lon = block_origin(top["block"].to_numpy())
        out += md_table(
            ["Block (SW lat, lon)", "Source detections", "Factor with", "Factor without", "Change"],
            [
                [f"{int(b)} ({la:.1f}, {lo:.1f})", int(s), num(fa, 4), num(fb, 4), pct(ch, True)]
                for b, la, lo, s, fa, fb, ch in zip(
                    top["block"],
                    lat,
                    lon,
                    top["source_total"],
                    top["factor_with"],
                    top["factor_without"],
                    top["rel_change"],
                    strict=True,
                )
            ],
        )
        out += [""]
    return out


def _holdout_section(hold: dict[str, dict], cube: Cube) -> list[str]:
    out = [
        "## 5. Observed MODIS vs VIIRS-derived MODIS-eq, 2022-2025 (association, not cause)",
        "",
        f"Source: S-NPP -> target SA2.2 factor fitted on 2012-02..2021-12 (`k` selected inside that training set) and applied unchanged to S-NPP 2022-2025, against the observed counts. Same count definition as the calendar (default filters, 0.1 degree grid). "
        f'The observed MODIS of 2022+ is flagged "{FLAG}": a gap between the two can come from the drift, from the S-NPP side or from the factor, and this table does not separate them.',
        "",
    ]
    for label, h in hold.items():
        out += [
            f"### {label}",
            "",
            f"`k` = {h['k']:g}{' (fallback)' if h['k_fallback'] else ''}; fitted on {h['fit_months']} months.",
            "",
        ]
        y = h["years"]
        out += md_table(
            [
                "Year",
                "Observed",
                "VIIRS-derived (eq.)",
                "Relative bias",
                "WAPE block-month",
                "WAPE block-year",
                "Note",
            ],
            [
                [
                    int(r.year),
                    int(r.obs),
                    int(round(r.pred)),
                    pct(r.bias, True),
                    pct(r.wape_block_month),
                    pct(r.wape_block_year),
                    FLAG,
                ]
                for r in y.itertuples()
            ],
        )
        out += [""]
    # Per block for the MODIS target.
    h = hold["MODIS (Terra + Aqua)"]
    b = h["blocks"]
    if not b.empty:
        piv_o = b.pivot_table(index="block", columns="year", values="obs", aggfunc="sum", fill_value=0)
        piv_p = b.pivot_table(index="block", columns="year", values="pred", aggfunc="sum", fill_value=0)
        tot = piv_o.sum(axis=1).sort_values(ascending=False)
        yrs = list(piv_o.columns)
        rows = []
        lat, lon = block_origin(tot.head(15).index.to_numpy())
        for (blk, t), la, lo in zip(tot.head(15).items(), lat, lon, strict=True):
            r = [f"{int(blk)} ({la:.1f}, {lo:.1f})", int(t)]
            for yy in yrs:
                o, p = piv_o.loc[blk, yy], piv_p.loc[blk, yy]
                r.append(pct(p / o - 1, True) if o > 0 else "-")
            rows.append(r)
        out += [
            "### Per block, MODIS target: the 15 blocks with most observed detections in 2022-2025",
            "",
            "Cells: block-year relative bias (derived / observed - 1).",
            "",
        ]
        out += md_table(["Block (SW lat, lon)", "Observed 2022-2025"] + [str(y) for y in yrs], rows)
        out += [""]
        for yy in yrs:
            o, p = piv_o[yy], piv_p[yy]
            m = o > 0
            rb = (p[m] / o[m] - 1).to_numpy()
            q = np.percentile(rb, [10, 50, 90])
            out.append(
                f"- {yy}: {int(m.sum())} blocks with observed detections; block-year relative bias p10 {pct(q[0], True)}, median {pct(q[1], True)}, p90 {pct(q[2], True)} (unweighted)."
            )
        out += [""]
    return out


def _p8_section(tab: pd.DataFrame, note: str) -> list[str]:
    flagged = tab[tab["flagged"]].sort_values(["satellite", "ym"])
    out = [
        "## 6. P8 diagnostic: days with detections per satellite-month (diagnostic only, changes nothing)",
        "",
        f"Source: {note}. Period 2000-2025. Days with at least one detection in the satellite-month, compared with {int(P8_RATIO * 100)} % of the median of the same calendar month over "
        + "; ".join(f"{SAT_NAME[s]} {a}-{b}" for s, (a, b) in P8_REF.items())
        + ". The first partial month of a record (`PARTIAL_MONTHS`) is out of the median. The series and the fits are not changed by this table.",
        "",
        f"Satellite-months examined: {len(tab)}; flagged: {len(flagged)}.",
        "",
    ]
    sat_cnt = tab.groupby("satellite")["flagged"].agg(["sum", "count"])
    out += md_table(
        ["Satellite", "Months", "Flagged"],
        [[SAT_NAME[s], int(r["count"]), int(r["sum"])] for s, r in sat_cnt.iterrows()],
    )
    out += [""]
    rows = []
    for r in flagged.itertuples():
        rows.append(
            [
                SAT_NAME[r.satellite],
                f"{r.year}-{r.month:02d}",
                int(r.days),
                num(r.median, 1),
                pct(r.ratio),
                "known partial first month" if r.known_partial_first_month else "",
            ]
        )
    out += md_table(
        ["Satellite", "Month", "Days with detections", "Calendar-month median", "Ratio", "Note"], rows
    )
    return out


def build_sa26_report(
    *,
    stats: DetectionStats,
    epochs: dict[str, Epoch],
    ratios: dict[str, pd.DataFrame],
    placebo: dict,
    comps: dict[str, FactorComparison],
    window_label: dict[str, str],
    hold: dict[str, dict],
    cube: Cube,
    p8: pd.DataFrame,
    p8_note: str,
    run_date: dt.date,
) -> str:
    head = [
        "# SA2.6: Terra and Aqua orbital drift diagnostics",
        "",
        f"Generated by `firecal harmonize drift` on {run_date.isoformat()}. All numbers come from code; prose is fixed. Rules: P3, P4 and P8 of `plan/02-harmonization.md` (pre-registration and Revision 1). "
        "This report is descriptive: the only decision it feeds is the P4 gate, which is in `reports/02/SA2.8.md`. The cause of the drift is unverified here (an association between acquisition time and the ratios is not a cause).",
        "",
        f"Drift epochs found (P3): Terra {epochs['terra'].start or 'none'}+, Aqua {epochs['aqua'].start or 'none'}+. "
        + " ".join(f"{k}: window {v}." for k, v in window_label.items()),
        "",
    ]
    out = head + _hours_section(stats, epochs) + _ratio_section(ratios) + _placebo_section(placebo)
    out += _factors_section(comps, window_label) + _holdout_section(hold, cube) + _p8_section(p8, p8_note)
    return "\n".join(out) + "\n"
