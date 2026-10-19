"""Event Hubs consumer: the other end of dugout.stream.replay.EventHubsSink.

No checkpoint store: every run starts from a position given at start-up, never from saved
progress. The default is "@latest", so start the runner before the replay; `from_start` reads
the whole retained stream (a hub keeps 24 hours, so earlier replays would come back too).

The replay sends no end marker, so a run ends when no event has arrived for `idle_s` seconds
after the first one. `batches` then yields None (end of run) and, with `follow`, goes on
waiting for the next run.

Receiving uses EventHubConsumerClient.receive_batch (azure-eventhub 5.15.1), which blocks until
the client is closed, so it runs in a thread and the batches come back through a queue.
"""

from __future__ import annotations

import json
import os
import queue
import threading
import time
from collections.abc import Callable, Iterator
from typing import Protocol


class Runner(Protocol):
    def send(self, events: list[dict]) -> None: ...
    def end_run(self) -> None: ...


class EventHubsSource:
    def __init__(self, client, *, starting_position: str = "@latest", idle_s: float = 10.0,
                 poll_s: float = 1.0, clock: Callable[[], float] = time.monotonic) -> None:
        self._client, self._position = client, starting_position
        self._idle_s, self._poll_s, self._clock = idle_s, poll_s, clock

    @classmethod
    def from_env(cls, *, from_start: bool = False, idle_s: float = 10.0) -> EventHubsSource:
        from azure.eventhub import EventHubConsumerClient

        client = EventHubConsumerClient.from_connection_string(
            os.environ["EVENTHUB_CONNECTION_STRING"],
            consumer_group=os.environ.get("EVENTHUB_CONSUMER_GROUP", "$Default"),
            eventhub_name=os.environ.get("EVENTHUB_NAME"),
        )
        return cls(client, starting_position="-1" if from_start else "@latest", idle_s=idle_s)

    def batches(self, follow: bool = False) -> Iterator[list[dict] | None]:
        """Event batches in arrival order; None marks the end of a run."""
        inbox: queue.Queue = queue.Queue()

        def on_batch(_context, batch) -> None:
            inbox.put([json.loads(e.body_as_str()) for e in batch])

        def on_error(_context, error: Exception) -> None:
            inbox.put(error)

        receiver = threading.Thread(
            target=self._client.receive_batch, daemon=True,
            kwargs=dict(on_event_batch=on_batch, on_error=on_error, max_wait_time=self._poll_s,
                        starting_position=self._position))
        receiver.start()
        in_run, last = False, self._clock()
        try:
            while True:
                try:
                    item = inbox.get(timeout=self._poll_s)
                except queue.Empty:
                    item = []
                if isinstance(item, Exception):
                    raise item
                if item:
                    in_run, last = True, self._clock()
                    yield item
                elif in_run and self._clock() - last >= self._idle_s:
                    in_run = False
                    yield None
                    if not follow:
                        return
        finally:
            self._client.close()
            receiver.join(timeout=10)


def run_source(source: EventHubsSource, runner: Runner, *, follow: bool = False) -> None:
    for batch in source.batches(follow):
        if batch is None:
            runner.end_run()
        else:
            runner.send(batch)
