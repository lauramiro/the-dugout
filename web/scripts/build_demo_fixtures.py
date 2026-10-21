"""Build the replay files in web/public/demo from the recorded demo match (seed 73).

Everything here is pipeline output; nothing is hand-shaped:

- snapshots and decision points from dugout.stream (state engine and triggers), fed the
  recorded events in seq order, exactly as `python -m dugout.stream.snapshots` does;
- one card per decision point: the payload from dugout.engine.payload.decide on the
  point's own snapshot, narrated by dugout.agents.pipeline with the stub client (which
  answers with the template text, so every line still goes through the grounding check);
- manager_action on each payload from the deciding team's sub events (see manager_action);
- a review block per card for the full-time screen: the manager's call priced by the
  engine on the same draws as the card, the gap to the model's call, and a recap line
  (template until the recap writer lands);
- the home win-probability series from the engine's no-change run once a minute.

    uv run python web/scripts/build_demo_fixtures.py

Writes match.jsonl, tracking/ (1 Hz chunks plus index.json), roster.json,
snapshots.jsonl, cards.json and winprob.jsonl.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import yaml
from numpy.random import SeedSequence

from dugout.agents.lexicon import DECIMAL_SEPARATOR, LOCALES
from dugout.agents.pipeline import NarrationPipeline, StubClient
from dugout.agents.templates import MODES
from dugout.engine.options import Option, evaluate
from dugout.engine.payload import _exposed_player, decide
from dugout.engine.wp import Flank, simulate_diff, summarize
from dugout.stream.replay import read_events
from dugout.stream.snapshots import lineup_from_scenario, process

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "web" / "public" / "demo"
EVENTS = ROOT / "data" / "demo-rfc-cas-0073.jsonl"
TRACKING = ROOT / "data" / "demo-rfc-cas-0073.tracking.jsonl"
SCENARIO = ROOT / "scenarios" / "riverside-castleton.yaml"
HALF_MS = 2_700_000
MIN_MS = 60_000
CHUNK_MS = 10 * MIN_MS
ATTACK_OFF, ATTACK_ON = {"CM", "FB"}, {"ST", "W"}  # the simulated manager's attacking change


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r, separators=(",", ":")) + "\n" for r in rows), encoding="utf-8")


def order(period: int, t_ms: int) -> tuple[int, int]:
    return period, t_ms


def write_tracking() -> dict[int, int]:
    """1 Hz frames in 10-minute chunks per period; returns each period's last frame t_ms."""
    out = DEMO / "tracking"
    out.mkdir(exist_ok=True)
    for old in out.glob("*.jsonl"):
        old.unlink()
    end: dict[int, int] = {}
    rows: dict[int, list[dict]] = {1: [], 2: []}
    with TRACKING.open(encoding="utf-8") as f:
        for line in f:
            frame = json.loads(line)
            end[frame["period"]] = frame["t_ms"]
            if frame["t_ms"] % 1000 == 0:
                rows[frame["period"]].append(frame)
    chunks = []
    for period in (1, 2):
        left = rows[period]
        start = 0 if period == 1 else HALF_MS
        i = 0
        while left:
            hi = start + (i + 1) * CHUNK_MS
            part = [f for f in left if f["t_ms"] < hi]
            left = left[len(part):]
            if part:
                name = f"p{period}-{i:02d}.jsonl"
                write_jsonl(out / name, part)
                chunks.append({"file": name, "period": period, "from_t_ms": part[0]["t_ms"], "to_t_ms": part[-1]["t_ms"]})
            i += 1
    index = {"hz": 1, "period_end_t_ms": {str(p): t for p, t in end.items()}, "chunks": chunks}
    (out / "index.json").write_text(json.dumps(index, indent=1), encoding="utf-8")
    return end


def build_roster() -> dict:
    scenario = yaml.safe_load(SCENARIO.read_text(encoding="utf-8"))
    roster = {"home": scenario["home"]["code"], "away": scenario["away"]["code"], "teams": {}, "players": {}}
    for side in ("home", "away"):
        team = scenario[side]
        roster["teams"][team["code"]] = {"name": team["name"]}
        for p in team["players"]:
            roster["players"][p["id"]] = {"team": team["code"], "name": p["name"], "role": p["role"], "side": p["side"]}
    return roster


def sub_windows(events: list[dict]) -> list[dict]:
    """Each team's substitution windows in match order: subs at the same instant are one window."""
    windows: dict[tuple, dict] = {}
    for e in events:
        if e["type"] == "sub":
            w = windows.setdefault((e["team"], e["period"], e["t_ms"]),
                                   {"team": e["team"], "period": e["period"], "t_ms": e["t_ms"], "subs": []})
            w["subs"].append({"off": e["player_id"], "on": e["player_in_id"]})
    return sorted(windows.values(), key=lambda w: order(w["period"], w["t_ms"]))


