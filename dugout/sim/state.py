"""Match state: one serialisable object that can be forked.

Everything the simulator needs to continue a match lives here, including the
random generator's state, so a match can be saved mid-play and resumed with an
identical event stream. `fork(branch)` copies the state and gives the copy a
fresh, independent random stream derived from the match entropy, the moment of
the fork and the branch number. Two forks with the same branch number draw the
same numbers, which is what common random numbers across options needs.
"""

from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field, fields

import numpy as np

HALF_S = 45 * 60


@dataclass
class Player:
    id: str
    team: str
    name: str
    role: str
    side: str
    attack: float
    defence: float
    pace: float
    stamina: float
    work_rate: float
    condition: float = 1.0  # hidden; the engine never sees it
    on_pitch: bool = True


@dataclass
class MatchState:
    match_id: str
    entropy: list[int]
    home: str
    away: str
    players: dict[str, Player]
    rng: np.random.Generator
    score: dict[str, int] = field(default_factory=dict)
    period: int = 1
    clock_s: int = 0
    period_end_s: int = HALF_S
    possession: str = ""
    third: int = 1  # 0 own third, 1 middle, 2 attacking third, for the team in possession
    channel: str = "centre"  # from the team in possession's view
    dead_s: int = 0  # seconds of dead ball left before the restart
    restart: str | None = None  # restart kind pending while the ball is dead
    seq: int = 0
    in_play_s: int = 0
    finished: bool = False
    load: dict[str, float] = field(default_factory=dict)  # this minute's high-intensity cost, by player
    managers: list[str] = field(default_factory=list)  # teams whose simulated manager makes changes
    slow_managers: list[str] = field(default_factory=list)
    pending: list[dict] = field(default_factory=list)  # changes decided on, waiting for their moment
    subs_used: dict[str, int] = field(default_factory=dict)
    windows_used: dict[str, int] = field(default_factory=dict)  # in-play windows; half-time is free
    attacking_subs: dict[str, int] = field(default_factory=dict)
    subbed_off: list[str] = field(default_factory=list)

    def opponent(self, team: str) -> str:
        return self.away if team == self.home else self.home

    def to_dict(self) -> dict:
        d = {f.name: getattr(self, f.name) for f in fields(self) if f.name not in ("players", "rng")}
        d["players"] = [asdict(p) for p in self.players.values()]
        d["rng"] = self.rng.bit_generator.state
        return copy.deepcopy(d)

    @classmethod
    def from_dict(cls, d: dict) -> MatchState:
        d = copy.deepcopy(d)
        rng = np.random.Generator(np.random.PCG64())
        rng.bit_generator.state = d.pop("rng")
        players = {p["id"]: Player(**p) for p in d.pop("players")}
        return cls(players=players, rng=rng, **d)

    def fork(self, branch: int) -> MatchState:
        child = copy.deepcopy(self)
        seed = np.random.SeedSequence([*self.entropy, self.period, self.clock_s, self.seq, branch])
        child.rng = np.random.Generator(np.random.PCG64(seed))
        return child
