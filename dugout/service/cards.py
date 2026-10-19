"""Decision cards: engine payload plus pipeline narration, cached per (decision_id, locale, mode).

Numbers come from the engine payload; the pipeline only supplies text that passed the
grounding check (decision 14: narrate once per card, then serve from the cache).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from threading import Lock
from typing import Callable, Protocol

from dugout.agents.pipeline import NarrationPipeline, StubClient
from dugout.engine.payload import decide
from dugout.service.store import MemoryStore, Store

LOCALES = ("en", "es", "ca")
MODES = ("casual", "analyst")

Engine = Callable[[dict, str, str], dict]


class Narrator(Protocol):
    def run(self, payload: dict, locale: str = "en", mode: str = "casual"): ...


class CardService:
    def __init__(self, engine: Engine, pipeline: Narrator, store: Store) -> None:
        self._engine = engine
        self._pipeline = pipeline
        self._store = store
        self._locks: defaultdict[tuple[str, str, str], Lock] = defaultdict(Lock)
        self._locks_guard = Lock()

    def open(self, snapshot: dict, team: str, trigger: str) -> dict:
        """Run the engine for one decision point and keep its payload."""
        payload = self._engine(snapshot, team, trigger)
        self._store.put_decision(payload)
        return payload

    def payload(self, decision_id: str) -> dict | None:
        return self._store.get_decision(decision_id)

    def card(self, decision_id: str, locale: str, mode: str) -> dict | None:
        if locale not in LOCALES or mode not in MODES:
            raise ValueError(f"unsupported locale {locale!r} or mode {mode!r}")
        key = (decision_id, locale, mode)
        cached = self._store.get_card(key)
        if cached is not None:
            return cached
        payload = self._store.get_decision(decision_id)
        if payload is None:
            return None
        with self._key_lock(key):
            cached = self._store.get_card(key)
            if cached is None:
                narration = self._pipeline.run(payload, locale, mode)
                cached = {"decision_id": decision_id, "locale": locale, "mode": mode,
                          "payload": payload, **asdict(narration)}
                self._store.put_card(key, cached)
        return cached

    def _key_lock(self, key: tuple[str, str, str]) -> Lock:
        with self._locks_guard:
            return self._locks[key]


def default_service(store: Store | None = None) -> CardService:
    """Engine with its default sample count, narration through the stub model client."""
    return CardService(lambda snapshot, team, trigger: decide(snapshot, team, trigger),
                       NarrationPipeline(StubClient()), store or MemoryStore())
