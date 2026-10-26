"""Decision cards: engine payload plus pipeline narration, cached per (decision_id, locale, mode).

Numbers come from the engine payload; the pipeline only supplies text that passed the
grounding check (decision 14: narrate once per card, then serve from the cache).
"""

from __future__ import annotations

import os
from collections import defaultdict
from threading import Lock
from typing import Callable, Protocol

from dugout.agents.foundry import ENV_ENDPOINT, client_from_env
from dugout.agents.lexicon import LOCALES
from dugout.agents.pipeline import NarrationPipeline, StubClient, card_fields
from dugout.agents.workflow import NarrationWorkflow
from dugout.engine.payload import decide
from dugout.service.store import MemoryStore, Store

MODES = ("casual", "analyst")

Engine = Callable[..., dict]  # (snapshot, team, trigger, *, decision_id=None)


class Narrator(Protocol):
    def run(self, payload: dict, locale: str = "en", mode: str = "casual"): ...


class CardService:
    def __init__(self, engine: Engine, pipeline: Narrator, store: Store) -> None:
        self._engine = engine
        self._pipeline = pipeline
        self.store = store
        self._locks: defaultdict[tuple[str, str, str], Lock] = defaultdict(Lock)
        self._locks_guard = Lock()

    def open(self, snapshot: dict, team: str, trigger: str, decision_id: str | None = None) -> dict:
        """Run the engine for one decision point and keep its payload. A decision point's
        own id, when given, is the payload's id."""
        payload = (self._engine(snapshot, team, trigger) if decision_id is None
                   else self._engine(snapshot, team, trigger, decision_id=decision_id))
        self.store.put_decision(payload)
        return payload

    def payload(self, decision_id: str) -> dict | None:
        return self.store.get_decision(decision_id)

    def card(self, decision_id: str, locale: str, mode: str) -> dict | None:
        if locale not in LOCALES or mode not in MODES:
            raise ValueError(f"unsupported locale {locale!r} or mode {mode!r}")
        key = (decision_id, locale, mode)
        cached = self.store.get_card(key)
        if cached is not None:
            return cached
        payload = self.store.get_decision(decision_id)
        if payload is None:
            return None
        with self._key_lock(key):
            cached = self.store.get_card(key)
            if cached is None:
                narration = self._pipeline.run(payload, locale, mode)
                cached = {"decision_id": decision_id, "locale": locale, "mode": mode,
                          "payload": payload, **card_fields(narration)}
                self.store.put_card(key, cached)
        return cached

    def _key_lock(self, key: tuple[str, str, str]) -> Lock:
        with self._locks_guard:
            return self._locks[key]


def narrated_by() -> str:
    """Who narrates cards in this process: "foundry" when FOUNDRY_ENDPOINT is set, else "templates"
    (the stub client answers with the templates). Read by /healthz and the MCP tools."""
    return "foundry" if os.environ.get(ENV_ENDPOINT) else "templates"


def default_narrator() -> Narrator:
    """The Agent Framework workflow on Foundry when FOUNDRY_ENDPOINT is set, else the stub client."""
    if narrated_by() == "foundry":
        return NarrationWorkflow(client_from_env())
    return NarrationPipeline(StubClient())


def default_service(store: Store | None = None) -> CardService:
    """Engine with its default sample count, narration from default_narrator()."""
    return CardService(lambda snapshot, team, trigger, **kw: decide(snapshot, team, trigger, **kw),
                       default_narrator(), store or MemoryStore())
