"""Counterfactual check: the engine's estimated gap against the true gap from forks.

    uv run python -m eval.counterfactual pairs [--forks 500] [--workers 4]
    uv run python -m eval.counterfactual calibrate
    uv run python -m eval.counterfactual plot
    uv run python -m eval.counterfactual all

For every seed: run the match, feed its events through the state engine and the
triggers, and at each decision point compare two numbers for the same change, the
deciding team's like-for-like substitution of the player the engine picks:

- engine gap: `decide(snapshot, team, trigger)`, win probability of
  `sub_like_for_like` minus no change, with its 90% interval. The engine reads the
  snapshot only.
- true gap: the simulator's hidden state at the same (period, t_ms), forked and
  played to the end with that player off for a like-for-like bench player, against
  no change, on common random numbers (`dugout.sim.counterfactual`).

The snapshot at (period, t_ms) covers the events before t_ms, and the simulator is
stepped to exactly that second, so both sides see the same match. Story points add
moments the demo is built around that the triggers may not raise.

`pairs` is the expensive step (forks) and writes `eval/results/counterfactual_pairs.csv`
with each point's engine inputs, so `calibrate` and `plot` rerun from the CSV alone.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections.abc import Iterator
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.random import SeedSequence

from dugout.engine import wp
from dugout.engine.options import Option as EngineOption
from dugout.engine.options import evaluate
from dugout.engine.payload import _exposed_player, decide
from dugout.engine.wp import Flank
from dugout.sim import managers
from dugout.sim.counterfactual import NO_CHANGE, Option, _results
from dugout.sim.match import new_match, run_to_end, step
from dugout.sim.scenario import load_scenario
from dugout.sim.state import MatchState
from dugout.stream.snapshots import lineup_from_scenario, process

ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / "scenarios" / "riverside-castleton.yaml"
RESULTS = ROOT / "eval" / "results"
PAIRS_CSV = RESULTS / "counterfactual_pairs.csv"
CALIBRATION_JSON = RESULTS / "calibration.json"
SCATTER_SVG = RESULTS / "counterfactual.svg"

DEMO_SEED = 73
FIT_SEEDS = tuple(range(2, 31, 2))  # 15 seeds
TEST_SEEDS = (*range(1, 30, 2), DEMO_SEED)  # 16 seeds; the demo is reported, never fitted
SEEDS = tuple(sorted({*FIT_SEEDS, *TEST_SEEDS}))
FORKS = 500  # per option per point
ENGINE_N = 20_000  # decide()'s default

# (seed, period, t_ms, team, player off): the demo's fade at 64', RFC-03 off.
STORY_POINTS = ((DEMO_SEED, 2, 64 * 60_000, "RFC", "RFC-03"),)

ILLUSTRATIVE = {"slope": 0.6, "floor": 0.8, "bench": 1.03}  # wp.py before calibration

COLUMNS = ("seed", "set", "point_id", "source", "team", "trigger", "period", "t_ms", "minute",
           "goals_for", "goals_against", "for90", "against90", "off", "off_role", "on",
           "condition_est", "trend_per_min", "opp_condition_est", "opp_trend_per_min", "hidden_condition",
           "engine_gap", "engine_lo", "engine_hi", "true_gap", "true_se", "true_win_base",
           "true_win_sub", "true_dxpts", "forks", "skip")


def seed_set(seed: int) -> str:
    return "fit" if seed in FIT_SEEDS else "test"


# --- engine side ---------------------------------------------------------------

@contextmanager
def constants(slope: float, floor: float) -> Iterator[None]:
    """Temporarily set the engine's fatigue constants (read by simulate_diff at call time)."""
    old = wp.FATIGUE_SLOPE, wp.FATIGUE_FLOOR
    wp.FATIGUE_SLOPE, wp.FATIGUE_FLOOR = slope, floor
    try:
        yield
    finally:
        wp.FATIGUE_SLOPE, wp.FATIGUE_FLOOR = old


