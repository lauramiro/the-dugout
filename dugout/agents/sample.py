"""Sample decision payloads (contract 4) for tests and the local stub client."""

from __future__ import annotations

import copy

SAMPLE_PAYLOAD: dict = {
    "decision_id": "rfc-62-01",
    "t_ms": 3720000,
    "team": "RFC",
    "trigger": "condition_below_60",
    "options": [
        {"id": "no_change", "label": "No change", "win": 0.687, "draw": 0.240,
         "loss": 0.073, "xpts": 2.30, "delta_win": 0.0},
        {"id": "sub_lb", "label": "Replace left-back (RFC-03 for RFC-15)",
         "win": 0.726, "draw": 0.217, "loss": 0.057, "xpts": 2.39,
         "delta_win": 0.039, "ci90": [0.021, 0.057]},
    ],
    "recommendation": {"option_id": "sub_lb", "strength": "strong"},
    "evidence": [
        {"type": "condition", "player_id": "RFC-03", "value": 0.60, "trend_per_min": -0.008},
        {"type": "flank_threat", "channel": "RFC_left", "share": 0.41},
    ],
    "manager_action": None,
}


def toss_up_payload() -> dict:
    """The sample payload with a gap under one point and a toss-up label."""
    payload = copy.deepcopy(SAMPLE_PAYLOAD)
    option = payload["options"][1]
    option.update(win=0.691, draw=0.238, loss=0.071, xpts=2.31,
                  delta_win=0.004, ci90=[-0.012, 0.020])
    payload["recommendation"]["strength"] = "toss_up"
    return payload
