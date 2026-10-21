"""Decision points: triggers, the one-open-card rule, both teams."""
import subprocess
import sys

import pytest

from pathlib import Path

from dugout.sim.match import run_match
from dugout.stream.replay import read_events
from dugout.stream.snapshots import lineup_from_scenario, process
from dugout.stream.state_engine import StateEngine
from dugout.stream.triggers import CARD_TIMEOUT_SNAPSHOTS, CONDITION_LINE, CONDITION_MARGIN, DecisionPoints

H2 = 45 * 60 * 1000
ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / "scenarios" / "riverside-castleton.yaml"


TEAM = {f"{t}-{i:02d}": 0.8 for t in "AB" for i in range(2, 6)}


def snap(t_s, est=None, period=None, no_band=()):
    """A minimal snapshot: outfield players A-02..A-05 and B-02..B-05, at 0.8 unless given."""
    est = {**TEAM, **(est or {})}
    t_ms = int(t_s * 1000)
    return {"match_id": "m", "t_ms": t_ms, "period": period or (1 if t_ms < H2 else 2),
            "score": {"A": 0, "B": 0}, "subs_left": {"A": 5, "B": 5}, "windows_left": {"A": 3, "B": 3},
            "rates": {"A": {"for90": 1.35, "against90": 1.35}, "B": {"for90": 1.35, "against90": 1.35}},
            "players": [{"id": pid, "team": pid[0], "role": "FB", "condition_est": v,
                         "condition_band": None if pid in no_band else [round(v - 0.07, 2), round(v + 0.07, 2)]}
                        for pid, v in est.items()],
            "threat_by_channel": {}}


def ev(t_s, type_, team, **kw):
    t_ms = int(t_s * 1000)
    return {"match_id": "m", "seq": 0, "t_ms": t_ms, "period": 1 if t_ms < H2 else 2,
            "type": type_, "team": team, **kw}


def sub(t_s, team, off, on):
    return ev(t_s, "sub", team, player_id=off, player_in_id=on, outcome="like_for_like")


def opened(records):
    return [r for r in records if r["kind"] == "decision_point"]


def run(points, ticks):
    """ticks: list of (snapshot, events); returns every record."""
    out = []
    for s, events in ticks:
        out += points.on_snapshot(s, events)
    return out + points.finish()


def test_triggers_never_import_the_simulator():
    code = ("import sys, dugout.stream.triggers; "
            "assert not [m for m in sys.modules if m.startswith('dugout.sim')], 'dugout.sim imported'")
    subprocess.run([sys.executable, "-c", code], check=True)


def test_condition_drop_fires_once_per_player_for_his_team():
    ticks = [(snap(3600, {"B-02": 0.70}), []), (snap(3610, {"B-02": 0.66}), []),
             (snap(3620, {"B-02": 0.70}), []), (snap(3630, {"B-02": 0.60}), [])]
    (point,) = opened(run(DecisionPoints(), ticks))
    assert point["trigger"] == "condition_drop" and point["team"] == "B"
    assert point["detail"] == {"player_id": "B-02", "condition_est": 0.66, "condition_band": [0.59, 0.73],
                               "team_median": 0.8}
    assert point["t_ms"] == 3_610_000 and point["snapshot"]["t_ms"] == 3_610_000


def test_condition_drop_needs_both_the_margin_and_the_line():
    assert (CONDITION_MARGIN, CONDITION_LINE) == (0.10, 0.69)
    # far below his team but still fresh: no card (a player who started less fresh)
    fresh = {"A-02": 0.75, **{f"A-{i:02d}": 0.95 for i in range(3, 6)}}
    # under the line, but so is his team: no card
    tired = {"A-02": 0.62, **{f"A-{i:02d}": 0.66 for i in range(3, 6)}}
    assert opened(run(DecisionPoints(), [(snap(3600, fresh), []), (snap(3610, tired), [])])) == []


def test_condition_drop_waits_for_the_band():
    ticks = [(snap(1000, {"A-02": 0.6}, no_band={"A-02"}), []), (snap(1010, {"A-02": 0.6}), [])]
    (point,) = opened(run(DecisionPoints(), ticks))
    assert point["t_ms"] == 1_010_000


def test_goal_after_55_opens_for_both_teams_conceding_side_first():
    early = run(DecisionPoints(), [(snap(54 * 60 + 50), [ev(54 * 60 + 45, "goal", "A")])])
    assert opened(early) == []
    points = DecisionPoints()
    ticks = [(snap(56 * 60), [ev(55 * 60 + 55, "goal", "A")])]
    ticks += [(snap(56 * 60 + 10 * (i + 1)), []) for i in range(CARD_TIMEOUT_SNAPSHOTS)]
    first, second = opened(run(points, ticks))
    assert (first["team"], first["trigger"]) == ("B", "goal_after_55")
    assert (second["team"], second["trigger"]) == ("A", "goal_after_55")
    assert second["t_ms"] == first["t_ms"] + CARD_TIMEOUT_SNAPSHOTS * 10_000


def test_manager_sub_opens_one_point_per_window():
    ticks = [(snap(3600), [sub(3595, "A", "A-02", "A-12"), sub(3595, "A", "A-03", "A-13")])]
    (point,) = opened(run(DecisionPoints(), ticks))
    assert (point["team"], point["trigger"]) == ("A", "manager_sub")
    assert point["detail"] == {"subs": [{"off": "A-02", "on": "A-12"}, {"off": "A-03", "on": "A-13"}]}


