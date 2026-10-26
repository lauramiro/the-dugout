"""Service endpoints, with a fake publisher and an in-memory store."""
import pytest
from fastapi.testclient import TestClient

from dugout.agents.pipeline import NarrationPipeline, StubClient
from dugout.agents.sample import SAMPLE_PAYLOAD
from dugout.service.app import app, get_cards, get_publisher
from dugout.service.cards import CardService
from dugout.service.store import MemoryStore

SNAPSHOT = {"t_ms": 3_720_000, "score": {"RFC": 1, "CAS": 0},
            "rates": {"RFC": {"for90": 1.5, "against90": 1.2}, "CAS": {"for90": 1.2, "against90": 1.5}}}


class FakePublisher:
    def __init__(self):
        self.sent = []

    def publish(self, payload):
        self.sent.append(payload)

    def client_url(self):
        return "wss://example.invalid/client/hubs/decisions"


TOKEN = "test-token"


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("DECISIONS_TOKEN", TOKEN)
    pub, engine_calls = FakePublisher(), []

    def engine(snapshot, team, trigger):
        engine_calls.append(team)
        return {**SAMPLE_PAYLOAD, "team": team, "trigger": trigger}

    cards = CardService(engine, NarrationPipeline(StubClient()), MemoryStore())
    app.dependency_overrides[get_publisher] = lambda: pub
    app.dependency_overrides[get_cards] = lambda: cards
    yield TestClient(app), pub, engine_calls
    app.dependency_overrides.clear()


def open_decision(client, token=TOKEN, **extra):
    body = {"snapshot": SNAPSHOT, "team": "RFC", "trigger": "condition_drop", **extra}
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post("/decisions", json=body, headers=headers)


def test_post_decisions_returns_and_publishes_the_card(env):
    client, pub, _ = env
    r = open_decision(client)
    assert r.status_code == 200
    body = r.json()
    assert body["pushed"] is True
    card = body["card"]
    assert card["decision_id"] == "rfc-62-01" and card["locale"] == "en" and card["mode"] == "casual"
    assert card["payload"]["recommendation"] == SAMPLE_PAYLOAD["recommendation"]
    assert pub.sent == [card]


def test_post_decisions_without_web_pubsub_still_returns_the_card(env):
    client, _, _ = env
    app.dependency_overrides[get_publisher] = lambda: None
    body = open_decision(client).json()
    assert body["pushed"] is False and body["card"]["decision_id"] == "rfc-62-01"


def test_post_decisions_for_the_away_team(env):
    client, _, calls = env
    assert open_decision(client, team="CAS").status_code == 200
    assert calls == ["CAS"]


def test_post_decisions_rejects_a_team_not_in_the_snapshot(env):
    client, pub, calls = env
    assert open_decision(client, team="XXX").status_code == 422
    assert calls == [] and pub.sent == []


def test_post_decisions_needs_the_write_token(env):
    client, pub, calls = env
    assert open_decision(client, token=None).status_code == 401
    assert open_decision(client, token="wrong").status_code == 401
    assert calls == [] and pub.sent == []


def test_post_decisions_is_off_without_a_configured_token(env, monkeypatch):
    client, pub, calls = env
    monkeypatch.delenv("DECISIONS_TOKEN")
    assert open_decision(client).status_code == 403
    assert calls == [] and pub.sent == []


def test_post_decisions_rejects_an_unsupported_locale(env):
    client, _, _ = env
    assert open_decision(client, locale="fr").status_code == 422


def test_get_decision_serves_other_locales_from_the_cache(env):
    client, _, calls = env
    open_decision(client)
    r = client.get("/decisions/rfc-62-01", params={"locale": "es", "mode": "analyst"})
    assert r.status_code == 200
    assert r.json()["locale"] == "es" and r.json()["mode"] == "analyst"
    assert client.get("/decisions/rfc-62-01", params={"locale": "es", "mode": "analyst"}).json() == r.json()
    assert len(calls) == 1


