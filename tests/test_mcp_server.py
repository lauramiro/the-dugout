"""MCP server tools, in process and over the service's /mcp route."""
import asyncio

import pytest
from fastapi.testclient import TestClient
from mcp import Client

from dugout.agents.grounding import Narration, check_narration
from dugout.agents.pipeline import NarrationPipeline, StubClient
from dugout.service import mcp_server
from dugout.service.app import app
from dugout.service.cards import CardService
from dugout.service.store import MemoryStore
from dugout.engine.payload import decide

TOOLS = {"match_overview", "match_state", "price_options", "explain_decision"}


@pytest.fixture
def cards(monkeypatch):
    service = CardService(lambda s, team, trigger, **kw: decide(s, team, trigger, n=2_000, **kw),
                          NarrationPipeline(StubClient()), MemoryStore())
    monkeypatch.setattr(mcp_server, "_cards", lambda: service)
    return service


def call(name: str, args: dict | None = None):
    async def go():
        async with Client(mcp_server.server) as client:
            return await client.call_tool(name, args or {})
    return asyncio.run(go())


def data(result) -> dict:
    assert not result.is_error, result.content
    out = result.structured_content
    return out.get("result", out)


def test_tools_are_listed_read_only():
    async def go():
        async with Client(mcp_server.server) as client:
            return await client.list_tools()
    tools = asyncio.run(go()).tools
    assert {t.name for t in tools} == TOOLS
    assert all(t.annotations.read_only_hint for t in tools)
    assert all(t.description for t in tools)


def test_overview_lists_the_demo_match_and_its_decision_points():
    out = data(call("match_overview"))
    assert out["match_id"] == "rfc-cas-0073" and out["synthetic"] is True
    assert out["final_score"] == {"RFC": 3, "CAS": 2}
    assert len(out["goals"]) == 5 and len(out["substitutions"]) == 3
    assert out["decision_points"] and all(p["team"] in ("RFC", "CAS") for p in out["decision_points"])


def test_state_at_a_minute_is_the_last_snapshot_before_it():
    out = data(call("match_state", {"minute": 64}))
    assert out["clock"] == "64' (half 2)"
    rfc03 = next(p for p in out["players"] if p["id"] == "RFC-03")
    assert 0 < rfc03["condition_est"] < 1


def test_price_options_runs_the_engine():
    out = data(call("price_options", {"minute": 64, "team": "rfc"}))
    assert out["team"] == "RFC" and out["options"][0]["id"] == "no_change"
    assert out["recommendation"]["strength"] in ("strong", "lean", "toss_up")
    assert out["trigger"] == "on_request"  # asked by an agent, not raised by a trigger or a substitution


def test_price_options_refuses_an_unknown_team():
    assert call("price_options", {"minute": 64, "team": "XYZ"}).is_error


@pytest.mark.parametrize("locale", ["en", "es"])
def test_explain_decision_opens_a_demo_point_and_returns_a_grounded_card(cards, locale):
    point = data(call("match_overview"))["decision_points"][0]
    out = data(call("explain_decision", {"decision_id": point["decision_id"], "locale": locale, "mode": "analyst"}))
    assert (out["decision_id"], out["locale"], out["mode"]) == (point["decision_id"], locale, "analyst")
    assert check_narration(Narration(out["headline"], out["reason"]), out["payload"], locale) == []
    assert cards.payload(point["decision_id"]) is not None


def test_explain_decision_refuses_an_unknown_id(cards):
    assert call("explain_decision", {"decision_id": "nope"}).is_error


def test_explain_decision_refuses_an_unknown_locale(cards):
    assert call("explain_decision", {"decision_id": "x", "locale": "fr"}).is_error


