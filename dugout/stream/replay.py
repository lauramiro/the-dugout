"""Replay a recorded events JSONL into Event Hubs, or stdout when no connection is set.

    python -m dugout.stream.replay data/rfc-cas-0001.jsonl --speed 20

Settings (environment or a .env file in the working directory):
    EVENTHUB_CONNECTION_STRING   namespace or hub connection string
    EVENTHUB_NAME                hub name (not needed if the string carries EntityPath)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import Protocol

SPEEDS = (1, 5, 20)


class Sink(Protocol):
    def send(self, events: list[dict]) -> None: ...
    def close(self) -> None: ...


class MemorySink:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def send(self, events: list[dict]) -> None:
        self.events.extend(events)

    def close(self) -> None:
        pass


class StdoutSink:
    def send(self, events: list[dict]) -> None:
        for e in events:
            print(json.dumps(e), flush=True)

    def close(self) -> None:
        pass


class EventHubsSink:
    """One batch per send, keyed by match so a match stays in order on one partition."""

    def __init__(self, connection_string: str, eventhub_name: str | None = None) -> None:
        from azure.eventhub import EventHubProducerClient

        self._client = EventHubProducerClient.from_connection_string(
            connection_string, eventhub_name=eventhub_name
        )

    def send(self, events: list[dict]) -> None:
        from azure.eventhub import EventData

        batch = self._client.create_batch(partition_key=events[0]["match_id"])
        for e in events:
            batch.add(EventData(json.dumps(e)))
        self._client.send_batch(batch)

    def close(self) -> None:
        self._client.close()


def read_events(path: Path) -> list[dict]:
    with Path(path).open(encoding="utf-8") as f:
        events = [json.loads(line) for line in f if line.strip()]
    return sorted(events, key=lambda e: e["seq"])


def replay(
    events: Iterable[dict],
    sink: Sink,
    speed: int = 1,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Send events to the sink, spaced by match clock divided by `speed`.

    Events are taken in the order given (read_events sorts by seq). Events with the
    same period and t_ms go out as one batch. Match time only advances within a
    period, so the break between halves is not waited out. Due times are measured
    from the start, so sleep overshoot does not accumulate.
    """
    if speed not in SPEEDS:
        raise ValueError(f"speed must be one of {SPEEDS}, got {speed}")
    start = clock()
    offset_ms = 0
    prev: tuple[int, int] | None = None
    group: list[dict] = []

    def flush() -> None:
        if not group:
            return
        wait = start + offset_ms / 1000 / speed - clock()
        if wait > 0:
            sleep(wait)
        sink.send(list(group))
        group.clear()

    for e in events:
        key = (e["period"], e["t_ms"])
        if key != prev:
            flush()
            if prev is not None and key[0] == prev[0]:
                offset_ms += max(0, key[1] - prev[1])
            prev = key
        group.append(e)
    flush()


def load_dotenv(path: Path = Path(".env")) -> None:
    """Minimal KEY=VALUE reader; real environment variables win."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("\"'"))


def make_sink() -> Sink:
    conn = os.environ.get("EVENTHUB_CONNECTION_STRING")
    if conn:
        return EventHubsSink(conn, os.environ.get("EVENTHUB_NAME"))
    return StdoutSink()


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="dugout.stream.replay")
    ap.add_argument("events", type=Path, help="events JSONL (contract 1)")
    ap.add_argument("--speed", type=int, choices=SPEEDS, default=1)
    args = ap.parse_args(argv)

    load_dotenv()
    sink = make_sink()
    print(f"replaying {args.events} at {args.speed}x into {type(sink).__name__}", file=sys.stderr)
    try:
        replay(read_events(args.events), sink, speed=args.speed)
    finally:
        sink.close()


if __name__ == "__main__":
    main()
