# Fuentes de datos

Verificado el 2026-11-14 salvo donde dice "sin verificar".

## FIRMS por país (histórico, standard processing)

- CSV anual por país y sensor, **sin login**:
  `https://firms.modaps.eosdis.nasa.gov/data/country/{modis|viirs-snpp|viirs-jpss1}/{YEAR}/{sensor}_{YEAR}_Argentina.csv`
- Tamaños (HEAD, 2023): MODIS 3,9 MB, VIIRS S-NPP 13,8 MB, VIIRS NOAA-20 (`viirs-jpss1`) 13,5 MB. MODIS 2001:
  2,6 MB. Total Argentina estimado ≈ 400 MB.
- Página: https://firms.modaps.eosdis.nasa.gov/country/ (instrumentos listados: MODIS, VIIRS NOAA-20; S-NPP sigue
  respondiendo por URL).
- Rangos según el FAQ de FIRMS: MODIS Terra desde 2000-11-01, Aqua desde 2002-07; VIIRS S-NPP 2012-01-20 a
  2026-11-02; NOAA-20 desde 2018-04-01; NOAA-21 desde 2024-01-17. NOAA-21 por país: sin verificar.
- El standard processing tiene 2–3 meses de demora.

## FIRMS area API (meses recientes)

- `https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/{SOURCE}/{west,south,east,north}/{DAY_RANGE}/{DATE}`
- `DAY_RANGE` 1..5. Límite: 5000 transacciones cada 10 minutos por MAP_KEY (gratis).
- Fuentes: `MODIS_NRT`, `MODIS_SP`, `VIIRS_NOAA20_NRT`, `VIIRS_NOAA20_SP`, `VIIRS_NOAA21_NRT`, `VIIRS_NOAA21_SP`,
  `VIIRS_SNPP_NRT`, `VIIRS_SNPP_SP`.
- Disponibilidad por sensor: `/api/data_availability/csv/{MAP_KEY}/{SENSOR}`.
- MAP_KEY en `.env` como `FIRMS_MAP_KEY`. Sin ella, la serie termina donde termina el standard processing y la UI lo
  dice.

## Continuidad

- Suomi NPP dejó de producir en FIRMS el 2026-11-02 15:40 UTC. La continuidad post-MODIS usa NOAA-20 y NOAA-21.
- Fin de misión de Terra y Aqua y efecto de la deriva orbital: sin verificar.

## ENSO

- ONI mensual de NOAA CPC: https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt
- Fase: Niño ≥ +0,5, Niña ≤ −0,5, Neutro en el medio. Implementación de referencia de clima-ideas copiada en
  [../reference/enso.py](../reference/enso.py).

## Pendiente de verificar

Catálogo de Focos de Calor y Visor Temático de CONAE, SPI/SPEI (CHIRPS, ERA5, SPEIbase), FWI de Copernicus CEMS,
cobertura del suelo (MCD12Q1 o ESA WorldCover), áreas quemadas MCD64A1.
