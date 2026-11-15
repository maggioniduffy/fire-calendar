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
| 2 | MODIS–VIIRS harmonization + ML | [plan/02-harmonization.md](plan/02-harmonization.md) | 1 | closed 2026-11-15 (part deferred) |
| 3 | Calendar and per-area analytics | [plan/03-calendar-analytics.md](plan/03-calendar-analytics.md) | 2 | done (backend) |
| 4 | Web app | [plan/04-web-app.md](plan/04-web-app.md) | 0, 3 | active |
| 5 | ENSO and fire (ENSO-lite only) | [plan/05-enso-drought.md](plan/05-enso-drought.md) | 3, SA0.9 | active (drought deferred) |
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
