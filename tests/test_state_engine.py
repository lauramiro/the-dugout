"""State engine: observable match state and snapshots every 10 s (contract 3)."""
import subprocess
import sys

import numpy as np
import pytest

from dugout.sim.match import new_match, run_match, step
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


# --- item 2: scoring rates ------------------------------------------------------

TWO_GK = [{"id": "A-01", "team": "A", "role": "GK", "side": "centre", "starting": True},
          {"id": "B-01", "team": "B", "role": "GK", "side": "centre", "starting": True}]


def at(snaps, period, t_s):
    return next(x for x in snaps if x["period"] == period and x["t_ms"] == t_s * 1000)


def test_rates_start_at_the_prior_for_both_teams():
    engine = StateEngine(TWO_GK, prior90=1.4)
    (snap, _), = engine.feed(ev(1, 0, "restart", "A", outcome="kickoff"))
    assert snap["rates"] == {"A": {"for90": 1.4, "against90": 1.4}, "B": {"for90": 1.4, "against90": 1.4}}


def test_rates_blend_moves_from_the_prior_towards_the_rolling_rate():
    # A shoots 0.25 xG every 5 minutes (4.5 xG/90); B never shoots
    events = [ev(1, 0, "restart", "A", outcome="kickoff")]
    events += [ev(i + 2, 60 + 300 * i, "shot", "A", channel="centre", outcome="saved", xg=0.25)
               for i in range(9)]
    events.append(ev(20, 2699, "pass", "B"))
    snaps = run_engine(StateEngine(TWO_GK), events)
    gaps = []
    for minute in (10, 20, 30, 40):
        r = at(snaps, 1, minute * 60)["rates"]
        assert r["A"]["for90"] == r["B"]["against90"] and r["A"]["against90"] == r["B"]["for90"]
        assert 1.35 < r["A"]["for90"] < 4.5
        assert 0.0 < r["A"]["against90"] < 1.35
        gaps.append(4.5 - r["A"]["for90"])
    assert gaps == sorted(gaps, reverse=True) and gaps[0] > gaps[-1] + 0.3


def test_rolling_rate_forgets_shots_older_than_20_minutes():
    events = [ev(1, 0, "restart", "A", outcome="kickoff"),
              ev(2, 60, "shot", "A", channel="centre", outcome="saved", xg=0.5),
              ev(3, 2699, "pass", "B")]
    snaps = run_engine(StateEngine(TWO_GK), events)
    assert at(snaps, 1, 20 * 60)["rates"]["A"]["for90"] > 1.35
    late = at(snaps, 1, 22 * 60)["rates"]["A"]
    assert late["for90"] == late["against90"] < 1.35


# --- item 3: condition estimate ---------------------------------------------------

SQUAD = [{"id": "A-01", "team": "A", "role": "GK", "side": "centre", "starting": True},
         {"id": "A-02", "team": "A", "role": "FB", "side": "left", "starting": True},
         {"id": "A-03", "team": "A", "role": "CB", "side": "centre", "starting": True},
         {"id": "A-12", "team": "A", "role": "FB", "side": "left", "starting": False},
         {"id": "B-01", "team": "B", "role": "GK", "side": "centre", "starting": True}]


def running(gaps, until_s=2690):
    """Kick-off, then each of A-02 and A-03 runs every gaps(t) seconds: hsr 20 m, every
    third run a sprint instead."""
    events, seq = [ev(1, 0, "restart", "A", outcome="kickoff")], 1
    for pid in ("A-02", "A-03"):
        t, k = 5, 0
        while t < until_s:
            seq += 1
            kind = "sprint" if k % 3 == 2 else "hsr"
            events.append(ev(seq, t, kind, "A", player_id=pid, dist_m=20.0 if kind == "hsr" else 25.0))
            t, k = t + gaps(t), k + 1
    events.sort(key=lambda e: e["t_ms"])
    for i, e in enumerate(events):
        e["seq"] = i + 1
    return events


def player(snap, pid):
    return next(p for p in snap["players"] if p["id"] == pid)


def test_steady_running_keeps_the_estimate_near_full():
    snaps = run_engine(StateEngine(SQUAD), running(lambda t: 30))
    p = player(at(snaps, 1, 40 * 60), "A-02")
    assert p["condition_est"] > 0.95 and abs(p["trend_per_min"]) < 0.005
    assert p["baseline_hsr_m_10m"] == pytest.approx(p["hsr_m_10m"], rel=0.1)


def test_estimate_falls_when_running_drops_below_his_own_baseline():
    snaps = run_engine(StateEngine(SQUAD), running(lambda t: 30 if t < 25 * 60 else 75))
    early, late = player(at(snaps, 1, 25 * 60), "A-02"), player(at(snaps, 1, 44 * 60), "A-02")
    assert early["condition_est"] > 0.95
    assert late["condition_est"] < 0.85 and late["trend_per_min"] < 0
    assert late["condition_band"][0] < late["condition_est"] < late["condition_band"][1]
    assert late["hsr_m_10m"] < late["baseline_hsr_m_10m"]


def test_estimate_is_clipped_and_band_wider_for_low_sprint_roles():
    snaps = run_engine(StateEngine(SQUAD), running(lambda t: 30 if t < 21 * 60 else 9000)
                       + [ev(10_000, 2695, "pass", "B"),
                          ev(10_001, 2700, "restart", "B", period=2, outcome="kickoff"),
                          ev(10_002, 4500, "pass", "B")])
    last = at(snaps, 2, 4500)
    fb, cb = player(last, "A-02"), player(last, "A-03")
    assert fb["condition_est"] == cb["condition_est"] == 0.3
    width = lambda p: p["condition_band"][1] - p["condition_band"][0]  # noqa: E731
    mid = at(snaps, 1, 10 * 60)
    assert width(player(mid, "A-03")) > width(player(mid, "A-02"))
    assert player(last, "A-01")["condition_est"] is None


