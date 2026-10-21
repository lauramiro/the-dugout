"""Snapshots (contract 3) and decision points from a recorded events JSONL.

    python -m dugout.stream.snapshots --events data/rfc-cas-0002.jsonl \\
        --scenario scenarios/riverside-castleton.yaml --out data/rfc-cas-0002.snapshots.jsonl

One JSON record per line, in stream order:
    {"kind": "snapshot", "snapshot": {...}}
    {"kind": "decision_point", "id", "t_ms", "period", "team", "trigger", "raised_t_ms",
     "detail", "snapshot"}
    {"kind": "card_closed", "id", "t_ms", "period", "team", "reason"}

Only this command reads the scenario, and from it only each player's id, team, role,
side, whether he starts and his minutes in the last 7 days (public lineup information);
ratings and story levers stay with the simulator.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

from dugout.sim.scenario import load_scenario
from dugout.stream.replay import read_events
from dugout.stream.state_engine import StateEngine
from dugout.stream.triggers import DecisionPoints


def lineup_from_scenario(path: str | Path) -> list[dict]:
    scenario = load_scenario(path)
    return [{"id": p.id, "team": team.code, "role": p.role, "side": p.side, "starting": p in team.starters,
             "recent_minutes": p.recent_minutes}
            for team in (scenario.home, scenario.away) for p in team.players]


def process(events: Iterable[dict], lineup: list[dict], prior90: float = 1.35) -> Iterator[dict]:
    engine, points = StateEngine(lineup, prior90=prior90), DecisionPoints()

    def records(ticks):
        for snapshot, new in ticks:
            yield {"kind": "snapshot", "snapshot": snapshot}
            yield from points.on_snapshot(snapshot, new)

    for e in events:
        yield from records(engine.feed(e))
    yield from records(engine.finish())
    yield from points.finish()


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="dugout.stream.snapshots")
    ap.add_argument("--events", type=Path, required=True, help="events JSONL (contract 1)")
    ap.add_argument("--scenario", type=Path, required=True, help="scenario YAML, for the lineup")
    ap.add_argument("--out", type=Path, required=True, help="snapshots and decision points JSONL")
    ap.add_argument("--prior", type=float, default=1.35, help="pre-match xG/90 for each team")
    args = ap.parse_args(argv)

    counts: dict[str, int] = {}
    last = None
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        for r in process(read_events(args.events), lineup_from_scenario(args.scenario), args.prior):
            f.write(json.dumps(r) + "\n")
            counts[r["kind"]] = counts.get(r["kind"], 0) + 1
            if r["kind"] == "snapshot":
                last = r["snapshot"]
            elif r["kind"] == "decision_point":
                print(f"{r['t_ms'] // 60_000:>3}' {r['team']} {r['trigger']} {r['detail']}", file=sys.stderr)
    score = " ".join(f"{t} {g}" for t, g in last["score"].items()) if last else "no events"
    print(f"{args.out}: {counts.get('snapshot', 0)} snapshots, {counts.get('decision_point', 0)} "
          f"decision points; final {score}", file=sys.stderr)


if __name__ == "__main__":
    main()