def situation(row: dict) -> dict:
    """decide()'s simulate_diff inputs, rebuilt from a pairs row."""
    opp_flank = None
    if row.get("opp_condition_est", "") != "":
        opp_flank = Flank(c0=float(row["opp_condition_est"]), drain=max(0.0, -float(row["opp_trend_per_min"])))
    return dict(t0=int(row["minute"]), home_goals=int(row["goals_for"]), away_goals=int(row["goals_against"]),
                lam_home90=float(row["for90"]), lam_away90=float(row["against90"]),
                flank=Flank(c0=float(row["condition_est"]), drain=max(0.0, -float(row["trend_per_min"]))),
                opp_flank=opp_flank)


def engine_gap(row: dict, slope: float, floor: float, bench: float, n: int = ENGINE_N
               ) -> tuple[float, float, float]:
    """Gap of a like-for-like sub now over no change, with its 90% interval, as decide()
    computes it (same seed, same draws), under the given constants."""
    opts = [EngineOption("no_change", "No change"), EngineOption("sub", "Sub", sub_at=int(row["minute"]))]
    with constants(slope, floor):
        _, sub = evaluate(situation(row), opts, SeedSequence(int(row["t_ms"])), n=n, sub_quality=bench)
    return sub.delta_win, sub.ci90[0], sub.ci90[1]


# --- simulator side ------------------------------------------------------------

