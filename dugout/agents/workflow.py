"""Narration as a Microsoft Agent Framework workflow.

narrator -> check_narrator -> localizer -> check_localizer, where each check is a plain code
step (the grounding check) and a failed check sends the stage back once with the errors
attached. Timeouts, model errors and a second failed check end in the template, exactly as in
NarrationPipeline. Docs: https://learn.microsoft.com/en-us/agent-framework/concepts/workflows/
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, replace

from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler

from dugout.agents.grounding import Narration, check_narration
from dugout.agents.pipeline import (
    DEFAULT_TIMEOUT_S,
    MAX_ATTEMPTS,
    Card,
    ModelClient,
    ModelError,
    ModelTimeout,
    build_request,
    load_prompt,
    parse_reply,
)
from dugout.agents.templates import template_narration

NARRATOR, CHECK_NARRATOR, LOCALIZER, CHECK_LOCALIZER = (
    "narrator", "check_narrator", "localizer", "check_localizer",
)


@dataclass(frozen=True, slots=True)
class Turn:
    """One model call to make: the stage, who it is for, and the retry context.

    locale and mode are the viewer's. The narrator always writes English analyst text.
    """

    stage: str  # NARRATOR or LOCALIZER
    payload: dict
    locale: str
    mode: str
    draft: Narration | None = None
    attempt: int = 0
    previous: str | None = None
    errors: list[str] | None = None

    @property
    def stage_target(self) -> tuple[str, str]:
        return ("en", "analyst") if self.stage == NARRATOR else (self.locale, self.mode)


@dataclass(frozen=True, slots=True)
class Reply:
    turn: Turn
    text: str


def _template(turn: Turn, reason: str) -> Card:
    narration = template_narration(turn.payload, turn.locale, turn.mode)
    return Card(narration.headline, narration.reason, "template", reason)


class ModelStep(Executor):
    """Calls the model for one stage. The blocking client runs in a worker thread."""

    def __init__(self, stage: str, client: ModelClient, timeout_s: float):
        super().__init__(id=stage)
        self._stage = stage
        self._client = client
        self._timeout_s = timeout_s

    @handler
    async def call(self, turn: Turn, ctx: WorkflowContext[Reply, Card]) -> None:
        locale, mode = turn.stage_target
        request = build_request(turn.payload, locale, mode, turn.draft)
        if turn.errors:
            request["previous"] = turn.previous
            request["errors"] = turn.errors
        try:
            text = await asyncio.to_thread(
                self._client.complete,
                load_prompt(self._stage),
                json.dumps(request, ensure_ascii=False),
                timeout_s=self._timeout_s,
            )
        except (ModelTimeout, TimeoutError):
            await ctx.yield_output(_template(turn, "timeout"))
        except ModelError:
            await ctx.yield_output(_template(turn, "error"))
        else:
            await ctx.send_message(Reply(turn, text))


class GroundingStep(Executor):
    """The code check between the model and the screen. No model is involved here."""

    def __init__(self, stage: str):
        super().__init__(id=f"check_{stage}")

    @handler
    async def check(self, reply: Reply, ctx: WorkflowContext[Turn, Card]) -> None:
        turn = reply.turn
        parsed = parse_reply(reply.text)
        errors = (
            [parsed] if isinstance(parsed, str)
            else check_narration(parsed, turn.payload, turn.stage_target[0])
        )
        if not errors:
            if turn.stage == NARRATOR:
                await ctx.send_message(
                    Turn(LOCALIZER, turn.payload, turn.locale, turn.mode, draft=parsed)
                )
            else:
                await ctx.yield_output(Card(parsed.headline, parsed.reason, "model"))
        elif turn.attempt + 1 < MAX_ATTEMPTS:
            await ctx.send_message(
                replace(turn, attempt=turn.attempt + 1, previous=reply.text, errors=errors)
            )
        else:
            await ctx.yield_output(_template(turn, "ungrounded"))


def _goes_to(stage: str):
    return lambda message: isinstance(message, Turn) and message.stage == stage


class NarrationWorkflow:
    """Same contract as NarrationPipeline.run, executed as a workflow graph."""

    def __init__(self, client: ModelClient, *, timeout_s: float = DEFAULT_TIMEOUT_S):
        self._client = client
        self._timeout_s = timeout_s

    def _build(self):
        narrator = ModelStep(NARRATOR, self._client, self._timeout_s)
        localizer = ModelStep(LOCALIZER, self._client, self._timeout_s)
        check_narrator = GroundingStep(NARRATOR)
        check_localizer = GroundingStep(LOCALIZER)
        return (
            WorkflowBuilder(
                start_executor=narrator,
                output_from=[narrator, check_narrator, localizer, check_localizer],
            )
            .add_edge(narrator, check_narrator)
            .add_edge(check_narrator, narrator, condition=_goes_to(NARRATOR))
            .add_edge(check_narrator, localizer, condition=_goes_to(LOCALIZER))
            .add_edge(localizer, check_localizer)
            .add_edge(check_localizer, localizer, condition=_goes_to(LOCALIZER))
            .build()
        )

    @property
    def executor_ids(self) -> list[str]:
        return [NARRATOR, CHECK_NARRATOR, LOCALIZER, CHECK_LOCALIZER]

    async def arun(self, payload: dict, locale: str = "en", mode: str = "casual") -> Card:
        result = await self._build().run(Turn(NARRATOR, payload, locale, mode))
        (card,) = result.get_outputs()
        return card

    def run(self, payload: dict, locale: str = "en", mode: str = "casual") -> Card:
        return asyncio.run(self.arun(payload, locale, mode))
