"""Home win probability for one snapshot: the engine's no-change run, as in the demo files.

web/scripts/build_demo_fixtures.py writes the replay's series with this function (n=20,000,
seeded by t_ms); the live runner publishes one point per match minute with fewer runs.
"""

from __future__ import annotations

from numpy.random import SeedSequence

from dugout.engine.payload import _exposed_player
from dugout.engine.wp import Flank, simulate_diff, summarize

MIN_MS = 60_000


def situation(snapshot: dict, team: str) -> dict:
    """The same situation decide() builds for this snapshot and team."""
    opp = next(t for t in snapshot["score"] if t != team)
    player = _exposed_player(snapshot, team)
    flank = None
    if player is not None:
        flank = Flank(c0=player["condition_est"], drain=max(0.0, -player.get("trend_per_min", 0.0)))
    return dict(t0=snapshot["t_ms"] // MIN_MS, home_goals=snapshot["score"][team], away_goals=snapshot["score"][opp],
                lam_home90=snapshot["rates"][team]["for90"], lam_away90=snapshot["rates"][team]["against90"], flank=flank)


def winprob_point(snapshot: dict, home: str, n: int = 4000, seed: int | None = None) -> dict:
    at = situation(snapshot, home)
    if snapshot["period"] == 1:
        at["t0"] = min(at["t0"], 45)  # first-half added time still has a whole half to come
    diff = simulate_diff(**at, seed=SeedSequence(snapshot["t_ms"] if seed is None else seed), n=n)
    o = summarize(diff)
    return {"kind": "winprob", "period": snapshot["period"], "t_ms": snapshot["t_ms"], "team": home,
            "win": round(o.win, 3), "draw": round(o.draw, 3), "loss": round(o.loss, 3)}
