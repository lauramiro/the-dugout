"""Load and validate a match scenario (teams, squads, ratings) from YAML."""

from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class TeamSpec:
    code: str
    name: str
    players: tuple[PlayerSpec, ...]  # first STARTERS start

    @property
    def starters(self) -> tuple[PlayerSpec, ...]:
        return self.players[:STARTERS]


@dataclass(frozen=True, slots=True)
class Scenario:
    match_id_prefix: str
    home: TeamSpec
    away: TeamSpec


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
    if [p.role for p in players[:STARTERS]].count("GK") != 1:
        raise ValueError(f"{code}: starters need exactly one GK")
    return TeamSpec(code=code, name=raw["name"], players=players)


def load_scenario(path: str | Path) -> Scenario:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    home, away = _team(raw["home"]), _team(raw["away"])
    if home.code == away.code:
        raise ValueError("home and away codes must differ")
    return Scenario(match_id_prefix=raw["match_id_prefix"], home=home, away=away)
