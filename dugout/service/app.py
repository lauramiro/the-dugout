"""Decision service: snapshot and decision point in, narrated card out, pushed through Web PubSub.

    uvicorn dugout.service.app:app --port 8000

Settings (environment): WEBPUBSUB_CONNECTION_STRING, WEBPUBSUB_HUB (default "decisions"),
STUB_CORS_ORIGINS (comma separated, default "*"; same name as the stub so the deployed
setting carries over). Without a connection string the push is skipped and reported as such.
The model client is still the stub until Foundry is set up.
"""

from __future__ import annotations

import os
from collections import Counter
from functools import cache
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from dugout.service.cards import CardService, default_service
from dugout.service.publisher import Publisher, default_publisher

Locale = Literal["en", "es", "ca"]
Mode = Literal["casual", "analyst"]


class DecisionRequest(BaseModel):
    snapshot: dict
    team: str
    trigger: str
    locale: Locale = "en"
    mode: Mode = "casual"


class VoteRequest(BaseModel):
    decision_id: str
    viewer_id: str
    option_id: str


app = FastAPI(title="dugout decision service")
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
def healthz() -> dict:
    return {"ok": True}


@app.get("/negotiate")
def negotiate(publisher: Publisher | None = Depends(get_publisher)) -> dict:
    """Short-lived WebSocket URL for the browser (the static site has no server of its own)."""
    if publisher is None:
        return {"url": None}
    return {"url": publisher.client_url()}


@app.post("/decisions")
def open_decision(req: DecisionRequest, cards: CardService = Depends(get_cards),
                  publisher: Publisher | None = Depends(get_publisher)) -> dict:
    """Run the engine for the team's decision point and publish its card in the requested
    locale and mode. Other locales and modes are narrated on first GET."""
    for key in ("rates", "score"):
        if req.team not in req.snapshot.get(key, {}):
            raise HTTPException(422, f"team {req.team!r} is not in snapshot[{key!r}]")
    payload = cards.open(req.snapshot, req.team, req.trigger)
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


@app.post("/votes")
def cast_vote(req: VoteRequest, cards: CardService = Depends(get_cards)) -> dict:
    payload = cards.payload(req.decision_id)
    if payload is None:
        raise HTTPException(404, "unknown decision")
    if req.option_id not in {o["id"] for o in payload["options"]}:
        raise HTTPException(422, f"unknown option {req.option_id!r}")
    if not cards.store.add_vote(req.decision_id, req.viewer_id, req.option_id):
        raise HTTPException(409, "viewer already voted on this decision")
    return _tally(cards, req.decision_id)


@app.get("/votes/{decision_id}")
def get_votes(decision_id: str, cards: CardService = Depends(get_cards)) -> dict:
    if cards.payload(decision_id) is None:
        raise HTTPException(404, "unknown decision")
    return _tally(cards, decision_id)


def _tally(cards: CardService, decision_id: str) -> dict:
    counts = Counter(cards.store.votes(decision_id).values())
    return {"decision_id": decision_id, "counts": dict(sorted(counts.items())),
            "total": sum(counts.values())}
