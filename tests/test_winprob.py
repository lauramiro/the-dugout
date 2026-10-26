"""Per-minute win probability for the live feed: the same calculation as the demo files."""
import json
import time
from pathlib import Path

import pytest

from dugout.engine.payload import decide
from dugout.stream.replay import read_events
from dugout.stream.snapshots import lineup_from_scenario, process
from dugout.stream.winprob import winprob_point

ROOT = Path(__file__).parent.parent
DEMO = ROOT / "data" / "demo-rfc-cas-0073.jsonl"
SCENARIO = ROOT / "scenarios" / "riverside-castleton.yaml"
SERIES = ROOT / "web" / "public" / "demo" / "winprob.jsonl"


@pytest.fixture(scope="module")
def snapshots():
    return [r["snapshot"] for r in process(read_events(DEMO), lineup_from_scenario(SCENARIO)) if r["kind"] == "snapshot"]


def test_point_matches_the_build_scripts_series(snapshots):
    series = {(r["period"], r["t_ms"]): r for r in map(json.loads, SERIES.read_text(encoding="utf-8").splitlines())}
    checked = 0
    for s in snapshots:
        key = (s["period"], s["t_ms"])
        if key in series and s["t_ms"] in (600_000, 3_600_000, 4_800_000):
            point = winprob_point(s, "RFC", n=20_000, seed=s["t_ms"])
            assert point["kind"] == "winprob" and point["team"] == "RFC"
            assert (point["period"], point["t_ms"]) == key
            assert point["win"] == pytest.approx(series[key]["win"], abs=0.02)
            checked += 1
    assert checked == 3


def test_point_is_fast(snapshots):
    s = next(s for s in snapshots if s["t_ms"] == 3_600_000)
    winprob_point(s, "RFC", n=4000)  # warm-up, so a cold first call on a busy machine does not count
    times = []
    for _ in range(3):
        start = time.perf_counter()
        winprob_point(s, "RFC", n=4000)
        times.append(time.perf_counter() - start)
    assert min(times) < 0.25


@pytest.mark.parametrize("t_ms", [3_000_000, 4_140_000, 4_920_000, 5_280_000])
def test_away_card_baseline_matches_the_home_series(snapshots, t_ms):
    """The away team's no-change card and the home series read the same match: away loss is home win."""
    s = next(s for s in snapshots if s["period"] == 2 and s["t_ms"] == t_ms)
    home = winprob_point(s, "RFC", n=20_000)
    no_change = decide(s, "CAS", "test")["options"][0]
    assert no_change["loss"] == pytest.approx(home["win"], abs=0.02)
    assert no_change["win"] == pytest.approx(home["loss"], abs=0.02)
