"""Event contract shared by the simulator, the state engine and the UI.

See docs/data-contracts.md for all four shapes and their conventions.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

EVENT_TYPES = frozenset(
    {"pass", "carry", "duel", "press", "shot", "goal", "foul", "card", "out",
     "restart", "sub", "sprint", "hsr"}
)
RUNNING_TYPES = frozenset({"sprint", "hsr"})
OPTIONAL_FIELDS = ("dist_m", "player_in_id")  # left out of the JSON when null
CHANNELS = ("left", "centre", "right")
PITCH_LENGTH = 105.0
PITCH_WIDTH = 68.0


@dataclass(frozen=True, slots=True)
class Event:
    match_id: str
    seq: int
    t_ms: int
    period: int
    type: str
    team: str
    player_id: str | None = None
    channel: str | None = None
    x: float | None = None
    y: float | None = None
    end_x: float | None = None
    end_y: float | None = None
    outcome: str | None = None
    xg: float | None = None
    dist_m: float | None = None  # running events only; left out of the JSON when null
    player_in_id: str | None = None  # sub only (player_id is the player going off); left out when null

    def __post_init__(self) -> None:
        if self.type not in EVENT_TYPES:
            raise ValueError(f"unknown event type: {self.type}")
        if self.channel is not None and self.channel not in CHANNELS:
            raise ValueError(f"unknown channel: {self.channel}")
        if self.dist_m is not None and self.type not in RUNNING_TYPES:
            raise ValueError(f"dist_m is only for {sorted(RUNNING_TYPES)} events")
        if self.player_in_id is not None and self.type != "sub":
            raise ValueError("player_in_id is only for sub events")

    def to_dict(self) -> dict:
        d = asdict(self)
        for key in OPTIONAL_FIELDS:
            if d[key] is None:
                del d[key]
        return d
