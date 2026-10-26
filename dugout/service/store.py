"""Storage for decisions, cards and votes. MemoryStore is what runs: votes reset when the service
scales to zero. A Cosmos DB store behind the same Protocol is the production path (README).
"""

from __future__ import annotations

from threading import Lock
from typing import Protocol


class StoreFull(Exception):
    """The store holds as many decisions or ballots as it is allowed to."""


class Store(Protocol):
    def put_decision(self, payload: dict) -> None: ...
    def get_decision(self, decision_id: str) -> dict | None: ...
    def put_card(self, key: tuple[str, str, str], card: dict) -> None: ...
    def get_card(self, key: tuple[str, str, str]) -> dict | None: ...
    def add_vote(self, decision_id: str, viewer_id: str, option_id: str, replace: bool = False) -> bool:
        """Record the viewer's vote; False (and no change) if they already voted, unless
        `replace`. Raises StoreFull when a new ballot would go over the store's bounds."""
        ...
    def votes(self, decision_id: str) -> dict[str, str]:
        """Option id by viewer id."""
        ...


class MemoryStore:
    """Votes are bounded: the vote routes are public, and the service accepts votes for live
    cards it has no payload for, so a flood of made-up ids or viewers must not grow memory."""

    def __init__(self, max_decisions: int = 5_000, max_ballots: int = 50_000) -> None:
        self._decisions: dict[str, dict] = {}
        self._cards: dict[tuple[str, str, str], dict] = {}
        self._votes: dict[str, dict[str, str]] = {}
        self._max_decisions, self._max_ballots = max_decisions, max_ballots
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

    def add_vote(self, decision_id: str, viewer_id: str, option_id: str, replace: bool = False) -> bool:
        with self._lock:
            ballots = self._votes.get(decision_id)
            if ballots is None:
                if len(self._votes) >= self._max_decisions:
                    raise StoreFull("too many decisions with votes")
                ballots = self._votes[decision_id] = {}
            if viewer_id in ballots:
                if not replace:
                    return False
            elif len(ballots) >= self._max_ballots:
                raise StoreFull("too many votes on this decision")
            ballots[viewer_id] = option_id
            return True

    def votes(self, decision_id: str) -> dict[str, str]:
        with self._lock:
            return dict(self._votes.get(decision_id, {}))
