"""Observable match state from the event stream, as a snapshot every 10 s (contract 3).

Fed contract-1 event dicts one at a time in `seq` order, plus a lineup: one dict per
squad player with `id`, `team`, `role`, `side` and `starting`. Nothing else about a
player is known here, and this module never imports the simulator.

A snapshot at `(period, t_ms)` is the state at that instant: it covers every event
of the period with a smaller `t_ms`. Snapshots run every 10 s from each period's
kick-off; a period's last one is the first boundary after its last event, so it
covers the whole period. Windows such as "the last 10 minutes" are measured on a
played clock that runs on from the first half's last snapshot into the second half,
so first-half added time is neither lost nor counted twice.
"""

from __future__ import annotations

from dataclasses import dataclass, field

HALF_MS = 45 * 60 * 1000  # second-half kick-off, match clock
SNAPSHOT_MS = 10_000
MAX_SUBS, MAX_WINDOWS = 5, 3
MIN_MS = 60_000

# Scoring rates: weight on the rolling rate grows with played time up to RATE_W_MAX at 90'.
RATE_WINDOW_MS = 20 * MIN_MS
RATE_W_MAX = 0.6


@dataclass
class _Player:
    id: str
    team: str
    role: str
    side: str
    on_pitch: bool
    on_since: int | None  # played ms when he came on
    hsr: list[tuple[int, float]] = field(default_factory=list)  # (played ms, metres)
    sprints: list[int] = field(default_factory=list)  # played ms


class StateEngine:
    def __init__(self, lineup: list[dict], prior90: float = 1.35) -> None:
        self.prior90 = prior90
        self.players = {p["id"]: _Player(p["id"], p["team"], p["role"], p["side"],
                                         bool(p["starting"]), 0 if p["starting"] else None)
                        for p in lineup}
        self.teams = list(dict.fromkeys(p["team"] for p in lineup))
        self.match_id: str | None = None
        self.score = dict.fromkeys(self.teams, 0)
        self.subs_used = dict.fromkeys(self.teams, 0)
        self.windows: dict[str, set] = {t: set() for t in self.teams}  # in-play (period, t_ms)
        self.shots: list[tuple[int, int, str, str, float]] = []  # (played, period, team, channel, xg)
        self._seq: int | None = None
        self._period: int | None = None
        self._last_t = 0
        self._next_t = 0
        self._offset = 0  # played ms at this period's kick-off, minus its kick-off t_ms
        self._kicked_off = False
        self._pending: list[dict] = []

    # --- clock ----------------------------------------------------------------

    def played(self, t_ms: int) -> int:
        """Played ms for a match-clock time in the current period."""
        return self._offset + t_ms

    # --- feeding --------------------------------------------------------------

    def feed(self, event: dict) -> list[tuple[dict, list[dict]]]:
        """Take one event; return the (snapshot, events since the previous snapshot)
        pairs for every 10 s boundary passed before it."""
        if self._seq is not None and event["seq"] <= self._seq:
            raise ValueError(f"events must come in seq order: {event['seq']} after {self._seq}")
        self._seq = event["seq"]
        self.match_id = self.match_id or event.get("match_id")
        out = []
        period, t = event["period"], event["t_ms"]
        if self._period is None:
            self._start_period(period, played_start=0)
        elif period != self._period:
            out += self._close_period()
            self._start_period(period, played_start=self.played(self._next_t - SNAPSHOT_MS))
        out += self._emit_until(t)
        self._apply(event)
        self._last_t = t
        self._pending.append(event)
        return out

    def finish(self) -> list[tuple[dict, list[dict]]]:
        """End of the stream: close the current period."""
        return self._close_period() if self._period is not None else []

    def _start_period(self, period: int, played_start: int) -> None:
        kickoff = 0 if period == 1 else HALF_MS
        self._period, self._next_t, self._last_t = period, kickoff, kickoff
        self._offset = played_start - kickoff
        self._kicked_off = False

    def _close_period(self) -> list[tuple[dict, list[dict]]]:
        out = self._emit_until(self._last_t)
        out.append(self._emit())
        return out

    def _emit_until(self, t: int) -> list[tuple[dict, list[dict]]]:
        out = []
        while self._next_t <= t:
            out.append(self._emit())
        return out

    def _emit(self) -> tuple[dict, list[dict]]:
        snap = self.snapshot(self._next_t)
        events, self._pending = self._pending, []
        self._next_t += SNAPSHOT_MS
        return snap, events

    def _apply(self, e: dict) -> None:
        kind, team = e["type"], e["team"]
        if kind == "goal":
            self.score[team] += 1
        elif kind == "sub":
            self._sub(e)
        elif kind == "restart":
            self._kicked_off = True
        elif kind == "shot" and e.get("xg") is not None:
            self.shots.append((self.played(e["t_ms"]), e["period"], team, e["channel"], e["xg"]))

    def _sub(self, e: dict) -> None:
        team = e["team"]
        off, on = self.players[e["player_id"]], self.players[e["player_in_id"]]
        off.on_pitch = False
        on.on_pitch, on.on_since = True, self.played(e["t_ms"])
        self.subs_used[team] += 1
        half_time = e["period"] == 2 and e["t_ms"] == HALF_MS and not self._kicked_off
        if not half_time:
            self.windows[team].add((e["period"], e["t_ms"]))

    # --- snapshot -------------------------------------------------------------

    def snapshot(self, t_ms: int) -> dict:
        return {
            "match_id": self.match_id,
            "t_ms": t_ms,
            "period": self._period,
            "score": dict(self.score),
            "subs_left": {t: MAX_SUBS - self.subs_used[t] for t in self.teams},
            "windows_left": {t: MAX_WINDOWS - len(self.windows[t]) for t in self.teams},
            "rates": self._rates(self.played(t_ms)),
            "players": [self._player_dict(p) for p in self.players.values() if p.on_pitch],
            "threat_by_channel": {},
        }

    def _rates(self, now: int) -> dict:
        """Prior blended with each team's rolling xG for and against over the last 20 minutes."""
        span = min(now, RATE_WINDOW_MS)
        w = RATE_W_MAX * min(now, 90 * MIN_MS) / (90 * MIN_MS) if span >= MIN_MS else 0.0
        xg = dict.fromkeys(self.teams, 0.0)
        for played, _, team, _, x in self.shots:
            if now - RATE_WINDOW_MS <= played < now:
                xg[team] += x
        per90 = {t: xg[t] / span * 90 * MIN_MS if span else 0.0 for t in self.teams}

        def blend(rolling: float) -> float:
            return round(w * rolling + (1 - w) * self.prior90, 2)

        return {t: {"for90": blend(per90[t]),
                    "against90": blend(sum(v for u, v in per90.items() if u != t))}
                for t in self.teams}

    def _player_dict(self, p: _Player) -> dict:
        outfield = p.role != "GK"
        return {"id": p.id, "role": p.role,
                "condition_est": 1.0 if outfield else None,
                "condition_band": [1.0, 1.0] if outfield else None,
                "trend_per_min": 0.0}
