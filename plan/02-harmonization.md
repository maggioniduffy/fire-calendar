# Phase 2 — MODIS–VIIRS harmonization

Status: closed on 2026-11-15 (SA2.6, SA2.8, SA2.9 and SA2.10 deferred) · Depends on: 1 · Refs: `docs/validation.md`

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

## Baseline design (decided 2026-11-14, with advisor consultation)

Everything below is design; the assumptions about the data stay "unverified" until the first real run.

- **Scales:** MODIS = Terra + Aqua; VIIRS = S-NPP only. NOAA-20 is never added to S-NPP: it enters through a
  NOAA-20→S-NPP transfer factor fitted from 2018-05, which is chained for continuity. The partial months 2012-01
  and 2018-04 are excluded. Day and night are fitted separately and summed. Months with Terra only (before Aqua)
  need a Terra-only factor.
- **Count:** the one the calendar shows: detections after `FilterConfig`, as they come out of the 0.1° grid. The
  table of 1 km cells per day (SA2.1, Aqua ~ S-NPP pair) is kept for LightGBM and as a diagnostic. All methods are
  evaluated on the same count.
- **Region:** 2.5° lat/lon blocks (origin −90/−180, they nest with both grids, no new data).
- **Unit:** fitted on sums per region × month of the year × day/night; evaluated per region-month of each test
  year and per region-year total.
- **Estimator (SA2.2):** ratio of sums, with shrinkage toward the national factor of the same month and day/night:
  `f = (M + k·f_national) / (V + k)`, with `k` chosen inside the training set. Intervals from the dispersion of
  the leave-one-year-out factors, not from the Poisson variance.
- **Metrics** (the same for ML later), per test year, region and direction: relative bias (Σpred/Σobs − 1), WAPE,
  MAE, mean Poisson deviance and, in the inverse series, interval coverage.
- **Quantile matching (SA2.3):** on region-month totals, pooling the months of the year; zero maps to zero and
  only the positives are fitted; above the training maximum, constant ratio. It is not additive, so it is not
  applied cell by cell: it serves to see whether the ratio depends on the activity level.
- **Stability (MODIS version and orbital drift):** year and `version` do not enter the baseline. With the first
  run a table is published: factor per year (national and per block, by day/night and by Terra and Aqua),
  NOAA-20/S-NPP per year as a control without MODIS, Terra/Aqua per year, mean acquisition time per satellite and
  year, and the rolling-origin control. If a step appears in 2018 or 2023 with the VIIRS control flat, it is
  adjusted per epoch and the inverse series is calibrated only with 2012–2017 (same `version` as 2000–2011), and
  SA2.8 is resumed.

- **Finding 2026-11-14 (`docs/research/data-sources.md`):** since 2018 MODIS flags more hot spots as `type` 2
  (static source), so the `type == 0` filter removes 3–4 points more than before. The stability table is computed
  with and without the `type` filter to measure how much of the step comes from there.

- **First run (2026-11-14, [reports/02/baselines.md](../reports/02/baselines.md)):** the scale factor (SA2.2)
  beats quantile matching (SA2.3) in both directions: leave-one-year-out block-month WAPE 17.2 % vs. 19.4 %
  (VIIRS→MODIS) and 17.9 % vs. 19.4 % (MODIS→VIIRS); the rolling-origin control agrees. National VIIRS→MODIS
  factor 0.302 (day 0.360, night 0.147). No clear step in 2018 or 2023: the `type` filter moves the 2018 ratio
  from 0.308 to 0.302. Open: (1) the inverse-series intervals cover 26 % (jackknife) and 54 % (interannual
  dispersion) against a nominal 80 %; intervals that include the count noise are needed before SA2.11; (2) in
  2024–2025 the Terra/Aqua ratio drops (0.59 → 0.41) and Terra's mean overpass time moves earlier (13:55 → 13:15
  UTC by day) while S-NPP and NOAA-20 stay fixed: compatible with Terra orbital drift, cause unverified. The
  total MODIS series (Terra + Aqua) shows no step in those years.

## LightGBM design (SA2.4 and SA2.7, decided 2026-11-14 before running, with advisor consultation)

- **Unit:** 0.1° cell × month × day/night, only rows with some active sensor; predictions are summed to
  block-month to evaluate the same way as SA2.2. Second cheap candidate: LightGBM directly on block-month, heavily
  regularized, to separate how much comes from the resolution and how much from the variables. Cell-day
  discarded (different overpass times and little coincidence at 1 km). Measured in 2020: 52,316 active rows; 17 %
  of S-NPP detections fall in rows without MODIS.
- **Base:** the baseline enters as an offset, `init_score = log(f_block × source + ε)`, with the source smoothed
  over 3×3 for rows without source. With zero trees the model reproduces SA2.2; it is checked that block totals
  match SA2.2 within ~1 %. The factor used in the training rows comes from an inner leave-one-year-out
  (out-of-sample), never fitted on those same rows.
- **Variables:** source counts and FRP per satellite and day/night, FRP per detection, day/night share, source
  count over 3×3, source total in the block, month of the year. With and without the Terra/Aqua ratio (Terra
  changes in 2024–2025 and Aqua does not exist before 2002-07). Lat/lon only in an ablation. Out: year,
  `version`, previous month. Every SA2.7 variable has to exist in 2000–2011 (MODIS only). No land cover (SA0.8
  pending) and no scan angle (there is no `scan`).
