# SA5.5 ENSO-lite: fire-season totals vs lagged ONI

Retrospective association analysis. It is not a prediction, not an alert and not a causal claim.
Design: `plan/05-enso-drought.md`, section "SA5.5 pre-registered design" (fixed 2026-11-15 before the run).
Deviations from the design: see the section "Deviations and open points".

- **Random seed:** 20261115 (numpy `SeedSequence`; separate streams for permutations, block bootstrap, iid bootstrap)
- Permutations: 5000 whole-year shuffles, shared by all areas. Bootstrap resamples: 2000 (block length 3).

## 1. Primary specification

- Area: Cordoba preset (approximate rectangle, lat -35 to -29.5, lon -65.8 to -61.8; not the official boundary).
- Series: VIIRS-eq scale of the harmonized layer, raw (not detrended) season totals; seasons 2001-2025 (n = 25).
- Fire season: the 4 consecutive calendar months (circular) with the highest climatological median total; labelled by the year of its first month; incomplete seasons dropped.
- Lag k (0-12): ONI value (3-month mean dated at its central month) at season start minus k months; no further averaging.
- Statistic: Spearman rho per lag. 95% CI by moving-block bootstrap over seasons (block 3) labelled **approximate, coverage unverified**, next to an iid pairs bootstrap.
- Baseline: shuffled years (each season keeps its 13-lag ONI vector). Per-lag p is two-sided with the +1 correction; family-wise p uses max |rho| over the 13 lags.
- Lag-1 autocorrelation (consecutive years): season total 0.20; ONI at lag 0 -0.15.

## 2. Primary result (Cordoba, VIIRS-eq, raw season totals)

| lag (months) | rho | block-bootstrap 95% CI | iid-bootstrap 95% CI | per-lag p (permutation) |
|---:|---:|---|---|---:|
| 0 | -0.07 | [-0.51, 0.41] | [-0.48, 0.37] | 0.7644 |
| 1 | -0.24 | [-0.58, 0.26] | [-0.58, 0.20] | 0.2490 |
| 2 | -0.35 | [-0.65, 0.12] | [-0.63, 0.05] | 0.0850 |
| 3 | -0.27 | [-0.61, 0.12] | [-0.60, 0.10] | 0.1774 |
| 4 | -0.16 | [-0.58, 0.25] | [-0.53, 0.22] | 0.4421 |
| 5 | -0.12 | [-0.54, 0.30] | [-0.51, 0.25] | 0.5595 |
| 6 | -0.14 | [-0.55, 0.29] | [-0.52, 0.24] | 0.5057 |
| 7 | -0.08 | [-0.51, 0.35] | [-0.46, 0.29] | 0.6901 |
| 8 | -0.03 | [-0.43, 0.38] | [-0.42, 0.35] | 0.8960 |
| 9 | -0.01 | [-0.40, 0.41] | [-0.40, 0.39] | 0.9710 |
| 10 | 0.08 | [-0.33, 0.49] | [-0.32, 0.45] | 0.7015 |
| 11 | 0.09 | [-0.33, 0.51] | [-0.32, 0.46] | 0.6563 |
| 12 | 0.09 | [-0.35, 0.57] | [-0.37, 0.49] | 0.6761 |

**Family-wise p (max |rho| over lags 0-12, 5000 whole-year permutations): 0.3049**
(observed max |rho| = 0.35 at lag 2).

**No-signal statement.** In the primary family (n = 25 seasons) no lag shows an association distinguishable from shuffled years: the largest |rho| is 0.35 at lag 2, family-wise p = 0.3049 (>= 0.05). This means *not detectable with this sample*, not *no association*.

## 3. Season window per area

Primary: **Jul-Oct** (start month 7, length 4), holding **65.5%** of the annual median total (sum of the 12 monthly medians).

| month | median monthly total (VIIRS-eq) | share of annual median total |
|---|---:|---:|
| Jan | 431.5 | 4.9% |
| Feb | 265.0 | 3.0% |
| Mar | 253.2 | 2.9% |
| Apr | 274.6 | 3.1% |
| May | 254.3 | 2.9% |
| Jun | 391.0 | 4.4% |
| Jul | 950.0 | 10.7% |
| Aug | 1645.2 | 18.6% |
| Sep | 1999.0 | 22.6% |
| Oct | 1200.2 | 13.6% |
| Nov | 799.3 | 9.0% |
| Dec | 382.1 | 4.3% |

