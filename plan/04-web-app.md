# Phase 4 — Web app

Status: active (SA4.10–SA4.14 opened 2026-11-15) · Depends on: 0, 3 · Refs: `docs/design.md`

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
| SA4.5 | Inspector: SA3.4 figures, series selector: reported per sensor, MODIS-equivalent or VIIRS-equivalent (2000–2011 marked "estimated"), calibration version, source and period | Sonnet | e2e — **done 2026-11-15** (Reported = per-sensor columns of `/calendar`; ENSO row hidden until phase 5) |
| SA4.6 | CSV downloads (hot spots and calendar) | Sonnet | e2e: the file downloads with the SA3.6 columns — **done 2026-11-15** (hot-spot button is removed after the first 404) |
| SA4.8 | "Dashboard" view of the selected area (tab next to the map), charts linked to each other and to the calendar: harmonized monthly series with uncertainty band and per-sensor series; totals per year; seasonality (median and p10–p90 per month with the current year on top); monthly anomaly; day/night split and FRP distribution; ENSO phase and drought (if phase 5 exists). Each chart with source and period, exportable as PNG and CSV | Sonnet | e2e: choose area → charts with the same totals as SA3.4; vitest of scales — **done 2026-11-15** (day/night, FRP and ENSO charts deferred: no payload provides them) |
| SA4.7 | Accessibility: AA contrast, keyboard, visible focus, phone width | Sonnet | Playwright + axe with no errors — **done 2026-11-15** (`e2e/a11y.spec.ts`; keyboard-only polygon drawing out of scope, lat/lon + radius is the keyboard alternative) |
| SA4.9 | Calendar strip readable on desktop: grid turned sideways (years across, months down, summary/toggle/legend in a side column) and a drag handle to resize the strip (pointer + keyboard, height kept in `localStorage`, hidden at phone width) | Opus + Sonnet | vitest of the arrow keys + e2e of drag, keyboard, reload and layout — **done 2026-11-15** |
| SA4.10 | Shell: top bar removed; hover header at the top edge (icon + "Fire Calendar - NASA Space Apps Challenge"); settings gear bottom-left opening a modal (theme, language, challenge, author); flame emblem as favicon and app icon | Codex | vitest of the modal + e2e of hover header and settings — **done 2026-11-15** |
| SA4.11 | Calendar Nov–Dec rows hidden under the ENSO strip at 1440×720 (hover blocked) | Codex | e2e: hover on Nov and Dec shows the tooltip at 1440×720 — **done 2026-11-15** (rows shrink to fit with the ENSO row; scroll only at the minimum strip height; gear clears the legend) |
| SA4.12 | API `/cells` and `/detections` over a range (start→end) or a season (months × year span); single-month answers unchanged | Codex | pytest: range = sum of months, season filter, total = `/calendar` sum, month regression — **done 2026-11-15** (detections over the cap are an evenly spaced sample for ranges and seasons) |
| SA4.13 | Static export: raw detections as 1° tiles per month; static client sums cells and loads detections for ranges and seasons | Codex | pytest of the tile writer + vitest of the static client; export size reported — **done 2026-11-15** (5° tiles by default: ~22 files per month instead of ~233, to stay under the Pages file limit) |
| SA4.14 | Period selection UI: month, range (shift-click or pickers), season; map overlay shows period and summed total | Codex | vitest of reducer/request + e2e on API and static fixtures |
