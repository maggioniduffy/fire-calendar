# Fase 1 — Datos FIRMS

Estado: activa · Depende de: 0 (SA0.8) · Refs: `docs/architecture.md`, `docs/research/data-sources.md`

## Objetivo

Focos de calor de MODIS y VIIRS 2000–hoy, filtrados y en una grilla liviana de Argentina para consultar cualquier área del país.

## Datos

MODIS C6.1 (Terra desde 11/2000, Aqua desde 7/2002), VIIRS 375 m (S-NPP desde 1/2012, NOAA-20, NOAA-21).
Archivo standard por país para la historia (URL en `docs/research/data-sources.md`; S-NPP termina el 2026-11-02);
NRT por API de área para los meses que el standard todavía no cubre, solo si hay `FIRMS_MAP_KEY`.

## Tareas

| ID | Tarea | Agente | Hecho cuando |
|---|---|---|---|
| SA1.1 | Descarga idempotente de los CSV anuales de Argentina (MODIS, VIIRS S-NPP, VIIRS NOAA-20) | Sonnet escribe, opencode corre | Archivos con checksum + unit de idempotencia |
| SA1.2 | Ingesta a Parquet con esquema único (sensor, satélite, fecha/hora, día/noche, lat, lon, confianza, FRP, tipo) | Sonnet | Unit sobre filas sintéticas de cada sensor |
| SA1.3 | Filtros: solo `type` vegetación (sin fuentes fijas ni mar adentro); confianza MODIS ≥ umbral, VIIRS nominal o alta; umbral configurable | Sonnet | Unit: cada filtro descarta lo esperado |
| SA1.4 | Grilla de Argentina: conteo por celda (0,1° y 0,25°) × día × sensor × día/noche | Sonnet escribe, opencode corre | Parquet particionado por año + unit de agregación |
| SA1.5 | Detecciones crudas de Argentina en DuckDB para consultas y CSV (postergado: el CSV sale del Parquet) | Sonnet | Consulta por polígono < 2 s en Córdoba |
| SA1.6 | Ingesta NRT de los meses sin standard por API de área (solo con `FIRMS_MAP_KEY`) | Sonnet | Una corrida trae el último día disponible |
| SA1.7 | Perfil de datos: focos por año, sensor y región; huecos | opencode | `reports/01/SA1.7.md` |

## Abierto

- Resuelto el 2026-11-14: cobertura Argentina (≈ 400 MB). Otros países, más adelante, con el mismo descargador.
