"""Options evaluated on common random numbers, with paired intervals on the gap.

Every option reuses the same SeedSequence, so all options see the same draws and the
gap to no change is a paired difference. Multipliers are illustrative assumptions.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.random import SeedSequence

from dugout.engine.wp import BENCH_QUALITY, simulate_diff, summarize

Z90 = 1.6448536269514722  # two-sided 90% normal quantile
ATTACK_HOME, ATTACK_AWAY = 1.12, 1.08  # attacking change raises both teams' rates
DEFEND_HOME, DEFEND_AWAY = 0.88, 0.92  # defensive change lowers both


@dataclass(frozen=True)
class Option:
    id: str
    label: str
    sub_at: int | None = None
    home_mult: float = 1.0
    away_mult: float = 1.0


@dataclass(frozen=True)
class OptionResult:
    id: str
    label: str
    win: float
    draw: float
    loss: float
    xpts: float
    delta_win: float
    ci90: tuple[float, float] | None  # None for the reference option


def default_options(t0: int) -> list[Option]:
    return [
        Option("no_change", "No change"),
        Option("sub_like_for_like", "Like-for-like substitution", sub_at=t0),
        Option("attacking", "Attacking change", home_mult=ATTACK_HOME, away_mult=ATTACK_AWAY),
        Option("defensive", "Defensive change", home_mult=DEFEND_HOME, away_mult=DEFEND_AWAY),
    ]


def evaluate(situation: dict, options: list[Option], seed: SeedSequence, *, n: int = 20_000,
             sub_quality: float = BENCH_QUALITY) -> list[OptionResult]:
    """Run every option on the same draws; the first option is the reference (no change)."""
    diffs = [simulate_diff(**situation, seed=seed, n=n, sub_at=o.sub_at, sub_quality=sub_quality,
                           home_mult=o.home_mult, away_mult=o.away_mult) for o in options]
    ref_win = diffs[0] > 0
    results = []
    for i, (o, diff) in enumerate(zip(options, diffs)):
        out = summarize(diff)
        gap = (diff > 0).astype(np.float64) - ref_win
        mean = float(gap.mean())
        if i == 0:
            ci = None
        else:
            half = Z90 * float(gap.std(ddof=1)) / np.sqrt(n)
            ci = (mean - half, mean + half)
        results.append(OptionResult(o.id, o.label, out.win, out.draw, out.loss, out.xpts, mean, ci))
    return results


def strength_label(gap_points: float) -> str:
    """strong at 3 points or more, lean 1 to 3, toss_up under 1 (docs/data-contracts.md)."""
    gap = round(gap_points, 9)
    if gap >= 3.0:
        return "strong"
    if gap >= 1.0:
        return "lean"
    return "toss_up"
