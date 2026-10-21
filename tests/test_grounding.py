import copy

import pytest

from dugout.agents.grounding import Narration, check_grounding, check_narration
from dugout.agents.sample import SAMPLE_PAYLOAD

GROUNDED = {"en": "RFC-03 is fading (60%). Changing now: +3.9 pts win probability (strong)."}


def payload_with(**delta):
    payload = copy.deepcopy(SAMPLE_PAYLOAD)
    payload["options"][1].update(delta)
    return payload


def test_grounded_line_has_no_errors():
    assert check_grounding(GROUNDED["en"], SAMPLE_PAYLOAD, "en") == []


@pytest.mark.parametrize("locale", ["fr", "de"])
def test_only_english_is_checked(locale):
    with pytest.raises(ValueError, match="locale"):
        check_grounding(GROUNDED["en"], SAMPLE_PAYLOAD, locale)


def test_wrong_number_is_reported():
    errors = check_grounding(GROUNDED["en"].replace("+3.9", "+4.9"), SAMPLE_PAYLOAD, "en")
    assert any("4.9" in e for e in errors)


def test_wrong_sign_is_reported():
    errors = check_grounding(GROUNDED["en"].replace("+3.9", "-3.9"), SAMPLE_PAYLOAD, "en")
    assert any("3.9" in e for e in errors)


def test_rounding_edge_rounds_half_up():
    payload = payload_with(delta_win=0.0385)
    assert check_grounding(GROUNDED["en"], payload, "en") == []
    errors = check_grounding(GROUNDED["en"].replace("+3.9", "+3.8"), payload, "en")
    assert errors


def test_whole_number_casual_phrasing():
    line = "The model rates changing now about 4 points better (strong)."
    assert check_grounding(line, SAMPLE_PAYLOAD, "en") == []
    assert check_grounding(line.replace("4 points", "3 points"), SAMPLE_PAYLOAD, "en")


def test_interval_bounds_and_probabilities_are_known():
    line = "Win 72.6% against 68.7%, interval +2.1 to +5.7 (strong)."
    assert check_grounding(line, SAMPLE_PAYLOAD, "en") == []


def test_xpts_matches_with_two_decimals():
    assert check_grounding("xPts 2.39 against 2.30 (strong).", SAMPLE_PAYLOAD, "en") == []
    assert check_grounding("xPts 2.49 (strong).", SAMPLE_PAYLOAD, "en")


def test_decimal_comma_is_rejected_in_english():
    errors = check_grounding(GROUNDED["en"].replace("+3.9", "+3,9"), SAMPLE_PAYLOAD, "en")
    assert any("decimal" in e for e in errors)


def test_player_id_inside_text_is_not_read_as_a_number():
    assert check_grounding("RFC-15 comes on for RFC-03 (strong).", SAMPLE_PAYLOAD, "en") == []


def test_invented_player_is_reported():
    errors = check_grounding(GROUNDED["en"].replace("RFC-03", "RFC-99"), SAMPLE_PAYLOAD, "en")
    assert any("RFC-99" in e for e in errors)


def test_wrong_label_is_reported():
    errors = check_grounding(GROUNDED["en"].replace("strong", "lean"), SAMPLE_PAYLOAD, "en")
    assert any("strong" in e for e in errors)


def test_missing_label_is_reported():
    errors = check_grounding("RFC-03 is fading (60%).", SAMPLE_PAYLOAD, "en")
    assert any("strong" in e for e in errors)


def test_decimal_comma_with_a_matching_value_is_still_rejected():
    errors = check_grounding("Win 72,6% (strong).", SAMPLE_PAYLOAD, "en")
    assert any("decimal" in e for e in errors)


def test_narration_word_limits():
    ok = Narration(headline="RFC-03 is fading (60%)",
                   reason="Changing now: +3.9 pts win probability (strong).")
    assert check_narration(ok, SAMPLE_PAYLOAD, "en") == []
    long_headline = Narration(headline=" ".join(["word"] * 13), reason=ok.reason)
    assert any("headline" in e for e in check_narration(long_headline, SAMPLE_PAYLOAD, "en"))
    long_reason = Narration(headline=ok.headline, reason="(strong) " + " ".join(["word"] * 25))
    assert any("reason" in e for e in check_narration(long_reason, SAMPLE_PAYLOAD, "en"))


def test_value_that_rounds_to_zero_matches_either_sign():
    payload = payload_with(delta_win=-0.0004)
    for quoted in ("+0.0", "-0.0", "0.0"):
        line = f"Changing now: {quoted} pts win probability (strong)."
        assert check_grounding(line, payload, "en") == []
