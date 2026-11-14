"""Error metrics shared by the harmonization baselines (and the ML models that must beat them)."""

import numpy as np

POISSON_EPS = 1e-3  # floor for the predicted mean in the Poisson deviance (counts, so well below 1)


def _flat(obs, pred) -> tuple[np.ndarray, np.ndarray]:
    return np.asarray(obs, dtype="float64").ravel(), np.asarray(pred, dtype="float64").ravel()


def relative_bias(obs, pred) -> float:
    """sum(pred) / sum(obs) - 1; nan when there is nothing observed."""
    o, p = _flat(obs, pred)
    return float(p.sum() / o.sum() - 1) if o.sum() > 0 else float("nan")


def wape(obs, pred) -> float:
    """Weighted absolute percentage error: sum|pred - obs| / sum(obs)."""
    o, p = _flat(obs, pred)
    return float(np.abs(p - o).sum() / o.sum()) if o.sum() > 0 else float("nan")


def mae(obs, pred) -> float:
    o, p = _flat(obs, pred)
    return float(np.abs(p - o).mean()) if o.size else float("nan")


def poisson_deviance(obs, pred, eps: float = POISSON_EPS) -> float:
    """Mean Poisson deviance 2 * (y log(y / mu) - (y - mu)), with y log(y / mu) = 0 at y = 0, mu >= eps."""
    o, p = _flat(obs, pred)
    if not o.size:
        return float("nan")
    mu = np.maximum(p, eps)
    with np.errstate(divide="ignore", invalid="ignore"):
        term = np.where(o > 0, o * np.log(np.where(o > 0, o, 1.0) / mu), 0.0)
    return float((2 * (term - (o - mu))).mean())


def summarize(obs, pred) -> dict[str, float]:
    return {
        "bias": relative_bias(obs, pred),
        "wape": wape(obs, pred),
        "mae": mae(obs, pred),
        "deviance": poisson_deviance(obs, pred),
    }
