"""Shared cover-letter validation helpers."""

from __future__ import annotations


def is_cover_letter_structure_coherent(text: str, *, language_code: str) -> bool:
    lang = str(language_code or "").strip().lower()
    is_en = lang.startswith("en")
    is_fr = lang.startswith("fr")
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
        duplicate_subject = (
            sum(1 for line in lines if line.lower().startswith("subject:")) > 1
        )
        for idx, line in enumerate(lines[:3]):
            if "dear " in line.lower():
                salutation_index = idx
                break
        salutation_ok = salutation_index >= 0
        closing_tokens = ("sincerely", "best regards", "kind regards")
    elif is_fr:
        subject_ok = first_line.startswith("objet:")
        duplicate_subject = (
            sum(1 for line in lines if line.lower().startswith("objet:")) > 1
        )
        for idx, line in enumerate(lines[:3]):
            lowered = line.lower()
            if any(
                token in lowered for token in ("madame", "monsieur", "madame, monsieur")
            ):
                salutation_index = idx
                break
        salutation_ok = salutation_index >= 0
        closing_tokens = ("cordialement", "salutations", "agreer")
    else:
        subject_labels = (
            "asunto",
            "betreff",
            "oggetto",
            "assunto",
            "betreft",
            "件名",
            "主题",
            "主題",
            "제목",
            "الموضوع",
            "тема",
        )
        first_line_raw = lines[0].strip()
        first_line_folded = first_line.casefold()
        subject_ok = (
            (":" in first_line_raw or "：" in first_line_raw)
            and len(first_line_raw) >= 6
            and (
                any(first_line_folded.startswith(label) for label in subject_labels)
                or len(first_line_raw.split()) >= 2
                or any(ord(ch) > 127 for ch in first_line_raw)
            )
        )
        first_label = first_line_raw.split(":", 1)[0].split("：", 1)[0].casefold()
        duplicate_subject = bool(
            first_label
            and sum(
                1
                for line in lines
                if line.strip().casefold().startswith(f"{first_label}:")
                or line.strip().casefold().startswith(f"{first_label}：")
            )
            > 1
        )
        salutation_index = 1 if len(lines) >= 4 else -1
        salutation_ok = salutation_index >= 0
        closing_tokens = ()
        closing_index = len(lines) - 2 if len(lines) >= 5 else len(lines) - 1
    for idx in range(len(lines) - 1, max(-1, len(lines) - 4), -1):
        lowered = lines[idx].lower()
        if closing_tokens and any(token in lowered for token in closing_tokens):
            closing_index = idx
            break
    closing_ok = closing_index >= 0
    body_ok = (
        salutation_ok
        and closing_ok
        and any(line.strip() for line in lines[salutation_index + 1 : closing_index])
    )
    return bool(
        subject_ok
        and not duplicate_subject
        and salutation_ok
        and closing_ok
        and body_ok
    )
