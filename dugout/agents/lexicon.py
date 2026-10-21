"""Locale constants shared by the templates and the grounding check. The project is English only."""

from __future__ import annotations

LOCALES = ("en",)

DECIMAL_SEPARATOR = {"en": "."}

# The strength label is copied from recommendation.strength, never chosen.
STRENGTH_LABELS = {
    "en": {"strong": "strong", "lean": "lean", "toss_up": "toss-up"},
}
