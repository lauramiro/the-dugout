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
  width   median band width, overall and by role, at 62'
  ceiling the same correlations for hidden relative condition itself (no noise at all)

    uv run python eval/condition_estimate.py --seeds 20 [--out eval/results/x.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dugout.sim.match import new_match, step  # noqa: E402
from dugout.sim.scenario import load_scenario  # noqa: E402
from dugout.stream.state_engine import StateEngine  # noqa: E402

SCENARIO = ROOT / "scenarios" / "riverside-castleton.yaml"
T62 = 62 * 60
FOCUS = "RFC-03"


def lineup_of(scenario):
    return [{"id": p.id, "team": t.code, "role": p.role, "side": p.side, "starting": i < 11}
            for t in (scenario.home, scenario.away) for i, p in enumerate(t.players)]


def play(scenario, seed):
    """Events to 64' and hidden condition at each whole match minute, keyed (period, t_ms)."""
    s, events = new_match(scenario, seed)
    hidden = {}
    while not s.finished and (s.period, s.clock_s) <= (2, T62 + 120):
        events += step(s)
        if s.clock_s % 60 == 0:
            hidden[(s.period, s.clock_s * 1000)] = {p.id: p.condition for p in s.players.values()}
    return events, hidden


def snapshots(lineup, events):
    engine, snaps = StateEngine(lineup), []
    for e in events:
        snaps += [snap for snap, _ in engine.feed(e.to_dict())]
    return snaps + [snap for snap, _ in engine.finish()]


def corr(pairs):
    return float(np.corrcoef(np.array(pairs).T)[0, 1]) if len(pairs) > 2 else float("nan")


def measure(seeds):
    scenario = load_scenario(SCENARIO)
    lineup = lineup_of(scenario)
    starters = {p.id for t in (scenario.home, scenario.away) for p in t.starters}
    at62, pooled, rel62, ceil62, ceil_pooled = [], [], [], [], []
    below = valid = covered = counted = 0
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
        "seeds": [min(seeds), max(seeds)],
        "r62": round(corr(at62), 3), "n62": len(at62),
        "pooled": round(corr(pooled), 3), "n_pooled": len(pooled),
        "rel62": round(corr(rel62), 3),
        "below": int(below), "valid": valid,
        "cover": round(covered / counted, 3) if counted else None,
        "width": round(float(np.median(every)), 3) if every else None,
        "width_by_role": {r: round(float(np.median(w)), 3) for r, w in sorted(widths.items())},
        "ceiling_r62": round(corr(ceil62), 3), "ceiling_pooled": round(corr(ceil_pooled), 3),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument("--first", type=int, default=1)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    result = measure(range(args.first, args.first + args.seeds))
    print(json.dumps(result, indent=1))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
