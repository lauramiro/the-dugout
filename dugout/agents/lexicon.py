"""Per-locale constants shared by the templates and the grounding check."""

from __future__ import annotations

LOCALES = ("en", "es")

DECIMAL_SEPARATOR = {"en": ".", "es": ","}

# The strength label is copied from recommendation.strength, never chosen.
STRENGTH_LABELS = {
    "en": {"strong": "strong", "lean": "lean", "toss_up": "toss-up"},
    "es": {"strong": "fuerte", "lean": "leve", "toss_up": "igualado"},
}

# Phrases that put a player on the pitch. The tiring player in the condition evidence is the one
# who would come off, so that id in one of these is backwards.
# "{id}" stands for the player id pattern.
COMING_ON = {
    "en": (
        r"\b(?:bring|brings|bringing|brought|send|sends|sending|sent|put|puts|putting"
        r"|introduce|introduces|introducing|throw|throws|throwing)\s+(?:on\s+|in\s+)?{id}",
        r"{id}\s+(?:comes|come|coming|to\s+come|goes|going)\s+on\b",
    ),
    "es": (
        r"\b(?:entra|entre|entren|entrar|meter\s+a|mete\s+a|meta\s+a|metan\s+a"
        r"|dar\s+entrada\s+a|da\s+entrada\s+a)\s+{id}",
    ),
}
