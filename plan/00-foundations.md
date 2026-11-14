# Fase 0 — Bases

Estado: activa · Refs: `docs/architecture.md`, `docs/design.md` (solo SA0.4–SA0.5), `docs/agents.md`, `docs/research/data-sources.md`

## Objetivo

Repo listo para sumar capas y acceso a datos resuelto.

## Tareas

| ID | Tarea | Agente | Hecho cuando |
|---|---|---|---|
| SA0.1 | Reglas de Space Apps 2026: código o datos preparados antes del evento, licencia, entregables (video, slides, página del proyecto, repo público) → `docs/research/rules.md` | Opus | Hecho (histórico: ya no se compite) ✅ |
| SA0.2 | Monorepo según `docs/architecture.md`: `backend/` (uv, Python 3.12, paquete `firecal`) y `web/` (pnpm, Vite, React, TS, deck.gl); `Makefile`; `data/` fuera de git | Sonnet | `make dev` levanta API y app. Mitad backend hecha ✅; mitad web hecha ✅ (`web/` con `dev`, `build`, `test`, `e2e`); faltan los targets `web*` del `Makefile` |
| SA0.3 | CI (GitHub Actions): ruff, pytest, eslint, tsc, vitest, Playwright | Sonnet | CI verde en un PR. Job backend (ruff, pytest) hecho ✅; job web pendiente de `web/` |
| SA0.4 | Tokens de `docs/design.md`, tema claro/oscuro, `web/src/i18n/es.ts` y `en.ts` | Sonnet | Cambio de tema y de idioma sin recarga; ningún string fuera de i18n ✅ |
| SA0.5 | Shell de la app según el canvas: barra superior con desafío y autor, panel izquierdo, mapa, inspector, franja del calendario | Sonnet | Layout fijo en ambos temas y a ancho de teléfono ✅ |
| SA0.6 | FastAPI (`/health`, `/layers`, `/layers/{id}`) y manifiesto validado con pydantic según `docs/architecture.md`, con `source`, `period`, `license` y campo opcional `experimental` | Sonnet | Unit de manifiesto válido e inválido. Hecho ✅ |
| SA0.7 | Capa de prueba de punta a punta con focos falsos | Sonnet | e2e: la capa aparece y se inspecciona. Lado web ✅ con fixture estático; falta servirla desde la API |
| SA0.8 | Acceso a datos (lista abajo) → `docs/research/data-sources.md` | Opus | FIRMS verificado el 2026-11-14; el resto pendiente (postergado salvo lo que pida la fase activa) |
| SA0.9 | ONI mensual (NOAA CPC) y fase ENSO por mes, portando `docs/reference/enso.py` (clima-ideas F0.10) a `firecal.io.enso` | Sonnet | Parquet + unit de umbrales sobre serie sintética. Código y unit hechos ✅ (regla CPC de 5 estaciones); corrida real pendiente: `www.cpc.ncep.noaa.gov` bloqueado en la sesión en la nube |

## SA0.8: qué investigar

FIRMS ✅ (ver `docs/research/data-sources.md`) · Catálogo de Focos de Calor y
Áreas Quemadas y Visor Temático de CONAE (acceso, licencia) · SPI/SPEI: CHIRPS, ERA5, SPEIbase · FWI de
Copernicus CEMS · cobertura del suelo global (MODIS MCD12Q1 o ESA WorldCover) · deriva orbital de Terra y Aqua
y fechas de fin de misión · dónde desplegar la demo gratis.

## Tests

Unit: manifiesto, fase ENSO, store de tema e idioma. e2e: shell, tema, idioma, capa de prueba.
