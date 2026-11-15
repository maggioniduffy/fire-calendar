# Architecture

Same as clima-ideas, with the `firecal` package.

## Structure

```
backend/            uv, Python 3.12
  src/firecal/
    io/             downloads and ingestion (FIRMS per country, FIRMS API, ONI)
    stages/         grid/, harmonize/, calendar/, enso/  (one folder per phase)
    layers/         layer writing + manifest
    api/            FastAPI, read-only over data/processed
    cli.py          `firecal <stage> <step>`
  tests/            unit (fast) and slow (marked)
web/                pnpm, Vite, React, TypeScript, deck.gl
  src/i18n/         es.ts and en.ts: all UI texts
  src/theme/        tokens (see docs/design.md)
  e2e/              Playwright, with fake fixtures
data/               raw/ interim/ processed/  (out of git)
reports/            per-phase reports (reports/NN/<ID>.md)
Makefile            install, dev, test, lint
```

## Flow

`io` downloads → `stages/*` computes → `layers` publishes to `data/processed/<layer_id>/` → API serves → web draws.
Each step is an idempotent CLI command (`firecal <stage> <step>`).

## Layer contract

`data/processed/<layer_id>/manifest.json`:

```json
{
  "id": "fire-grid",
  "title": "Hot spots per cell",
  "kind": "events | points | grid | series | polygons",
  "source": "NASA FIRMS (MODIS C6.1, VIIRS 375 m)",
  "period": "2000-11-01/2026-08-31",
  "license": "NASA open data",
  "updated_at": "ISO-8601",
  "experimental": false,
  "files": ["grid.parquet"]
}
```

`experimental` is optional. Tables in Parquet/GeoParquet. The UI takes source and period from the manifest. The API
validates the manifest with pydantic and serves only files listed in `files`.

## API

`GET /health` · `GET /layers` · `GET /layers/{id}` · `GET /layers/{id}/data` · `POST /calendar` ·
`POST /stats` · `POST /export.csv` (phase 3).

## Static publishing

Online there is no API: results are precomputed per area (provinces and departments) and uploaded as JSON to a
bucket (Cloudflare R2) with paths that mimic the API's; the static web reads them when the build has
`VITE_DATA_URL` and, without that variable, uses `/api` as in local. `R2_*` credentials in the environment or in
`.env`.

## Tests

- Unit with synthetic data of known result (pytest, vitest).
- e2e with fake layers in `web/e2e/fixtures/` (Playwright), without depending on real data.
- `@pytest.mark.slow`: real data or long runs; outside CI.
- CI (GitHub Actions): ruff, pytest, eslint, tsc, vitest, Playwright.
