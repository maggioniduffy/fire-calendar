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
| 2 | MODIS–VIIRS harmonization + ML | [plan/02-harmonization.md](plan/02-harmonization.md) | 1 | active (part deferred) |
| 3 | Calendar and per-area analytics | [plan/03-calendar-analytics.md](plan/03-calendar-analytics.md) | 2 | active |
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
