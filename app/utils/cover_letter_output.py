"""Sanitizers for generated cover-letter text."""

from __future__ import annotations

import re
from typing import List, Optional

_THINK_BLOCK_RE = re.compile(r"(?is)<think\b[^>]*>.*?</think>")
_THINK_TAG_RE = re.compile(r"(?i)</?think\b[^>]*>")
_CHATML_TOKEN_RE = re.compile(r"<\|im_(?:start|end)\|>")
_PLACEHOLDER_LINE_RE = re.compile(r"^\s*<\s*(paragraph|paragraphe)\b", re.IGNORECASE)
_SUBJECT_LINE_RE = re.compile(r"^\s*(subject:|objet:)", re.IGNORECASE)
_SALUTATION_LINE_RE = re.compile(
    r"^\s*(dear\b|madame\b|monsieur\b|madame,\s*monsieur\b)",
    re.IGNORECASE,
)
_CLOSING_LINE_RE = re.compile(
    r"^\s*(sincerely\b|best regards\b|kind regards\b|cordialement\b|salutations\b|je vous prie d['’]agreer\b)",
    re.IGNORECASE,
)
_PROMPT_MARKER_RE = re.compile(
    r"^\s*(task:|rules:|structure:|quality_review_json:|current_cover_letter:|"
    r"offer_keywords_json\b|candidate data\b|donnees candidat\b|offre cible:|target offer:|"
    r"mandatory output rules\b|sortie obligatoire\b|style directions\b|directives style\b|"
    r"user instruction\b|instruction utilisateur\b|need to ensure\b|check for any missing info\b|"
    r"structure-wise\b|finally,\s*proofread\b|output only the final letter text\b)",
    re.IGNORECASE,
)


def _collapse_blank_lines(lines: List[str]) -> List[str]:
    collapsed: List[str] = []
    last_blank = True
    for raw_line in lines:
        line = raw_line.rstrip()
        is_blank = not line.strip()
        if is_blank:
            if not last_blank:
                collapsed.append("")
            last_blank = True
            continue
        collapsed.append(line)
        last_blank = False
    while collapsed and not collapsed[-1].strip():
        collapsed.pop()
    return collapsed


def _find_first_matching_index(
    lines: List[str], pattern: re.Pattern[str]
) -> Optional[int]:
    for idx, line in enumerate(lines):
        if pattern.search(line):
            return idx
    return None


def sanitize_generated_cover_letter(text: str) -> str:
    """Strip reasoning/prompt leakage and keep only plausible letter content."""
    content = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    if not content.strip():
        return ""

    content = _THINK_BLOCK_RE.sub("\n", content)
    content = _THINK_TAG_RE.sub("", content)
    content = _CHATML_TOKEN_RE.sub("", content)

    lines = [line.rstrip() for line in content.split("\n")]
    start_idx = _find_first_matching_index(lines, re.compile(r"."))
    if start_idx is not None:
        lines = lines[start_idx:]

    letter_start_idx = _find_first_matching_index(
        lines,
        re.compile(
            r"^\s*(subject:|objet:|dear\b|madame\b|monsieur\b|madame,\s*monsieur\b)",
            re.IGNORECASE,
        ),
    )
    if letter_start_idx is not None:
        lines = lines[letter_start_idx:]

    if lines and _SUBJECT_LINE_RE.search(lines[0]):
        salutation_idx = _find_first_matching_index(lines[1:], _SALUTATION_LINE_RE)
        if salutation_idx is not None:
            salutation_idx += 1
            lines = [lines[0], ""] + lines[salutation_idx:]
        else:
            lines = [lines[0]]

    cleaned_lines: List[str] = []
    for line in lines:
        if _PLACEHOLDER_LINE_RE.search(line):
            continue
        if _PROMPT_MARKER_RE.search(line):
            break
        cleaned_lines.append(line)

    closing_idx: Optional[int] = None
    for idx in range(len(cleaned_lines) - 1, -1, -1):
        if _CLOSING_LINE_RE.search(cleaned_lines[idx]):
            closing_idx = idx
            break

    if closing_idx is not None:
        tail: List[str] = []
        non_empty_tail = 0
        for line in cleaned_lines[closing_idx + 1 :]:
            if _PROMPT_MARKER_RE.search(line):
                break
            tail.append(line)
            if line.strip():
                non_empty_tail += 1
            if non_empty_tail >= 2:
                break
        cleaned_lines = cleaned_lines[: closing_idx + 1] + tail

    cleaned_lines = _collapse_blank_lines(cleaned_lines)
    return "\n".join(cleaned_lines).strip()
