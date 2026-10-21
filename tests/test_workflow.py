"""The pipeline's behaviour, checked again against the Agent Framework workflow."""

import asyncio
import json

import pytest

from dugout.agents.grounding import check_narration
from dugout.agents.pipeline import ModelError, ModelTimeout, NarrationPipeline, StubClient
from dugout.agents.sample import SAMPLE_PAYLOAD, toss_up_payload
from dugout.agents.templates import template_narration
from dugout.agents.workflow import NarrationWorkflow

NARRATOR_OK = json.dumps({
    "headline": "RFC-03 is fading (60%).",
    "reason": "Changing now: +3.9 pts win probability (strong).",
})
NARRATOR_BAD = NARRATOR_OK.replace("+3.9", "+4.9")
LOCALIZER_ES_OK = json.dumps({
    "headline": "RFC-03 se está agotando (60%).",
    "reason": "Cambiar ahora: +3,9 pts de probabilidad de victoria (fuerte).",
})
LOCALIZER_ES_BAD = LOCALIZER_ES_OK.replace("+3,9", "+3,8")


def run(script, locale="es", mode="analyst", payload=SAMPLE_PAYLOAD):
    client = StubClient(script)
    return NarrationWorkflow(client).run(payload, locale, mode), client


def test_passes_first_time():
    card, client = run([NARRATOR_OK, LOCALIZER_ES_OK])
    assert card.source == "model"
    assert card.headline == "RFC-03 se está agotando (60%)."
    assert len(client.calls) == 2


def test_passes_on_retry_with_errors_attached():
    card, client = run([NARRATOR_BAD, NARRATOR_OK, LOCALIZER_ES_OK])
    assert card.source == "model"
    assert len(client.calls) == 3
    retry_user = json.loads(client.calls[1].user)
    assert any("4.9" in e for e in retry_user["errors"])
    assert retry_user["previous"] == NARRATOR_BAD
    assert "errors" not in json.loads(client.calls[0].user)


def test_stages_use_their_own_prompts():
    _, client = run([NARRATOR_OK, LOCALIZER_ES_OK])
    assert client.calls[0].system != client.calls[1].system
    assert "draft" not in json.loads(client.calls[0].user)
    assert json.loads(client.calls[1].user)["draft"]["headline"] == "RFC-03 is fading (60%)."


def test_narrator_failing_twice_falls_back_to_template():
    card, client = run([NARRATOR_BAD, NARRATOR_BAD])
    expected = template_narration(SAMPLE_PAYLOAD, "es", "analyst")
    assert (card.source, card.fallback) == ("template", "ungrounded")
    assert (card.headline, card.reason) == (expected.headline, expected.reason)
    assert len(client.calls) == 2


def test_localizer_failing_twice_falls_back_to_template():
    card, client = run([NARRATOR_OK, LOCALIZER_ES_BAD, LOCALIZER_ES_BAD])
    expected = template_narration(SAMPLE_PAYLOAD, "es", "analyst")
    assert (card.source, card.reason) == ("template", expected.reason)
    assert len(client.calls) == 3


def test_localizer_output_is_checked_in_the_target_locale():
    decimal_point = LOCALIZER_ES_OK.replace("+3,9", "+3.9")
    card, _ = run([NARRATOR_OK, decimal_point, LOCALIZER_ES_OK])
    assert card.source == "model" and "+3,9" in card.reason


@pytest.mark.parametrize("failure, reason", [
    (ModelTimeout(), "timeout"), (TimeoutError(), "timeout"), (ModelError("x"), "error"),
])
def test_narrator_failure_falls_back_without_retry(failure, reason):
    card, client = run([failure])
    assert card.source == "template" and card.fallback == reason
    assert len(client.calls) == 1


def test_localizer_timeout_falls_back_to_template():
    card, client = run([NARRATOR_OK, ModelTimeout()])
    assert card.source == "template" and card.fallback == "timeout"
    assert len(client.calls) == 2


def test_reply_that_is_not_json_counts_as_a_failed_attempt():
    card, client = run(["not json", NARRATOR_OK, LOCALIZER_ES_OK])
    assert card.source == "model" and len(client.calls) == 3


def test_word_limits_apply_to_model_replies():
    long_reply = json.dumps({"headline": " ".join(["word"] * 13) + " (strong)", "reason": "x"})
    card, _ = run([long_reply, long_reply])
    assert card.source == "template" and card.fallback == "ungrounded"


@pytest.mark.parametrize("payload", [SAMPLE_PAYLOAD, toss_up_payload()], ids=["strong", "toss_up"])
@pytest.mark.parametrize("mode", ["casual", "analyst"])
@pytest.mark.parametrize("locale", ["en", "es"])
def test_default_stub_client_produces_grounded_cards(locale, mode, payload):
    card = NarrationWorkflow(StubClient()).run(payload, locale, mode)
    assert card.source == "model"
    narration = template_narration(payload, locale, mode)
    assert (card.headline, card.reason) == (narration.headline, narration.reason)
    assert check_narration(narration, payload, locale) == []


@pytest.mark.parametrize("script", [
    [NARRATOR_OK, LOCALIZER_ES_OK],
    [NARRATOR_BAD, NARRATOR_OK, LOCALIZER_ES_OK],
    [NARRATOR_BAD, NARRATOR_BAD],
    [NARRATOR_OK, LOCALIZER_ES_BAD, LOCALIZER_ES_BAD],
    [ModelTimeout()],
    [NARRATOR_OK, ModelError("x")],
])
def test_workflow_and_pipeline_agree(script):
    from_workflow, _ = run(list(script))
    from_pipeline = NarrationPipeline(StubClient(list(script))).run(SAMPLE_PAYLOAD, "es", "analyst")
    assert from_workflow == from_pipeline


def test_graph_is_narrator_check_localizer_check():
    ids = NarrationWorkflow(StubClient()).executor_ids
    assert ids == ["narrator", "check_narrator", "localizer", "check_localizer"]


def test_async_entry_point_works_inside_a_running_loop():
    async def go():
        return await NarrationWorkflow(StubClient()).arun(SAMPLE_PAYLOAD, "en", "casual")

    assert asyncio.run(go()).source == "model"
