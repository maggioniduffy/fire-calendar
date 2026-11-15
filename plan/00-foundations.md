# Phase 0 — Foundations

Status: active · Refs: `docs/architecture.md`, `docs/design.md` (SA0.4–SA0.5 only), `docs/agents.md`, `docs/research/data-sources.md`

## Goal

Repo ready to add layers, and data access resolved.

## Tasks

| ID | Task | Agent | Done when |
|---|---|---|---|
| SA0.1 | Space Apps 2026 rules: code or data prepared before the event, license, deliverables (video, slides, project page, public repo) → `docs/research/rules.md` | Opus | Done (historical: no longer competing) ✅ |
| SA0.2 | Monorepo per `docs/architecture.md`: `backend/` (uv, Python 3.12, `firecal` package) and `web/` (pnpm, Vite, React, TS, deck.gl); `Makefile`; `data/` out of git | Sonnet | `make dev` starts API and app. Done ✅ (2026-11-14; full `make dev` not tested end to end) |
| SA0.3 | CI (GitHub Actions): ruff, pytest, eslint, tsc, vitest, Playwright | Sonnet | CI green on a PR. Backend and web jobs (tsc, eslint, vitest, Playwright) written ✅; the web job has not yet run on GitHub |
| SA0.4 | Tokens from `docs/design.md`, light/dark theme, `web/src/i18n/es.ts` and `en.ts` | Sonnet | Theme and language switch without reload; no string outside i18n. Done ✅ (e2e and vitest) |
| SA0.5 | App shell per the canvas: top bar with challenge and author, left panel, map, inspector, calendar strip | Sonnet | Fixed layout in both themes and at phone width. Done ✅ (e2e) |
| SA0.6 | FastAPI (`/health`, `/layers`, `/layers/{id}`) and manifest validated with pydantic per `docs/architecture.md`, with `source`, `period`, `license` and optional `experimental` field | Sonnet | Unit for valid and invalid manifest. Done ✅ |
| SA0.7 | End-to-end test layer with fake hot spots | Sonnet | e2e: the layer appears and can be inspected. Done ✅ |
| SA0.8 | Data access (list below) → `docs/research/data-sources.md` | Opus | FIRMS verified on 2026-11-14; the rest pending (deferred except what the active phase asks for) |
| SA0.9 | Monthly ONI (NOAA CPC) and ENSO phase per month, porting `docs/reference/enso.py` (clima-ideas F0.10) to `firecal.io.enso` | Sonnet | Parquet + threshold unit on a synthetic series. Code and unit done ✅ (CPC 5-season rule); run 2026-11-14: 921 months, 1950-01 to 2026-09 |

## SA0.8: what to investigate

FIRMS ✅ (see `docs/research/data-sources.md`) · CONAE's Hot Spots and Burned Areas Catalog and Thematic Viewer
(access, license) · SPI/SPEI: CHIRPS, ERA5, SPEIbase · Copernicus CEMS FWI · global land cover (MODIS MCD12Q1 or
ESA WorldCover) · Terra and Aqua orbital drift and end-of-mission dates · where to deploy the demo for free.

## Tests

Unit: manifest, ENSO phase, theme and language store. e2e: shell, theme, language, test layer.
