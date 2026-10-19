"""Seed search: find a seed where the demo story happens on its own.

The story: Riverside lead at 60'; the left-back RFC-03 (the played-midweek
lever) fades by about 62'; Castleton equalise down that flank between 70' and
80'; Riverside's manager takes RFC-03 off at about 78'. Every candidate is an
honest simulation of the scenario; nothing is written or edited by hand.

This is an authoring tool, so it may read hidden values. "Fades" means the
hidden condition of RFC-03 first drops below `FADE_BELOW`, the level at which
the simulated manager treats a player as fading (`managers.FADE`), so the fade
minute is the first whole minute the manager could start reacting. Minutes are
whole match minutes: 80 means 80:00 to 80:59, and the second half runs on from
45 (an event at t_ms 4_800_000 is minute 80).

Channel mapping: event channels are from the scoring team's view. RFC-03 is
Riverside's left-back, so the flank he covers is Riverside's left, which is
Castleton's right: the equaliser must be a Castleton goal with channel "right".
"""

from __future__ import annotations

from collections.abc import Iterable
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass

from dugout.contracts import Event
from dugout.sim import managers
from dugout.sim.counterfactual import NO_CHANGE, Option, play_to, true_gap
from dugout.sim.match import MIRROR, new_match, step
from dugout.sim.scenario import Scenario

HOME, AWAY = "RFC", "CAS"
FADING_PLAYER = "RFC-03"
FLANK_FOR_HOME = "left"  # RFC-03's side, from Riverside's view
EQUALISER_CHANNEL = MIRROR[FLANK_FOR_HOME]  # the same flank from Castleton's view
FADE_BELOW = managers.FADE
LEAD_AT = 60


@dataclass(frozen=True, slots=True)
class Windows:
    fade: tuple[int, int]
    equaliser: tuple[int, int]
    sub: tuple[int, int] | None  # None: any time after the fade


NARROW = Windows(fade=(60, 64), equaliser=(70, 80), sub=(76, 80))
WIDE = Windows(fade=(60, 64), equaliser=(65, 85), sub=None)


@dataclass(frozen=True, slots=True)
class Match:
    fade: int
    equaliser: int
    sub: int


def minute(e: Event) -> int:
    return e.t_ms // 60_000


def check_story(events: list[Event], fade_minute: int | None, windows: Windows) -> Match | None:
    """The minutes of the story if `events` tell it inside `windows`, else None.

    `fade_minute` is the first minute RFC-03's hidden condition was below
    `FADE_BELOW`, or None if it never was; it is not in the event stream.
    """
    if fade_minute is None or not windows.fade[0] <= fade_minute <= windows.fade[1]:
        return None
    goals = [e for e in events if e.type == "goal"]
    score = {HOME: 0, AWAY: 0}
    for e in goals:
        if minute(e) < LEAD_AT:
            score[e.team] += 1
    if score[HOME] <= score[AWAY]:
        return None
    equaliser = None
    for e in goals:
        if minute(e) < LEAD_AT:
            continue
        score[e.team] += 1
        if (e.team == AWAY and score[HOME] == score[AWAY] and e.channel == EQUALISER_CHANNEL
                and windows.equaliser[0] <= minute(e) <= windows.equaliser[1]):
            equaliser = minute(e)
            break
    if equaliser is None:
        return None
    for e in events:
        if (e.type == "sub" and e.team == HOME and e.player_id == FADING_PLAYER
                and _sub_in_window(minute(e), fade_minute, windows)):
            return Match(fade_minute, equaliser, minute(e))
    return None


def _sub_in_window(m: int, fade_minute: int, windows: Windows) -> bool:
    if windows.sub is None:
        return m >= fade_minute
    return windows.sub[0] <= m <= windows.sub[1]


# Fallback order (decision 11): 1) 2,000 seeds, narrow windows; 2) the same seeds,
# wide windows; 3) up to 10,000 seeds. Scenario levers are not a step here: that
# is the user's call.
STEP_SEEDS = 2000


def fallback_step(seed: int, m: Match) -> int:
    """The first fallback step that finds this seed with this match."""
    if seed > STEP_SEEDS:
        return 3
    narrow = (NARROW.equaliser[0] <= m.equaliser <= NARROW.equaliser[1]
              and NARROW.sub[0] <= m.sub <= NARROW.sub[1])
    return 1 if narrow else 2


def play_seed(scenario: Scenario, seed: int) -> tuple[list[Event], int | None]:
    """Play one match; return its events and the minute RFC-03 first fell below FADE_BELOW."""
    s, events = new_match(scenario, seed)
    fade = None
    while not s.finished:
        events += step(s)
        if fade is None and s.clock_s % 60 == 0 and s.players[FADING_PLAYER].condition < FADE_BELOW:
            fade = s.clock_s // 60
    return events, fade


def _try(args: tuple[Scenario, int, Windows]) -> tuple[int, Match] | None:
    scenario, seed, windows = args
    events, fade = play_seed(scenario, seed)
    m = check_story(events, fade, windows)
    return (seed, m) if m else None


def search(scenario: Scenario, seeds: Iterable[int], windows: Windows, workers: int | None = None
           ) -> list[tuple[int, Match]]:
    """(seed, match) for every seed whose honest simulation tells the story, in seed order."""
    jobs = [(scenario, seed, windows) for seed in seeds]
    if workers == 1:
        results = map(_try, jobs)
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(_try, jobs, chunksize=16))
    return [r for r in results if r]


# --- ranking by honest gap ---------------------------------------------------

@dataclass(frozen=True, slots=True)
class Gap:
    seed: int
    match: Match | None
    on: str  # the like-for-like bench player
    delta_win: float  # win probability, RFC-03 off against no change
    delta_xpts: float


def honest_gap(scenario: Scenario, seed: int, fade_minute: int, n: int, match: Match | None = None) -> Gap:
    """True gap at the fade minute: no change against RFC-03 off for a like-for-like bench player."""
    s, _ = new_match(scenario, seed)
    play_to(s, fade_minute)
    on = managers._like_for_like(s, s.players[FADING_PLAYER], set())
    option = Option(f"sub_{FADING_PLAYER}", f"{FADING_PLAYER} off, {on} on", subs=((FADING_PLAYER, on),))
    _, sub = true_gap(s, HOME, [NO_CHANGE, option], n)
    return Gap(seed, match, on, sub.delta_win, sub.delta_xpts)


def _gap_job(args: tuple[Scenario, int, Match, int]) -> Gap:
    scenario, seed, m, n = args
    return honest_gap(scenario, seed, m.fade, n, m)


def rank_by_gap(scenario: Scenario, found: list[tuple[int, Match]], n: int = 500,
                workers: int | None = None) -> list[Gap]:
    """Matching seeds with their true gap, the largest gain from the change first."""
    jobs = [(scenario, seed, m, n) for seed, m in found]
    if workers == 1:
        gaps = list(map(_gap_job, jobs))
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            gaps = list(pool.map(_gap_job, jobs))
    return sorted(gaps, key=lambda g: (-g.delta_win, -g.delta_xpts, g.seed))
