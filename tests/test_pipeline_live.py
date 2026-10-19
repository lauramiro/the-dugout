"""Live pipeline: the demo stream through the runner with an in-process service and a fake publisher."""
import io
import json
from pathlib import Path

import pytest

from dugout.agents.pipeline import NarrationPipeline, StubClient
from dugout.engine.payload import decide
from dugout.service.cards import CardService
from dugout.service.store import MemoryStore
from dugout.stream import pipeline as live
from dugout.stream.pipeline import HttpDecisions, InProcessDecisions, PipelineRunner
from dugout.stream.replay import read_events, replay
from dugout.stream.snapshots import lineup_from_scenario, process

ROOT = Path(__file__).parent.parent
DEMO = ROOT / "data" / "demo-rfc-cas-0073.jsonl"
SCENARIO = ROOT / "scenarios" / "riverside-castleton.yaml"


class FakePublisher:
    def __init__(self):
        self.sent = []

    def publish(self, payload):
        self.sent.append(payload)

    def client_url(self):
        return "wss://example.invalid"


def make_runner(publisher, **kw):
    cards = CardService(lambda s, t, g, **k: decide(s, t, g, n=500, **k),
                        NarrationPipeline(StubClient()), MemoryStore())
    return PipelineRunner(lineup_from_scenario(SCENARIO), InProcessDecisions(cards, publisher), publisher, **kw)


@pytest.fixture(scope="module")
def run():
    """The demo stream through the runner, and the same stream through snapshots.process."""
    pub = FakePublisher()
    runner = make_runner(pub)
    replay(read_events(DEMO), runner, speed=20, clock=lambda: 0.0, sleep=lambda s: None)
    runner.end_run()
    reference = list(process(read_events(DEMO), lineup_from_scenario(SCENARIO)))
    return pub.sent, reference, runner


def test_every_snapshot_and_card_in_order(run):
    sent, reference, runner = run
    expected = []
    for r in reference:
        if r["kind"] == "snapshot":
            expected.append(("snapshot", r["snapshot"]["t_ms"]))
        elif r["kind"] == "card_closed":
            expected.append(("card_closed", r["id"]))
        else:
            expected.append(("card", r["id"]))
    got = [("card_closed", m["id"]) if m.get("kind") == "card_closed"
           else ("card", m["decision_id"]) if "decision_id" in m
           else ("snapshot", m["t_ms"]) for m in sent]
    assert got == expected
    assert sum(k == "card" for k, _ in got) >= 3 and not runner.errors


def test_a_cards_id_is_its_decision_points_id(run):
    sent, reference, _ = run
    points = {r["id"]: r for r in reference if r["kind"] == "decision_point"}
    cards = [m for m in sent if "decision_id" in m]
    assert [c["decision_id"] for c in cards] == list(points)
    for c in cards:
        assert c["payload"]["decision_id"] == c["decision_id"]
        assert c["payload"]["team"] == points[c["decision_id"]]["team"]
        assert c["payload"]["trigger"] == points[c["decision_id"]]["trigger"]


def test_every_card_closes_once(run):
    sent, _, _ = run
    opened = [m["decision_id"] for m in sent if "decision_id" in m]
    closed = [m["id"] for m in sent if m.get("kind") == "card_closed"]
    assert sorted(opened) == sorted(closed)


def test_a_second_run_starts_clean():
    pub = FakePublisher()
    runner = make_runner(pub)
    events = read_events(DEMO)[:300]
    for _ in range(2):
        runner.send(events)
        runner.end_run()
    snapshots = [m["t_ms"] for m in pub.sent if "subs_left" in m]
    half = len(snapshots) // 2
    assert snapshots[:half] == snapshots[half:]


def test_a_failing_service_does_not_stop_the_stream():
    class Broken:
        def open(self, point):
            raise RuntimeError("service down")

    pub = FakePublisher()
    runner = PipelineRunner(lineup_from_scenario(SCENARIO), Broken(), pub)
    runner.send(read_events(DEMO))
    runner.end_run()
    assert runner.errors and sum("subs_left" in m for m in pub.sent) > 100


def test_http_decisions_posts_the_point_with_its_id(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout):
        seen["url"], seen["body"] = req.full_url, json.loads(req.data)
        return io.BytesIO(b'{"pushed": true}')

    monkeypatch.setattr(live.urllib.request, "urlopen", fake_urlopen)
    point = {"id": "rfc-62-01", "team": "RFC", "trigger": "manager_sub", "snapshot": {"t_ms": 1}}
    assert HttpDecisions("https://svc.example/").open(point) == {"pushed": True}
    assert seen["url"] == "https://svc.example/decisions"
    assert seen["body"]["decision_id"] == "rfc-62-01" and seen["body"]["snapshot"] == {"t_ms": 1}


# Message shapes against web/lib/live.ts (LiveDataSource.receive), which tells messages apart by key:
#   :87  if ("decision_id" in msg) { const payload = msg as DecisionPayload; ... payload.t_ms ... narration: {} }
#   :92  } else if ("seq" in msg) {            (a match event)
#   :96  } else if ("ball" in msg) {           (a tracking frame)
#   :100 } else if ("subs_left" in msg) {      (a Snapshot: reads s.t_ms)
#   :104 } else { return; }                    (anything else is ignored)
SNAPSHOT_KEYS = {"t_ms", "score", "subs_left", "windows_left", "rates", "players", "threat_by_channel"}  # contracts.ts Snapshot
PAYLOAD_KEYS = {"decision_id", "t_ms", "team", "trigger", "options", "recommendation", "evidence", "manager_action"}


def test_snapshot_messages_are_read_as_snapshots(run):
    snaps = [m for m in run[0] if "subs_left" in m]
    assert snaps
    for m in snaps:
        assert SNAPSHOT_KEYS <= set(m)
        assert not {"decision_id", "seq", "ball"} & set(m)  # earlier branches in receive()
        assert isinstance(m["t_ms"], int)


def test_card_closed_messages_are_ignored_by_live_ts(run):
    closed = [m for m in run[0] if m.get("kind") == "card_closed"]
    assert closed and not {"decision_id", "seq", "ball", "subs_left"} & set(closed[0])


def test_card_messages_carry_a_full_payload(run):
    card = next(m for m in run[0] if "decision_id" in m)
    assert set(card["payload"]) == PAYLOAD_KEYS
    assert {"headline", "reason", "source", "locale", "mode"} <= set(card)


@pytest.mark.xfail(strict=True, reason="live.ts reads t_ms and the options from the message itself, "
                   "but the service publishes a card with them under 'payload' (see TASK.md, Blocked)")
def test_card_messages_match_what_live_ts_reads(run):
    card = next(m for m in run[0] if "decision_id" in m)
    assert PAYLOAD_KEYS <= set(card)
