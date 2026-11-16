# Portfolio handoff: fire-calendar

Everything needed to add fire-calendar to a portfolio. Figures are copied from the README and the reports in this
repo; keep them as written (each has a source and period). Last checked: 2026-11-16.

## At a glance

| Field | Value |
|---|---|
| Name | fire-calendar (UI: "Calendario de fuego") |
| One-liner | A harmonized MODIS + VIIRS fire calendar for Argentina, 2000 to today |
| Context | Built for the CONAE challenge "Harmonization of MODIS and VIIRS Hot Spots", NASA Space Apps Challenge 2026 (COR-CAT-08, Córdoba) |
| Role | Solo author: problem framing, method, validation design, data pipeline, web app, deployment |
| How it was built | With an AI coding assistant (Claude Code). The author planned each task and reviewed and validated the results; disclosed in the README |
| Dates | 2026-11-14 to 2026-11-16 (git history) |
| Live | https://fire-calendar.pages.dev/ |
| Code | https://github.com/maggioniduffy/fire-calendar |
| Demo deck | 7 slides; add the public PDF link once uploaded |
| Images | `app-cordoba.png` (app on Córdoba, 2026-10, 3200×1800), `icon-512.png` (app icon) in this folder |
| Tags | Remote sensing, Earth observation, NASA FIRMS, MODIS, VIIRS, wildfire, time series, uncertainty quantification, conformal prediction, LightGBM, Python, FastAPI, React, TypeScript, MapLibre, Cloudflare Pages |

## Short description (card, ~40 words)

MODIS and VIIRS satellites both detect fires, but VIIRS reports about 3.3× more hot spots, so long records break
when MODIS retires. fire-calendar harmonizes NASA FIRMS data for Argentina, 2000 to 2026, into one comparable
series with uncertainty bands, shown as a calendar for 513 areas.

Spanish: MODIS y VIIRS detectan incendios, pero VIIRS reporta unas 3,3 veces más focos, así que los registros
largos se cortan cuando MODIS se retira. fire-calendar armoniza datos de NASA FIRMS para Argentina, de 2000 a 2026,
en una serie comparable con bandas de incertidumbre, como calendario para 513 áreas.

## Case study (long form)

**Problem.** NASA FIRMS reports active-fire hot spots from MODIS (1 km, since 2000) and VIIRS (375 m, since 2012).
Over Argentina, VIIRS S-NPP reports about 3.3 times more hot spots than MODIS (2012-02 to 2025-12; night about
6.8×, day about 2.8×). A record that switches sensors shows a jump that is not a change in fire. MODIS (Terra and
Aqua) is being retired and S-NPP stopped in FIRMS on 2026-11-02, so continuity matters now.

**Approach.**
- Python pipeline: FIRMS per-country files plus the FIRMS area API for recent months; filters (type 0, MODIS
  confidence ≥ 30, VIIRS nominal or high); 0.1° grid per satellite; one source per satellite-month, never summed.
- Harmonization: a scale factor per 2.5° block, month and day/night, shrunk toward the national factor:
  `f = (M + k·f_national) / (V + k)`. Two output scales, MODIS-equivalent and VIIRS-equivalent.
- Uncertainty: 80 % conformal bands calibrated with nested leave-one-year-out residuals.
- Continuity: NOAA-20 and NOAA-21 carry the series after S-NPP and MODIS. Calibration frozen and checksummed
  (`sf-2026.11.2`); the build refuses a mismatching file.
- Recent months: near-real-time data enters with a static-source mask and is marked provisional.

**Validation (pre-registered rules, fixed before each run).**
- Block-year WAPE, leave-one-year-out 2012–2025: 10.1 % (VIIRS → MODIS-eq) and 10.6 % (MODIS → VIIRS-eq).
- Band coverage: 80.6 % for a nominal 80 % (block-year).
- Simulated MODIS switch-off (cut-offs 2021–2024): block-year WAPE 12.3 %.
- Baselines: quantile matching lost in both directions (11.1 % and 11.2 %).

**Machine learning, reported honestly.** LightGBM (Poisson/Tweedie) on cell × month × day/night rows, with the
factor as an offset. Features: count, FRP, FRP per detection, 3×3 neighbourhood count, day/night share, block
total, month. Most used: FRP per detection toward MODIS (47 % of gain), 3×3 count toward VIIRS (67 %). Adding
MODIS MCD64A1 burned area changed nothing. Toward MODIS it came close (block-month WAPE 15.9 % vs 17.2 %) but
failed the bias rule, so the simple factor is what ships.

**Product.** Static web app on Cloudflare Pages: 513 areas (24 provinces, 489 departments), year × month calendar,
anomalies against the climatology, ENSO phase row, map of hot spots by month, range or season, CSV download.
Spanish first, full English, light and dark themes, keyboard and screen-reader support (axe checks in CI).

**ENSO.** Shown as association, never cause. In Córdoba no association is detectable over 25 seasons (largest
|ρ| 0.35, family-wise p 0.30).

**Engineering.** Python 3.12 (uv, pandas, LightGBM, FastAPI), TypeScript + React + MapLibre GL, Vitest and
Playwright (e2e, accessibility), GitHub Actions pipeline that rebuilds the data and deploys.

## Highlight bullets (pick 3–4)

- Turned two incompatible NASA satellite fire records into one 2000–2026 series with calibrated uncertainty.
- Validated with pre-registered rules: 10 % block-year error, 80.6 % coverage for an 80 % band.
- Tested gradient boosting against a simple baseline and shipped the baseline when ML did not win.
- Published a bilingual, accessible fire calendar for every province and department of Argentina.

## What not to claim

- Not an alert or forecasting system: everything is retrospective.
- ENSO is an association, not a cause.
- No award or ranking unless one is announced. The README says the project is not competing; check that this is
  still accurate before you call it a hackathon submission.
- Unverified in the repo: exact FIRMS and NOAA CPC terms, the CARTO attribution wording, the exact MODIS
  shutdown date, the official Córdoba boundary (the app uses geoBoundaries ADM2).
- No code license file yet; add one before inviting reuse.

## Credits to show

Data: NASA FIRMS (MODIS C6.1, VIIRS 375 m), NOAA CPC ONI, geoBoundaries ADM2 (CC BY 3.0 IGO), CARTO basemaps.
Built with AI assistance (Claude Code).
