"""How well the observable condition estimate tracks hidden condition.

Plays seeds of the scenario (played-midweek lever on RFC-03) to a little past 62',
reads hidden condition every match minute, and feeds the events to the state engine.
Hidden values are read here only; the state engine never sees them.

Reports, over all seeds:
  r62     correlation of condition_est with hidden condition across the outfield
          players on at 62' who have a complete baseline
  pooled  the same over every minute from the end of each baseline to 64'
  rel62   correlation at 62' with condition relative to the player's own baseline
          (his mean hidden condition over his first 20 minutes), what the estimate aims at
  below   seeds where RFC-03 reads below the median of the other Riverside starters at 62'
  cover   share of starter-minutes whose 90% band holds condition relative to his own
          baseline, clipped to 0.3-1.0
  cover_abs  the same against hidden condition itself, which the estimate aims at once it
          knows a player's recent minutes
  width   median band width, overall and by role, at 62'
  ceiling the same correlations for hidden relative condition itself (no noise at all)

    uv run python eval/condition_estimate.py --seeds 20 [--first 1] [--no-recent] [--out eval/results/x.json]

--no-recent drops recent_minutes from the lineup, which gives the estimate before it knew them.

--triggers plays whole matches through the state engine and dugout.stream.triggers instead and
reports the condition_drop cards: per match for each team, how often Riverside's first one is
RFC-03, its minute against the hidden fade (first minute below managers.FADE), and the share of
cards whose player is within 0.05 of FADE at the card. --scan does the same over a grid of
margins and lines, which is how the constants in triggers.py were chosen on seeds 1-20.

    uv run python eval/condition_estimate.py --triggers --seeds 20 [--scan]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dugout.sim import managers  # noqa: E402
from dugout.sim.match import new_match, step  # noqa: E402
from dugout.sim.scenario import load_scenario  # noqa: E402
from dugout.stream.snapshots import lineup_from_scenario  # noqa: E402
from dugout.stream import triggers  # noqa: E402
from dugout.stream.state_engine import StateEngine  # noqa: E402

SCENARIO = ROOT / "scenarios" / "riverside-castleton.yaml"
T62 = 62 * 60
FOCUS = "RFC-03"


def play(scenario, seed):
    """Events to 64' and hidden condition at each whole match minute, keyed (period, t_ms)."""
    s, events = new_match(scenario, seed)
    hidden = {}
    while not s.finished and (s.period, s.clock_s) <= (2, T62 + 120):
        events += step(s)
        if s.clock_s % 60 == 0:
            hidden[(s.period, s.clock_s * 1000)] = {p.id: p.condition for p in s.players.values()}
    return events, hidden


def play_all(scenario, seed):
    """Every event and hidden condition at each whole match minute, keyed (period, t_ms)."""
    s, events = new_match(scenario, seed)
    hidden = {}
    while not s.finished:
        events += step(s)
        if s.clock_s % 60 == 0:
            hidden[(s.period, s.clock_s * 1000)] = {p.id: p.condition for p in s.players.values()}
    return [e.to_dict() for e in events], hidden


def condition_cards(lineup, events, margin, line):
    """The condition_drop cards that open, with the trigger's constants set to margin and line."""
    saved = triggers.CONDITION_MARGIN, triggers.CONDITION_LINE
    triggers.CONDITION_MARGIN, triggers.CONDITION_LINE = margin, line
    try:
        engine, points, out = StateEngine(lineup), triggers.DecisionPoints(), []
        for e in events:
            for snap, new in engine.feed(e):
                out += points.on_snapshot(snap, new)
        for snap, new in engine.finish():
            out += points.on_snapshot(snap, new)
        out += points.finish()
    finally:
        triggers.CONDITION_MARGIN, triggers.CONDITION_LINE = saved
    return [r for r in out if r["kind"] == "decision_point" and r["trigger"] == "condition_drop"]


