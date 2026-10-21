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


def test_cards_closings_and_snapshots_in_order(run):
    """Cards and closings in the reference order (first copy of each card); snapshots are a
    subset of the reference's, in order."""
    sent, reference, runner = run
    expected = [("card_closed", r["id"]) if r["kind"] == "card_closed" else ("card", r["id"])
                for r in reference if r["kind"] != "snapshot"]
    got, seen = [], set()
    for m in sent:
        if m.get("kind") == "card_closed":
            got.append(("card_closed", m["id"]))
        elif "decision_id" in m and m["decision_id"] not in seen:
            seen.add(m["decision_id"])
            got.append(("card", m["decision_id"]))
    assert got == expected
    reference_times = [r["snapshot"]["t_ms"] for r in reference if r["kind"] == "snapshot"]
    times = [m["t_ms"] for m in sent if "subs_left" in m]
    it = iter(reference_times)
    assert all(t in it for t in times)
    assert sum(k == "card" for k, _ in got) >= 3 and not runner.errors


def test_a_cards_id_is_its_decision_points_id(run):
    sent, reference, _ = run
    points = {r["id"]: r for r in reference if r["kind"] == "decision_point"}
    cards = [m for m in sent if "decision_id" in m]
    assert list(dict.fromkeys(c["decision_id"] for c in cards)) == list(points)
    for c in cards:
        assert c["payload"]["decision_id"] == c["decision_id"]
        assert c["payload"]["team"] == points[c["decision_id"]]["team"]
        assert c["payload"]["trigger"] == points[c["decision_id"]]["trigger"]


def test_every_card_closes_once(run):
    sent, _, _ = run
    opened = list(dict.fromkeys(m["decision_id"] for m in sent if "decision_id" in m))
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
SNAPSHOT_KEYS = {"t_ms", "score", "subs_left", "windows_left", "rates", "players"}  # what the live page reads of contracts.ts Snapshot
PAYLOAD_KEYS = {"decision_id", "t_ms", "team", "trigger", "options", "recommendation", "evidence", "manager_action"}


def test_snapshot_messages_are_read_as_snapshots(run):
    snaps = [m for m in run[0] if "subs_left" in m]
    assert snaps
    for m in snaps:
        assert SNAPSHOT_KEYS <= set(m)
        assert not {"decision_id", "seq", "ball"} & set(m)  # earlier branches in receive()
        assert isinstance(m["t_ms"], int)


def test_card_closed_messages_carry_what_live_ts_reads(run):
    closed = [m for m in run[0] if m.get("kind") == "card_closed"]
    assert closed and not {"decision_id", "seq", "ball", "subs_left"} & set(closed[0])
    cards = {m["decision_id"] for m in run[0] if "decision_id" in m}
    for m in closed:
        assert {"id", "t_ms", "period", "reason"} <= set(m) and m["id"] in cards


def test_card_messages_carry_a_full_payload(run):
    card = next(m for m in run[0] if "decision_id" in m)
    assert set(card["payload"]) == PAYLOAD_KEYS
    assert {"headline", "reason", "source", "locale", "mode"} <= set(card)


def test_card_messages_match_what_live_ts_reads(run):
    """web/lib/live.ts: a card is recognised by decision_id and read from msg.payload, with
    its narration from headline, reason and source under msg.locale and msg.mode."""
    card = next(m for m in run[0] if "decision_id" in m and m.get("kind") != "card_closed")
    assert PAYLOAD_KEYS <= set(card["payload"]) and card["payload"]["decision_id"] == card["decision_id"]
    assert {"headline", "reason", "source"} <= set(card) and card["locale"] == "en"
    assert isinstance(card["payload"]["t_ms"], int)


# --- publish errors, every narration, smaller snapshots ---

class FlakyPublisher(FakePublisher):
    """Refuses every third snapshot, as Web PubSub does when it throttles (429)."""

    def __init__(self):
        super().__init__()
        self.snapshots = 0

    def publish(self, payload):
        if "subs_left" in payload:
            self.snapshots += 1
            if self.snapshots % 3 == 0:
                raise RuntimeError("429 Too Many Requests")
        super().publish(payload)


def test_a_failing_publisher_does_not_stop_the_stream():
    pub = FlakyPublisher()
    runner = make_runner(pub)
    runner.send(read_events(DEMO))
    runner.end_run()
    assert runner.publish_errors == pub.snapshots // 3 > 0
    assert any(m.get("kind") == "card_closed" and m["reason"] == "full_time" for m in pub.sent)


