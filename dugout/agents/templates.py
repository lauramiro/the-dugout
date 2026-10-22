"""Locale formatting and the template fallback (always available, also used when the model is slow)."""

from __future__ import annotations

from decimal import Decimal

from dugout.agents.grounding import Narration, PLAYER_ID, recommended_option, round_half_up
from dugout.agents.lexicon import DECIMAL_SEPARATOR, LOCALES, STRENGTH_LABELS
from dugout.stream.triggers import CONDITION_LINE

MODES = ("casual", "analyst")
WHOLE_NUMBER_MAX_POINTS = 1  # under this many points the options are "close" in casual wording


def _number(value: Decimal, digits: int, locale: str, signed: bool = False) -> str:
    rounded = round_half_up(value, digits)
    if rounded == 0:
        rounded = abs(rounded)
    text = f"{rounded:+f}" if signed else f"{rounded:f}"
    return text.replace(".", DECIMAL_SEPARATOR[locale])


def _pct(value: float) -> Decimal:
    return Decimal(str(value)) * 100


def _find_condition(payload: dict) -> dict | None:
    return next((e for e in payload.get("evidence", []) if e["type"] == "condition"), None)


def _player(payload: dict, option: dict) -> str | None:
    condition = _find_condition(payload)
    if condition and condition.get("player_id"):
        return condition["player_id"]
    found = PLAYER_ID.findall(option["label"])
    return found[0] if found else None


def format_payload(payload: dict, locale: str) -> dict[str, str]:
    """Preformat the payload numbers for a locale, so no model has to round or localize."""
    if locale not in LOCALES:
        raise ValueError(f"unknown locale: {locale}")
    option = recommended_option(payload)
    delta = _pct(option["delta_win"])
    out = {
        "minute": str(payload["t_ms"] // 60000),
        "strength": STRENGTH_LABELS[locale][payload["recommendation"]["strength"]],
        "delta": _number(delta, 1, locale, signed=True),
        "delta_whole": _number(abs(delta), 0, locale),
    }
    if (player := _player(payload, option)) is not None:
        out["player"] = player
    if condition := _find_condition(payload):
        out["condition"] = _number(_pct(condition["value"]), 0, locale)
    if "ci90" in option:
        low, high = option["ci90"]
        out["ci_low"] = _number(_pct(low), 1, locale, signed=True)
        out["ci_high"] = _number(_pct(high), 1, locale, signed=True)
    for item in payload["options"]:
        for key in ("win", "draw", "loss"):
            out[f"{key}_{item['id']}"] = _number(_pct(item[key]), 1, locale)
        out[f"xpts_{item['id']}"] = _number(Decimal(str(item["xpts"])), 2, locale)
    return out


_TEXT = {
    "en": {
        # Per trigger: the player fading (only below the condition line), else the plain line.
        "headline": {
            "condition_drop": ("{player} is fading ({condition}%).", "Change under review for {player}."),
            "goal_after_55": ("After the goal, {player} is fading ({condition}%).",
                              "After the goal: a change under review."),
            "manager_sub": ("After the change, {player} is fading ({condition}%).",
                            "After the change: the next move under review."),
        },
        "headline_none": "Substitution under review.",
        "interval": ", 90% interval {ci_low} to {ci_high}",
        "units": ("point", "points"), "better": "better", "worse": "worse",
        "analyst": {
            "change": "Changing now: {delta} pts win probability{interval} ({strength}).",
            "keep": "No change is the better option: changing now moves win probability by {delta} pts{interval} ({strength}).",
            "close": "The options are close: changing now moves win probability by {delta} pts{interval} ({strength}).",
        },
        "casual": {
            "change": "The model rates changing now about {n} {unit} {direction} ({strength}).",
            "keep": "No change looks better: the model rates changing now about {n} {unit} worse ({strength}).",
            "close": "The options are close: the model sees almost no difference ({strength}).",
        },
    },
    "es": {
        "headline": {
            "condition_drop": ("{player} se está agotando ({condition}%).", "Cambio en estudio para {player}."),
            "goal_after_55": ("Tras el gol, {player} se está agotando ({condition}%).",
                              "Tras el gol: un cambio en estudio."),
            "manager_sub": ("Tras el cambio, {player} se está agotando ({condition}%).",
                            "Tras el cambio: el siguiente movimiento en estudio."),
        },
        "headline_none": "Sustitución en estudio.",
        "interval": ", intervalo del 90%: {ci_low} a {ci_high}",
        "units": ("punto", "puntos"), "better": "mejor", "worse": "peor",
        "analyst": {
            "change": "Cambiar ahora: {delta} pts de probabilidad de victoria{interval} ({strength}).",
            "keep": "Mejor no cambiar: cambiar ahora mueve la probabilidad de victoria {delta} pts{interval} ({strength}).",
            "close": "Las opciones están muy parejas: cambiar ahora mueve la probabilidad de victoria {delta} pts{interval} ({strength}).",
        },
        "casual": {
            "change": "El modelo valora cambiar ahora cerca de {n} {unit} {direction} ({strength}).",
            "keep": "Mejor no cambiar: el modelo valora cambiar ahora cerca de {n} {unit} peor ({strength}).",
            "close": "Las opciones están muy parejas: el modelo no ve apenas diferencia ({strength}).",
        },
    },
}


def template_narration(payload: dict, locale: str, mode: str) -> Narration:
    if mode not in MODES:
        raise ValueError(f"unknown mode: {mode}")
    values = format_payload(payload, locale)
    text = _TEXT[locale]
    strength = payload["recommendation"]["strength"]
    option = recommended_option(payload)

    condition = _find_condition(payload)
    fading, plain = text["headline"][payload["trigger"]]
    if condition is not None and condition["value"] < CONDITION_LINE and "player" in values:
        headline = fading.format(**values)
    elif payload["trigger"] != "condition_drop":
        headline = plain
    elif "player" in values:
        headline = plain.format(**values)
    else:
        headline = text["headline_none"]

    if strength == "toss_up":
        kind = "close"
    elif payload["recommendation"]["option_id"] == "no_change":
        kind = "keep"
    else:
        kind = "change"

    delta = _pct(option["delta_win"])
    n = round_half_up(abs(delta), 0)
    if mode == "casual" and kind != "close" and n < WHOLE_NUMBER_MAX_POINTS:
        kind = "close"
    unit = text["units"][0 if n == 1 else 1]
    direction = text["better"] if delta >= 0 else text["worse"]
    interval = text["interval"].format(**values) if "ci_low" in values else ""
    reason = text[mode][kind].format(
        **values, interval=interval, n=values["delta_whole"], unit=unit, direction=direction
    )
    return Narration(headline=headline, reason=reason)