The window of every exploratory area is in the first exploratory table (column `window`, share of the annual median total in parentheses).

## 4. Era checks (primary configuration)

VIIRS-eq is *estimated* from MODIS in 2000-2011 and observed from 2012 (seasons are assigned to the era of the year of their first month; n = 11 estimated, 14 observed). The estimated era may carry a different scale and variability than the observed one, so two checks are reported:

- within-era ranks: season totals are replaced by their percentile rank within each era (rank/(n+1)) before the Spearman computation; ONI is ranked over all seasons;
- observed-only: seasons from 2012 onward only.

| lag | rho within-era ranks (n = 25) | per-lag p | rho observed-only 2012-2025 (n = 14) | per-lag p |
|---:|---:|---:|---:|---:|
| 0 | 0.11 | 0.6077 | -0.53 | 0.0584 |
| 1 | -0.01 | 0.9516 | -0.52 | 0.0610 |
| 2 | -0.13 | 0.5249 | -0.46 | 0.1000 |
| 3 | -0.17 | 0.4201 | -0.25 | 0.3811 |
| 4 | -0.08 | 0.6989 | -0.17 | 0.5597 |
| 5 | -0.07 | 0.7417 | -0.07 | 0.8030 |
| 6 | -0.07 | 0.7377 | -0.06 | 0.8398 |
| 7 | -0.07 | 0.7285 | -0.03 | 0.9144 |
| 8 | -0.05 | 0.8246 | 0.01 | 0.9794 |
| 9 | -0.04 | 0.8496 | 0.00 | 0.9992 |
| 10 | 0.03 | 0.9008 | 0.14 | 0.6321 |
| 11 | 0.06 | 0.7648 | 0.18 | 0.5195 |
| 12 | 0.13 | 0.5353 | 0.36 | 0.1984 |

Family-wise p (max |rho| over lags): within-era ranks 0.8508; observed-only 0.2150.

## 5. Exploratory tables (not used for the headline)

Reported for completeness; many configurations were examined, so isolated large values are expected by chance. Sign convention: rho > 0 means larger season totals with higher ONI (warmer ENSO phase) at that lag, rho < 0 the opposite. The configurations are not independent (nested and overlapping areas, the same ONI series, MODIS-eq and VIIRS-eq views of the same detections), and "own family-wise p" corrects only for the 13 lags of that one configuration; the p over all configurations is the one that accounts for the whole exploratory set. Configurations: all of Argentina and four approximate regions (VIIRS-eq, raw); MODIS-eq 2003-2023 (Aqua full years; Terra drift 2024-2025) for Cordoba and the five areas; log1p-detrended VIIRS-eq totals (OLS linear trend removed) for Cordoba and the five areas.

**Family-wise p over all 17 exploratory configurations x 13 lags: 0.0714** (observed max |rho| = 0.65).

### 5.1 Best lag per configuration

