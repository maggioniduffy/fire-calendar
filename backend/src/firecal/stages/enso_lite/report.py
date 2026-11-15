# ruff: noqa: E501
"""Render the SA5.5 report (Markdown) and its machine-readable JSON. Neutral wording: association only."""

import numpy as np

from firecal.stages.calendar.service import clean
from firecal.stages.enso_lite.run import AREA_LABELS, MODIS_RANGE, SPLIT_YEAR

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def window_text(w: dict) -> str:
    if w["fallback"]:
        return f"Jul-Jun total (fallback: best 4-month window holds {w['best_share']:.1%} < 40%)"
    s, n = w["start_month"], w["length"]
    return f"{MONTHS[s - 1]}-{MONTHS[(s + n - 2) % 12]}"


def _f(v, d=2) -> str:
    return "n/a" if v is None or not np.isfinite(v) else f"{v:.{d}f}"


def _p(v) -> str:
    return "n/a" if v is None or not np.isfinite(v) else f"{v:.4f}"


def primary_table(p: dict) -> str:
    lines = [
        "| lag (months) | rho | block-bootstrap 95% CI | iid-bootstrap 95% CI | per-lag p (permutation) |",
        "|---:|---:|---|---|---:|",
    ]
    for k in range(13):
        cb = f"[{_f(p['ci_block'][0][k])}, {_f(p['ci_block'][1][k])}]"
        ci = f"[{_f(p['ci_iid'][0][k])}, {_f(p['ci_iid'][1][k])}]"
        lines.append(f"| {k} | {_f(p['rho'][k])} | {cb} | {ci} | {_p(p['p_lag'][k])} |")
    return "\n".join(lines)


def _verdict(p_fw: float, p: dict) -> str:
    k = p["best_lag"]
    if p_fw >= 0.05:
        return (
            f"**No-signal statement.** In the primary family (n = {p['n']} seasons) no lag shows an association "
            f"distinguishable from shuffled years: the largest |rho| is {_f(abs(p['rho'][k]))} at lag {k}, "
            f"family-wise p = {_p(p_fw)} (>= 0.05). This means *not detectable with this sample*, not "
            "*no association*."
        )
    return (
        f"**Signal statement.** In the primary family (n = {p['n']} seasons) the largest |rho| is "
        f"{_f(abs(p['rho'][k]))} at lag {k} (rho = {_f(p['rho'][k])}), family-wise p = {_p(p_fw)} (< 0.05). This "
        "is a statistical association between ONI and the season total in this sample; it says nothing about "
        "mechanism, and it is a single area, so it is not a general result."
    )


def exploratory_summary(res: list[dict]) -> str:
    lines = [
        "| configuration | n | seasons | window | lag at max abs rho | rho | per-lag p | own family-wise p |",
        "|---|---:|---|---|---:|---:|---:|---:|",
    ]
    for r in res:
        k = r["best_lag"]
        lines.append(
            f"| {r['label']} | {r['n']} | {r['first_year']}-{r['last_year']} | {window_text(r['window'])} "
            f"({r['window']['share']:.0%}) | {k} | {_f(r['rho'][k])} | {_p(r['p_lag'][k])} | {_p(r['p_fw'])} |"
        )
    return "\n".join(lines)


def exploratory_grid(res: list[dict]) -> str:
    head = "| configuration | " + " | ".join(f"L{k}" for k in range(13)) + " |"
    lines = [head, "|---|" + "---:|" * 13]
    for r in res:
        lines.append(f"| {r['label']} | " + " | ".join(_f(v) for v in r["rho"]) + " |")
    return "\n".join(lines)


def clim_table(clim) -> str:
    med = clim["median"].to_numpy(dtype=float)
    tot = float(np.nansum(med))
    lines = ["| month | median monthly total (VIIRS-eq) | share of annual median total |", "|---|---:|---:|"]
    for m in range(12):
        lines.append(f"| {MONTHS[m]} | {_f(med[m], 1)} | {med[m] / tot:.1%} |")
    return "\n".join(lines)


def era_table(e: dict) -> str:
    we, oo = e["within_era"], e["observed_only"]
    lines = [
        f"| lag | rho within-era ranks (n = {we['n']}) | per-lag p | rho observed-only {SPLIT_YEAR}-2025 "
        f"(n = {oo['n']}) | per-lag p |",
        "|---:|---:|---:|---:|---:|",
    ]
    for k in range(13):
        lines.append(
            f"| {k} | {_f(we['rho'][k])} | {_p(we['p_lag'][k])} | {_f(oo['rho'][k])} | {_p(oo['p_lag'][k])} |"
        )
    return "\n".join(lines)


