"""Build the replay fixtures in web/public/demo from a simulator run.

FIXTURE: the snapshots, decision cards and win-probability series written here stand in
for the state engine, decision engine and agents output until wave 3 replaces them with
real files. Snapshot condition estimates are hand-shaped curves (not the state engine);
hsr, sprint, score, subs and threat come from the events. Decision payloads come from
dugout.engine.payload.decide on those snapshots, and narrations from the template
fallback, so every number on a card is engine output.

    uv run python -m dugout.sim run --seed 2 --out web/public/demo/match.jsonl
    uv run python web/scripts/build_demo_fixtures.py

Writes tracking/ (1 Hz chunks plus index.json), roster.json, snapshots.jsonl,
cards.json and winprob.jsonl, and deletes the raw 2 Hz tracking file.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml
from numpy.random import SeedSequence

from dugout.agents.templates import MODES, template_narration
from dugout.agents.lexicon import LOCALES
from dugout.engine.payload import decide, _exposed_player
from dugout.engine.wp import Flank, simulate_diff, summarize

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "web" / "public" / "demo"
HALF_MS = 2_700_000
MIN_MS = 60_000
CHUNK_MS = 10 * MIN_MS
PRIOR = {"RFC": (1.5, 1.2), "CAS": (1.2, 1.5)}  # xG/90 for, against (illustrative)
SUBS, WINDOWS = 5, 3

# Hand-shaped condition curves: 1.0 through the 20-minute baseline, then a linear drain.
# RFC-03 (played midweek) crosses 0.60 at 62'; others drain by role with a small spread.
DRAIN = {"FB": 0.0062, "W": 0.0064, "CM": 0.0058, "CB": 0.0042, "ST": 0.0060}
DRAIN_OVERRIDE = {"RFC-03": 0.40 / 42}
BAND = {"FB": 0.08, "W": 0.08, "CM": 0.09, "ST": 0.09, "CB": 0.12}  # wider for low-sprint roles

# Decision points in seed 2: (period, t_ms, team, trigger).
DECISIONS = [
    (2, 62 * MIN_MS, "RFC", "condition_below_60"),
    (2, 70 * MIN_MS, "CAS", "manager_sub"),
    (2, 78 * MIN_MS + 19_000, "RFC", "manager_sub"),
]


def key(period: int, t_ms: int) -> int:
    """Elapsed playing time: the second half follows the first half's final frame."""
    return t_ms if period == 1 else END[1] + 500 + (t_ms - HALF_MS)


def jitter(pid: str) -> float:
    return int(hashlib.sha1(pid.encode()).hexdigest()[:4], 16) / 0xFFFF - 0.5


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r, separators=(",", ":")) + "\n" for r in rows), encoding="utf-8")


raw_tracking = DEMO / "match.tracking.jsonl"
events = read_jsonl(DEMO / "match.jsonl")
END: dict[int, int] = {}
frames = []
if raw_tracking.exists():
    for f in read_jsonl(raw_tracking):
        END[f["period"]] = f["t_ms"]
        if f["t_ms"] % 1000 == 0:
            frames.append(f)
else:
    index = json.loads((DEMO / "tracking" / "index.json").read_text(encoding="utf-8"))
    END = {int(p): t for p, t in index["period_end_t_ms"].items()}

scenario = yaml.safe_load((ROOT / "scenarios" / "riverside-castleton.yaml").read_text(encoding="utf-8"))
roster = {"home": scenario["home"]["code"], "away": scenario["away"]["code"], "teams": {}, "players": {}}
for side in ("home", "away"):
    team = scenario[side]
    roster["teams"][team["code"]] = {"name": team["name"]}
    for p in team["players"]:
        roster["players"][p["id"]] = {"team": team["code"], "name": p["name"], "role": p["role"], "side": p["side"]}
ROLE = {pid: p["role"] for pid, p in roster["players"].items()}


def condition(pid: str, minute_on: float, minute: float) -> float:
    if ROLE[pid] == "GK":
        return None
    drain = DRAIN_OVERRIDE.get(pid, DRAIN[ROLE[pid]] * (1 + 0.5 * jitter(pid)))
    worked = max(0.0, minute - max(20.0, minute_on + 10.0))
    return max(0.3, min(1.0, 1.0 - drain * worked))


