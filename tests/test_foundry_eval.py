"""The narration eval's plumbing, against the stub client (no cloud, no cost)."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from dugout.agents.pipeline import ModelError, ModelTimeout, StubClient
from dugout.agents.sample import SAMPLE_PAYLOAD
from dugout.agents.workflow import NarrationWorkflow

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("narration_eval", ROOT / "eval" / "narration.py")
narration_eval = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = narration_eval  # dataclasses look the module up by name
spec.loader.exec_module(narration_eval)

GOOD = json.dumps({"headline": "RFC-03 is fading (60%).",
                   "reason": "Changing now: +3.9 pts win probability (strong)."})
BAD = GOOD.replace("+3.9", "+4.9")


@pytest.fixture(scope="module")
def payloads():
    return narration_eval.build_payloads(10)


def test_payloads_come_from_the_engine_and_are_distinct(payloads):
    assert len(payloads) == 10
    assert len({p["decision_id"] for p in payloads}) == 10
    for p in payloads:
        assert {"options", "recommendation", "evidence", "t_ms", "team"} <= set(p)


def test_payloads_start_with_the_real_decision_points(payloads):
    triggers = [p["trigger"] for p in payloads]
    real = [t for t in triggers if t != narration_eval.SAMPLE_TRIGGER]
    assert real and triggers[: len(real)] == real


def test_recording_client_grades_each_reply_independently():
    inner = StubClient([GOOD, GOOD, BAD, ModelTimeout(), ModelError("x")])
    recorder = narration_eval.RecordingClient(inner)
    workflow = NarrationWorkflow(recorder)
    workflow.run(SAMPLE_PAYLOAD, "en", "analyst")      # narrator ok, localizer ok
    workflow.run(SAMPLE_PAYLOAD, "en", "analyst")      # narrator bad, then timeout on the retry
    workflow.run(SAMPLE_PAYLOAD, "en", "analyst")      # narrator error
    graded = narration_eval.grade(recorder.calls)
    assert [c.outcome for c in graded] == ["ok", "ok", "ok", "timeout", "error"]
    assert [c.passed for c in graded] == [True, True, False, None, None]
    assert [c.retry for c in graded] == [False, False, False, True, False]


def test_summary_counts_pass_rate_retries_fallbacks_and_latency():
    inner = StubClient([GOOD, GOOD, BAD, GOOD, GOOD, ModelTimeout()])
    recorder = narration_eval.RecordingClient(inner)
    workflow = NarrationWorkflow(recorder)
    cards = [narration_eval.timed(workflow, SAMPLE_PAYLOAD, "en", "analyst") for _ in range(3)]
    summary = narration_eval.summarize(cards, narration_eval.grade(recorder.calls))
    assert summary["cards"] == 3
    assert summary["cards_model"] == 2 and summary["cards_template"] == 1
    assert summary["fallbacks"] == {"timeout": 1}
    assert summary["first_attempt_replies"] == 4 and summary["first_attempt_passed"] == 3
    assert summary["retries"] == 1 and summary["retries_passed"] == 1
    assert summary["median_call_s"] >= 0 and summary["median_card_s"] >= 0


def test_report_has_the_numbers_and_no_secrets(monkeypatch):
    monkeypatch.setenv("FOUNDRY_API_KEY", "super-secret-key")
    recorder = narration_eval.RecordingClient(StubClient())
    workflow = NarrationWorkflow(recorder)
    cards = [narration_eval.timed(workflow, SAMPLE_PAYLOAD, "en", m) for m in ("casual", "analyst")]
    summary = narration_eval.summarize(cards, narration_eval.grade(recorder.calls))
    report = narration_eval.render(summary, label="stub client", payload_note="2 payloads")
    assert "Grounding pass rate" in report and "Template fallbacks" in report
    assert "Median latency" in report and "Retries" in report
    assert "super-secret-key" not in report


def test_error_classes_group_by_kind():
    classify = narration_eval.classify
    assert classify("number +4.9 does not match any payload field") == "number not in payload"
    assert classify("player RFC-99 is not in the payload") == "unknown player id"
    assert classify("player RFC-03 is the one who would come off, not on") == "player on, not off"
    assert classify("strength label 'lean' contradicts the recommendation ('strong')") == "wrong strength label"
    assert classify("strength label 'strong' is missing") == "strength label missing"
    assert classify("headline is longer than 12 words") == "over the word limit"
    assert classify("reply is not JSON with a headline and a reason") == "not valid JSON"
    assert classify("internal name 'no_change' in the text; use plain words") == "internal name"
    assert classify("player RFC-09 is not the tiring player; only he would come off") == "takes off a player who is not tiring"
    assert classify("taking RFC-03 off is the like-for-like change, but the model's pick is another option; "
                    "name that option instead") == "takes a player off when the pick is another option"
    assert classify("'expected points' without an expected-points value; the gap between options is in points "
                    "of win probability") == "gap called expected points"
    assert classify("'0 points': say the options are about even, without a number") == "casual: zero points"
    assert classify("something new") == "other"


def test_stub_client_run_over_engine_payloads_passes_everything(payloads):
    recorder = narration_eval.RecordingClient(StubClient())
    workflow = NarrationWorkflow(recorder)
    cards = [narration_eval.timed(workflow, p, "en", "casual") for p in payloads[:3]]
    graded = narration_eval.grade(recorder.calls)
    assert all(c.passed for c in graded) and all(c.card.source == "model" for c in cards)