| configuration | n | seasons | window | lag at max abs rho | rho | per-lag p | own family-wise p |
|---|---:|---|---|---:|---:|---:|---:|
| argentina / VIIRS-EQ / raw | 25 | 2001-2025 | Jul-Oct (64%) | 2 | -0.55 | 0.0056 | 0.0252 |
| noa / VIIRS-EQ / raw | 25 | 2001-2025 | Aug-Nov (80%) | 3 | -0.56 | 0.0044 | 0.0200 |
| nea / VIIRS-EQ / raw | 25 | 2001-2025 | Jul-Oct (70%) | 1 | -0.41 | 0.0464 | 0.1626 |
| pampas / VIIRS-EQ / raw | 25 | 2001-2025 | Jul-Oct (52%) | 3 | -0.59 | 0.0022 | 0.0114 |
| patagonia / VIIRS-EQ / raw | 25 | 2000-2024 | Dec-Mar (69%) | 7 | 0.33 | 0.1004 | 0.3397 |
| cordoba / MODIS-EQ / raw | 21 | 2003-2023 | Jul-Oct (66%) | 2 | -0.38 | 0.0824 | 0.2937 |
| argentina / MODIS-EQ / raw | 21 | 2003-2023 | Jul-Oct (67%) | 2 | -0.48 | 0.0276 | 0.1158 |
| noa / MODIS-EQ / raw | 21 | 2003-2023 | Aug-Nov (78%) | 3 | -0.54 | 0.0152 | 0.0530 |
| nea / MODIS-EQ / raw | 21 | 2003-2023 | Jul-Oct (73%) | 11 | 0.34 | 0.1374 | 0.4031 |
| pampas / MODIS-EQ / raw | 21 | 2003-2023 | Jul-Oct (51%) | 2 | -0.58 | 0.0062 | 0.0330 |
| patagonia / MODIS-EQ / raw | 20 | 2003-2022 | Dec-Mar (63%) | 7 | 0.49 | 0.0288 | 0.1188 |
| cordoba / VIIRS-EQ / log1p-detrended | 25 | 2001-2025 | Jul-Oct (66%) | 2 | -0.28 | 0.1700 | 0.4961 |
| argentina / VIIRS-EQ / log1p-detrended | 25 | 2001-2025 | Jul-Oct (64%) | 1 | -0.54 | 0.0056 | 0.0296 |
| noa / VIIRS-EQ / log1p-detrended | 25 | 2001-2025 | Aug-Nov (80%) | 2 | -0.65 | 0.0008 | 0.0040 |
| nea / VIIRS-EQ / log1p-detrended | 25 | 2001-2025 | Jul-Oct (70%) | 1 | -0.33 | 0.1124 | 0.3565 |
| pampas / VIIRS-EQ / log1p-detrended | 25 | 2001-2025 | Jul-Oct (52%) | 3 | -0.58 | 0.0032 | 0.0152 |
| patagonia / VIIRS-EQ / log1p-detrended | 25 | 2000-2024 | Dec-Mar (69%) | 7 | 0.32 | 0.1070 | 0.3583 |

### 5.2 Spearman rho by lag

| configuration | L0 | L1 | L2 | L3 | L4 | L5 | L6 | L7 | L8 | L9 | L10 | L11 | L12 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| argentina / VIIRS-EQ / raw | -0.30 | -0.51 | -0.55 | -0.38 | -0.23 | -0.14 | -0.14 | -0.08 | -0.02 | 0.00 | 0.09 | 0.09 | 0.09 |
| noa / VIIRS-EQ / raw | -0.33 | -0.38 | -0.53 | -0.56 | -0.40 | -0.28 | -0.20 | -0.17 | -0.11 | -0.04 | -0.01 | 0.06 | 0.06 |
| nea / VIIRS-EQ / raw | -0.27 | -0.41 | -0.40 | -0.22 | -0.11 | -0.03 | -0.04 | 0.04 | 0.09 | 0.09 | 0.16 | 0.17 | 0.16 |
| pampas / VIIRS-EQ / raw | -0.15 | -0.40 | -0.57 | -0.59 | -0.49 | -0.43 | -0.43 | -0.39 | -0.31 | -0.26 | -0.15 | -0.14 | -0.06 |
| patagonia / VIIRS-EQ / raw | 0.15 | 0.10 | 0.07 | 0.06 | 0.07 | 0.10 | 0.26 | 0.33 | 0.25 | 0.21 | 0.19 | 0.17 | 0.15 |
| cordoba / MODIS-EQ / raw | -0.12 | -0.28 | -0.38 | -0.29 | -0.20 | -0.15 | -0.15 | -0.08 | 0.02 | 0.05 | 0.13 | 0.17 | 0.20 |
| argentina / MODIS-EQ / raw | -0.29 | -0.46 | -0.48 | -0.27 | -0.13 | -0.04 | -0.04 | 0.04 | 0.13 | 0.15 | 0.22 | 0.26 | 0.26 |
| noa / MODIS-EQ / raw | -0.31 | -0.39 | -0.52 | -0.54 | -0.33 | -0.22 | -0.14 | -0.11 | -0.01 | 0.08 | 0.11 | 0.17 | 0.20 |
| nea / MODIS-EQ / raw | -0.20 | -0.31 | -0.29 | -0.11 | 0.01 | 0.08 | 0.09 | 0.17 | 0.24 | 0.25 | 0.30 | 0.34 | 0.34 |
| pampas / MODIS-EQ / raw | -0.16 | -0.41 | -0.58 | -0.56 | -0.47 | -0.38 | -0.40 | -0.35 | -0.27 | -0.20 | -0.12 | -0.08 | -0.02 |
| patagonia / MODIS-EQ / raw | 0.26 | 0.21 | 0.16 | 0.15 | 0.14 | 0.25 | 0.43 | 0.49 | 0.33 | 0.26 | 0.24 | 0.22 | 0.17 |
| cordoba / VIIRS-EQ / log1p-detrended | -0.08 | -0.20 | -0.28 | -0.27 | -0.17 | -0.15 | -0.16 | -0.12 | -0.06 | -0.03 | 0.05 | 0.07 | 0.12 |
| argentina / VIIRS-EQ / log1p-detrended | -0.40 | -0.54 | -0.53 | -0.41 | -0.26 | -0.17 | -0.14 | -0.09 | -0.02 | -0.01 | 0.05 | 0.08 | 0.15 |
| noa / VIIRS-EQ / log1p-detrended | -0.52 | -0.55 | -0.65 | -0.61 | -0.44 | -0.33 | -0.24 | -0.21 | -0.18 | -0.09 | -0.07 | -0.00 | 0.01 |
| nea / VIIRS-EQ / log1p-detrended | -0.21 | -0.33 | -0.32 | -0.21 | -0.09 | -0.01 | -0.01 | 0.04 | 0.06 | 0.03 | 0.07 | 0.08 | 0.11 |
| pampas / VIIRS-EQ / log1p-detrended | -0.18 | -0.39 | -0.53 | -0.58 | -0.48 | -0.44 | -0.44 | -0.41 | -0.33 | -0.28 | -0.19 | -0.16 | -0.05 |
| patagonia / VIIRS-EQ / log1p-detrended | 0.18 | 0.12 | 0.10 | 0.09 | 0.10 | 0.13 | 0.27 | 0.32 | 0.25 | 0.21 | 0.20 | 0.17 | 0.16 |

