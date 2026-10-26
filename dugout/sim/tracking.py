"""2 Hz tracking frames for drawing the pitch.

Each team holds a formation template that shifts with the ball (up when it has
the ball, back when it does not), and players ease towards their template spot
with a little noise. Speeds come from successive positions. Frames are drawn
from events and observable match state only, never from condition, and are
never an input to the decision engine. Noise comes from a fork of the match
state on a reserved branch, so writing tracking never changes the events.
"""

from __future__ import annotations

import math


from dugout.contracts import PITCH_LENGTH, PITCH_WIDTH, Event
from dugout.sim.match import Y_BANDS, step
from dugout.sim.state import MatchState, Player

TRACKING_BRANCH = 2**32 - 1
FRAME_MS = 500

# Template spots, team-relative: x towards the opponent's goal, y towards the team's left.
TEMPLATE_X = {"GK": 5.0, "CB": 22.0, "FB": 26.0, "CM": 42.0, "W": 58.0, "ST": 64.0}
SIDE_Y = {"left": 52.0, "centre": 34.0, "right": 16.0}
WIDE_Y = {"left": 60.0, "centre": 34.0, "right": 8.0}  # full-backs and wingers
SPREAD_Y = 12.0  # gap between players sharing a role and side
IN_POSSESSION_X, OUT_OF_POSSESSION_X = 8.0, -6.0
# Share of the ball's offset followed in x and in y, and share of the possession push.
FOLLOW = {"GK": (0.1, 0.15, 0.25), "outfield": (0.45, 0.3, 1.0)}
EASE, NOISE_M = 0.3, 0.3
MAX_SPEED = 9.0  # m/s; caps a player's step between frames
BALL_EASE = 0.6


def _attacking_up(s: MatchState, team: str, period: int) -> bool:
    return (team == s.home) == (period == 1)


def _flip(s: MatchState, team: str, period: int, x: float, y: float) -> tuple[float, float]:
    """Team-relative to absolute coordinates, or back: the map is its own inverse."""
    return (x, y) if _attacking_up(s, team, period) else (PITCH_LENGTH - x, PITCH_WIDTH - y)


def _clip(x: float, y: float, margin: float = 0.0) -> tuple[float, float]:
    return (min(PITCH_LENGTH - margin, max(margin, x)), min(PITCH_WIDTH - margin, max(margin, y)))


def _template(players: list[Player]) -> dict[str, tuple[float, float]]:
    groups: dict[tuple[str, str], list[Player]] = {}
    for p in sorted(players, key=lambda p: p.id):
        groups.setdefault((p.role, p.side), []).append(p)
    spots = {}
    for (role, side), ps in groups.items():
        base_y = (WIDE_Y if role in ("FB", "W") else SIDE_Y)[side]
        for i, p in enumerate(ps):
            spots[p.id] = (TEMPLATE_X[role], base_y + (i - (len(ps) - 1) / 2) * SPREAD_Y)
    return spots


class _Tracker:
    def __init__(self, s: MatchState) -> None:
        self.rng = s.fork(TRACKING_BRANCH).rng
        self.pos: dict[str, tuple[float, float]] = {}
        self.ball = (PITCH_LENGTH / 2, PITCH_WIDTH / 2)
        self.period = 0

    def frame(self, s: MatchState, period: int, t_ms: int, on: list[Player],
              ball_target: tuple[float, float], possession: str) -> dict:
        reset = period != self.period
        if reset:
            self.period, self.pos = period, {}
            self.ball = (PITCH_LENGTH / 2, PITCH_WIDTH / 2)
        bx, by = self.ball
        self.ball = (round(bx + BALL_EASE * (ball_target[0] - bx), 1), round(by + BALL_EASE * (ball_target[1] - by), 1))
        noise = self.rng.normal(0.0, NOISE_M, size=(len(on), 2))
        rows = []
        for team in (s.home, s.away):
            ps = [p for p in on if p.team == team]
            spots = _template(ps)
            rbx, rby = _flip(s, team, period, *self.ball)
            push = IN_POSSESSION_X if team == possession else OUT_OF_POSSESSION_X
            for p in ps:
                fx, fy, fp = FOLLOW["GK" if p.role == "GK" else "outfield"]
                tx, ty = spots[p.id]
                tx += fp * push + fx * (rbx - PITCH_LENGTH / 2)
                ty += fy * (rby - PITCH_WIDTH / 2)
                target = _flip(s, team, period, *_clip(tx, ty, margin=1.0))
                rows.append((p.id, target))
        players = []
        for (pid, (tx, ty)), (nx, ny) in zip(rows, noise):
            if reset or pid not in self.pos:
                x, y, v = tx, ty, 0.0
            else:
                px, py = self.pos[pid]
                dx, dy = EASE * (tx - px) + nx, EASE * (ty - py) + ny
                scale = min(1.0, MAX_SPEED * FRAME_MS / 1000 / max(math.hypot(dx, dy), 1e-9))
                x, y = _clip(px + scale * dx, py + scale * dy)
            x, y = round(float(x), 1), round(float(y), 1)
            if pid in self.pos and not reset:
                v = math.dist((x, y), self.pos[pid]) / (FRAME_MS / 1000)
            self.pos[pid] = (x, y)
            players.append({"id": pid, "x": x, "y": y, "v": round(v, 1)})
        self.pos = {p["id"]: self.pos[p["id"]] for p in players}
        return {"match_id": s.match_id, "period": period, "t_ms": t_ms,
                "ball": {"x": self.ball[0], "y": self.ball[1]}, "players": players}


def _zone_target(s: MatchState) -> tuple[float, float]:
    """Centre of the zone the team in possession is playing in, in absolute coordinates."""
    lo, hi = Y_BANDS[s.channel]
    return _flip(s, s.possession, s.period, s.third * 35.0 + 17.5, (lo + hi) / 2)


def _event_target(events: list[Event]) -> tuple[float, float] | None:
    for e in reversed(events):
        if e.end_x is not None:
            return e.end_x, e.end_y
        if e.x is not None:
            return e.x, e.y
    return None


def run_with_tracking(s: MatchState) -> tuple[list[Event], list[dict]]:
    """Play `s` to the end and return its events and 2 Hz tracking frames."""
    tracker = _Tracker(s)
    events: list[Event] = []
    frames: list[dict] = []
    while not s.finished:
        period, t_ms, possession = s.period, s.clock_s * 1000, s.possession
        on = [p for p in s.players.values() if p.on_pitch]
        target = _zone_target(s)
        frames.append(tracker.frame(s, period, t_ms, on, target, possession))
        new = step(s)
        events += new
        if s.period == period:
            on, possession = [p for p in s.players.values() if p.on_pitch], s.possession
        frames.append(tracker.frame(s, period, t_ms + FRAME_MS, on, _event_target(new) or target, possession))
    return events, frames