def test_get_decision_defaults_and_errors(env):
    client, _, _ = env
    assert client.get("/decisions/missing").status_code == 404
    open_decision(client)
    assert client.get("/decisions/rfc-62-01").json()["locale"] == "en"
    assert client.get("/decisions/rfc-62-01", params={"mode": "loud"}).status_code == 422


def vote(client, viewer="v1", option="sub_lb", decision="rfc-62-01"):
    return client.post("/votes", json={"decision_id": decision, "viewer_id": viewer, "option_id": option})


def test_votes_one_per_viewer_and_tally(env):
    client, _, _ = env
    open_decision(client)
    assert vote(client, "v1", "sub_lb").status_code == 200
    assert vote(client, "v2", "no_change").status_code == 200
    assert vote(client, "v3", "sub_lb").status_code == 200
    assert vote(client, "v1", "no_change").status_code == 409
    tally = client.get("/votes/rfc-62-01").json()
    assert tally == {"decision_id": "rfc-62-01", "counts": {"no_change": 1, "sub_lb": 2}, "total": 3}


def test_vote_validation(env):
    client, _, _ = env
    assert vote(client).status_code == 404
    assert client.get("/votes/rfc-62-01").status_code == 404
    open_decision(client)
    assert vote(client, option="made_up").status_code == 422
    assert client.get("/votes/rfc-62-01").json()["total"] == 0
    assert vote(client, viewer="v" * 65).status_code == 422
    assert vote(client, viewer="").status_code == 422


def test_negotiate_and_healthz(env):
    client, _, _ = env
    assert client.get("/negotiate").json() == {"url": "wss://example.invalid/client/hubs/decisions"}
    assert client.get("/healthz").json()["ok"] is True
    app.dependency_overrides[get_publisher] = lambda: None
    assert client.get("/negotiate").json() == {"url": None}


def test_healthz_says_what_the_service_runs_on_without_secrets(env, monkeypatch):
    client, _, _ = env
    monkeypatch.setenv("FOUNDRY_ENDPOINT", "https://secret-host.example")
    monkeypatch.setenv("FOUNDRY_API_KEY", "k3y")
    monkeypatch.setenv("FOUNDRY_MODEL", "gpt-5-mini")
    body = client.get("/healthz").json()
    assert body == {"ok": True, "narration": "foundry", "model": "gpt-5-mini", "push": "web_pubsub",
                    "decisions_route": "on", "mcp": "/mcp"}
    for name in ("FOUNDRY_ENDPOINT", "FOUNDRY_API_KEY", "FOUNDRY_MODEL", "DECISIONS_TOKEN"):
        monkeypatch.delenv(name)
    app.dependency_overrides[get_publisher] = lambda: None
    assert client.get("/healthz").json() == {"ok": True, "narration": "templates", "model": None, "push": "off",
                                             "decisions_route": "off", "mcp": "/mcp"}


def test_post_decisions_uses_the_decision_points_id(monkeypatch):
    monkeypatch.setenv("DECISIONS_TOKEN", TOKEN)
    from dugout.engine.payload import decide
    cards = CardService(lambda s, t, g, **kw: decide(s, t, g, n=2_000, **kw),
                        NarrationPipeline(StubClient()), MemoryStore())
    pub = FakePublisher()
    app.dependency_overrides[get_publisher] = lambda: pub
    app.dependency_overrides[get_cards] = lambda: cards
    try:
        snap = {**SNAPSHOT, "subs_left": {"RFC": 5, "CAS": 5}, "players": [], "threat_by_channel": {}}
        body = {"snapshot": snap, "team": "RFC", "trigger": "manager_sub", "decision_id": "rfc-62-03"}
        headers = {"Authorization": f"Bearer {TOKEN}"}
        card = TestClient(app).post("/decisions", json=body, headers=headers).json()["card"]
    finally:
        app.dependency_overrides.clear()
    assert card["decision_id"] == card["payload"]["decision_id"] == "rfc-62-03"
    assert pub.sent == [card] and cards.payload("rfc-62-03") is not None