### 5.3 Region boxes (approximate, not official boundaries)

- All of Argentina (data box): lat -56 to -21, lon -74 to -53
- NOA (approximate box): lat -30 to -21.8, lon -69 to -62.5
- NEA (approximate box): lat -30 to -22, lon -62.5 to -53.5
- Pampas (approximate box): lat -39.5 to -31, lon -65 to -57.5
- Patagonia (approximate box): lat -56 to -39.5, lon -73.6 to -62
- Cordoba preset (approximate rectangle): lat -35 to -29.5, lon -65.8 to -61.8

The boxes are simple lat/lon rectangles chosen for this analysis (edges on 0.1 degree cell borders; cells are selected by center). They are **approximate, not official boundaries**, and some include cells outside the named region (sin verificar).

## 6. Power note

With n = 25 seasons, the null distribution of the shuffled-years baseline gives (95th percentile): a per-lag threshold of |rho| >= 0.39 and a family-wise threshold (max over 13 lags) of |rho| >= 0.50. Associations weaker than that cannot be told apart from chance with this sample. A null result therefore means "not detectable with this sample", not "no association". The block-bootstrap CI assumes weak dependence between neighbouring seasons; its coverage at this n has not been verified, and the iid CI is shown beside it for that reason.

## 7. Sources and periods

- Fire data: NASA FIRMS standard country files (Argentina): MODIS Terra/Aqua, VIIRS 375 m S-NPP/NOAA-20 (layer `harmonized`, period 2000-11-01/2025-12-31, license NASA open data). Harmonization: method `scale_factor`, calibration id `sf-2026.11.1`. VIIRS-eq 2000-2011 is estimated from MODIS (modeled, with the layer's own uncertainty, which is not propagated here).
- ONI: NOAA CPC ONI (https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt), monthly values 1950-01 / 2026-09.
- Analysis: `firecal enso lite`, seed 20261115.

## 8. Deviations and open points

- Permutations: one shared permutation of the calendar years 2000-2025 is drawn per resample; each area uses the order it induces on its own valid seasons (a uniform permutation of those seasons), so areas with different season sets share the same draw.
- Seasons with any of the 13 lag values missing are dropped; the primary series keeps 25 seasons.
- Within-era ranks are applied to the fire totals only (ONI is not re-ranked by era); this is an interpretation of the design wording.
- "All areas x lags" family-wise p for the exploratory set covers the 17 configurations listed in 5.1.
- Region boxes, Argentina (data box includes any cell with detections inside it) and Cordoba are approximate. The block-bootstrap CI is approximate with unverified coverage.
- No moving-block coverage simulation, no drought variable (SPI/SPEI deferred), no causal analysis.
