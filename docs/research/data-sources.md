# Data sources

Verified on 2026-11-14 except where it says "unverified".

## FIRMS per country (historical, standard processing)

- Yearly CSV per country and sensor, **no login**:
  `https://firms.modaps.eosdis.nasa.gov/data/country/{modis|viirs-snpp|viirs-jpss1}/{YEAR}/{sensor}_{YEAR}_Argentina.csv`
- Sizes (HEAD, 2023): MODIS 3.9 MB, VIIRS S-NPP 13.8 MB, VIIRS NOAA-20 (`viirs-jpss1`) 13.5 MB. MODIS 2001:
  2.6 MB. Argentina total measured on 2026-11-14: 487 MB (48 files, 2000–2025).
- Page: https://firms.modaps.eosdis.nasa.gov/country/ (instruments listed: MODIS, VIIRS NOAA-20; S-NPP still
  responds by URL).
- Ranges per the FIRMS FAQ: MODIS Terra from 2000-11-01, Aqua from 2002-07; VIIRS S-NPP 2012-01-20 to 2026-11-02;
  NOAA-20 from 2018-04-01; NOAA-21 from 2024-01-17. NOAA-21 per country: unverified.
- Standard processing lags 2–3 months. On 2026-11-14 no sensor had a 2026 file (404): the standard series ends on
  2025-12-31.
- Columns and codes seen in the files (2026-11-14): `satellite` MODIS `Terra`/`Aqua`, VIIRS `N` (S-NPP) and `N20`
  (NOAA-20); `confidence` VIIRS `l`/`n`/`h`; `type` present. MODIS `version`: `6.2` (2000–2017), `6.03`
  (2018–2022), `61.03` (2023–2025); VIIRS `2`. See "MODIS version codes" below.

### MODIS version codes (reviewed on 2026-11-14)

Sources read: [FIRMS attributes](https://www.earthdata.nasa.gov/data/tools/firms/active-fire-data-attributes-modis-viirs),
[FIRMS FAQ](https://www.earthdata.nasa.gov/data/tools/firms/faq) and the
[MODIS C6/C6.1 user guide](https://earthdata.nasa.gov/s3fs-public/2023-09/MODIS_C6_C6.1_Fire_User_Guide_1.0.pdf).

- Verified: `version` is the collection plus an origin suffix (URT, RT, NRT); no suffix means standard processing.
  No Argentina year carries a suffix, so there are no NRT rows mixed in.
- Verified (guide, sec. 2.1): between Collection 6 and 6.1 there were no algorithm or active-fire product changes;
  the guide says they can be mixed freely and that FRP does not change.
- Verified (guide, sec. 5.5): in MCD14ML, version 3 of the product keeps the format but brings a much improved
  typing of hot spots ("typing of hot spots").
- Unverified: that `6.03` is Collection 6 version 03 and `61.03` is Collection 6.1 version 03 (inferred from the
  `VV` pattern); what exactly `6.2` is; which years were reprocessed in C6.1.
- Measured in our files (MODIS Argentina, raw detections): the share of `type` 2 (other static land source) goes
  from 0.3–1.9 % per year in 2000–2017 (`6.2`) to 2.6–5.8 % in 2018–2025 (`6.03` and `61.03`). It is consistent
  with the typing change, cause unverified. Consequence: the `type == 0` filter (SA1.3) drops about 3–4 percentage
  points more MODIS hot spots since 2018, a small artificial step in the filtered series that phase 2 has to
  measure (stability table). No other change in `type` is seen in 2023.
- The Aqua share of MODIS hot spots rises to 67–69 % in 2024–2025 (60–65 % in 2003–2023). This is only described;
  the relation to Terra's orbital drift remains unverified.
- The MODIS standard file (MCD14ML) carries no `scan` or `track` (guide, table 10); `scan` exists only in NRT.
  The scan angle is not available as a variable for SA2.7 with these files.

## FIRMS area API (recent months)

- `https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/{SOURCE}/{west,south,east,north}/{DAY_RANGE}/{DATE}`
- `DAY_RANGE` 1..5. Limit: 5000 transactions every 10 minutes per MAP_KEY (free).
- Sources: `MODIS_NRT`, `MODIS_SP`, `VIIRS_NOAA20_NRT`, `VIIRS_NOAA20_SP`, `VIIRS_NOAA21_NRT`, `VIIRS_NOAA21_SP`,
  `VIIRS_SNPP_NRT`, `VIIRS_SNPP_SP`.
- Availability per sensor: `/api/data_availability/csv/{MAP_KEY}/{SENSOR}`.
- MAP_KEY in `.env` as `FIRMS_MAP_KEY`. Without it, the series ends where standard processing ends and the UI says
  so.

## Continuity

- Suomi NPP stopped producing in FIRMS on 2026-11-02 15:40 UTC. Post-MODIS continuity uses NOAA-20 and NOAA-21.
- Terra and Aqua: per the Earthdata notice
  ([MODIS to VIIRS transition](https://www.earthdata.nasa.gov/data/alerts-outages/transition-from-modis-viirs)),
  they start shutting down operations in late 2026 or early 2027. Exact date and effect of orbital drift:
  unverified.
- S-NPP in FIRMS: available from 2012-01-20 to 2026-11-02 (FIRMS FAQ).

## ENSO

- Monthly ONI from NOAA CPC: https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt
- Phase: El Niño ≥ +0.5, La Niña ≤ −0.5, Neutral in between. Clima-ideas reference implementation copied to
  [../reference/enso.py](../reference/enso.py).

## Pending verification

CONAE's Hot Spots Catalog and Thematic Viewer, SPI/SPEI (CHIRPS, ERA5, SPEIbase), Copernicus CEMS FWI, land cover
(MCD12Q1 or ESA WorldCover), MCD64A1 burned areas.
