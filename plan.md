# Plan: calendario de fuego armonizado MODIS + VIIRS

Desafío de CONAE del NASA Space Apps Challenge 2026, "Harmonization of MODIS and VIIRS Hot Spots". No se compite;
sin plazo. Autor: Faustino Maggioni Duffy.

Producto: pipeline Python que arma una serie de focos de calor armonizada 2000–hoy para Argentina en dos escalas
(MODIS-equivalente y VIIRS-equivalente, que sigue cuando MODIS se apague) y una app web con calendario año×mes,
anomalías, fase ENSO y CSV descargable.

Docs: [arquitectura](docs/architecture.md), [diseño](docs/design.md), [validación](docs/validation.md),
[fuentes de datos](docs/research/data-sources.md), [delegación](docs/agents.md).

## Fases

| # | Fase | Archivo | Depende de | Estado |
|---|---|---|---|---|
| 0 | Bases y acceso a datos | [plan/00-foundations.md](plan/00-foundations.md) | — | activa |
| 1 | Datos FIRMS: descarga, filtros, grilla | [plan/01-data.md](plan/01-data.md) | 0 | activa |
| 2 | Armonización MODIS–VIIRS + ML | [plan/02-harmonization.md](plan/02-harmonization.md) | 1 | activa (parte postergada) |
| 3 | Calendario y análisis por área | [plan/03-calendar-analytics.md](plan/03-calendar-analytics.md) | 2 | activa |
| 4 | App web | [plan/04-web-app.md](plan/04-web-app.md) | 0, 3 | activa |
| 5 | ENSO y fuego (solo ENSO-lite) | [plan/05-enso-drought.md](plan/05-enso-drought.md) | 3, SA0.9 | activa (sequía postergada) |
| 5b | Ríos atmosféricos y fuego | [plan/05b-atmospheric-rivers.md](plan/05b-atmospheric-rivers.md) | 4 | postergado |
| 6 | Predicción experimental | [plan/06-ml-outlook.md](plan/06-ml-outlook.md) | 2, 5 | postergado |
| 7 | Publicación | [plan/07-submission.md](plan/07-submission.md) | 4 | activa |

## Orden

0 → (backend SA0.2/SA0.6 ∥ web SA0.4/SA0.5) → 1 → 2 → 3 → (4 ∥ 5 ENSO-lite) → 7.

Si algo se demora, se recorta en este orden: pestaña Dashboard (SA4.8), análisis de rezagos SA5.5 (queda la fila
de fase ENSO), LightGBM (queda el factor de escala), NRT.

## Avance

- 2026-11-14: repo separado de clima-ideas (antes `space-apps/` en la rama `claude/space-apps-fire-calendar-plan`).
  Fuentes FIRMS verificadas. SA0.1 hecho (reglas del evento, ya sin efecto).
- 2026-11-14: backend `firecal` (uv, Python 3.12), Makefile, CI backend, manifiesto + API (SA0.2 backend, SA0.3
  backend, SA0.6), ONI y fase ENSO (SA0.9), descarga, ingesta, filtros y grilla FIRMS (SA1.1–SA1.4), todo con unit
  tests sin red. La sesión en la nube no llega a FIRMS ni a CPC (proxy 403), así que la descarga real y SA1.7
  quedan para una corrida local: `make install`, `cd backend && uv run firecal enso build`,
  `uv run firecal firms download`, `ingest`, `grid`, `profile`.
- 2026-11-14: se habilitaron FIRMS y CPC en el entorno de la nube y se corrió todo. ONI: 921 meses (1950-01 a
  2026-09). FIRMS: 48 archivos 2000–2025; sin archivo standard 2026 todavía. SA1.1–SA1.4 y SA1.7 hechos
  ([reports/01/SA1.7.md](reports/01/SA1.7.md)). Abierto para la fase 2: el código `version` de MODIS cambia en 2018
  y 2023 (sin verificar qué implica).
- 2026-11-14: flujo de agentes en `.claude/agents/` (Opus orquesta, Sonnet construye, Haiku investiga, Fable
  asesora hasta el 2026-11-17). Web en Makefile y CI con eslint (SA0.2, SA0.4, SA0.5, SA0.7 hechos; SA0.3 espera
  un PR). Códigos `version` de MODIS revisados en `docs/research/data-sources.md`: sin cambio de algoritmo entre
  C6 y C6.1; desde 2018 más focos tipo 2. Fase 2: diseño de baselines decidido, SA2.1, SA2.2, SA2.3 y SA2.5
  hechos ([reports/02/baselines.md](reports/02/baselines.md)): gana el factor de escala. Siguiente: intervalos
  de la serie inversa con cobertura real, después SA2.4 y SA2.7 (LightGBM) contra ese baseline.
- 2026-11-14: intervalos conformales anidados para SA2.2, con cota aditiva para predicciones chicas y filas
  definidas por la fuente: cobertura 80 % (nominal 80 %) en los dos sentidos, bloque-mes y bloque-año; el peor
  año bloque-año baja a 67–72 %. Solo 0,3 % de las detecciones VIIRS caen donde MODIS no vio nada. Diseño de
  LightGBM y criterio de publicación fijados en `plan/02-harmonization.md`; siguiente: SA2.4 y SA2.7.

