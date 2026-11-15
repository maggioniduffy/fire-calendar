# fire-calendar

Harmonized MODIS + VIIRS fire calendar for Argentina. Built around the CONAE challenge of the NASA Space Apps
Challenge 2026, "Harmonization of MODIS and VIIRS Hot Spots" (COR-CAT-08, Córdoba venue). It is not competing:
no hackathon deadline applies. Author: Faustino Maggioni Duffy.

Status: phases 0 to 5 (ENSO-lite) are implemented; publication (phase 7) is in progress. See [plan.md](plan.md).

## Problem

MODIS (Terra and Aqua) and VIIRS (S-NPP and NOAA-20, 375 m) both report active-fire hot spots through NASA
FIRMS, but their counts are not comparable. On the Argentine data used here, S-NPP yields about 3.3 times more
hot spots than MODIS in the overlap period 2012-02 to 2025-12 (night: about 6.8; day: about 2.8), because VIIRS has
finer resolution (375 m vs. 1 km) and the overpass times differ
([plan/02-harmonization.md](plan/02-harmonization.md)). A raw count series that switches from MODIS to VIIRS therefore shows a step that is not a change in fire activity.

A harmonized series from 2000 to today, in the scale of either sensor, lets trends and anomalies be read across the
sensor change. This matters because MODIS is being retired: per the Earthdata notice
([MODIS to VIIRS transition](https://www.earthdata.nasa.gov/data/alerts-outages/transition-from-modis-viirs)),
Terra and Aqua start shutting down operations in late 2026 or early 2027 (exact date and effect of orbital drift:
unverified), and VIIRS continues. S-NPP stopped producing in FIRMS on 2026-11-02; continuity then relies on
NOAA-20 and NOAA-21.

## What the product is

- A Python pipeline (`backend/`) that builds a harmonized hot-spot series in two scales: MODIS-equivalent and
  VIIRS-equivalent (the latter keeps going when MODIS ends).
- A web app (`web/`) with a year × month calendar, anomalies against the climatology, an ENSO phase row, a
  dashboard tab and CSV download. The initial view is Córdoba province, or an area of similar size around the user
  if they agree to share their location.
- Data covers all of Argentina (FIRMS per-country files).
- It is **not an alert system**. Everything is retrospective: it counts hot spots already detected.
- ENSO is shown as an association, never as a cause. In the ENSO-lite analysis for Córdoba (VIIRS-eq season
  totals, n = 25 seasons, lags 0 to 12 months) no lag is distinguishable from shuffled years (largest |rho| 0.35
  at lag 2, family-wise p = 0.3049). That means "not detectable with this sample", not "no association"
  ([reports/05/SA5.5.md](reports/05/SA5.5.md)).

## Harmonization method

Details: [plan/02-harmonization.md](plan/02-harmonization.md), [docs/validation.md](docs/validation.md),
[reports/02/baselines.md](reports/02/baselines.md).

- **Scales.** MODIS = Terra + Aqua. VIIRS = S-NPP only. NOAA-20 is never added to S-NPP; after S-NPP ends
  (2026-11-02) it enters through a NOAA-20 to S-NPP transfer factor fitted from 2018-05 (national total 1.015).
  NOAA-21 is used only as a whole-month fallback when NOAA-20 is missing. Satellites are never averaged.
- **Scale factor (SA2.2).** Ratio of sums per 2.5° lat/lon block, month of the year and day/night, with shrinkage
  toward the national factor of the same month and day/night: `f = (M + k·f_national) / (V + k)`, where `k` is
  chosen inside the training set. Counts are detections after the filters (`type` 0, MODIS confidence >= 30,
  VIIRS nominal or high) summed from a 0.1° grid.
- **Calibration** `sf-2026.11.2`, frozen with its sha256 in `backend/calibrations/` (the build refuses a file that
  does not match, and a version is never overwritten). It keeps every pair of `sf-2026.11.1` (fitted 2012-02 to
  2025-12) byte for byte and adds NOAA-21 to S-NPP, NOAA-21 to NOAA-20 and the post-MODIS route.
- **Bands.** Conformal intervals (nominal 80 %) per block-month and block-year, calibrated with nested
  leave-one-year-out residuals. Block-year bands of an incomplete year are flagged `partial_year` (coverage on
  partial years unverified).
- **After MODIS (SA2.10).** MODIS-eq after MODIS comes from a direct NOAA-20 to MODIS factor (2018-05 to 2025-12),
  chosen over the chain NOAA-20 → S-NPP → MODIS by a rule fixed before the run; the difference is within noise
  ([reports/02/SA2.10.md](reports/02/SA2.10.md)). Simulating MODIS being switched off (cut-offs 2021 to 2024, test
  years to 2025): block-year WAPE 12.3 %, national bias −3.3 %, block-year band coverage 76.1 %. The frozen band,
  tested once on January to April 2026, covered 72.1 % (coverage unverified; no fire-season month after 2025 is
  validated yet). MODIS-eq of this route means MODIS as observed in 2018-05 to 2025-12, which includes the Terra
  and Aqua orbit drift (Terra 2023+, Aqua 2024+, cause unverified, [reports/02/SA2.6.md](reports/02/SA2.6.md)).
  When S-NPP ends the route changes and MODIS-eq can step by up to about 14 % (January daytime) with no change in
  fire.
- **Recent months.** 2026 comes from the FIRMS area API: standard processing first, then near real time (NRT,
  marked provisional until standard processing replaces it). NRT rows have no `type`, so a static-source mask built
  from the standard history replaces the `type` filter (national bias within 2.3 % on 2025,
  [reports/01/SA1.6_nrt_mask.md](reports/01/SA1.6_nrt_mask.md)). Incomplete satellite-months are left out
  ([reports/01/SA1.6_completeness.md](reports/01/SA1.6_completeness.md)).
- **Drift and backward validation.** Dropping the drift years does not improve training on 2012 to 2015 for any
  pair under the pre-registered rule ([reports/02/SA2.8.md](reports/02/SA2.8.md)). Observed MODIS from 2022 is
  flagged "orbit drift (unverified cause)".
- **2000 to 2011.** VIIRS did not exist yet; the VIIRS-equivalent series for those years is derived from MODIS and
  labelled "estimated" (`estimado`), never "detected".
- **Baselines.** SA2.3 (quantile matching per region) was also run and loses to the factor in both directions.
- **Machine learning.** LightGBM (SA2.4 toward MODIS, SA2.7 inverse series) was tested against the factor under a
  criterion fixed before the run. It does not beat the factor in either direction, so the published series uses the
  SA2.2 factor ([plan/02-harmonization.md](plan/02-harmonization.md), [reports/02/baselines.md](reports/02/baselines.md)).
  Adding MCD64A1 burned area to the inverse-series model does not change that
  ([reports/02/SA2.9.md](reports/02/SA2.9.md)).

### Error by method and direction

All test years pooled (2012 to 2025). "b-month" is per block-month, "b-year" per block-year. WAPE is the weighted
absolute percentage error; bias is Σpred/Σobs − 1.

VIIRS (S-NPP) to MODIS-equivalent:

| Scheme | Method | Bias b-month | WAPE b-month | MAE b-month | Deviance b-month | Bias b-year | WAPE b-year | MAE b-year |
|---|---|---|---|---|---|---|---|---|
| leave-one-year-out | SA2.2 factor | +0.9 % | 17.2 % | 11.3 | 5.20 | +0.9 % | 10.1 % | 79.2 |
| leave-one-year-out | SA2.3 quantiles | +3.4 % | 19.4 % | 12.7 | 6.33 | +3.4 % | 11.1 % | 87.1 |
| rolling origin | SA2.2 factor | +2.4 % | 18.7 % | 12.3 | 5.64 | +2.4 % | 11.4 % | 89.5 |
| rolling origin | SA2.3 quantiles | +8.0 % | 21.9 % | 14.4 | 6.99 | +8.0 % | 13.8 % | 108.3 |

MODIS to VIIRS-equivalent (inverse series):

| Scheme | Method | Bias b-month | WAPE b-month | MAE b-month | Deviance b-month | Bias b-year | WAPE b-year | MAE b-year |
|---|---|---|---|---|---|---|---|---|
| leave-one-year-out | SA2.2 factor | -0.9 % | 17.9 % | 39.0 | 27.71 | -0.9 % | 10.6 % | 275.7 |
| leave-one-year-out | SA2.3 quantiles | -1.9 % | 19.4 % | 42.3 | 27.85 | -1.9 % | 11.2 % | 290.5 |
| rolling origin | SA2.2 factor | -2.1 % | 18.7 % | 40.8 | 29.44 | -2.1 % | 11.5 % | 301.4 |
| rolling origin | SA2.3 quantiles | -6.6 % | 20.3 % | 44.3 | 30.53 | -6.6 % | 12.7 % | 332.1 |

Conformal interval coverage (nominal 80 %, leave-one-year-out, rows with source > 0, all test years):

| Direction | Level | Coverage | Relative width |
|---|---|---|---|
| VIIRS (S-NPP) to MODIS-eq | block-month | 80.2 % | 0.59 |
| MODIS to VIIRS-eq | block-month | 80.1 % | 0.62 |
| VIIRS (S-NPP) to MODIS-eq | block-year | 80.6 % | 0.35 |
| MODIS to VIIRS-eq | block-year | 80.7 % | 0.37 |

Coverage by year varies more at block-year (few rows per test year). Rows where the source sensor has 0 hot spots
and the target has some cannot be predicted by a factor; they are 0.3 % of the target detections or less and are
reported in the baselines report. The relationship between sensors may drift over time (for example Terra orbital
drift, cause unverified), which can lower coverage in a given year.

## Data sources and licenses

Verified on 2026-11-14 unless marked otherwise; see [docs/research/data-sources.md](docs/research/data-sources.md).

| Source | What | URL |
|---|---|---|
| NASA FIRMS, per-country yearly CSV | MODIS C6.1 (Terra, Aqua), VIIRS S-NPP and NOAA-20 375 m, standard processing; no login | `https://firms.modaps.eosdis.nasa.gov/data/country/{modis\|viirs-snpp\|viirs-jpss1}/{YEAR}/{sensor}_{YEAR}_Argentina.csv` |
| NASA FIRMS area API | Recent months (NRT and standard), needs a free MAP_KEY | `https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/{SOURCE}/{west,south,east,north}/{DAY_RANGE}/{DATE}` |
| NOAA CPC ONI | Monthly Oceanic Niño Index; El Niño >= +0.5, La Niña <= −0.5, Neutral between | https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt |

- Standard FIRMS processing lags 2 to 3 months. On 2026-11-15 the per-country files ended on 2025-12-31; the area
  API had standard processing to 2026-08-31 (MODIS) and 2026-07-31 (VIIRS) and NRT after that. The published series
  runs to 2026-10, the last complete month, with the NRT months marked provisional. S-NPP ended on 2026-11-02.
- NOAA-21 has no per-country files; its standard data comes from the area API (2023-03 onward).
- NASA MCD64A1 C6.1 burned area (LP DAAC, needs a free Earthdata login) was used only in the SA2.9 test; its terms
  beyond the catalogue record (no access constraints) are unverified.
- Terms and citation: the repo records the data license as "NASA open data" in its layer manifests
  ([docs/architecture.md](docs/architecture.md)). The exact FIRMS and NOAA CPC terms of use and the preferred
  citation text are not stated in the repo: unverified. Check the FIRMS and CPC sites before reuse.
- Basemap: CARTO Positron and Dark Matter styles (`basemaps.cartocdn.com`), loaded without a key through
  MapLibre GL, which shows the attribution carried by the style (compact control). The attribution wording and the
  CARTO terms are not stated in the repo: unverified.
- Code license: no license file yet.

Everything modeled shows its source and period in the UI and in the layer manifests.

## Use of AI tools

Code, tests, documentation and analysis in this repository were written with an AI coding assistant (Claude Code,
Anthropic), with the author planning each task and reviewing and validating the results. Commits made this way
carry a `Co-Authored-By: Claude` trailer. No AI-generated images, video or audio are used.

## How to run

Prerequisites:

- [uv](https://docs.astral.sh/uv/) and Python 3.12 (`requires-python = ">=3.12,<3.13"`; uv installs it).
- Node 22 (version used in CI; no `engines` field is declared) and pnpm (the lockfile is used with
  `--frozen-lockfile`; no `packageManager` field is declared).
- No API key is needed: the pipeline uses only the historical per-country files. `.env.example` lists
  `FIRMS_MAP_KEY` for the FIRMS area API (recent months), but the current backend does not read it yet.

```sh
make install          # uv sync in backend/, pnpm install in web/
```

Data pipeline, from `backend/` in this order (`data/` is git-ignored; override with `FIRECAL_DATA_DIR`):

```sh
cd backend
uv run firecal enso build         # download ONI, classify ENSO phases
uv run firecal firms download     # yearly country CSVs (idempotent; --year-from, --year-to, --product)
uv run firecal firms ingest       # raw CSV to parquet, unified schema
uv run firecal firms grid         # filter detections, aggregate to a regular grid
uv run firecal series build --version sf-2026.11.2   # apply the frozen calibration, publish series, bands, manifest
```

The calibrations are frozen and committed in `backend/calibrations/`; `firecal series calibrate --version <new>`
fits and freezes a new one (an existing version is refused).

Optional: `firecal harmonize evaluate` regenerates the error report, `firecal enso lite` the ENSO-lite analysis,
`firecal firms profile` the data profile.

Heavy runs (download, ingest, grid, evaluation) are meant to run locally with a 4 GB memory cap and few workers:

```sh
systemd-run --user --scope -p MemoryMax=4G uv run firecal firms grid
```

Run the app:

```sh
make dev              # API (firecal serve --reload, port 8000) and web (vite dev) together
```

Tests and checks:

```sh
make test             # backend pytest + web vitest
make lint             # ruff check and format check + tsc and eslint
cd web && pnpm e2e    # Playwright end-to-end tests
```

## Live demo

Not deployed yet (SA7.2).

## UI language

The UI is Spanish first, with complete English, and every string goes through i18n (`web/src/i18n/`). It shows the
challenge name and the author.

## Repo layout

```
backend/   uv project (Python 3.12): firecal CLI, pipeline stages, read-only API, tests
web/       pnpm project: Vite, React, TypeScript, deck.gl, MapLibre; vitest and Playwright
docs/      architecture, design, validation, data-source notes, screenshots
plan/      one file per phase; plan.md is the index
reports/   generated reports per phase (baselines, ENSO-lite, ...)
data/      local data and outputs (not in git)
```

Links: [plan.md](plan.md), [docs/architecture.md](docs/architecture.md), [docs/design.md](docs/design.md),
[docs/validation.md](docs/validation.md), [reports/](reports/). Architecture and practices are taken from
[clima-ideas](https://github.com/maggioniduffy/clima-ideas).
