"""Event Hubs consumer with a fake client (the real one waits for the user's OK)."""
import json
import threading
import time

import pytest

from dugout.stream.consumer import EventHubsSource, run_source


class FakeEventData:
    def __init__(self, event):
        self._body = json.dumps(event)

    def body_as_str(self):
        return self._body


class FakeClient:
    """Stands in for EventHubConsumerClient: receive_batch blocks until close()."""

    def __init__(self, batches, fail=None):
        """`batches` items are event lists, or (delay_s, event list) to arrive later."""
        self.batches, self.fail = batches, fail
        self.kwargs = {}
        self.closed = threading.Event()

    def receive_batch(self, on_event_batch, **kwargs):
        self.kwargs = kwargs
        for b in self.batches:
            delay, b = b if isinstance(b, tuple) else (0, b)
            end = time.monotonic() + delay
            while time.monotonic() < end:
                on_event_batch(None, [])
                time.sleep(0.01)
            on_event_batch(None, [FakeEventData(e) for e in b])
        if self.fail:
            kwargs["on_error"](None, self.fail)
        while not self.closed.is_set():
            on_event_batch(None, [])  # what max_wait_time produces when idle
            time.sleep(0.01)

    def close(self):
        self.closed.set()


class Recorder:
    def __init__(self):
        self.log = []

    def send(self, events):
        self.log.append(("send", [e["seq"] for e in events]))

    def end_run(self):
        self.log.append(("end",))


def source(client, **kw):
    return EventHubsSource(client, idle_s=0.1, poll_s=0.02, **kw)


def test_batches_arrive_in_order_then_the_run_ends():
    client = FakeClient([[{"seq": 1}, {"seq": 2}], [{"seq": 3}]])
    rec = Recorder()
    run_source(source(client), rec)
    assert rec.log == [("send", [1, 2]), ("send", [3]), ("end",)]
    assert client.closed.is_set()


def test_reads_from_the_latest_by_default_and_from_the_start_on_request():
    a, b = FakeClient([[{"seq": 1}]]), FakeClient([[{"seq": 1}]])
    run_source(source(a), Recorder())
    run_source(source(b, starting_position="-1"), Recorder())
    assert a.kwargs["starting_position"] == "@latest" and b.kwargs["starting_position"] == "-1"
    assert "checkpoint_store" not in a.kwargs and a.kwargs["max_wait_time"] == 0.02


def test_idle_before_the_first_event_is_not_an_end_of_run():
    client = FakeClient([(0.4, [{"seq": 1}])])  # longer than idle_s
    rec = Recorder()
    run_source(source(client), rec)
    assert rec.log == [("send", [1]), ("end",)]


def test_follow_goes_on_to_a_second_run():
    client = FakeClient([[{"seq": 1}], (0.4, [{"seq": 1}])])
    gen = source(client).batches(follow=True)
    got = [next(gen) for _ in range(4)]
    gen.close()
    assert got == [[{"seq": 1}], None, [{"seq": 1}], None]
    assert client.closed.is_set()


def test_a_receive_error_is_raised():
    client = FakeClient([], fail=RuntimeError("auth failed"))
    with pytest.raises(RuntimeError, match="auth failed"):
        list(source(client).batches())
    assert client.closed.is_set()
