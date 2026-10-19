"""Realism check: do simulated matches look like football?

Targets (approximate, over many seeds): 2.5 to 3 goals and 20 to 30 shots per
match, about 55 minutes of ball in play.
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


def summarise(s: MatchState, events: list[Event]) -> MatchSummary:
    shots = [e for e in events if e.type == "shot"]
    return MatchSummary(
        goals=sum(s.score.values()),
        shots=len(shots),
        xg=round(sum(e.xg or 0.0 for e in shots), 2),
        in_play_min=round(s.in_play_s / 60, 1),
        home_goals=s.score[s.home],
        away_goals=s.score[s.away],
    )


def realism(scenario: Scenario, seeds: range) -> dict[str, dict[str, float]]:
    rows = [summarise(*run_match(scenario, seed)) for seed in seeds]
    out: dict[str, dict[str, float]] = {}
    for key in ("goals", "shots", "xg", "in_play_min", "home_goals", "away_goals"):
        v = np.array([getattr(r, key) for r in rows], dtype=float)
        out[key] = {"mean": round(float(v.mean()), 2), "p10": float(np.percentile(v, 10)),
                    "p90": float(np.percentile(v, 90))}
    results = [(r.home_goals > r.away_goals) - (r.home_goals < r.away_goals) for r in rows]
    out["results"] = {"home_win": round(results.count(1) / len(rows), 3),
                      "draw": round(results.count(0) / len(rows), 3),
                      "away_win": round(results.count(-1) / len(rows), 3)}
    return out
