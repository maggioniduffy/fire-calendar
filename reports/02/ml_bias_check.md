# LightGBM cell-model bias: is it structural?

Run: 2026-11-15, with `backend/scripts/ml_bias_check.py` on the cache of the final run of
`firecal harmonize evaluate --ml` (no retraining). Source: NASA FIRMS per-country files, standard processing;
leave-one-year-out with a 6-month gap, 14 test years (2012–2025). Retrospective; not an alert system.

## Hypothesis

The cell model only predicts on rows where the source is active in the cell or in its 3×3 neighborhood, but it is
evaluated against all target detections. Detections outside those rows are unreachable, so the total bias should
be approximately `−(fraction outside the rows)`.

## Result: structural in the total, not in individual years

| Direction | Fraction outside the rows | Cell bias vs. all | Cell bias vs. its rows | SA2.2 bias |
|---|---|---|---|---|
| SA2.4 VIIRS → MODIS | 2.58 % | −2.52 % | +0.06 % | +0.93 % |
| SA2.7 MODIS → VIIRS | 6.22 % | −6.73 % | −0.54 % | −0.95 % |

- **Total (verified):** counted over its own rows, the cell model's bias is almost zero (+0.06 % and −0.54 %). The
  negative total bias comes from detections the model cannot reach. The relation
  `total_bias = (1 + row_bias) × (1 − fraction_outside) − 1` holds exactly, but it is an accounting identity; the
  real test is that `row_bias ≈ 0`, and in the total it holds.
- **Per year (not structural):** the bias on its rows ranges from −10.0 % to +3.6 % (SA2.4) and from −8.9 % to
  +5.3 % (SA2.7), while the fraction outside ranges from 0.9 % to 9.4 %. The fraction outside explains only a few
  points of each year.
- **Worst SA2.4 year (2024, −12.4 %):** fraction outside 2.7 %; on its rows it is still −10.0 %. Not structural,
  and SA2.2 has almost the same bias that year (−10.2 %): it is a hard year for both methods, not a defect of
  LightGBM itself. The cause remains unverified (2024 is the year the Terra/Aqua ratio changes, see the stability
  table in `baselines.md`).
- **Worst SA2.7 year (2022, −13.0 %):** fraction outside 4.6 %; on its rows −8.9 %; SA2.2 −10.7 % that year.
- **SA2.2 does not change** when restricted to the cell model's reach (+0.93 % and −0.95 %): only 0.02 % and
  0.30 % of detections fall in block-months where SA2.2 predicts 0.

## What changes

The verdict does not change: the publication criterion was fixed before the run, and the cell model fails the
total bias as evaluated. What is learned: if the cell model were to be improved, the missing piece is estimating
the detections outside its rows (for example with the block factor), not correcting the model within them. That
would be a new design and a new run with the criterion fixed in advance, not an adjustment of this one.

Comparison not used in the verdict: "SA2.2 vs. the cell model's rows" (+3.6 % and +5.6 %) is not fair, because
SA2.2 works per block and was not trained on those rows.

Reproduce: `cd backend && uv run python scripts/ml_bias_check.py <ml-cache.pkl>`.
