# Plan: harmonized MODIS + VIIRS fire calendar

CONAE challenge of the NASA Space Apps Challenge 2026, "Harmonization of MODIS and VIIRS Hot Spots". Not
competing; no deadline. Author: Faustino Maggioni Duffy.

Product: a Python pipeline that builds a harmonized hot-spot series 2000–today for Argentina in two scales
(MODIS-equivalent and VIIRS-equivalent, which keeps going when MODIS is switched off) and a web app with a
year × month calendar, anomalies, ENSO phase and downloadable CSV.

Docs: [architecture](docs/architecture.md), [design](docs/design.md), [validation](docs/validation.md),
[data sources](docs/research/data-sources.md), [delegation](docs/agents.md).

## Phases

| # | Phase | File | Depends on | Status |
|---|---|---|---|---|
| 0 | Foundations and data access | [plan/00-foundations.md](plan/00-foundations.md) | — | active |
| 1 | FIRMS data: download, filters, grid | [plan/01-data.md](plan/01-data.md) | 0 | active |
| 2 | MODIS–VIIRS harmonization + ML | [plan/02-harmonization.md](plan/02-harmonization.md) | 1 | done 2026-11-15 (incl. post-MODIS continuity) |
| 3 | Calendar and per-area analytics | [plan/03-calendar-analytics.md](plan/03-calendar-analytics.md) | 2 | done (backend) |
| 4 | Web app | [plan/04-web-app.md](plan/04-web-app.md) | 0, 3 | done (backend + web) |
| 5 | ENSO and fire (ENSO-lite only) | [plan/05-enso-drought.md](plan/05-enso-drought.md) | 3, SA0.9 | ENSO-lite done (drought deferred) |
| 5b | Atmospheric rivers and fire | [plan/05b-atmospheric-rivers.md](plan/05b-atmospheric-rivers.md) | 4 | deferred |
| 6 | Experimental prediction | [plan/06-ml-outlook.md](plan/06-ml-outlook.md) | 2, 5 | deferred |
| 7 | Publication | [plan/07-submission.md](plan/07-submission.md) | 4 | active |

## Order

0 → (backend SA0.2/SA0.6 ∥ web SA0.4/SA0.5) → 1 → 2 → 3 → (4 ∥ 5 ENSO-lite) → 7.

If something slips, cut in this order: Dashboard tab (SA4.8), lag analysis SA5.5 (the ENSO phase row stays),
LightGBM (the scale factor stays), NRT.

## Progress

- 2026-11-14: repo split from clima-ideas (formerly `space-apps/` on branch
  `claude/space-apps-fire-calendar-plan`). FIRMS sources verified. SA0.1 done (event rules, no longer in effect).
- 2026-11-14: `firecal` backend (uv, Python 3.12), Makefile, backend CI, manifest + API (SA0.2 backend, SA0.3
  backend, SA0.6), ONI and ENSO phase (SA0.9), FIRMS download, ingestion, filters and grid (SA1.1–SA1.4), all with
  unit tests and no network. The cloud session cannot reach FIRMS or CPC (proxy 403), so the real download and
  SA1.7 are left for a local run: `make install`, `cd backend && uv run firecal enso build`,
  `uv run firecal firms download`, `ingest`, `grid`, `profile`.
- 2026-11-14: FIRMS and CPC were enabled in the cloud environment and everything was run. ONI: 921 months (1950-01
  to 2026-09). FIRMS: 48 files 2000–2025; no standard 2026 file yet. SA1.1–SA1.4 and SA1.7 done
  ([reports/01/SA1.7.md](reports/01/SA1.7.md)). Open for phase 2: the MODIS `version` code changes in 2018 and
  2023 (what that implies is unverified).
- 2026-11-14: agent workflow in `.claude/agents/` (Opus orchestrates, Sonnet builds, Haiku researches, Fable
  advises until 2026-11-17). Web in Makefile and CI with eslint (SA0.2, SA0.4, SA0.5, SA0.7 done; SA0.3 waits for
  a PR). MODIS `version` codes reviewed in `docs/research/data-sources.md`: no algorithm change between C6 and
  C6.1; more type 2 hot spots since 2018. Phase 2: baseline design decided, SA2.1, SA2.2, SA2.3 and SA2.5 done
  ([reports/02/baselines.md](reports/02/baselines.md)): the scale factor wins. Next: inverse-series intervals with
  real coverage, then SA2.4 and SA2.7 (LightGBM) against that baseline.