def render_markdown(r: dict) -> str:
    p, e, pv = r["primary"], r["era"], r["provenance"]
    w = p["window"]
    k = p["best_lag"]
    boxes = "\n".join(
        f"- {AREA_LABELS[a]}: lat {b[0]:g} to {b[1]:g}, lon {b[2]:g} to {b[3]:g}"
        for a, b in r["boxes"].items()
    )
    ef = r["exploratory_fw"]
    pw = r["power"]
    out = f"""# SA5.5 ENSO-lite: fire-season totals vs lagged ONI

Retrospective association analysis. It is not a prediction, not an alert and not a causal claim.
Design: `plan/05-enso-drought.md`, section "SA5.5 pre-registered design" (fixed 2026-11-15 before the run).
Deviations from the design: see the section "Deviations and open points".

- **Random seed:** {r["seed"]} (numpy `SeedSequence`; separate streams for permutations, block bootstrap, iid bootstrap)
- Permutations: {r["n_perm"]} whole-year shuffles, shared by all areas. Bootstrap resamples: {r["n_boot"]} (block length {r["block_len"]}).

## 1. Primary specification

- Area: Cordoba preset (approximate rectangle, lat {r["boxes"]["cordoba"][0]:g} to {r["boxes"]["cordoba"][1]:g}, lon {r["boxes"]["cordoba"][2]:g} to {r["boxes"]["cordoba"][3]:g}; not the official boundary).
- Series: VIIRS-eq scale of the harmonized layer, raw (not detrended) season totals; seasons {p["first_year"]}-{p["last_year"]} (n = {p["n"]}).
- Fire season: the 4 consecutive calendar months (circular) with the highest climatological median total; labelled by the year of its first month; incomplete seasons dropped.
- Lag k (0-12): ONI value (3-month mean dated at its central month) at season start minus k months; no further averaging.
- Statistic: Spearman rho per lag. 95% CI by moving-block bootstrap over seasons (block {r["block_len"]}) labelled **approximate, coverage unverified**, next to an iid pairs bootstrap.
- Baseline: shuffled years (each season keeps its 13-lag ONI vector). Per-lag p is two-sided with the +1 correction; family-wise p uses max |rho| over the 13 lags.
- Lag-1 autocorrelation (consecutive years): season total {_f(p["ac_y"])}; ONI at lag 0 {_f(p["ac_oni0"])}.

## 2. Primary result (Cordoba, VIIRS-eq, raw season totals)

{primary_table(p)}

**Family-wise p (max |rho| over lags 0-12, {r["n_perm"]} whole-year permutations): {_p(p["p_fw"])}**
(observed max |rho| = {_f(abs(p["rho"][k]))} at lag {k}).

{_verdict(p["p_fw"], p)}

## 3. Season window per area

Primary: **{window_text(w)}** (start month {w["start_month"]}, length {w["length"]}), holding **{w["share"]:.1%}** of the annual median total (sum of the 12 monthly medians{", fallback to Jul-Jun used" if w["fallback"] else ""}).

{clim_table(r["primary_clim"])}

The window of every exploratory area is in the first exploratory table (column `window`, share of the annual median total in parentheses).

## 4. Era checks (primary configuration)

VIIRS-eq is *estimated* from MODIS in 2000-2011 and observed from 2012 (seasons are assigned to the era of the year of their first month; n = {e["within_era"]["n_est"]} estimated, {e["within_era"]["n_obs"]} observed). The estimated era may carry a different scale and variability than the observed one, so two checks are reported:

- within-era ranks: season totals are replaced by their percentile rank within each era (rank/(n+1)) before the Spearman computation; ONI is ranked over all seasons;
- observed-only: seasons from {SPLIT_YEAR} onward only.

{era_table(e)}

Family-wise p (max |rho| over lags): within-era ranks {_p(e["within_era"]["p_fw"])}; observed-only {_p(e["observed_only"]["p_fw"])}.

## 5. Exploratory tables (not used for the headline)

Reported for completeness; many configurations were examined, so isolated large values are expected by chance. Sign convention: rho > 0 means larger season totals with higher ONI (warmer ENSO phase) at that lag, rho < 0 the opposite. The configurations are not independent (nested and overlapping areas, the same ONI series, MODIS-eq and VIIRS-eq views of the same detections), and "own family-wise p" corrects only for the 13 lags of that one configuration; the p over all configurations is the one that accounts for the whole exploratory set. Configurations: all of Argentina and four approximate regions (VIIRS-eq, raw); MODIS-eq {MODIS_RANGE[0]}-{MODIS_RANGE[1]} (Aqua full years; Terra drift 2024-2025) for Cordoba and the five areas; log1p-detrended VIIRS-eq totals (OLS linear trend removed) for Cordoba and the five areas.

**Family-wise p over all {ef["n_configs"]} exploratory configurations x 13 lags: {_p(ef["p"])}** (observed max |rho| = {_f(ef["observed_max_abs_rho"])}).

### 5.1 Best lag per configuration

{exploratory_summary(r["exploratory"])}

### 5.2 Spearman rho by lag

{exploratory_grid(r["exploratory"])}

### 5.3 Region boxes (approximate, not official boundaries)

{boxes}

The boxes are simple lat/lon rectangles chosen for this analysis (edges on 0.1 degree cell borders; cells are selected by center). They are **approximate, not official boundaries**, and some include cells outside the named region (sin verificar).

## 6. Power note

With n = {p["n"]} seasons, the null distribution of the shuffled-years baseline gives (95th percentile): a per-lag threshold of |rho| >= {_f(pw["crit_abs_rho_per_lag_95"])} and a family-wise threshold (max over 13 lags) of |rho| >= {_f(pw["crit_abs_rho_familywise_95"])}. Associations weaker than that cannot be told apart from chance with this sample. A null result therefore means "not detectable with this sample", not "no association". The block-bootstrap CI assumes weak dependence between neighbouring seasons; its coverage at this n has not been verified, and the iid CI is shown beside it for that reason.

## 7. Sources and periods

- Fire data: {pv["fire_source"]} (layer `{pv["fire_layer"]}`, period {pv["fire_period"]}, license {pv["fire_license"]}). Harmonization: method `{pv["fire_method"]}`, calibration id `{pv["calibration_version"]}`. VIIRS-eq 2000-2011 is estimated from MODIS (modeled, with the layer's own uncertainty, which is not propagated here).
- ONI: {pv["oni_source"]} ({pv["oni_url"]}), monthly values {pv["oni_period"]}.
- Analysis: `firecal enso lite`, seed {r["seed"]}.

## 8. Deviations and open points

- Permutations: one shared permutation of the calendar years {r["year_axis"][0]}-{r["year_axis"][1]} is drawn per resample; each area uses the order it induces on its own valid seasons (a uniform permutation of those seasons), so areas with different season sets share the same draw.
- Seasons with any of the 13 lag values missing are dropped; the primary series keeps {p["n"]} seasons.
- Within-era ranks are applied to the fire totals only (ONI is not re-ranked by era); this is an interpretation of the design wording.
- "All areas x lags" family-wise p for the exploratory set covers the {ef["n_configs"]} configurations listed in 5.1.
- Region boxes, Argentina (data box includes any cell with detections inside it) and Cordoba are approximate. The block-bootstrap CI is approximate with unverified coverage.
- No moving-block coverage simulation, no drought variable (SPI/SPEI deferred), no causal analysis.
"""
    return out


