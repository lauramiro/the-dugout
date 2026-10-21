"""MCP server: the state engine, the decision engine and the narration agents as tools.

Mounted on the decision service at /mcp (Streamable HTTP, stateless, JSON responses), so any MCP
client (GitHub Copilot agent mode, a Foundry agent, Claude, the MCP Inspector) can ask what the
demo match looks like at a minute, what each option is worth there, and for a grounded card in
English or Spanish. Docs: https://modelcontextprotocol.io/docs/learn/server-concepts

The tools read the recorded demo match (seed 73) through the same state engine and triggers as
the live pipeline. Numbers come from the engine; text comes from the narration workflow and its
grounding check, exactly as on screen. Cards opened by the live pipeline are served too.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp_types import ToolAnnotations

from dugout.engine.payload import decide
from dugout.service.cards import CardService
from dugout.stream.replay import read_events
from dugout.stream.snapshots import lineup_from_scenario, process

ROOT = Path(__file__).resolve().parents[2]
DEMO_EVENTS = ROOT / "data" / "demo-rfc-cas-0073.jsonl"
SCENARIO = ROOT / "scenarios" / "riverside-castleton.yaml"
MIN_MS = 60_000
HALF_MIN = 45

Locale = Literal["en", "es"]
Mode = Literal["casual", "analyst"]
READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)

server = MCPServer(
    name="the-dugout",
    title="The Dugout",
    instructions=(
        "Explains a football manager's substitution decisions on a synthetic match (fictional "
        "clubs Riverside FC and Castleton Athletic). Start with match_overview, then match_state "
        "or price_options at a minute, and explain_decision for a narrated card. Win probabilities "
        "are model estimates, not predictions; nothing here is about betting."
    ),
)


@cache
def _demo() -> dict[str, Any]:
    """Snapshots and decision points of the demo match, from the state engine and the triggers."""
    events = list(read_events(DEMO_EVENTS))
    records = list(process(events, lineup_from_scenario(SCENARIO)))
    return {
        "events": events,
        "snapshots": [r["snapshot"] for r in records if r["kind"] == "snapshot"],
        "points": {r["id"]: r for r in records if r["kind"] == "decision_point"},
    }


def _cards() -> CardService:
    from dugout.service.app import get_cards  # the service's own card store and narrator

    return get_cards()


def _snapshot_at(minute: int, period: int | None) -> dict[str, Any]:
    period = period or (1 if minute < HALF_MIN else 2)
    t_ms = minute * MIN_MS
    earlier = [s for s in _demo()["snapshots"] if (s["period"], s["t_ms"]) <= (period, t_ms)]
    if not earlier:
        raise ValueError(f"no snapshot at {minute}' in period {period}")
    return earlier[-1]


def _team(snapshot: dict, team: str) -> str:
    team = team.upper()
    if team not in snapshot["score"]:
        raise ValueError(f"team must be one of {sorted(snapshot['score'])}, not {team!r}")
    return team


def _clock(period: int, t_ms: int) -> str:
    return f"{t_ms // MIN_MS}' (half {period})"


@server.tool(annotations=READ_ONLY)
def match_overview() -> dict[str, Any]:
    """The demo match: clubs, final score, goals, substitutions and every decision point the
    triggers raised (condition drop, goal after 55', manager substitution)."""
    demo = _demo()
    events, last = demo["events"], demo["snapshots"][-1]
    return {
        "match_id": last["match_id"],
        "synthetic": True,
        "final_score": last["score"],
        "goals": [{"clock": _clock(e["period"], e["t_ms"]), "team": e["team"], "player_id": e["player_id"]}
                  for e in events if e["type"] == "goal"],
        "substitutions": [{"clock": _clock(e["period"], e["t_ms"]), "team": e["team"], "kind": e["outcome"],
                           "off": e["player_id"], "on": e["player_in_id"]}
                          for e in events if e["type"] == "sub"],
        "decision_points": [{"decision_id": p["id"], "clock": _clock(p["period"], p["t_ms"]),
                             "minute": p["t_ms"] // MIN_MS, "period": p["period"], "team": p["team"],
                             "trigger": p["trigger"], "detail": p["detail"]}
                            for p in demo["points"].values()],
    }


@server.tool(annotations=READ_ONLY)
def match_state(minute: int, period: int | None = None) -> dict[str, Any]:
    """What a club could observe at a minute of the demo match: score, substitutions and windows
    left, scoring rates per 90, and each outfield player's condition estimate (0 to 1) with its
    trend per minute. Period defaults to 1 before 45' and 2 from 45'."""
    s = _snapshot_at(minute, period)
    return {
        "clock": _clock(s["period"], s["t_ms"]),
        "score": s["score"],
        "subs_left": s["subs_left"],
        "windows_left": s["windows_left"],
        "rates_per_90": s["rates"],
        "players": [{"id": p["id"], "team": p["team"], "role": p["role"], "condition_est": p["condition_est"],
                     "trend_per_min": p["trend_per_min"]}
                    for p in s["players"] if p["condition_est"] is not None],
    }


@server.tool(annotations=READ_ONLY)
def price_options(minute: int, team: str, period: int | None = None) -> dict[str, Any]:
    """The decision engine at a minute of the demo match, for one team (RFC or CAS): win, draw
    and loss probability and expected points for no change, a like-for-like substitution, an
    attacking and a defensive change, each option's gap to no change with a 90% interval, the
    recommended option with its strength (strong, lean or toss-up) and the evidence. 20,000
    simulated runs per option on common random numbers."""
    s = _snapshot_at(minute, period)
    return decide(s, _team(s, team), "manager_sub")


@server.tool(annotations=READ_ONLY)
def explain_decision(decision_id: str, locale: Locale = "en",
                     mode: Mode = "casual") -> dict[str, Any]:
    """A narrated decision card: the engine's payload plus a headline and reason written by the
    narration agents (Microsoft Agent Framework on Foundry when configured) and passed by the
    grounding check, which verifies every number against the payload. `source` says whether the
    text came from the model or from the template fallback. decision_id is one from
    match_overview, or a card the live pipeline opened. casual is plain words; analyst adds
    decimals and the interval."""
    cards = _cards()
    if cards.payload(decision_id) is None:
        point = _demo()["points"].get(decision_id)
        if point is None:
            raise ValueError(f"unknown decision_id {decision_id!r}; see match_overview")
        cards.open(point["snapshot"], point["team"], point["trigger"], decision_id)
    return cards.card(decision_id, locale, mode)