def classify(window: dict, exposed: str | None, roles: dict[str, str]) -> str | None:
    """The card option a window matches: the exposed player taken off is the like-for-like
    option, a midfielder or full-back off for a forward is the attacking change; anything
    else is a change the card did not price (None)."""
    if exposed is not None and any(s["off"] == exposed for s in window["subs"]):
        return "sub_like_for_like"
    if any(roles[s["off"]] in ATTACK_OFF and roles[s["on"]] in ATTACK_ON for s in window["subs"]):
        return "attacking"
    return None


def manager_action(point: dict, payload: dict, windows: list[dict], events: list[dict],
                   end: tuple[int, int], roles: dict[str, str]) -> dict:
    """What the deciding team's manager did about this decision point.

    manager_sub: the change that raised the point. condition_drop: the change that took
    the flagged player off, or no change if he stayed on to the end. goal_after_55: the
    team's next change before the next goal, or no change. `period`/`t_ms` mark when the
    call became known (the change, the next goal, or full time)."""
    team, trigger = point["team"], point["trigger"]
    at = order(point["period"], point["raised_t_ms"])
    exposed = next((e["player_id"] for e in payload["evidence"] if e["type"] == "condition"), None)
    later = [w for w in windows if w["team"] == team and order(w["period"], w["t_ms"]) >= at]
    until = end
    if trigger == "manager_sub":
        found = next((w for w in later if order(w["period"], w["t_ms"]) == at), None)
    elif trigger == "condition_drop":
        player = point["detail"]["player_id"]
        found = next((w for w in later if any(s["off"] == player for s in w["subs"])), None)
    else:
        goals = [order(e["period"], e["t_ms"]) for e in events if e["type"] == "goal"
                 and order(e["period"], e["t_ms"]) > at]
        until = goals[0] if goals else end
        found = next((w for w in later if order(w["period"], w["t_ms"]) < until), None)
    if found is None:
        return {"period": until[0], "t_ms": until[1], "subs": [], "option_id": "no_change"}
    option = None if trigger == "manager_sub" else classify(found, exposed, roles)
    return {"period": found["period"], "t_ms": found["t_ms"], "subs": found["subs"], "option_id": option}


def situation(snapshot: dict, team: str) -> dict:
    """The same situation decide() builds for this snapshot and team."""
    opp = next(t for t in snapshot["score"] if t != team)
    player = _exposed_player(snapshot, team)
    flank = None
    if player is not None:
        flank = Flank(c0=player["condition_est"], drain=max(0.0, -player.get("trend_per_min", 0.0)))
    return dict(t0=snapshot["t_ms"] // MIN_MS, home_goals=snapshot["score"][team], away_goals=snapshot["score"][opp],
                lam_home90=snapshot["rates"][team]["for90"], lam_away90=snapshot["rates"][team]["against90"], flank=flank)


