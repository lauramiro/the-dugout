"""Locale formatting and the template fallback (always available, also used when the model is slow)."""

from __future__ import annotations

from decimal import Decimal

from dugout.agents.grounding import Narration, PLAYER_ID, round_half_up
from dugout.agents.lexicon import DECIMAL_SEPARATOR, LOCALES, STRENGTH_LABELS

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


def _recommended_and_alternative(payload: dict) -> dict:
    """The option the strength label is about, or the best alternative to no change."""
    by_id = {o["id"]: o for o in payload["options"]}
    recommended = by_id[payload["recommendation"]["option_id"]]
    if recommended["id"] != "no_change":
        return recommended
    alternatives = [o for o in payload["options"] if o["id"] != "no_change"]
    return max(alternatives, key=lambda o: o["delta_win"]) if alternatives else recommended


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
    option = _recommended_and_alternative(payload)
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
        "headline": "{player} is fading ({condition}%).",
        "headline_plain": "Change under review for {player}.",
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
        "headline": "{player} se está agotando ({condition}%).",
        "headline_plain": "Cambio en estudio para {player}.",
        "headline_none": "Sustitución en estudio.",
        "interval": ", intervalo del 90%: {ci_low} a {ci_high}",
        "units": ("punto", "puntos"), "better": "mejor", "worse": "peor",
        "analyst": {
            "change": "Cambiar ahora: {delta} pts de probabilidad de victoria{interval} ({strength}).",
            "keep": "Mejor no cambiar: cambiar ahora mueve la probabilidad de victoria {delta} pts{interval} ({strength}).",
            "close": "Las opciones están muy parejas: cambiar ahora mueve la probabilidad de victoria {delta} pts{interval} ({strength}).",
        },
        "casual": {
            "change": "El modelo valora cambiar ahora unos {n} {unit} {direction} ({strength}).",
            "keep": "Mejor no cambiar: el modelo valora cambiar ahora unos {n} {unit} peor ({strength}).",
            "close": "Las opciones están muy parejas: el modelo no ve apenas diferencia ({strength}).",
        },
    },
    "ca": {
        "headline": "{player} s'està esgotant ({condition}%).",
        "headline_plain": "Canvi en estudi per a {player}.",
        "headline_none": "Substitució en estudi.",
        "interval": ", interval del 90%: {ci_low} a {ci_high}",
        "units": ("punt", "punts"), "better": "millor", "worse": "pitjor",
        "analyst": {
            "change": "Canviar ara: {delta} punts de probabilitat de victòria{interval} ({strength}).",
            "keep": "Millor no canviar: canviar ara mou la probabilitat de victòria {delta} punts{interval} ({strength}).",
            "close": "Les opcions estan molt igualades: canviar ara mou la probabilitat de victòria {delta} punts{interval} ({strength}).",
        },
        "casual": {
            "change": "El model valora canviar ara uns {n} {unit} {direction} ({strength}).",
            "keep": "Millor no canviar: el model valora canviar ara uns {n} {unit} pitjor ({strength}).",
            "close": "Les opcions estan molt igualades: el model gairebé no hi veu diferència ({strength}).",
        },
    },
}


def template_narration(payload: dict, locale: str, mode: str) -> Narration:
    if mode not in MODES:
        raise ValueError(f"unknown mode: {mode}")
    values = format_payload(payload, locale)
    text = _TEXT[locale]
    strength = payload["recommendation"]["strength"]
    option = _recommended_and_alternative(payload)

    if "player" not in values:
        headline = text["headline_none"]
    elif "condition" not in values:
        headline = text["headline_plain"].format(**values)
    else:
        headline = text["headline"].format(**values)

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
