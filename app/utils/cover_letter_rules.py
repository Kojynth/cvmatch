"""Shared cover-letter validation helpers."""

from __future__ import annotations


def is_cover_letter_structure_coherent(text: str, *, language_code: str) -> bool:
    is_en = str(language_code or "").strip().lower().startswith("en")
    letter = str(text or "").strip()
    if not letter:
        return False
    lines = [line.strip() for line in letter.splitlines() if line.strip()]
    if len(lines) < 4:
        return False
    first_line = lines[0].lower()
    salutation_index = -1
    closing_index = -1
    if is_en:
        subject_ok = first_line.startswith("subject:")
        for idx, line in enumerate(lines[:3]):
            if "dear " in line.lower():
                salutation_index = idx
                break
        salutation_ok = salutation_index >= 0
        closing_tokens = ("sincerely", "best regards", "kind regards")
    else:
        subject_ok = first_line.startswith("objet:")
        for idx, line in enumerate(lines[:3]):
            lowered = line.lower()
            if any(
                token in lowered for token in ("madame", "monsieur", "madame, monsieur")
            ):
                salutation_index = idx
                break
        salutation_ok = salutation_index >= 0
        closing_tokens = ("cordialement", "salutations", "agreer")
    for idx in range(len(lines) - 1, max(-1, len(lines) - 4), -1):
        lowered = lines[idx].lower()
        if any(token in lowered for token in closing_tokens):
            closing_index = idx
            break
    closing_ok = closing_index >= 0
    body_ok = (
        salutation_ok
        and closing_ok
        and any(line.strip() for line in lines[salutation_index + 1 : closing_index])
    )
    return bool(subject_ok and salutation_ok and closing_ok and body_ok)