def snapshot_at(period: int, t_ms: int, before: bool = False) -> dict:
    """State after every event up to (period, t_ms); before=True leaves out that instant's
    events, so a manager_sub decision sees the player still on."""
    now = key(period, t_ms)
    past = [e for e in events if key(e["period"], e["t_ms"]) < now or (not before and key(e["period"], e["t_ms"]) == now)]
    minute = now / MIN_MS
    on = {pid: 0.0 for pid in roster["players"] if int(pid[-2:]) <= 11}
    subs_used = {"RFC": 0, "CAS": 0}
    windows = {"RFC": set(), "CAS": set()}
    score = {"RFC": 0, "CAS": 0}
    for e in past:
        if e["type"] == "goal":
            score[e["team"]] += 1
        elif e["type"] == "sub":
            on.pop(e["player_id"], None)
            on[e["player_in_id"]] = e["t_ms"] / MIN_MS
            subs_used[e["team"]] += 1
            if (e["period"], e["t_ms"]) != (2, HALF_MS):
                windows[e["team"]].add((e["period"], e["t_ms"]))

    def run_stats(pid: str, lo: float, hi: float) -> tuple[float, int]:
        hsr, sprints = 0.0, 0
        for e in past:
            if e["player_id"] == pid and lo <= key(e["period"], e["t_ms"]) / MIN_MS < hi:
                if e["type"] == "hsr":
                    hsr += e["dist_m"]
                elif e["type"] == "sprint":
                    sprints += 1
        return hsr, sprints

    clock = t_ms / MIN_MS  # condition curves run on the match clock, windows on elapsed time
    players = []
    for pid, minute_on in on.items():
        c = condition(pid, minute_on, clock)
        hsr, sprints = run_stats(pid, minute - 10, minute + 1e-9)
        base_from = 0.0 if minute_on == 0.0 else key(2, int(minute_on * MIN_MS)) / MIN_MS
        b_hsr, b_spr = run_stats(pid, base_from, base_from + 20)
        p = {"id": pid, "condition_est": None if c is None else round(c, 2), "condition_band": None,
             "trend_per_min": None, "hsr_m_10m": round(hsr), "baseline_hsr_m_10m": round(b_hsr / 2),
             "sprints_10m": sprints, "baseline_sprints_10m": round(b_spr / 2)}
        if c is not None:
            prev = condition(pid, minute_on, clock - 1)
            band = BAND[ROLE[pid]]
            p["condition_band"] = [round(max(0.3, c - band), 2), round(min(1.0, c + band), 2)]
            p["trend_per_min"] = round(c - prev, 4)
        players.append(p)

    rates = {}
    threat = {}
    for team, opp in (("RFC", "CAS"), ("CAS", "RFC")):
        recent = [e for e in past if e["type"] == "shot" and key(e["period"], e["t_ms"]) / MIN_MS > minute - 20]
        xg_for = sum(e["xg"] for e in recent if e["team"] == team) * 90 / 20
        xg_against = sum(e["xg"] for e in recent if e["team"] == opp) * 90 / 20
        weight = min(1.0, minute / 20) * 0.5
        rates[team] = {"for90": round((1 - weight) * PRIOR[team][0] + weight * xg_for, 2),
                       "against90": round((1 - weight) * PRIOR[team][1] + weight * xg_against, 2)}
        # Opponent xG by channel over the last 15 minutes, seen from this team's side
        # (the opponent's left is this team's right), smoothed towards an even split.
        mirror = {"left": "right", "right": "left", "centre": "centre"}
        shares = {c: 0.05 for c in ("left", "centre", "right")}
        for e in past:
            if e["type"] == "shot" and e["team"] == opp and key(e["period"], e["t_ms"]) / MIN_MS > minute - 15:
                shares[mirror[e["channel"]]] += e["xg"]
        total = sum(shares.values())
        for c in ("left", "centre", "right"):
            threat[f"{team}_{c}"] = round(shares[c] / total, 2)

    return {"t_ms": t_ms, "score": score,
            "subs_left": {t: SUBS - n for t, n in subs_used.items()},
            "windows_left": {t: WINDOWS - len(w) for t, w in windows.items()},
            "rates": rates, "players": players, "threat_by_channel": threat}


