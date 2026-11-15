"""reports/02/SA2.10.md from code: P1 headline first, then tables, deviations and what stays unverified."""

import datetime as dt

import numpy as np
import pandas as pd

from firecal.stages.harmonize.continuity import (
    LAST_FULL_YEAR,
    LOYO_SPLIT,
    ROUTE_LABEL,
    ROUTES,
    Continuity,
    coverage_label,
    cutoff_year_table,
    horizon_table,
    horizon_within_year,
    loyo_table,
    loyo_year_table,
    partial_block_table,
    score,
    secondary_flagged,
    select,
)
from firecal.stages.harmonize.report import md_table, num, pct

CALIBRATION_BASE = "sf-2026.11.1"
CALIBRATION_NEW = "sf-2026.11.2"

DEVIATIONS = [
    (
        "2026-11-15",
        "The block-year band of the frozen calibration (calibrated on 12-month sums) is applied in P9 to a "
        "partial sum of 4 or 6 months.",
        "Only complete satellite-months exist for 2026 (P8); the coverage of the block-year band on partial "
        "years is unverified.",
    ),
    (
        "2026-11-15",
        "NOAA-21 pairs: the S-NPP / NOAA-20 side of 2023-2025 comes from the FIRMS country files and 2026 "
        "from the "
        "area API, not both sides from the same API path as written in step 3 of the completion plan.",
        "P7 passed (`reports/01/SA1.6_clip.md`): the API-SP 2025 clip matches the country files for S-NPP "
        "and "
        "NOAA-20 within tolerance. NOAA-21 has no country files (all of it is API, SP), so its clip stays "
        "unverified.",
    ),
    (
        "2026-11-15",
        "The direct route's conformal residuals re-select `k` inside every inner fold (as the chain's "
        "legs do), "
        "instead of reusing the outer fold's `k` as `fit_calibration` does for the older pairs.",
        "Revision 1 P5 asks for every factor of the route out-of-fold with its own `k`; chain and direct "
        "are then "
        "treated alike. The older pairs of `.1` are untouched.",
    ),
    (
        "2026-11-15",
        "The 2026 block (P2) and the frozen-artifact check (P9) score the complete satellite-months only "
        "(P8), "
        "which for the NOAA-20 -> MODIS route are 2026-01..04 (Terra is partial in 2026-05, -06 and -07) "
        "and for "
        "NOAA-20 -> S-NPP 2026-01..06 (S-NPP is partial in 2026-07), not 2026-01..07.",
        "P8 gates the satellite-months from 2026-01 on; no month was substituted.",
    ),
    (
        "2026-11-15",
        "The paired bootstrap resamples the rows of the (cut-off x test-year) block-year matrix and the "
        "blocks "
        "separately, since forward test years are not independent of the cut-off. Cells sharing a test "
        "year are not independent, so the interval is likely too narrow.",
        "P2 says 'years and blocks resampled separately'; here the first resampling unit is the cell "
        "(10 cells). Seed 20261114, 1000 resamples, 95 % percentile interval, as pre-registered.",
    ),
    (
        "2026-11-15",
        "For the chain route pair `k` is stored as nan (each leg has its own `k`, kept in the `legs` "
        "pairs of the "
        "same calibration).",
        "The calibration schema has one `k` per pair; the contract with the series code adds `route` and "
        "`legs`.",
    ),
]

MODIS_REF = (
    "MODIS-eq of the published route means MODIS as observed in 2018-05..2025-12, which includes the "
    "drift epoch (Terra 2023+, Aqua 2024+; cause unverified). "
    "It is not the same reference as S-NPP -> MODIS (2012-02..2025-12)."
)

UNVERIFIED = [
    "Observed MODIS from 2022 is in the drift epoch (Terra 2023+, Aqua 2024+ by P3, "
    "`reports/02/SA2.6.md`); the "
    "cause (orbit drift) is unverified. " + MODIS_REF + " "
    "So every "
    "forward score here, and the 2026 check, measure the factor against a drifting MODIS.",
    "The clip of NOAA-21 (area API to Argentina) has no country file to compare with: unverified.",
    "Only standard-processing (SP) months enter any fit or score here. NRT months are never used; the NRT "
    "vs SP "
    "processing difference is unverified.",
    "Degradation with the horizon is claimed only within the same test year (the horizon is confounded "
    "with the "
    "calendar year and with MODIS drift).",
    "The coverage of the conformal bands is measured, not guaranteed: outside 75-85 % it is labelled "
    "unverified "
    "and the band is not widened.",
    "Historical satellite-months below 90 % of the median number of detection days (P8 diagnostic) stay "
    "in the "
    "primary results; the secondary table leaves them out of the test months only.",
    "The factors are the same for every year of a calendar month; they carry no information on interannual "
    "changes of the NOAA-20 / MODIS relationship beyond what each cut-off saw.",
]


