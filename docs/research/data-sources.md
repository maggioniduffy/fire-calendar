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

## Boundaries

Used by the static export (SA7.2) for the province and department areas. Fetched with `firecal boundaries fetch`
(idempotent; `data/raw/boundaries/`, sha256 sidecars and `boundaries.json`). Read on 2026-11-15.

- Source: [geoBoundaries](https://www.geoboundaries.org) gbOpen, Argentina, simplified GeoJSON, repository
  `wmgeolab/geoBoundaries` pinned to commit `8ce2700661a28ee944350e2b329bbabb58d2ff83` (`main` on 2026-11-15).
  The files were built on 2023-12-12.
  `raw.githubusercontent.com` serves Git LFS pointers for them; the real bytes come from
  `https://media.githubusercontent.com/media/wmgeolab/geoBoundaries/<commit>/releaseData/gbOpen/ARG/ADM{1,2}/geoBoundaries-ARG-ADM{1,2}_simplified.geojson`
  (also works for the metadata JSON). The command checks the sha256 of both GeoJSON files against the pinned values.
- ADM2 (departments, published): 525 features, sha256 `cedee8710e49d9017327fc1d4b2dc536e95a82317dc94c3bac8d9404af6bf771`,
  source "Instituto Geografico Nacional and UNHCR, OCHA ROLAC" (boundary year 2020), license **CC BY 3.0 IGO**.
  The metadata declares 526 units; the file has 525.
- ADM1 (provinces, **lookup only, never published**): 23 features, sha256
  `7cc9b00ba139e57f59611993d96d07eb84d955ed5bd6bd6f1dcb864e1baf549c`, source "geoBoundaries, Wikimedia" (boundary
  year 2006), license CC BY 2.5 Generic.
- Attribution required (geoBoundaries `CITATION-AND-USE`): "Administrative boundaries courtesy of
  geoBoundaries.org" (the project asks to include the term "geoBoundaries" with a link to
  https://www.geoboundaries.org). Per-file sources must also be cited. The metadata writes its URLs as
  `https//host` (the colon is lost); the manifest restores it.
- ADM2 has no province field. Departments are assigned to a province by their point on surface inside the ADM1
  polygons, and the province geometry is the dissolve of its departments.

ADM1 defects found (they decide how departments are assigned, see `backend/src/firecal/stages/publish/areas.py`):

- "La Roja" is La Rioja (renamed). There is no Entre Ríos polygon, and the Buenos Aires polygon extends over it
  (its bbox reaches latitude -30.15): the 17 Entre Ríos departments (matched by name inside an approximate Entre
  Ríos bbox; list unverified against an official source) are assigned to `p-entre-rios`.
- The polygon of Ciudad Autónoma de Buenos Aires is displaced and covers 11 Gran Buenos Aires partidos: only the
  15 "Comuna N" departments go to the city.
- Coarse borders put four departments in the wrong province; fixed by shapeID (Rivadavia, cabecera Selva, to
  Santiago del Estero; Tafí del Valle and Juan B. Alberdi to Tucumán; Molinos to Salta). Found by comparing the
  department count per province with the official division, which was not checked against a primary source
  (unverified).
- Avellaneda (Buenos Aires), Monte Hermoso and Ushuaia fall in no polygon: assigned to the province of the closest
  assigned department (at most 0.1 degrees away).
- Remaining count differences with the official division (unverified): Corrientes 24 (official 25, "San Luis del
  Palmar" is not in ADM2 under that name) and Tierra del Fuego 2 departments in the data.
- 15 of the 525 ADM2 features are comunas of the city. The export skips every area below the API minimum of
  100 km2 and lists it in `manifest.json` (36 of 549: the 15 comunas, 15 Buenos Aires partidos (Gran Buenos Aires and
  Pinamar), 2 of Mendoza, 3 of San Juan and Tucumán's Capital).

## Pending verification

CONAE's Hot Spots Catalog and Thematic Viewer, SPI/SPEI (CHIRPS, ERA5, SPEIbase), Copernicus CEMS FWI, land cover
(MCD12Q1 or ESA WorldCover), MCD64A1 burned areas.