def test_mcp_route_answers_initialize_and_leaves_the_service_routes_alone():
    body = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                       "clientInfo": {"name": "test", "version": "0"}}}
    headers = {"Accept": "application/json, text/event-stream", "Host": "dugout.example.azurecontainerapps.io"}
    with TestClient(app) as client:
        res = client.post("/mcp", json=body, headers=headers)
        assert res.status_code == 200, res.text
        assert res.json()["result"]["serverInfo"]["name"] == "the-dugout"
        assert client.get("/healthz").json()["ok"] is True


def test_explain_decision_carries_the_decision_card_app():
    # MCP Apps: hosts that support it render ui://the-dugout/decision-card.html with the tool's
    # result; other clients get the same JSON as before.
    async def go():
        async with Client(mcp_server.server) as client:
            tools = (await client.list_tools()).tools
            read = await client.read_resource("ui://the-dugout/decision-card.html")
            return tools, read
    tools, read = asyncio.run(go())
    explain = next(t for t in tools if t.name == "explain_decision")
    assert explain.meta["ui"]["resourceUri"] == "ui://the-dugout/decision-card.html"
    assert explain.annotations.read_only_hint
    (page,) = read.contents
    assert page.mime_type == "text/html;profile=mcp-app"
    for step in ("ui/initialize", "ui/notifications/initialized", "ui/notifications/tool-result",
                 "ui/notifications/size-changed"):
        assert step in page.text


def test_explain_decision_gives_the_app_what_it_shows(cards, monkeypatch):
    monkeypatch.delenv("FOUNDRY_ENDPOINT", raising=False)
    # What the decision card reads beyond the card itself: names for the ids in the text, who
    # wrote the words, and the minute as the screens show it.
    point = data(call("match_overview"))["decision_points"][0]
    out = data(call("explain_decision", {"decision_id": point["decision_id"]}))
    for key in ("payload", "headline", "reason", "locale", "mode", "source"):
        assert key in out
    assert out["names"]["RFC-03"] == "Leon Varga" and out["names"]["CAS-01"]
    assert out["narrated_by"] == "templates"  # no FOUNDRY_ENDPOINT in the tests
    assert out["clock"] == f"{point['minute']}'"


@pytest.mark.parametrize("period, t_ms, label", [
    (1, 2_640_000, "44'"), (1, 2_700_000, "45'"), (1, 2_790_000, "45+2'"),
    (2, 3_630_000, "60'"), (2, 5_460_000, "90+2'"), (None, 5_460_000, "91'"),
])
def test_minute_labels_match_the_screens(period, t_ms, label):
    assert mcp_server.minute_label(period, t_ms) == label


def test_price_options_carries_the_card_app_too():
    # A bare engine payload: the App shows the options without narration.
    async def go():
        async with Client(mcp_server.server) as client:
            return (await client.list_tools()).tools
    tool = next(t for t in asyncio.run(go()) if t.name == "price_options")
    assert tool.meta["ui"]["resourceUri"] == mcp_server.CARD_APP
    out = data(call("price_options", {"minute": 64, "team": "RFC"}))
    assert out["clock"] == "64'" and out["names"]["RFC-03"] == "Leon Varga"
    assert out["options"] and out["recommendation"]


def test_explain_decision_on_a_lost_card_says_unknown(cards, monkeypatch):
    point = data(call("match_overview"))["decision_points"][0]
    monkeypatch.setattr(cards, "card", lambda *a, **k: None)
    result = call("explain_decision", {"decision_id": point["decision_id"]})
    assert result.is_error and "unknown decision_id" in str(result.content)


def test_overview_clock_uses_the_screens_minute():
    assert mcp_server._clock(1, 2_790_000) == "45+2' (half 1)"
    assert mcp_server._clock(2, 3_840_000) == "64' (half 2)"


def test_anticipated_errors_reach_the_agent_with_their_message():
    # ToolError, not ValueError: the SDK hides any other exception's message from the client.
    assert "team must be one of" in str(call("price_options", {"minute": 64, "team": "XYZ"}).content)
    assert "see match_overview" in str(call("explain_decision", {"decision_id": "rfc-1-99"}).content)
