import copy

import pytest

from dugout.agents.grounding import Narration, check_grounding, check_narration
from dugout.agents.sample import SAMPLE_PAYLOAD

GROUNDED = {
    "en": "RFC-03 is fading (60%). Changing now: +3.9 pts win probability (strong).",
    "es": "RFC-03 se esta agotando (60%). Cambiar ahora: +3,9 pts de probabilidad de victoria (fuerte).",
}


def payload_with(**delta):
    payload = copy.deepcopy(SAMPLE_PAYLOAD)
    payload["options"][1].update(delta)
    return payload


@pytest.mark.parametrize("locale", ["en", "es"])
def test_grounded_line_has_no_errors(locale):
    assert check_grounding(GROUNDED[locale], SAMPLE_PAYLOAD, locale) == []


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


def test_decimal_comma_is_parsed_for_es_and_ca():
    for locale in ("es",):
        assert check_grounding(GROUNDED[locale].replace("+3,9", "+4,9"), SAMPLE_PAYLOAD, locale)


def test_decimal_point_is_rejected_in_decimal_comma_locales():
    errors = check_grounding(GROUNDED["es"].replace("+3,9", "+3.9"), SAMPLE_PAYLOAD, "es")
    assert any("decimal" in e for e in errors)


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


def test_label_in_other_locale_is_wrong_label():
    errors = check_grounding(GROUNDED["es"].replace("fuerte", "leve"), SAMPLE_PAYLOAD, "es")
    assert any("fuerte" in e for e in errors)


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


@pytest.mark.parametrize("name", ["sub_like_for_like", "no_change", "delta_whole", "win_sub_lb", "numbers.delta"])
def test_internal_names_are_reported(name):
    errors = check_grounding(f"The model favours {name}: +3.9 pts (strong).", SAMPLE_PAYLOAD, "en")
    assert errors == [f"internal name '{name}' in the text; use plain words"]


# The tiring player in the condition evidence is the one who would come off.
@pytest.mark.parametrize("locale, text", [
    ("en", "Bring on RFC-03 as a like-for-like change (strong)."),
    ("en", "Bring RFC-03 on now (strong)."),
    ("en", "The model would send on RFC-03 (strong)."),
    ("en", "RFC-03 comes on for the last half hour (strong)."),
    ("en", "Introduce RFC-03 on the left (strong)."),
    ("es", "Que entre RFC-03 por la banda (fuerte)."),
    ("es", "Meter a RFC-03 ahora (fuerte)."),
    ("es", "Dar entrada a RFC-03 (fuerte)."),
])
def test_player_named_as_coming_on_is_reported(locale, text):
    assert check_grounding(text, SAMPLE_PAYLOAD, locale) == [
        "player RFC-03 is the one who would come off, not on"]


@pytest.mark.parametrize("locale, text", [
    ("en", "Bring on a fresh player for RFC-03 (strong)."),
    ("en", "Take RFC-03 off and bring on a like-for-like change (strong)."),
    ("en", "Replace RFC-03 now (strong)."),
    ("es", "Sacar a RFC-03 y que entre un jugador fresco (fuerte)."),
])
def test_player_coming_off_is_fine(locale, text):
    assert check_grounding(text, SAMPLE_PAYLOAD, locale) == []