- **Hyperparameters:** small grid chosen inside each outer training set by inner leave-one-year-out block-month
  WAPE; few threads, under 4 GB.
- **Intervals:** the same nested conformal scheme as the baseline applied to the point prediction, to compare
  coverage and width with SA2.2. Quantile LightGBM only as a block-month-level diagnostic.
- **Publication criterion (fixed before the run), per direction; LightGBM is published only if it meets all:**
  leave-one-year-out block-month WAPE at least 1 point lower than SA2.2 and block-year no higher; lower
  block-month WAPE in at least 10 of 14 test years; improvement of the same sign with rolling origin; total
  |bias| no worse than SA2.2's + 0.5 points and the worst year no worse; block-month Poisson deviance no worse;
  in SA2.7, coverage 80 ± 5 % and width no larger; the paired bootstrap interval (by year and block) of the WAPE
  difference excludes zero. Otherwise the report says "does not beat the factor" and SA2.2 is published.

- **LightGBM (2026-11-15, [reports/02/baselines.md](../reports/02/baselines.md)):** does not beat the factor in
  either direction under the fixed criterion; the `harmonized` layer stays with SA2.2. VIIRS→MODIS came close
  (cell: block-month WAPE 15.9 % vs 17.2 %, 12 of 14 years, but bias −2.5 %; block-month: bootstrap with limit
  +0.02). The first SA2.7 run diverged numerically; `max_delta_step = 1` was added after that run (it was not in
  the prior design, applies to both directions) along with a prediction check. Open: grid reduced for time. Cell
  model bias verified ([reports/02/ml_bias_check.md](../reports/02/ml_bias_check.md)): structural in the total
  (in its rows +0.06 % and −0.54 %), not in individual years; the worst SA2.4 year (2024) is hard for SA2.2 too.

## Tasks

| ID | Task | Agent | Done when |
|---|---|---|---|
| SA2.1 | VIIRS regrouped into 1 km cells per day (one detection per cell), pairs of similar overpasses (Aqua ~ S-NPP) | Sonnet | Unit: N detections in one cell count as 1. Done ✅ (2026-11-14; in 2020, of 71,819 Aqua cell-days only 29,937 have S-NPP in the same 0.01° cell: exact coincidence at 1 km is low and SA2.4/SA2.7 will need a neighborhood) |
| SA2.2 | Baseline: MODIS/VIIRS scale factor per region and month of the year, in both directions | Sonnet | Unit with synthetic data of known factor. Done ✅ (2026-11-14; [reports/02/baselines.md](../reports/02/baselines.md)) |
| SA2.3 | Quantile matching per region | Sonnet | Unit: recovers the target distribution on synthetic data. Done ✅ (2026-11-14; loses to SA2.2 in both directions) |
| SA2.4 | LightGBM toward MODIS: MODIS-equivalent count from VIIRS counts by confidence, FRP, day/night, month, latitude, land cover | Sonnet implements, opencode trains | Error per test year vs. SA2.2 and SA2.3. Done ✅ (2026-11-15): does not beat the factor; cell fails the bias (−2.5 % vs +0.9 %), block-month fails the bootstrap (+0.02) |
| SA2.5 | Leave-one-year-out validation with gap and nested selection (`docs/validation.md`) | Sonnet | Unit: no test day in training. Done ✅ (2026-11-14; leave-one-year-out with gap and rolling origin) |
| SA2.6 | (deferred) Effect of Terra and Aqua orbital drift in recent years (magnitude unverified) | opencode | `reports/02/SA2.6.md` with figures |
| SA2.7 | Inverse series: LightGBM with Poisson or Tweedie objective that estimates VIIRS counts per cell and day from MODIS count and FRP, (no scan angle: the standard file carries no `scan`), day/night, month, land cover and hot spots of neighboring days; intervals by quantile regression | Sonnet implements, opencode trains | Error and interval coverage per test year vs. inverse SA2.2. Done ✅ (2026-11-15): does not beat the factor (cell fails all; block-month fails 1, 4 and 7) |
| SA2.8 | (deferred) Backward validation: train from 2016 onward and evaluate on 2012–2015, to simulate estimating the past and see whether the relationship changes over time | Sonnet | Error table per region and year; unit: no test year in training |
| SA2.9 | (deferred) MCD64A1 burned areas (2000–) as a SA2.7 variable for fires that MODIS did not flag as hot spots; Landsat only if SA0.8 confirms access and coverage | Sonnet writes, opencode runs | SA2.7 error with and without the variable |
| SA2.10 | (deferred) Post-MODIS continuity: calibration frozen with version and date; ingesting a new VIIRS year updates both series without recalibrating | Sonnet | Unit: adding a year does not change previous values |
| SA2.11 | Final series in two scales (MODIS-eq and VIIRS-eq) with uncertainty band; manifest with method, calibration version, source and period | Sonnet | Published layer + load e2e. Done ✅ (2026-11-15; `harmonized` layer with frozen calibration `sf-2026.11.1` of the SA2.2 factor and conformal bands per block-month and block-year; API unit; the web load e2e is left for phase 4; MODIS-eq from NOAA-20 once MODIS and S-NPP end has no band) |

## Deliverable

Error table per method, direction and region, including backward validation. The method that wins on test is
published; if LightGBM does not beat the scale factor, we report it and use the factor. Observed 2000–today trend
per region with its interval; no projection of decades (it requires climate scenarios, out of scope).
