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

## Completion plan (2026-11-15)

Approved by the user on 2026-11-15; saved here at step 0 so it is in the repo. Phase 2 is reopened for SA2.6,
SA2.8, SA2.9 and SA2.10, with SA1.6 (recent data) from phase 1.

### Context

The core differential of the challenge is one harmonized MODIS + VIIRS series that keeps going after MODIS. Before
this plan the published layer (calibration `sf-2026.11.1`, SA2.2 scale factor) stops at 2025-12, NOAA-21 is not in
the pipeline, the calibration was frozen only by convention (tracked in `backend/calibrations/`, no guard),
MODIS-eq after MODIS has no validated band, and the Terra/Aqua drift is unexplained.

Facts as of 2026-11-15 (FIRMS `data_availability` with the key):

- Standard processing (SP) through the area API: MODIS to 2026-08-31; VIIRS S-NPP, NOAA-20 and NOAA-21 to
  2026-07-31 (NOAA-21 SP from 2023-03-01). NRT after that to today (MODIS_NRT from 2026-09-01, VIIRS NRT from
  2026-08-01). S-NPP ended on 2026-11-02. Per-country files exist only to 2025 (NOAA-21 country files: 404).
- Area API: at most 5 days per request, 5000 requests per 10 minutes, bounding box only (needs clipping to
  Argentina). BA_MODIS through the area API returned only a header.
- Advisor review: Aqua drifts too (Terra daytime 14:22 -> 13:15 UTC and Aqua 18:01 -> 19:08 between 2018 and
  2025; Terra/S-NPP falls, Aqua/S-NPP rises and they partly cancel); every year up to 2025 is in-sample for
  `sf-2026.11.1`; NRT rows have no `type`, so the default `FilterConfig` (types=(0,), keep_missing_type=False)
  drops them all; refitting cannot keep the old pairs identical (`fit_calibration` takes the blocks of the whole
  cube and re-selects `k`).
- Code map: NOAA-21, NRT, the area API and MAP_KEY are absent from `backend/src`; `PRODUCTS` (io/firms.py),
  `_VIIRS_SATELLITE`, `SATS` (harmonize/series.py) and `regions.SATELLITES` are hard-coded (a `noaa21` column would
  be dropped silently by `wide_counts`); ingest parses the year from the file name; grid groups by satellite and
  reads every product=*/year=*, so SP and NRT would be summed; `sensor_months` treats any month with one row as
  complete; `save_calibration` overwrote silently and `publish` re-saved it; `OVERLAP_END = 2025-12` in
  evaluate.py; `band_block_year` of the current year changes as months are added; the manifest source text is
  hard-coded.

Outcome: a pre-registered, validated post-MODIS continuity with honest error numbers, the series extended into 2026
(SP, then NRT flagged provisional), drift and backward-validation reports, and a new immutable calibration
`sf-2026.11.2` built by extension of `.1`. The static export is regenerated afterwards (not deployed).

### Steps

0. **Freeze guard and pre-registration** (first commit, before any 2026 data). `save_calibration` refuses an
   existing version; `series build`/`publish` verify the sha256 against `backend/calibrations/`; `series calibrate`
   requires an explicit new version. Pre-registration below; the advisor reviews it before step 1 results are
   looked at.
1. **SA2.6 drift diagnostics + SA2.8 backward validation** (existing data, in parallel).
   - SA2.6: per-year table by satellite and day/night: overpass time, Terra/S-NPP, Aqua/S-NPP, MODIS/S-NPP,
     NOAA-20/S-NPP control; factors fitted with and without drift years; observed MODIS vs VIIRS-derived MODIS-eq
     2022–2025 (association). `terra_to_viirs` evaluated separately (most exposed: applied to 2000–2002). Output
     `reports/02/SA2.6.md`, generated by code.
   - SA2.8: train 2016+, test 2012–2015 with the `harmonize/evaluate.py` machinery, per block and year, with and
     without drift years; paired bootstrap. Output `reports/02/SA2.8.md`.
   - Decision by the pre-registered criterion. Observed MODIS 2022+ flagged "orbit drift (unverified cause)".
2. **SA1.6 recent data** (in parallel with step 1).
   - `firecal firms area`: SP (2026-01 to SP end) then NRT (after) for MODIS, S-NPP, NOAA-20 and NOAA-21 (also
     NOAA-21 SP from 2023-03 for its overlap fit) over the Argentina bbox in 5-day chunks, `FIRMS_MAP_KEY` from the
     environment; NRT raw archived on download (it rolls off the API); idempotent per chunk; retries.
   - Clip to Argentina with the geoBoundaries ADM2 union. Validation: API-SP 2025 clipped vs the 2025 country
     files, row match both ways per satellite; stop and document if the mismatch exceeds tolerance or is off the
     border.
   - Products carry a processing level (sp/nrt, source country/api) under `interim/firms/detections/`; the grid
     picks per satellite x month country-SP > API-SP > NRT and never sums. When 2026 country files appear: a
     documented re-issue, source recorded per year.
   - NRT static-source mask built from SP history (recurrence of `type` != 0 per cell), validated on SP 2025
     (`type == 0` count vs no-type + mask, per block and day/night); the residual is published as the NRT proxy
     bias.
   - Completeness: days with detections per satellite-month; the in-progress month is excluded; partial months
     are flagged.
