# Arquitectura

Igual que clima-ideas, con el paquete `firecal`.

## Estructura

```
backend/            uv, Python 3.12
  src/firecal/
    io/             descargas e ingesta (FIRMS por país, FIRMS API, ONI)
    stages/         grid/, harmonize/, calendar/, enso/  (una carpeta por fase)
    layers/         escritura de capas + manifiesto
    api/            FastAPI, solo lectura de data/processed
    cli.py          `firecal <stage> <step>`
  tests/            unit (rápidos) y slow (marcados)
web/                pnpm, Vite, React, TypeScript, deck.gl
  src/i18n/         es.ts y en.ts: todos los textos de UI
  src/theme/        tokens (ver docs/design.md)
  e2e/              Playwright, con fixtures falsos
data/               raw/ interim/ processed/  (fuera de git)
reports/            informes por fase (reports/NN/<ID>.md)
Makefile            install, dev, test, lint
```

## Flujo

`io` descarga → `stages/*` calcula → `layers` publica en `data/processed/<layer_id>/` → API sirve → web dibuja.
Cada paso es un comando CLI idempotente (`firecal <stage> <step>`).

## Contrato de capas

`data/processed/<layer_id>/manifest.json`:

```json
{
  "id": "fire-grid",
  "title": "Focos de calor por celda",
  "kind": "events | points | grid | series | polygons",
  "source": "NASA FIRMS (MODIS C6.1, VIIRS 375 m)",
  "period": "2000-11-01/2026-08-31",
  "license": "NASA open data",
  "updated_at": "ISO-8601",
  "experimental": false,
  "files": ["grid.parquet"]
}
```

`experimental` es opcional. Tablas en Parquet/GeoParquet. La UI toma fuente y período del manifiesto. La API
valida el manifiesto con pydantic y solo sirve archivos listados en `files`.

## API

`GET /health` · `GET /layers` · `GET /layers/{id}` · `GET /layers/{id}/data` · `POST /calendar` ·
`POST /stats` · `POST /export.csv` (fase 3).

## Publicación estática

En línea no hay API: los resultados se precalculan por área (provincias y departamentos) y se suben como JSON a un
bucket (Cloudflare R2) con rutas que imitan las de la API; la web estática los lee cuando el build tiene
`VITE_DATA_URL` y, sin esa variable, usa `/api` como en local. Credenciales `R2_*` en el entorno o en `.env`.

## Tests

- Unit con datos sintéticos de resultado conocido (pytest, vitest).
- e2e con capas falsas en `web/e2e/fixtures/` (Playwright), sin depender de datos reales.
- `@pytest.mark.slow`: datos reales o corridas largas; fuera de CI.
- CI (GitHub Actions): ruff, pytest, eslint, tsc, vitest, Playwright.
