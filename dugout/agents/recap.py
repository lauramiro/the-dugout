"""Full-time recap writer: one grounded line per decision row, per mode, with a template fallback.

Each row compares the manager's call with the model's call. The recap reuses the grounding check
unchanged by presenting the row as a payload that holds only the row's own numbers, so a line can
quote the minute, the win-probability gap and the expected-points gap and nothing else.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from dugout.agents.grounding import Narration, check_narration
from dugout.agents.pipeline import (
    DEFAULT_TIMEOUT_S,
    MAX_ATTEMPTS,
    ModelClient,
    ModelError,
    ModelTimeout,
    load_prompt,
)
from dugout.agents.lexicon import LOCALES
from dugout.agents.templates import MODES, format_payload
from dugout.engine.options import strength_label

LOCALE = "en"  # the default locale
OPTION_ID = "model_call"

# Blame, hindsight and betting wording that a recap line must never carry.
_FORBIDDEN = {
    "en": re.compile(
        r"\b(would have|would've|should have|could have|mistake|wrong|blame|betting|odds|will)\b",
        re.IGNORECASE,
    ),
    "es": re.compile(
        r"\b(habría|habrían|hubiera|hubieran|debería haber|debió|error|equivocad[oa]s?|culpa|apuestas?|cuotas)\b",
        re.IGNORECASE,
    ),
}

# The calls as the fixture script names them (the engine's labels, lower case after the first
# word). A call not listed here is shown as written.
_CALLS = {
    "es": {
        "no change": "no cambiar",
        "like-for-like substitution": "un cambio en la misma posición",
        "attacking change": "un cambio ofensivo",
        "defensive change": "un cambio defensivo",
        "a later like-for-like change": "el mismo cambio más tarde",
    },
}


@dataclass(frozen=True, slots=True)
class RecapRow:
    """One decision at full time. The gaps are the model's call minus the manager's call."""

    decision_id: str
    minute: int
    team: str
    manager_call: str
    model_call: str
    gap_win: float  # fraction, 0.039 is 3.9 points of win probability
    gap_xpts: float


@dataclass(frozen=True, slots=True)
class RecapLine:
    decision_id: str
    minute: int
    team: str
    text: str
    source: str  # "model" or "template"
    fallback: str | None = None  # "timeout", "error" or "ungrounded" when source is "template"


def recap_payload(row: RecapRow) -> dict:
    """The row as a decision payload, carrying only the row's own numbers and ids."""
    gap, xpts = abs(row.gap_win), abs(row.gap_xpts)
    return {
        "decision_id": row.decision_id,
        "t_ms": row.minute * 60000,
        "team": row.team,
        "options": [{
            "id": OPTION_ID, "label": row.model_call,
            "win": gap, "draw": gap, "loss": gap, "xpts": xpts, "delta_win": gap,
        }],
        "recommendation": {"option_id": OPTION_ID, "strength": strength_label(gap * 100)},
        "evidence": [],
        "manager_action": row.manager_call,
    }


def call_text(call: str, locale: str) -> str:
    """A call in the viewer's language. English calls are the engine's labels as given.

    A like-for-like label names its player ("like-for-like substitution for RFC-03"); the id is kept.
    """
    calls = _CALLS.get(locale)
    if calls is None:
        return call
    base, sep, player = call.partition(" for ")
    if sep and base.lower() in calls:
        return f"{calls[base.lower()]} ({player})"
    return calls.get(call.lower(), call)


def _numbers(row: RecapRow, locale: str) -> dict[str, str]:
    values = format_payload(recap_payload(row), locale)
    return {
        "minute": values["minute"],
        "strength": values["strength"],
        "delta": values["delta"],
        "delta_whole": values["delta_whole"],
        "xpts_gap": values[f"xpts_{OPTION_ID}"],
    }


def _check_locale_and_modes(locale: str, modes) -> None:
    if locale not in LOCALES:
        raise ValueError(f"unknown locale: {locale}")
    for mode in modes:
        if mode not in MODES:
            raise ValueError(f"unknown mode: {mode}")


