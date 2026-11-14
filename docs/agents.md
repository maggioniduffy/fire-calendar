# Plantillas de delegación

Definiciones en `.claude/agents/`: `builder` (Sonnet), `researcher` (Haiku), `advisor` (Fable, hasta el
2026-11-17). Opus orquesta, planifica y revisa; no delega la revisión.

## builder (Sonnet): implementar y testear

```
Task: plan/NN-x.md, <ID>. Read only that file and the refs it names.
Allowed edit surfaces: <paths>
Done when: <criterio de la tarea>
Tests first when a deterministic test applies.
Return: changed files, commands run with results.
```

## researcher (Haiku): leer código, APIs, fuentes y unit tests puntuales

```
Question: <una sola pregunta acotada>
Look in: <rutas o URLs>
Return: answer first, then evidence (file:line, URL or command output); mark "sin verificar" what is not confirmed.
```

Para unit tests: `Write unit tests for <módulo> under <ruta de tests>; do not edit source.`

## advisor (Fable): solo problemas complejos, hasta el 2026-11-17

```
Problem: <decisión o bloqueo>, with what was tried and the options on the table.
Read: <archivos>
Return: recommendation, main risk, and what evidence would change it. No edits.
```

## Corridas largas (sesión en la nube u opencode)

```bash
opencode run --title "<ID>" "<prompt>"
```

Prompt: objetivo, rutas en alcance, restricciones (no editar código fuera de alcance, no secretos),
formato de respuesta, y archivo de salida en `reports/<fase>/<ID>.md`.
