# Phase 3 — Calendar and per-area analytics

Status: active · Depends on: 2 · Refs: `docs/architecture.md` (API)

## Goal

For an area and a date range, everything the challenge asks for: calendar, most active months and years, anomaly
of the current month, and CSV.

## Tasks

| ID | Task | Agent | Done when |
|---|---|---|---|
| SA3.1 | Area: GeoJSON polygon, or lat/lon + radius; size validation | Sonnet | Unit for valid and invalid area |
| SA3.2 | Year × month matrix of hot spots reported per sensor and harmonized in both scales (MODIS-eq, VIIRS-eq with 2000–2011 marked as estimated) | Sonnet | Unit on synthetic grid |
| SA3.3 | Climatology: median and p10–p90 per month; anomaly of the current month (absolute and in percentile) | Sonnet | Unit with known values |
| SA3.4 | Key figures: most active month and year, period total, comparison of the current month with the median | Sonnet | Unit |
| SA3.5 | Endpoints: `POST /calendar`, `POST /stats`, `POST /export.csv` | Sonnet | API unit + response with source and period |
| SA3.6 | CSV: raw hot spots where they exist (Argentina), counts per cell elsewhere; calendar matrix | Sonnet | Unit: expected columns and rows |
