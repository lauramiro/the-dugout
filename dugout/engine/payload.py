"""Snapshot (contract 3) in, decision payload (contract 4) out.

Reads snapshot fields only; never imports the simulator package. Rates and effects are
illustrative assumptions on synthetic data. The snapshot carries no positions, so the
exposed flank is taken to be the higher-threat of the team's left and right channels,
and the exposed player the outfielder with the lowest condition estimate.
"""
from __future__ import annotations

from numpy.random import SeedSequence

from dugout.engine.options import OptionResult, default_options, evaluate, strength_label
from dugout.engine.wp import Flank


def _exposed_player(snapshot: dict, team: str) -> dict | None:
    tired = [p for p in snapshot["players"]
             if p["id"].startswith(f"{team}-") and p.get("condition_est") is not None]
    return min(tired, key=lambda p: p["condition_est"], default=None)


def _flank_channel(snapshot: dict, team: str) -> tuple[str, float] | None:
    threat = snapshot.get("threat_by_channel", {})
    flanks = [(c, threat[c]) for c in (f"{team}_left", f"{team}_right") if c in threat]
    return max(flanks, key=lambda cv: cv[1], default=None)


def _recommend(results: list[OptionResult]) -> dict:
    """Best win probability; ties keep no change. Gap is to no change, or to the
    runner-up when no change is itself best."""
    best = results[0]
    for r in results[1:]:
        if r.win > best.win:
            best = r
    if best.id == "no_change":
        rest = [r.win for r in results[1:]]
        gap = best.win - max(rest) if rest else 0.0
    else:
        gap = best.win - results[0].win
    return {"option_id": best.id, "strength": strength_label(gap * 100)}


def _option_dict(r: OptionResult) -> dict:
    d = {"id": r.id, "label": r.label, "win": round(r.win, 3), "draw": round(r.draw, 3),
         "loss": round(r.loss, 3), "xpts": round(r.xpts, 2), "delta_win": round(r.delta_win, 3)}
    if r.ci90 is not None:
        d["ci90"] = [round(r.ci90[0], 3), round(r.ci90[1], 3)]
    return d


def decide(snapshot: dict, team: str, trigger: str, seed: SeedSequence | None = None, *,
           n: int = 20_000) -> dict:
    opp = next(t for t in snapshot["score"] if t != team)
    minute = snapshot["t_ms"] // 60_000
    player = _exposed_player(snapshot, team)
    flank = None
    if player is not None:
        flank = Flank(c0=player["condition_est"], drain=max(0.0, -player.get("trend_per_min", 0.0)))
    situation = dict(t0=minute, home_goals=snapshot["score"][team], away_goals=snapshot["score"][opp],
                     lam_home90=snapshot["rates"][team]["for90"],
                     lam_away90=snapshot["rates"][team]["against90"], flank=flank)

    options = default_options(minute)
    if flank is None or snapshot["subs_left"].get(team, 0) <= 0:
        options = [o for o in options if o.id != "sub_like_for_like"]
    elif player is not None:
        options = [o if o.id != "sub_like_for_like"
                   else type(o)(o.id, f"Like-for-like substitution for {player['id']}", sub_at=minute)
                   for o in options]
    results = evaluate(situation, options, seed if seed is not None else SeedSequence(snapshot["t_ms"]), n=n)

    evidence = []
    if player is not None:
        evidence.append({"type": "condition", "player_id": player["id"],
                         "value": player["condition_est"], "trend_per_min": player.get("trend_per_min", 0.0)})
        channel = _flank_channel(snapshot, team)
        if channel is not None:
            evidence.append({"type": "flank_threat", "channel": channel[0], "share": channel[1]})
    second = snapshot["t_ms"] // 1000 % 60
    return {"decision_id": f"{team.lower()}-{minute}-{second:02d}", "t_ms": snapshot["t_ms"], "team": team,
            "trigger": trigger, "options": [_option_dict(r) for r in results],
            "recommendation": _recommend(results), "evidence": evidence, "manager_action": None}
