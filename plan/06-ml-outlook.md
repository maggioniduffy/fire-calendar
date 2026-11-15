# Phase 6 — Experimental prediction

Status: deferred · Depends on: 2, 5 · Refs: `docs/validation.md`; frozen registry and experimental layer as clima-ideas F6.4 and F6.6 (https://github.com/maggioniduffy/clima-ideas/blob/main/plan/06-forecast.md)

Experimental: nobody uses it to decide. It measures whether a model predicts fire activity better than the
climatology.

## Question

What is the probability that next month has more hot spots than the area's median (terciles)?

## Tasks

| ID | Task | Agent | Done when |
|---|---|---|---|
| SA6.1 | Variables: ONI and its forecast, recent SPEI, FWI, hot-spot anomaly of the previous month, month of the year; atmospheric-river days if 5b exists | Sonnet | Unit: no variable with an availability date later than the issue date |
| SA6.2 | Baselines: climatology, persistence and analog years with the same ENSO phase | Sonnet | Unit |
| SA6.3 | Logistic regression and LightGBM validated with scheme F6.2 | Sonnet implements, opencode trains | RPS and Brier per test year vs. each baseline |
| SA6.4 | Frozen registry of predictions, as clima-ideas F6.4 | Sonnet | Unit: cannot be edited or issued with a past date |
| SA6.5 | "Experimental" layer with probability, uncertainty, skill and a fixed notice "Experimental, not an alert" | Sonnet | e2e: see prediction, skill and notice |

## Rules

Maximum horizon: 6 months. No projections of decades; that requires climate scenarios and is out of scope.

If a model does not beat the climatology, we report it and the layer shows it.