- 2026-11-14: nested conformal intervals for SA2.2, with an additive bound for small predictions and
  source-defined rows: 80 % coverage (nominal 80 %) in both directions, month-block and year-block; the worst
  year-block year drops to 67–72 %. Only 0.3 % of VIIRS detections fall where MODIS saw nothing. LightGBM design
  and publication criterion fixed in `plan/02-harmonization.md`; next: SA2.4 and SA2.7.
- 2026-11-15: SA2.11 done: `harmonized` layer (`firecal series calibrate|build`) with the MODIS-eq and VIIRS-eq
  series per 0.1° cell and month, 2000-11 to 2025-12, scale-factor method (calibration `sf-2026.11.1`) and
  block bands. VIIRS-eq 2000–2011 marked "estimated"; 2000–2002 uses Terra's factor alone (extrapolation
  unverified). LightGBM (SA2.4, SA2.7) in progress: if it passes the fixed criterion, it replaces the layer's
  method.
- 2026-11-15: phase 2 closed. LightGBM (SA2.4, SA2.7) does not beat the scale factor under the criterion fixed
  before the run; SA2.2 is published (`harmonized` layer, calibration `sf-2026.11.1`). Phase 3 was done in
  parallel in another session (branch `fm/phase-3-calendar`, merged here).
- 2026-11-15: phase 3 done (SA3.1–SA3.6), on the published `harmonized` schema and not on the method: area
  (circle or GeoJSON polygon, approximate Córdoba preset), year×month matrix, climatology, anomaly of the last
  available month, key figures, `POST /calendar`, `/stats` and `/export.csv`. Area band = block band scaled by
  the area fraction (unverified). Open: validate that band and the official Córdoba boundary.
- 2026-11-15: LightGBM cell-model bias verified
  ([reports/02/ml_bias_check.md](reports/02/ml_bias_check.md)): structural in the total (it comes from detections
  outside its rows), not in individual years. The verdict does not change.
- 2026-11-15: phase 4 started. SA4.1 done: data client (`VITE_DATA_URL` or `/api`), selection state, area by
  Córdoba preset, lat/lon + radius, drawn polygon and "Use my location" (230 km; denied stays on Córdoba). E2E run
  on synthetic API fixtures generated from the real app (`backend/scripts/web_fixtures.py`, drift test). The API
  has no "reported" scale yet (SA4.5).
- 2026-11-15: SA4.2 done: `POST /cells` (cells of one month in the area, total equal to `/calendar`) and
  `POST /detections` (capped, 404 without raw detections); map draws the area outline and cells, raw points at
  zoom ≥ 8 when the server has them, overlay with month and area total.
- 2026-11-15: SA4.3 + SA4.4 done: calendar card with the year × month heatmap (count, single-hue violet ramp) and
  the anomaly view against the `/stats` climatology median (blue/orange, neutral `--raised`), tooltip with count,
  source and period, keyboard grid. Scales in `web/src/charts/scales.ts`. Cells with no data are hatched. The
  light-theme ramp darkens with the count (dark theme lightens), a deviation from "grows in lightness" in
  `docs/design.md` for the cream theme.
- 2026-11-15: SA4.5 (inspector, series selector) and SA4.6 (CSV downloads) done and integrated with the map and
  calendar. The fake hot-spot test layer is gone (inspector detail/provenance blocks, map point layer,
  `loadLayers`, `layers/manifest.ts`); `/calendar` is fetched on area, period and scale only, `/stats` also on the
  chosen month, so changing the month does not refetch the calendar. e2e fixtures hold `/cells` and per-month
  `/stats` for every month of the synthetic period; the climatology now also returns p25 and p75.
- 2026-11-15: SA4.8 and SA4.7 done, phase 4 closed. Dashboard tab (monthly series with band, totals per year,
  seasonality, anomaly; CSV/PNG per chart; day/night, FRP and ENSO charts deferred: no payload provides them);
  seasonality draws the p10–p90 range and the "normal" band p25–p75 with the median and the latest year on top.
  Accessibility: axe (WCAG 2 A/AA) with 0 violations on map, dashboard, light/dark and 360 px; keyboard tab order
  and a month stepper for the dashboard charts; focus ring accent with casing. Keyboard-only polygon drawing is out
  of scope: lat/lon + radius is the keyboard alternative.
- 2026-11-15: phase 4 checked on real data ([reports/04/real-data-check.md](reports/04/real-data-check.md)): 10 items
  walked, none failed; API under 0.6 s. Unverified: raw points seen on screen at zoom >= 8, hot-spot button after a
  404, chart CSV contents, contrast over the real basemap and screen readers. CI on main fails at `pnpm e2e` (webServer
  timeout); fix on branch `fix/ci-web-e2e`, not yet confirmed in CI.