def step_to(s: MatchState, period: int, t_ms: int) -> None:
    """Step until the clock reads (period, t_ms): every event before t_ms is played."""
    target = (period, t_ms // 1000)
    while not s.finished and (s.period, s.clock_s) < target:
        step(s)


def like_for_like_bench(s: MatchState, off: str) -> str | None:
    """A bench player in the same role, same side first."""
    p = s.players[off]
    bench = sorted((b for b in s.players.values() if b.team == p.team and not b.on_pitch
                    and b.role == p.role and b.id not in s.subbed_off),
                   key=lambda b: (b.side != p.side, b.id))
    return bench[0].id if bench else None


@dataclass(frozen=True)
class TrueGap:
    gap: float  # win probability, sub minus no change
    se: float  # paired standard error
    win_base: float
    win_sub: float
    dxpts: float


def true_pair(s: MatchState, team: str, off: str, on: str, forks: int) -> TrueGap:
    """`dugout.sim.counterfactual.true_gap` for no change against one sub, keeping the
    branch outcomes so the paired standard error can be given too."""
    base = np.array(_results(s, team, NO_CHANGE, forks))
    sub = np.array(_results(s, team, Option("sub", f"{off} off, {on} on", subs=((off, on),)), forks))
    d = (sub > 0).astype(float) - (base > 0)

    def xpts(r: np.ndarray) -> float:
        return float(3 * np.mean(r > 0) + np.mean(r == 0))

    return TrueGap(gap=float(d.mean()), se=float(d.std(ddof=1) / math.sqrt(forks)),
                   win_base=float(np.mean(base > 0)), win_sub=float(np.mean(sub > 0)),
                   dxpts=xpts(sub) - xpts(base))


# --- pairs ---------------------------------------------------------------------

def decision_points(seed: int) -> tuple[list[dict], dict[tuple[int, int], dict]]:
    """Trigger decision points of one match, and every snapshot by (period, t_ms)."""
    s, events = new_match(load_scenario(SCENARIO), seed)
    events += run_to_end(s)
    points, snaps = [], {}
    for r in process([e.to_dict() for e in events], lineup_from_scenario(SCENARIO)):
        if r["kind"] == "decision_point":
            points.append(r)
        elif r["kind"] == "snapshot":
            snaps[(r["snapshot"]["period"], r["snapshot"]["t_ms"])] = r["snapshot"]
    return points, snaps


def _base_row(seed: int, point_id: str, source: str, team: str, trigger: str, snapshot: dict,
              player: dict | None) -> dict:
    opp = next(t for t in snapshot["score"] if t != team)
    row = dict.fromkeys(COLUMNS, "")
    row.update(seed=seed, set=seed_set(seed), point_id=point_id, source=source, team=team, trigger=trigger,
               period=snapshot["period"], t_ms=snapshot["t_ms"], minute=snapshot["t_ms"] // 60_000,
               goals_for=snapshot["score"][team], goals_against=snapshot["score"][opp],
               for90=snapshot["rates"][team]["for90"], against90=snapshot["rates"][team]["against90"])
    if player is not None:
        row.update(off=player["id"], condition_est=player["condition_est"],
                   trend_per_min=player.get("trend_per_min", 0.0))
    opp_player = _exposed_player(snapshot, opp)
    if opp_player is not None:
        row.update(opp_condition_est=opp_player["condition_est"],
                   opp_trend_per_min=opp_player.get("trend_per_min", 0.0))
    return row


def seed_pairs(seed: int, forks: int = FORKS) -> list[dict]:
    """Every pair of one seed, in match order. Rows that cannot be paired carry `skip`."""
    points, snaps = decision_points(seed)
    todo = []  # (row, decide payload or None)
    for p in points:
        player = _exposed_player(p["snapshot"], p["team"])
        row = _base_row(seed, p["id"], "trigger", p["team"], p["trigger"], p["snapshot"], player)
        payload = decide(p["snapshot"], p["team"], p["trigger"])
        sub = next((o for o in payload["options"] if o["id"] == "sub_like_for_like"), None)
        if sub is None:
            row["skip"] = "engine offers no like-for-like sub"
        else:
            row.update(engine_gap=sub["delta_win"], engine_lo=sub["ci90"][0], engine_hi=sub["ci90"][1])
        todo.append(row)
    for st_seed, period, t_ms, team, off in STORY_POINTS:
        if st_seed != seed:
            continue
        snap = snaps[(period, t_ms)]
        player = next(q for q in snap["players"] if q["id"] == off)
        row = _base_row(seed, f"{team.lower()}-{t_ms // 60_000}-story", "story", team, "story", snap, player)
        gap, lo, hi = engine_gap(row, wp.FATIGUE_SLOPE, wp.FATIGUE_FLOOR, wp.BENCH_QUALITY)
        row.update(engine_gap=round(gap, 3), engine_lo=round(lo, 3), engine_hi=round(hi, 3))
        todo.append(row)
    todo.sort(key=lambda r: (r["period"], r["t_ms"]))

    s, _ = new_match(load_scenario(SCENARIO), seed)
    for row in todo:
        step_to(s, row["period"], row["t_ms"])
        if row["skip"]:
            continue
        team, off = row["team"], row["off"]
        row["off_role"] = s.players[off].role
        row["hidden_condition"] = round(s.players[off].condition, 3)
        on = like_for_like_bench(s, off)
        if not s.players[off].on_pitch:
            row["skip"] = "player not on the pitch in the simulator"
        elif on is None:
            row["skip"] = "no like-for-like player on the bench"
        elif not managers.window_open(s, team, False):
            row["skip"] = "no substitution window left"
        else:
            g = true_pair(s, team, off, on, forks)
            row.update(on=on, true_gap=round(g.gap, 4), true_se=round(g.se, 4),
                       true_win_base=round(g.win_base, 4), true_win_sub=round(g.win_sub, 4),
                       true_dxpts=round(g.dxpts, 4), forks=forks)
    return todo


def write_pairs(rows: list[dict], path: Path = PAIRS_CSV) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)


def read_pairs(path: Path = PAIRS_CSV) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def paired(rows: list[dict]) -> list[dict]:
    return [r for r in rows if not r["skip"] and r["true_gap"] != ""]


def run_pairs(seeds: tuple[int, ...], forks: int, workers: int, out: Path = PAIRS_CSV,
              resume: bool = True) -> list[dict]:
    """Pairs for every seed, saved after each seed. With resume, seeds already in `out`
    at the same fork count are kept and not rerun."""
    rows = read_pairs(out) if resume and out.exists() else []
    other = {int(r["seed"]) for r in rows if r["forks"] not in ("", str(forks))}
    done = {int(r["seed"]) for r in rows} - other
    rows = [r for r in rows if int(r["seed"]) in done and int(r["seed"]) in seeds]
    todo = [s for s in seeds if s not in done]
    if done & set(seeds):
        print(f"kept {len(done & set(seeds))} seeds from {out}", file=sys.stderr)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for seed, got in zip(todo, pool.map(seed_pairs, todo, [forks] * len(todo))):
            print(f"seed {seed:>3} ({seed_set(seed)}): {len(got)} points, {len(paired(got))} paired",
                  file=sys.stderr, flush=True)
            rows += got
            write_pairs(sorted(rows, key=lambda r: (int(r["seed"]), int(r["period"]), int(r["t_ms"]))), out)
    return read_pairs(out)


