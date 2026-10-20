"""Items 2 and 3: options on common random numbers, and strength labels.

Run with the illustrative fatigue constants, so the expectations below do not move
when wp.py's calibrated constants are refitted.
"""
from functools import partial

import pytest
from numpy.random import SeedSequence

from dugout.engine import options, wp
from dugout.engine.options import Option, default_options, strength_label
from dugout.engine.wp import Flank

SITUATION = dict(t0=62, home_goals=1, away_goals=0, lam_home90=1.5, lam_away90=1.2,
                 flank=Flank(c0=0.60, drain=0.008))


evaluate = partial(options.evaluate, sub_quality=1.03)


@pytest.fixture(autouse=True)
def illustrative_constants(monkeypatch):
    monkeypatch.setattr(wp, "FATIGUE_SLOPE", 0.6)
    monkeypatch.setattr(wp, "FATIGUE_FLOOR", 0.8)


def by_id(results):
    return {r.id: r for r in results}


def test_identical_options_have_zero_gap():
    twins = [Option("no_change", "No change"), Option("twin", "Same again")]
    res = by_id(evaluate(SITUATION, twins, SeedSequence(1), n=5_000))
    assert res["twin"].delta_win == 0.0
    assert res["twin"].ci90 == (0.0, 0.0)


def test_no_change_is_the_reference():
    res = by_id(evaluate(SITUATION, default_options(62), SeedSequence(1), n=5_000))
    assert res["no_change"].delta_win == 0.0
    assert res["no_change"].ci90 is None


def test_default_options_cover_the_four_choices():
    assert [o.id for o in default_options(62)] == ["no_change", "sub_like_for_like", "attacking", "defensive"]


def test_probabilities_sum_to_one_and_xpts_follow():
    for r in evaluate(SITUATION, default_options(62), SeedSequence(1), n=5_000):
        assert r.win + r.draw + r.loss == pytest.approx(1.0)
        assert r.xpts == pytest.approx(3 * r.win + r.draw)


def test_like_for_like_sub_helps_a_tired_flank():
    r = by_id(evaluate(SITUATION, default_options(62), SeedSequence(1), n=50_000))["sub_like_for_like"]
    assert r.delta_win > 0
    assert r.ci90[0] < r.delta_win < r.ci90[1]


def test_interval_narrows_as_runs_grow():
    def width(n):
        r = by_id(evaluate(SITUATION, default_options(62), SeedSequence(1), n=n))["sub_like_for_like"]
        return r.ci90[1] - r.ci90[0]

    assert width(40_000) < width(2_500) / 2


def test_defensive_lowers_both_rates_so_it_protects_a_lead():
    r = by_id(evaluate(SITUATION, default_options(62), SeedSequence(1), n=50_000))
    assert r["defensive"].delta_win > 0 > r["attacking"].delta_win


@pytest.mark.parametrize("points,label", [
    (0.0, "toss_up"), (0.99, "toss_up"), (1.0, "lean"), (2.99, "lean"), (3.0, "strong"), (7.5, "strong"),
])
def test_strength_boundaries(points, label):
    assert strength_label(points) == label
