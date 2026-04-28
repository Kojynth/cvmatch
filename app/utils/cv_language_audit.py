"""Audit helpers for CV language consistency."""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Tuple

from .language_policy import (

    _language_marker_scores,
    is_mixed_or_mismatched_language,
    normalize_language_code,
    text_matches_target_language,
)


FRENCH_NARRATIVE_MARKERS = {
    "le",
    "la",
    "les",
    "de",
    "des",
    "du",
    "un",
    "une",
    "avec",
    "pour",
    "dans",
    "apres",
    "precedent",
    "repris",
    "refondu",
    "fichier",
    "suivi",
    "suivre",
    "rediger",
    "redaction",
    "automatisation",
    "ameliorer",
    "lisibilite",
    "utilisabilite",
    "tresorerie",
    "structure",
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
SCRIPT_TARGET_LANGUAGES = {"ja", "zh", "ko", "ar", "ru", "el"}


def _contains_cross_language_markers(text: str, *, target_language: str) -> bool:
    tokens = re.findall(r"[a-zA-Z]+", str(text or "").casefold())
    if len(tokens) < 8:
        return False
    fr_count = sum(1 for token in tokens if token in FRENCH_NARRATIVE_MARKERS)
    en_count = sum(1 for token in tokens if token in ENGLISH_NARRATIVE_MARKERS)
    if target_language == "en":
        return fr_count >= 2 and en_count >= 2
    return en_count >= 2 and fr_count >= 2


def _ascii_fold(text: str) -> str:
    return (
        unicodedata.normalize("NFKD", str(text or ""))
        .encode("ascii", "ignore")
        .decode("ascii")
        .casefold()
    )


def _folded_tokens(text: str) -> List[str]:
    return re.findall(r"[a-z]+", _ascii_fold(text))


def _looks_like_french_narrative_with_english_terms(text: str) -> bool:
    """Reject French narrative that only looks English because of role/tool labels."""
    tokens = _folded_tokens(text)
    if len(tokens) < 5:
        return False
    fr_count = sum(1 for token in tokens if token in FRENCH_NARRATIVE_MARKERS)
    en_count = sum(1 for token in tokens if token in ENGLISH_NARRATIVE_MARKERS)
    return fr_count >= 2 and fr_count >= en_count


def _has_strong_foreign_language_evidence(text: str, *, target_language: str) -> bool:
    target = normalize_language_code(target_language)
    scores = _language_marker_scores(text)
    target_score = int(scores.get(target) or 0)
    foreign_scores = [
        int(score or 0) for lang, score in scores.items() if lang != target
    ]
    foreign_best = max(foreign_scores, default=0)
    if foreign_best <= 0:
        return False
    if foreign_best >= 3 and foreign_best > target_score:
        return True
    return foreign_best >= 2 and target_score == 0


def is_cv_narrative_language_mismatch(text: Any, *, target_language: str) -> bool:
    value = str(text or "").strip()
    if not value:
        return False
    target = normalize_language_code(target_language)
    if target in SCRIPT_TARGET_LANGUAGES:
        return is_mixed_or_mismatched_language(value, target)
    if _contains_cross_language_markers(value, target_language=target):
        return True
    if target == "en" and _looks_like_french_narrative_with_english_terms(value):
        return True
    if _has_strong_foreign_language_evidence(value, target_language=target):
        return True
    return False


def is_cv_narrative_language_compatible(
    text: Any,
    *,
    target_language: str,
    min_tokens: int = 3,
) -> bool:
    target = normalize_language_code(target_language)
    value = str(text or "").strip()
    if not value:
        return True
    if is_cv_narrative_language_mismatch(value, target_language=target):
        return False
    if target in SCRIPT_TARGET_LANGUAGES:
        return text_matches_target_language(
            value,
            target,
            min_tokens=min_tokens,
        )
    if text_matches_target_language(value, target, min_tokens=min_tokens):
        return True
    return not _has_strong_foreign_language_evidence(value, target_language=target)


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
            description = entry.get("description")
            if isinstance(description, str) and description.strip():
                fragments.append(description)
            elif isinstance(description, list):
                fragments.extend(
                    str(item).strip()
                    for item in description
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
        if is_cv_narrative_language_mismatch(text, target_language=target)
    ]

    return {
        "target_language": target_raw or target,
        "normalized_target_language": target,
        "language_ok": not bool(mixed_sections),
        "mixed_language_sections": mixed_sections,
        "language_penalty": 20.0 if mixed_sections else 0.0,
    }
