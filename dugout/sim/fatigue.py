"""Hidden fatigue: how a player's condition drains and recovers.

Every match-clock minute each player on the pitch loses a base drain for his
role plus a cost for each high-intensity action he made that minute. Higher
work rate raises the base drain; higher stamina shrinks the whole drain.
Half-time gives a little back. All values are tunable assumptions.
"""

from __future__ import annotations

from dugout.contracts import Event
from dugout.sim.state import MatchState, Player

BASE_DRAIN = {"GK": 0.0008, "CB": 0.0024, "FB": 0.0028, "CM": 0.0028, "W": 0.0028, "ST": 0.0026}
ACTION_COST = {"duel": 0.001, "foul": 0.001}
HALF_TIME_RECOVERY = 0.05
MIN_CONDITION = 0.2


def stamina_factor(p: Player) -> float:
    return 1.0 + 2.5 * (0.78 - p.stamina)


def work_factor(p: Player) -> float:
    return 0.7 + 0.4 * p.work_rate


def add_load(s: MatchState, events: list[Event]) -> None:
    """Record this second's high-intensity actions against the players who made them."""
    for e in events:
        cost = ACTION_COST.get(e.type)
        if cost and e.player_id:
            s.load[e.player_id] = s.load.get(e.player_id, 0.0) + cost


def drain_minute(s: MatchState) -> None:
    for p in s.players.values():
        if p.on_pitch:
            drain = (BASE_DRAIN[p.role] * work_factor(p) + s.load.get(p.id, 0.0)) * stamina_factor(p)
            p.condition = max(MIN_CONDITION, p.condition - drain)
    s.load.clear()


def half_time(s: MatchState) -> None:
    for p in s.players.values():
        if p.on_pitch:
            p.condition = min(1.0, p.condition + HALF_TIME_RECOVERY)
