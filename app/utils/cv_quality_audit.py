"""Quality audit helpers for generated CV payloads.

The goal is to catch CVs that are lexically aligned with the offer but still
fail basic recruiter-facing quality constraints such as date consistency,
missing durations, and overlong pseudo-bullets.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List

try:
    from ..logging.safe_logger import get_safe_logger
    from ..config import DEFAULT_PII_CONFIG

    logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)
except Exception:  # pragma: no cover - fallback import path
    import logging

    logger = logging.getLogger(__name__)

from .title_cleaner import clean_title_simple


_PRESENT_TOKENS = {
    # English / French
    "present",
    "current",
    "en cours",
    "aujourd'hui",
    "aujourd hui",
    "maintenant",
    # Japanese
    "現在",
    "現職",
    # Chinese
    "至今",
    "现在",
    # Korean
    "현재",
}

_PERSONAL_PRONOUN_PATTERNS = {
    "fr": re.compile(r"\b(?:je|j'|moi|mon|ma|mes|notre|nos)\b", re.IGNORECASE),
    "en": re.compile(r"\b(?:i|my|mine|we|our|ours)\b", re.IGNORECASE),
}

_CLICHE_PATTERNS = {
    "fr": re.compile(
        r"\b(?:rigoureux|rigoureuse|efficace|efficacite|dynamique|motive|motivation|"
        r"polyvalent|polyvalente|curieux|curieuse|savoir vendre ses idees)\b",
        re.IGNORECASE,
    ),
    "en": re.compile(
        r"\b(?:dynamic|motivated|motivating|efficient|efficiency|passionate|"
        r"results-oriented|team player|hard-working)\b",
        re.IGNORECASE,
    ),
}

_INLINE_PSEUDO_BULLET_PATTERN = re.compile(
    r"(?:[:;]\s*[-•])|(?:\s-\s+\w.{15,}\s*;\s*-\s+\w)",
    re.IGNORECASE,
)

_WORD_PATTERN = re.compile(r"\b\S+\b", re.UNICODE)
_MODE_OR_LOCATION_SUFFIXES = {
    "remote",
    "hybrid",
    "on site",
    "onsite",
    "on-site",
    "teletravail",
    "télétravail",
    "presentiel",
    "présentiel",
    "paris",
    "france",
    "london",
    "berlin",
    "madrid",
    "tokyo",
}
_REGION_CODE_SUFFIXES = {
    "fr",
    "fra",
    "uk",
    "us",
    "usa",
    "eu",
    "emea",
    "apac",
    "latam",
    "anz",
}
_PURE_DATE_OR_PERIOD_SUFFIX = re.compile(
    r"^(?:\d{4}(?:\s*[-/]\s*\d{4})?|(?:0?[1-9]|1[0-2])/\d{4}|q[1-4]\s*\d{4})$",
    re.IGNORECASE,
)


def _should_strip_trailing_parenthetical(content: str) -> bool:
    text = str(content or "").strip()
    if not text:
        return False
    lowered = text.casefold()
    if lowered in _MODE_OR_LOCATION_SUFFIXES:
        return True
    if lowered in _REGION_CODE_SUFFIXES:
        return True
    if _PURE_DATE_OR_PERIOD_SUFFIX.fullmatch(lowered):
        return True
    tokens = [token for token in re.split(r"[\s,;/()-]+", lowered) if token]
    if tokens and all(
        token in _MODE_OR_LOCATION_SUFFIXES
        or token in _REGION_CODE_SUFFIXES
        or bool(_PURE_DATE_OR_PERIOD_SUFFIX.fullmatch(token))
        for token in tokens
    ):
        return True
    return False


def clean_target_job_title(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        cleaned = clean_title_simple(text, max_length=120).strip()
    except Exception:
        cleaned = text
    trailing_group = re.search(r"\s+\(([^()]{2,40})\)\s*$", cleaned)
    if trailing_group:
        content = trailing_group.group(1).strip()
        if _should_strip_trailing_parenthetical(content):
            cleaned = cleaned[: trailing_group.start()].rstrip(" ,-")
    return cleaned.strip()


def _word_count(text: Any) -> int:
    return len(_WORD_PATTERN.findall(str(text or "").strip()))


def _as_text_items(values: Iterable[Any]) -> List[str]:
    output: List[str] = []
    for value in values:
        if isinstance(value, str) and value.strip():
            output.append(value.strip())
    return output


def _classify_date_format(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    lowered = text.lower()
    if lowered in _PRESENT_TOKENS or text in _PRESENT_TOKENS:
        return "present"
    if re.fullmatch(r"(0[1-9]|1[0-2])/\d{4}", text):
        return "mm/yyyy"
    if re.fullmatch(r"\d{4}", text):
        return "yyyy"
    # CJK locale-native date formats (Japanese/Chinese: YYYY年MM月, Korean: YYYY.MM)
    if re.fullmatch(r"\d{4}年(0[1-9]|1[0-2])月", text):
        return "mm/yyyy"
    if re.fullmatch(r"\d{4}\.(0[1-9]|1[0-2])", text):
        return "mm/yyyy"
    if re.fullmatch(r"\d{4}年", text):
        return "yyyy"
    return "other"


def _has_reliable_duration_dates(entry: Dict[str, Any]) -> bool:
    start_format = _classify_date_format(entry.get("start_date"))
    end_format = _classify_date_format(entry.get("end_date"))
    if not start_format:
        return False
    if end_format in {"mm/yyyy", "yyyy", "present"}:
        return True
    return False


def _collect_text_sections(cv_json: Dict[str, Any]) -> List[str]:
    sections: List[str] = []
    summary = cv_json.get("summary")
    if isinstance(summary, str) and summary.strip():
        sections.append(summary.strip())

    for entry in cv_json.get("experience") or []:
        if not isinstance(entry, dict):
            continue
        if isinstance(entry.get("summary"), str) and entry.get("summary").strip():
            sections.append(entry["summary"].strip())
        sections.extend(_as_text_items(entry.get("highlights") or []))

    for entry in cv_json.get("projects") or []:
        if not isinstance(entry, dict):
            continue
        if isinstance(entry.get("description"), str) and entry.get("description").strip():
            sections.append(entry["description"].strip())

    return sections


def build_cv_quality_audit(
    cv_json: Dict[str, Any],
    *,
    target_language: str = "",
) -> Dict[str, Any]:
    payload = cv_json if isinstance(cv_json, dict) else {}
    language = str(target_language or "").strip().lower()

    date_values: List[str] = []
    bullet_count_issues: List[str] = []
    bullet_length_issues: List[str] = []
    summary_length_issues: List[str] = []
    duration_missing: List[str] = []
    ats_text_issues: List[str] = []
    personal_pronoun_sections: List[str] = []
    cliche_sections: List[str] = []

    top_summary = str(payload.get("summary") or "").strip()
    if _word_count(top_summary) > 38:
        summary_length_issues.append("summary")

    for idx, entry in enumerate(payload.get("experience") or [], start=1):
        if not isinstance(entry, dict):
            continue
        label = f"experience_{idx}"
        highlights = _as_text_items(entry.get("highlights") or [])
        entry_summary = str(entry.get("summary") or "").strip()
        if highlights and not 2 <= len(highlights) <= 4:
            bullet_count_issues.append(label)
        elif not highlights and not entry_summary:
            bullet_count_issues.append(label)

        for bullet_index, bullet in enumerate(highlights, start=1):
            if _word_count(bullet) > 40:
                bullet_length_issues.append(f"{label}.highlight_{bullet_index}")

        if entry_summary and _word_count(entry_summary) > 38:
            summary_length_issues.append(label)

        if _has_reliable_duration_dates(entry) and not str(entry.get("duration") or "").strip():
            duration_missing.append(label)

        for field in ("start_date", "end_date"):
            value = str(entry.get(field) or "").strip()
            if value:
                date_values.append(value)

    for idx, entry in enumerate(payload.get("education") or [], start=1):
        if not isinstance(entry, dict):
            continue
        for field in ("start_date", "end_date"):
            value = str(entry.get(field) or "").strip()
            if value:
                date_values.append(value)

    concrete_formats = {
        fmt for fmt in (_classify_date_format(value) for value in date_values) if fmt
    }
    date_format_ok = True
    if "other" in concrete_formats:
        date_format_ok = False

    for section_name, text in [("summary", top_summary)]:
        if text and _INLINE_PSEUDO_BULLET_PATTERN.search(text):
            ats_text_issues.append(section_name)
    for idx, entry in enumerate(payload.get("experience") or [], start=1):
        if not isinstance(entry, dict):
            continue
        text = str(entry.get("summary") or "").strip()
        if text and _INLINE_PSEUDO_BULLET_PATTERN.search(text):
            ats_text_issues.append(f"experience_{idx}")

    sections = _collect_text_sections(payload)
    language_supported = language.startswith(("fr", "en"))
    if language_supported:
        lang_key = "en" if language.startswith("en") else "fr"
        pronoun_pattern = _PERSONAL_PRONOUN_PATTERNS.get(lang_key)
        cliche_pattern = _CLICHE_PATTERNS.get(lang_key)
        for idx, text in enumerate(sections, start=1):
            section_name = f"text_section_{idx}"
            if pronoun_pattern and pronoun_pattern.search(text):
                personal_pronoun_sections.append(section_name)
            if cliche_pattern and cliche_pattern.search(text):
                cliche_sections.append(section_name)

    score = 100.0
    penalties: Dict[str, float] = {}

    def apply_penalty(key: str, amount: float) -> None:
        nonlocal score
        penalties[key] = round(amount, 2)
        score = max(0.0, score - amount)

    if not date_format_ok:
        apply_penalty("date_format", 12.0)
    if duration_missing:
        apply_penalty("duration", min(14.0, 6.0 + (2.0 * len(duration_missing))))
    if bullet_count_issues:
        apply_penalty(
            "bullet_count",
            min(20.0, 8.0 + (2.0 * max(0, len(bullet_count_issues) - 1))),
        )
    if bullet_length_issues:
        apply_penalty(
            "bullet_length",
            min(18.0, 6.0 + (2.0 * len(bullet_length_issues))),
        )
    if summary_length_issues:
        apply_penalty(
            "summary_density",
            min(16.0, 5.0 + (2.0 * len(summary_length_issues))),
        )
    if ats_text_issues:
        apply_penalty("ats_text", min(14.0, 8.0 + (2.0 * len(ats_text_issues))))
    if personal_pronoun_sections:
        apply_penalty("personal_pronouns", min(10.0, 4.0 + len(personal_pronoun_sections)))
    if cliche_sections:
        apply_penalty("cliches", min(8.0, 3.0 + len(cliche_sections)))

    sufficient = (
        score >= 72.0
        and date_format_ok
        and not duration_missing
        and not bullet_count_issues
        and not bullet_length_issues
        and not ats_text_issues
    )

    audit = {
        "score": round(score, 2),
        "penalty": round(100.0 - score, 2),
        "sufficient": bool(sufficient),
        "target_language": language,
        "language_style_supported": bool(language_supported),
        "cleaned_target_job_title": clean_target_job_title(payload.get("target_job_title") or ""),
        "date_format_ok": bool(date_format_ok),
        "duration_ok": not bool(duration_missing),
        "bullets_ok": not bool(bullet_count_issues or bullet_length_issues),
        "ats_text_ok": not bool(ats_text_issues),
        "bullet_count_issues": bullet_count_issues,
        "bullet_length_issues": bullet_length_issues,
        "summary_length_issues": summary_length_issues,
        "duration_missing": duration_missing,
        "ats_text_issues": ats_text_issues,
        "personal_pronoun_sections": personal_pronoun_sections,
        "cliche_sections": cliche_sections,
        "penalties": penalties,
    }

    if not sufficient:
        logger.info(
            "CV quality audit insufficient: score=%s date_ok=%s duration_missing=%s bullet_count=%s bullet_length=%s ats=%s",
            audit["score"],
            audit["date_format_ok"],
            len(duration_missing),
            len(bullet_count_issues),
            len(bullet_length_issues),
            len(ats_text_issues),
        )

    return audit
