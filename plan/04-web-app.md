# Phase 4 — Web app

Status: active (SA4.8 last) · Depends on: 0, 3 · Refs: `docs/design.md`

## Goal

The challenge app with the layout of the design canvas: choose area and period, see the fire history and download
it.

## Tasks

| ID | Task | Agent | Done when |
|---|---|---|---|
| SA4.1 | Area: draw on the map, enter lat/lon + radius, "Use my location" (asks permission; default radius ~230 km); initial view: Córdoba province | Sonnet | e2e of each mode; without permission it stays on Córdoba — **done 2026-11-15** (keyboard-only drawing open for SA4.7) |
| SA4.2 | deck.gl map with hot spots (raw or cells depending on zoom) and the selected area | Sonnet | e2e: changes when the area moves — **done 2026-11-15** (zoom ≥ 8 detection mode covered by backend tests only) |
| SA4.3 | Calendar: year × month heatmap with a colorblind-safe sequential ramp; tooltip with count and source | Sonnet | e2e + vitest of the color scale — **done 2026-11-15** |
| SA4.4 | Anomalies: year × month vs. median with a blue/orange diverging ramp; current month highlighted with the accent | Sonnet | e2e — **done 2026-11-15** |
| SA4.5 | Inspector: SA3.4 figures, series selector: reported per sensor, MODIS-equivalent or VIIRS-equivalent (2000–2011 marked "estimated"), calibration version, source and period | Sonnet | e2e |
| SA4.6 | CSV downloads (hot spots and calendar) | Sonnet | e2e: the file downloads with the SA3.6 columns |
| SA4.8 | "Dashboard" view of the selected area (tab next to the map), charts linked to each other and to the calendar: harmonized monthly series with uncertainty band and per-sensor series; totals per year; seasonality (median and p10–p90 per month with the current year on top); monthly anomaly; day/night split and FRP distribution; ENSO phase and drought (if phase 5 exists). Each chart with source and period, exportable as PNG and CSV | Sonnet | e2e: choose area → charts with the same totals as SA3.4; vitest of scales |
| SA4.7 | Accessibility: AA contrast, keyboard, visible focus, phone width | Sonnet | Playwright + axe with no errors |