# --- calibration ---------------------------------------------------------------

GRID = {"slope": (0.0, 0.3, 0.6, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0),
        "floor": (0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0),
        "bench": (0.97, 1.0, 1.03, 1.06)}
FINE_STEP = {"slope": 0.15, "floor": 0.025, "bench": 0.015}  # second pass around the best cell
FIT_N = 5_000  # engine runs per option while searching; reported numbers use ENGINE_N
BOOT = 2_000  # bootstrap resamples over test seeds


def trigger_rows(rows: list[dict], which: str) -> list[dict]:
    """Paired trigger points of one seed set; story points are reported apart."""
    return [r for r in paired(rows) if r["set"] == which and r["source"] == "trigger"]


def engine_gaps(rows: list[dict], c: dict, n: int = ENGINE_N) -> np.ndarray:
    """(gap, lo, hi) per row under constants c."""
    return np.array([engine_gap(r, c["slope"], c["floor"], c["bench"], n) for r in rows]).reshape(-1, 3)


def _sse(args: tuple[list[dict], dict]) -> float:
    rows, c = args
    true = np.array([float(r["true_gap"]) for r in rows])
    return float(np.sum((engine_gaps(rows, c, FIT_N)[:, 0] - true) ** 2))


def fit(rows: list[dict], workers: int) -> tuple[dict, float]:
    """Least squares on the fit points: a grid over the three constants, then a finer
    grid around the best cell. Returns the constants and the mean squared error."""
    keys = ("slope", "floor", "bench")

    def search(cands: list[dict]) -> tuple[dict, float]:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            sse = list(pool.map(_sse, [(rows, c) for c in cands], chunksize=4))
        i = int(np.argmin(sse))
        return cands[i], sse[i] / len(rows)

    best, _ = search([dict(zip(keys, v)) for v in
                      ((s, f, b) for s in GRID["slope"] for f in GRID["floor"] for b in GRID["bench"])])
    fine = [{k: round(best[k] + (d - 1) * FINE_STEP[k], 4) for k, d in zip(keys, ds)}
            for ds in np.ndindex(3, 3, 3)]
    return search([c for c in fine if c["slope"] >= 0])


def metrics(rows: list[dict], gaps: np.ndarray) -> dict:
    """Engine against truth; gaps and errors in points of win probability."""
    true = np.array([float(r["true_gap"]) for r in rows])
    eng, lo, hi = gaps[:, 0], gaps[:, 1], gaps[:, 2]
    err = eng - true
    corr = float(np.corrcoef(eng, true)[0, 1]) if eng.std() > 0 and true.std() > 0 else float("nan")
    return {"n": len(rows), "seeds": len({r["seed"] for r in rows}),
            "mean_engine": round(100 * float(eng.mean()), 2), "mean_true": round(100 * float(true.mean()), 2),
            "mean_error": round(100 * float(err.mean()), 2),
            "mean_abs_error": round(100 * float(np.abs(err).mean()), 2),
            "rmse": round(100 * float(np.sqrt(np.mean(err ** 2))), 2), "correlation": round(corr, 3),
            "sign_agreement": round(float(np.mean(np.sign(np.round(eng, 3)) == np.sign(true))), 3),
            "coverage90": round(float(np.mean((lo <= true) & (true <= hi))), 3),
            "mean_true_se": round(100 * float(np.mean([float(r["true_se"]) for r in rows])), 2)}


