"""Per-locale constants shared by the templates and the grounding check."""

from __future__ import annotations

LOCALES = ("en", "es")

DECIMAL_SEPARATOR = {"en": ".", "es": ","}

# The strength label is copied from recommendation.strength, never chosen.
STRENGTH_LABELS = {
    "en": {"strong": "strong", "lean": "lean", "toss_up": "toss-up"},
    "es": {"strong": "fuerte", "lean": "leve", "toss_up": "igualado"},
}