def _cov(x):
    return f"{pct(x)} ({coverage_label(x)})" if np.isfinite(x) else "-"


def _f(x, nd=3):
    return num(x, nd)


def _headline(res: Continuity, route: str, ext_pair, p9: pd.DataFrame | None) -> list[str]:
    d = res.decision
    full = [c for c in res.forward.cells if c.test_year <= LAST_FULL_YEAR]
    pub = select(full, route=route)
    by, bm = score(pub, "block-year"), score(pub, "block-month")
    other = "direct" if route == "chain" else "chain"
    s_o = score(select(full, route=other))
    out = ["## Headline (P1)", ""]
    n_ch = int((d.per_cutoff["better"] == "chain").sum())
    n_di = int((d.per_cutoff["better"] == "direct").sum())
    label = (
        "the direct NOAA-20 -> MODIS factor" if route == "direct" else "the chain NOAA-20 -> S-NPP -> MODIS"
    )
    out.append(
        f"- **Route:** {label} is published as the MODIS-eq route after MODIS. P5 on the pooled forward "
        f"holdouts (10 cut-off x test-year cells): {d.reason}. Robustness: {d.robust_note}. "
        f"The difference is within noise (bootstrap {pct(d.boot['wape_diff'], True)} "
        f"[{pct(d.boot['wape_lo'], True)}, {pct(d.boot['wape_hi'], True)}]; cut-offs split "
        f"{n_ch}-{n_di}) and the chain has the "
        f"{'smaller' if abs(d.chain['bias']) < abs(d.direct['bias']) else 'larger'} pooled bias "
        f"({pct(d.chain['bias'], True)} vs {pct(d.direct['bias'], True)}): the direct factor is kept as the "
        "baseline by the pre-registered rule, not because it was shown to be better."
    )
    out.append(
        f"- **Error (forward holdouts, cut-offs 2021-2024, test years to {LAST_FULL_YEAR}, pooled):** "
        "block-year WAPE "
        f"{pct(by['wape'])} and national bias {pct(by['bias'], True)} for the published route "
        f"({other}: {pct(s_o['wape'])}, {pct(s_o['bias'], True)}); block-month WAPE {pct(bm['wape'])}. "
        f"Scored against observed MODIS, which drifts from 2022 (see unverified items)."
    )
    cov9 = ""
    if p9 is not None and len(p9):
        q = p9[(p9["leg"].str.startswith("NOAA-20 -> MODIS")) & (p9["scope"].str.startswith("2026"))]
        if len(q):
            q = q.iloc[0]
            cov9 = (
                f" The frozen `{CALIBRATION_NEW}` band was tested only in P9: block-year {pct(q['cov_by'])} "
                f"on {q['scope'].split('(')[1].rstrip(')')} (Jan-Apr 2026, n = {int(q['n_by'])} rows), "
                f"{coverage_label(q['cov_by'])}. The band is not widened. No month of the main fire "
                "season after 2025 is validated."
            )
    out.append(
        f"- **Coverage (nominal 80 %, rows with source > 0):** block-year {pct(by['coverage'])} "
        f"({coverage_label(by['coverage'])}), relative width {pct(by['width'])}; block-month "
        f"{pct(bm['coverage'])} "
        f"({coverage_label(bm['coverage'])}). This is the coverage of bands refitted at each cut-off." + cov9
    )
    if p9 is not None and len(p9):
        r = p9[(p9["leg"].str.startswith("NOAA-20 -> MODIS")) & (p9["scope"].str.startswith("2026"))]
        if len(r):
            r = r.iloc[0]
            o = p9[
                p9["leg"].str.startswith("NOAA-20 -> MODIS")
                & (p9["scope"] == "2022-2025 forward holdouts pooled")
            ]
            oos_txt = (
                f"the same calendar months of 2022-2025 out of sample (forward holdouts) score "
                f"{pct(o.iloc[0]['wape_by'])} and {pct(o.iloc[0]['bias'], True)}. "
                if len(o)
                else ""
            )
            out.append(
                f"- **Frozen artifact on 2026 (P9, {r['scope']}):** the published route applied unchanged "
                f"scores block-year WAPE {pct(r['wape_by'])} and bias {pct(r['bias'], True)} against a "
                f"drifted MODIS; {oos_txt}Reported as is; it changes no decision."
            )
    else:
        out.append(f"- **Frozen artifact on 2026 (P9):** pending, `{CALIBRATION_NEW}` is not frozen yet.")
    if ext_pair is not None:
        out.append(
            f"- `{CALIBRATION_NEW}` carries the route as pair `noaa20_to_modis` with route `{ext_pair.route}`"
            + (f" and legs `{', '.join(ext_pair.legs)}`" if ext_pair.legs else "")
            + f", fitted on {ext_pair.start}..{ext_pair.end} ({ext_pair.n_months} months); "
            f"`{CALIBRATION_BASE}` pairs "
            "are byte for byte unchanged."
        )
    return out + [""]