def bootstrap(rows: list[dict], gaps: np.ndarray, seed: int = 0) -> dict:
    """90% intervals for mean error and correlation, resampling whole seeds."""
    rng = np.random.default_rng(seed)
    groups: dict[str, list[int]] = {}
    for i, r in enumerate(rows):
        groups.setdefault(r["seed"], []).append(i)
    idx_by_seed = list(groups.values())
    true = np.array([float(r["true_gap"]) for r in rows])
    me, co = [], []
    for _ in range(BOOT):
        idx = np.concatenate([idx_by_seed[j] for j in rng.integers(0, len(idx_by_seed), len(idx_by_seed))])
        e, tr = gaps[idx, 0], true[idx]
        me.append(100 * float(np.mean(e - tr)))
        if e.std() > 0 and tr.std() > 0:
            co.append(float(np.corrcoef(e, tr)[0, 1]))

    def q(xs: list[float]) -> list[float]:
        return [round(float(np.quantile(xs, 0.05)), 3), round(float(np.quantile(xs, 0.95)), 3)]

    return {"mean_error_ci90": q(me), "correlation_ci90": q(co) if co else None}


def _story(rows: list[dict], c: dict) -> list[dict]:
    return [{"point_id": r["point_id"], "seed": int(r["seed"]), "off": r["off"],
             "condition_est": float(r["condition_est"]), "hidden_condition": float(r["hidden_condition"]),
             "engine_gap": round(100 * engine_gap(r, c["slope"], c["floor"], c["bench"])[0], 2),
             "true_gap": round(100 * float(r["true_gap"]), 2), "true_se": round(100 * float(r["true_se"]), 2)}
            for r in paired(rows) if r["source"] == "story"]


def _corr(a: list[float], b: list[float]) -> float:
    return round(float(np.corrcoef(a, b)[0, 1]), 3)


def calibrate(rows: list[dict], workers: int, path: Path = CALIBRATION_JSON) -> dict:
    """Fit on the fit seeds' trigger points; report before and after on the test seeds'."""
    fit_rows, test_rows = trigger_rows(rows, "fit"), trigger_rows(rows, "test")
    fitted, fit_mse = fit(fit_rows, workers)
    both = (("before", ILLUSTRATIVE), ("after", fitted))
    out = {"fit_seeds": list(FIT_SEEDS), "test_seeds": list(TEST_SEEDS),
           "forks": sorted({int(r["forks"]) for r in paired(rows)}), "engine_n": ENGINE_N, "fit_n": FIT_N,
           "points": len(rows), "paired": len(paired(rows)), "fit_points": len(fit_rows),
           "test_points": len(test_rows), "skipped": {}, "illustrative": ILLUSTRATIVE, "fitted": fitted,
           "fit_rmse": round(100 * math.sqrt(fit_mse), 2)}
    for r in rows:
        if r["skip"]:
            out["skipped"][r["skip"]] = out["skipped"].get(r["skip"], 0) + 1
    for name, c in both:
        g = engine_gaps(test_rows, c)
        out[name] = {"test": {**metrics(test_rows, g), **bootstrap(test_rows, g)}, "story": _story(rows, c)}
    out["test_by_trigger"] = {}
    for trig in sorted({r["trigger"] for r in test_rows}):
        sub = [r for r in test_rows if r["trigger"] == trig]
        out["test_by_trigger"][trig] = {name: metrics(sub, engine_gaps(sub, c)) for name, c in both}
    true = [float(r["true_gap"]) for r in test_rows]
    hidden = [float(r["hidden_condition"]) for r in test_rows]
    est = [float(r["condition_est"]) for r in test_rows]
    out["test_inputs"] = {"corr_est_hidden": _corr(est, hidden), "corr_hidden_true_gap": _corr(hidden, true),
                          "corr_est_true_gap": _corr(est, true),
                          "mean_condition_est": round(float(np.mean(est)), 3),
                          "mean_hidden_condition": round(float(np.mean(hidden)), 3),
                          "share_true_gap_negative": round(float(np.mean(np.array(true) < 0)), 3)}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    return out


# --- scatter plot --------------------------------------------------------------

SIZE, PAD, TOP, PANEL_W = 360.0, 56.0, 44.0, 460

