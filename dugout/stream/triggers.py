"""Decision points for both teams from snapshots and the events between them.

Triggers:
- `condition_below_60`: an outfield player's condition estimate crosses below 0.60;
  once per player, for his team.
- `goal_after_55`: a goal from 55:00 on; one point for each team, the conceding team first.
- `manager_sub`: any substitution; one point per team per window, for the team that made it.

One card is open at a time; other points wait in a queue, oldest first. A card closes
when its team makes a change, or after CARD_TIMEOUT_SNAPSHOTS snapshots (3 minutes of
match clock), or at the end of the stream. A change also drops that team's waiting
points, since the change answers them, and a waiting condition point is dropped if the
player is no longer on the pitch. A point that waited opens on the latest snapshot.

Reads snapshots and event dicts only; never imports the simulator.
"""

from __future__ import annotations

from dataclasses import dataclass, field

CONDITION_LINE = 0.60
GOAL_MINUTE = 55
CARD_TIMEOUT_SNAPSHOTS = 18  # 3 minutes of match clock at one snapshot every 10 s


@dataclass
class _Point:
    team: str
    trigger: str
    raised_t_ms: int
    detail: dict = field(default_factory=dict)


class DecisionPoints:
    def __init__(self) -> None:
        self.queue: list[_Point] = []
        self.open: dict | None = None  # the open card's record
        self._age = 0  # snapshots since the open card opened
        self._last_est: dict[str, float] = {}
        self._fired: set[str] = set()  # players with a condition point already
        self._count: dict[tuple[str, int], int] = {}

    def on_snapshot(self, snapshot: dict, events: list[dict]) -> list[dict]:
        """Take the next snapshot and the events since the previous one; return the
        records it produces (`card_closed`, then at most one `decision_point`)."""
        out = []
        changed = {e["team"] for e in events if e["type"] == "sub"}
        if self.open is not None:
            self._age += 1
            if self.open["team"] in changed:
                out.append(self._close(snapshot, "change"))
            elif self._age >= CARD_TIMEOUT_SNAPSHOTS:
                out.append(self._close(snapshot, "timeout"))
        self.queue = [p for p in self.queue if p.team not in changed]
        self.queue += self._raise(snapshot, events)
        if self.open is None:
            on_pitch = {p["id"] for p in snapshot["players"]}
            while self.queue:
                point = self.queue.pop(0)
                if point.trigger != "condition_below_60" or point.detail["player_id"] in on_pitch:
                    out.append(self._open(snapshot, point))
                    break
        return out

    def finish(self) -> list[dict]:
        """End of the stream: close the open card and drop the queue."""
        self.queue = []
        if self.open is None:
            return []
        return [self._close({"t_ms": self.open["t_ms"], "period": self.open["period"]}, "full_time")]

    def _raise(self, snapshot: dict, events: list[dict]) -> list[_Point]:
        points = []
        windows: dict[tuple, list[dict]] = {}
        for e in events:
            if e["type"] == "sub":
                windows.setdefault((e["team"], e["period"], e["t_ms"]), []).append(e)
            elif e["type"] == "goal" and e["period"] == 2 and e["t_ms"] >= GOAL_MINUTE * 60_000:
                conceding = next(t for t in snapshot["score"] if t != e["team"])
                points += [_Point(team, "goal_after_55", e["t_ms"], {"scorer_team": e["team"]})
                           for team in (conceding, e["team"])]
        for (team, _, t_ms), subs in windows.items():
            points.append(_Point(team, "manager_sub", t_ms,
                                 {"subs": [{"off": s["player_id"], "on": s["player_in_id"]} for s in subs]}))
        points.sort(key=lambda p: p.raised_t_ms)
        for p in snapshot["players"]:
            est = p.get("condition_est")
            if est is None:
                continue
            before = self._last_est.get(p["id"], 1.0)
            self._last_est[p["id"]] = est
            if est < CONDITION_LINE <= before and p["id"] not in self._fired:
                self._fired.add(p["id"])
                points.append(_Point(p["team"], "condition_below_60", snapshot["t_ms"],
                                     {"player_id": p["id"], "condition_est": est,
                                      "condition_band": p.get("condition_band")}))
        return points

    def _open(self, snapshot: dict, point: _Point) -> dict:
        minute = snapshot["t_ms"] // 60_000
        n = self._count[(point.team, minute)] = self._count.get((point.team, minute), 0) + 1
        # rates with the deciding team first: dugout.engine.payload.decide reads its team from there
        rates = snapshot["rates"]
        snap = {**snapshot, "rates": {point.team: rates[point.team],
                                      **{t: r for t, r in rates.items() if t != point.team}}}
        self.open = {"kind": "decision_point", "id": f"{point.team.lower()}-{minute}-{n:02d}",
                     "t_ms": snapshot["t_ms"], "period": snapshot["period"], "team": point.team,
                     "trigger": point.trigger, "raised_t_ms": point.raised_t_ms, "detail": point.detail,
                     "snapshot": snap}
        self._age = 0
        return self.open

    def _close(self, snapshot: dict, reason: str) -> dict:
        record = {"kind": "card_closed", "id": self.open["id"], "t_ms": snapshot["t_ms"],
                  "period": snapshot["period"], "team": self.open["team"], "reason": reason}
        self.open = None
        return record
