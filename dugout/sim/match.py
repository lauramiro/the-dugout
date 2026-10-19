"""One-second-tick possession model: possessions, shots and goals.

Each second the team in possession, in a given third and channel, may advance,
shoot (attacking third only), lose the ball, put it out, drop back or switch
channel. The odds come from the edge between the attacking players involved in
that third and channel and the defenders facing them. Every rating is scaled by
the player's hidden condition, so fatigue weakens exactly the zones a tired
player covers. Attackers prefer channels where their edge is largest, which is
how a tired full-back draws the opponent's chances to his flank.

All rates are tunable assumptions, checked against the realism targets in
`dugout.sim.realism`.
"""

from __future__ import annotations

import math

import numpy as np

from dugout.contracts import CHANNELS, PITCH_LENGTH, PITCH_WIDTH, Event
from dugout.sim.scenario import Scenario
from dugout.sim.state import HALF_S, MatchState, Player

# How involved each role is, by third. Attack: the possessing team's third.
# Defence: the defending team's own third (0 = its defensive third).
ATT_W = {
    0: {"GK": 0.3, "CB": 1.0, "FB": 0.8, "CM": 0.6, "W": 0.2, "ST": 0.1},
    1: {"GK": 0.0, "CB": 0.3, "FB": 0.6, "CM": 1.0, "W": 0.6, "ST": 0.3},
    2: {"GK": 0.0, "CB": 0.05, "FB": 0.4, "CM": 0.6, "W": 1.0, "ST": 1.0},
}
DEF_W = {
    0: {"GK": 0.4, "CB": 1.0, "FB": 1.0, "CM": 0.5, "W": 0.2, "ST": 0.05},
    1: {"GK": 0.0, "CB": 0.4, "FB": 0.6, "CM": 1.0, "W": 0.5, "ST": 0.3},
    2: {"GK": 0.0, "CB": 0.1, "FB": 0.3, "CM": 0.6, "W": 0.8, "ST": 1.0},
}

# Per-second base probabilities, by third of the team in possession.
P_ADV = (0.10, 0.07, 0.0)
P_BACK = (0.0, 0.025, 0.03)
P_TO = (0.025, 0.045, 0.07)
P_SHOT = 0.017
P_OUT = 0.02
P_FOUL = 0.006  # by the defending team; about 22 a match
P_SWITCH = 0.05
CENTRE_SHOT_MULT = 1.3

K_EDGE = 3.0  # how strongly the attack-defence edge moves the odds
K_CHOICE = 4.0  # how strongly attackers prefer the channel with the best edge
LEAD_MULT, TRAIL_MULT = 0.9, 1.12  # leader sits deeper, trailer pushes

XG_MEDIAN = {"centre": 0.12, "left": 0.06, "right": 0.06}
XG_SIGMA = 0.8
P_SAVED, P_BLOCKED = 0.35, 0.25  # of non-goal shots; the rest go off target
P_CORNER_SAVED, P_CORNER_BLOCKED = 0.3, 0.5
P_THROW_TO_OPPONENT = 0.6

DEAD_S = {
    "kickoff": (45, 70),
    "throw_in": (12, 25),
    "goal_kick": (20, 35),
    "corner": (25, 40),
    "keeper": (5, 10),
    "free_kick": (15, 30),
}
ADDED_MIN = {1: (1, 3), 2: (3, 7)}

MIRROR = {"left": "right", "right": "left", "centre": "centre"}
Y_BANDS = {"right": (0.0, 23.0), "centre": (23.0, 45.0), "left": (45.0, PITCH_WIDTH)}


def side_weight(side: str, channel: str) -> float:
    if side == channel:
        return 1.0
    if "centre" in (side, channel):
        return 0.35
    return 0.0


def _on_pitch(s: MatchState, team: str) -> list[Player]:
    return [p for p in s.players.values() if p.team == team and p.on_pitch]


def strength(s: MatchState, team: str, third: int, channel: str, kind: str) -> float:
    table = ATT_W if kind == "attack" else DEF_W
    num = den = 0.0
    for p in _on_pitch(s, team):
        w = table[third][p.role] * side_weight(p.side, channel)
        if w == 0.0:
            continue
        skill = p.attack if kind == "attack" else p.defence
        num += w * (0.7 * skill + 0.3 * p.pace) * p.condition
        den += w
    return num / den if den else 0.0


def edge(s: MatchState, team: str, third: int, channel: str) -> float:
    dfn = s.opponent(team)
    return strength(s, team, third, channel, "attack") - strength(s, dfn, 2 - third, MIRROR[channel], "defence")


def _score_mult(s: MatchState, team: str) -> float:
    lead = s.score[team] - s.score[s.opponent(team)]
    return LEAD_MULT if lead > 0 else TRAIL_MULT if lead < 0 else 1.0


