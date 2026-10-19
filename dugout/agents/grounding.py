"""Deterministic grounding check: the code that stands between the agents and the screen.

Every number in a text must match a payload field after rounding, every player id
must exist in the payload, the strength label must match the recommendation, and
a narration must respect the word limits. An empty error list means grounded.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from dugout.agents.lexicon import DECIMAL_SEPARATOR, LOCALES, STRENGTH_LABELS

MAX_HEADLINE_WORDS = 12
MAX_REASON_WORDS = 25
INTERVAL_PERCENT = 90

_PLAYER_ID = re.compile(r"\b[A-Z]{2,4}-\d{2,3}\b")
_NUMBER = re.compile(r"(?<!\w)([+\-−])?(\d+)(?:([.,])(\d+))?")


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


def payload_player_ids(payload: dict) -> set[str]:
    found: set[str] = set()

    def walk(node) -> None:
        if isinstance(node, str):
            found.update(_PLAYER_ID.findall(node))
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

    known_ids = payload_player_ids(payload)
    for player_id in dict.fromkeys(_PLAYER_ID.findall(text)):
        if player_id not in known_ids:
            errors.append(f"player {player_id} is not in the payload")

    candidates = payload_numbers(payload)
    separator = DECIMAL_SEPARATOR[locale]
    for match in _NUMBER.finditer(_PLAYER_ID.sub(" ", text)):
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

    strength = payload["recommendation"]["strength"]
    labels = STRENGTH_LABELS[locale]
    if not _word_boundary(labels[strength]).search(text):
        errors.append(f"strength label '{labels[strength]}' is missing")
    for other, label in labels.items():
        if other != strength and _word_boundary(label).search(text):
            errors.append(
                f"strength label '{label}' contradicts the recommendation ('{labels[strength]}')"
            )
    return errors


def check_narration(narration: Narration, payload: dict, locale: str) -> list[str]:
    errors = check_grounding(narration.text, payload, locale)
    if len(narration.headline.split()) > MAX_HEADLINE_WORDS:
        errors.append(f"headline is longer than {MAX_HEADLINE_WORDS} words")
    if len(narration.reason.split()) > MAX_REASON_WORDS:
        errors.append(f"reason is longer than {MAX_REASON_WORDS} words")
    return errors