def _pooled_table(res: Continuity, route_published: str) -> list[str]:
    full = [c for c in res.forward.cells if c.test_year <= LAST_FULL_YEAR]
    rows = []
    for route in ROUTES:
        sel = select(full, route=route)
        by, bm = score(sel, "block-year"), score(sel, "block-month")
        rows.append(
            [
                ROUTE_LABEL[route] + (" (published)" if route == route_published else ""),
                pct(by["wape"]),
                pct(by["bias"], True),
                pct(bm["wape"]),
                pct(bm["bias"], True),
                f"{pct(by['coverage'])} ({coverage_label(by['coverage'])})",
                pct(by["width"]),
                f"{pct(bm['coverage'])} ({coverage_label(bm['coverage'])})",
                pct(bm["width"]),
            ]
        )
    return md_table(
        [
            "Route",
            "Block-year WAPE",
            "National bias",
            "Block-month WAPE",
            "Block-month bias",
            "Block-year coverage",
            "Block-year rel. width",
            "Block-month coverage",
            "Block-month rel. width",
        ],
        rows,
    )


def _coverage_by_year(res: Continuity) -> list[str]:
    full = [c for c in res.forward.cells if c.test_year <= LAST_FULL_YEAR]
    rows = []
    for y in sorted({c.test_year for c in full}):
        r = [y]
        for route in ROUTES:
            s = score(select(full, route=route, test_year=y))
            r += [pct(s["wape"]), pct(s["bias"], True), pct(s["coverage"]), pct(s["width"])]
        rows.append(r)
    heads = ["Test year"] + [f"{r} {m}" for r in ROUTES for m in ("WAPE", "bias", "coverage", "width")]
    return md_table(heads, rows)


def seam_table(cal_ext) -> pd.DataFrame:
    """National factor by calendar month and day/night: direct NOAA-20 -> MODIS vs the chain product."""
    di = cal_ext.pairs["noaa20_to_modis"].f_nat
    ch = cal_ext.pairs["noaa20_to_snpp"].f_nat * cal_ext.pairs["viirs_to_modis"].f_nat
    rows = []
    for m in range(12):
        for k, dn in enumerate(("day", "night")):
            rows.append(
                {
                    "month": m + 1,
                    "dn": dn,
                    "direct": di[m, k],
                    "chain": ch[m, k],
                    "ratio": di[m, k] / ch[m, k],
                }
            )
    return pd.DataFrame(rows)


def _seam(cal_ext) -> list[str]:
    t = seam_table(cal_ext)
    pc = {n: cal_ext.pairs[n] for n in ("noaa20_to_modis", "noaa20_to_snpp", "viirs_to_modis")}
    top = t.loc[(t["ratio"] - 1).abs().nlargest(3).index]
    mx = t.loc[(t["ratio"] - 1).abs().idxmax()]
    names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    out = md_table(
        [
            "Month",
            "Day/night",
            "Direct (`noaa20_to_modis`)",
            "Chain (`noaa20_to_snpp` x `viirs_to_modis`)",
            "Direct / chain",
        ],
        [
            [names[int(r.month) - 1], r.dn, _f(r.direct), _f(r.chain), pct(r.ratio - 1, True)]
            for r in t.itertuples()
        ],
    )
    out += [
        "",
        "National factors (`f_nat`) of `"
        + CALIBRATION_NEW
        + "`; per-pair fitted periods: "
        + "; ".join(f"`{n}` {p.start}..{p.end}" for n, p in pc.items())
        + ".",
        "",
        "When S-NPP ends the series switches from S-NPP -> MODIS to NOAA-20 -> MODIS; the national factors "
        f"differ by up to {abs(mx['ratio'] - 1) * 100:.1f} % in {names[int(mx['month']) - 1]} ({mx['dn']}) "
        "(largest three: "
        + ", ".join(f"{names[int(r.month) - 1]} {r.dn} {pct(r.ratio - 1, True)}" for r in top.itertuples())
        + "): a step in MODIS-eq at the switch is expected and is an artifact of the route, not a change "
        "in fire.",
    ]
    return out