3. **SA2.10 continuity** (after steps 1–2).
   - NOAA-21: product `viirs-jpss2`, satellite `noaa21`, added everywhere listed above without disturbing old
     pairs.
   - `sf-2026.11.2` by extension of `.1`: load `.1`, append `noaa21_to_snpp` (SP overlap 2023-03..2026-07, both
     sides from the same API path), `noaa21_to_noaa20`, and the end-to-end chain route NOAA-20 -> S-NPP -> MODIS
     with its own conformal residuals (inner leave-one-year-out, both factors out-of-fold), indexed on `.1`'s
     blocks; a test checks that `.1` pairs serialize identically. Never fitted on NRT rows.
   - Series rules: VIIRS-eq after S-NPP = NOAA-20 transferred; NOAA-21 only as a whole-month national fallback; no
     averaging. MODIS-eq after MODIS = chain with its band. Status adds `provisional` (NRT) and the source per
     month; S-NPP Aug–Oct 2026 is NRT only (observed but provisional).
   - Headline validation ("MODIS-off simulation") and frozen-artifact check as pre-registered below. MODIS-eq
     means "MODIS as in the calibration period".
   - Unit tests: adding a month or year never changes earlier SP rows within a version; NRT rows change only when
     their processing level changes; calibration overwrite refused; sha mismatch refused.
   - Output `reports/02/SA2.10.md`; manifest source text and NOTES_ES/NOTES_EN updated; web status badges for
     provisional months (Spanish first, full English) with e2e.
4. **SA2.9 burned areas** (research, in parallel, low cost): check FIRMS BA_MODIS/BA_VIIRS, UMD MCD64A1, ESA
   FireCCI, GWIS; if none is reachable without new credentials, mark blocked with the reason.
5. **Close**: rebuild the series with `.2`, re-run `make static-export` and the static e2e (no deploy); README
   method and error section with the continuity numbers; tasks marked here, in `plan/01-data.md` (SA1.6) and in
   `plan.md`.

Verification: `make backend-test`, `make backend-lint`, web `pnpm test`, `pnpm typecheck`, `pnpm lint`,
`pnpm e2e --trace off`; real run of the full pipeline with 2026 data; SA2.6, SA2.8 and SA2.10 reports generated
by code; clip check and NRT proxy inside tolerance; Córdoba calendar to the latest complete month with
provisional months marked; calibration sha check passes and an overwrite attempt fails.

## Pre-registration (2026-11-15, fixed before any step 1 result or 2026 data is looked at)

What was already seen when this was written: everything in `reports/02/baselines.md` (including the per-year
ratio tables and the mean acquisition time table), the FIRMS availability dates above. Not yet seen: any factor
fitted without drift years, any SA2.8 number, any 2026 detection, any forward-holdout or chain number. Nothing
below is changed after those are seen; a deviation found necessary is written as a dated "deviation" line with its
reason, and the original rule is still reported.

Common definitions: the count, filters, 2.5° blocks, metrics (relative bias = Σpred/Σobs − 1, WAPE =
Σ|pred − obs|/Σobs, Poisson deviance), the SA2.2 estimator with `k` selected inside the training set, and the
nested conformal intervals are those of `reports/02/baselines.md`. Day and night are fitted separately and summed.
"Block-year" = sum over the months of a test year of one block. Paired bootstrap: years and blocks resampled
separately, 1000 resamples, seed 20261114, 95 % percentile interval; "excludes zero" means the whole interval is on
the favourable side.

### P1. Headline metrics

- **Continuity (SA2.10, the headline):** MODIS-eq computed from NOAA-20 (the route that runs after MODIS and
  S-NPP end), against observed MODIS (Terra + Aqua), on forward holdouts: **block-year WAPE** (primary), national
  relative bias and block-month WAPE (secondary), block-year conformal coverage and relative width (nominal 80 %,
  acceptable 75–85 %).
- **SA2.8:** block-year WAPE and relative bias per test year 2012–2015 and pooled, both main directions
  (VIIRS -> MODIS and MODIS -> VIIRS), plus `terra_to_viirs`.
- **SA2.6:** descriptive (tables); the only decision is P4.

### P2. Forward holdouts ("MODIS-off simulation")

- Cut-offs: end of 2021, 2022, 2023 and 2024. For each cut-off, every factor in the route (S-NPP -> MODIS,
  NOAA-20 -> S-NPP, and the direct NOAA-20 -> MODIS comparator) is refitted, with `k` re-selected by the inner
  leave-one-year-out, on overlap months up to the cut-off only (NOAA-20 pairs from 2018-05). Test: every full
  calendar year after the cut-off up to 2025, and 2026-01..2026-07 (SP, both sensors) as a separate partial block.
- No gap between training and test in the forward holdouts: it mimics deployment, where the frozen calibration is
  applied from the month after its fitted period. The leave-one-year-out with a 6-month gap (as in SA2.5) is run
  alongside, over 2018-05..2025-12, for the same route.
