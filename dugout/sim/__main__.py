"""Command line: run one match to JSONL, or check realism over many seeds.

    python -m dugout.sim run --seed 1 --out data/rfc-cas-0001.jsonl
        (also writes data/rfc-cas-0001.tracking.jsonl)
    python -m dugout.sim realism --seeds 100
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

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
    else:
        stats = realism(scenario, range(1, args.seeds + 1))
        for key, v in stats.items():
            target = TARGETS.get(key)
            print(f"{key:<12} {v}" + (f"  target {target}" if target else ""))


if __name__ == "__main__":
    main()
