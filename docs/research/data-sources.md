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
  (2018–2022), `61.03` (2023–2025); VIIRS `2`. Meaning of those version codes: unverified.

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
- End of mission of Terra and Aqua and effect of orbital drift: unverified.

## ENSO

- Monthly ONI from NOAA CPC: https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt
- Phase: El Niño ≥ +0.5, La Niña ≤ −0.5, Neutral in between. Clima-ideas reference implementation copied to
  [../reference/enso.py](../reference/enso.py).

## Pending verification

CONAE's Hot Spots Catalog and Thematic Viewer, SPI/SPEI (CHIRPS, ERA5, SPEIbase), Copernicus CEMS FWI, land cover
(MCD12Q1 or ESA WorldCover), MCD64A1 burned areas.
