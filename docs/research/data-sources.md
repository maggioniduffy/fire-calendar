# Fuentes de datos

Verificado el 2026-11-14 salvo donde dice "sin verificar".

## FIRMS por país (histórico, standard processing)

- CSV anual por país y sensor, **sin login**:
  `https://firms.modaps.eosdis.nasa.gov/data/country/{modis|viirs-snpp|viirs-jpss1}/{YEAR}/{sensor}_{YEAR}_Argentina.csv`
- Tamaños (HEAD, 2023): MODIS 3,9 MB, VIIRS S-NPP 13,8 MB, VIIRS NOAA-20 (`viirs-jpss1`) 13,5 MB. MODIS 2001:
  2,6 MB. Total Argentina medido el 2026-11-14: 487 MB (48 archivos, 2000–2025).
- Página: https://firms.modaps.eosdis.nasa.gov/country/ (instrumentos listados: MODIS, VIIRS NOAA-20; S-NPP sigue
  respondiendo por URL).
- Rangos según el FAQ de FIRMS: MODIS Terra desde 2000-11-01, Aqua desde 2002-07; VIIRS S-NPP 2012-01-20 a
  2026-11-02; NOAA-20 desde 2018-04-01; NOAA-21 desde 2024-01-17. NOAA-21 por país: sin verificar.
- El standard processing tiene 2–3 meses de demora. El 2026-11-14 ningún sensor tenía archivo 2026 (404): la
  serie standard termina el 2025-12-31.
- Columnas y códigos vistos en los archivos (2026-11-14): `satellite` MODIS `Terra`/`Aqua`, VIIRS `N` (S-NPP) y
  `N20` (NOAA-20); `confidence` VIIRS `l`/`n`/`h`; `type` presente. `version` MODIS: `6.2` (2000–2017), `6.03`
  (2018–2022), `61.03` (2023–2025); VIIRS `2`. Ver "Códigos de versión de MODIS" abajo.

### Códigos de versión de MODIS (revisado el 2026-11-14)

Fuentes leídas: [atributos FIRMS](https://www.earthdata.nasa.gov/data/tools/firms/active-fire-data-attributes-modis-viirs),
[FAQ de FIRMS](https://www.earthdata.nasa.gov/data/tools/firms/faq) y la
[guía de usuario MODIS C6/C6.1](https://earthdata.nasa.gov/s3fs-public/2023-09/MODIS_C6_C6.1_Fire_User_Guide_1.0.pdf).

- Verificado: `version` es colección más un sufijo de origen (URT, RT, NRT); sin sufijo es standard processing.
  Ningún año de Argentina trae sufijo, así que no hay filas NRT mezcladas.
- Verificado (guía, sec. 2.1): entre Colección 6 y 6.1 no hubo cambios de algoritmo ni de producto de fuego activo;
  la guía dice que se pueden mezclar libremente y que el FRP no cambia.
- Verificado (guía, sec. 5.5): en MCD14ML la versión 3 del producto mantiene el formato pero trae una tipificación
  de focos ("typing of hot spots") muy mejorada.
- Sin verificar: que `6.03` sea Colección 6 versión 03 y `61.03` Colección 6.1 versión 03 (se infiere del patrón
  `VV`); qué es exactamente `6.2`; qué años se reprocesaron en C6.1.
- Medido en nuestros archivos (MODIS Argentina, detecciones crudas): la proporción de `type` 2 (otra fuente fija
  en tierra) pasa de 0,3–1,9 % por año en 2000–2017 (`6.2`) a 2,6–5,8 % en 2018–2025 (`6.03` y `61.03`). Es
  compatible con el cambio de tipificación, sin verificar la causa. Consecuencia: el filtro `type == 0` (SA1.3)
  descarta unos 3–4 puntos porcentuales más de focos MODIS desde 2018, un escalón artificial chico en la serie
  filtrada que la fase 2 tiene que medir (tabla de estabilidad). En 2023 no se ve otro cambio en `type`.
- La proporción de focos de Aqua en MODIS sube a 67–69 % en 2024–2025 (60–65 % en 2003–2023). Solo se describe;
  la relación con la deriva orbital de Terra queda sin verificar.
- El archivo standard de MODIS (MCD14ML) no trae `scan` ni `track` (guía, tabla 10); `scan` solo existe en NRT.
  El ángulo de escaneo no está disponible como variable para SA2.7 con estos archivos.

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
- Terra y Aqua: según el aviso de Earthdata
  ([transición de MODIS a VIIRS](https://www.earthdata.nasa.gov/data/alerts-outages/transition-from-modis-viirs)),
  empiezan a apagar operaciones a fines de 2026 o principios de 2027. Fecha exacta y efecto de la deriva orbital:
  sin verificar.
- S-NPP en FIRMS: disponible del 2012-01-20 al 2026-11-02 (FAQ de FIRMS).

## ENSO

- ONI mensual de NOAA CPC: https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt
- Fase: Niño ≥ +0,5, Niña ≤ −0,5, Neutro en el medio. Implementación de referencia de clima-ideas copiada en
  [../reference/enso.py](../reference/enso.py).

## Pendiente de verificar

Catálogo de Focos de Calor y Visor Temático de CONAE, SPI/SPEI (CHIRPS, ERA5, SPEIbase), FWI de Copernicus CEMS,
cobertura del suelo (MCD12Q1 o ESA WorldCover), áreas quemadas MCD64A1.