- Error is reported by years since the cut-off (1, 2, 3, 4) pooled over cut-offs, and per cut-off. Test years
  2018–2021 and 2022–2025 are reported separately in the leave-one-year-out (drift epoch vs before).
- The forward holdouts are scored once with this protocol; they choose the route (P5), nothing else.

### P3. Drift epoch rule

- Per satellite (Terra, Aqua) and per year: mean daytime acquisition time (UTC) of the detections after the
  default filter. A year is in that satellite's drift epoch when it differs from the satellite's 2003–2020 mean
  by more than 15 minutes; the epoch starts at the first such year and includes every later year.
- For pairs involving MODIS (Terra + Aqua), the drift years are the union of the Terra and Aqua epochs; for
  `terra_to_viirs` only Terra's.
- Expectation from the rounded table (not a result, the code decides on unrounded times): Terra 2023+ (2022 is
  about 14.8 minutes off), Aqua 2024+.

### P4. Recalibration criterion (main pairs `viirs_to_modis`, `modis_to_viirs`; `terra_to_viirs` separately)

The main pairs are changed only if both hold:

1. Dropping the drift years moves the national factor (ratio of sums over 2012-02..2025-12, day and night summed)
   by more, in absolute value, than dropping any other contiguous window of the same number of years inside
   2012–2025 (windows overlapping the drift window are excluded from the comparison).
2. In SA2.8 (train 2016+, test 2012–2015), training without the drift years is no worse than training with them on
   pooled block-year WAPE and on pooled |bias|, and better on at least one of the two, with the paired bootstrap
   interval of that difference excluding zero.

Otherwise the result is reported only. In either case nothing changes inside `sf-2026.11.2`: `.2` keeps `.1`'s
pairs byte for byte; a recalibration, if warranted, goes to a later version with its own report. Observed MODIS in
drift years is flagged "orbit drift (unverified cause)" regardless of the outcome.

### P5. Chain vs direct comparator

- Chain: NOAA-20 -> S-NPP (`noaa20_to_snpp`) then S-NPP -> MODIS (`viirs_to_modis`), each with its own block
  factors. Direct baseline: one NOAA-20 -> MODIS factor (same estimator, same `k` selection), fitted on
  2018-05..cut-off.
- The chain is published only if, on the P2 forward holdouts pooled over cut-offs and years, its block-year WAPE is
  lower than the direct factor's and its |national bias| is not worse by more than 0.5 points. Otherwise the
  report says the chain does not beat the direct factor and the direct factor is published as the MODIS-eq route
  after MODIS (in `.2`, as an added pair; `.1` pairs untouched).
- The published route gets its own conformal residuals (inner leave-one-year-out, every factor of the route
  out-of-fold) for block-month and block-year bands.

### P6. NRT static-source mask acceptance

- NRT rows have no `type`. The mask removes NRT detections falling in cells where SP history shows recurrent
  non-vegetation sources (`type` != 0). Cell size and recurrence threshold are chosen from a small grid (cells
  0.01° or 0.02°; recurrence in at least 2, 3 or 5 distinct years) on SP 2012–2024, by the smallest national
  |bias| of (all-type count minus masked) vs `type == 0` count on SP 2024; then scored once on SP 2025.
- Accepted if on SP 2025, per satellite and day/night, the national relative bias of the proxy count vs the
  `type == 0` count is within ±3 %, and block-year |bias| is within ±10 % in blocks with at least 100 `type == 0`
  detections. The 2025 residual (national and per block) is published as the NRT proxy bias.
- If not accepted: NRT months are not entered into the series; they are listed as "pending standard processing".

### P7. Clip tolerance (area API bbox -> Argentina)

- API-SP 2025 clipped with the geoBoundaries ADM2 union vs the 2025 country files, matched per satellite on
  (acq_date, acq_time, latitude, longitude rounded to 4 decimals). Accepted if, per satellite, the unmatched rows
  in each direction are under 0.5 % of the country-file rows, and at least 95 % of the unmatched rows lie within
  5 km of the Argentina boundary. Otherwise stop, document and do not use API data until it is resolved.

### P8. Completeness

- A satellite-month enters the series only if the source window covers the whole month (data end date ≥ last day
  of the month) and the number of days with at least one detection (before filters, clipped to Argentina) is at
  least 90 % of the median for that calendar month and satellite over SP 2012–2025 (MODIS satellites over
  2003–2025). The in-progress month is never included. A closed month below the threshold is flagged `partial`
  and left out of the series (as `PARTIAL_MONTHS` already does).

### P9. Frozen-artifact check

- `.1` (and `.2` for its added pairs) applied unchanged to 2026-01..2026-07 SP (MODIS and VIIRS both SP), scored
  once by leg: S-NPP -> MODIS, NOAA-20 -> S-NPP, and the published NOAA-20 -> MODIS route; block-month and
  block-year (7 months) WAPE, national bias, band coverage. Reported as is; it changes no decision. MODIS in 2026
  is in the drift epoch, so this measures "MODIS as in the calibration period" against a drifted MODIS, and the
  report says so.