def to_json(r: dict) -> dict:
    def conf(x):
        return {
            "key": x["key"],
            "label": x["label"],
            "area": x["area"],
            "scale": x["scale"],
            "transform": x["transform"],
            "n": x["n"],
            "first_year": x["first_year"],
            "last_year": x["last_year"],
            "window": x["window"],
            "lags": list(range(13)),
            "rho": x["rho"],
            "ci_block": {
                "lo": x["ci_block"][0],
                "hi": x["ci_block"][1],
                "note": "approximate, coverage unverified",
            },
            "ci_iid": {"lo": x["ci_iid"][0], "hi": x["ci_iid"][1]},
            "p_lag": x["p_lag"],
            "p_familywise": x["p_fw"],
            "best_lag": x["best_lag"],
            "lag1_autocorr_total": x["ac_y"],
            "lag1_autocorr_oni0": x["ac_oni0"],
            "seasons": x["years"],
            "season_totals": x["totals"],
        }

    e = r["era"]
    return clean(
        {
            "design": "plan/05-enso-drought.md#SA5.5",
            "association_only": True,
            "seed": r["seed"],
            "n_perm": r["n_perm"],
            "n_boot": r["n_boot"],
            "block_len": r["block_len"],
            "provenance": r["provenance"],
            "boxes_approximate_not_official": r["boxes"],
            "primary": conf(r["primary"]),
            "era": {
                "split_year": e["split_year"],
                "within_era": e["within_era"],
                "observed_only": e["observed_only"],
            },
            "exploratory": [conf(x) for x in r["exploratory"]],
            "exploratory_familywise": r["exploratory_fw"],
            "power": r["power"],
        }
    )
