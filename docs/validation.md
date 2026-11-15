# Validation

Adapted from scheme F6.2 of clima-ideas. No random k-fold: neighboring days and months of the same year (and of the
same ENSO year) leak information between training and test.

- **External, leave-one-year-out with a gap:** each year is the test set once; the 6 months before and after that
  year are removed from training. Error is reported per year, per region and per ENSO phase.
- **Internal, nested:** hyperparameters and feature selection are chosen only inside the training set of each
  external split. The external test year never touches that choice.
- **Inputs as they were available** (prediction only, phase 6): no variable with an availability date later than
  the issue date.
- **Control:** the same scheme with a pure rolling origin (train up to year t, evaluate t+1), to see whether the
  error changes in recent years.
- **Baseline always alongside:** each model is compared with the simplest method for its task (scale factor for
  harmonization, climatology and persistence for prediction). The simplest one that does not lose is published.
- Unit: no test date, gap included, appears in the training set of its split.
