import json
from pathlib import Path

import pytest

from dugout.stream.replay import MemorySink, read_events, replay

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