def build_sa210_report(
    res: Continuity,
    cal_ext=None,
    p9: pd.DataFrame | None = None,
    noaa21: pd.DataFrame | None = None,
    run_date: dt.date | None = None,
) -> str:
    d = res.decision
    fw = res.forward
    flagged = res.inputs.flagged
    route = cal_ext.pairs["noaa20_to_modis"].route if cal_ext is not None else d.route
    ext_pair = cal_ext.pairs["noaa20_to_modis"] if cal_ext is not None else None
    out = [
        "# SA2.10: post-MODIS continuity (NOAA-20 -> MODIS-eq)",
        "",
        f"Generated by `firecal harmonize continuity` on {(run_date or res.run_date).isoformat()}. All "
        "numbers "
        "come from code. Do not edit by hand. Pre-registration: `plan/02-harmonization.md` (P1, P2, P5, "
        "P8, P9 and "
        "Revision 1); nothing below uses a threshold that is not written there.",
        "",
        "Retrospective validation, not an alert system. " + MODIS_REF + " See `reports/02/SA2.6.md`.",
        "",
    ]
    out += _headline(res, route, ext_pair, p9)
    if cal_ext is not None and cal_ext.pairs["noaa20_to_modis"].route != d.route:
        out += [
            f"> Warning: the P5 decision of this run ({d.route}) differs from the route in "
            f"`{CALIBRATION_NEW}` "
            f"({cal_ext.pairs['noaa20_to_modis'].route}); the frozen file is not changed.",
            "",
        ]

    out += [
        "## Design",
        "",
        "- Counts, filters, 2.5 degree blocks, metrics (relative bias = sum(pred)/sum(obs) - 1; WAPE = "
        "sum|pred - obs| / sum(obs)), the SA2.2 estimator with `k` selected by the inner "
        "leave-one-year-out, and the "
        "conformal intervals are those of `reports/02/baselines.md`. Day and night are fitted separately "
        "and summed. "
        "Block-year = sum over the months of a test year of one block. All cubes are on the 70 blocks of "
        f"`{CALIBRATION_BASE}` (detections in other blocks dropped: {res.inputs.dropped_counts:.0f}).",
        "- Chain: NOAA-20 -> S-NPP (months from 2018-05) then S-NPP -> MODIS (months from 2012-02), each "
        "leg with "
        "its own `k`; the route factor is the product per month x block x day/night. Direct: one NOAA-20 "
        "-> MODIS "
        "factor, same estimator and `k` selection, months from 2018-05.",
        "- Forward holdouts (P2): cut-offs end of 2021, 2022, 2023, 2024; every leg and `k` refitted on "
        "months up to "
        "the cut-off, no gap; test every full calendar year after it up to 2025 (10 cut-off x test-year "
        "cells) and, "
        "apart, the 2026 block of complete satellite-months. Pooled = sum|err| / sum(obs) over all "
        "(cut-off, test year, block) rows. The 2026 block never enters the P5 decision.",
        "- Conformal bands per cut-off: residuals of the inner leave-one-year-out (6-month gap) on months "
        "up to the "
        "cut-off, every leg out-of-fold with its own `k`; coverage rows are those with source (NOAA-20) > "
        "0, pooled.",
        "",
        "## 1. Chain vs direct on the forward holdouts (P5)",
        "",
    ]
    out += _pooled_table(res, route)
    ch, di = d.chain, d.direct
    out += [
        "",
        "P5 rule: the chain is published only if its pooled block-year WAPE is lower than the direct "
        "factor's "
        f"({pct(ch['wape'])} vs {pct(di['wape'])}) and its |national bias| is not worse by more than 0.5 "
        "points "
        f"({pct(abs(ch['bias']))} vs {pct(abs(di['bias']))}). Decision: **{d.route}** ({d.reason}). "
        f"Ties go to the direct factor.",
        "",
        "Paired bootstrap of the pooled block-year difference chain - direct (negative = chain better; "
        "seed 20261114, "
        f"{d.boot['n_boot']} resamples, 95 % percentile; not a gate):",
        "",
    ]
    b = d.boot
    out += md_table(
        ["Metric", "Difference", "95 % interval"],
        [
            [
                "Block-year WAPE",
                pct(b["wape_diff"], True),
                f"[{pct(b['wape_lo'], True)}, {pct(b['wape_hi'], True)}]",
            ],
            [
                "abs(national bias)",
                pct(b["bias_diff"], True),
                f"[{pct(b['bias_lo'], True)}, {pct(b['bias_hi'], True)}]",
            ],
        ],
    )
    out += ["", "Per cut-off (block-year, pooled over its test years):", ""]
    out += md_table(
        ["Cut-off", "Chain WAPE", "Direct WAPE", "Chain - direct", "Chain bias", "Direct bias", "Better"],
        [
            [
                int(r.cutoff),
                pct(r.chain_wape),
                pct(r.direct_wape),
                pct(r.diff, True),
                pct(r.chain_bias, True),
                pct(r.direct_bias, True),
                r.better,
            ]
            for r in d.per_cutoff.itertuples()
        ],
    )
    out += ["", f"Robustness: {d.robust_note}.", ""]
    out += [
        "Biases that are disclosed, not corrected: the direct factor has only 3.7 training years at "
        "cut-off 2021 "
        "(NOAA-20 from 2018-05), while the chain's second leg has 9.9; the forward tests score against "
        "drifted MODIS, "
        "which favours a recently trained factor.",
        "",
        "Factors refitted at each cut-off (`k` selected inside the training months):",
        "",
    ]
    rows = []
    for c in sorted({k[0] for k in fw.ks}):
        m = fw.train_months[c]
        rows.append(
            [
                c,
                m["noaa20_to_snpp"],
                m["viirs_to_modis"],
                m["noaa20_to_modis"],
                fw.ks[c, "chain"]["noaa20_to_snpp"],
                fw.ks[c, "chain"]["viirs_to_modis"],
                fw.ks[c, "direct"]["noaa20_to_modis"],
            ]
        )
    out += md_table(
        [
            "Cut-off",
            "Months NOAA-20 -> S-NPP",
            "Months S-NPP -> MODIS",
            "Months NOAA-20 -> MODIS",
            "k leg 1",
            "k leg 2",
            "k direct",
        ],
        rows,
    )

    out += ["", "## 2. Cut-off x test-year (block-year)", ""]
    t = cutoff_year_table(fw)
    out += md_table(
        ["Cut-off", "Test year", "Chain WAPE", "Chain bias", "Direct WAPE", "Direct bias"],
        [
            [
                int(r.cutoff),
                "2026 (partial, see 5)" if r.test_year == 2026 else int(r.test_year),
                pct(r.chain_wape),
                pct(r.chain_bias, True),
                pct(r.direct_wape),
                pct(r.direct_bias, True),
            ]
            for r in t.itertuples()
        ],
    )

    out += ["", "## 3. Error by years since the cut-off", ""]
    h = horizon_table(fw)
    out += md_table(
        ["Years since cut-off", "Cells", "Chain WAPE", "Chain bias", "Direct WAPE", "Direct bias"],
        [
            [
                int(r.horizon),
                int(r.n_cells),
                pct(r.chain_wape),
                pct(r.chain_bias, True),
                pct(r.direct_wape),
                pct(r.direct_bias, True),
            ]
            for r in h.itertuples()
        ],
    )
    out += [
        "",
        "The horizon is confounded with the calendar year (horizon 4 is only test year 2025 from cut-off "
        "2021, "
        "horizon 1 includes 2022, the year MODIS starts to drift). A degradation with the horizon is "
        "claimed only "
        "within the same test year:",
        "",
    ]
    w = horizon_within_year(fw)
    out += md_table(
        ["Test year", "Route", "Cut-offs", "Block-year WAPE by cut-off", "Grows with horizon"],
        [
            [int(r.test_year), r.route, r.cutoffs, r.wape_by_cutoff, "yes" if r.grows_with_horizon else "no"]
            for r in w.itertuples()
        ],
    )
    n_grow = {route_: int(w[(w["route"] == route_) & w["grows_with_horizon"]].shape[0]) for route_ in ROUTES}
    n_all = {route_: int((w["route"] == route_).sum()) for route_ in ROUTES}
    out += [
        "",
        "Within the same test year the error is non-decreasing with the horizon in "
        + "; ".join(f"{n_grow[r]} of {n_all[r]} test years for the {r} route" for r in ROUTES)
        + ".",
    ]

    out += ["", "## 4. Test year, coverage and width (pooled over cut-offs, block-year)", ""]
    out += _coverage_by_year(res)

    out += ["", "## 5. The 2026 partial block (complete satellite-months only)", ""]
    pb = partial_block_table(fw)
    out += md_table(
        [
            "Cut-off",
            "Route",
            "Months scored",
            "Block-year WAPE 2026",
            "Bias 2026",
            "Same calendar months 2022-2025 WAPE",
            "Bias 2022-2025",
        ],
        [
            [
                int(r.cutoff),
                r.route,
                r.months_2026,
                pct(r.wape_2026),
                pct(r.bias_2026, True),
                pct(r.wape_ref),
                pct(r.bias_ref, True),
            ]
            for r in pb.itertuples()
        ],
    )
    out += [
        "",
        "The reference (like-for-like) is the sum of the same calendar months in the test years 2022-2025 "
        "of the same "
        "cut-off, out of sample. 2026 never enters the P5 decision.",
        "",
        "## 6. Leave-one-year-out with a 6-month gap over 2018-05..2025-12 (alongside)",
        "",
        "Each year is predicted by factors fitted on the other years minus the 6 months on each side "
        "(every leg and `k` refitted); the training uses years after the test year too, so it is not a "
        "forward test. "
        f"{LOYO_SPLIT[0][0]}-{LOYO_SPLIT[0][1]} vs {LOYO_SPLIT[1][0]}-{LOYO_SPLIT[1][1]} is a fixed "
        "split, not the P3 epoch.",
        "",
    ]
    lt = loyo_table(res.loyo)
    out += md_table(
        [
            "Test years",
            "Chain block-year WAPE",
            "Chain bias",
            "Chain block-month WAPE",
            "Direct block-year WAPE",
            "Direct bias",
            "Direct block-month WAPE",
        ],
        [
            [
                r.years,
                pct(r.chain_by_wape),
                pct(r.chain_by_bias, True),
                pct(r.chain_bm_wape),
                pct(r.direct_by_wape),
                pct(r.direct_by_bias, True),
                pct(r.direct_bm_wape),
            ]
            for r in lt.itertuples()
        ],
    )
    out += ["", "Per year:", ""]
    ly = loyo_year_table(res.loyo)
    out += md_table(
        ["Test year", "Chain WAPE", "Chain bias", "Direct WAPE", "Direct bias"],
        [
            [
                int(r.test_year),
                pct(r.chain_wape),
                pct(r.chain_bias, True),
                pct(r.direct_wape),
                pct(r.direct_bias, True),
            ]
            for r in ly.itertuples()
        ],
    )

    out += [
        "",
        "## 7. Secondary: without the historically flagged satellite-months",
        "",
        "Test months where NOAA-20, Terra or Aqua is flagged `partial` by the completeness diagnostic "
        "before 2026 "
        "(fewer than 90 % of the median detection days; P8 diagnostic, `reports/02/SA2.6.md`) are left "
        "out of the "
        "scoring of both routes. The primary results above keep them; fits are unchanged. Flagged months: "
        + "; ".join(f"{s} {len(flagged.get(s, ()))}" for s in ("noaa20", "terra", "aqua"))
        + " (all history).",
        "",
    ]
    sf = secondary_flagged(fw, res.loyo, flagged)
    out += md_table(
        ["Scope", "Route", "WAPE all", "Bias all", "WAPE without flagged", "Bias without flagged"],
        [
            [
                r.scope,
                r.route,
                pct(r.wape_all),
                pct(r.bias_all, True),
                pct(r.wape_excl),
                pct(r.bias_excl, True),
            ]
            for r in sf.itertuples()
        ],
    )
    if len(res.inputs.gated_out):
        out += ["", "2026 satellite-months left out of every fit and score (P8, not `complete` or NRT):", ""]
        g = res.inputs.gated_out
        out += md_table(
            ["Satellite", "Month", "Level", "Status", "Days with detections", "Threshold days"],
            [
                [r.satellite, r.month, r.level, r.status, r.days_with_detections, r.threshold_days]
                for r in g.itertuples()
            ],
        )

    out += ["", "## 8. NOAA-21 pairs added in the extension", ""]
    if noaa21 is not None and len(noaa21):
        out += md_table(
            [
                "Pair",
                "Months",
                "Fitted period",
                "k",
                "National ratio",
                "LOYO block-month WAPE",
                "LOYO block-year WAPE",
                "LOYO bias",
            ],
            [
                [
                    r.label,
                    int(r.months),
                    r.period,
                    f"{r.k:g}" + (" (fallback)" if r.k_fallback else ""),
                    _f(r.national_ratio),
                    pct(r.loyo_wape_bm),
                    pct(r.loyo_wape_by),
                    pct(r.loyo_bias, True),
                ]
                for r in noaa21.itertuples()
            ],
        )
        out += [
            "",
            "Standard-processing months 2023-03..2026-07 with complete satellites only, never NRT; "
            "factors indexed on "
            f"the blocks of `{CALIBRATION_BASE}`. The leave-one-year-out is informative (few years); "
            "NOAA-21 is "
            "used only as a whole-month national fallback by the series rules.",
        ]
    else:
        out += [f"Pending: `{CALIBRATION_NEW}` is not frozen yet."]

    out += ["", "## 9. Frozen-artifact check on 2026 (P9)", ""]
    if p9 is not None and len(p9):
        out += [
            f"`{CALIBRATION_BASE}` (S-NPP -> MODIS and NOAA-20 -> S-NPP) and `{CALIBRATION_NEW}` (the "
            "published "
            "NOAA-20 -> MODIS route) applied unchanged to the 2026 standard-processing months with complete "
            "satellites, scored by leg once, as a mechanical rule of the pre-registration. 2022-2025 rows "
            "use the same calendar months: 'in-sample' "
            "because those "
            "years are inside the fitted period of the frozen file, 'out of sample' for the forward "
            "holdouts of the "
            "published route. Coverage rows are those with source > 0. MODIS 2026 is in the drift epoch, "
            "so this "
            "measures MODIS as in the calibration period against a drifted MODIS.",
            "",
        ]
        ns = p9[p9["leg"].str.startswith("NOAA-20 -> S-NPP")]
        s26 = ns[ns["scope"].str.startswith("2026")].iloc[0]
        sref = ns[ns["scope"] == "2022-2025 pooled"].iloc[0]
        out += md_table(
            [
                "Leg",
                "Scope",
                "Months / note",
                "Block-month WAPE",
                "Block-year WAPE",
                "National bias",
                "Block-month coverage",
                "Block-year coverage",
                "Block-year rows (n)",
            ],
            [
                [
                    r.leg,
                    r.scope,
                    r.note,
                    pct(r.wape_bm),
                    pct(r.wape_by),
                    pct(r.bias, True),
                    _cov(r.cov_bm),
                    _cov(r.cov_by),
                    int(r.n_by),
                ]
                for r in p9.itertuples()
            ],
        )
        out += [
            "",
            "The block-year band is calibrated on 12-month sums and is applied here to a partial sum: its "
            "coverage on partial years is unverified. NOAA-20 -> S-NPP bias is "
            f"{pct(s26['bias'], True)} in 2026 against {pct(sref['bias'], True)} in the same months of "
            "2022-2025 (association; cause unverified).",
            "",
            "Reported as is; it changes no decision. P8 gates the 2026 months, so no secondary table is "
            "needed here.",
        ]
    else:
        out += [f"Pending: `{CALIBRATION_NEW}` is not frozen yet."]

    out += ["", "## 10. The switch from S-NPP -> MODIS to NOAA-20 -> MODIS (national factors)", ""]
    if cal_ext is not None:
        out += _seam(cal_ext)
    else:
        out += [f"Pending: `{CALIBRATION_NEW}` is not frozen yet."]

    out += ["", "## Deviations", ""]
    for date, what, why in DEVIATIONS:
        out.append(f"- deviation ({date}): {what} Reason: {why}")
    out += ["", "## Unverified", ""]
    out += [f"- {u}" for u in UNVERIFIED]
    out.append("")
    return "\n".join(out)