def measure_triggers(matches, lineup, margin, line):
    per_team = {"RFC": 0, "CAS": 0}
    first = honest = total = 0
    lags = []
    for events, hidden in matches:
        cards = condition_cards(lineup, events, margin, line)
        for c in cards:
            per_team[c["team"]] += 1
            h = hidden.get((c["period"], c["t_ms"] // 60_000 * 60_000), {}).get(c["detail"]["player_id"])
            if h is not None:
                total += 1
                honest += h < managers.FADE + 0.05
        rfc = [c for c in cards if c["team"] == "RFC"]
        if rfc and rfc[0]["detail"]["player_id"] == FOCUS:
            first += 1
            fade = next((k for k in sorted(hidden) if hidden[k][FOCUS] < managers.FADE), None)
            if fade is not None:
                lags.append((rfc[0]["t_ms"] - fade[1]) // 60_000)
    n = len(matches)
    return {"margin": margin, "line": line, "matches": n,
            "cards_per_match": {t: round(v / n, 2) for t, v in per_team.items()},
            "rfc_first_is_rfc03": first,
            "lag_minutes_median": float(np.median(lags)) if lags else None,
            "lag_minutes_iqr": [float(np.percentile(lags, q)) for q in (25, 75)] if lags else None,
            "honest": round(honest / total, 3) if total else None}


def snapshots(lineup, events):
    engine, snaps = StateEngine(lineup), []
    for e in events:
        snaps += [snap for snap, _ in engine.feed(e.to_dict())]
    return snaps + [snap for snap, _ in engine.finish()]


def corr(pairs):
    return float(np.corrcoef(np.array(pairs).T)[0, 1]) if len(pairs) > 2 else float("nan")


def measure(seeds, recent=True):
    scenario = load_scenario(SCENARIO)
    lineup = lineup_from_scenario(SCENARIO)
    if not recent:
        lineup = [{k: v for k, v in p.items() if k != "recent_minutes"} for p in lineup]
    starters = {p.id for t in (scenario.home, scenario.away) for p in t.starters}
    at62, pooled, rel62, ceil62, ceil_pooled = [], [], [], [], []
    below = valid = covered = covered_abs = counted = 0
    widths: dict[str, list[float]] = {}
    for seed in seeds:
        events, hidden = play(scenario, seed)
        own = {pid: np.mean([hidden[(1, m * 60_000)][pid] for m in range(1, 21)]) for pid in starters}
        for snap in snapshots(lineup, events):
            key = (snap["period"], snap["t_ms"])
            h = hidden.get(key)
            if h is None:
                continue
            ests = {p["id"]: p for p in snap["players"]
                    if p["condition_est"] is not None and p["condition_band"] is not None}
            pooled += [(p["condition_est"], h[pid]) for pid, p in ests.items()]
            ceil_pooled += [(h[pid] / own[pid], h[pid]) for pid in ests if pid in starters]
            for pid, p in ests.items():
                if pid in starters:
                    lo, hi = p["condition_band"]
                    covered += lo <= min(1.0, max(0.3, h[pid] / own[pid])) <= hi
                    covered_abs += lo <= min(1.0, max(0.3, h[pid])) <= hi
                    counted += 1
            if key != (2, T62 * 1000):
                continue
            at62 += [(p["condition_est"], h[pid]) for pid, p in ests.items()]
            rel62 += [(p["condition_est"], h[pid] / own[pid]) for pid, p in ests.items() if pid in starters]
            ceil62 += [(h[pid] / own[pid], h[pid]) for pid in ests if pid in starters]
            for p in ests.values():
                widths.setdefault(p["role"], []).append(p["condition_band"][1] - p["condition_band"][0])
            others = [p["condition_est"] for pid, p in ests.items()
                      if pid in starters and pid.startswith("RFC") and pid != FOCUS]
            if FOCUS in ests:
                valid += 1
                below += ests[FOCUS]["condition_est"] < np.median(others)
    every = [w for ws in widths.values() for w in ws]
    return {
        "seeds": [min(seeds), max(seeds)], "recent_minutes": recent,
        "r62": round(corr(at62), 3), "n62": len(at62),
        "pooled": round(corr(pooled), 3), "n_pooled": len(pooled),
        "rel62": round(corr(rel62), 3),
        "below": int(below), "valid": valid,
        "cover": round(covered / counted, 3) if counted else None,
        "cover_abs": round(covered_abs / counted, 3) if counted else None,
        "width": round(float(np.median(every)), 3) if every else None,
        "width_by_role": {r: round(float(np.median(w)), 3) for r, w in sorted(widths.items())},
        "ceiling_r62": round(corr(ceil62), 3), "ceiling_pooled": round(corr(ceil_pooled), 3),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument("--first", type=int, default=1)
    ap.add_argument("--no-recent", action="store_true", help="lineup without recent_minutes")
    ap.add_argument("--triggers", action="store_true", help="measure condition_drop cards instead")
    ap.add_argument("--scan", action="store_true", help="with --triggers: a grid of margins and lines")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    seeds = range(args.first, args.first + args.seeds)
    if args.triggers:
        scenario, lineup = load_scenario(SCENARIO), lineup_from_scenario(SCENARIO)
        matches = [play_all(scenario, seed) for seed in seeds]
        grid = ([(m, ln) for m in (0.06, 0.08, 0.10, 0.12) for ln in (1.0, 0.72, 0.70, 0.69, 0.68, 0.67, 0.66)]
                if args.scan else [(triggers.CONDITION_MARGIN, triggers.CONDITION_LINE)])
        result = {"seeds": [min(seeds), max(seeds)],
                  "results": [measure_triggers(matches, lineup, m, ln) for m, ln in grid]}
    else:
        result = measure(seeds, recent=not args.no_recent)
    print(json.dumps(result, indent=1))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
