import numpy as np
import pytest

from firecal.stages.harmonize.metrics import (
    mae,
    poisson_deviance,
    relative_bias,
    summarize,
    wape,
)

OBS = np.array([10.0, 20.0, 30.0, 40.0])
PRED = np.array([12.0, 18.0, 33.0, 40.0])


def test_relative_bias_hand_computed():
    assert relative_bias(OBS, PRED) == pytest.approx(103 / 100 - 1)


def test_wape_hand_computed():
    assert wape(OBS, PRED) == pytest.approx((2 + 2 + 3 + 0) / 100)


def test_mae_hand_computed():
    assert mae(OBS, PRED) == pytest.approx(7 / 4)


def test_poisson_deviance_hand_computed():
    # y=0, mu=1 -> 2; y=2, mu=1 -> 2 * (2 ln 2 - 1); mean = 2 ln 2
    assert poisson_deviance([0, 2], [1, 1]) == pytest.approx(2 * np.log(2))


def test_perfect_prediction_has_zero_error():
    s = summarize(OBS, OBS)
    assert s == {"bias": 0.0, "wape": 0.0, "mae": 0.0, "deviance": pytest.approx(0.0)}


def test_nothing_observed_is_nan_not_an_error():
    assert np.isnan(relative_bias([0, 0], [1, 1]))
    assert np.isnan(wape([0, 0], [1, 1]))


def test_deviance_is_finite_when_prediction_is_zero():
    assert np.isfinite(poisson_deviance([5, 0], [0, 0]))
