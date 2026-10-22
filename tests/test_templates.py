import copy

import pytest

from dugout.agents.grounding import check_narration
from dugout.agents.sample import SAMPLE_PAYLOAD, toss_up_payload
from dugout.agents.templates import format_payload, template_narration

LOCALES = ["en", "es"]
MODES = ["casual", "analyst"]
CLOSE = {"en": "options are close", "es": "opciones estan muy parejas"}


def no_change_payload():
    payload = copy.deepcopy(SAMPLE_PAYLOAD)
    payload["options"][1].update(delta_win=-0.008, win=0.679, draw=0.245, loss=0.076,
                                 xpts=2.28, ci90=[-0.02, 0.004])
    payload["recommendation"] = {"option_id": "no_change", "strength": "lean"}
    return payload


@pytest.mark.parametrize("payload", [SAMPLE_PAYLOAD, toss_up_payload(), no_change_payload()],
                         ids=["strong", "toss_up", "no_change"])
@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("locale", LOCALES)
def test_template_output_passes_grounding(locale, mode, payload):
    narration = template_narration(payload, locale, mode)
    assert check_narration(narration, payload, locale, mode=mode) == []


def test_english_analyst_matches_the_plan_template():
    narration = template_narration(SAMPLE_PAYLOAD, "en", "analyst")
    assert narration.headline == "RFC-03 is fading (60%)."
    assert narration.reason.startswith("Changing now: +3.9 pts win probability")
    assert "(strong)" in narration.reason
    assert "+2.1 to +5.7" in narration.reason


def test_casual_uses_whole_numbers_and_plain_words():
    narration = template_narration(SAMPLE_PAYLOAD, "en", "casual")
    assert "about 4 points better" in narration.reason
    assert "3.9" not in narration.text and "2.1" not in narration.text


def test_decimal_comma_in_spanish_analyst():
    for locale in ("es",):
        narration = template_narration(SAMPLE_PAYLOAD, locale, "analyst")
        assert "+3,9" in narration.reason
        assert "+2,1" in narration.reason and "+5,7" in narration.reason


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("locale", LOCALES)
def test_toss_up_says_the_options_are_close(locale, mode):
    text = template_narration(toss_up_payload(), locale, mode).text
    normal = text.replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o")
    assert CLOSE[locale] in normal


def test_format_payload_preformats_numbers_per_locale():
    en = format_payload(SAMPLE_PAYLOAD, "en")
    es = format_payload(SAMPLE_PAYLOAD, "es")
    assert (en["delta"], es["delta"]) == ("+3.9", "+3,9")
    assert (en["ci_low"], en["ci_high"]) == ("+2.1", "+5.7")
    assert es["ci_low"] == "+2,1"
    assert en["condition"] == "60"
    assert en["delta_whole"] == "4"
    assert en["player"] == "RFC-03"
    assert es["strength"] == "fuerte"
    assert en["win_no_change"] == "68.7" and es["win_sub_lb"] == "72,6"


def test_negative_delta_reads_as_worse_in_casual():
    narration = template_narration(no_change_payload(), "en", "casual")
    assert "worse" in narration.reason


def trigger_payload(trigger: str, condition: float) -> dict:
    payload = copy.deepcopy(SAMPLE_PAYLOAD)
    payload["trigger"] = trigger
    payload["evidence"][0]["value"] = condition
    return payload


@pytest.mark.parametrize("locale", LOCALES)
def test_manager_sub_above_the_condition_line_is_not_fading(locale):
    # The 69' demo card: the manager's change raised it, the flagged player is at 75%.
    payload = trigger_payload("manager_sub", 0.75)
    narration = template_narration(payload, locale, "casual")
    assert "fading" not in narration.text and "agotando" not in narration.text
    assert narration.headline != template_narration(trigger_payload("goal_after_55", 0.75), locale, "casual").headline


@pytest.mark.parametrize("trigger", ["condition_drop", "goal_after_55", "manager_sub"])
def test_headline_says_fading_only_below_the_condition_line(trigger):
    assert "fading (60%)" in template_narration(trigger_payload(trigger, 0.60), "en", "casual").headline
    assert "fading" not in template_narration(trigger_payload(trigger, 0.75), "en", "casual").headline


@pytest.mark.parametrize("trigger", ["condition_drop", "goal_after_55", "manager_sub"])
@pytest.mark.parametrize("condition", [0.60, 0.75])
@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("locale", LOCALES)
def test_every_trigger_headline_passes_grounding(locale, mode, condition, trigger):
    payload = trigger_payload(trigger, condition)
    assert check_narration(template_narration(payload, locale, mode), payload, locale, mode=mode) == []
