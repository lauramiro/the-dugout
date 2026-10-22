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

# English words that have no place in Spanish text: the model sometimes leaves one behind
# ("about 2 puntos mejor").
FOREIGN_WORDS = {
    "en": (),
    "es": ("the", "and", "about", "points", "point", "better", "worse", "model", "change", "changes",
           "option", "options", "with", "for", "than", "off", "fresh", "interval", "probability",
           "trade-offs", "trade-off"),
}

# Phrases that call the options close. Only a toss-up card, or one whose gap rounds to 0 points,
# may use them. "close to 4 points" and "cerca de" are about a number, not the options.
CLOSE_PHRASES = {
    "en": (r"\bclose\b(?!\s+to\b)", r"\bneck and neck\b", r"\b(?:about|roughly|nearly|almost) even\b",
           r"\bevenly matched\b"),
    "es": (r"\bcercan[oa]s?\b", r"\bparej[oa]s?\b", r"\bigualad[oa]s\b", r"\bigualada\b"),
}

# Phrases that take a player off for a fresh one: the like-for-like change. Only the tiring player
# in the condition evidence goes off, and only when that change is the model's pick (a headline
# once said "Take CAS-02 off" on a card that picked an attacking change).
TAKING_OFF = {
    "en": (r"\b(?:take|takes|taking|took)\s+{id}\s+off\b", r"\bfresh\s+(?:player|legs)\s+for\s+{id}"),
    "es": (r"\bsacar\s+a\s+{id}", r"\bsaca\s+a\s+{id}", r"\bjugador\s+fresco\s+por\s+{id}"),
}

# A casual gap of zero points: say the options are about even instead ("about 0 points better").
ZERO_POINTS = {"en": r"(?<![\d.])0\s+points?\b", "es": r"(?<![\d,])0\s+puntos?\b"}

# Expected points, which a text may name only beside an expected-points value: the gap between
# options is in points of win probability, and the model sometimes calls it expected points
# ("+5.8 points in expected points" for a 0.15 gain).
EXPECTED_POINTS = {
    "en": r"\bexpected[\s-]+points?\b",
    "es": r"\bpuntos?\s+esperados?\b",
}

# The article before a lower-case word ("an like-for-like", "a attacking change"). Upper-case
# ids ("an RFC-03") and "a one-off" are left alone.
WRONG_ARTICLE = {
    "en": (r"\b[Aa]n\s+(?=[bcdfgjklmnpqrstvwxz])", r"\b[Aa]\s+(?=[aei]|o(?!ne))"),
    "es": (),
}
