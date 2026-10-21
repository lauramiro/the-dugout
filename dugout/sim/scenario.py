"""Load and validate a match scenario (teams, squads, ratings) from YAML."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from dugout.contracts import CHANNELS

ROLES = ("GK", "CB", "FB", "CM", "W", "ST")
RATINGS = ("attack", "defence", "pace", "stamina", "work_rate")
STARTERS = 11
SQUAD_SIZE = 18


@dataclass(frozen=True, slots=True)
class PlayerSpec:
    id: str
    name: str
    role: str
    side: str
    attack: float
    defence: float
    pace: float
    stamina: float
    work_rate: float
    # Minutes played in the last 7 days: public lineup information for the state engine.
    # The simulator never reads it; hidden starting condition is the played_midweek lever.
    recent_minutes: int = 0


@dataclass(frozen=True, slots=True)
class TeamSpec:
    code: str
    name: str
    players: tuple[PlayerSpec, ...]  # first STARTERS start

    @property
    def starters(self) -> tuple[PlayerSpec, ...]:
        return self.players[:STARTERS]


@dataclass(frozen=True, slots=True)
class Levers:
    """Story levers set in the scenario. All default to off."""

    start_condition: dict[str, float] = field(default_factory=dict)  # "played midweek"
    slow_manager: frozenset[str] = frozenset()  # team codes whose manager reacts late


@dataclass(frozen=True, slots=True)
class Scenario:
    match_id_prefix: str
    home: TeamSpec
    away: TeamSpec
    levers: Levers = Levers()


def _team(raw: dict) -> TeamSpec:
    code = raw["code"]
    players = tuple(PlayerSpec(**p) for p in raw["players"])
    if len(players) != SQUAD_SIZE:
        raise ValueError(f"{code}: expected {SQUAD_SIZE} players, got {len(players)}")
    if len({p.id for p in players}) != len(players):
        raise ValueError(f"{code}: duplicate player ids")
    for p in players:
        if not p.id.startswith(f"{code}-"):
            raise ValueError(f"{p.id}: id must start with {code}-")
        if p.role not in ROLES:
            raise ValueError(f"{p.id}: unknown role {p.role}")
        if p.side not in CHANNELS:
            raise ValueError(f"{p.id}: unknown side {p.side}")
        for r in RATINGS:
            if not 0.0 <= getattr(p, r) <= 1.0:
                raise ValueError(f"{p.id}: {r} must be between 0 and 1")
        if isinstance(p.recent_minutes, bool) or not isinstance(p.recent_minutes, int) or p.recent_minutes < 0:
            raise ValueError(f"{p.id}: recent_minutes must be a whole number of minutes, 0 or more")
    if [p.role for p in players[:STARTERS]].count("GK") != 1:
        raise ValueError(f"{code}: starters need exactly one GK")
    return TeamSpec(code=code, name=raw["name"], players=players)


def _levers(raw: dict, home: TeamSpec, away: TeamSpec) -> Levers:
    ids = {p.id for team in (home, away) for p in team.players}
    start = {str(k): float(v) for k, v in (raw.get("played_midweek") or {}).items()}
    for pid, c in start.items():
        if pid not in ids:
            raise ValueError(f"played_midweek: unknown player {pid}")
        if not 0.0 < c <= 1.0:
            raise ValueError(f"played_midweek: {pid} condition must be in (0, 1]")
    slow = frozenset(raw.get("slow_manager") or ())
    if not slow <= {home.code, away.code}:
        raise ValueError(f"slow_manager: unknown team in {sorted(slow)}")
    return Levers(start_condition=start, slow_manager=slow)


def load_scenario(path: str | Path) -> Scenario:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    home, away = _team(raw["home"]), _team(raw["away"])
    if home.code == away.code:
        raise ValueError("home and away codes must differ")
    return Scenario(match_id_prefix=raw["match_id_prefix"], home=home, away=away,
                    levers=_levers(raw.get("levers") or {}, home, away))