def test_one_open_card_at_a_time_and_the_queue_waits():
    ticks = [(snap(3600, {"A-02": 0.55, "B-02": 0.5}), [])]
    ticks += [(snap(3600 + 10 * (i + 1), {"A-02": 0.55, "B-02": 0.5}), [])
              for i in range(CARD_TIMEOUT_SNAPSHOTS + 1)]
    records = run(DecisionPoints(), ticks)
    kinds = [(r["kind"], r["team"]) for r in records]
    assert kinds == [("decision_point", "A"), ("card_closed", "A"), ("decision_point", "B"),
                     ("card_closed", "B")]
    assert records[1]["reason"] == "timeout" and records[3]["reason"] == "full_time"
    assert records[2]["raised_t_ms"] == 3_600_000 < records[2]["t_ms"]


def test_a_change_by_the_deciding_team_closes_the_card_and_answers_its_queue():
    # B scores: A's goal card opens, B's waits. B then makes a change while A's card is
    # open; that answers B's waiting card and raises a manager_sub card for B instead.
    ticks = [(snap(3600), [ev(3595, "goal", "B")]),
             (snap(3610), [sub(3605, "B", "B-02", "B-12")])]
    ticks += [(snap(3620 + 10 * i), []) for i in range(CARD_TIMEOUT_SNAPSHOTS)]
    seen = [(r["team"], r["trigger"]) for r in opened(run(DecisionPoints(), ticks))]
    assert seen == [("A", "goal_after_55"), ("B", "manager_sub")]


def test_change_closes_the_open_card_for_that_team():
    ticks = [(snap(3600, {"A-02": 0.55}), []),
             (snap(3610), [sub(3605, "A", "A-02", "A-12")])]
    records = run(DecisionPoints(), ticks)
    assert [(r["kind"], r.get("trigger") or r.get("reason")) for r in records] == [
        ("decision_point", "condition_drop"), ("card_closed", "change"),
        ("decision_point", "manager_sub"), ("card_closed", "full_time")]


def test_queued_condition_card_is_dropped_once_the_player_is_off():
    later = snap(3610, {"A-02": 0.55})
    later["players"] = [p for p in later["players"] if p["id"] != "B-02"]  # off in a window not shown
    ticks = [(snap(3600, {"A-02": 0.55, "B-02": 0.5}), []),
             (later, [sub(3605, "A", "A-03", "A-13")])]
    records = run(DecisionPoints(), ticks)
    assert ("B", "condition_drop") not in [(r["team"], r.get("trigger")) for r in opened(records)]


def test_decision_point_snapshot_lists_the_deciding_team_first_in_rates():
    (point,) = opened(run(DecisionPoints(), [(snap(3600, {"B-02": 0.5}), [])]))
    assert next(iter(point["snapshot"]["rates"])) == "B"


@pytest.mark.parametrize("seed", [2, 7])
def test_simulated_match_opens_cards_one_at_a_time(scenario, seed):
    lineup = lineup_from_scenario(SCENARIO)
    _, events = run_match(scenario, seed)
    engine, points, records = StateEngine(lineup), DecisionPoints(), []
    for e in events:
        for s, new in engine.feed(e.to_dict()):
            records += points.on_snapshot(s, new)
    for s, new in engine.finish():
        records += points.on_snapshot(s, new)
    records += points.finish()
    open_now = None
    for r in records:
        if r["kind"] == "decision_point":
            assert open_now is None
            open_now = r["id"]
        else:
            assert r["id"] == open_now
            open_now = None
    assert open_now is None
    subs = {(e.team, e.period, e.t_ms) for e in events if e.type == "sub"}
    raised = [r for r in opened(records) if r["trigger"] == "manager_sub"]
    assert raised and len(raised) <= len(subs)


def test_cli_writes_snapshots_and_decision_points(scenario, tmp_path):
    import json
    from pathlib import Path

    s, events = run_match(scenario, 2)
    src, out = tmp_path / "events.jsonl", tmp_path / "snapshots.jsonl"
    src.write_text("".join(json.dumps(e.to_dict()) + "\n" for e in reversed(events)), encoding="utf-8")
    path = Path(__file__).resolve().parents[1] / "scenarios" / "riverside-castleton.yaml"
    subprocess.run([sys.executable, "-m", "dugout.stream.snapshots", "--events", str(src),
                    "--scenario", str(path), "--out", str(out)], check=True)
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    snaps = [r["snapshot"] for r in rows if r["kind"] == "snapshot"]
    assert snaps[-1]["score"] == s.score
    assert {r["kind"] for r in rows} == {"snapshot", "decision_point", "card_closed"}
    assert {r["team"] for r in rows if r["kind"] == "decision_point"} == {"RFC", "CAS"}


def test_demo_seed_73_opens_a_condition_drop_card_for_rfc_03_between_60_and_70():
    """A check, not a fit: the margin and the line were chosen on seeds 1-20."""
    records = list(process(read_events(ROOT / "data" / "demo-rfc-cas-0073.jsonl"), lineup_from_scenario(SCENARIO)))
    cards = [r for r in opened(records) if r["trigger"] == "condition_drop"]
    rfc = [r for r in cards if r["team"] == "RFC"]
    assert rfc and rfc[0]["detail"]["player_id"] == "RFC-03"
    assert rfc[0]["period"] == 2 and 60 <= rfc[0]["t_ms"] // 60_000 < 70
