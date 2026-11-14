# fire-calendar

Calendario de fuego armonizado MODIS + VIIRS. Nació para el desafío de CONAE del NASA Space Apps Challenge 2026,
"Harmonization of MODIS and VIIRS Hot Spots" (COR-CAT-08 en la sede Córdoba). No se compite: el plazo de la
hackatón no aplica. Autor: Faustino Maggioni Duffy. Guiado por [plan.md](plan.md).

Arquitectura y prácticas tomadas de [clima-ideas](https://github.com/maggioniduffy/clima-ideas); lo necesario está
copiado en `docs/` para que este repo se lea solo.

## Flujo

- Empezar toda tarea en modo plan, salvo que se indique lo contrario.
- Cargar solo `plan.md` y la fase activa; las referencias de `docs/` solo cuando la tarea lo pide.
- Al cerrar una tarea: marcarla en su fase y actualizar el estado en `plan.md`.

## Orquestación

| Rol | Quién | Hace |
|---|---|---|
| Plan, orquestación, revisión | Opus (sesión principal) | Divide tareas, delega, revisa diffs e informes |
| Implementar y testear | Sonnet (subagente `builder`) | Código, unit tests (pytest, vitest) y e2e (Playwright) |
| Investigar y leer | Haiku (subagente `researcher`) | Lectura del código, APIs y fuentes de datos, unit tests puntuales |
| Asesor | Fable (subagente `advisor`), hasta el 2026-11-17 | Segunda opinión solo en tareas o problemas complejos; no edita |
| Corridas largas y datos grandes | sesión en la nube u opencode | Descargas, pipeline, entrenamientos, suites lentas |

Los subagentes están definidos en `.claude/agents/`. Plantillas de delegación: [docs/agents.md](docs/agents.md).
Ciclo por tarea: se pasa por referencia (`plan/NN-*.md`, ID, archivos permitidos, criterio de "hecho"); el agente
devuelve resultado y comandos con su salida resumida; Opus revisa `git status`, `git diff --stat` y un test
enfocado.

## Alcance

- Datos: Argentina completa (archivos FIRMS por país). Vista inicial: provincia de Córdoba, o un área de tamaño
  similar alrededor del usuario si acepta compartir su ubicación.
- UI en español primero, con inglés completo. La UI muestra el nombre del desafío y el autor.

## Reglas

- Código, nombres de archivo y commits en inglés (Conventional Commits). UI en español primero.
- Nada inventado: lo no verificado se marca "sin verificar"; todo dato modelado muestra fuente y período.
- ML solo con un baseline simple al lado; si no le gana, se informa y se usa el baseline.
- No es un sistema de alerta. Todo es retrospectivo; la fase 6 (postergada) sería "Experimental", con baseline e
  incertidumbre. Asociaciones (ENSO y fuego) se muestran como asociación, nunca como causa.
- `data/` y `.env` fuera de git. Corridas pesadas en local con tope de 4 GB de RAM
  (`systemd-run --user --scope -p MemoryMax=4G ...`) y pocos workers.
