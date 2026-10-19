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

import math
from bisect import bisect_left
from dataclasses import dataclass, field

HALF_MS = 45 * 60 * 1000  # second-half kick-off, match clock
SNAPSHOT_MS = 10_000
MAX_SUBS, MAX_WINDOWS = 5, 3
MIN_MS = 60_000

# Scoring rates: weight on the rolling rate grows with played time up to RATE_W_MAX at 90'.
RATE_WINDOW_MS = 20 * MIN_MS
RATE_W_MAX = 0.6

# Condition estimate: high-speed running per in-play minute against the player's own first
# 20 minutes on the pitch, hsr metres weighted above sprint counts. Running is taken to fall
# faster than condition, so the smoothed ratio is raised to COND_EXP. Assumptions, not fitted.
BASELINE_MS = 20 * MIN_MS
RECENT_MS = 10 * MIN_MS
HSR_WEIGHT = 0.7
EW_TAU_MS = 15 * MIN_MS
COND_EXP = 2 / 3
COND_MIN, COND_MAX = 0.3, 1.0
TREND_MS = 5 * MIN_MS
BAND_HALF = 0.08
LOW_SPRINT_ROLES = frozenset({"CB", "CM"})
LOW_SPRINT_BAND = 1.5  # band multiplier where sprints say little
DEAD_BALL = frozenset({"foul", "out", "goal"})
DEAD_SHOT = frozenset({"off_target", "saved"})  # goal kick, keeper's ball or corner


