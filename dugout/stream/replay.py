"""Replay a recorded events JSONL into Event Hubs, or stdout when no connection is set.

    python -m dugout.stream.replay data/rfc-cas-0001.jsonl --speed 20
    python -m dugout.stream.replay data/demo-rfc-cas-0073.jsonl --speed 5 --every 30
    python -m dugout.stream.replay data/demo-rfc-cas-0073.jsonl --speed 5 --every 30 --write-schedule out/schedule.json

With --every N the replay waits for the next kick-off slot (every N minutes from midnight UTC)
before it starts; the scheduled job in infra/deploy.sh starts it shortly before each slot.
--write-schedule writes the schedule the live page counts down to, and replays nothing.

Settings (environment or a .env file in the working directory):
    EVENTHUB_CONNECTION_STRING   namespace or hub connection string
    EVENTHUB_NAME                hub name (not needed if the string carries EntityPath)
For a container command without flags: REPLAY_EVENTS (the events file), REPLAY_SPEED and
REPLAY_EVERY_MIN stand in for the argument and the flags.
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
# The live runner (dugout.stream.consumer) ends a run after RUN_IDLE_S (30 s) without events, so no wait
# may reach that: a goal celebration is 65 s of match time, 13 s at 5x.
MAX_WAIT_S = 8.0
# A job that starts this late after its slot still kicks off at once instead of waiting a
# whole cycle.
LATE_S = 120


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


def timed_groups(
    events: Iterable[dict], speed: int = 1, max_wait_s: float | None = MAX_WAIT_S
) -> Iterator[tuple[float, list[dict]]]:
    """(seconds from the start, batch) for each batch of events sharing a period and t_ms.

    Match time only advances within a period, so the break between halves is not waited out,
    and a wait longer than `max_wait_s` is cut to it.
    """
    if speed not in SPEEDS:
        raise ValueError(f"speed must be one of {SPEEDS}, got {speed}")
    due = 0.0
    prev: tuple[int, int] | None = None
    group: list[dict] = []
    for e in events:
        key = (e["period"], e["t_ms"])
        if key != prev:
            if group:
                yield due, group
                group = []
            if prev is not None and key[0] == prev[0]:
                wait = max(0, key[1] - prev[1]) / 1000 / speed
                due += wait if max_wait_s is None else min(wait, max_wait_s)
            prev = key
        group.append(e)
    if group:
        yield due, group


def replay(
    events: Iterable[dict],
    sink: Sink,
    speed: int = 1,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    max_wait_s: float | None = MAX_WAIT_S,
) -> None:
    """Send events to the sink, spaced by match clock divided by `speed` (see timed_groups).

    Events are taken in the order given (read_events sorts by seq). Due times are measured
    from the start, so sleep overshoot does not accumulate.
    """
    groups = timed_groups(events, speed, max_wait_s)
    start = clock()
    for due, group in groups:
        wait = start + due - clock()
        if wait > 0:
            sleep(wait)
        sink.send(group)


def run_seconds(events: Iterable[dict], speed: int = 1, max_wait_s: float | None = MAX_WAIT_S) -> float:
    """Wall seconds from the first batch to the last."""
    due = 0.0
    for due, _ in timed_groups(events, speed, max_wait_s):
        pass
    return due


def kickoff_slot(now_s: float, every_min: int, late_s: float = LATE_S) -> float:
    """The slot to kick off at (epoch seconds): the one just passed when it is at most `late_s`
    ago, else the next. Slots fall every `every_min` minutes from midnight UTC."""
    period = every_min * 60
    last = now_s // period * period
    return last if now_s - last <= late_s else last + period


def schedule(events: list[dict], speed: int, every_min: int, max_wait_s: float | None = MAX_WAIT_S) -> dict:
    """What the live page needs to count down to the next kick-off (web/lib/schedule.ts)."""
    return {
        "match_id": events[0]["match_id"] if events else None,
        "every_min": every_min,
        "speed": speed,
        "duration_ms": round(run_seconds(events, speed, max_wait_s) * 1000),
    }


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
    load_dotenv()
    env = os.environ
    ap = argparse.ArgumentParser(prog="dugout.stream.replay")
    ap.add_argument("events", type=Path, nargs="?", default=env.get("REPLAY_EVENTS"),
                    help="events JSONL (contract 1)")
    ap.add_argument("--speed", type=int, choices=SPEEDS, default=int(env.get("REPLAY_SPEED", 1)))
    ap.add_argument("--every", type=int, metavar="MIN", default=int(env.get("REPLAY_EVERY_MIN", 0)),
                    help="kick off on the next slot of every MIN minutes from midnight UTC (a divisor of 60)")
    ap.add_argument("--write-schedule", type=Path, metavar="PATH",
                    help="write the live page's schedule (needs --every) and replay nothing")
    args = ap.parse_args(argv)
    if args.events is None:
        ap.error("give an events file or set REPLAY_EVENTS")
    if args.every and (args.every < 0 or 60 % args.every):
        ap.error("--every must divide 60")
    events = read_events(args.events)

    if args.write_schedule:
        if not args.every:
            ap.error("--write-schedule needs --every")
        args.write_schedule.write_text(json.dumps(schedule(events, args.speed, args.every)) + "\n", encoding="utf-8")
        print(f"wrote {args.write_schedule}", file=sys.stderr)
        return

    if args.every:
        slot = kickoff_slot(time.time(), args.every)
        wait = slot - time.time()
        print(f"kick-off at {time.strftime('%H:%M:%S', time.gmtime(slot))} UTC, in {max(0, wait):.0f} s", file=sys.stderr)
        if wait > 0:
            time.sleep(wait)
    sink = make_sink()
    print(f"replaying {args.events} at {args.speed}x into {type(sink).__name__}", file=sys.stderr)
    try:
        replay(events, sink, speed=args.speed)
    finally:
        sink.close()


if __name__ == "__main__":
    main()