def manager_option(snapshot: dict, payload: dict, action: dict) -> dict | None:
    """The manager's call as an option on the card's own draws (decide's default seed), so
    its gap to the card's options is a paired difference. A like-for-like change made later
    than the card is priced as that change at its minute; a manager_sub card was opened after
    the change, so his call is the card's no-change option. None when the engine has no
    option for what he did, or none at the minute he did it."""
    by_id = {o["id"]: o for o in payload["options"]}
    if payload["trigger"] == "manager_sub":
        o = by_id["no_change"]
    elif action["option_id"] == "sub_like_for_like" and action["t_ms"] // MIN_MS > payload["t_ms"] // MIN_MS:
        minute = action["t_ms"] // MIN_MS
        options = [Option("no_change", "No change"), Option("manager", "Manager's change", sub_at=minute)]
        r = evaluate(situation(snapshot, payload["team"]), options, SeedSequence(snapshot["t_ms"]))[1]
        return {"id": "manager_later", "minute": minute, "win": round(r.win, 3), "xpts": round(r.xpts, 2)}
    elif action["option_id"] == "no_change" or (action["option_id"] in by_id
                                                 and action["t_ms"] // MIN_MS == payload["t_ms"] // MIN_MS):
        o = by_id[action["option_id"]]
    else:
        return None  # an attacking change made later has no option at its own minute
    return {"id": o["id"], "win": o["win"], "xpts": o["xpts"]}


# Recap lines until dugout.agents.recap lands. Options and trade-offs, never verdicts.
RECAP = {
    "en": {
        "same": "Manager and model chose the same option.",
        "gap": "The model's option rated {win} pts of win probability and {xpts} expected points above the manager's.",
        "behind": "The manager's call rated {win} pts of win probability and {xpts} expected points above the model's option.",
        "unpriced": "The card has no option for the manager's change at the minute he made it, so there is no gap to show.",
    },
    "es": {
        "same": "El entrenador y el modelo eligieron la misma opción.",
        "gap": "La opción del modelo valía {win} pts de probabilidad de victoria y {xpts} puntos esperados más que la del entrenador.",
        "behind": "La decisión del entrenador valía {win} pts de probabilidad de victoria y {xpts} puntos esperados más que la opción del modelo.",
        "unpriced": "La tarjeta no tiene ninguna opción para el cambio del entrenador en el minuto en que lo hizo, así que no hay diferencia que mostrar.",
    },
    "ca": {
        "same": "L'entrenador i el model van triar la mateixa opció.",
        "gap": "L'opció del model valia {win} punts de probabilitat de victòria i {xpts} punts esperats més que la de l'entrenador.",
        "behind": "La decisió de l'entrenador valia {win} punts de probabilitat de victòria i {xpts} punts esperats més que l'opció del model.",
        "unpriced": "La targeta no té cap opció per al canvi de l'entrenador al minut en què el va fer, així que no hi ha diferència a mostrar.",
    },
}


def fmt(value: float, digits: int, locale: str) -> str:
    return f"{abs(value):.{digits}f}".replace(".", DECIMAL_SEPARATOR[locale])


def review(payload: dict, manager: dict | None) -> dict:
    model = next(o for o in payload["options"] if o["id"] == payload["recommendation"]["option_id"])
    if manager is None:
        gap_win = gap_xpts = None
        kind = "unpriced"
    else:
        gap_win = round(model["win"] - manager["win"], 3)
        gap_xpts = round(model["xpts"] - manager["xpts"], 2)
        kind = "same" if manager["id"] == model["id"] else "gap" if gap_win >= 0 else "behind"
    recap = {loc: RECAP[loc][kind].format(win=fmt((gap_win or 0) * 100, 1, loc), xpts=fmt(gap_xpts or 0, 2, loc))
             for loc in LOCALES}
    return {"model": {"id": model["id"], "win": model["win"], "xpts": model["xpts"]}, "manager": manager,
            "gap_win": gap_win, "gap_xpts": gap_xpts, "recap": recap, "recap_source": "template"}


def main() -> None:
    end = write_tracking()
    shutil.copyfile(EVENTS, DEMO / "match.jsonl")
    roster = build_roster()
    (DEMO / "roster.json").write_text(json.dumps(roster, indent=1), encoding="utf-8")
    roles = {pid: p["role"] for pid, p in roster["players"].items()}

    events = list(read_events(EVENTS))
    records = list(process(events, lineup_from_scenario(SCENARIO)))
    snapshots = [r["snapshot"] for r in records if r["kind"] == "snapshot"]
    points = [r for r in records if r["kind"] == "decision_point"]
    closed = {r["id"]: r for r in records if r["kind"] == "card_closed"}
    write_jsonl(DEMO / "snapshots.jsonl", snapshots)

    windows = sub_windows(events)
    full_time = (2, end[2])
    pipeline = NarrationPipeline(StubClient())
    cards = []
    for point in points:
        payload = decide(point["snapshot"], point["team"], point["trigger"])
        payload["manager_action"] = manager_action(point, payload, windows, events, full_time, roles)
        narration = {}
        for loc in LOCALES:
            narration[loc] = {}
            for mode in MODES:
                card = pipeline.run(payload, loc, mode)
                # The stub client returns the template text; label it as such, not as a model.
                narration[loc][mode] = {"headline": card.headline, "reason": card.reason, "source": "template"}
        c = closed[point["id"]]
        cards.append({"period": point["period"], "point_id": point["id"], "payload": payload, "narration": narration,
                      "closed": {"period": c["period"], "t_ms": c["t_ms"], "reason": c["reason"]},
                      "review": review(payload, manager_option(point["snapshot"], payload, payload["manager_action"]))})
    (DEMO / "cards.json").write_text(json.dumps({"cards": cards}, indent=1, ensure_ascii=False), encoding="utf-8")

    # Home win probability once a minute, the same call as decide()'s no-change option.
    series = []
    home = roster["home"]
    for s in snapshots:
        if s["t_ms"] % MIN_MS:
            continue
        at = situation(s, home)
        if s["period"] == 1:
            at["t0"] = min(at["t0"], 45)  # first-half added time still has a whole half to come
        diff = simulate_diff(**at, seed=SeedSequence(s["t_ms"]), n=20_000)
        o = summarize(diff)
        series.append({"period": s["period"], "t_ms": s["t_ms"], "team": home,
                       "win": round(o.win, 3), "draw": round(o.draw, 3), "loss": round(o.loss, 3)})
    write_jsonl(DEMO / "winprob.jsonl", series)

    for c in cards:
        p, a, r = c["payload"], c["payload"]["manager_action"], c["review"]
        print(f"{p['t_ms'] // MIN_MS:>3}' {p['decision_id']:<11} {p['trigger']:<19} model {p['recommendation']['option_id']}"
              f" ({p['recommendation']['strength']}); manager {a['option_id']} at {a['t_ms'] // MIN_MS}' {a['subs']};"
              f" gap {r['gap_win']} / {r['gap_xpts']}")


main()
