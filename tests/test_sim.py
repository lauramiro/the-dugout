import json

import pytest

from dugout.contracts import EVENT_TYPES, PITCH_LENGTH, PITCH_WIDTH, Event
from dugout.sim.match import new_match, run_match, run_to_end, step
from dugout.sim.realism import realism
from dugout.sim.state import HALF_S, MatchState


def dicts(events):
    return [e.to_dict() for e in events]


def advance(s, seconds):
    events = []
    for _ in range(seconds):
        events += step(s)
    return events


def test_same_seed_same_stream(scenario):
    _, a = run_match(scenario, 7)
    _, b = run_match(scenario, 7)
    assert dicts(a) == dicts(b)


def test_different_seeds_differ(scenario):
    _, a = run_match(scenario, 7)
    _, b = run_match(scenario, 8)
    assert dicts(a) != dicts(b)


def test_save_and_resume_mid_match_is_identical(scenario):
    s, _ = new_match(scenario, 3)
    advance(s, 3000)
    saved = json.loads(json.dumps(s.to_dict()))
    resumed = MatchState.from_dict(saved)
    assert dicts(run_to_end(s)) == dicts(run_to_end(resumed))
    assert resumed.score == s.score


def test_fork_same_branch_same_draws_and_parent_untouched(scenario):
    s, _ = new_match(scenario, 11)
    advance(s, 3700)
    before = s.to_dict()
    a, b, c = s.fork(1), s.fork(1), s.fork(2)
    ea, eb, ec = run_to_end(a), run_to_end(b), run_to_end(c)
    assert dicts(ea) == dicts(eb)
    assert dicts(ea) != dicts(ec)
    assert s.to_dict() == before


def test_fork_sees_changed_condition(scenario):
    """A fork is a real counterfactual: changing hidden state in one branch changes its future."""
    s, _ = new_match(scenario, 11)
    advance(s, 3700)
    before = s.players["RFC-03"].condition
    a, b = s.fork(1), s.fork(1)
    b.players["RFC-03"].condition = 0.4
    assert dicts(run_to_end(a)) != dicts(run_to_end(b))
    assert s.players["RFC-03"].condition == before


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_match_invariants(scenario, seed):
    s, events = run_match(scenario, seed)
    assert s.finished
    assert [e.seq for e in events] == list(range(1, len(events) + 1))
    assert all(e.type in EVENT_TYPES for e in events)
    goals = [e for e in events if e.type == "goal"]
    assert len(goals) == sum(s.score.values())
    for team in (s.home, s.away):
        assert sum(e.team == team for e in goals) == s.score[team]
    for e in events:
        assert e.period in (1, 2)
        assert e.t_ms >= (0 if e.period == 1 else HALF_S * 1000)
        if e.x is not None:
            assert 0 <= e.x <= PITCH_LENGTH and 0 <= e.y <= PITCH_WIDTH
    kickoffs = [e for e in events if e.type == "restart" and e.outcome == "kickoff"]
    assert len(kickoffs) == 2 + len(goals)
    second_half = [e for e in events if e.period == 2]
    assert second_half[0].type == "restart" and second_half[0].team == s.away


def test_attacking_direction_flips_at_half_time(scenario):
    """Home attacks towards x = 105 in the first half and towards x = 0 in the second."""
    _, events = run_match(scenario, 5)
    home_shots = [e for e in events if e.type == "shot" and e.team == "RFC"]
    assert all(e.x > 52.5 for e in home_shots if e.period == 1)
    assert all(e.x < 52.5 for e in home_shots if e.period == 2)


def test_event_rejects_unknown_type():
    with pytest.raises(ValueError):
        Event(match_id="m", seq=1, t_ms=0, period=1, type="dribble", team="RFC")


def test_realism_smoke(scenario):
    stats = realism(scenario, range(1, 31))
    assert 1.5 <= stats["goals"]["mean"] <= 4.0
    assert 15 <= stats["shots"]["mean"] <= 35
    assert 50 <= stats["in_play_min"]["mean"] <= 65
