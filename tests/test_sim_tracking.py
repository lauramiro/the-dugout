import json
import math
import subprocess
import sys

import pytest

from dugout.contracts import PITCH_LENGTH, PITCH_WIDTH
from dugout.sim.match import new_match, run_match
from dugout.sim.state import HALF_S
from dugout.sim.tracking import run_with_tracking


@pytest.fixture(scope="module")
def tracked(scenario):
    s, events = new_match(scenario, 6)
    more, frames = run_with_tracking(s)
    return s, events + more, frames


def test_tracking_does_not_change_the_event_stream(scenario, tracked):
    _, events, _ = tracked
    _, plain = run_match(scenario, 6)
    assert [e.to_dict() for e in events] == [e.to_dict() for e in plain]


def test_one_frame_every_500_ms_in_each_period(tracked):
    _, _, frames = tracked
    for period, start in ((1, 0), (2, HALF_S * 1000)):
        ts = [f["t_ms"] for f in frames if f["period"] == period]
        assert ts[0] == start
        assert ts == list(range(start, ts[-1] + 1, 500))
        assert ts[-1] >= start + HALF_S * 1000 - 500
    assert [f["period"] for f in frames] == sorted(f["period"] for f in frames)


def test_every_on_pitch_player_in_every_frame(tracked):
    s, events, frames = tracked
    on = {p.id for p in s.players.values() if p.on_pitch}
    off = {e.player_id for e in events if e.type == "sub"}
    for f in frames:
        ids = [p["id"] for p in f["players"]]
        assert len(ids) == len(set(ids)) == 22
        assert sum(i.startswith(s.home) for i in ids) == 11
    assert {p["id"] for p in frames[-1]["players"]} == on
    assert not off & {p["id"] for p in frames[-1]["players"]}


def test_coordinates_inside_the_pitch(tracked):
    _, _, frames = tracked
    for f in frames:
        for obj in (f["ball"], *f["players"]):
            assert 0 <= obj["x"] <= PITCH_LENGTH and 0 <= obj["y"] <= PITCH_WIDTH


def test_speed_comes_from_successive_positions(tracked):
    _, _, frames = tracked
    speeds = []
    for prev, cur in zip(frames, frames[1:]):
        if cur["period"] != prev["period"]:
            continue
        last = {p["id"]: p for p in prev["players"]}
        for p in cur["players"]:
            if p["id"] in last:
                q = last[p["id"]]
                assert p["v"] == pytest.approx(math.dist((p["x"], p["y"]), (q["x"], q["y"])) / 0.5, abs=0.35)
                speeds.append(p["v"])
    assert max(speeds) < 12.0
    assert 0.5 < sum(speeds) / len(speeds) < 4.0


def test_frames_carry_observables_only(tracked):
    _, _, frames = tracked
    for f in frames[:50]:
        assert set(f) == {"match_id", "period", "t_ms", "ball", "players"}
        for p in f["players"]:
            assert set(p) == {"id", "x", "y", "v"}


def test_same_seed_same_frames(scenario, tracked):
    _, _, frames = tracked
    s, _ = new_match(scenario, 6)
    _, again = run_with_tracking(s)
    assert again == frames


def test_cli_run_writes_tracking_next_to_events(tmp_path):
    out = tmp_path / "m.jsonl"
    subprocess.run([sys.executable, "-m", "dugout.sim", "run", "--seed", "2", "--out", str(out)],
                   check=True, capture_output=True)
    events = out.read_text(encoding="utf-8").splitlines()
    frames = (tmp_path / "m.tracking.jsonl").read_text(encoding="utf-8").splitlines()
    assert events and frames
    assert json.loads(frames[0])["t_ms"] == 0
