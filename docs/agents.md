# Delegation templates

## Sonnet

```
Task: plan/NN-x.md, <ID>. Read only that file and the refs it names.
Allowed edit surfaces: <paths>
Done when: <task criterion>
Tests first when a deterministic test applies.
Return: changed files, commands run with results.
```

## Long runs (cloud session or opencode)

```bash
opencode run --title "<ID>" "<prompt>"
```

Prompt: goal, paths in scope, constraints (do not edit code out of scope, no secrets), response format, and an
output file at `reports/<phase>/<ID>.md`.
