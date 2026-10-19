import subprocess
import sys

import pytest

from dugout.sim.counterfactual import NO_CHANGE, Option, play_to, true_gap
from dugout.sim.match import new_match

SUB_LB = Option("sub_lb", "Replace left-back (RFC-03 for RFC-15)", subs=(("RFC-03", "RFC-15"),))


@pytest.fixture(scope="module")
def at_62(scenario):
    s, _ = new_match(scenario, 1)
    play_to(s, 62)
    return s


def test_play_to_stops_at_the_minute(at_62):
    assert (at_62.period, at_62.clock_s) == (2, 62 * 60)
    assert at_62.players["RFC-03"].on_pitch


def test_true_gap_at_62(at_62):
    before = at_62.to_dict()
    results = true_gap(at_62, "RFC", [NO_CHANGE, SUB_LB], n=60)
    assert at_62.to_dict() == before
    base, sub = results
    assert (base.id, sub.id) == ("no_change", "sub_lb")
    for r in results:
        assert r.win + r.draw + r.loss == pytest.approx(1.0)
        assert r.xpts == pytest.approx(3 * r.win + r.draw)
    assert base.delta_win == 0.0 and base.delta_xpts == 0.0
    assert sub.delta_win == pytest.approx(sub.win - base.win)
    assert (sub.win, sub.draw, sub.loss) != (base.win, base.draw, base.loss)


def test_common_random_numbers_give_zero_gap_for_an_identical_option(at_62):
    same = Option("same", "No change under another name")
    base, twin = true_gap(at_62, "RFC", [NO_CHANGE, same], n=40)
    assert (twin.win, twin.draw, twin.loss) == (base.win, base.draw, base.loss)
    assert twin.delta_win == 0.0


def test_true_gap_is_repeatable(at_62):
    assert true_gap(at_62, "RFC", [NO_CHANGE, SUB_LB], n=30) == true_gap(at_62, "RFC", [NO_CHANGE, SUB_LB], n=30)


def test_true_gap_needs_no_change_and_legal_subs(at_62):
    with pytest.raises(ValueError):
        true_gap(at_62, "RFC", [SUB_LB], n=5)
    with pytest.raises(ValueError):
        true_gap(at_62, "RFC", [NO_CHANGE, Option("bad", "bad", subs=(("RFC-03", "CAS-15"),))], n=5)


def test_cli_gap_prints_a_true_gap():
    out = subprocess.run([sys.executable, "-m", "dugout.sim", "gap", "--seed", "1", "--minute", "62",
                          "--team", "RFC", "--off", "RFC-03", "--on", "RFC-15", "--n", "20"],
                         check=True, capture_output=True, text=True).stdout
    assert "no_change" in out and "sub" in out and "true gap" in out
