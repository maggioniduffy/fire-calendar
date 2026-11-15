# Phase 5 — ENSO, drought and fire

Status: ENSO-lite done 2026-11-15 (SA5.2, SA5.4 without drought, SA5.5); SA5.1 and SA5.3 deferred · Depends on: 3, 0 (SA0.9) · Refs: `docs/validation.md`, `docs/research/data-sources.md` (ENSO)

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
| SA5.2 | Hot-spot calendar split by ENSO phase (median per month in El Niño, La Niña, Neutral) | Sonnet | Unit on a synthetic series. Done ✅ (`enso` block in `/calendar`) |
| SA5.3 | (deferred) Lagged correlation ONI → SPEI → hot spots per region, with bootstrap CI | opencode analyzes, Sonnet codes | `reports/05/SA5.3.md` + lag unit |
| SA5.4 | UI: ENSO phase row under the calendar and area drought in the inspector (drought deferred), with source and period | Sonnet | e2e. Done ✅ (2026-11-15, ENSO row only; drought deferred with SA5.1) |
| SA5.5 | ENSO-lite: fire-season anomaly (per area) vs. ONI with lags 0–12 months; Spearman with block-bootstrap CI and a shuffled-years baseline; reported even when there is no signal and shown as "association", never as cause | Sonnet codes, cloud runs | `reports/05/SA5.5.md` + lag and shuffling units. Done ✅ (2026-11-15: Córdoba no detectable association, family-wise p 0.30) |

## SA5.5 pre-registered design (fixed 2026-11-15, before the run)

Reviewed with the advisor. Fixed before the ONI–fire numbers are looked at; any later change is reported as a
deviation.

- **Primary family**: Córdoba preset, VIIRS-eq scale, raw season totals, lags 0–12. Exploratory (reported,
  not used for the headline): all of Argentina and approximate regions NOA, NEA, Pampas, Patagonia (lat/lon
  boxes, labelled approximate), MODIS-eq 2003–2023 (Aqua full years; Terra drift 2024–2025), log1p-detrended totals.
- **Fire season** per area: the 4 consecutive calendar months (circular, so Dec–Mar is allowed) with the highest
  climatological median total. Season labelled by the year of its first month; incomplete seasons dropped. If
  an area's monthly climatology is flat or bimodal (no window holds ≥ 40 % of the annual median total), use the
  Jul–Jun total instead and say so.
- **Lag k**: ONI value (already a 3-month mean dated at its central month) at season start − k months. No
  further averaging.
- **Statistic**: Spearman rho per lag. 95 % CI by moving-block bootstrap over seasons (block 3, 2000
  resamples), labelled "approximate, coverage unverified"; an iid pairs bootstrap reported beside it, and
  lag-1 autocorrelation of both series.
- **Shuffled-years baseline**: 5000 permutations of whole years (each season keeps its 13-lag ONI vector),
  one shared permutation across all areas. Per-lag p, and a family-wise p for max |rho| over the 13 lags of
  the primary family (and over all areas × lags for the exploratory set).
- **Era check**: Spearman on within-era ranks (estimated 2000–2011 vs observed 2012–2025) and an
  observed-only 2012–2025 run.
- **Language**: association, never cause. At n ≈ 25, per-lag significance needs roughly |rho| ≥ 0.4, and
  more family-wise: a null result means "not detectable with this sample", not "no association".
