# Phase 2 — MODIS–VIIRS harmonization

Status: active (SA2.6, SA2.8, SA2.9 and SA2.10 deferred) · Depends on: 1 · Refs: `docs/validation.md`

## Question

How do we turn 2000–today into a single series where the source sensor no longer matters, in both scales and
without breaking when MODIS stops operating?

## Approach

2012–today overlap: both sensors measure the same thing. VIIRS sees more small hot spots because of its
resolution (375 m vs. 1 km), and the overpass times differ. With that period we calibrate in both directions:

- **Toward MODIS:** VIIRS → "MODIS-equivalent". Long series, comparable with the literature.
- **Toward VIIRS (inverse series):** MODIS → "VIIRS-equivalent" for 2000–2011. Estimates how many hot spots VIIRS
  would have recorded in an area and period, with uncertainty; it does not locate individual hot spots that MODIS
  did not detect. In the UI it says "estimated" (`estimado`), never "detected".
- **Continuity:** when MODIS is switched off, each new year of VIIRS (S-NPP, NOAA-20, NOAA-21 and later JPSS,
  dates unverified) enters both series with the calibration frozen.

Supervised, not reinforcement learning: there are observed pairs (MODIS and VIIRS, same cell and day) and there is
no agent, environment or reward.

## Tasks

| ID | Task | Agent | Done when |
|---|---|---|---|
| SA2.1 | VIIRS regrouped into 1 km cells per day (one detection per cell), pairs of similar overpasses (Aqua ~ S-NPP) | Sonnet | Unit: N detections in one cell count as 1 |
| SA2.2 | Baseline: MODIS/VIIRS scale factor per region and month of the year, in both directions | Sonnet | Unit with synthetic data of known factor |
| SA2.3 | Quantile matching per region | Sonnet | Unit: recovers the target distribution on synthetic data |
| SA2.4 | LightGBM toward MODIS: MODIS-equivalent count from VIIRS counts by confidence, FRP, day/night, month, latitude, land cover | Sonnet implements, opencode trains | Error per test year vs. SA2.2 and SA2.3 |
| SA2.5 | Leave-one-year-out validation with gap and nested selection (`docs/validation.md`) | Sonnet | Unit: no test day in training |
| SA2.6 | (deferred) Effect of Terra and Aqua orbital drift in recent years (magnitude unverified) | opencode | `reports/02/SA2.6.md` with figures |
| SA2.7 | Inverse series: LightGBM with Poisson or Tweedie objective that estimates VIIRS counts per cell and day from MODIS count and FRP, scan angle, day/night, month, land cover and hot spots of neighboring days; intervals by quantile regression | Sonnet implements, opencode trains | Error and interval coverage per test year vs. inverse SA2.2 |
| SA2.8 | (deferred) Backward validation: train from 2016 onward and evaluate on 2012–2015, to simulate estimating the past and see whether the relationship changes over time | Sonnet | Error table per region and year; unit: no test year in training |
| SA2.9 | (deferred) MCD64A1 burned areas (2000–) as a SA2.7 variable for fires that MODIS did not flag as hot spots; Landsat only if SA0.8 confirms access and coverage | Sonnet writes, opencode runs | SA2.7 error with and without the variable |
| SA2.10 | (deferred) Post-MODIS continuity: calibration frozen with version and date; ingesting a new VIIRS year updates both series without recalibrating | Sonnet | Unit: adding a year does not change previous values |
| SA2.11 | Final series in two scales (MODIS-eq and VIIRS-eq) with uncertainty band; manifest with method, calibration version, source and period | Sonnet | Published layer + load e2e |

## Deliverable

Error table per method, direction and region, including backward validation. The method that wins on test is
published; if LightGBM does not beat the scale factor, we report it and use the factor. Observed 2000–today trend
per region with its interval; no projection of decades (it requires climate scenarios, out of scope).
