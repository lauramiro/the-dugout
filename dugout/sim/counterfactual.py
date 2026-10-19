"""True gap between options, measured by forking the hidden match state.

Each option is played to the end from the same moment N times. Branch k of
every option uses the same random stream (`MatchState.fork(k)`), so the
options differ only by the change itself: common random numbers. The deciding
team's simulated manager is frozen in every branch, so "no change" means no
change; the opponent's manager keeps to his script. This is the ground truth
the decision engine's estimated gap is checked against.
"""

from __future__ import annotations

from dataclasses import dataclass

from dugout.sim.match import make_subs, run_to_end, step
from dugout.sim.state import HALF_S, MatchState


@dataclass(frozen=True, slots=True)
class Option:
    id: str
    label: str
    subs: tuple[tuple[str, str], ...] = ()  # (off, on), made now as one window


@dataclass(frozen=True, slots=True)
class OptionResult:
    id: str
    label: str
    win: float
    draw: float
    loss: float
    xpts: float
    delta_win: float  # against no change
    delta_xpts: float


NO_CHANGE = Option("no_change", "No change")


def play_to(s: MatchState, minute: int) -> None:
    """Step to a match minute; 45 and later is the second half."""
    target = (1, minute * 60) if minute * 60 < HALF_S else (2, minute * 60)
    while not s.finished and (s.period, s.clock_s) < target:
        step(s)


def _results(s: MatchState, team: str, option: Option, n: int) -> list[int]:
    out = []
    for branch in range(1, n + 1):
        child = s.fork(branch)
        child.managers = [t for t in child.managers if t != team]
        if option.subs:
            make_subs(child, team, list(option.subs))
        run_to_end(child)
        diff = child.score[team] - child.score[child.opponent(team)]
        out.append((diff > 0) - (diff < 0))
    return out


def true_gap(s: MatchState, team: str, options: list[Option], n: int) -> list[OptionResult]:
    """Win, draw, loss and expected points per option for `team`, plus the gap to no change."""
    if not any(o.id == NO_CHANGE.id for o in options):
        raise ValueError("options must include no_change")
    rows = {}
    for o in options:
        res = _results(s, team, o, n)
        win, draw = res.count(1) / n, res.count(0) / n
        rows[o.id] = (o, win, draw, res.count(-1) / n)
    _, bw, bd, _ = rows[NO_CHANGE.id]
    base_xpts = 3 * bw + bd
    return [OptionResult(id=o.id, label=o.label, win=w, draw=d, loss=lo, xpts=3 * w + d,
                         delta_win=w - bw, delta_xpts=3 * w + d - base_xpts)
            for o, w, d, lo in rows.values()]
