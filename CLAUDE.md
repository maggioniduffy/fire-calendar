# fire-calendar

Harmonized MODIS + VIIRS fire calendar. Born for the CONAE challenge of the NASA Space Apps Challenge 2026,
"Harmonization of MODIS and VIIRS Hot Spots" (COR-CAT-08 at the Córdoba venue). It is not competing: the hackathon
deadline does not apply. Author: Faustino Maggioni Duffy. Guided by [plan.md](plan.md).

Architecture and practices taken from [clima-ideas](https://github.com/maggioniduffy/clima-ideas); what is needed
is copied into `docs/` so this repo reads on its own.

## Workflow

- Start every task in plan mode, unless told otherwise.
- Load only `plan.md` and the active phase; the `docs/` references only when the task asks for them.
- When closing a task: mark it in its phase and update the status in `plan.md`.

## Orchestration

| Role | Who | Does |
|---|---|---|
| Plan, orchestration, review | Opus (main session) | Splits tasks, delegates, reviews diffs and reports |
| Implement and fix | Sonnet (subagent) | Code, unit tests (pytest, vitest) and e2e (Playwright) |
| Long runs and large data | cloud session or opencode | Downloads, pipeline, training, slow suites |

Delegation templates: [docs/agents.md](docs/agents.md). Cycle per task: passed by reference
(`plan/NN-*.md`, ID, allowed files, "done" criterion); the agent returns the result and the commands it ran with
summarized output; Opus reviews `git status`, `git diff --stat` and one focused test.

## Scope

- Data: all of Argentina (FIRMS per-country files). Initial view: Córdoba province, or an area of similar size
  around the user if they agree to share their location.
- UI in Spanish first, with complete English. The UI shows the challenge name and the author.

## Rules

- Code, file names and commits in English (Conventional Commits). Documentation, plans and phases in English. UI in
  Spanish first.
- Nothing invented: anything unverified is marked "unverified"; every modeled figure shows source and period.
- ML only with a simple baseline next to it; if it does not beat the baseline, say so and use the baseline.
- This is not an alert system. Everything is retrospective; phase 6 (deferred) would be "Experimental", with a
  baseline and uncertainty. Associations (ENSO and fire) are shown as association, never as cause.
- `data/` and `.env` stay out of git. Heavy runs happen locally with a 4 GB RAM cap
  (`systemd-run --user --scope -p MemoryMax=4G ...`) and few workers.