def _dead(s: MatchState, kind: str) -> None:
    lo, hi = DEAD_S[kind]
    s.dead_s = int(s.rng.integers(lo, hi + 1))
    s.restart = kind


def _xy(s: MatchState, team: str, third: int, channel: str) -> tuple[float, float]:
    """Absolute pitch position for a team-relative third and channel."""
    x = s.rng.uniform(third * 35.0, third * 35.0 + 35.0)
    y = s.rng.uniform(*Y_BANDS[channel])
    attacking_up = (team == s.home) == (s.period == 1)
    if not attacking_up:
        x, y = PITCH_LENGTH - x, PITCH_WIDTH - y
    return round(x, 1), round(y, 1)


def _pick(s: MatchState, team: str, third: int, channel: str, table: dict) -> str:
    ps = _on_pitch(s, team)
    w = np.array([table[third][p.role] * max(side_weight(p.side, channel), 0.05) for p in ps])
    return ps[int(s.rng.choice(len(ps), p=w / w.sum()))].id


def _choose_channel(s: MatchState, team: str, third: int) -> str:
    logits = np.array([K_CHOICE * edge(s, team, third, c) for c in CHANNELS])
    p = np.exp(logits - logits.max())
    return CHANNELS[int(s.rng.choice(3, p=p / p.sum()))]


def _event(s: MatchState, type_: str, team: str, **kw) -> Event:
    s.seq += 1
    return Event(match_id=s.match_id, seq=s.seq, t_ms=s.clock_s * 1000, period=s.period,
                 type=type_, team=team, **kw)


def _change_possession(s: MatchState) -> None:
    s.possession = s.opponent(s.possession)
    s.third = 2 - s.third
    s.channel = MIRROR[s.channel]


# --- actions -----------------------------------------------------------------

def _advance(s: MatchState) -> list[Event]:
    team, z, ch = s.possession, s.third, s.channel
    pid = _pick(s, team, z, ch, ATT_W)
    x, y = _xy(s, team, z, ch)
    s.third = z + 1
    s.channel = _choose_channel(s, team, s.third)
    ex, ey = _xy(s, team, s.third, s.channel)
    return [_event(s, "pass", team, player_id=pid, channel=ch, x=x, y=y, end_x=ex, end_y=ey, outcome="complete")]


def _back(s: MatchState) -> list[Event]:
    team, z, ch = s.possession, s.third, s.channel
    pid = _pick(s, team, z, ch, ATT_W)
    x, y = _xy(s, team, z, ch)
    s.third = z - 1
    ex, ey = _xy(s, team, s.third, ch)
    return [_event(s, "pass", team, player_id=pid, channel=ch, x=x, y=y, end_x=ex, end_y=ey, outcome="complete")]


def _switch(s: MatchState) -> list[Event]:
    team, z, ch = s.possession, s.third, s.channel
    pid = _pick(s, team, z, ch, ATT_W)
    x, y = _xy(s, team, z, ch)
    s.channel = _choose_channel(s, team, z)
    ex, ey = _xy(s, team, z, s.channel)
    return [_event(s, "pass", team, player_id=pid, channel=ch, x=x, y=y, end_x=ex, end_y=ey, outcome="complete")]


def _turnover(s: MatchState) -> list[Event]:
    dfn = s.opponent(s.possession)
    z, ch = 2 - s.third, MIRROR[s.channel]
    pid = _pick(s, dfn, z, ch, DEF_W)
    x, y = _xy(s, dfn, z, ch)
    _change_possession(s)
    return [_event(s, "duel", dfn, player_id=pid, channel=ch, x=x, y=y, outcome="won")]


def _foul(s: MatchState) -> list[Event]:
    dfn = s.opponent(s.possession)
    z, ch = 2 - s.third, MIRROR[s.channel]
    pid = _pick(s, dfn, z, ch, DEF_W)
    x, y = _xy(s, dfn, z, ch)
    _dead(s, "free_kick")
    return [_event(s, "foul", dfn, player_id=pid, channel=ch, x=x, y=y, outcome="committed")]


def _out(s: MatchState) -> list[Event]:
    team, z = s.possession, s.third
    ch = s.channel if s.channel != "centre" else str(s.rng.choice(["left", "right"]))
    x, y = _xy(s, team, z, ch)
    ev = [_event(s, "out", team, channel=ch, x=x, y=y, outcome="throw_in")]
    s.channel = ch
    if s.rng.random() < P_THROW_TO_OPPONENT:
        _change_possession(s)
    _dead(s, "throw_in")
    return ev


