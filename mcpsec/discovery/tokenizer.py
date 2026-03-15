from __future__ import annotations

import re

STOP_WORDS = frozenset([
    "a", "an", "the", "to", "from", "for", "of", "in", "on",
    "at", "and", "or", "is", "it", "be", "as", "by", "with",
])


def tokenize(text: str) -> list[str]:
    """Tokenize text: split snake_case/camelCase, lowercase, remove stop words and short tokens."""
    # Split on underscores and hyphens
    parts = re.split(r"[_\-]", text)

    tokens: list[str] = []
    for part in parts:
        # Split camelCase: insert space before each uppercase letter preceded by a lowercase
        camel_split = re.sub(r"([a-z])([A-Z])", r"\1 \2", part)
        # Also split sequences like "XMLParser" → "XML Parser"
        camel_split = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", camel_split)
        tokens.extend(camel_split.split())

    # Lowercase
    tokens = [t.lower() for t in tokens]

    # Remove stop words, single chars, and empty strings
    tokens = [t for t in tokens if t and len(t) > 1 and t not in STOP_WORDS]

    # Deduplicate preserving order
    seen: set[str] = set()
    result: list[str] = []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            result.append(t)

    return result
