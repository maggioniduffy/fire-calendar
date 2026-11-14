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