def test_every_card_is_narrated_in_every_locale_and_mode(run):
    sent, _, _ = run
    cards = [m for m in sent if "decision_id" in m]
    versions = {}
    for c in cards:
        versions.setdefault(c["decision_id"], set()).add((c["locale"], c["mode"]))
    assert versions and all(v == {("en", "casual"), ("en", "analyst"), ("es", "casual"), ("es", "analyst")}
                            for v in versions.values())
    first = {}
    for c in cards:
        first.setdefault(c["decision_id"], (c["locale"], c["mode"]))
    assert set(first.values()) == {("en", "casual")}  # the default version goes out first


def test_published_snapshots_are_thinned_and_slim(run):
    sent, reference, _ = run
    snaps = [m for m in sent if "subs_left" in m]
    all_snaps = [r for r in reference if r["kind"] == "snapshot"]
    assert len(snaps) < len(all_snaps) / 2
    opened_at = {r["snapshot"]["t_ms"] for r in reference if r["kind"] == "decision_point"}
    # the clock restarts at 45:00 for the second half, so gaps are measured within a period
    pairs = [(a, b) for a, b in zip(snaps, snaps[1:]) if a["period"] == b["period"]]
    short = [b["t_ms"] for a, b in pairs if b["t_ms"] - a["t_ms"] < 30_000]
    assert all(t in opened_at for t in short), "a snapshot closer than 30 s must be one a card opened on"
    assert pairs and max(b["t_ms"] - a["t_ms"] for a, b in pairs) <= 30_000
    for s in snaps:
        assert "threat_by_channel" not in s
        assert all(not {"team", "role"} & set(p) for p in s["players"])


def test_each_card_follows_the_snapshot_it_opened_on(run):
    sent, reference, _ = run
    opened = {r["id"]: r["snapshot"]["t_ms"] for r in reference if r["kind"] == "decision_point"}
    last_snapshot = None
    for m in sent:
        if "subs_left" in m:
            last_snapshot = m["t_ms"]
        elif "decision_id" in m and m["locale"] == "en" and m["mode"] == "casual":
            assert last_snapshot == opened[m["decision_id"]]


def test_other_versions_can_be_narrated_on_a_thread_pool():
    from concurrent.futures import ThreadPoolExecutor

    pub = live.LockedPublisher(FakePublisher())
    cards = CardService(lambda s, t, g, **k: decide(s, t, g, n=500, **k),
                        NarrationPipeline(StubClient()), MemoryStore())
    pool = ThreadPoolExecutor(max_workers=3)
    runner = PipelineRunner(lineup_from_scenario(SCENARIO), InProcessDecisions(cards, pub, extra=pool), pub)
    runner.send(read_events(DEMO))
    runner.end_run()
    pool.shutdown(wait=True)
    sent = pub._inner.sent
    ids = {m["decision_id"] for m in sent if "decision_id" in m}
    assert ids and sum("decision_id" in m for m in sent) == 4 * len(ids)


def test_key_events_are_published_and_others_are_not(run):
    sent = run[0]
    events = [m for m in sent if "seq" in m]
    types = [e["type"] for e in events]
    assert set(types) <= set(live.KEY_EVENT_TYPES)
    assert types.count("goal") == 5 and types.count("sub") == 3
    assert not {"pass", "hsr", "sprint"} & set(types)


def test_one_winprob_point_per_match_minute(run):
    points = [m for m in run[0] if m.get("kind") == "winprob"]
    keys = [(p["period"], p["t_ms"]) for p in points]
    assert keys == sorted(set(keys))
    assert all(p["t_ms"] % 60_000 == 0 for p in points)
    assert len(points) >= 90
    assert all(p["team"] == "RFC" for p in points)


def test_a_failing_winprob_point_does_not_stop_the_stream(monkeypatch):
    def broken(snapshot, home, n=4000, seed=None):
        raise KeyError("rates")

    monkeypatch.setattr(live, "winprob_point", broken)
    pub = FakePublisher()
    runner = make_runner(pub)
    runner.send(read_events(DEMO))
    runner.end_run()
    assert runner.publish_errors > 0
    assert any(m.get("kind") == "card_closed" and m["reason"] == "full_time" for m in pub.sent)


def test_slim_snapshots_keep_the_match_id(run):
    snaps = [m for m in run[0] if "subs_left" in m]
    assert all(s["match_id"] == "rfc-cas-0073" for s in snaps)