@dataclass
class _Player:
    id: str
    team: str
    role: str
    side: str
    on_pitch: bool
    on_since: int | None  # played ms when he came on
    hsr_t: list[int] = field(default_factory=list)  # played ms of each hsr run
    hsr_m: list[float] = field(default_factory=list)
    sprint_t: list[int] = field(default_factory=list)
    baseline: tuple[float, int, float] | None = None  # hsr m, sprints, in-play ms
    ew_m: float = 0.0  # exponentially weighted hsr metres, sprints and in-play ms
    ew_n: float = 0.0
    ew_inplay: float = 0.0
    ew_at: int | None = None
    smooth: float = 1.0
    est: float = 1.0
    history: list[tuple[int, float]] = field(default_factory=list)  # (played ms, est)

    def hsr_between(self, a: int, b: int) -> float:
        return sum(self.hsr_m[bisect_left(self.hsr_t, a):bisect_left(self.hsr_t, b)])

    def sprints_between(self, a: int, b: int) -> int:
        return bisect_left(self.sprint_t, b) - bisect_left(self.sprint_t, a)


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
        self._live = False
        self._inplay = 0  # in-play ms so far
        self._inplay_at = 0  # played ms that count runs to
        self._marks: list[tuple[int, int]] = [(0, 0)]  # (played, in-play) where liveness changes

    # --- clock ----------------------------------------------------------------

    def played(self, t_ms: int) -> int:
        """Played ms for a match-clock time in the current period."""
        return self._offset + t_ms

    def _set_live(self, now: int, live: bool) -> None:
        if self._live:
            self._inplay += now - self._inplay_at
        self._inplay_at = now
        if live != self._live:
            self._marks.append((now, self._inplay))
            self._live = live

    def inplay_at(self, played: int) -> float:
        """In-play ms up to a played time; exact, since liveness is constant between marks."""
        if played >= self._inplay_at:
            return self._inplay + (played - self._inplay_at if self._live else 0)
        i = bisect_left(self._marks, (played, -1))
        if i < len(self._marks) and self._marks[i][0] == played:
            return self._marks[i][1]
        p0, c0 = self._marks[i - 1]
        p1, c1 = self._marks[i] if i < len(self._marks) else (self._inplay_at, self._inplay)
        return c0 + (c1 - c0) * (played - p0) / (p1 - p0) if p1 > p0 else c0

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
        self._set_live(self.played(self._last_t + 1000), False)
        out.append(self._emit())
        return out

    def _emit_until(self, t: int) -> list[tuple[dict, list[dict]]]:
        out = []
        while self._next_t <= t:
            out.append(self._emit())
        return out

    def _emit(self) -> tuple[dict, list[dict]]:
        now = self.played(self._next_t)
        self._set_live(max(now, self._inplay_at), self._live)
        for p in self.players.values():
            if p.on_pitch and p.role != "GK":
                self._update_condition(p, now)
        snap = self.snapshot(self._next_t)
        events, self._pending = self._pending, []
        self._next_t += SNAPSHOT_MS
        return snap, events

    def _apply(self, e: dict) -> None:
        kind, team = e["type"], e["team"]
        now = self.played(e["t_ms"])
        player = self.players.get(e.get("player_id") or "")
        if kind == "restart":
            self._set_live(now, True)
        elif kind in DEAD_BALL or (kind == "shot" and e.get("outcome") in DEAD_SHOT):
            self._set_live(now + 1000, False)
        if kind == "hsr" and player is not None:
            player.hsr_t.append(now)
            player.hsr_m.append(e["dist_m"])
        elif kind == "sprint" and player is not None:
            player.sprint_t.append(now)
        elif kind == "goal":
            self.score[team] += 1
        elif kind == "sub":
            self._sub(e)
        elif kind == "restart":
            self._kicked_off = True
        elif kind == "shot" and e.get("xg") is not None:
            self.shots.append((now, e["period"], team, e["channel"], e["xg"]))

    def _sub(self, e: dict) -> None:
        team = e["team"]
        off, on = self.players[e["player_id"]], self.players[e["player_in_id"]]
        off.on_pitch = False
        on.on_pitch, on.on_since = True, self.played(e["t_ms"])
        self.subs_used[team] += 1
        half_time = e["period"] == 2 and e["t_ms"] == HALF_MS and not self._kicked_off
        if not half_time:
            self.windows[team].add((e["period"], e["t_ms"]))

    # --- condition ------------------------------------------------------------

    def _update_condition(self, p: _Player, now: int) -> None:
        """Advance one outfield player's estimate to a snapshot boundary.

        Exponentially weighted hsr metres, sprints and in-play time since he came on give
        his current running rates; each is compared with his own baseline rate."""
        prev = p.ew_at if p.ew_at is not None else p.on_since
        d_inplay = self.inplay_at(now) - self.inplay_at(prev)
        decay = math.exp(-(now - prev) / EW_TAU_MS)
        p.ew_m = p.ew_m * decay + p.hsr_between(prev, now)
        p.ew_n = p.ew_n * decay + p.sprints_between(prev, now)
        p.ew_inplay = p.ew_inplay * decay + d_inplay
        p.ew_at = now
        on = p.on_since
        if now - on < BASELINE_MS:
            return  # still setting his own baseline
        if p.baseline is None:
            end = on + BASELINE_MS
            p.baseline = (p.hsr_between(on, end), p.sprints_between(on, end),
                          self.inplay_at(end) - self.inplay_at(on))
        base_m, base_n, base_inplay = p.baseline
        if p.ew_inplay > 0 and base_inplay > 0:
            ratios = []
            if base_m > 0:
                ratios.append((HSR_WEIGHT, p.ew_m / p.ew_inplay / (base_m / base_inplay)))
            if base_n > 0:
                ratios.append((1 - HSR_WEIGHT, p.ew_n / p.ew_inplay / (base_n / base_inplay)))
            if ratios:
                p.smooth = sum(w * r for w, r in ratios) / sum(w for w, _ in ratios)
        p.est = min(COND_MAX, max(COND_MIN, max(p.smooth, 0.0) ** COND_EXP))
        p.history.append((now, p.est))

    def _trend(self, p: _Player, now: int) -> float:
        """Change in the estimate per minute over the last 5 minutes."""
        if not p.history or now - p.history[0][0] < TREND_MS:
            return 0.0
        then, est = p.history[bisect_left(p.history, (now - TREND_MS, -1.0))]
        return (p.est - est) / ((now - then) / MIN_MS) if now > then else 0.0

    # --- snapshot -------------------------------------------------------------

    def snapshot(self, t_ms: int) -> dict:
        now = self.played(t_ms)
        return {
            "match_id": self.match_id,
            "t_ms": t_ms,
            "period": self._period,
            "score": dict(self.score),
            "subs_left": {t: MAX_SUBS - self.subs_used[t] for t in self.teams},
            "windows_left": {t: MAX_WINDOWS - len(self.windows[t]) for t in self.teams},
            "rates": self._rates(now),
            "players": [self._player_dict(p, now) for p in self.players.values() if p.on_pitch],
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

    def _player_dict(self, p: _Player, now: int) -> dict:
        start = max(p.on_since, now - RECENT_MS)
        d = {"id": p.id, "role": p.role,
             "condition_est": None, "condition_band": None, "trend_per_min": 0.0,
             "hsr_m_10m": round(p.hsr_between(start, now)), "baseline_hsr_m_10m": None,
             "sprints_10m": p.sprints_between(start, now), "baseline_sprints_10m": None}
        if p.baseline is not None:
            d["baseline_hsr_m_10m"] = round(p.baseline[0] * RECENT_MS / BASELINE_MS)
            d["baseline_sprints_10m"] = round(p.baseline[1] * RECENT_MS / BASELINE_MS, 1)
        if p.role != "GK":
            half = BAND_HALF * (LOW_SPRINT_BAND if p.role in LOW_SPRINT_ROLES else 1.0)
            d["condition_est"] = round(p.est, 3)
            d["condition_band"] = [round(max(0.0, p.est - half), 3), round(min(1.0, p.est + half), 3)]
            d["trend_per_min"] = round(self._trend(p, now), 4)
        return d
