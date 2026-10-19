import json

import pytest

from dugout.agents.grounding import Narration, check_narration
from dugout.agents.pipeline import ModelError, ModelTimeout, StubClient, load_prompt
from dugout.agents.recap import MODES, RecapRow, recap_payload, template_line, write_recap

STRONG = RecapRow("rfc-62-01", 62, "RFC", "No change", "Replace left-back (RFC-03 for RFC-15)", 0.039, 0.09)
LEAN = RecapRow("rfc-79-01", 79, "RFC", "No change", "Replace winger (RFC-11 for RFC-19)", 0.021, 0.04)
CLOSE = RecapRow("rfc-70-01", 70, "RFC", "No change", "Replace striker (RFC-09 for RFC-20)", 0.004, 0.01)
SAME = RecapRow("rfc-84-01", 84, "RFC", "No change", "No change", 0.0, 0.0)
ROWS = [STRONG, LEAN, CLOSE, SAME]

STRONG_ANALYST_OK = "62': the model preferred Replace left-back (RFC-03 for RFC-15) by +3.9 pts win probability (strong)."
LEAN_ANALYST_OK = "79': the model preferred Replace winger (RFC-11 for RFC-19) by +2.1 pts win probability (lean)."
STRONG_CASUAL_OK = "62': the model rated the left-back change about 4 points better (strong)."


def stub(items):
    """A scripted client whose text items are wrapped as the JSON the recap prompt asks for; "" stays raw."""
    return StubClient([json.dumps({"line": i}) if isinstance(i, str) and i else i for i in items])


def test_grounded_reply_is_used():
    client = stub([STRONG_ANALYST_OK])
    result = write_recap([STRONG], client, modes=("analyst",))
    (line,) = result["analyst"]
    assert (line.source, line.fallback, line.text) == ("model", None, STRONG_ANALYST_OK)
    assert (line.decision_id, line.minute) == ("rfc-62-01", 62)
    assert len(client.calls) == 1


def test_ungrounded_reply_gets_one_retry_with_errors_then_falls_back():
    bad = STRONG_ANALYST_OK.replace("+3.9", "+4.9")
    client = stub([bad, bad])
    (line,) = write_recap([STRONG], client, modes=("analyst",))["analyst"]
    assert (line.source, line.fallback) == ("template", "ungrounded")
    assert line.text == template_line(STRONG, "en", "analyst")
    assert len(client.calls) == 2
    retry = json.loads(client.calls[1].user)
    assert any("4.9" in e for e in retry["errors"])
    assert json.loads(client.calls[0].user).get("errors") is None


def test_retry_can_recover():
    bad = STRONG_ANALYST_OK.replace("+3.9", "+4.9")
    client = stub([bad, STRONG_ANALYST_OK])
    (line,) = write_recap([STRONG], client, modes=("analyst",))["analyst"]
    assert (line.source, line.text) == ("model", STRONG_ANALYST_OK)


def test_reply_that_is_not_json_counts_as_a_failed_attempt():
    client = stub(["", STRONG_ANALYST_OK])
    (line,) = write_recap([STRONG], client, modes=("analyst",))["analyst"]
    assert line.source == "model" and len(client.calls) == 2


@pytest.mark.parametrize("phrase", [
    "the model would have won", "the manager should have changed", "that was a mistake", "the wrong call",
])
def test_blame_and_counterfactual_wording_is_rejected(phrase):
    text = f"62': {phrase}, +3.9 pts win probability (strong)."
    client = stub([text, text])
    (line,) = write_recap([STRONG], client, modes=("analyst",))["analyst"]
    assert (line.source, line.fallback) == ("template", "ungrounded")


def test_wrong_strength_label_is_rejected():
    text = STRONG_ANALYST_OK.replace("(strong)", "(lean)")
    (line,) = write_recap([STRONG], stub([text, text]), modes=("analyst",))["analyst"]
    assert line.source == "template"


def test_too_long_reply_is_rejected():
    text = "62': " + " ".join(["word"] * 30) + " +3.9 (strong)."
    (line,) = write_recap([STRONG], stub([text, text]), modes=("analyst",))["analyst"]
    assert line.source == "template"


@pytest.mark.parametrize("failure, reason", [
    (ModelTimeout(), "timeout"), (TimeoutError(), "timeout"), (ModelError("x"), "error"),
])
def test_timeout_and_error_fall_back_per_row_without_retry(failure, reason):
    client = stub([failure, LEAN_ANALYST_OK])
    result = write_recap([STRONG, LEAN], client, modes=("analyst",))
    first, second = result["analyst"]
    assert (first.source, first.fallback) == ("template", reason)
    assert second.source == "model"
    assert len(client.calls) == 2


def test_one_line_per_row_in_each_mode_in_row_order():
    result = write_recap(ROWS, stub([ModelTimeout()] * 8))
    assert set(result) == set(MODES) == {"casual", "analyst"}
    for mode in MODES:
        assert [line.decision_id for line in result[mode]] == [r.decision_id for r in ROWS]
        assert all(line.source == "template" for line in result[mode])


def test_unknown_locale_and_mode_are_refused():
    with pytest.raises(ValueError):
        write_recap(ROWS, stub([]), locale="fr")
    with pytest.raises(ValueError):
        write_recap(ROWS, stub([]), modes=("shouting",))


@pytest.mark.parametrize("row", ROWS, ids=["strong", "lean", "close", "same"])
@pytest.mark.parametrize("mode", MODES)
def test_every_template_passes_the_grounding_check(row, mode):
    text = template_line(row, "en", mode)
    assert check_narration(Narration("", text), recap_payload(row), "en") == []
    assert "would have" not in text and "wrong" not in text


def test_templates_say_the_model_and_never_claim_a_result():
    for row in ROWS:
        for mode in MODES:
            text = template_line(row, "en", mode).lower()
            assert "model" in text
            assert "would have won" not in text and " will " not in text


def test_recap_payload_exposes_only_the_row_numbers():
    from dugout.agents.grounding import payload_numbers

    shown = {format(n.normalize(), "f") for n in payload_numbers(recap_payload(STRONG))}
    assert shown == {"62", "90", "3.9", "0.09"}


def test_request_carries_preformatted_numbers_and_the_row():
    client = stub([STRONG_ANALYST_OK])
    write_recap([STRONG], client, modes=("analyst",))
    request = json.loads(client.calls[0].user)
    assert request["target"] == {"locale": "en", "mode": "analyst"}
    assert request["row"]["manager_call"] == "No change"
    assert request["numbers"]["delta"] == "+3.9" and request["numbers"]["strength"] == "strong"
    assert client.calls[0].system == load_prompt("recap")


def test_prompt_carries_the_rules():
    prompt = load_prompt("recap").lower()
    for rule in ("the model", "would have won", "25 words", "strength", "never compute", "options"):
        assert rule in prompt
