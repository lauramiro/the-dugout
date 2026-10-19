"""Storage for decisions, cards and votes. Cosmos DB replaces MemoryStore later (decision 16)."""

from __future__ import annotations

from threading import Lock
from typing import Protocol


class Store(Protocol):
    def put_decision(self, payload: dict) -> None: ...
    def get_decision(self, decision_id: str) -> dict | None: ...
    def put_card(self, key: tuple[str, str, str], card: dict) -> None: ...
    def get_card(self, key: tuple[str, str, str]) -> dict | None: ...
    def add_vote(self, decision_id: str, viewer_id: str, option_id: str) -> bool:
        """Record the viewer's vote; False (and no change) if they already voted."""
        ...
    def votes(self, decision_id: str) -> dict[str, str]:
        """Option id by viewer id."""
        ...


class MemoryStore:
    def __init__(self) -> None:
        self._decisions: dict[str, dict] = {}
        self._cards: dict[tuple[str, str, str], dict] = {}
        self._votes: dict[str, dict[str, str]] = {}
        self._lock = Lock()

    def put_decision(self, payload: dict) -> None:
        with self._lock:
            self._decisions[payload["decision_id"]] = payload

    def get_decision(self, decision_id: str) -> dict | None:
        return self._decisions.get(decision_id)

    def put_card(self, key: tuple[str, str, str], card: dict) -> None:
        with self._lock:
            self._cards[key] = card

    def get_card(self, key: tuple[str, str, str]) -> dict | None:
        return self._cards.get(key)

    def add_vote(self, decision_id: str, viewer_id: str, option_id: str) -> bool:
        with self._lock:
            ballots = self._votes.setdefault(decision_id, {})
            if viewer_id in ballots:
                return False
            ballots[viewer_id] = option_id
            return True

    def votes(self, decision_id: str) -> dict[str, str]:
        with self._lock:
            return dict(self._votes.get(decision_id, {}))
