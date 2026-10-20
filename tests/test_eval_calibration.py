"""The engine runs on the constants fitted by `python -m eval.counterfactual calibrate`."""
import json

from dugout.engine import options, wp
from eval.counterfactual import CALIBRATION_JSON, FIT_SEEDS, TEST_SEEDS


def test_wp_constants_are_the_fitted_ones():
    fitted = json.loads(CALIBRATION_JSON.read_text(encoding="utf-8"))["fitted"]
    assert (wp.FATIGUE_SLOPE, wp.FATIGUE_FLOOR, wp.BENCH_QUALITY) == (
        fitted["slope"], fitted["floor"], fitted["bench"])
    assert options.BENCH_QUALITY == wp.BENCH_QUALITY


def test_fit_and_test_seeds_do_not_overlap():
    assert not set(FIT_SEEDS) & set(TEST_SEEDS)
    assert 73 in TEST_SEEDS
