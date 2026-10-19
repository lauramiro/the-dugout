"""Items 4 and 5: snapshot in, decision payload out; engine isolation; speed."""
import subprocess
import sys
import time
from pathlib import Path

from numpy.random import SeedSequence

from dugout.engine.payload import decide

# sample snapshot from docs/data-contracts.md contract 3
SNAPSHOT = {
    "t_ms": 3720000, "score": {"RFC": 1, "CAS": 0},
    "subs_left": {"RFC": 5, "CAS": 4}, "windows_left": {"RFC": 3, "CAS": 2},
    "rates": {"RFC": {"for90": 1.5, "against90": 1.2}, "CAS": {"for90": 1.2, "against90": 1.5}},
    "players": [{"id": "RFC-03", "condition_est": 0.60, "condition_band": [0.52, 0.68],
                 "trend_per_min": -0.008, "hsr_m_10m": 210, "baseline_hsr_m_10m": 380,
                 "sprints_10m": 3, "baseline_sprints_10m": 7},
                {"id": "RFC-01", "condition_est": None, "condition_band": None,
                 "trend_per_min": 0.0, "hsr_m_10m": 0, "baseline_hsr_m_10m": 0,
                 "sprints_10m": 0, "baseline_sprints_10m": 0}],
    "threat_by_channel": {"RFC_left": 0.41, "RFC_centre": 0.33, "RFC_right": 0.26},
}
N = 20_000


def payload(**kw):
    return decide(SNAPSHOT, "RFC", "condition_below_60", SeedSequence(5), n=N, **kw)


def test_contract_4_keys_and_types():
    p = payload()
    assert set(p) == {"decision_id", "t_ms", "team", "trigger", "options", "recommendation",
                      "evidence", "manager_action"}
    assert p["decision_id"] == "rfc-62-00"
    assert p["t_ms"] == 3720000 and p["team"] == "RFC" and p["trigger"] == "condition_below_60"
    assert p["manager_action"] is None
    assert len(p["options"]) == 4
    for o in p["options"]:
        assert isinstance(o["id"], str) and isinstance(o["label"], str)
        for k in ("win", "draw", "loss", "xpts", "delta_win"):
            assert isinstance(o[k], float)
    ref, *rest = p["options"]
    assert ref["id"] == "no_change" and ref["delta_win"] == 0.0 and "ci90" not in ref
    for o in rest:
        lo, hi = o["ci90"]
        assert lo <= o["delta_win"] <= hi
    rec = p["recommendation"]
    assert rec["option_id"] in {o["id"] for o in p["options"]}
    assert rec["strength"] in {"strong", "lean", "toss_up"}


def test_evidence_names_the_tired_player_and_the_flank():
    ev = {e["type"]: e for e in payload()["evidence"]}
    assert ev["condition"] == {"type": "condition", "player_id": "RFC-03", "value": 0.60,
                               "trend_per_min": -0.008}
    assert ev["flank_threat"] == {"type": "flank_threat", "channel": "RFC_left", "share": 0.41}


def test_tired_flank_makes_the_sub_the_recommendation():
    rec = payload()["recommendation"]
    assert rec["option_id"] == "sub_like_for_like"


def test_no_subs_left_drops_the_sub_option():
    snap = {**SNAPSHOT, "subs_left": {"RFC": 0, "CAS": 4}}
    ids = [o["id"] for o in decide(snap, "RFC", "manager_sub", SeedSequence(5), n=2_000)["options"]]
    assert "sub_like_for_like" not in ids


def test_same_seed_same_payload():
    assert payload() == payload()


def test_engine_never_imports_sim():
    code = "import sys, dugout.engine.payload; print(any(m.startswith('dugout.sim') for m in sys.modules))"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"
    for f in (Path(__file__).resolve().parents[1] / "dugout" / "engine").glob("*.py"):
        assert "dugout.sim" not in f.read_text(encoding="utf-8")


def test_twenty_thousand_runs_four_options_under_two_seconds():
    start = time.perf_counter()
    payload()
    elapsed = time.perf_counter() - start
    print(f"decide: {elapsed:.3f}s")
    assert elapsed < 2.0


AWAY = {
    **SNAPSHOT,
    "players": [{"id": "CAS-04", "condition_est": 0.55, "condition_band": [0.47, 0.63],
                 "trend_per_min": -0.01, "hsr_m_10m": 190, "baseline_hsr_m_10m": 370,
                 "sprints_10m": 2, "baseline_sprints_10m": 7}],
    "threat_by_channel": {"CAS_left": 0.20, "CAS_centre": 0.30, "CAS_right": 0.50},
}


def test_away_team_decision_reads_that_teams_rates_and_players():
    p = decide(AWAY, "CAS", "condition_below_60", SeedSequence(5), n=2_000)
    assert p["team"] == "CAS" and p["decision_id"].startswith("cas-62-")
    ev = {e["type"]: e for e in p["evidence"]}
    assert ev["condition"]["player_id"] == "CAS-04"
    assert ev["flank_threat"] == {"type": "flank_threat", "channel": "CAS_right", "share": 0.50}
    other = decide(AWAY, "CAS", "condition_below_60", SeedSequence(5), n=2_000)
    assert other == p


def test_away_team_uses_its_own_rates():
    swapped = {**AWAY, "rates": {"RFC": {"for90": 1.5, "against90": 1.2},
                                 "CAS": {"for90": 3.0, "against90": 0.4}}}
    base = decide(AWAY, "CAS", "t", SeedSequence(5), n=2_000)
    strong = decide(swapped, "CAS", "t", SeedSequence(5), n=2_000)
    assert strong["options"][0]["win"] > base["options"][0]["win"]


def test_two_decisions_in_one_minute_get_distinct_ids():
    a = decide({**SNAPSHOT, "t_ms": 3_720_000}, "RFC", "t", SeedSequence(5), n=500)
    b = decide({**SNAPSHOT, "t_ms": 3_745_000}, "RFC", "t", SeedSequence(5), n=500)
    assert a["decision_id"] != b["decision_id"]
    assert a["decision_id"] == "rfc-62-00" and b["decision_id"] == "rfc-62-25"


def test_snapshot_without_trend_per_min():
    player = {k: v for k, v in SNAPSHOT["players"][0].items() if k != "trend_per_min"}
    snap = {**SNAPSHOT, "players": [player]}
    ev = decide(snap, "RFC", "t", SeedSequence(5), n=500)["evidence"][0]
    assert ev["trend_per_min"] == 0.0


def test_decision_id_override_is_kept():
    p = payload(decision_id="rfc-62-07")
    assert p["decision_id"] == "rfc-62-07"