def test_substitute_sets_his_baseline_from_when_he_comes_on():
    events = [ev(1, 0, "restart", "A", outcome="kickoff"), ev(2, 2690, "pass", "A", period=1),
              ev(3, 2700, "sub", "A", period=2, player_id="A-02", player_in_id="A-12"),
              ev(4, 2700, "restart", "B", period=2, outcome="kickoff")]
    seq = 4
    for t in range(2705, 2700 + 30 * 60, 30):
        seq += 1
        events.append(ev(seq, t, "hsr", "A", player_id="A-12", dist_m=20.0))
    snaps = run_engine(StateEngine(SQUAD), events)
    at_10 = player(at(snaps, 2, 2700 + 10 * 60), "A-12")
    assert at_10["condition_est"] == 1.0 and at_10["baseline_hsr_m_10m"] is None
    at_25 = player(at(snaps, 2, 2700 + 25 * 60), "A-12")
    assert at_25["baseline_hsr_m_10m"] is not None and at_25["condition_est"] > 0.95


def test_midweek_left_back_reads_lowest_at_62_and_estimate_tracks_hidden_condition(scenario):
    """Seeds 1-20 with the played-midweek lever on RFC-03. Hidden condition is read here only."""
    lineup, t62 = lineup_of(scenario), 62 * 60
    below = valid = 0
    at62, pooled = [], []
    for seed in range(1, 21):
        s, events = new_match(scenario, seed)
        hidden = {}
        while not s.finished and (s.period, s.clock_s) <= (2, t62 + 120):
            events += step(s)
            if s.clock_s % 60 == 0:
                hidden[(s.period, s.clock_s * 1000)] = {p.id: p.condition for p in s.players.values()}
        snaps = run_engine(StateEngine(lineup), [e.to_dict() for e in events])
        for snap in snaps:
            h = hidden.get((snap["period"], snap["t_ms"]))
            ests = {p["id"]: p["condition_est"] for p in snap["players"]
                    if p["condition_est"] is not None and p["baseline_hsr_m_10m"] is not None}
            if h is None:
                continue
            pooled += [(v, h[pid]) for pid, v in ests.items()]
            if (snap["period"], snap["t_ms"]) != (2, t62 * 1000):
                continue
            at62 += [(v, h[pid]) for pid, v in ests.items()]
            starters = {p.id for p in scenario.home.starters}
            others = [v for pid, v in ests.items() if pid in starters and pid != "RFC-03"]
            if "RFC-03" in ests:
                valid += 1
                below += ests["RFC-03"] < np.median(others)
    r62, r_all = (float(np.corrcoef(np.array(x).T)[0, 1]) for x in (at62, pooled))
    print(f"\nRFC-03 below the median of the other Riverside starters at 62' in {below}/{valid} seeds; "
          f"correlation with hidden condition: {r62:.2f} at 62' (n={len(at62)}), "
          f"{r_all:.2f} over every minute after the baselines (n={len(pooled)})")
    assert valid >= 15 and below > valid / 2
    assert r_all > 0


# --- item 4: threat by channel ----------------------------------------------------

def shots(team, channel, times_s, seq0, period=None):
    return [ev(seq0 + i, t, "shot", team, period=period, channel=channel, outcome="blocked", xg=0.1)
            for i, t in enumerate(times_s)]


def test_no_shots_means_an_even_split_for_both_teams():
    (snap, _), = StateEngine(TWO_GK).feed(ev(1, 0, "restart", "A", outcome="kickoff"))
    assert snap["threat_by_channel"] == {f"{t}_{c}": pytest.approx(1 / 3, abs=0.001)
                                         for t in ("A", "B") for c in ("left", "centre", "right")}


def test_shots_down_one_flank_give_that_key_the_largest_share():
    # B attacks down its own left, which is A's right
    events = [ev(1, 0, "restart", "A", outcome="kickoff")] + shots("B", "left", [300, 400, 500], 2)
    events.append(ev(10, 600, "pass", "A"))
    threat = at(run_engine(StateEngine(TWO_GK), events), 1, 600)["threat_by_channel"]
    a = {c: threat[f"A_{c}"] for c in ("left", "centre", "right")}
    assert max(a, key=a.get) == "right" and a["right"] > 0.5
    assert threat["B_left"] == threat["B_centre"] == threat["B_right"]  # A has not shot


def test_threat_is_the_last_15_minutes_against_the_first_half():
    events = [ev(1, 0, "restart", "A", outcome="kickoff")]
    events += shots("B", "right", [600, 900, 1200], 2)  # first half: A's left
    events += [ev(10, 2690, "pass", "A", period=1), ev(11, 2700, "restart", "B", period=2, outcome="kickoff")]
    events += shots("B", "left", [4000, 4100], 20)  # after 66': A's right
    events.append(ev(30, 4200, "pass", "A"))
    snap = at(run_engine(StateEngine(TWO_GK), events), 2, 4200)
    now, first = snap["threat_by_channel"], snap["threat_by_channel_first_half"]
    assert max(("A_left", "A_centre", "A_right"), key=now.get) == "A_right"
    assert max(("A_left", "A_centre", "A_right"), key=first.get) == "A_left"
    early = at(run_engine(StateEngine(TWO_GK), events), 2, 3600)["threat_by_channel"]
    # nothing in the last 15 minutes: the split falls back to the first half
    assert max(("A_left", "A_centre", "A_right"), key=early.get) == "A_left"
