import json
from pathlib import Path

import pytest

from dugout.stream.replay import (
    MAX_WAIT_S, MemorySink, kickoff_slot, main, read_events, replay, run_seconds, schedule,
)

FIXTURE = Path(__file__).parent / "fixtures" / "replay-events.jsonl"


class FakeClock:
    """Injected clock and sleep, so spacing is checked without waiting."""

    def __init__(self):
        self.now = 100.0

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def run(speed):
    clock = FakeClock()
    stamped = []

    class Stamping(MemorySink):
        def send(self, events):
            stamped.extend((clock.now, e["seq"]) for e in events)
            super().send(events)

    sink = Stamping()
    replay(read_events(FIXTURE), sink, speed=speed, clock=clock.time, sleep=clock.sleep)
    return sink, stamped


def test_read_events_orders_by_seq():
    assert [e["seq"] for e in read_events(FIXTURE)] == [1, 2, 3, 4, 5, 6]


def test_replay_delivers_every_event_in_seq_order():
    sink, _ = run(20)
    assert [e["seq"] for e in sink.events] == [1, 2, 3, 4, 5, 6]
    assert sink.events[0] == json.loads(FIXTURE.read_text().splitlines()[1])


def test_spacing_at_20x():
    _, stamped = run(20)
    at = {seq: t - 100.0 for t, seq in stamped}
    assert at[1] == pytest.approx(0.0)
    assert at[2] == pytest.approx(1.0 / 20)
    assert at[3] == pytest.approx(2.0 / 20)
    assert at[4] == pytest.approx(2.0 / 20)  # same match clock as seq 3
    assert at[6] - at[5] == pytest.approx(4.0 / 20)


def test_halftime_is_not_waited_out():
    _, stamped = run(1)
    at = {seq: t - 100.0 for t, seq in stamped}
    assert at[5] == pytest.approx(at[4])


def test_events_sharing_a_match_clock_go_out_as_one_batch():
    batches = []

    class Batches(MemorySink):
        def send(self, events):
            batches.append([e["seq"] for e in events])

    clock = FakeClock()
    replay(read_events(FIXTURE), Batches(), speed=5, clock=clock.time, sleep=clock.sleep)
    assert batches == [[1], [2], [3, 4], [5], [6]]


def test_rejects_unknown_speed():
    with pytest.raises(ValueError):
        replay([], MemorySink(), speed=3)


def test_long_waits_are_cut_so_the_runner_does_not_end_the_run():
    events = [{"seq": 1, "match_id": "m", "period": 2, "t_ms": 0},
              {"seq": 2, "match_id": "m", "period": 2, "t_ms": 65_000}]  # a goal celebration
    assert run_seconds(events, speed=5) == pytest.approx(MAX_WAIT_S)
    assert run_seconds(events, speed=5, max_wait_s=None) == pytest.approx(13.0)


def test_run_seconds_matches_the_replay():
    _, stamped = run(5)
    assert run_seconds(read_events(FIXTURE), speed=5) == pytest.approx(stamped[-1][0] - stamped[0][0])


def test_kickoff_slot_waits_for_the_next_slot_unless_just_late():
    slot = 1_800 * 1000  # a half-hour boundary in epoch seconds
    assert kickoff_slot(slot - 120, 30) == slot  # the job starts two minutes early
    assert kickoff_slot(slot + 30, 30) == slot  # a late start still kicks off at once
    assert kickoff_slot(slot + 600, 30) == slot + 1_800


def test_schedule_is_what_the_page_counts_down_to():
    events = read_events(FIXTURE)
    s = schedule(events, speed=5, every_min=30)
    assert s == {"match_id": events[0]["match_id"], "every_min": 30, "speed": 5,
                 "duration_ms": round(run_seconds(events, 5) * 1000)}


def test_write_schedule_replays_nothing(tmp_path, capsys):
    out = tmp_path / "schedule.json"
    main([str(FIXTURE), "--speed", "5", "--every", "30", "--write-schedule", str(out)])
    assert json.loads(out.read_text())["every_min"] == 30
    assert capsys.readouterr().out == ""


def test_every_must_divide_an_hour():
    with pytest.raises(SystemExit):
        main([str(FIXTURE), "--every", "25", "--write-schedule", "x.json"])
