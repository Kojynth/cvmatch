"""Audit helpers for CV language consistency."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from .language_policy import (
    is_mixed_or_mismatched_language,
    normalize_language_code,
)


FRENCH_NARRATIVE_MARKERS = {
    "avec",
    "des",
    "les",
    "pour",
    "dans",
    "suivre",
    "rediger",
    "redaction",
    "plans",
    "tests",
    "anomalies",
    "bilans",
    "recettes",
}
ENGLISH_NARRATIVE_MARKERS = {
    "with",
    "for",
    "and",
    "writing",
    "reports",
    "testing",
    "quality",
    "practice",
    "hands",
    "validation",
    "delivery",
}


def _contains_cross_language_markers(text: str, *, target_language: str) -> bool:
    tokens = re.findall(r"[a-zA-Z]+", str(text or "").casefold())
    if len(tokens) < 8:
        return False
    fr_count = sum(1 for token in tokens if token in FRENCH_NARRATIVE_MARKERS)
    en_count = sum(1 for token in tokens if token in ENGLISH_NARRATIVE_MARKERS)
    if target_language == "en":
        return fr_count >= 2 and en_count >= 2
    return en_count >= 2 and fr_count >= 2


def audit_cv_language_consistency(
    cv_json: Dict[str, Any],
    *,
    target_language: str,
) -> Dict[str, Any]:
    """Check generated CV sections for mixed or mismatched language."""
    payload = cv_json if isinstance(cv_json, dict) else {}
    target_raw = str(target_language or "").strip().lower()
    target = normalize_language_code(target_language)

    section_samples: List[Tuple[str, str]] = []

    def add_sample(section_name: str, value: Any) -> None:
        if not isinstance(value, str):
            return
        text = " ".join(str(value or "").split()).strip()
        if len(text) < 40:
            return
        section_samples.append((section_name, text))

    add_sample("summary", payload.get("summary"))

    experiences = payload.get("experience")
    if isinstance(experiences, list):
        for idx, entry in enumerate(experiences, start=1):
            if not isinstance(entry, dict):
                continue
            fragments: List[str] = []
            for key in ("summary",):
                value = entry.get(key)
                if isinstance(value, str) and value.strip():
                    fragments.append(value)
            highlights = entry.get("highlights")
            if isinstance(highlights, list):
                fragments.extend(
                    str(item).strip()
                    for item in highlights
                    if isinstance(item, str) and str(item).strip()
                )
            add_sample(f"experience_{idx}", " ".join(fragments))

    projects = payload.get("projects")
    if isinstance(projects, list):
        for idx, entry in enumerate(projects, start=1):
            if not isinstance(entry, dict):
                continue
            fragments: List[str] = []
            for key in ("description", "technologies"):
                value = entry.get(key)
                if isinstance(value, str) and value.strip():
                    fragments.append(value)
            add_sample(f"projects_{idx}", " ".join(fragments))

    education = payload.get("education")
    if isinstance(education, list):
        for idx, entry in enumerate(education, start=1):
            if not isinstance(entry, dict):
                continue
            details = entry.get("details")
            if isinstance(details, list):
                add_sample(
                    f"education_{idx}",
                    " ".join(
                        str(item).strip()
                        for item in details
                        if isinstance(item, str) and str(item).strip()
                    ),
                )

    mixed_sections = [
        section_name
        for section_name, text in section_samples
        if is_mixed_or_mismatched_language(text, target)
        or _contains_cross_language_markers(text, target_language=target)
    ]

    return {
        "target_language": target_raw or target,
        "normalized_target_language": target,
        "language_ok": not bool(mixed_sections),
        "mixed_language_sections": mixed_sections,
        "language_penalty": 20.0 if mixed_sections else 0.0,
    }
