"""Item 1: the engine reproduces the wiki sanity table within 1 point.

The table was made with the illustrative fatigue constants, so these tests set them
explicitly; the constants in wp.py are calibrated (docs/evaluation.md).
"""
import numpy as np
import pytest
from numpy.random import SeedSequence

from dugout.engine import wp
from dugout.engine.wp import Flank, simulate_diff, summarize

N = 100_000
TOL = 0.01
ILLUSTRATIVE_SLOPE, ILLUSTRATIVE_FLOOR, ILLUSTRATIVE_BENCH = 0.6, 0.8, 1.03

# situation kwargs, (win, draw, loss) from the wiki sanity table
ROWS = {
    "0' equal": (dict(t0=0, home_goals=0, away_goals=0, lam_home90=1.35, lam_away90=1.35),
                 (0.359, 0.284, 0.358)),
    "0' 1.5 v 1.2": (dict(t0=0, home_goals=0, away_goals=0, lam_home90=1.5, lam_away90=1.2),
                     (0.432, 0.277, 0.290)),
    "80' 1-0": (dict(t0=80, home_goals=1, away_goals=0, lam_home90=1.5, lam_away90=1.2),
                (0.826, 0.157, 0.018)),
    "85' 2-0": (dict(t0=85, home_goals=2, away_goals=0, lam_home90=1.5, lam_away90=1.2),
                (0.990, 0.010, 0.001)),
}
LB = dict(t0=62, home_goals=1, away_goals=0, lam_home90=1.5, lam_away90=1.2,
          flank=Flank(c0=0.60, drain=0.008))
LB_ROWS = {
    "62' no change": (dict(), (0.687, 0.240, 0.073)),
    "62' sub now": (dict(sub_at=62), (0.726, 0.217, 0.057)),
    "62' sub at 78": (dict(sub_at=78), (0.712, 0.227, 0.062)),
}


@pytest.fixture(autouse=True)
def illustrative_constants(monkeypatch):
    monkeypatch.setattr(wp, "FATIGUE_SLOPE", ILLUSTRATIVE_SLOPE)
    monkeypatch.setattr(wp, "FATIGUE_FLOOR", ILLUSTRATIVE_FLOOR)


def check(diff, expected):
    out = summarize(diff)
    for got, want in zip((out.win, out.draw, out.loss), expected):
        assert got == pytest.approx(want, abs=TOL)
    assert out.win + out.draw + out.loss == pytest.approx(1.0)
    assert out.xpts == pytest.approx(3 * out.win + out.draw)


@pytest.mark.parametrize("name", list(ROWS))
def test_baseline_rows(name):
    kwargs, expected = ROWS[name]
    check(simulate_diff(**kwargs, seed=SeedSequence(7), n=N), expected)


@pytest.mark.parametrize("name", list(LB_ROWS))
def test_left_back_rows(name):
    extra, expected = LB_ROWS[name]
    check(simulate_diff(**LB, **extra, seed=SeedSequence(7), n=N, sub_quality=ILLUSTRATIVE_BENCH), expected)


def test_same_seed_is_reproducible():
    a = simulate_diff(**LB, seed=SeedSequence(3), n=5_000)
    b = simulate_diff(**LB, seed=SeedSequence(3), n=5_000)
    assert np.array_equal(a, b)


def test_does_not_touch_global_randomness():
    np.random.seed(123)
    before = np.random.random()
    np.random.seed(123)
    simulate_diff(**LB, seed=SeedSequence(3), n=1_000)
    assert np.random.random() == before
