# Delegation templates

Definitions in `.claude/agents/`: `builder` (Sonnet), `researcher` (Haiku), `advisor` (Fable, until
2026-11-17). Opus orchestrates, plans and reviews; it does not delegate the review.

## builder (Sonnet): implement and test

```
Task: plan/NN-x.md, <ID>. Read only that file and the refs it names.
Allowed edit surfaces: <paths>
Done when: <task criterion>
Tests first when a deterministic test applies.
Return: changed files, commands run with results.
```

## researcher (Haiku): read code, APIs, sources and targeted unit tests

```
Question: <a single bounded question>
Look in: <paths or URLs>
Return: answer first, then evidence (file:line, URL or command output); mark what is not confirmed "unverified".
```

For unit tests: `Write unit tests for <module> under <tests path>; do not edit source.`

## advisor (Fable): complex problems only, until 2026-11-17

```
Problem: <decision or blocker>, with what was tried and the options on the table.
Read: <files>
Return: recommendation, main risk, and what evidence would change it. No edits.
```

## Long runs (cloud session or opencode)

```bash
opencode run --title "<ID>" "<prompt>"
```

Prompt: goal, paths in scope, constraints (do not edit code out of scope, no secrets), response format, and an
output file at `reports/<phase>/<ID>.md`.
