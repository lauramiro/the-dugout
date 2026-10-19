import dataclasses
import json

import numpy as np

from dugout.sim.match import new_match, run_match, run_to_end, step
from dugout.sim.scenario import Levers
from dugout.sim.state import HALF_S, MatchState


def dicts(events):
    return [e.to_dict() for e in events]


def run_until(s, period, clock_s):
    while not s.finished and (s.period, s.clock_s) < (period, clock_s):
        step(s)


def outfield_starters(s):
    return [p for p in s.players.values() if p.role != "GK" and p.on_pitch]


def test_scenario_sets_midweek_lever_on_left_back(scenario):
    assert scenario.levers.start_condition["RFC-03"] < 1.0
    s, _ = new_match(scenario, 1)
    assert s.players["RFC-03"].condition == scenario.levers.start_condition["RFC-03"]
    assert s.players["RFC-02"].condition == 1.0


def test_condition_falls_over_a_match(scenario):
    s, _ = new_match(scenario, 4)
    run_until(s, 2, HALF_S + 20 * 60)
    mid = {p.id: p.condition for p in outfield_starters(s)}
    run_to_end(s)
    for pid, c in mid.items():
        p = s.players[pid]
        if p.on_pitch:
            assert p.condition < c
    end = [p.condition for p in outfield_starters(s)]
    assert 0.5 < np.mean(end) < 0.85


def test_goalkeeper_drains_less_than_outfield(scenario):
    s, _ = run_match(scenario, 4)
    outfield = [p.condition for p in outfield_starters(s)]
    assert s.players["RFC-01"].condition > max(outfield)


def test_half_time_gives_condition_back(scenario):
    s, _ = new_match(scenario, 2)
    while s.period == 1:
        before = {p.id: p.condition for p in outfield_starters(s)}
        step(s)
    for pid, c in before.items():
        assert s.players[pid].condition > c


def test_midweek_lever_leaves_left_back_lower(scenario):
    fresh = dataclasses.replace(scenario, levers=Levers())
    for seed in range(1, 6):
        a, _ = new_match(scenario, seed)
        b, _ = new_match(fresh, seed)
        run_until(a, 2, 60 * 60)
        run_until(b, 2, 60 * 60)
        assert a.players["RFC-03"].condition < b.players["RFC-03"].condition


def test_save_and_resume_mid_minute_keeps_drain_state(scenario):
    s, _ = new_match(scenario, 9)
    for _ in range(3031):
        step(s)
    resumed = MatchState.from_dict(json.loads(json.dumps(s.to_dict())))
    assert dicts(run_to_end(s)) == dicts(run_to_end(resumed))
    assert {p.id: p.condition for p in s.players.values()} == \
        {p.id: p.condition for p in resumed.players.values()}
