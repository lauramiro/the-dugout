"""Minute-level Poisson win-probability simulation.

All rates and multipliers here are illustrative assumptions on synthetic data, not
fitted football effects. Nothing in this module calls a model.

Common random numbers: the caller passes a SeedSequence; each call builds a fresh
Generator from it and draws the same uniforms in the same order, so two calls with
the same SeedSequence share every draw. Goals come from inverse-CDF sampling of the
shared uniforms, so a higher rate can only add goals on a given draw.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.random import Generator, SeedSequence

ADDED = 6  # assumed second-half added time, minutes
LEAD_DAMP = 0.9  # leader sits deeper
TRAIL_PUSH = 1.15  # trailer pushes
# Fatigue constants fitted to true gaps on seeds 2-30 even (eval/counterfactual.py,
# docs/evaluation.md), on the load-based condition estimate with recent minutes and the
# condition_drop trigger; the illustrative values were 0.6, 0.8 and 1.03.
FATIGUE_SLOPE = 1.35  # extra opponent rate per unit of condition below FATIGUE_FLOOR
FATIGUE_FLOOR = 0.925
CONDITION_MIN = 0.3
BENCH_QUALITY = 1.06  # opponent rate multiplier once a like-for-like bench player is on
_MAX_GOALS = 4  # per team per minute; the tail beyond this is negligible at these rates


@dataclass(frozen=True)
class Flank:
    """Condition of the exposed defender and its drain per minute."""

    c0: float
    drain: float = 0.0


@dataclass(frozen=True)
class Outcome:
    win: float
    draw: float
    loss: float
    xpts: float


def summarize(diff: np.ndarray) -> Outcome:
    win = float(np.mean(diff > 0))
    draw = float(np.mean(diff == 0))
    loss = float(np.mean(diff < 0))
    return Outcome(win, draw, loss, 3 * win + draw)


def _poisson_icdf(u: np.ndarray, lam: np.ndarray) -> np.ndarray:
    """Poisson draw from uniforms u at per-run rate lam (inverse CDF, k up to _MAX_GOALS)."""
    term = np.exp(-lam)
    cdf = term.copy()
    k = (u > cdf).astype(np.int64)
    for i in range(1, _MAX_GOALS):
        term = term * lam / i
        cdf += term
        k += u > cdf
    return k


def simulate_diff(t0: int, home_goals: int, away_goals: int,
                  lam_home90: float, lam_away90: float, seed: SeedSequence, *,
                  n: int = 20_000, flank: Flank | None = None,
                  sub_at: int | None = None, sub_quality: float = BENCH_QUALITY,
                  home_mult: float = 1.0, away_mult: float = 1.0) -> np.ndarray:
    """Final goal difference (home minus away) for n runs from minute t0.

    flank: exposed home defender; while unsubbed his fatigue lifts the away rate.
    sub_at: minute of a like-for-like sub, which removes the penalty (bench player
    slightly weaker, sub_quality). home_mult / away_mult scale each team's rate
    (tactical changes).
    """
    rng: Generator = np.random.default_rng(seed)
    h = np.full(n, home_goals, dtype=np.int64)
    a = np.full(n, away_goals, dtype=np.int64)
    base_h = lam_home90 / 90.0 * home_mult
    base_a = lam_away90 / 90.0 * away_mult
    c = flank.c0 if flank is not None else None
    for minute in range(t0, 90 + ADDED):
        lead = h - a
        lh = np.where(lead > 0, base_h * LEAD_DAMP, np.where(lead < 0, base_h * TRAIL_PUSH, base_h))
        la = np.where(lead < 0, base_a * LEAD_DAMP, np.where(lead > 0, base_a * TRAIL_PUSH, base_a))
        if c is not None:
            if sub_at is not None and minute >= sub_at:
                la = la * sub_quality
            else:
                la = la * (1 + FATIGUE_SLOPE * max(0.0, FATIGUE_FLOOR - c))
            c = max(CONDITION_MIN, c - flank.drain)
        # both uniforms are drawn every minute so the stream never depends on the option
        u_h = rng.random(n)
        u_a = rng.random(n)
        h = h + _poisson_icdf(u_h, lh)
        a = a + _poisson_icdf(u_a, la)
    return h - a
