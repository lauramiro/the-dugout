"""Simulated managers: a scripted substitution policy for each bench.

Once a player is clearly fading (condition below FADE) the manager decides on
a like-for-like change, and makes it after a reaction delay. When trailing
after 65' he also makes attacking changes. Changes wait for a dead ball, or
happen at half-time, and keep to five substitutions in at most three in-play
windows plus half-time. The simulated manager stands in for a real one's eyes,
so he reads the hidden condition; the decision engine never does. All values
are tunable assumptions.
"""

from __future__ import annotations

from dugout.sim.state import MatchState, Player

MAX_SUBS, MAX_WINDOWS = 5, 3
FADE = 0.6
REACTION_MIN = (8, 15)
SLOW_REACTION_MIN = (14, 18)
ATTACK_FROM_S = 65 * 60
ATTACK_DELAY_MIN = (2, 5)
MAX_ATTACKING = 2
BUNDLE_S = 180  # a change due this soon joins the window being opened now
# Who can cover a role, best first.
COVER = {"CB": ("CB", "FB", "CM"), "FB": ("FB", "CB", "CM"), "CM": ("CM", "W", "FB"),
         "W": ("W", "ST", "CM"), "ST": ("ST", "W", "CM")}
ATTACK_OFF, ATTACK_ON = ("CM", "FB"), ("ST", "W")  # best first


def window_open(s: MatchState, team: str, half_time: bool) -> bool:
    return s.subs_used[team] < MAX_SUBS and (half_time or s.windows_used[team] < MAX_WINDOWS)


def _bench(s: MatchState, team: str, taken: set[str]) -> list[Player]:
    return [p for p in s.players.values()
            if p.team == team and not p.on_pitch and p.role != "GK"
            and p.id not in s.subbed_off and p.id not in taken]


def _like_for_like(s: MatchState, off: Player, taken: set[str]) -> str | None:
    bench = _bench(s, off.team, taken)
    for role in COVER[off.role]:
        fits = sorted((p for p in bench if p.role == role), key=lambda p: (p.side != off.side, p.id))
        if fits:
            return fits[0].id
    return None


def _attacking_pair(s: MatchState, team: str, taken: set[str]) -> tuple[str, str] | None:
    bench = _bench(s, team, taken)
    ons = [p for role in ATTACK_ON for p in sorted(bench, key=lambda p: p.id) if p.role == role]
    offs = sorted((p for p in s.players.values() if p.team == team and p.on_pitch
                   and p.role in ATTACK_OFF and p.id not in taken),
                  key=lambda p: (ATTACK_OFF.index(p.role), p.condition, p.id))
    return (offs[0].id, ons[0].id) if ons and offs else None


def _trailing(s: MatchState, team: str) -> bool:
    return s.score[team] < s.score[s.opponent(team)]


def plan(s: MatchState, team: str) -> None:
    """Once a minute: decide on changes and when to make them. Draws only when deciding."""
    if s.period == 2 and s.windows_used[team] >= MAX_WINDOWS:
        return
    mine = [e for e in s.pending if e["team"] == team]
    room = MAX_SUBS - s.subs_used[team] - len(mine)
    planned = {e["off"] for e in mine}
    slow = team in s.slow_managers
    fading = sorted((p for p in s.players.values() if p.team == team and p.on_pitch and p.role != "GK"
                     and p.condition < FADE and p.id not in planned), key=lambda p: (p.condition, p.id))
    for p in fading:
        if room <= 0:
            return
        if _like_for_like(s, p, set()) is None:
            continue
        lo, hi = SLOW_REACTION_MIN if slow else REACTION_MIN
        _schedule(s, team, "like_for_like", p.id, int(s.rng.integers(lo, hi + 1)))
        room -= 1
    if (room > 0 and s.period == 2 and s.clock_s >= ATTACK_FROM_S and _trailing(s, team)
            and s.attacking_subs[team] < MAX_ATTACKING and not any(e["kind"] == "attacking" for e in mine)):
        lo, hi = ATTACK_DELAY_MIN
        _schedule(s, team, "attacking", None, int(s.rng.integers(lo, hi + 1)))


def _schedule(s: MatchState, team: str, kind: str, off: str | None, delay_min: int) -> None:
    s.pending.append({"team": team, "kind": kind, "off": off, "due": [s.period, s.clock_s + 60 * delay_min]})


def due(s: MatchState, team: str, half_time: bool) -> list[tuple[str, str, str]]:
    """Take the changes ready now off the list and pair each with a player: (off, on, kind)."""
    mine = [e for e in s.pending if e["team"] == team]
    now = (s.period, s.clock_s)
    if not half_time and not any(tuple(e["due"]) <= now for e in mine):
        return []
    soon = (s.period, s.clock_s + BUNDLE_S)
    ready = mine if half_time else [e for e in mine if tuple(e["due"]) <= soon]
    s.pending = [e for e in s.pending if not any(e is r for r in ready)]
    subs: list[tuple[str, str, str]] = []
    taken: set[str] = set()
    for e in ready:
        if s.subs_used[team] + len(subs) >= MAX_SUBS:
            break
        if e["kind"] == "like_for_like":
            off = s.players[e["off"]]
            on = _like_for_like(s, off, taken) if off.on_pitch and off.id not in taken else None
            pair = (off.id, on) if on else None
        else:
            pair = _attacking_pair(s, team, taken) if _trailing(s, team) else None
        if pair:
            subs.append((*pair, e["kind"]))
            taken.update(pair)
    if s.period == 2 and not half_time and s.windows_used[team] + 1 >= MAX_WINDOWS:
        s.pending = [e for e in s.pending if e["team"] != team]  # no window would be left for them
    return subs
