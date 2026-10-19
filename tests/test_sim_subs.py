import dataclasses
import json

import pytest

from dugout.contracts import Event
from dugout.sim import managers
from dugout.sim.match import make_subs, new_match, run_match, run_to_end, step
from dugout.sim.scenario import Levers
from dugout.sim.state import HALF_S, MatchState

SEEDS = range(1, 61)


@pytest.fixture(scope="module")
def matches(scenario):
    return [run_match(scenario, seed) for seed in SEEDS]


def replay(scenario, s, events):
    """Walk the stream, checking every sub against who is on the pitch; return per-team sub windows."""
    on = {p.id for team in (scenario.home, scenario.away) for p in team.starters}
    gone, windows = set(), {s.home: set(), s.away: set()}
    for e in events:
        if e.player_id and e.type != "sub":
            assert e.player_id in on, e
        if e.type != "sub":
            continue
        assert e.player_id in on and e.player_in_id not in on and e.player_in_id not in gone
        assert e.player_id.startswith(e.team) and e.player_in_id.startswith(e.team)
        on.remove(e.player_id)
        on.add(e.player_in_id)
        gone.add(e.player_id)
        assert sum(pid.startswith(e.team) for pid in on) == 11
        windows[e.team].add((e.period, e.t_ms))
    assert on == {p.id for p in s.players.values() if p.on_pitch}
    return windows


def test_sub_event_shape():
    e = Event(match_id="m", seq=1, t_ms=0, period=2, type="sub", team="RFC",
              player_id="RFC-03", player_in_id="RFC-15", outcome="like_for_like")
    assert Event(**e.to_dict()) == e
    assert "player_in_id" not in Event(match_id="m", seq=1, t_ms=0, period=1, type="pass", team="RFC").to_dict()
    with pytest.raises(ValueError):
        Event(match_id="m", seq=1, t_ms=0, period=1, type="pass", team="RFC", player_in_id="RFC-15")


def test_sub_invariants_over_many_seeds(scenario, matches):
    total = 0
    for s, events in matches:
        windows = replay(scenario, s, events)
        for team in (s.home, s.away):
            subs = [e for e in events if e.type == "sub" and e.team == team]
            total += len(subs)
            assert len(subs) <= 5 and s.subs_used[team] == len(subs)
            in_play = {w for w in windows[team] if w != (2, HALF_S * 1000)}
            assert len(in_play) <= 3 and s.windows_used[team] == len(in_play)
    assert total / len(matches) > 1.0


def test_subs_only_at_a_dead_ball_or_half_time(scenario):
    seen = 0
    for seed in range(1, 21):
        s, _ = new_match(scenario, seed)
        while not s.finished:
            period, dead = s.period, s.dead_s
            subs = [e for e in step(s) if e.type == "sub"]
            seen += len(subs)
            for e in subs:
                assert dead > 0 or (period == 1 and (e.period, e.t_ms) == (2, HALF_S * 1000))
    assert seen > 0


def test_attacking_changes_only_when_trailing_after_65(matches):
    seen = 0
    for s, events in matches:
        score = {s.home: 0, s.away: 0}
        for e in events:
            if e.type == "goal":
                score[e.team] += 1
            if e.type == "sub" and e.outcome == "attacking":
                seen += 1
                assert e.period == 2 and e.t_ms >= 65 * 60 * 1000
                assert score[e.team] < score[s.opponent(e.team)]
            elif e.type == "sub":
                assert e.outcome == "like_for_like"
    assert seen > 0


def test_fading_player_is_scheduled_after_a_reaction_delay(scenario):
    s, _ = new_match(dataclasses.replace(scenario, levers=Levers()), 5)
    while (s.period, s.clock_s) < (2, 60 * 60 - 1):
        step(s)
    s.pending = []
    s.players["CAS-07"].condition = 0.5
    step(s)
    (entry,) = [p for p in s.pending if p["off"] == "CAS-07"]
    lo, hi = managers.REACTION_MIN
    assert entry["kind"] == "like_for_like"
    assert entry["due"][0] == 2 and lo * 60 <= entry["due"][1] - 60 * 60 <= hi * 60


def test_slow_manager_lever_reacts_later(scenario):
    assert "RFC" in scenario.levers.slow_manager
    s, _ = new_match(scenario, 5)
    while (s.period, s.clock_s) < (2, 60 * 60 - 1):
        step(s)
    s.pending = []
    s.players["RFC-07"].condition = 0.5
    step(s)
    (entry,) = [p for p in s.pending if p["off"] == "RFC-07"]
    lo, hi = managers.SLOW_REACTION_MIN
    assert lo * 60 <= entry["due"][1] - 60 * 60 <= hi * 60
    assert managers.SLOW_REACTION_MIN[0] > managers.REACTION_MIN[0]


def test_make_subs_rejects_illegal_changes(scenario):
    s, _ = new_match(scenario, 1)
    with pytest.raises(ValueError):
        make_subs(s, "RFC", [("RFC-03", "RFC-02")])  # RFC-02 is already on
    with pytest.raises(ValueError):
        make_subs(s, "RFC", [("RFC-03", "CAS-15")])
    make_subs(s, "RFC", [("RFC-03", "RFC-15")])
    with pytest.raises(ValueError):
        make_subs(s, "RFC", [("RFC-15", "RFC-03")])  # subbed-off players never return
    assert s.windows_used["RFC"] == 1


def test_frozen_manager_makes_no_subs(scenario):
    s, _ = new_match(scenario, 3)
    s.managers = [s.away]
    events = run_to_end(s)
    assert not any(e.type == "sub" and e.team == s.home for e in events)


def test_save_and_resume_with_pending_subs(scenario):
    for seed in SEEDS:
        s, _ = new_match(scenario, seed)
        while not s.finished and not s.pending:
            step(s)
        if s.pending:
            break
    resumed = MatchState.from_dict(json.loads(json.dumps(s.to_dict())))
    assert [e.to_dict() for e in run_to_end(s)] == [e.to_dict() for e in run_to_end(resumed)]
