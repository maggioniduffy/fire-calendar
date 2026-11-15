# Phase 3 — Calendar and per-area analytics

Status: done (backend) · Depends on: 2 · Refs: `docs/architecture.md` (API)

## Goal

For an area and a date range, everything the challenge asks for: calendar, most active months and years, anomaly
of the current month, and CSV.

## Tasks

| ID | Task | Agent | Done when |
|---|---|---|---|
| SA3.1 | Area: GeoJSON polygon, or lat/lon + radius; size validation | Sonnet | Unit for valid and invalid area. Done ✅ (2026-11-15; circle of 5–500 km or GeoJSON polygon of 100 to 3,000,000 km² inside Argentina's bounding box; Córdoba preset = approximate rectangle, unverified) |
| SA3.2 | Year × month matrix of hot spots reported per sensor and harmonized in both scales (MODIS-eq, VIIRS-eq with 2000–2011 marked as estimated) | Sonnet | Unit on synthetic grid. Done ✅ (2026-11-15; on the published `harmonized` schema; area band = block band scaled by the area fraction and summed across blocks, unverified. Córdoba: VIIRS-eq estimated 2000-11 to 2012-01, 135 months) |
| SA3.3 | Climatology: median and p10–p90 per month; anomaly of the current month (absolute and in percentile) | Sonnet | Unit with known values. Done ✅ (2026-11-15; numpy linear quantiles over complete years, without the reference year; reference month = last available month, retrospective) |
| SA3.4 | Key figures: most active month and year, period total, comparison of the current month with the median | Sonnet | Unit. Done ✅ (2026-11-15; most active year only among complete years; the number of estimated months in the total is reported) |
| SA3.5 | Endpoints: `POST /calendar`, `POST /stats`, `POST /export.csv` | Sonnet | API unit + response with source and period. Done ✅ (2026-11-15; area or preset, range clipped to the layer's period, 422/503; meta with source, period, method, calibration, retrospective; real Córdoba: 2200 cells, /calendar 0.5 s) |
| SA3.6 | CSV: raw hot spots where they exist (Argentina), counts per cell elsewhere; calendar matrix | Sonnet | Unit: expected columns and rows. Done ✅ (2026-11-15; `kind` = calendar, cells or detections; raw hot spots come from `data/interim` with the phase 1 filters; estimated months only as counts per cell; with cell-center selection, MODIS hot spots match the series) |