- 2026-11-15: SA4.9 done: the calendar strip was clipped (fixed 22vh, 26 year rows). Grid turned sideways and a
  drag handle added (`StripResizer`). Arrow keys now follow the drawing: Left/Right = year, Up/Down = month.
  Checked: vitest, tsc, eslint and the calendar, shell and a11y e2e specs; the other e2e specs were not rerun.
- 2026-11-15: SA5.2 done: `/calendar` carries an `enso` block (ONI and phase per month, NOAA CPC; medians,
  p25 and p75 of hot spots per calendar month and phase). The session moved to the clima-ideas network and the real
  pipeline was rebuilt (FIRMS 2000–2025, ONI to 2026-09). SA5.5 done ([reports/05/SA5.5.md](reports/05/SA5.5.md)),
  design pre-registered with the advisor: Córdoba, VIIRS-eq, Jul–Oct season, n = 25: no association detectable
  (max |rho| 0.35 at lag 2, family-wise p 0.30; detectable needs |rho| ≥ 0.50). Exploratory areas (NOA, Pampas,
  Argentina) show small own p values but are not independent and are not the headline.
- 2026-11-15: SA5.4 done, ENSO-lite closed. Calendar ENSO row (12 phase segments per year column, ONI, source and
  period, association note; hidden with a note when `enso` is null) and a "By ENSO phase" toggle in the dashboard
  seasonality (few-years points marked). Full e2e 59/59; one earlier a11y tab-order failure did not reproduce
  (possibly flaky, unverified). Next: phase 7 (README, deployed demo).
- 2026-11-15: phase 7 started (branch `fm/phase-7-publication`). SA7.1 done: README in English with the problem,
  the SA2.2 method and its error and coverage tables (copied from `reports/02/baselines.md`), sources and how to
  run. Unverified: exact FIRMS and CPC terms, CARTO attribution text; no code license file yet. SA7.2 static
  export designed in `plan/07-submission.md`; boundary candidate geoBoundaries ADM2 (IGN + OCHA ROLAC,
  CC BY 3.0 IGO); its ADM1 file lacks Entre Ríos, so provinces are to be built from ADM2.
- 2026-11-15: SA7.2 built and tested, not yet deployed. `firecal boundaries fetch` (geoBoundaries ADM2 pinned to
  commit 8ce2700, CC BY 3.0 IGO) and `firecal publish export`: 513 areas (24 provinces, 489 departments; Córdoba 26),
  4197 files, 492 MB; 36 areas under 100 km² skipped; files equal the API on synthetic and real data. ADM1 is used
  only to assign provinces and is wrong in places: 43 corrections hard-coded and listed in the manifest (Entre Ríos
  department list and per-province counts unverified). Web static mode (`VITE_DATA_URL=/data`, region picker,
  location -> province, attribution) with e2e 64/64. Hosting decided: Cloudflare Pages project `fire-calendar`
  (created). The cloud session cannot upload (its proxy replaces wrangler's upload token), so deploy runs from the
  manual `deploy-demo` workflow, which needs the CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID secrets and the
  workflow on the default branch.
- 2026-11-15: phase 2 completed (branch `fm/phase-2-continuity`), pre-registered with the advisor before any
  result. Freeze guard: calibrations live in `backend/calibrations/` with sha256, build verifies, overwrite refused.
  SA2.6 drift (Terra 2023+, Aqua 2024+; cause unverified) and SA2.8 backward validation (no recalibration warranted
  under the rule; `terra_to_viirs` only under the 2022+ sensitivity window, for a later version). SA1.6: FIRMS area
  API (SP then NRT, NOAA-21), Argentina clip (P7 passes), one source per satellite-month, NRT static-source mask,
  completeness gate. SA2.9: MCD64A1 burned area does not change the SA2.7 verdict. SA2.10: `sf-2026.11.2`, direct
  NOAA-20 -> MODIS route (block-year WAPE 12.3 %, within noise of the chain), frozen band coverage on Jan–Apr 2026
  unverified (72.1 %). Series to 2026-10 with provisional NRT months and web badges; static export regenerated, not
  deployed. Open: map view does not mark provisional months; calendar rows Nov–Dec sit under the ENSO strip at
  1440x720 (hover blocked, keyboard works); a11y tab-order test flaky (also on the base).
