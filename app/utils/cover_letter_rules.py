"""Shared cover-letter validation helpers."""

from __future__ import annotations

import re


def is_cover_letter_structure_coherent(text: str, *, language_code: str) -> bool:
    is_en = str(language_code or "").strip().lower().startswith("en")
    letter = str(text or "").strip()
    if not letter:
        return False
    lines = [line.strip() for line in letter.splitlines() if line.strip()]
    if len(lines) < 4:
        return False
    first_line = lines[0].lower()
    if is_en:
        subject_ok = first_line.startswith("subject:")
        salutation_ok = any("dear " in line.lower() for line in lines[:3])
        closing_ok = any(
            token in " ".join(lines[-3:]).lower()
            for token in ("sincerely", "best regards", "kind regards")
        )
    else:
        subject_ok = first_line.startswith("objet:")
        salutation_ok = any(
            token in " ".join(lines[:3]).lower()
            for token in ("madame", "monsieur", "madame, monsieur")
        )
        closing_ok = any(
            token in " ".join(lines[-3:]).lower()
            for token in ("cordialement", "salutations", "agreer")
        )
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", letter) if part.strip()]
    body_count = max(0, len(paragraphs) - 3)
    return bool(subject_ok and salutation_ok and closing_ok and body_count >= 2)

