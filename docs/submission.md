# Space Apps submission text

Draft for the NASA Space Apps Challenge 2026 project page (CONAE challenge "Harmonization of MODIS and VIIRS Hot
Spots"). Figures copied from the README; check them against it before submitting.

## Project name

fire-calendar: harmonized MODIS + VIIRS fire calendar for Argentina

## Summary (50-200 words)

MODIS and VIIRS both detect active fires, but VIIRS (375 m) reports about 3.3 times more hot spots than MODIS
(1 km) over Argentina, so a count series that moves from one sensor to the other jumps with no change in fire. With
Terra and Aqua being retired, that break is about to hit every long fire record. fire-calendar harmonizes NASA FIRMS
hot spots from 2000 to today into two comparable scales, MODIS-equivalent and VIIRS-equivalent, using a scale
factor per 2.5° block, month and day/night, with 80 % conformal uncertainty bands. The factor was validated
leave-one-year-out (block-year WAPE about 10 %) and beat both a quantile-matching baseline and a LightGBM model,
so the simple method is the one published. Continuity after MODIS and after S-NPP (ended 2026-11-02) goes through
NOAA-20 and NOAA-21. The web app shows a year × month calendar, anomalies against the climatology, an ENSO row
(association, not cause) and CSV downloads for every Argentine province and department, starting from Córdoba.
It is retrospective, not an alert system.

## Project details

**What it does.** A Python pipeline downloads FIRMS per-country files (MODIS C6.1, VIIRS S-NPP, NOAA-20) and the
FIRMS area API for recent months, filters them (type 0, MODIS confidence >= 30, VIIRS nominal or high), grids them
at 0.1° and converts each sensor to the other's scale with a frozen, checksummed calibration. Every modeled number
carries its source, period and an uncertainty band; years before VIIRS (2000-2011) are labelled "estimated".

**How it was validated.** Leave-one-year-out and rolling-origin tests over 2012-2025, a simulated MODIS switch-off
(cut-offs 2021-2024: block-year WAPE 12.3 %), drift checks on Terra and Aqua, and a pre-registered comparison
against baselines. Machine learning was tried and did not beat the factor, so it is not used.

**Machine learning, tested and reported.** LightGBM models (Poisson/Tweedie) were trained on 0.1° cell × month ×
day/night rows in both directions, starting from the scale factor as an offset so they could only add corrections.
Features: hot-spot count, fire radiative power (FRP) and FRP per detection, count over the 3×3 neighbourhood, the
day/night share, the count of the other half of the day, the block total and the month (lat/lon and the Terra/Aqua
share only as ablations). The most used features were FRP per detection (47 % of gain) toward MODIS and the 3×3
neighbourhood count (67 %) toward VIIRS. MODIS MCD64A1 burned area was added as a further variable and changed
nothing (+0.08 points). The rule for publishing ML was fixed before the run. VIIRS→MODIS came close (block-month
WAPE 15.9 % vs 17.2 %) but failed on bias (−2.5 % vs +0.9 %), so the published series uses the factor.

**What comes next.** (1) Validate the factor on the first full fire season after MODIS and S-NPP (2026), since
the frozen bands have only been checked on January–April 2026. (2) An experimental outlook: the probability that
next month has more hot spots than the area's median, up to 6 months ahead, from ENSO (ONI and its forecast),
drought (SPEI), fire weather (FWI) and the previous month's anomaly. Logistic regression and LightGBM would be
scored (RPS, Brier) against climatology, persistence and ENSO-analog years, with predictions frozen in a
registry and shown as "Experimental, not an alert"; if they do not beat climatology, the app says so. (3) Atmospheric
rivers and fire in the Andes and Patagonia: whether a very wet season relieves fire right away or grows fuel for
the next dry one. (4) Land cover as a variable and the official Córdoba boundary.

**Benefits and impact.** Researchers, fire brigades and provincial agencies can read trends and anomalies across
the sensor change instead of mistaking a satellite switch for a change in fire activity, and keep a series going
after MODIS ends.

**Tools.** Python 3.12 (uv, pandas, LightGBM for the ML test), FastAPI, TypeScript + React + MapLibre
GL, Vitest and Playwright, GitHub Actions, Cloudflare Pages (static JSON per province and department).

**What we considered.** Honesty over polish: unverified items are marked as such, ENSO is shown as association
only, and the app is explicitly retrospective. UI in Spanish with full English.

## Use of SI

Code, documentation and analysis were written with an AI coding assistant (Claude Code), with the author planning,
reviewing and validating every result. No SI-generated images, video or audio. Disclosed in the README ("Use of AI tools").

## NASA data

| Link text | URL |
|---|---|
| NASA FIRMS active fire data (MODIS C6.1, VIIRS S-NPP / NOAA-20 / NOAA-21 375 m) | https://firms.modaps.eosdis.nasa.gov/ |
| FIRMS per-country archive downloads | https://firms.modaps.eosdis.nasa.gov/country/ |
| FIRMS area API | https://firms.modaps.eosdis.nasa.gov/api/area/ |
| MODIS to VIIRS transition notice (Earthdata) | https://www.earthdata.nasa.gov/data/alerts-outages/transition-from-modis-viirs |
| MCD64A1 C6.1 burned area (LP DAAC), used in one test | https://lpdaac.usgs.gov/products/mcd64a1v061/ |

## Other data and resources

| Link text | URL |
|---|---|
| NOAA CPC Oceanic Niño Index (ONI) | https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt |
| geoBoundaries Argentina ADM2 (CC BY 3.0 IGO) | https://www.geoboundaries.org/ |
| CARTO basemaps (Positron, Dark Matter) | https://carto.com/basemaps |
| MapLibre GL JS | https://maplibre.org/ |
| Source code | https://github.com/maggioniduffy/fire-calendar |

## Links

- Project: https://fire-calendar.pages.dev/ (production URL; it always serves the latest deploy, unlike a
  per-deployment hash URL)
- Demo: pending (at most 7 slides or a video of 30 s or less, public link)