CSS = """
  :root { --bg: #ffffff; --ink: #1f2328; --muted: #656d76; --line: #d0d7de;
          --fit: #8c959f; --test: #0969da; --story: #bc4c00; }
  @media (prefers-color-scheme: dark) {
    :root { --bg: #0d1117; --ink: #e6edf3; --muted: #9198a1; --line: #30363d;
            --fit: #6e7681; --test: #4493f8; --story: #f0883e; } }
  svg { background: var(--bg); font-family: system-ui, sans-serif; }
  .title { fill: var(--ink); font-size: 15px; font-weight: 600; text-anchor: middle; }
  .axis { fill: var(--ink); font-size: 12px; text-anchor: middle; }
  .note { fill: var(--muted); font-size: 11px; }
  .tick { fill: var(--muted); font-size: 11px; text-anchor: middle; }
  .end { text-anchor: end; } .start { text-anchor: start; }
  .frame { fill: none; stroke: var(--line); }
  .grid { stroke: var(--line); stroke-width: 0.5; }
  .diag { stroke: var(--ink); stroke-width: 1; stroke-dasharray: 4 3; }
  .whisker { stroke-width: 1; opacity: 0.3; }
  .whisker.fit { stroke: var(--fit); } .whisker.test { stroke: var(--test); }
  .whisker.story { stroke: var(--story); opacity: 0.8; }
  .pt.fit { fill: none; stroke: var(--fit); stroke-width: 1.2; }
  .pt.test { fill: var(--test); fill-opacity: 0.75; }
  .pt.story { fill: var(--story); stroke: var(--bg); stroke-width: 1; }
"""


