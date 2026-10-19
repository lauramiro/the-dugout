"""Live pipeline: events in, snapshots and cards out through Web PubSub.

    python -m dugout.stream.pipeline data/demo-rfc-cas-0073.jsonl --scenario scenarios/riverside-castleton.yaml
    python -m dugout.stream.pipeline --eventhub --follow --scenario scenarios/riverside-castleton.yaml

Each event goes to the state engine; each snapshot is published as it is, and goes to the
decision-point triggers. A closed card is published as its `card_closed` record. A decision
point is sent to the decision service (in process, or over HTTP when SERVICE_URL is set),
which runs the engine, narrates and publishes the card. The runner only moves messages:
numbers come from the engine and text from the narration pipeline.

Settings (environment or .env): EVENTHUB_CONNECTION_STRING, EVENTHUB_NAME, EVENTHUB_CONSUMER_GROUP
(default $Default) for the Event Hubs source; WEBPUBSUB_CONNECTION_STRING, WEBPUBSUB_HUB for
publishing; SERVICE_URL for a remote decision service. For a container command without flags:
PIPELINE_SOURCE=eventhub (read Event Hubs and keep following) and SCENARIO (default
scenarios/riverside-castleton.yaml).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from collections.abc import Iterable
from pathlib import Path
from typing import Protocol

from dugout.service.app import DecisionRequest, open_and_publish
from dugout.service.cards import CardService, default_service
from dugout.service.publisher import Publisher, default_publisher
from dugout.stream.replay import SPEEDS, load_dotenv, read_events, replay
from dugout.stream.snapshots import lineup_from_scenario
from dugout.stream.state_engine import StateEngine
from dugout.stream.triggers import DecisionPoints


class Decisions(Protocol):
    def open(self, point: dict) -> dict:
        """Send one decision point (a `decision_point` record); return the service's answer."""
        ...


def _request(point: dict, locale: str, mode: str) -> dict:
    return {"snapshot": point["snapshot"], "team": point["team"], "trigger": point["trigger"],
            "decision_id": point["id"], "locale": locale, "mode": mode}


class InProcessDecisions:
    """The decision service called as a function: same logic as POST /decisions."""

    def __init__(self, cards: CardService, publisher: Publisher | None,
                 locale: str = "en", mode: str = "casual") -> None:
        self._cards, self._publisher, self._locale, self._mode = cards, publisher, locale, mode

    def open(self, point: dict) -> dict:
        req = DecisionRequest(**_request(point, self._locale, self._mode))
        return open_and_publish(self._cards, self._publisher, req)


class HttpDecisions:
    """The deployed decision service, which publishes the card itself."""

    def __init__(self, base_url: str, locale: str = "en", mode: str = "casual", timeout_s: float = 60) -> None:
        self._url, self._locale, self._mode, self._timeout = base_url.rstrip("/") + "/decisions", locale, mode, timeout_s

    def open(self, point: dict) -> dict:
        body = json.dumps(_request(point, self._locale, self._mode)).encode()
        req = urllib.request.Request(self._url, body, {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self._timeout) as res:
            return json.load(res)


class PipelineRunner:
    """A replay Sink: feed it event batches, call `end_run` when the stream ends."""

    def __init__(self, lineup: list[dict], decisions: Decisions, publisher: Publisher | None,
                 prior90: float = 1.35) -> None:
        self._lineup, self._prior90 = lineup, prior90
        self._decisions, self._publisher = decisions, publisher
        self.errors: list[tuple[str, Exception]] = []
        self._reset()

    def _reset(self) -> None:
        self._engine = StateEngine(self._lineup, prior90=self._prior90)
        self._points = DecisionPoints()

    def send(self, events: list[dict]) -> None:
        for e in events:
            self._handle(self._engine.feed(e))

    def end_run(self) -> None:
        """End of the stream: last snapshots, close the open card, and start clean for the next run."""
        self._handle(self._engine.finish())
        for record in self._points.finish():
            self._publish(record)
        self._reset()

    def close(self) -> None:
        pass

    def _handle(self, ticks: Iterable[tuple[dict, list[dict]]]) -> None:
        for snapshot, new in ticks:
            self._publish(snapshot)
            for record in self._points.on_snapshot(snapshot, new):
                if record["kind"] == "card_closed":
                    self._publish(record)
                else:
                    self._open(record)

    def _publish(self, message: dict) -> None:
        if self._publisher is not None:
            self._publisher.publish(message)

    def _open(self, point: dict) -> None:
        # a failed card must not stop the stream; the error is kept and printed
        try:
            self._decisions.open(point)
        except Exception as err:
            self.errors.append((point["id"], err))
            print(f"decision {point['id']} failed: {err!r}", file=sys.stderr)


def make_decisions(publisher: Publisher | None, service_url: str | None) -> Decisions:
    if service_url:
        return HttpDecisions(service_url)
    return InProcessDecisions(default_service(), publisher)


def main(argv: list[str] | None = None) -> None:
    load_dotenv()
    from_env = os.environ.get("PIPELINE_SOURCE") == "eventhub"
    ap = argparse.ArgumentParser(prog="dugout.stream.pipeline")
    ap.add_argument("events", type=Path, nargs="?", help="events JSONL (contract 1); omit with --eventhub")
    ap.add_argument("--eventhub", action="store_true", default=from_env, help="read from Event Hubs instead of a file")
    ap.add_argument("--scenario", type=Path, default=Path(os.environ.get("SCENARIO", "scenarios/riverside-castleton.yaml")),
                    help="scenario YAML, for the lineup")
    ap.add_argument("--speed", type=int, choices=SPEEDS, default=1, help="file source only")
    ap.add_argument("--follow", action="store_true", default=from_env, help="Event Hubs: keep waiting for further runs")
    ap.add_argument("--from-start", action="store_true",
                    help="Event Hubs: read the whole retained stream, not only new events")
    ap.add_argument("--prior", type=float, default=1.35, help="pre-match xG/90 for each team")
    args = ap.parse_args(argv)
    if bool(args.events) == args.eventhub:
        ap.error("give an events file or --eventhub, not both or neither")

    publisher = default_publisher()
    decisions = make_decisions(publisher, os.environ.get("SERVICE_URL"))
    runner = PipelineRunner(lineup_from_scenario(args.scenario), decisions, publisher, args.prior)
    print(f"source {'Event Hubs' if args.eventhub else args.events}; decisions via {type(decisions).__name__}; "
          f"publishing {'to Web PubSub' if publisher else 'nowhere (WEBPUBSUB_CONNECTION_STRING not set)'}",
          file=sys.stderr)
    if args.eventhub:
        from dugout.stream.consumer import EventHubsSource, run_source

        source = EventHubsSource.from_env(from_start=args.from_start)
        run_source(source, runner, follow=args.follow)
    else:
        replay(read_events(args.events), runner, speed=args.speed)
        runner.end_run()
    if runner.errors:
        sys.exit(f"{len(runner.errors)} decision(s) failed")


if __name__ == "__main__":
    main()
