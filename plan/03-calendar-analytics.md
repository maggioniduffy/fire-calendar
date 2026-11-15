# Fase 3 — Calendario y análisis por área

Estado: activa · Depende de: 2 · Refs: `docs/architecture.md` (API)

## Objetivo

Para un área y un rango de fechas, todo lo que pide el desafío: calendario, meses y años más activos, anomalía
del mes actual y CSV.

## Tareas

| ID | Tarea | Agente | Hecho cuando |
|---|---|---|---|
| SA3.1 | Área: polígono GeoJSON, o lat/lon + radio; validación de tamaño | Sonnet | Unit de área válida e inválida. Hecho ✅ (2026-11-15; círculo de 5–500 km o polígono GeoJSON de 100 a 3.000.000 km² dentro de la caja de Argentina; preset Córdoba = rectángulo aproximado, sin verificar) |
| SA3.2 | Matriz año×mes de focos reportados por sensor y armonizados en las dos escalas (MODIS-eq, VIIRS-eq con 2000–2011 marcado como estimado) | Sonnet | Unit sobre grilla sintética. Hecho ✅ (2026-11-15; sobre el esquema publicado de `harmonized`; banda del área = banda de bloque escalada por la fracción del área y sumada entre bloques, sin verificar. Córdoba: VIIRS-eq estimado 2000-11 a 2012-01, 135 meses) |
| SA3.3 | Climatología: mediana y p10–p90 por mes; anomalía del mes en curso (absoluta y en percentil) | Sonnet | Unit con valores conocidos. Hecho ✅ (2026-11-15; cuantiles lineales de numpy sobre años completos, sin el año de referencia; mes de referencia = último mes disponible, retrospectivo) |
| SA3.4 | Cifras clave: mes y año más activos, total del período, comparación del mes actual con la mediana | Sonnet | Unit. Hecho ✅ (2026-11-15; año más activo solo entre años completos; se informa cuántos meses estimados entran en el total) |
| SA3.5 | Endpoints: `POST /calendar`, `POST /stats`, `POST /export.csv` | Sonnet | Unit de API + respuesta con fuente y período |
| SA3.6 | CSV: focos crudos donde existen (Argentina), conteos por celda en el resto; matriz del calendario | Sonnet | Unit: columnas y filas esperadas |