def _panel(rows: list[dict], gaps: np.ndarray, x0: float, title: str, note: str, lim: int) -> list[str]:
    left, bottom = x0 + PAD, TOP + SIZE

    def px(v: float) -> float:
        return round(left + (v + lim) / (2 * lim) * SIZE, 1)

    def py(v: float) -> float:
        return round(bottom - (v + lim) / (2 * lim) * SIZE, 1)

    def clip(v: float) -> float:
        return max(-lim, min(lim, v))

    out = [f'<text x="{left + SIZE / 2}" y="24" class="title">{title}</text>',
           f'<text x="{left + SIZE / 2}" y="38" class="note" text-anchor="middle">{note}</text>',
           f'<rect x="{left}" y="{TOP}" width="{SIZE}" height="{SIZE}" class="frame"/>']
    tick = 10 if lim > 20 else 5
    for v in range(-(lim // tick) * tick, lim + 1, tick):
        out += [f'<line x1="{px(v)}" y1="{TOP}" x2="{px(v)}" y2="{bottom}" class="grid"/>',
                f'<line x1="{left}" y1="{py(v)}" x2="{left + SIZE}" y2="{py(v)}" class="grid"/>',
                f'<text x="{px(v)}" y="{bottom + 16}" class="tick">{v:+d}</text>',
                f'<text x="{left - 6}" y="{py(v) + 4}" class="tick end">{v:+d}</text>']
    mid_y = TOP + SIZE / 2
    out += [f'<line x1="{px(-lim)}" y1="{py(-lim)}" x2="{px(lim)}" y2="{py(lim)}" class="diag"/>',
            f'<text x="{px(lim) - 6}" y="{py(lim) + 16}" class="tick end">y = x</text>',
            f'<text x="{left + SIZE / 2}" y="{bottom + 36}" class="axis">true gap from forks (points of win probability)</text>',
            f'<text x="{x0 + 16}" y="{mid_y}" class="axis" transform="rotate(-90 {x0 + 16} {mid_y})">'
            f'engine gap (points)</text>']
    for r, (g, _, _) in sorted(zip(rows, gaps), key=lambda rg: (rg[0]["source"] == "story", rg[0]["set"] == "test")):
        tx, ey = 100 * float(r["true_gap"]), 100 * g
        half = 100 * 1.645 * float(r["true_se"])
        cls = "story" if r["source"] == "story" else r["set"]
        label = (f'seed {r["seed"]} {r["point_id"]} {r["trigger"]} {r["off"]}: '
                 f'engine {ey:+.1f}, true {tx:+.1f} (se {100 * float(r["true_se"]):.1f})')
        out.append(f'<line x1="{px(clip(tx - half))}" y1="{py(clip(ey))}" x2="{px(clip(tx + half))}" '
                   f'y2="{py(clip(ey))}" class="whisker {cls}"/>')
        cx, cy = px(clip(tx)), py(clip(ey))
        if cls == "story":
            out.append(f'<path d="M{cx},{cy - 7} l7,7 l-7,7 l-7,-7 z" class="pt story"><title>{label}</title></path>')
        else:
            out.append(f'<circle cx="{cx}" cy="{cy}" r="3.5" class="pt {cls}"><title>{label}</title></circle>')
    return out


def plot(rows: list[dict], calibration: dict | None = None, path: Path = SCATTER_SVG) -> None:
    """Engine gap against true gap for every pair, with y = x; a second panel once calibrated."""
    done = paired(rows)
    panels = [("Illustrative constants", ILLUSTRATIVE)]
    if calibration is not None:
        panels.append(("Calibrated on the fit seeds", calibration["fitted"]))
    gaps = [engine_gaps(done, c) for _, c in panels]
    biggest = max([15.0] + [100 * abs(float(r["true_gap"])) for r in done]
                  + [100 * abs(float(v)) for g in gaps for v in g[:, 0]])
    lim = 5 * math.ceil(biggest / 5)
    test = [j for j, r in enumerate(done) if r["set"] == "test" and r["source"] == "trigger"]
    body = []
    for i, ((title, c), g) in enumerate(zip(panels, gaps)):
        m = metrics([done[j] for j in test], g[test])
        note = (f"slope {c['slope']}, floor {c['floor']}, bench {c['bench']}. Test points: "
                f"mean error {m['mean_error']:+.1f}, r = {m['correlation']:.2f}")
        body += _panel(done, g, PANEL_W * i, title, note, lim)
    y = TOP + SIZE + 64
    body += [f'<circle cx="{PAD + 4}" cy="{y}" r="3.5" class="pt fit"/>',
             f'<text x="{PAD + 14}" y="{y + 4}" class="tick start">fit seeds</text>',
             f'<circle cx="{PAD + 94}" cy="{y}" r="3.5" class="pt test"/>',
             f'<text x="{PAD + 104}" y="{y + 4}" class="tick start">test seeds</text>',
             f'<path d="M{PAD + 194},{y - 6} l6,6 l-6,6 l-6,-6 z" class="pt story"/>',
             f'<text x="{PAD + 206}" y="{y + 4}" class="tick start">seed 73 at 64:00, RFC-03 off (story point)</text>',
             f'<text x="{PAD}" y="{y + 24}" class="tick start">{len(done)} pairs. Whiskers: 90% interval of the '
             f'true gap (paired forks). Points beyond the axes are drawn at the edge.</text>']
    width, height = PANEL_W * len(panels) + 20, y + 40
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
           f'viewBox="0 0 {width} {height}">\n<style>{CSS}</style>\n'
           f'<rect width="100%" height="100%" fill="var(--bg)"/>\n' + "\n".join(body) + "\n</svg>\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(svg, encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="eval.counterfactual")
    ap.add_argument("cmd", choices=("pairs", "calibrate", "plot", "all"))
    ap.add_argument("--seeds", type=int, nargs="*", default=list(SEEDS), help="seeds for pairs")
    ap.add_argument("--forks", type=int, default=FORKS, help="forks per option per point")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--pairs", type=Path, default=PAIRS_CSV,
                    help="pairs CSV; calibration.json and counterfactual.svg go beside it")
    ap.add_argument("--fresh", action="store_true", help="rerun every seed instead of resuming")
    args = ap.parse_args(argv)
    calibration_json, svg = args.pairs.with_name(CALIBRATION_JSON.name), args.pairs.with_name(SCATTER_SVG.name)
    if args.cmd in ("pairs", "all"):
        run_pairs(tuple(args.seeds), args.forks, args.workers, args.pairs, resume=not args.fresh)
    rows = read_pairs(args.pairs)
    calibration = None
    if args.cmd in ("calibrate", "all"):
        calibration = calibrate(rows, args.workers, calibration_json)
        print(json.dumps({k: calibration[k] for k in ("fitted", "before", "after")}, indent=1))
    elif calibration_json.exists():
        calibration = json.loads(calibration_json.read_text(encoding="utf-8"))
    if args.cmd != "pairs":
        plot(rows, calibration, svg)
        print(f"{svg}: {len(paired(rows))} pairs", file=sys.stderr)


if __name__ == "__main__":
    main()
