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
from dugout.agents.templates import MODES, format_payload
from dugout.engine.options import strength_label

LOCALE = "en"  # the project is English only
OPTION_ID = "model_call"

# Blame, hindsight and betting wording that a recap line must never carry.
_FORBIDDEN = re.compile(
    r"\b(would have|would've|should have|could have|mistake|wrong|blame|betting|odds|will)\b",
    re.IGNORECASE,
)


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


def _numbers(row: RecapRow) -> dict[str, str]:
    values = format_payload(recap_payload(row), LOCALE)
    return {
        "minute": values["minute"],
        "strength": values["strength"],
        "delta": values["delta"],
        "delta_whole": values["delta_whole"],
        "xpts_gap": values[f"xpts_{OPTION_ID}"],
    }


def _check_locale_and_modes(locale: str, modes) -> None:
    if locale != LOCALE:
        raise ValueError(f"the recap is written in English only, not {locale}")
    for mode in modes:
        if mode not in MODES:
            raise ValueError(f"unknown mode: {mode}")


def template_line(row: RecapRow, locale: str, mode: str) -> str:
    _check_locale_and_modes(locale, (mode,))
    v = _numbers(row)
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


def _parse(reply: str) -> str | list[str]:
    """The line, or a one-item error list when the reply is not the JSON the prompt asks for."""
    try:
        line = json.loads(reply)["line"]
    except (ValueError, KeyError, TypeError):
        return ["reply is not JSON with a line"]
    if not isinstance(line, str) or not line.strip():
        return ["reply is not JSON with a line"]
    return line.strip()


def _errors(line: str, row: RecapRow) -> list[str]:
    errors = check_narration(Narration(headline="", reason=line), recap_payload(row), LOCALE)
    errors += [f"'{m.group(0)}' is not allowed in a recap line" for m in _FORBIDDEN.finditer(line)]
    return errors


def _write_line(row: RecapRow, mode: str, client: ModelClient, timeout_s: float) -> RecapLine:
    def template(reason: str) -> RecapLine:
        return RecapLine(row.decision_id, row.minute, row.team, template_line(row, LOCALE, mode),
                         "template", reason)

    request = {
        "target": {"locale": LOCALE, "mode": mode},
        "row": {
            "minute": row.minute, "team": row.team,
            "manager_call": row.manager_call, "model_call": row.model_call,
            "gap_win": row.gap_win, "gap_xpts": row.gap_xpts,
        },
        "numbers": _numbers(row),
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
        errors = parsed if isinstance(parsed, list) else _errors(parsed, row)
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
    return {mode: [_write_line(row, mode, client, timeout_s) for row in rows] for mode in modes}
