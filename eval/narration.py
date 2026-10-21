"""Narration eval: grounding pass rate, retries, template fallbacks and latency on real engine payloads.

Payloads come from the recorded demo match: the state engine finds the decision points, the
decision engine values the options, and any shortfall up to --count is filled with snapshots
spaced across the match (trigger "eval_sample"), alternating teams. Each payload is narrated
in English in both modes through the Agent Framework workflow, and every model reply is graded
again by the grounding check, so the pass rate does not depend on the workflow's own bookkeeping.

    uv run python eval/narration.py --client stub          # offline, free
    uv run python eval/narration.py --client foundry       # real calls: needs FOUNDRY_* variables

The Foundry run bills per token. Settings come from the environment (see env.example); the key
is never written to the report.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from dugout.agents.grounding import check_narration
from dugout.agents.pipeline import (
    Card,
    ModelClient,
    ModelError,
    ModelTimeout,
    StubClient,
    parse_reply,
)
from dugout.agents.workflow import NarrationWorkflow
from dugout.engine.payload import decide
from dugout.stream.replay import read_events
from dugout.stream.snapshots import lineup_from_scenario, process

ROOT = Path(__file__).resolve().parents[1]
EVENTS = ROOT / "data" / "demo-rfc-cas-0073.jsonl"
SCENARIO = ROOT / "scenarios" / "riverside-castleton.yaml"
RESULTS = ROOT / "eval" / "results" / "narration.md"
SAMPLE_TRIGGER = "eval_sample"
SAMPLE_FROM_MS = 25 * 60_000  # condition estimates exist after the 20-minute baseline
SAMPLE_TO_MS = 88 * 60_000
LOCALE = "en"
MODES = ("casual", "analyst")


def build_payloads(count: int = 50) -> list[dict]:
    """Real decision points first, then evenly spaced snapshots until there are `count`."""
    records = list(process(read_events(EVENTS), lineup_from_scenario(SCENARIO)))
    points = [r for r in records if r["kind"] == "decision_point"]
    payloads = [decide(r["snapshot"], r["team"], r["trigger"]) for r in points][:count]
    wanted = count - len(payloads)
    if wanted > 0:
        snapshots = [r["snapshot"] for r in records
                     if r["kind"] == "snapshot" and SAMPLE_FROM_MS <= r["snapshot"]["t_ms"] <= SAMPLE_TO_MS]
        teams = list(snapshots[0]["score"])
        step = len(snapshots) / wanted
        for i in range(wanted):
            snapshot = snapshots[int(i * step)]
            payloads.append(decide(snapshot, teams[i % len(teams)], SAMPLE_TRIGGER))
    return payloads


@dataclass
class RecordedCall:
    request: dict
    reply: str | None
    outcome: str  # "ok", "timeout" or "error"
    latency_s: float


class RecordingClient:
    """Wraps a ModelClient and records every call, including the ones that fail."""

    def __init__(self, inner: ModelClient):
        self._inner = inner
        self.calls: list[RecordedCall] = []

    def complete(self, system: str, user: str, *, timeout_s: float) -> str:
        start = time.perf_counter()
        reply, outcome = None, "ok"
        try:
            reply = self._inner.complete(system, user, timeout_s=timeout_s)
            return reply
        except (ModelTimeout, TimeoutError):
            outcome = "timeout"
            raise
        except ModelError:
            outcome = "error"
            raise
        finally:
            self.calls.append(RecordedCall(json.loads(user), reply, outcome, time.perf_counter() - start))


@dataclass
class GradedCall:
    stage: str
    retry: bool
    outcome: str
    latency_s: float
    passed: bool | None  # None when there was no reply to grade
    errors: list[str] = field(default_factory=list)


def grade(calls: list[RecordedCall]) -> list[GradedCall]:
    graded = []
    for call in calls:
        stage = "localizer" if "draft" in call.request else "narrator"
        retry = "errors" in call.request
        if call.outcome != "ok":
            graded.append(GradedCall(stage, retry, call.outcome, call.latency_s, None))
            continue
        parsed = parse_reply(call.reply)
        errors = [parsed] if isinstance(parsed, str) else check_narration(
            parsed, call.request["payload"], call.request["target"]["locale"])
        graded.append(GradedCall(stage, retry, "ok", call.latency_s, not errors, errors))
    return graded


@dataclass
class TimedCard:
    card: Card
    latency_s: float


def timed(workflow: NarrationWorkflow, payload: dict, locale: str, mode: str) -> TimedCard:
    start = time.perf_counter()
    card = workflow.run(payload, locale, mode)
    return TimedCard(card, time.perf_counter() - start)


def classify(error: str) -> str:
    if error.startswith("number") and "decimal separator" in error:
        return "wrong decimal separator"
    if error.startswith("number"):
        return "number not in payload"
    if error.startswith("player"):
        return "unknown player id"
    if "contradicts" in error:
        return "wrong strength label"
    if error.startswith("strength label") and "missing" in error:
        return "strength label missing"
    if "longer than" in error:
        return "over the word limit"
    if error.startswith("reply is not JSON"):
        return "not valid JSON"
    if error.startswith("internal name"):
        return "internal name"
    return "other"


def _median(values: list[float]) -> float:
    return statistics.median(values) if values else 0.0


def _p95(values: list[float]) -> float:
    return sorted(values)[min(len(values) - 1, int(0.95 * len(values)))] if values else 0.0


def summarize(cards: list[TimedCard], graded: list[GradedCall]) -> dict:
    fallbacks: dict[str, int] = {}
    for c in cards:
        if c.card.source == "template":
            fallbacks[c.card.fallback] = fallbacks.get(c.card.fallback, 0) + 1
    first = [g for g in graded if not g.retry and g.outcome == "ok"]
    retries = [g for g in graded if g.retry]
    failures: dict[str, int] = {}
    for g in graded:
        for error in g.errors:
            failures[classify(error)] = failures.get(classify(error), 0) + 1
    latencies = [g.latency_s for g in graded]
    return {
        "cards": len(cards),
        "cards_model": sum(c.card.source == "model" for c in cards),
        "cards_template": sum(c.card.source == "template" for c in cards),
        "fallbacks": fallbacks,
        "calls": len(graded),
        "call_timeouts": sum(g.outcome == "timeout" for g in graded),
        "call_errors": sum(g.outcome == "error" for g in graded),
        "first_attempt_replies": len(first),
        "first_attempt_passed": sum(bool(g.passed) for g in first),
        "by_stage": {s: (sum(1 for g in first if g.stage == s), sum(bool(g.passed) for g in first if g.stage == s))
                     for s in ("narrator", "localizer")},
        "retries": len(retries),
        "retries_passed": sum(bool(g.passed) for g in retries),
        "failure_kinds": failures,
        "median_call_s": _median(latencies),
        "p95_call_s": _p95(latencies),
        "median_card_s": _median([c.latency_s for c in cards]),
        "p95_card_s": _p95([c.latency_s for c in cards]),
    }


def _pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.1f}%" if whole else "n/a"


def render(s: dict, *, label: str, payload_note: str) -> str:
    fallbacks = ", ".join(f"{k} {v}" for k, v in sorted(s["fallbacks"].items())) or "none"
    kinds = "\n".join(f"- {k}: {v}" for k, v in sorted(s["failure_kinds"].items(), key=lambda kv: -kv[1])) or "- none"
    stages = ", ".join(f"{name} {passed}/{total}" for name, (total, passed) in s["by_stage"].items())
    return f"""# Narration eval

