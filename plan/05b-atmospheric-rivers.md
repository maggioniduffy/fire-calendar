# Phase 5b — Atmospheric rivers and fire (optional)

Status: deferred · Depends on: 4 · Refs: clima-ideas `plan/01-atmospheric-rivers.md` and `plan/00-foundations.md` (F0.9) at https://github.com/maggioniduffy/clima-ideas

Only if the app (phase 4) already works.

## Question

Does the arrival (or absence) of atmospheric rivers mark the end or the severity of the fire season? It applies
mostly to the Andes and Patagonia; in subtropical South America, to the low-level jet (unverified how much it
weighs in Córdoba).

## Atmospheric river–fire relationship (hypotheses to measure)

Contributed by the user on 2026-10-28; cited source: Stanford Doerr School of Sustainability (no URL, unverified).

1. **Immediate relief:** heavy rain puts out or slows active fires and wets dry soils during drought. Measurable:
   drop in hot spots in the days after an atmospheric river.
2. **Deferred risk:** a very wet period grows grass and shrubs that later dry out and leave fine fuel; danger rises
   in the following dry season. Measurable: days with an atmospheric river (or rain) in the wet season vs. hot
   spots in the following dry one, with a lag of months.
3. **Debris flows after fire:** torrential rain over a recently burned area, which neither absorbs water nor holds
   the soil, triggers debris flows, landslides and flash floods. Connects with phase 4 of clima-ideas
   ([plan/04-debris-flows.md](https://github.com/maggioniduffy/clima-ideas/blob/main/plan/04-debris-flows.md)): burned areas as a susceptibility factor.

## Tasks

| ID | Task | Agent | Done when |
|---|---|---|---|
| SA5b.1 | If clima-ideas phase 1 has events, import them; if not, ERA5 IVT for the region | opencode | Events or daily IVT in Zarr |
| SA5b.2 | Baseline detector: IVT ≥ 250 kg m⁻¹ s⁻¹ with minimum persistence | Sonnet | Unit on a synthetic field |
| SA5b.3 | TECA BARD only if clima-ideas F0.9 left it working; compare with SA5b.2 | opencode | Agreement table, or "not used" |
| SA5b.4 | Atmospheric-river days per month: extra calendar row and variable for phase 6 | Sonnet | e2e |
| SA5b.5 | Measure relationships 1 and 2: hot spots before and after each event (event composite) and lagged correlation between wet and dry season | opencode analyzes, Sonnet codes | `reports/05b/SA5b.5.md` with CI, or "no signal" |
| SA5b.6 | Relationship 3: list of heavy-rain events over areas burned in the previous 12 months (MCD64A1/VNP64A1 burned areas) as input for clima-ideas phase 4 | opencode | Case table with date, area and source |
