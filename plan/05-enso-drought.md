# Phase 5 — ENSO, drought and fire

Status: active for ENSO-lite only (SA5.2, SA5.4 without drought, SA5.5); SA5.1 and SA5.3 deferred · Depends on: 3, 0 (SA0.9) · Refs: `docs/validation.md`, `docs/research/data-sources.md` (ENSO)

## Question

Does the ENSO phase, through drought, change how much burns? Chain: ENSO → rainfall anomaly → drought → dry fuel →
hot spots. Hypothesis to measure, not to assert: in north-central Argentina La Niña brings drought and more hot
spots.

## Data

ONI (SA0.9), SPI/SPEI at 3 and 6 months (CHIRPS or ERA5, per SA0.8; licenses unverified), Copernicus CEMS FWI
(access unverified).

## Tasks

| ID | Task | Agent | Done when |
|---|---|---|---|
| SA5.1 | (deferred) Monthly SPI/SPEI per cell | Sonnet writes, opencode runs | Unit against published reference values |
| SA5.2 | Hot-spot calendar split by ENSO phase (median per month in El Niño, La Niña, Neutral) | Sonnet | Unit on a synthetic series |
| SA5.3 | (deferred) Lagged correlation ONI → SPEI → hot spots per region, with bootstrap CI | opencode analyzes, Sonnet codes | `reports/05/SA5.3.md` + lag unit |
| SA5.4 | UI: ENSO phase row under the calendar and area drought in the inspector (drought deferred), with source and period | Sonnet | e2e |
| SA5.5 | ENSO-lite: fire-season anomaly (per area) vs. ONI with lags 0–12 months; Spearman with block-bootstrap CI and a shuffled-years baseline; reported even when there is no signal and shown as "association", never as cause | Sonnet codes, cloud runs | `reports/05/SA5.5.md` + lag and shuffling units |
