"""Per-locale constants shared by the templates and the grounding check."""

from __future__ import annotations

LOCALES = ("en", "es", "ca")

DECIMAL_SEPARATOR = {"en": ".", "es": ",", "ca": ","}

# The strength label is copied from recommendation.strength, never chosen.
STRENGTH_LABELS = {
    "en": {"strong": "strong", "lean": "lean", "toss_up": "toss-up"},
    "es": {"strong": "fuerte", "lean": "leve", "toss_up": "igualado"},
    "ca": {"strong": "forta", "lean": "lleu", "toss_up": "igualat"},
}
