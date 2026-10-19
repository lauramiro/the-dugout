"""Command line: run one match to JSONL, or check realism over many seeds.

    python -m dugout.sim run --seed 1 --out data/rfc-cas-0001.jsonl
        (also writes data/rfc-cas-0001.tracking.jsonl)
    python -m dugout.sim realism --seeds 100
    python -m dugout.sim gap --seed 1 --minute 62 --team RFC --off RFC-03 --on RFC-15
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dugout.sim.counterfactual import NO_CHANGE, Option, play_to, true_gap
from dugout.sim.match import new_match, run_match
from dugout.sim.realism import TARGETS, realism, summarise
from dugout.sim.scenario import load_scenario
from dugout.sim.tracking import run_with_tracking

DEFAULT_SCENARIO = Path(__file__).resolve().parents[2] / "scenarios" / "riverside-castleton.yaml"


def _write_jsonl(path: Path, rows) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(prog="dugout.sim")
    ap.add_argument("--scenario", type=Path, default=DEFAULT_SCENARIO)
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="simulate one match")
    run.add_argument("--seed", type=int, required=True)
    run.add_argument("--out", type=Path, help="write events as JSONL, and tracking frames beside them")
    rl = sub.add_parser("realism", help="summarise many seeds against the realism targets")
    rl.add_argument("--seeds", type=int, default=100)
    gp = sub.add_parser("gap", help="true gap between no change and a substitution, from forks")
    gp.add_argument("--seed", type=int, required=True)
    gp.add_argument("--minute", type=int, default=62)
    gp.add_argument("--team", required=True)
    gp.add_argument("--off", required=True, help="player going off")
    gp.add_argument("--on", required=True, help="player coming on")
    gp.add_argument("--n", type=int, default=500, help="forks per option")
    args = ap.parse_args()

    scenario = load_scenario(args.scenario)
    if args.cmd == "run":
        if args.out:
            s, events = new_match(scenario, args.seed)
            more, frames = run_with_tracking(s)
            events += more
            args.out.parent.mkdir(parents=True, exist_ok=True)
            _write_jsonl(args.out, (e.to_dict() for e in events))
            _write_jsonl(args.out.with_name(args.out.stem + ".tracking.jsonl"), frames)
        else:
            s, events = run_match(scenario, args.seed)
        sm = summarise(s, events)
        print(f"{s.match_id}: {s.home} {sm.home_goals}-{sm.away_goals} {s.away} | "
              f"shots {sm.shots}, xG {sm.xg}, ball in play {sm.in_play_min} min, {len(events)} events")
    elif args.cmd == "gap":
        s, _ = new_match(scenario, args.seed)
        play_to(s, args.minute)
        sub = Option(f"sub_{args.off}", f"{args.off} off, {args.on} on", subs=((args.off, args.on),))
        print(f"{s.match_id} at {s.clock_s // 60}': {s.home} {s.score[s.home]}-{s.score[s.away]} {s.away}, "
              f"{args.n} forks per option, common random numbers")
        for r in true_gap(s, args.team, [NO_CHANGE, sub], args.n):
            print(f"{r.id:<16} win {r.win:.3f}  draw {r.draw:.3f}  loss {r.loss:.3f}  xpts {r.xpts:.2f}  "
                  f"true gap {100 * r.delta_win:+.1f} pts win, {r.delta_xpts:+.2f} xpts")
    else:
        stats = realism(scenario, range(1, args.seeds + 1))
        for key, v in stats.items():
            target = TARGETS.get(key)
            print(f"{key:<12} {v}" + (f"  target {target}" if target else ""))


if __name__ == "__main__":
    main()
