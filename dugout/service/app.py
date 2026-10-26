"""Decision service: snapshot and decision point in, narrated card out, pushed through Web PubSub.

    uvicorn dugout.service.app:app --port 8000

Settings (environment): WEBPUBSUB_CONNECTION_STRING, WEBPUBSUB_HUB (default "decisions"),
STUB_CORS_ORIGINS (comma separated, default "*"; named after the first walking-skeleton
service, kept so the deployed setting carries over), DECISIONS_TOKEN (the bearer token
POST /decisions requires; without it the route is off, since a card it opens goes to every
open page). Without a connection string the push is skipped and reported as such.
Narration goes through Foundry when FOUNDRY_ENDPOINT is set, else the stub client. The MCP
server (dugout.service.mcp_server) is mounted at /mcp.
"""

from __future__ import annotations

import hmac
import os
import re
from collections import Counter
from contextlib import asynccontextmanager
from functools import cache
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from dugout.agents.foundry import ENV_ENDPOINT, ENV_MODEL
from dugout.engine.options import default_options
from dugout.service.cards import CardService, default_service
from dugout.service.mcp_server import server as mcp_server
from dugout.service.publisher import Publisher, default_publisher
from dugout.service.store import StoreFull

Locale = Literal["en", "es"]
Mode = Literal["casual", "analyst"]


class DecisionRequest(BaseModel):
    snapshot: dict
    team: str
    trigger: str
    decision_id: str | None = None  # the decision point's id; derived from the clock when absent
    locale: Locale = "en"
    mode: Mode = "casual"


# Votes are kept in memory, so ids are bounded; the page's viewer id is a 36-character UUID.
Id = Field(min_length=1, max_length=64)


class VoteRequest(BaseModel):
    decision_id: str = Id
    viewer_id: str = Id
    option_id: str = Id


# Stateless with JSON responses, so any replica can answer any request (Container Apps scales
# to zero and out). The Host check is for servers bound to localhost; this one sits behind ingress.
mcp_app = mcp_server.streamable_http_app(streamable_http_path="/mcp", stateless_http=True,
                                         json_response=True, host="0.0.0.0")


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with mcp_server.session_manager.run():
        yield


app = FastAPI(title="dugout decision service", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("STUB_CORS_ORIGINS", "*").split(","),
    allow_methods=["GET", "POST"],
)


@cache
def get_cards() -> CardService:
    return default_service()


@cache
def _publisher() -> Publisher | None:
    return default_publisher()


def get_publisher() -> Publisher | None:
    return _publisher()


@app.get("/healthz")
def healthz(publisher: Publisher | None = Depends(get_publisher)) -> dict:
    """Up, plus what the service runs on (names only, never endpoints or keys)."""
    foundry = bool(os.environ.get(ENV_ENDPOINT))
    return {"ok": True,
            "narration": "foundry" if foundry else "templates",
            "model": os.environ.get(ENV_MODEL) if foundry else None,
            "push": "web_pubsub" if publisher is not None else "off",
            "decisions_route": "on" if os.environ.get("DECISIONS_TOKEN") else "off",
            "mcp": "/mcp"}


@app.get("/negotiate")
def negotiate(publisher: Publisher | None = Depends(get_publisher)) -> dict:
    """Short-lived WebSocket URL for the browser (the static site has no server of its own)."""
    if publisher is None:
        return {"url": None}
    return {"url": publisher.client_url()}


def require_write_token(authorization: str | None = Header(default=None)) -> None:
    """POST /decisions publishes to every viewer, so it needs DECISIONS_TOKEN as a bearer token.
    The deployed runner opens decisions in process and never calls the route."""
    token = os.environ.get("DECISIONS_TOKEN")
    if not token:
        raise HTTPException(403, "opening decisions over HTTP is off (DECISIONS_TOKEN not set)")
    if not hmac.compare_digest((authorization or "").encode(), f"Bearer {token}".encode()):
        raise HTTPException(401, "missing or wrong bearer token")


@app.post("/decisions", dependencies=[Depends(require_write_token)])
def open_decision(req: DecisionRequest, cards: CardService = Depends(get_cards),
                  publisher: Publisher | None = Depends(get_publisher)) -> dict:
    """Run the engine for the team's decision point and publish its card in the requested
    locale and mode. Other locales and modes are narrated on first GET."""
    for key in ("rates", "score"):
        if req.team not in req.snapshot.get(key, {}):
            raise HTTPException(422, f"team {req.team!r} is not in snapshot[{key!r}]")
    return open_and_publish(cards, publisher, req)


def open_and_publish(cards: CardService, publisher: Publisher | None, req: DecisionRequest) -> dict:
    """What POST /decisions does, callable without HTTP (the pipeline runner uses it in process)."""
    payload = cards.open(req.snapshot, req.team, req.trigger, req.decision_id)
    card = cards.card(payload["decision_id"], req.locale, req.mode)
    if publisher is None:
        return {"pushed": False, "reason": "WEBPUBSUB_CONNECTION_STRING not set", "card": card}
    publisher.publish(card)
    return {"pushed": True, "card": card}


@app.get("/decisions/{decision_id}")
def get_decision(decision_id: str, locale: Locale = "en", mode: Mode = "casual",
                 cards: CardService = Depends(get_cards)) -> dict:
    card = cards.card(decision_id, locale, mode)
    if card is None:
        raise HTTPException(404, "unknown decision")
    return card


# Decision ids as the triggers and the engine write them: club, minute, two-digit sequence.
DECISION_ID = re.compile(r"[a-z]{2,4}-\d{1,3}-\d{2}")
ENGINE_OPTIONS = frozenset(o.id for o in default_options(0))


def _vote_options(cards: CardService, decision_id: str) -> tuple[frozenset[str], bool]:
    """The options a vote may name, and whether the service knows the card. The live runner
    opens decisions in its own process, so the service often has no payload for a live card;
    then any of the engine's options counts."""
    payload = cards.payload(decision_id)
    if payload is not None:
        return frozenset(o["id"] for o in payload["options"]), True
    if DECISION_ID.fullmatch(decision_id):
        return ENGINE_OPTIONS, False
    raise HTTPException(404, "unknown decision")


@app.post("/votes")
def cast_vote(req: VoteRequest, cards: CardService = Depends(get_cards)) -> dict:
    options, known = _vote_options(cards, req.decision_id)
    if req.option_id not in options:
        raise HTTPException(422, f"unknown option {req.option_id!r}")
    # A live card's id comes back with each half-hourly replay of the demo match, so a vote
    # again replaces the viewer's earlier one; on a card the service opened, the first stands.
    try:
        added = cards.store.add_vote(req.decision_id, req.viewer_id, req.option_id, replace=not known)
    except StoreFull as err:
        raise HTTPException(503, str(err)) from err
    if not added:
        raise HTTPException(409, "viewer already voted on this decision")
    return _tally(cards, req.decision_id)


@app.get("/votes/{decision_id}")
def get_votes(decision_id: str, cards: CardService = Depends(get_cards)) -> dict:
    _vote_options(cards, decision_id)
    return _tally(cards, decision_id)


def _tally(cards: CardService, decision_id: str) -> dict:
    counts = Counter(cards.store.votes(decision_id).values())
    return {"decision_id": decision_id, "counts": dict(sorted(counts.items())),
            "total": sum(counts.values())}


# Last, so the service's own routes match first.
app.mount("/", mcp_app)
