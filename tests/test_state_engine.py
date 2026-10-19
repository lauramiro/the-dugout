"""State engine: observable match state and snapshots every 10 s (contract 3)."""
import subprocess
import sys

import pytest

from dugout.sim.match import run_match
from dugout.sim.state import HALF_S
from dugout.stream.state_engine import MAX_SUBS, MAX_WINDOWS, StateEngine

H2 = HALF_S * 1000  # second-half kick-off, t_ms


def lineup_of(scenario):
    return [{"id": p.id, "team": t.code, "role": p.role, "side": p.side, "starting": i < 11}
            for t in (scenario.home, scenario.away) for i, p in enumerate(t.players)]


def run_engine(engine, events):
    snaps = []
    for e in events:
        snaps += [snap for snap, _ in engine.feed(e)]
    snaps += [snap for snap, _ in engine.finish()]
    return snaps


def ev(seq, t_s, type_, team, period=None, **kw):
    t_ms = int(t_s * 1000)
    if period is None:
        period = 1 if t_ms < H2 else 2
    return {"match_id": "m", "seq": seq, "t_ms": t_ms, "period": period, "type": type_, "team": team,
            "player_id": None, "channel": None, "x": None, "y": None, "end_x": None, "end_y": None,
            "outcome": None, "xg": None, **kw}


@pytest.fixture(scope="module")
def simulated(scenario):
    s, events = run_match(scenario, 2)
    engine = StateEngine(lineup_of(scenario))
    return s, events, run_engine(engine, [e.to_dict() for e in events])


def test_state_engine_never_imports_the_simulator():
    code = ("import sys, dugout.stream.state_engine; "
            "assert not [m for m in sys.modules if m.startswith('dugout.sim')], 'dugout.sim imported'")
    subprocess.run([sys.executable, "-c", code], check=True)


def test_final_snapshot_matches_the_event_stream(simulated):
    s, events, snaps = simulated
    last = snaps[-1]
    assert last["score"] == s.score
    assert last["subs_left"] == {t: MAX_SUBS - s.subs_used[t] for t in (s.home, s.away)}
    assert last["windows_left"] == {t: MAX_WINDOWS - s.windows_used[t] for t in (s.home, s.away)}
    on = {p.id for p in s.players.values() if p.on_pitch}
    assert {p["id"] for p in last["players"]} == on
    assert last["period"] == 2 and last["t_ms"] > events[-1].t_ms


def test_snapshots_every_10_s_in_each_period(simulated):
    s, events, snaps = simulated
    for period, start in ((1, 0), (2, H2)):
        ts = [x["t_ms"] for x in snaps if x["period"] == period]
        assert ts[0] == start
        assert all(b - a == 10_000 for a, b in zip(ts, ts[1:]))
        last_event = max(e.t_ms for e in events if e.period == period)
        assert last_event < ts[-1] <= last_event + 10_000
    assert [x["period"] for x in snaps] == sorted(x["period"] for x in snaps)


def test_snapshot_shape(simulated):
    _, _, snaps = simulated
    snap = snaps[len(snaps) // 2]
    assert set(snap) >= {"match_id", "t_ms", "period", "score", "subs_left", "windows_left",
                         "rates", "players", "threat_by_channel"}
    assert len(snap["players"]) == 22
    gk = next(p for p in snap["players"] if p["id"] == "RFC-01")
    assert gk["role"] == "GK" and gk["condition_est"] is None and gk["condition_band"] is None


def test_score_counts_goals_and_snapshot_covers_events_before_its_time():
    lineup = [{"id": "A-01", "team": "A", "role": "GK", "side": "centre", "starting": True},
              {"id": "B-01", "team": "B", "role": "GK", "side": "centre", "starting": True}]
    engine = StateEngine(lineup)
    out = []
    for e in [ev(1, 0, "restart", "A", outcome="kickoff"), ev(2, 15, "goal", "A", player_id="A-01"),
              ev(3, 20, "pass", "B"), ev(4, 31, "goal", "B")]:
        out += [snap for snap, _ in engine.feed(e)]
    out += [snap for snap, _ in engine.finish()]
    assert [(x["t_ms"], x["score"]["A"], x["score"]["B"]) for x in out] == \
        [(0, 0, 0), (10_000, 0, 0), (20_000, 1, 0), (30_000, 1, 0), (40_000, 1, 1)]


def test_events_are_ordered_by_seq_not_t_ms():
    lineup = [{"id": "A-01", "team": "A", "role": "GK", "side": "centre", "starting": True}]
    engine = StateEngine(lineup)
    engine.feed(ev(1, 2830, "pass", "A", period=1))  # first-half added time
    engine.feed(ev(2, 2700, "restart", "A", period=2, outcome="kickoff"))
    with pytest.raises(ValueError):
        engine.feed(ev(2, 2701, "pass", "A", period=2))


def test_subs_and_windows():
    lineup = ([{"id": f"A-{i:02d}", "team": "A", "role": "CM", "side": "centre", "starting": i <= 11}
               for i in range(1, 19)] +
              [{"id": "B-01", "team": "B", "role": "GK", "side": "centre", "starting": True}])
    engine = StateEngine(lineup)
    events = [ev(1, 0, "restart", "A", outcome="kickoff"),
              ev(2, 2750, "pass", "A", period=1),
              # half-time: free window
              ev(3, 2700, "sub", "A", period=2, player_id="A-02", player_in_id="A-12"),
              ev(4, 2700, "restart", "B", period=2, outcome="kickoff"),
              # one in-play window with two changes
              ev(5, 3600, "sub", "A", player_id="A-03", player_in_id="A-13"),
              ev(6, 3600, "sub", "A", player_id="A-04", player_in_id="A-14"),
              ev(7, 3700, "sub", "A", player_id="A-05", player_in_id="A-15"),
              ev(8, 3710, "pass", "A")]
    snaps = run_engine(engine, events)
    last = snaps[-1]
    assert last["subs_left"] == {"A": 1, "B": 5}
    assert last["windows_left"] == {"A": 1, "B": 3}
    on = {p["id"] for p in last["players"]}
    assert {"A-12", "A-13", "A-14", "A-15"} <= on and not {"A-02", "A-03", "A-04", "A-05"} & on
