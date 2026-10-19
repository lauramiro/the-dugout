# Demo replay files (seed 2)

- `match.jsonl`: events (contract 1) from `uv run python -m dugout.sim run --seed 2 --out web/public/demo/match.jsonl`.
- `tracking/`: tracking frames (contract 2) thinned from 2 Hz to 1 Hz and split into 10-minute chunks (`index.json`).
- `roster.json`: names and roles from `scenarios/riverside-castleton.yaml`.

**Fixtures, to be replaced by real files in wave 3:**

- `snapshots.jsonl`: snapshots (contract 3) once a match minute. Condition estimates are hand-shaped curves; running counts, score, subs, rates and threat come from the events.
- `cards.json`: decision payloads (contract 4) from `dugout.engine.payload.decide` on those snapshots, with the template narration for each locale and mode.
- `winprob.jsonl`: home win probability per snapshot (engine no-change run). Not one of the four contracts.

Rebuild all of it with `uv run python web/scripts/build_demo_fixtures.py` after rerunning the simulator.
