"""Narration pipeline: narrator, grounding check, localizer, grounding check, template fallback.

The model sits behind the ModelClient protocol, so the Foundry client can be added
without touching the pipeline. Any grounding failure after one retry, and any
timeout, ends in the template for the viewer's locale and mode.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Protocol

from dugout.agents.grounding import Narration, check_narration
from dugout.agents.templates import format_payload, template_narration

PROMPTS = Path(__file__).parent / "prompts"
DEFAULT_TIMEOUT_S = 3.0
MAX_ATTEMPTS = 2  # first try plus one retry with the errors attached


class ModelTimeout(Exception):
    """Raised by a ModelClient when the model does not answer in time."""


class ModelError(Exception):
    """Raised by a ModelClient on a transport or service failure (not a timeout)."""


class ModelClient(Protocol):
    def complete(self, system: str, user: str, *, timeout_s: float) -> str: ...


@cache
def load_prompt(name: str) -> str:
    return (PROMPTS / f"{name}.md").read_text(encoding="utf-8")


@dataclass(frozen=True, slots=True)
class Card:
    headline: str
    reason: str
    source: str  # "model" or "template"
    fallback: str | None = None  # "timeout", "error" or "ungrounded" when source is "template"


@dataclass(frozen=True, slots=True)
class Call:
    system: str
    user: str


@dataclass
class StubClient:
    """Local ModelClient. With a script, replies in order (an Exception item is raised).
    Without one, answers with the template for the requested target, as a perfect model would."""

    script: list[str | BaseException] | None = None
    calls: list[Call] = field(default_factory=list)

    def complete(self, system: str, user: str, *, timeout_s: float) -> str:
        self.calls.append(Call(system, user))
        if self.script is None:
            request = json.loads(user)
            target = request["target"]
            narration = template_narration(request["payload"], target["locale"], target["mode"])
            return json.dumps({"headline": narration.headline, "reason": narration.reason})
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


class _Unavailable(Exception):
    def __init__(self, reason: str):
        self.reason = reason


def parse_reply(reply: str) -> Narration | str:
    try:
        data = json.loads(reply)
        return Narration(headline=str(data["headline"]), reason=str(data["reason"]))
    except (ValueError, KeyError, TypeError):
        return "reply is not JSON with a headline and a reason"


def build_request(payload: dict, locale: str, mode: str, draft: Narration | None) -> dict:
    request = {
        "target": {"locale": locale, "mode": mode},
        "payload": payload,
        "numbers": format_payload(payload, locale),
    }
    if draft is not None:
        request["draft"] = {"headline": draft.headline, "reason": draft.reason}
    return request


class NarrationPipeline:
    def __init__(self, client: ModelClient, *, timeout_s: float = DEFAULT_TIMEOUT_S):
        self._client = client
        self._timeout_s = timeout_s

    def run(self, payload: dict, locale: str = "en", mode: str = "casual") -> Card:
        try:
            draft = self._stage(
                "narrator", payload, "en", "analyst", None,
            )
            if draft is None:
                return self._template(payload, locale, mode, "ungrounded")
            final = self._stage("localizer", payload, locale, mode, draft)
        except _Unavailable as exc:
            return self._template(payload, locale, mode, exc.reason)
        if final is None:
            return self._template(payload, locale, mode, "ungrounded")
        return Card(final.headline, final.reason, "model")

    def _stage(self, prompt: str, payload: dict, locale: str, mode: str,
               draft: Narration | None) -> Narration | None:
        request = build_request(payload, locale, mode, draft)
        system = load_prompt(prompt)
        for _ in range(MAX_ATTEMPTS):
            try:
                reply = self._client.complete(
                    system, json.dumps(request, ensure_ascii=False), timeout_s=self._timeout_s
                )
            except (ModelTimeout, TimeoutError) as exc:
                raise _Unavailable("timeout") from exc
            except ModelError as exc:
                raise _Unavailable("error") from exc
            parsed = parse_reply(reply)
            errors = [parsed] if isinstance(parsed, str) else check_narration(parsed, payload, locale, mode)
            if not errors:
                return parsed
            request["previous"] = reply
            request["errors"] = errors
        return None

    @staticmethod
    def _template(payload: dict, locale: str, mode: str, reason: str) -> Card:
        narration = template_narration(payload, locale, mode)
        return Card(narration.headline, narration.reason, "template", reason)
