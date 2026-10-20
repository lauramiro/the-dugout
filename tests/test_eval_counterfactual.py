"""Counterfactual check: the same moment on both sides, and gaps computed as the
engine and the simulator compute them."""
import pytest

from dugout.engine import wp
from dugout.engine.payload import _exposed_player, decide
from dugout.sim.counterfactual import NO_CHANGE, Option, true_gap
from dugout.sim.match import new_match
from eval.counterfactual import (_base_row, constants, decision_points, engine_gap, like_for_like_bench,
                                 step_to, true_pair)


@pytest.fixture(scope="module")
def seed2(scenario):
    points, snaps = decision_points(2)
    return points, snaps


def test_step_to_reaches_the_snapshot_moment(scenario, seed2):
    points, _ = seed2
    p = next(p for p in points if p["period"] == 2)
    s, _ = new_match(scenario, 2)
    step_to(s, p["period"], p["t_ms"])
    assert (s.period, s.clock_s * 1000) == (p["period"], p["t_ms"])
    assert s.score == p["snapshot"]["score"]
    on = {q.id for q in s.players.values() if q.on_pitch}
    assert on == {q["id"] for q in p["snapshot"]["players"]}


def test_engine_gap_matches_decide(seed2):
    points, _ = seed2
    p = points[-1]
    payload = decide(p["snapshot"], p["team"], p["trigger"])
    sub = next(o for o in payload["options"] if o["id"] == "sub_like_for_like")
    row = _base_row(2, p["id"], "trigger", p["team"], p["trigger"], p["snapshot"],
                    _exposed_player(p["snapshot"], p["team"]))
    gap, lo, hi = engine_gap(row, wp.FATIGUE_SLOPE, wp.FATIGUE_FLOOR, wp.BENCH_QUALITY)
    assert [round(gap, 3), round(lo, 3), round(hi, 3)] == [sub["delta_win"], *sub["ci90"]]


def test_constants_are_restored():
    before = wp.FATIGUE_SLOPE, wp.FATIGUE_FLOOR
    with constants(9.0, 0.95):
        assert (wp.FATIGUE_SLOPE, wp.FATIGUE_FLOOR) == (9.0, 0.95)
    assert (wp.FATIGUE_SLOPE, wp.FATIGUE_FLOOR) == before


def test_true_pair_matches_true_gap(scenario):
    s, _ = new_match(scenario, 2)
    step_to(s, 2, 62 * 60_000)
    on = like_for_like_bench(s, "RFC-03")
    assert on == "RFC-15"
    g = true_pair(s, "RFC", "RFC-03", on, 20)
    _, sub = true_gap(s, "RFC", [NO_CHANGE, Option("sub", "sub", subs=(("RFC-03", on),))], 20)
    assert g.gap == pytest.approx(sub.delta_win)
    assert g.dxpts == pytest.approx(sub.delta_xpts)
    assert g.se > 0


def test_like_for_like_keeps_the_role(scenario):
    s, _ = new_match(scenario, 2)
    for pid in ("RFC-04", "RFC-07", "CAS-09"):
        assert s.players[like_for_like_bench(s, pid)].role == s.players[pid].role