def _shot(s: MatchState) -> list[Event]:
    team, ch = s.possession, s.channel
    dfn = s.opponent(team)
    pid = _pick(s, team, 2, ch, ATT_W)
    x, y = _xy(s, team, 2, ch)
    xg = float(np.clip(XG_MEDIAN[ch] * math.exp(XG_SIGMA * s.rng.standard_normal()), 0.01, 0.8))
    xg = round(xg, 3)
    if s.rng.random() < xg:
        ev = [_event(s, "shot", team, player_id=pid, channel=ch, x=x, y=y, outcome="goal", xg=xg),
              _event(s, "goal", team, player_id=pid, channel=ch, x=x, y=y)]
        s.score[team] += 1
        s.possession, s.third, s.channel = dfn, 1, "centre"
        _dead(s, "kickoff")
        return ev
    u = s.rng.random()
    outcome = "saved" if u < P_SAVED else "blocked" if u < P_SAVED + P_BLOCKED else "off_target"
    ev = [_event(s, "shot", team, player_id=pid, channel=ch, x=x, y=y, outcome=outcome, xg=xg)]
    if outcome == "saved":
        if s.rng.random() < P_CORNER_SAVED:
            _corner(s)
        else:
            s.possession, s.third, s.channel = dfn, 0, "centre"
            _dead(s, "keeper")
    elif outcome == "blocked":
        if s.rng.random() < P_CORNER_BLOCKED:
            _corner(s)
        else:
            _change_possession(s)
    else:
        s.possession, s.third, s.channel = dfn, 0, "centre"
        _dead(s, "goal_kick")
    return ev


def _corner(s: MatchState) -> None:
    s.third = 2
    if s.channel == "centre":
        s.channel = str(s.rng.choice(["left", "right"]))
    _dead(s, "corner")


def _play(s: MatchState) -> list[Event]:
    team, z, ch = s.possession, s.third, s.channel
    f = math.exp(K_EDGE * edge(s, team, z, ch))
    mult = _score_mult(s, team)
    p_shot = P_SHOT * f * mult * (CENTRE_SHOT_MULT if ch == "centre" else 1.0) if z == 2 else 0.0
    actions = (
        (p_shot, _shot),
        (P_ADV[z] * f * mult, _advance),
        (P_TO[z] / f, _turnover),
        (P_OUT, _out),
        (P_FOUL, _foul),
        (P_BACK[z], _back),
        (P_SWITCH, _switch),
    )
    u = s.rng.random()
    for p, action in actions:
        if u < p:
            return action(s)
        u -= p
    return []


# --- match flow --------------------------------------------------------------

def _restart_event(s: MatchState) -> Event:
    team = s.possession
    x, y = _xy(s, team, s.third, s.channel)
    ev = _event(s, "restart", team, channel=s.channel, x=x, y=y, outcome=s.restart)
    s.restart = None
    return ev


def _start_period(s: MatchState, period: int) -> list[Event]:
    s.period = period
    s.clock_s = 0 if period == 1 else HALF_S
    lo, hi = ADDED_MIN[period]
    s.period_end_s = s.clock_s + HALF_S + 60 * int(s.rng.integers(lo, hi + 1))
    s.possession = s.home if period == 1 else s.away
    s.third, s.channel, s.dead_s = 1, "centre", 0
    s.restart = "kickoff"
    return [_restart_event(s)]


def new_match(scenario: Scenario, seed: int) -> tuple[MatchState, list[Event]]:
    rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence(seed)))
    players: dict[str, Player] = {}
    for team in (scenario.home, scenario.away):
        for i, p in enumerate(team.players):
            players[p.id] = Player(id=p.id, team=team.code, name=p.name, role=p.role, side=p.side,
                                   attack=p.attack, defence=p.defence, pace=p.pace,
                                   stamina=p.stamina, work_rate=p.work_rate, on_pitch=i < 11)
    s = MatchState(match_id=f"{scenario.match_id_prefix}-{seed:04d}", entropy=[seed],
                   home=scenario.home.code, away=scenario.away.code, players=players, rng=rng,
                   score={scenario.home.code: 0, scenario.away.code: 0})
    return s, _start_period(s, 1)


def step(s: MatchState) -> list[Event]:
    """Advance the match by one second and return the events of that second."""
    if s.finished:
        return []
    if s.dead_s > 0:
        s.dead_s -= 1
        events = [] if s.dead_s else [_restart_event(s)]
    else:
        s.in_play_s += 1
        events = _play(s)
    s.clock_s += 1
    if s.clock_s >= s.period_end_s:
        if s.period == 1:
            events += _start_period(s, 2)
        else:
            s.finished = True
    return events


def run_to_end(s: MatchState) -> list[Event]:
    events: list[Event] = []
    while not s.finished:
        events += step(s)
    return events


def run_match(scenario: Scenario, seed: int) -> tuple[MatchState, list[Event]]:
    s, events = new_match(scenario, seed)
    events += run_to_end(s)
    return s, events
