"""Stub engine: returns the sample decision payload (contract 4) and pushes it to Web PubSub.

    uvicorn dugout.stub.app:app --port 8000

Settings (environment): WEBPUBSUB_CONNECTION_STRING, WEBPUBSUB_HUB (default "decisions"),
STUB_CORS_ORIGINS (comma separated, default "*"). Without a connection string the
push is skipped and reported as such.
"""

from __future__ import annotations

import os
from copy import deepcopy

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from dugout.service.publisher import Publisher, WebPubSubPublisher, default_publisher  # noqa: F401

SAMPLE_DECISION = {
    "decision_id": "rfc-62-01",
    "t_ms": 3720000,
    "team": "RFC",
    "trigger": "condition_drop",
    "options": [
        {"id": "no_change", "label": "No change", "win": 0.687, "draw": 0.240, "loss": 0.073,
         "xpts": 2.30, "delta_win": 0.0},
        {"id": "sub_lb", "label": "Replace left-back (RFC-03 for RFC-15)", "win": 0.726,
         "draw": 0.217, "loss": 0.057, "xpts": 2.39, "delta_win": 0.039, "ci90": [0.021, 0.057]},
    ],
    "recommendation": {"option_id": "sub_lb", "strength": "strong"},
    "evidence": [
        {"type": "condition", "player_id": "RFC-03", "value": 0.60, "trend_per_min": -0.008},
        {"type": "flank_threat", "channel": "RFC_left", "share": 0.41},
    ],
    "manager_action": None,
}


app = FastAPI(title="dugout stub engine")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("STUB_CORS_ORIGINS", "*").split(","),
    allow_methods=["GET", "POST"],
)


def get_publisher() -> Publisher | None:
    return default_publisher()


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.get("/decision")
def decision() -> dict:
    return deepcopy(SAMPLE_DECISION)


@app.post("/push")
def push(publisher: Publisher | None = Depends(get_publisher)) -> dict:
    payload = deepcopy(SAMPLE_DECISION)
    if publisher is None:
        return {"pushed": False, "reason": "WEBPUBSUB_CONNECTION_STRING not set", "decision": payload}
    publisher.publish(payload)
    return {"pushed": True, "decision": payload}


@app.get("/negotiate")
def negotiate(publisher: Publisher | None = Depends(get_publisher)) -> dict:
    """Short-lived WebSocket URL for the browser (the static site has no server of its own)."""
    if publisher is None:
        return {"url": None}
    return {"url": publisher.client_url()}
