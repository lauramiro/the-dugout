"""Observable match state from the event stream, as a snapshot every 10 s (contract 3).

Fed contract-1 event dicts one at a time in `seq` order, plus a lineup: one dict per
squad player with `id`, `team`, `role`, `side`, `starting` and optionally `recent_minutes`
(minutes played in the last 7 days, 0 if left out). Nothing else about a player is known
here, and this module never imports the simulator.

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

from dugout.contracts import CHANNELS

HALF_MS = 45 * 60 * 1000  # second-half kick-off, match clock
SNAPSHOT_MS = 10_000
MAX_SUBS, MAX_WINDOWS = 5, 3
MIN_MS = 60_000

# Scoring rates: weight on the rolling rate grows with played time up to RATE_W_MAX at 90'.
RATE_WINDOW_MS = 20 * MIN_MS
RATE_W_MAX = 0.6

# Condition estimate, mostly from accumulated load: every minute on the pitch costs a drain
# for the role and every run a little more, and half-time gives some back. The costs are the
# simulator's fatigue assumptions for an average player, not fitted. What load cannot see is a
# player tiring faster than his load says; the only sign of that is his running rate falling
# against his own first 20 minutes on the pitch, and with about one run per in-play minute that
# ratio is mostly Poisson noise, so it gets a small weight. Running is taken to fall faster
# than condition, so the ratio is raised to COND_EXP. The band is a 90% interval from the
# spread of drain between players on the same load and the run counts behind the ratio.
BASELINE_MS = 20 * MIN_MS
RECENT_MS = 10 * MIN_MS
EW_TAU_MS = 15 * MIN_MS
DRAIN_PER_MIN = {"CB": 0.0024, "FB": 0.0028, "CM": 0.0028, "W": 0.0028, "ST": 0.0026}
DRAIN_DEFAULT = 0.0027
SPRINT_COST, HSR_COST = 0.002, 0.0008
HALF_TIME_RECOVERY = 0.05
RATE_WEIGHT = 0.1
DRAIN_CV = 0.2  # drain between players on the same load (stamina, work rate): sd / mean
COND_EXP = 2 / 3
COND_MIN, COND_MAX = 0.3, 1.0
TREND_MS = 5 * MIN_MS
BAND_Z = 1.645  # 90%

# Recent minutes: a player who played in the last 7 days starts below 1.0. Stated assumption,
# not fitted: half of a full match's load is still there a few days later. FULL_MATCH_LOAD is
# this module's own load over 90 minutes for an outfield starter (mean 0.283 over seeds 1-20,
# half-time recovery included), so 90 recent minutes cost 0.14. The share is uncertain, anywhere
# from about a quarter to three quarters, so the band widens by RECENT_CV of the residual.
FULL_MATCH_LOAD = 0.28
RECENT_SHARE = 0.5
RECENT_COST_PER_MIN = RECENT_SHARE * FULL_MATCH_LOAD / 90
RECENT_CV = 0.5

# Threat by channel: share of the opponent's xG down each of a team's channels over the last
# 15 played minutes, shrunk towards the first-half split (even until the first shot) by a
# pseudo-count, since a 15-minute window often holds no shots.
THREAT_WINDOW_MS = 15 * MIN_MS
THREAT_PSEUDO_XG = 0.15
MIRROR = {"left": "right", "centre": "centre", "right": "left"}

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
    baseline: tuple[float, int, float] | None = None  # hsr m, runs (hsr and sprints), in-play ms
    residual: float = 0.0  # condition still spent from his recent minutes
    load: float = 0.0  # condition spent since he came on
    ew_runs: float = 0.0  # exponentially weighted runs and in-play ms
    ew_inplay: float = 0.0
    ew_inplay2: float = 0.0  # in-play ms under squared weights, for the effective sample size
    ew_at: int | None = None
    ratio: float = 1.0  # running rate against his baseline
    est: float = 1.0
    band: tuple[float, float] | None = None
    history: list[tuple[int, float]] = field(default_factory=list)  # (played ms, est)

    def hsr_between(self, a: int, b: int) -> float:
        return sum(self.hsr_m[bisect_left(self.hsr_t, a):bisect_left(self.hsr_t, b)])

    def hsr_runs_between(self, a: int, b: int) -> int:
        return bisect_left(self.hsr_t, b) - bisect_left(self.hsr_t, a)

    def sprints_between(self, a: int, b: int) -> int:
        return bisect_left(self.sprint_t, b) - bisect_left(self.sprint_t, a)


class StateEngine:
    def __init__(self, lineup: list[dict], prior90: float = 1.35) -> None:
        self.prior90 = prior90
        self.players = {p["id"]: _Player(p["id"], p["team"], p["role"], p["side"],
                                         bool(p["starting"]), 0 if p["starting"] else None,
                                         residual=RECENT_COST_PER_MIN * p.get("recent_minutes", 0))
                        for p in lineup}
        for p in self.players.values():
            p.est = self._clip(1.0 - p.residual)
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
            self._half_time()
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

    def _half_time(self) -> None:
        for p in self.players.values():
            if p.on_pitch:
                p.load = max(0.0, p.load - HALF_TIME_RECOVERY)

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
        if kind in DEAD_BALL or (kind == "shot" and e.get("outcome") in DEAD_SHOT):
            self._set_live(now + 1000, False)
        if kind == "restart":
            self._set_live(now, True)
            self._kicked_off = True
        elif kind == "hsr" and player is not None:
            player.hsr_t.append(now)
            player.hsr_m.append(e["dist_m"])
        elif kind == "sprint" and player is not None:
            player.sprint_t.append(now)
        elif kind == "goal":
            self.score[team] += 1
        elif kind == "sub":
            self._sub(e)
        if kind == "shot" and e.get("xg") is not None:
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
        """Advance one outfield player's load, estimate and band to a snapshot boundary.

        Load counts minutes and runs since he came on, on top of the residual from his recent
        minutes. Exponentially weighted runs and in-play time give his current running rate,
        compared with his own baseline rate."""
        prev = p.ew_at if p.ew_at is not None else p.on_since
        runs = p.hsr_runs_between(prev, now) + p.sprints_between(prev, now)
        p.load += (DRAIN_PER_MIN.get(p.role, DRAIN_DEFAULT) * (now - prev) / MIN_MS
                   + SPRINT_COST * p.sprints_between(prev, now) + HSR_COST * p.hsr_runs_between(prev, now))
        d_inplay = self.inplay_at(now) - self.inplay_at(prev)
        decay = math.exp(-(now - prev) / EW_TAU_MS)
        p.ew_runs = p.ew_runs * decay + runs
        p.ew_inplay = p.ew_inplay * decay + d_inplay
        p.ew_inplay2 = p.ew_inplay2 * decay ** 2 + d_inplay
        p.ew_at = now
        loaded = 1.0 - p.residual - p.load
        p.est = self._clip(loaded)
        p.history.append((now, p.est))
        on = p.on_since
        if now - on < BASELINE_MS:
            return  # still setting his own baseline
        if p.baseline is None:
            end = on + BASELINE_MS
            p.baseline = (p.hsr_between(on, end),
                          p.hsr_runs_between(on, end) + p.sprints_between(on, end),
                          self.inplay_at(end) - self.inplay_at(on))
        _, base_runs, base_inplay = p.baseline
        rate, rate_lo, rate_hi = 1.0, 1.0, 1.0
        if base_runs > 0 and base_inplay > 0 and p.ew_inplay > 0:
            expected = base_runs / base_inplay * p.ew_inplay
            p.ratio = p.ew_runs / expected
            # an exponentially weighted Poisson count n has variance k * n, k = sum w^2 / sum w
            k = p.ew_inplay2 / p.ew_inplay
            sd = math.sqrt(k * max(p.ew_runs, 1.0) / expected ** 2 + p.ratio ** 2 / base_runs)
            # not clipped: a rate above his baseline must be able to offset one below it
            rate, rate_lo, rate_hi = (max(p.ratio + z * sd, 0.0) ** COND_EXP for z in (0.0, -BAND_Z, BAND_Z))
        p.est = self._clip((1 - RATE_WEIGHT) * loaded + RATE_WEIGHT * rate)
        p.history[-1] = (now, p.est)
        drain = BAND_Z * math.hypot(DRAIN_CV * min(1.0, p.load), RECENT_CV * p.residual)
        lo = math.hypot(drain, RATE_WEIGHT * (rate - rate_lo))
        hi = math.hypot(drain, RATE_WEIGHT * (rate_hi - rate))
        p.band = (self._clip(p.est - lo), self._clip(p.est + hi))

    @staticmethod
    def _clip(x: float) -> float:
        return min(COND_MAX, max(COND_MIN, x))

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
            "threat_by_channel": self._threat(now),
            "threat_by_channel_first_half": self._threat_first_half(),
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

    def _against(self, team: str, keep) -> dict[str, float]:
        """Opponent xG by the channel it came down, from `team`'s own view."""
        xg = dict.fromkeys(CHANNELS, 0.0)
        for played, period, shooter, channel, x in self.shots:
            if shooter != team and channel in MIRROR and keep(played, period):
                xg[MIRROR[channel]] += x
        return xg

    @staticmethod
    def _shares(xg: dict[str, float], ref: dict[str, float], pseudo: float) -> dict[str, float]:
        total = sum(xg.values()) + pseudo
        return {c: (xg[c] + pseudo * ref[c]) / total if total else ref[c] for c in CHANNELS}

    def _first_half_split(self, team: str) -> dict[str, float]:
        even = dict.fromkeys(CHANNELS, 1 / 3)
        return self._shares(self._against(team, lambda _, period: period == 1), even, 0.0)

    def _threat(self, now: int) -> dict[str, float]:
        out = {}
        for team in self.teams:
            recent = self._against(team, lambda played, _: now - THREAT_WINDOW_MS <= played < now)
            shares = self._shares(recent, self._first_half_split(team), THREAT_PSEUDO_XG)
            out.update({f"{team}_{c}": round(v, 3) for c, v in shares.items()})
        return out

    def _threat_first_half(self) -> dict[str, float]:
        out = {}
        for team in self.teams:
            shares = self._first_half_split(team)
            out.update({f"{team}_{c}": round(v, 3) for c, v in shares.items()})
        return out

    def _player_dict(self, p: _Player, now: int) -> dict:
        start = max(p.on_since, now - RECENT_MS)
        d = {"id": p.id, "team": p.team, "role": p.role,
             "condition_est": None, "condition_band": None, "trend_per_min": 0.0,
             "hsr_m_10m": round(p.hsr_between(start, now)), "baseline_hsr_m_10m": None,
             "sprints_10m": p.sprints_between(start, now), "baseline_sprints_10m": None}
        if p.baseline is not None:
            d["baseline_hsr_m_10m"] = round(p.baseline[0] * RECENT_MS / BASELINE_MS)
            d["baseline_sprints_10m"] = round(p.sprints_between(p.on_since, p.on_since + BASELINE_MS)
                                              * RECENT_MS / BASELINE_MS, 1)
        if p.role != "GK":
            d["condition_est"] = round(p.est, 3)
            if p.band is not None:  # null while he is still setting his baseline
                d["condition_band"] = [round(p.band[0], 3), round(p.band[1], 3)]
            d["trend_per_min"] = round(self._trend(p, now), 4)
        return d