def for_team(snapshot: dict, team: str) -> dict:
    """Keep only the deciding team's rates and flank threat."""
    s = dict(snapshot)
    s["rates"] = {team: snapshot["rates"][team]}
    s["threat_by_channel"] = {k: v for k, v in snapshot["threat_by_channel"].items() if k.startswith(team)}
    return s


def main() -> None:
    # Tracking: 1 Hz frames in 10-minute chunks per period.
    if frames:
        out = DEMO / "tracking"
        out.mkdir(exist_ok=True)
        for old in out.glob("*.jsonl"):
            old.unlink()
        chunks = []
        for period in (1, 2):
            rows = [f for f in frames if f["period"] == period]
            start = 0 if period == 1 else HALF_MS
            i = 0
            while rows:
                hi = start + (i + 1) * CHUNK_MS
                part = [f for f in rows if f["t_ms"] < hi]
                rows = rows[len(part):]
                name = f"p{period}-{i:02d}.jsonl"
                write_jsonl(out / name, part)
                chunks.append({"file": name, "period": period, "from_t_ms": part[0]["t_ms"], "to_t_ms": part[-1]["t_ms"]})
                i += 1
        index = {"hz": 1, "period_end_t_ms": {str(p): t for p, t in END.items()}, "chunks": chunks}
        (out / "index.json").write_text(json.dumps(index, indent=1), encoding="utf-8")
        raw_tracking.unlink()

    (DEMO / "roster.json").write_text(json.dumps(roster, indent=1), encoding="utf-8")

    grid = [(1, t) for t in range(0, END[1] + 1, MIN_MS)] + [(2, t) for t in range(HALF_MS, END[2] + 1, MIN_MS)]
    grid += [(p, t) for p, t, _, _ in DECISIONS if t % MIN_MS]
    grid.sort(key=lambda pt: key(*pt))
    snapshots = [snapshot_at(p, t) for p, t in grid]
    write_jsonl(DEMO / "snapshots.jsonl", snapshots)

    by_time = {(p, t): s for (p, t), s in zip(grid, snapshots)}
    cards = []
    for period, t_ms, team, trigger in DECISIONS:
        snapshot = snapshot_at(period, t_ms, before=True) if trigger == "manager_sub" else by_time[(period, t_ms)]
        payload = decide(for_team(snapshot, team), team, trigger)
        narration = {}
        for loc in LOCALES:
            narration[loc] = {}
            for mode in MODES:
                n = template_narration(payload, loc, mode)
                narration[loc][mode] = {"headline": n.headline, "reason": n.reason, "source": "template"}
        cards.append({"period": period, "payload": payload, "narration": narration})
    (DEMO / "cards.json").write_text(json.dumps({"fixture": True, "cards": cards}, indent=1, ensure_ascii=False),
                                     encoding="utf-8")

    # Home win probability, same call as decide()'s no-change option from the home side.
    series = []
    for (period, t_ms), s in zip(grid, snapshots):
        home = for_team(s, "RFC")
        player = _exposed_player(home, "RFC")
        flank = None if player is None else Flank(c0=player["condition_est"],
                                                  drain=max(0.0, -player.get("trend_per_min", 0.0)))
        minute = min(t_ms // MIN_MS, 90) if period == 2 else min(t_ms // MIN_MS, 45)
        diff = simulate_diff(minute, s["score"]["RFC"], s["score"]["CAS"], home["rates"]["RFC"]["for90"],
                             home["rates"]["RFC"]["against90"], SeedSequence(t_ms), n=20_000, flank=flank)
        o = summarize(diff)
        series.append({"period": period, "t_ms": t_ms, "team": "RFC",
                       "win": round(o.win, 3), "draw": round(o.draw, 3), "loss": round(o.loss, 3)})
    write_jsonl(DEMO / "winprob.jsonl", series)
    for c in cards:
        p = c["payload"]
        print(p["decision_id"], p["recommendation"], [(o["id"], o["win"], o["delta_win"]) for o in p["options"]])


main()
