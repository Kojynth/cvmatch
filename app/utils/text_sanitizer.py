"""
Text sanitizer utilities for UI messages (Windows-safe, ASCII-only fallback).

This keeps user-facing strings readable on systems with non-UTF-8 code pages
without affecting PII redaction handled by safe_logger.
"""

import unicodedata
from typing import Optional


def sanitize_ascii(text: Optional[str]) -> str:
    """Return a best-effort ASCII version of text (strip non-ASCII).

    - Normalizes to NFKD to split accents, then drops non-ASCII bytes.
    - Safe for UI popups where emojis/accents render poorly on some systems.
    """
    if not isinstance(text, str):
        return "" if text is None else str(text)
    # Normalize and strip non-ASCII
    normalized = unicodedata.normalize("NFKD", text)
    ascii_bytes = normalized.encode("ascii", "ignore")
    return ascii_bytes.decode("ascii")

