"""Deterministic grounding check: the code that stands between the agents and the screen.

Every number in a text must match a payload field after rounding, every player id
must exist in the payload, the strength label must match the recommendation, no
internal name (an option id or request key) may appear, and a narration must respect
the word limits. An empty error list means grounded.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from dugout.agents.lexicon import (
    CLOSE_PHRASES, COMING_ON, DECIMAL_SEPARATOR, EXPECTED_POINTS, FOREIGN_WORDS, LOCALES, STRENGTH_LABELS,
    TAKING_OFF, TOSS_UP_ACTIONS, WRONG_ARTICLE, ZERO_POINTS,
)

MAX_HEADLINE_WORDS = 12
MAX_REASON_WORDS = 25
INTERVAL_PERCENT = 90

PLAYER_ID = re.compile(r"\b[A-Z]{2,4}-\d{2,3}\b")
_COMING_ON = {
    locale: tuple(re.compile(p.replace("{id}", rf"(?P<id>{PLAYER_ID.pattern})"), re.IGNORECASE)
                  for p in patterns)
    for locale, patterns in COMING_ON.items()
}
# Option ids and request keys (sub_like_for_like, delta_whole, numbers.delta, xpts) are not words for a viewer.
_INTERNAL_NAME = re.compile(r"\bnumbers\.\w+|\b[A-Za-z]+(?:_[A-Za-z0-9]+)+\b|\b[xX][pP][tT][sS]\b")
_NUMBER = re.compile(r"(?<!\w)([+\-−])?(\d+)(?:([.,])(\d+))?")
_FOREIGN = {locale: tuple(re.compile(rf"\b{w}\b", re.IGNORECASE) for w in words)
            for locale, words in FOREIGN_WORDS.items()}
_CLOSE = {locale: tuple(re.compile(p, re.IGNORECASE) for p in patterns) for locale, patterns in CLOSE_PHRASES.items()}
_ARTICLE = {locale: tuple(re.compile(p) for p in patterns) for locale, patterns in WRONG_ARTICLE.items()}
_TAKING_OFF = {
    locale: tuple(re.compile(p.replace("{id}", rf"(?P<id>{PLAYER_ID.pattern})"), re.IGNORECASE)
                  for p in patterns)
    for locale, patterns in TAKING_OFF.items()
}
_TOSS_UP_ACTIONS = {locale: re.compile(p, re.IGNORECASE) for locale, p in TOSS_UP_ACTIONS.items()}
_UNAS_PUNTOS = re.compile(r"\bunas\s+\d+\s+puntos?\b", re.IGNORECASE)
_ZERO_POINTS = {locale: re.compile(p, re.IGNORECASE) for locale, p in ZERO_POINTS.items()}
_EXPECTED_POINTS = {locale: re.compile(p, re.IGNORECASE) for locale, p in EXPECTED_POINTS.items()}
_INTERVAL_WORD = {"en": re.compile(r"\binterval\b", re.IGNORECASE), "es": re.compile(r"\bintervalo\b", re.IGNORECASE)}


@dataclass(frozen=True, slots=True)
class Narration:
    headline: str
    reason: str

    @property
    def text(self) -> str:
        return f"{self.headline} {self.reason}"


def round_half_up(value: Decimal, digits: int) -> Decimal:
    return value.quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP)


def _dec(value: float | int) -> Decimal:
    return Decimal(str(value))


def _pct(value: float) -> Decimal:
    return _dec(value) * 100


def recommended_option(payload: dict) -> dict:
    """The option the strength label is about, or the best alternative to no change."""
    by_id = {o["id"]: o for o in payload["options"]}
    recommended = by_id[payload["recommendation"]["option_id"]]
    if recommended["id"] != "no_change":
        return recommended
    alternatives = [o for o in payload["options"] if o["id"] != "no_change"]
    return max(alternatives, key=lambda o: o["delta_win"]) if alternatives else recommended


def payload_numbers(payload: dict) -> list[Decimal]:
    """Every figure the text may quote, in the units the viewer sees."""
    numbers = [Decimal(payload["t_ms"] // 60000), Decimal(INTERVAL_PERCENT)]
    for option in payload["options"]:
        numbers += [_pct(option[k]) for k in ("win", "draw", "loss", "delta_win")]
        numbers.append(_dec(option["xpts"]))
        numbers += [_pct(bound) for bound in option.get("ci90", [])]
    for item in payload.get("evidence", []):
        numbers += [_pct(item[k]) for k in ("value", "share", "trend_per_min") if k in item]
    return numbers


def _probabilities(payload: dict) -> list[Decimal]:
    return [_pct(option[k]) for option in payload["options"] for k in ("win", "draw", "loss")]


def _evidence_numbers(payload: dict) -> list[Decimal]:
    return [_pct(item[k]) for item in payload.get("evidence", [])
            for k in ("value", "share", "trend_per_min") if k in item]


def payload_player_ids(payload: dict) -> set[str]:
    found: set[str] = set()

    def walk(node) -> None:
        if isinstance(node, str):
            found.update(PLAYER_ID.findall(node))
        elif isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(payload)
    return found


def _matches(candidates: list[Decimal], sign: str, magnitude: Decimal, digits: int) -> bool:
    for candidate in candidates:
        if sign:
            negative = sign in "-−"
            if (candidate < 0) != negative:
                continue
            if round_half_up(candidate, digits) == (-magnitude if negative else magnitude):
                return True
        elif round_half_up(abs(candidate), digits) == magnitude:
            return True
    return False


def _word_boundary(word: str) -> re.Pattern:
    return re.compile(rf"(?<!\w){re.escape(word)}(?!\w)", re.IGNORECASE)


def check_grounding(text: str, payload: dict, locale: str) -> list[str]:
    if locale not in LOCALES:
        raise ValueError(f"unknown locale: {locale}")
    errors: list[str] = []

    if (dash := next((d for d in ("\u2014", "\u2013") if d in text), None)):
        errors.append(f"long dash '{dash}' in the text; use a comma, a colon or a full stop")
    if "~" in text:
        errors.append("'~' for about; write it in words")
    if locale == "es" and (match := _UNAS_PUNTOS.search(text)):
        errors.append(f"'{match.group(0)}': puntos is masculine, write unos")
    for name in dict.fromkeys(_INTERNAL_NAME.findall(text)):
        errors.append(f"internal name '{name}' in the text; use plain words")

    known_ids = payload_player_ids(payload)
    for player_id in dict.fromkeys(PLAYER_ID.findall(text)):
        if player_id not in known_ids:
            errors.append(f"player {player_id} is not in the payload")
    tiring = {item["player_id"] for item in payload.get("evidence", [])
              if item.get("type") == "condition" and item.get("player_id")}
    coming_on = dict.fromkeys(match.group("id") for pattern in _COMING_ON[locale]
                              for match in pattern.finditer(text))
    for player_id in (p for p in coming_on if p in tiring):
        errors.append(f"player {player_id} is the one who would come off, not on")
    taking_off = dict.fromkeys(match.group("id") for pattern in _TAKING_OFF[locale]
                               for match in pattern.finditer(text))
    pick = payload["recommendation"]["option_id"]
    for player_id in taking_off:
        if player_id not in tiring:
            errors.append(f"player {player_id} is not the tiring player; only he would come off")
        elif not pick.startswith("sub_"):
            errors.append(f"taking {player_id} off is the like-for-like change, but the model's pick is "
                          f"another option; name that option instead")

    candidates = payload_numbers(payload)
    xpts = [_dec(option["xpts"]) for option in payload["options"]]
    quotes_xpts = False
    separator = DECIMAL_SEPARATOR[locale]
    for match in _NUMBER.finditer(PLAYER_ID.sub(" ", text)):
        sign, whole, point, fraction = match.groups()
        quoted = match.group(0)
        if point and point != separator:
            errors.append(
                f"number {quoted} uses the wrong decimal separator; {locale} uses '{separator}'"
            )
            continue
        digits = len(fraction or "")
        magnitude = Decimal(f"{whole}.{fraction}" if fraction else whole)
        if not _matches(candidates, sign or "", magnitude, digits):
            errors.append(f"number {quoted} does not match any payload field")
        elif digits == 2 and _matches(xpts, sign or "", magnitude, digits):
            quotes_xpts = True
    if (match := _EXPECTED_POINTS[locale].search(text)) and not quotes_xpts:
        errors.append(f"'{match.group(0)}' without an expected-points value; "
                      "the gap between options is in points of win probability")

    for pattern in _FOREIGN[locale]:
        if (match := pattern.search(text)):
            errors.append(f"'{match.group(0)}' is not {locale}; write the whole text in {locale}")
    for pattern in _ARTICLE[locale]:
        for match in pattern.finditer(text):
            errors.append(f"wrong article '{match.group(0).strip()}' before '{text[match.end():].split()[0]}'")

    strength = payload["recommendation"]["strength"]
    whole_points = round_half_up(abs(_pct(recommended_option(payload)["delta_win"])), 0)
    if strength != "toss_up" and whole_points != 0:
        for pattern in _CLOSE[locale]:
            if (match := pattern.search(text)):
                errors.append(f"'{match.group(0)}' calls the options close, but the card is not a toss-up")
    labels = STRENGTH_LABELS[locale]
    if not _word_boundary(labels[strength]).search(text):
        errors.append(f"strength label '{labels[strength]}' is missing")
    for other, label in labels.items():
        if other != strength and _word_boundary(label).search(text):
            errors.append(
                f"strength label '{label}' contradicts the recommendation ('{labels[strength]}')"
            )
    # "The model sees a toss-up (toss-up)": the label belongs in the brackets once, not twice. "toss-up" and
    # "igualado" have no other sense here, so any second use counts; "strong" or "lean" may also be plain words
    # ("a strong drop"), so only the label right before its own brackets counts.
    label = labels[strength]
    twice = (len(_word_boundary(label).findall(text)) > 1 if strength == "toss_up"
             else re.search(rf"\b{re.escape(label)}\b[^()]{{0,3}}\(\s*{re.escape(label)}\s*\)", text, re.IGNORECASE))
    if twice:
        errors.append(f"'{label}' appears twice; write it once, as '({label})' at the end, not also in the sentence")
    # Lower case only: a reason that opens with "Igualado:" after a headline ending in "opciones" is fine.
    if locale == "es" and strength == "toss_up" and (match := re.search(r"\bopciones\s+igualado\b", text)):
        errors.append(f"'{match.group(0)}' does not agree; write 'las opciones están muy parejas (igualado)'")
    return errors


def check_narration(narration: Narration, payload: dict, locale: str, mode: str | None = None) -> list[str]:
    """check_grounding plus the word limits; with mode="casual", no interval and whole numbers only."""
    errors = check_grounding(narration.text, payload, locale)
    if payload["recommendation"]["strength"] == "toss_up" and (match := _TOSS_UP_ACTIONS[locale].search(narration.headline)):
        errors.append(f"toss-up headline calls for an action ('{match.group(0)}'); say the options are close")
    if mode == "casual":
        if _INTERVAL_WORD[locale].search(narration.text):
            errors.append("casual text does not quote the interval")
        for match in _NUMBER.finditer(PLAYER_ID.sub(" ", narration.text)):
            if match.group(4):
                errors.append(f"casual text uses whole numbers; {match.group(0)} has decimals")
        if (match := _ZERO_POINTS[locale].search(narration.text)):
            errors.append(f"'{match.group(0)}': say the options are about even, without a number")
        # Casual gives the gap in points only: rounded probabilities read as nonsense ("2% from 2%").
        # A percentage that is a piece of evidence (a player's condition) is still fine.
        probabilities, evidence = _probabilities(payload), _evidence_numbers(payload)
        text = PLAYER_ID.sub(" ", narration.text)
        for match in _NUMBER.finditer(text):
            if not text[match.end():].lstrip().startswith("%"):
                continue
            sign, whole, _, fraction = match.groups()
            magnitude = Decimal(f"{whole}.{fraction}" if fraction else whole)
            digits = len(fraction or "")
            if (_matches(probabilities, sign or "", magnitude, digits)
                    and not _matches(evidence, sign or "", magnitude, digits)):
                errors.append(f"casual text quotes no win, draw or loss probability ({match.group(0)}%); "
                              "give the gap in points")
    if len(narration.headline.split()) > MAX_HEADLINE_WORDS:
        errors.append(f"headline is longer than {MAX_HEADLINE_WORDS} words")
    if len(narration.reason.split()) > MAX_REASON_WORDS:
        errors.append(f"reason is longer than {MAX_REASON_WORDS} words")
    return errors