def template_line(row: RecapRow, locale: str, mode: str) -> str:
    _check_locale_and_modes(locale, (mode,))
    v = _numbers(row, locale)
    if locale == "es":
        return _template_es(row, mode, v)
    payload = recap_payload(row)
    n = v["delta_whole"]
    unit = "point" if n == "1" else "points"
    start = f"{v['minute']}': "
    if row.manager_call == row.model_call:
        return f"{start}the manager and the model made the same call, {row.manager_call} ({v['strength']})."
    if payload["recommendation"]["strength"] == "toss_up":
        if mode == "casual":
            return (f"{start}{row.manager_call} or {row.model_call}: "
                    f"the model sees almost no difference ({v['strength']}).")
        return (f"{start}the options were close: the model put {row.model_call} {v['delta']} pts ahead "
                f"of {row.manager_call}, {v['xpts_gap']} expected points ({v['strength']}).")
    if mode == "casual":
        return (f"{start}the manager chose {row.manager_call}; the model rated {row.model_call} "
                f"about {n} {unit} better ({v['strength']}).")
    return (f"{start}the manager chose {row.manager_call}; the model preferred {row.model_call}, "
            f"{v['delta']} pts win probability, {v['xpts_gap']} expected points ({v['strength']}).")


def _template_es(row: RecapRow, mode: str, v: dict[str, str]) -> str:
    manager, model = call_text(row.manager_call, "es"), call_text(row.model_call, "es")
    n = v["delta_whole"]
    unit = "punto" if n == "1" else "puntos"
    start = f"{v['minute']}': "
    if row.manager_call == row.model_call:
        return f"{start}el entrenador y el modelo tomaron la misma decisión, {manager} ({v['strength']})."
    if recap_payload(row)["recommendation"]["strength"] == "toss_up":
        if mode == "casual":
            return f"{start}{manager} o {model}: el modelo no ve apenas diferencia ({v['strength']})."
        return (f"{start}opciones parejas: el modelo puso {model} {v['delta']} pts por delante de "
                f"{manager}, {v['xpts_gap']} puntos esperados ({v['strength']}).")
    if mode == "casual":
        return (f"{start}el entrenador eligió {manager}; el modelo valoró {model} "
                f"cerca de {n} {unit} mejor ({v['strength']}).")
    return (f"{start}el entrenador eligió {manager}; el modelo prefirió {model}, "
            f"{v['delta']} pts de victoria, {v['xpts_gap']} puntos esperados ({v['strength']}).")


def _parse(reply: str) -> str | list[str]:
    """The line, or a one-item error list when the reply is not the JSON the prompt asks for."""
    try:
        line = json.loads(reply)["line"]
    except (ValueError, KeyError, TypeError):
        return ["reply is not JSON with a line"]
    if not isinstance(line, str) or not line.strip():
        return ["reply is not JSON with a line"]
    return line.strip()


def _errors(line: str, row: RecapRow, locale: str) -> list[str]:
    errors = check_narration(Narration(headline="", reason=line), recap_payload(row), locale)
    errors += [f"'{m.group(0)}' is not allowed in a recap line" for m in _FORBIDDEN[locale].finditer(line)]
    return errors


def _write_line(row: RecapRow, locale: str, mode: str, client: ModelClient,
                timeout_s: float) -> RecapLine:
    def template(reason: str) -> RecapLine:
        return RecapLine(row.decision_id, row.minute, row.team, template_line(row, locale, mode),
                         "template", reason)

    request = {
        "target": {"locale": locale, "mode": mode},
        "row": {
            "minute": row.minute, "team": row.team,
            "manager_call": call_text(row.manager_call, locale),
            "model_call": call_text(row.model_call, locale),
            "gap_win": row.gap_win, "gap_xpts": row.gap_xpts,
        },
        "numbers": _numbers(row, locale),
    }
    system = load_prompt("recap")
    for _ in range(MAX_ATTEMPTS):
        try:
            reply = client.complete(system, json.dumps(request, ensure_ascii=False), timeout_s=timeout_s)
        except (ModelTimeout, TimeoutError):
            return template("timeout")
        except ModelError:
            return template("error")
        parsed = _parse(reply)
        errors = parsed if isinstance(parsed, list) else _errors(parsed, row, locale)
        if not errors:
            return RecapLine(row.decision_id, row.minute, row.team, parsed, "model")
        request["previous"] = reply
        request["errors"] = errors
    return template("ungrounded")


def write_recap(rows: list[RecapRow], client: ModelClient, *, locale: str = LOCALE,
                modes: tuple[str, ...] = MODES, timeout_s: float = DEFAULT_TIMEOUT_S,
                ) -> dict[str, list[RecapLine]]:
    """One line per row for each mode, in row order. A slow or failing model costs only its row."""
    _check_locale_and_modes(locale, modes)
    return {mode: [_write_line(row, locale, mode, client, timeout_s) for row in rows] for mode in modes}