Run {date.today().isoformat()} with {label}.

{payload_note}

Each payload is narrated in English in both modes (casual, analyst) through the Agent Framework workflow:
{s['cards']} cards, {s['calls']} model calls. Every reply is graded again by `dugout/agents/grounding.py`, unchanged.

| Measure | Result |
| --- | --- |
| Grounding pass rate, first attempt | {_pct(s['first_attempt_passed'], s['first_attempt_replies'])} ({s['first_attempt_passed']} of {s['first_attempt_replies']} replies; {stages}) |
| Retries | {s['retries']} ({s['retries_passed']} passed on the retry) |
| Template fallbacks | {s['cards_template']} of {s['cards']} cards ({fallbacks}) |
| Cards shown from the model | {s['cards_model']} of {s['cards']} ({_pct(s['cards_model'], s['cards'])}) |
| Calls with no reply | {s['call_timeouts']} timeouts, {s['call_errors']} errors |
| Median latency, one model call | {s['median_call_s']:.2f} s (95th percentile {s['p95_call_s']:.2f} s) |
| Median latency, one card (both stages and any retry) | {s['median_card_s']:.2f} s (95th percentile {s['p95_card_s']:.2f} s) |

Why replies failed the check:

{kinds}

Notes: the pass rate counts replies, so a card that needed a retry counts one failure. A fallback card
shows the template, which passes the check by construction. Latency is wall-clock from this machine,
including the network, with the {s.get('timeout_note', 'default')} timeout per call.
"""


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="eval/narration.py")
    ap.add_argument("--client", choices=("stub", "foundry"), default="foundry")
    ap.add_argument("--count", type=int, default=50, help="decision payloads")
    ap.add_argument("--timeout", type=float, default=3.0, help="seconds per model call")
    ap.add_argument("--out", type=Path, default=RESULTS)
    args = ap.parse_args(argv)

    if args.client == "foundry":
        import os

        from dugout.agents.foundry import client_from_env
        inner, label = client_from_env(), f"Foundry deployment {os.environ['FOUNDRY_MODEL']}"
    else:
        inner, label = StubClient(), "the local stub client (template answers; plumbing check only)"

    payloads = build_payloads(args.count)
    real = sum(p["trigger"] != SAMPLE_TRIGGER for p in payloads)
    note = (f"{len(payloads)} decision payloads from data/{EVENTS.name} through the state engine and decision "
            f"engine: {real} real decision points and {len(payloads) - real} evenly spaced snapshots.")

    recorder = RecordingClient(inner)
    workflow = NarrationWorkflow(recorder, timeout_s=args.timeout)
    cards = []
    for i, payload in enumerate(payloads, 1):
        for mode in MODES:
            cards.append(timed(workflow, payload, LOCALE, mode))
        print(f"{i}/{len(payloads)} {payload['decision_id']}", flush=True)

    summary = summarize(cards, grade(recorder.calls))
    summary["timeout_note"] = f"{args.timeout:g} s"
    report = render(summary, label=label, payload_note=note)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
