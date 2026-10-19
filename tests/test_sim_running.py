import dataclasses

import pytest

from dugout.contracts import Event
from dugout.sim import fatigue
from dugout.sim.match import run_match

OLD_KEYS = ["match_id", "seq", "t_ms", "period", "type", "team", "player_id", "channel",
            "x", "y", "end_x", "end_y", "outcome", "xg"]


def test_event_json_shape_unchanged_without_distance():
    e = Event(match_id="m", seq=1, t_ms=0, period=1, type="pass", team="RFC")
    assert list(e.to_dict()) == OLD_KEYS
    assert Event(**e.to_dict()) == e


def test_event_carries_distance_for_running():
    e = Event(match_id="m", seq=1, t_ms=0, period=1, type="hsr", team="RFC", player_id="RFC-03", dist_m=21.4)
    d = e.to_dict()
    assert d["dist_m"] == 21.4
    assert Event(**d) == e


def test_distance_only_on_running_events():
    with pytest.raises(ValueError):
        Event(match_id="m", seq=1, t_ms=0, period=1, type="pass", team="RFC", dist_m=5.0)


def test_running_rate_scales_with_condition_to_the_power_1_5(scenario):
    s, _ = run_match(scenario, 1)
    p = dataclasses.replace(s.players["RFC-02"], condition=1.0)
    tired = dataclasses.replace(p, condition=0.64)
    for fresh_rate, tired_rate in zip(fatigue.run_rates(p), fatigue.run_rates(tired)):
        assert tired_rate == pytest.approx(fresh_rate * 0.64 ** 1.5)


def test_match_emits_sprints_and_hsr_with_distance(scenario):
    s, events = run_match(scenario, 3)
    running = [e for e in events if e.type in ("sprint", "hsr")]
    assert sum(e.type == "sprint" for e in running) > 200
    assert sum(e.type == "hsr" for e in running) > 400
    for e in running:
        assert e.player_id in s.players and e.team == s.players[e.player_id].team
        assert e.dist_m and e.dist_m > 0
    assert not any(e.type == "sprint" and s.players[e.player_id].role == "GK" for e in running)


def test_running_falls_in_the_second_half(realism_100):
    assert realism_100["sprints_h2"]["mean"] < realism_100["sprints_h1"]["mean"]
    assert realism_100["hsr_m_h2"]["mean"] < realism_100["hsr_m_h1"]["mean"]
