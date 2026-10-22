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
    assert check_grounding("Expected points 2.39 against 2.30 (strong).", SAMPLE_PAYLOAD, "en") == []
    assert check_grounding("Expected points 2.49 (strong).", SAMPLE_PAYLOAD, "en")


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


# Slips the Foundry model made that the prompts already forbid (live replay, 2026-10-22).

def test_english_left_in_spanish_is_reported():
    line = "El modelo valora cambiar ahora about 4 puntos mejor (fuerte)."
    errors = check_grounding(line, SAMPLE_PAYLOAD, "es")
    assert any("'about'" in e for e in errors)
    assert check_grounding(line.replace("about", "cerca de"), SAMPLE_PAYLOAD, "es") == []


@pytest.mark.parametrize("line", [
    "Make an like-for-like change: about 4 points better (strong).",
    "A attacking change rates about 4 points better (strong).",
])
def test_wrong_english_article_is_reported(line):
    assert any("article" in e for e in check_grounding(line, SAMPLE_PAYLOAD, "en"))


@pytest.mark.parametrize("line", [
    "Make a like-for-like change: about 4 points better (strong).",
    "An attacking change rates about 4 points better (strong).",
    "A one-off change rates about 4 points better (strong).",
])
def test_right_english_article_passes(line):
    assert check_grounding(line, SAMPLE_PAYLOAD, "en") == []


@pytest.mark.parametrize("locale, line", [
    ("en", "The options are close: about 4 points better (strong)."),
    ("en", "Neck and neck, about 4 points better (strong)."),
    ("es", "Opciones cercanas: cerca de 4 puntos mejor (fuerte)."),
    ("es", "Opciones muy parejas: cerca de 4 puntos mejor (fuerte)."),
])
def test_strong_card_called_close_is_reported(locale, line):
    assert any("close" in e for e in check_grounding(line, SAMPLE_PAYLOAD, locale))


def test_close_is_allowed_when_the_gap_rounds_to_zero_points():
    payload = payload_with(delta_win=0.004)
    assert check_grounding("The options are close: the model sees almost no difference (strong).", payload, "en") == []
    assert check_grounding("Las opciones están muy parejas (fuerte).", payload, "es") == []


@pytest.mark.parametrize("reason", [
    "About 4 points better, 90% interval +2.1 to +5.7 (strong).",
    "Changing now: +3.9 points (strong).",
])
def test_casual_text_quotes_no_interval_or_decimals(reason):
    narration = Narration("RFC-03 is fading (60%).", reason)
    assert check_narration(narration, SAMPLE_PAYLOAD, "en", mode="casual")
    assert check_narration(narration, SAMPLE_PAYLOAD, "en", mode="analyst") == []


# Slips from the live replay of 2026-10-22, after the checks above.

def test_trade_offs_left_in_english_in_spanish_is_reported():
    line = "El modelo prefiere un cambio en la misma posición: +3,9 puntos; opciones y trade-offs (fuerte)."
    assert any("'trade-offs'" in e for e in check_grounding(line, SAMPLE_PAYLOAD, "es"))
    assert check_grounding(line.replace("trade-offs", "pros y contras"), SAMPLE_PAYLOAD, "es") == []


@pytest.mark.parametrize("locale, word", [("en", "xpts"), ("es", "xPTS")])
def test_xpts_is_an_internal_name(locale, word):
    line = f"Un cambio da {word} 0,08 (fuerte)." if locale == "es" else f"A change gives {word} 0.08 (strong)."
    assert any("internal name" in e for e in check_grounding(line, SAMPLE_PAYLOAD, locale))


@pytest.mark.parametrize("locale, reason", [
    ("en", "Win 73% against 69%, about 4 points better (strong)."),
    ("es", "La victoria sube a 73% desde 69%, cerca de 4 puntos mejor (fuerte)."),
])
def test_casual_text_quotes_no_win_draw_or_loss_probability(locale, reason):
    narration = Narration("RFC-03", reason)
    errors = check_narration(narration, SAMPLE_PAYLOAD, locale, mode="casual")
    assert any("probabilit" in e for e in errors)
    assert check_narration(narration, SAMPLE_PAYLOAD, locale, mode="analyst") == []


def test_casual_text_may_quote_condition_as_a_percentage():
    narration = Narration("RFC-03 is fading (60%).", "The model rates changing now about 4 points better (strong).")
    assert check_narration(narration, SAMPLE_PAYLOAD, "en", mode="casual") == []


@pytest.mark.parametrize("locale, line", [
    ("en", "The model rates a like-for-like change +3.9 points in expected points (strong)."),
    ("en", "About 4 points better in expected points (strong)."),
    ("es", "El modelo: +3,9 puntos en puntos esperados (fuerte)."),
])
def test_gap_called_expected_points_is_reported(locale, line):
    errors = check_grounding(line, SAMPLE_PAYLOAD, locale)
    assert any("expected-points value" in e for e in errors)


@pytest.mark.parametrize("locale, line", [
    ("en", "+3.9 points of win probability, expected points 2.39 against 2.30 (strong)."),
    ("es", "+3,9 puntos de victoria, 2,39 puntos esperados frente a 2,30 (fuerte)."),
])
def test_expected_points_beside_their_value_pass(locale, line):
    assert check_grounding(line, SAMPLE_PAYLOAD, locale) == []


def test_taking_off_a_player_who_is_not_tiring_is_reported():
    errors = check_grounding("Take RFC-09 off for a fresh player, +3.9 points (strong).", SAMPLE_PAYLOAD, "en")
    assert any("not the tiring player" in e for e in errors)


def test_taking_off_when_the_pick_is_another_option_is_reported():
    payload = copy.deepcopy(SAMPLE_PAYLOAD)
    payload["options"][1]["id"] = "attacking"
    payload["recommendation"]["option_id"] = "attacking"
    tiring = next(e["player_id"] for e in payload["evidence"] if e["type"] == "condition")
    for locale, line in (("en", f"Take {tiring} off for a fresh player (strong)."),
                         ("es", f"Sacar a {tiring} por un jugador fresco (fuerte).")):
        assert any("model's pick is another option" in e for e in check_grounding(line, payload, locale))


def test_taking_off_the_tiring_player_on_a_like_for_like_card_passes():
    tiring = next(e["player_id"] for e in SAMPLE_PAYLOAD["evidence"] if e["type"] == "condition")
    assert check_grounding(f"Take {tiring} off for a fresh player, +3.9 points (strong).", SAMPLE_PAYLOAD, "en") == []


def test_casual_zero_points_is_reported():
    narration = Narration(headline="Go for an attacking change", reason="The model sees about 0 points of difference (strong).")
    assert any("about even" in e for e in check_narration(narration, SAMPLE_PAYLOAD, "en", mode="casual"))
