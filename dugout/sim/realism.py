"""Realism check: do simulated matches look like football?

Targets (approximate, over many seeds): 2.5 to 3 goals and 20 to 30 shots per
match, about 55 minutes of ball in play, and sprints and high-speed running
falling in the second half. Running is reported per player slot (team totals
over 22).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from dugout.contracts import Event
from dugout.sim.match import run_match
from dugout.sim.scenario import Scenario
from dugout.sim.state import MatchState

TARGETS = {"goals": (2.5, 3.0), "shots": (20.0, 30.0), "in_play_min": (50.0, 60.0)}


@dataclass(frozen=True, slots=True)
class MatchSummary:
    goals: int
    shots: int
    xg: float
    in_play_min: float
    home_goals: int
    away_goals: int
    sprints_h1: float
    sprints_h2: float
    hsr_m_h1: float
    hsr_m_h2: float


SLOTS = 22


def summarise(s: MatchState, events: list[Event]) -> MatchSummary:
    shots = [e for e in events if e.type == "shot"]

    def per_slot(type_: str, period: int, metres: bool) -> float:
        runs = [e for e in events if e.type == type_ and e.period == period]
        return round((sum(e.dist_m for e in runs) if metres else len(runs)) / SLOTS, 1)

    return MatchSummary(
        goals=sum(s.score.values()),
        shots=len(shots),
        xg=round(sum(e.xg or 0.0 for e in shots), 2),
        in_play_min=round(s.in_play_s / 60, 1),
        home_goals=s.score[s.home],
        away_goals=s.score[s.away],
        sprints_h1=per_slot("sprint", 1, False),
        sprints_h2=per_slot("sprint", 2, False),
        hsr_m_h1=per_slot("hsr", 1, True),
        hsr_m_h2=per_slot("hsr", 2, True),
    )


def realism(scenario: Scenario, seeds: range) -> dict[str, dict[str, float]]:
    rows = [summarise(*run_match(scenario, seed)) for seed in seeds]
    out: dict[str, dict[str, float]] = {}
    for key in ("goals", "shots", "xg", "in_play_min", "home_goals", "away_goals",
                "sprints_h1", "sprints_h2", "hsr_m_h1", "hsr_m_h2"):
        v = np.array([getattr(r, key) for r in rows], dtype=float)
        out[key] = {"mean": round(float(v.mean()), 2), "p10": float(np.percentile(v, 10)),
                    "p90": float(np.percentile(v, 90))}
    results = [(r.home_goals > r.away_goals) - (r.home_goals < r.away_goals) for r in rows]
    out["results"] = {"home_win": round(results.count(1) / len(rows), 3),
                      "draw": round(results.count(0) / len(rows), 3),
                      "away_win": round(results.count(-1) / len(rows), 3)}
    return out
