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
    "rates": {"RFC": {"for90": 1.5, "against90": 1.2}},
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
    return decide(SNAPSHOT, "condition_below_60", SeedSequence(5), n=N, **kw)


def test_contract_4_keys_and_types():
    p = payload()
    assert set(p) == {"decision_id", "t_ms", "team", "trigger", "options", "recommendation",
                      "evidence", "manager_action"}
    assert p["decision_id"] == "rfc-62-01"
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
    ids = [o["id"] for o in decide(snap, "manager_sub", SeedSequence(5), n=2_000)["options"]]
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
