# SA1.7 Perfil de datos FIRMS (Argentina)

Corrida: 2026-11-14 en la sesión en la nube, con `firecal firms download`, `ingest`, `grid` (0,1° y 0,25°) y
`profile` (tablas de abajo generadas por `firecal firms profile`). Fuente: archivos standard por país de NASA
FIRMS, `https://firms.modaps.eosdis.nasa.gov/data/country/{modis|viirs-snpp|viirs-jpss1}/{YEAR}/..._Argentina.csv`.

## Resumen

- 48 archivos (MODIS 2000–2025, VIIRS S-NPP 2012–2025, VIIRS NOAA-20 2018–2025), 487 MB de CSV. Detecciones
  a Parquet: 127 MB; grilla 0,1°: 18 MB; grilla 0,25°: 14 MB.
- Cobertura real: MODIS 2000-11-01 a 2025-12-31, S-NPP 2012-01-20 a 2025-12-31, NOAA-20 2018-04-01 a
  2025-12-31. Los inicios coinciden con el FAQ de FIRMS.
- **Hueco 2026:** los tres sensores dan 404 para 2026. La serie standard termina el 2025-12-31; los meses de 2026
  solo saldrían de la API NRT (SA1.6, requiere `FIRMS_MAP_KEY`).
- Sin meses vacíos dentro de la cobertura de cada producto.
- Una descarga (MODIS 2000) falló por un reset de conexión del proxy y se recuperó al reintentar; el descargador la
  marcó como `error`, no como `missing`.
- 2020 es el año con más focos en los tres productos (≈ 2,5 veces 2019 en MODIS). Solo describe conteos; no se
  interpreta causa.
- S-NPP y NOAA-20 dan conteos casi iguales en los años que comparten (2019–2025, diferencia < 5 %).

## Verificado en los archivos reales

- Columnas iguales a las asumidas por el parser (MODIS con `brightness`/`bright_t31`, VIIRS con
  `bright_ti4`/`bright_ti5`; ambos con `type`).
- `satellite`: MODIS `Terra`/`Aqua`; VIIRS `N` (S-NPP) y `N20` (NOAA-20). `confidence` VIIRS: `l`/`n`/`h`.
- `version` de MODIS cambia entre años: `6.2` en 2000–2017, `6.03` en 2018–2022 y `61.03` en 2023–2025. VIIRS:
  `2` en todos. Qué significa cada código y si cambia la detección: **sin verificar**; hay que revisarlo antes de
  la armonización (fase 2), porque un cambio de procesamiento en 2018 o 2023 se confundiría con un cambio real.


Retrospective counts of detections; not an alert system.
Filters: type in [0], MODIS confidence >= 30, VIIRS class in ['nominal', 'high'].

## Detecciones por año y producto (crudas / tras filtros)

<!-- generado por firecal firms profile -->

| Year | modis | viirs-jpss1 | viirs-snpp |
|---|---|---|---|
| 2000 | 7247 / 6732 | - | - |
| 2001 | 31835 / 29995 | - | - |
| 2002 | 60361 / 57491 | - | - |
| 2003 | 117090 / 110975 | - | - |
| 2004 | 99956 / 94954 | - | - |
| 2005 | 71179 / 67113 | - | - |
| 2006 | 84646 / 79808 | - | - |
| 2007 | 78065 / 73982 | - | - |
| 2008 | 104699 / 98975 | - | - |
| 2009 | 82012 / 78036 | - | - |
| 2010 | 62709 / 59424 | - | - |
| 2011 | 76429 / 72924 | - | - |
| 2012 | 61883 / 58289 | - | 189787 / 169182 |
| 2013 | 66549 / 63106 | - | 237553 / 210337 |
| 2014 | 36816 / 34538 | - | 126346 / 108470 |
| 2015 | 45133 / 42498 | - | 151071 / 136392 |
| 2016 | 55402 / 52693 | - | 181421 / 162934 |
| 2017 | 60280 / 57317 | - | 201664 / 180476 |
| 2018 | 55399 / 49992 | 130089 / 116454 | 184924 / 165584 |
| 2019 | 50370 / 45668 | 160664 / 141011 | 161688 / 143367 |
| 2020 | 124094 / 113716 | 434775 / 390958 | 448313 / 400953 |
| 2021 | 56867 / 51590 | 198976 / 171470 | 198060 / 170504 |
| 2022 | 77521 / 71024 | 312448 / 268257 | 312925 / 271393 |
| 2023 | 47910 / 44095 | 163741 / 139759 | 171695 / 147160 |
| 2024 | 49843 / 45453 | 157781 / 138943 | 152971 / 134624 |
| 2025 | 48121 / 43860 | 170323 / 148042 | 170674 / 149091 |

## Dropped per filter reason

| Product | type | modis_confidence | viirs_confidence |
|---|---|---|---|
| modis | 32009 | 76159 | 0 |
| viirs-jpss1 | 55178 | 0 | 158725 |
| viirs-snpp | 88786 | 0 | 249839 |

## Missing years (HTTP 404)

- modis 2026
- viirs-jpss1 2026
- viirs-snpp 2026

## Gaps (months with zero detections within each product's coverage)

- none
