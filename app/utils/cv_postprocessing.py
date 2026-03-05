"""
CV Postprocessing Module 

Centralized CV JSON postprocessing utilities.
Extracted from CVGenerationWorker in llm_worker.py.

Key features:
- Fallback CV JSON generation (deterministic)
- CV JSON sanitization and validation
- Contact information fallback
- Section merging and repair
- Text sanitization (placeholders, review markers)
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

from .cv_text_quality import clean_narrative_text

try:
    from ..logging.safe_logger import get_safe_logger
    from ..config import DEFAULT_PII_CONFIG
    logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


# Review marker patterns that indicate LLM produced meta-commentary instead of content
REVIEW_MARKERS_EN = (
    "the cv",
    "this cv",
    "resume",
    "curriculum vitae",
    "the candidate",
    "candidate should",
    "candidate must",
    "should be",
    "should include",
    "must be",
    "needs",
    "missing",
    "revise",
    "improve",
    "job offer",
    "job description",
)

REVIEW_MARKERS_FR = (
    "le cv",
    "ce cv",
    "le candidat",
    "devrait",
    "doit",
    "manque",
    "a revoir",
    "ameliorer",
)

REVIEW_MARKERS = REVIEW_MARKERS_EN + REVIEW_MARKERS_FR

# Placeholder patterns to strip from generated text
PLACEHOLDER_PATTERN = re.compile(
    r"\[(?:A COMPLETER|TO COMPLETE|VOTRE|YOUR|PROFILE_JSON|YEAR_OF_PROFILE_JSON|IMPACT)[^\]]*\]",
    re.IGNORECASE,
)

INTERNAL_MARKER_PATTERN = re.compile(
    r"(PROFILE_JSON|YEAR_OF_PROFILE_JSON)",
    re.IGNORECASE,
)


def _dedup_preserve(items: Sequence[str]) -> List[str]:
    """Deduplicate list while preserving order."""
    seen: set = set()
    output: List[str] = []
    for raw in items or []:
        text = str(raw or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(text)
    return output


def _trim_text(value: Any, max_chars: int) -> str:
    """Trim text to max characters with ellipsis."""
    text = "" if value is None else str(value)
    text = text.strip()
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars - 1].rstrip() + "…"


def text_has_review_markers(text: str) -> bool:
    """Check if text contains LLM review markers (meta-commentary).

    These markers indicate the LLM produced commentary about
    the CV rather than actual CV content.

    Args:
        text: Text to check

    Returns:
        True if review markers detected
    """
    if not text:
        return False

    lowered = text.strip().lower()

    # Check for common markers
    if any(marker in lowered for marker in REVIEW_MARKERS):
        return True

    # Check for English modal patterns
    if re.search(r"\b(should|must|needs)\b", lowered):
        return True

    return False


def strip_placeholders(text: str) -> str:
    """Remove placeholder tokens from generated text.

    Args:
        text: Text with potential placeholders

    Returns:
        Cleaned text, or empty string if internal markers remain
    """
    if not text:
        return ""

    cleaned = str(text)
    cleaned = PLACEHOLDER_PATTERN.sub("", cleaned)

    # If internal markers remain, text is invalid
    if INTERNAL_MARKER_PATTERN.search(cleaned):
        return ""

    return cleaned.strip()


def clean_text_field(
    value: Any,
    *,
    max_length: int = 0,
    check_review_markers: bool = True,
    dedupe_narrative: bool = False,
) -> str:
    """Clean a text field by removing placeholders and review markers.

    Args:
        value: Value to clean
        max_length: Maximum length (0 = no limit)
        check_review_markers: If True, return empty for review text

    Returns:
        Cleaned text
    """
    if not isinstance(value, str):
        return ""

    cleaned = strip_placeholders(value)
    if not cleaned:
        return ""

    if dedupe_narrative:
        cleaned = clean_narrative_text(cleaned)
        if not cleaned:
            return ""

    if check_review_markers and text_has_review_markers(cleaned):
        return ""

    if max_length > 0 and len(cleaned) > max_length:
        return ""

    return cleaned


def apply_contact_fallback(
    cv_json: Dict[str, Any],
    profile_json: Dict[str, Any],
    *,
    profile_name: str = "",
    profile_email: str = "",
    profile_phone: str = "",
    profile_linkedin: str = "",
) -> None:
    """Apply fallback values to CV contact section.

    Fills in missing contact fields from profile data.

    Args:
        cv_json: CV JSON to modify in place
        profile_json: Source profile JSON
        profile_name: Fallback name
        profile_email: Fallback email
        profile_phone: Fallback phone
        profile_linkedin: Fallback LinkedIn URL
    """
    if not isinstance(cv_json, dict) or not isinstance(profile_json, dict):
        return

    contact = cv_json.get("contact")
    if not isinstance(contact, dict):
        contact = {}
        cv_json["contact"] = contact

    personal = profile_json.get("personal_info")
    if not isinstance(personal, dict):
        personal = {}

    fallback = {
        "full_name": profile_name or "",
        "email": profile_email or "",
        "phone": profile_phone or "",
        "linkedin_url": profile_linkedin or "",
    }

    for field in ("full_name", "email", "phone", "linkedin_url", "location"):
        if contact.get(field):
            continue
        value = personal.get(field) or fallback.get(field)
        if value:
            contact[field] = value


def apply_target_fallback(
    cv_json: Dict[str, Any],
    *,
    job_title: str = "",
    company: str = "",
) -> None:
    """Apply fallback values for target job title and company.

    Args:
        cv_json: CV JSON to modify in place
        job_title: Fallback job title
        company: Fallback company name
    """
    if not isinstance(cv_json, dict):
        return

    if not cv_json.get("target_job_title") and job_title:
        cv_json["target_job_title"] = job_title
    if not cv_json.get("target_company") and company:
        cv_json["target_company"] = company


def summary_needs_rewrite(summary: str) -> bool:
    """Check if summary needs regeneration.

    Args:
        summary: Summary text to check

    Returns:
        True if summary is empty or contains review markers
    """
    if not summary or not summary.strip():
        return True
    return text_has_review_markers(summary)


def repair_summary_if_needed(
    cv_json_final: Dict[str, Any],
    cv_json_draft: Dict[str, Any],
) -> None:
    """Repair final summary using draft if needed.

    Args:
        cv_json_final: Final CV JSON to modify
        cv_json_draft: Draft CV JSON for fallback
    """
    if not isinstance(cv_json_final, dict):
        return

    summary = cv_json_final.get("summary") or ""
    if not summary_needs_rewrite(summary):
        return

    draft_summary = ""
    if isinstance(cv_json_draft, dict):
        draft_summary = cv_json_draft.get("summary") or ""

    if draft_summary and not summary_needs_rewrite(draft_summary):
        cv_json_final["summary"] = draft_summary
        logger.warning("Final summary looked like review text; reverted to draft summary.")
    else:
        cv_json_final["summary"] = ""
        logger.warning("Final summary looked like review text; cleared summary.")


def sanitize_cv_json_output(
    cv_json: Dict[str, Any],
    *,
    language_code: str = "fr",
) -> None:
    """Sanitize CV JSON by cleaning all text fields.

    Removes placeholders, review markers, and invalid entries.

    Args:
        cv_json: CV JSON to modify in place
        language_code: Language for default labels
    """
    if not isinstance(cv_json, dict):
        return

    fallback_category = "Skills" if language_code == "en" else "Competences"

    # Clean top-level text fields
    contact = cv_json.get("contact")
    if isinstance(contact, dict):
        for field in ("full_name", "email", "phone", "linkedin_url", "location"):
            contact[field] = clean_text_field(contact.get(field))

    cv_json["summary"] = clean_text_field(
        cv_json.get("summary") or "",
        dedupe_narrative=True,
    )
    cv_json["target_job_title"] = clean_text_field(cv_json.get("target_job_title") or "")
    cv_json["target_company"] = clean_text_field(cv_json.get("target_company") or "")

    # Clean skills
    cleaned_skills = []
    for category in cv_json.get("skills", []) or []:
        if not isinstance(category, dict):
            continue
        label = clean_text_field(category.get("category") or "")
        items = category.get("items") or []
        if not isinstance(items, list):
            items = []
        cleaned_items = []
        for item in items:
            if not isinstance(item, str):
                continue
            text = clean_text_field(item, max_length=80)
            if text and not text_has_review_markers(text):
                cleaned_items.append(text)
        cleaned_items = _dedup_preserve(cleaned_items)
        if cleaned_items:
            cleaned_skills.append({
                "category": label or fallback_category,
                "items": cleaned_items,
            })
    cv_json["skills"] = cleaned_skills

    # Clean experience
    cleaned_experience = []
    for entry in cv_json.get("experience", []) or []:
        if not isinstance(entry, dict):
            continue
        cleaned_entry = {
            "title": clean_text_field(entry.get("title") or ""),
            "company": clean_text_field(entry.get("company") or ""),
            "start_date": clean_text_field(entry.get("start_date") or ""),
            "end_date": clean_text_field(entry.get("end_date") or ""),
            "location": clean_text_field(entry.get("location") or ""),
            "summary": clean_text_field(
                entry.get("summary") or "",
                dedupe_narrative=True,
            ),
        }
        highlights = []
        for item in entry.get("highlights", []) or []:
            if isinstance(item, str):
                text = clean_text_field(item, dedupe_narrative=True)
                if text:
                    highlights.append(text)
        cleaned_entry["highlights"] = _dedup_preserve(highlights)
        if any(cleaned_entry.values()) or cleaned_entry["highlights"]:
            cleaned_experience.append(cleaned_entry)
    cv_json["experience"] = cleaned_experience

    # Clean education
    cleaned_education = []
    for entry in cv_json.get("education", []) or []:
        if not isinstance(entry, dict):
            continue
        cleaned_entry = {
            "school": clean_text_field(entry.get("school") or ""),
            "degree": clean_text_field(entry.get("degree") or ""),
            "field_of_study": clean_text_field(entry.get("field_of_study") or ""),
            "start_date": clean_text_field(entry.get("start_date") or ""),
            "end_date": clean_text_field(entry.get("end_date") or ""),
            "location": clean_text_field(entry.get("location") or ""),
            "details": [],
        }
        details = []
        for item in entry.get("details", []) or []:
            if isinstance(item, str):
                text = clean_text_field(item)
                if text:
                    details.append(text)
        cleaned_entry["details"] = _dedup_preserve(details)
        if any(
            cleaned_entry.get(f)
            for f in ("school", "degree", "field_of_study", "start_date", "end_date", "location")
        ) or cleaned_entry["details"]:
            cleaned_education.append(cleaned_entry)
    cv_json["education"] = cleaned_education

    # Clean projects
    cleaned_projects = []
    for entry in cv_json.get("projects", []) or []:
        if not isinstance(entry, dict):
            continue
        cleaned_entry = {
            "name": clean_text_field(entry.get("name") or ""),
            "description": clean_text_field(
                entry.get("description") or "",
                dedupe_narrative=True,
            ),
            "technologies": clean_text_field(entry.get("technologies") or ""),
            "url": clean_text_field(entry.get("url") or ""),
        }
        if any(cleaned_entry.values()):
            cleaned_projects.append(cleaned_entry)
    cv_json["projects"] = cleaned_projects

    # Clean languages
    cleaned_languages = []
    for entry in cv_json.get("languages", []) or []:
        if not isinstance(entry, dict):
            continue
        language = clean_text_field(entry.get("language") or "")
        level = clean_text_field(entry.get("level") or "")
        certification = clean_text_field(entry.get("certification") or "")
        if language:
            cleaned_languages.append(
                {
                    "language": language,
                    "level": level,
                    "certification": certification,
                }
            )
    cv_json["languages"] = cleaned_languages

    # Clean certifications
    cleaned_certs = []
    for entry in cv_json.get("certifications", []) or []:
        if not isinstance(entry, dict):
            continue
        cleaned_entry = {
            "name": clean_text_field(entry.get("name") or ""),
            "organization": clean_text_field(entry.get("organization") or ""),
            "date": clean_text_field(entry.get("date") or ""),
            "url": clean_text_field(entry.get("url") or ""),
        }
        if cleaned_entry.get("name"):
            cleaned_certs.append(cleaned_entry)
    cv_json["certifications"] = cleaned_certs

    # Clean ATS keywords
    if isinstance(cv_json.get("ats_keywords"), list):
        cleaned_keywords = []
        for item in cv_json.get("ats_keywords") or []:
            if isinstance(item, str):
                text = clean_text_field(item)
                if text:
                    cleaned_keywords.append(text)
        cv_json["ats_keywords"] = _dedup_preserve(cleaned_keywords)


def merge_cv_json_missing_sections(
    cv_json_final: Dict[str, Any],
    cv_json_draft: Dict[str, Any],
) -> None:
    """Merge missing sections from draft into final CV JSON.

    Args:
        cv_json_final: Final CV JSON to modify
        cv_json_draft: Draft CV JSON with potential fallback data
    """
    if not isinstance(cv_json_final, dict) or not isinstance(cv_json_draft, dict):
        return

    for key in (
        "skills",
        "experience",
        "education",
        "projects",
        "languages",
        "certifications",
    ):
        if not cv_json_final.get(key) and cv_json_draft.get(key):
            cv_json_final[key] = cv_json_draft[key]
            logger.warning("Final CVJSON missing %s; copied from draft.", key)


def _normalize_for_match(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    text = re.sub(r"[\W_]+", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _token_overlap(left: str, right: str) -> float:
    left_tokens = {tok for tok in _normalize_for_match(left).split() if len(tok) > 2}
    right_tokens = {tok for tok in _normalize_for_match(right).split() if len(tok) > 2}
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / float(max(len(left_tokens), len(right_tokens)))


def _text_similarity(left: str, right: str) -> float:
    left_norm = _normalize_for_match(left)
    right_norm = _normalize_for_match(right)
    if not left_norm or not right_norm:
        return 0.0
    return SequenceMatcher(None, left_norm, right_norm).ratio()


def _is_same_narrative(left: str, right: str) -> bool:
    left_norm = _normalize_for_match(left)
    right_norm = _normalize_for_match(right)
    if not left_norm or not right_norm:
        return False
    if left_norm == right_norm:
        return True
    if len(left_norm) >= 40 and left_norm in right_norm:
        return True
    if len(right_norm) >= 40 and right_norm in left_norm:
        return True
    return _token_overlap(left, right) >= 0.9


_CORPORATE_DESCRIPTION_HINTS = (
    " est ",
    " is ",
    "offre",
    "offres",
    "services",
    "service",
    "plateforme",
    "platform",
    "propose",
    "provides",
    "permet",
    "allows",
    "mission",
    "strategie",
    "strategy",
    "groupe",
    "group",
    "entreprise",
    "company",
    "filiale",
    "subsidiary",
    "leader",
)

_ACTION_EXPERIENCE_HINTS = (
    "managed",
    "developed",
    "implemented",
    "built",
    "designed",
    "led",
    "supported",
    "collaborated",
    "tested",
    "coordinated",
    "created",
    "analyzed",
    "improved",
    "delivered",
    "gere",
    "geree",
    "developpe",
    "realise",
    "mis en oeuvre",
    "contribue",
    "pilote",
    "assure",
    "coordonne",
    "analyse",
    "ameliore",
)


def _looks_like_company_description(text: str, company: str = "") -> bool:
    normalized = _normalize_for_match(text)
    if not normalized or len(normalized) < 50:
        return False

    company_norm = _normalize_for_match(company)
    corporate_hits = sum(
        1 for marker in _CORPORATE_DESCRIPTION_HINTS if marker in normalized
    )
    action_hits = sum(
        1 for marker in _ACTION_EXPERIENCE_HINTS if marker in normalized
    )

    company_as_subject = False
    if company_norm:
        if normalized.startswith(f"{company_norm} "):
            company_as_subject = True
        if company_norm in normalized and (
            " est " in normalized
            or " is " in normalized
            or " propose " in normalized
            or " provides " in normalized
            or " permet " in normalized
        ):
            company_as_subject = True

    if action_hits >= 2 and corporate_hits <= 1:
        return False
    if company_as_subject and corporate_hits >= 1:
        return True
    if corporate_hits >= 3 and action_hits == 0:
        return True
    return False


def _select_action_summary(
    summary: str,
    *,
    highlights: List[str],
    fallback_description: str,
    company: str,
) -> str:
    summary_text = clean_narrative_text(summary or "")
    if summary_text and not _looks_like_company_description(summary_text, company):
        return _trim_text(summary_text, 420)

    for item in highlights:
        text = clean_narrative_text(item)
        if not text:
            continue
        if _looks_like_company_description(text, company):
            continue
        return _trim_text(text, 280)

    fallback_text = clean_narrative_text(fallback_description or "")
    if fallback_text and not _looks_like_company_description(fallback_text, company):
        return _trim_text(fallback_text, 420)

    return ""


def _extract_profile_experiences(profile_json: Dict[str, Any]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    if not isinstance(profile_json, dict):
        return rows
    for item in profile_json.get("experiences") or []:
        if not isinstance(item, dict):
            continue
        row = {
            "title": clean_text_field(item.get("title") or ""),
            "company": clean_text_field(item.get("company") or ""),
            "start_date": clean_text_field(item.get("start_date") or ""),
            "end_date": clean_text_field(item.get("end_date") or ""),
            "location": clean_text_field(item.get("location") or ""),
            "description": clean_text_field(
                item.get("description") or "",
                check_review_markers=False,
                dedupe_narrative=True,
            ),
        }
        if not any(
            row.get(field)
            for field in ("title", "company", "start_date", "end_date", "location", "description")
        ):
            continue
        row["_title_norm"] = _normalize_for_match(row["title"])
        row["_company_norm"] = _normalize_for_match(row["company"])
        row["_start_norm"] = _normalize_for_match(row["start_date"])
        row["_end_norm"] = _normalize_for_match(row["end_date"])
        rows.append(row)
    return rows


def _score_profile_experience_match(entry: Dict[str, Any], profile_entry: Dict[str, Any]) -> float:
    score = 0.0

    title_norm = _normalize_for_match(entry.get("title"))
    company_norm = _normalize_for_match(entry.get("company"))
    start_norm = _normalize_for_match(entry.get("start_date"))
    end_norm = _normalize_for_match(entry.get("end_date"))

    profile_title = profile_entry.get("_title_norm", "")
    profile_company = profile_entry.get("_company_norm", "")
    profile_start = profile_entry.get("_start_norm", "")
    profile_end = profile_entry.get("_end_norm", "")

    if title_norm and profile_title:
        if title_norm == profile_title:
            score += 0.65
        else:
            score += 0.35 * _text_similarity(title_norm, profile_title)

    if company_norm and profile_company:
        if company_norm == profile_company:
            score += 0.60
        else:
            score += 0.30 * _text_similarity(company_norm, profile_company)

    if start_norm and profile_start and start_norm == profile_start:
        score += 0.12
    if end_norm and profile_end and end_norm == profile_end:
        score += 0.12

    return score


def _reconcile_experience_section(cv_json: Dict[str, Any], profile_json: Dict[str, Any]) -> None:
    if not isinstance(cv_json, dict):
        return
    experience_entries = cv_json.get("experience")
    if not isinstance(experience_entries, list):
        return

    profile_experiences = _extract_profile_experiences(profile_json)
    if not profile_experiences:
        return

    reconciled: List[Dict[str, Any]] = []
    reassigned_count = 0

    for raw_entry in experience_entries:
        if not isinstance(raw_entry, dict):
            continue

        entry = {
            "title": clean_text_field(raw_entry.get("title") or ""),
            "company": clean_text_field(raw_entry.get("company") or ""),
            "start_date": clean_text_field(raw_entry.get("start_date") or ""),
            "end_date": clean_text_field(raw_entry.get("end_date") or ""),
            "location": clean_text_field(raw_entry.get("location") or ""),
            "summary": clean_text_field(
                raw_entry.get("summary") or "",
                dedupe_narrative=True,
            ),
            "highlights": [],
        }

        highlights: List[str] = []
        for value in raw_entry.get("highlights") or []:
            if not isinstance(value, str):
                continue
            text = clean_text_field(value, dedupe_narrative=True)
            if text:
                highlights.append(text)
        highlights = _dedup_preserve(highlights)

        best_idx = -1
        best_score = 0.0
        for idx, profile_entry in enumerate(profile_experiences):
            score = _score_profile_experience_match(entry, profile_entry)
            if score > best_score:
                best_score = score
                best_idx = idx

        matched_profile = profile_experiences[best_idx] if best_idx >= 0 and best_score >= 0.45 else None
        expected_description = ""
        if matched_profile:
            expected_description = matched_profile.get("description") or ""
            for field in ("title", "company", "start_date", "end_date", "location"):
                if not entry.get(field) and matched_profile.get(field):
                    entry[field] = matched_profile[field]

        if expected_description:
            if not entry["summary"]:
                entry["summary"] = _select_action_summary(
                    "",
                    highlights=highlights,
                    fallback_description=expected_description,
                    company=entry.get("company") or "",
                )
            else:
                current_summary = entry["summary"]
                expected_overlap = _token_overlap(current_summary, expected_description)
                other_overlap = 0.0
                other_company_hit = False
                summary_norm = _normalize_for_match(current_summary)
                for idx, other in enumerate(profile_experiences):
                    if idx == best_idx:
                        continue
                    other_description = other.get("description") or ""
                    if other_description:
                        other_overlap = max(other_overlap, _token_overlap(current_summary, other_description))
                    other_company_norm = other.get("_company_norm", "")
                    if other_company_norm and other_company_norm in summary_norm:
                        other_company_hit = True

                if other_company_hit or (
                    other_overlap >= 0.42 and other_overlap > (expected_overlap + 0.12)
                ):
                    entry["summary"] = _select_action_summary(
                        "",
                        highlights=highlights,
                        fallback_description=expected_description,
                        company=entry.get("company") or "",
                    )
                    highlights = extract_experience_highlights(expected_description)
                    reassigned_count += 1

            if highlights:
                highlight_blob = " ".join(highlights)
                expected_overlap = _token_overlap(highlight_blob, expected_description)
                other_overlap = 0.0
                for idx, other in enumerate(profile_experiences):
                    if idx == best_idx:
                        continue
                    other_description = other.get("description") or ""
                    if other_description:
                        other_overlap = max(other_overlap, _token_overlap(highlight_blob, other_description))
                if other_overlap >= 0.42 and other_overlap > (expected_overlap + 0.12):
                    highlights = extract_experience_highlights(expected_description)

        summary_text = _select_action_summary(
            entry.get("summary") or "",
            highlights=highlights,
            fallback_description=expected_description,
            company=entry.get("company") or "",
        )
        summary_norm = _normalize_for_match(summary_text)
        cleaned_highlights: List[str] = []
        for highlight in highlights:
            text = clean_narrative_text(highlight)
            if not text:
                continue
            if _looks_like_company_description(text, entry.get("company") or ""):
                continue
            if summary_norm and _is_same_narrative(summary_text, text):
                continue
            cleaned_highlights.append(text)

        entry["summary"] = _trim_text(summary_text, 420)
        entry["highlights"] = _dedup_preserve(cleaned_highlights)[:4]

        if any(
            entry.get(field) for field in ("title", "company", "start_date", "end_date", "location", "summary")
        ) or entry["highlights"]:
            reconciled.append(entry)

    cv_json["experience"] = reconciled
    if reassigned_count:
        logger.warning("Experience reconciliation fixed %s likely misassigned summaries.", reassigned_count)


def _extract_profile_education(profile_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not isinstance(profile_json, dict):
        return rows

    for item in profile_json.get("education") or []:
        if not isinstance(item, dict):
            continue
        details: List[str] = []
        raw_details = item.get("details")
        if isinstance(raw_details, list):
            for value in raw_details:
                if isinstance(value, str):
                    text = clean_text_field(value, check_review_markers=False, dedupe_narrative=True)
                    if text:
                        details.append(text)
        description_text = item.get("description")
        if isinstance(description_text, str) and description_text.strip():
            text = clean_text_field(description_text, check_review_markers=False, dedupe_narrative=True)
            if text:
                details.append(text)
        grade_text = item.get("grade")
        if isinstance(grade_text, str) and grade_text.strip():
            details.append(grade_text.strip())

        row = {
            "school": clean_text_field(item.get("school") or "", check_review_markers=False),
            "degree": clean_text_field(item.get("degree") or "", check_review_markers=False),
            "field_of_study": clean_text_field(item.get("field_of_study") or "", check_review_markers=False),
            "start_date": clean_text_field(item.get("start_date") or "", check_review_markers=False),
            "end_date": clean_text_field(item.get("end_date") or "", check_review_markers=False),
            "location": clean_text_field(item.get("location") or "", check_review_markers=False),
            "details": _dedup_preserve(details)[:4],
        }
        if not any(
            row.get(field)
            for field in ("school", "degree", "field_of_study", "start_date", "end_date", "location")
        ) and not row["details"]:
            continue
        row["_school_norm"] = _normalize_for_match(row["school"])
        row["_degree_norm"] = _normalize_for_match(row["degree"])
        row["_start_norm"] = _normalize_for_match(row["start_date"])
        row["_end_norm"] = _normalize_for_match(row["end_date"])
        rows.append(row)

    return rows


def _score_profile_education_match(entry: Dict[str, Any], profile_entry: Dict[str, Any]) -> float:
    score = 0.0

    school_norm = _normalize_for_match(entry.get("school"))
    degree_norm = _normalize_for_match(entry.get("degree"))
    start_norm = _normalize_for_match(entry.get("start_date"))
    end_norm = _normalize_for_match(entry.get("end_date"))

    profile_school = profile_entry.get("_school_norm", "")
    profile_degree = profile_entry.get("_degree_norm", "")
    profile_start = profile_entry.get("_start_norm", "")
    profile_end = profile_entry.get("_end_norm", "")

    if school_norm and profile_school:
        if school_norm == profile_school:
            score += 0.65
        else:
            score += 0.30 * _text_similarity(school_norm, profile_school)

    if degree_norm and profile_degree:
        if degree_norm == profile_degree:
            score += 0.55
        else:
            score += 0.25 * _text_similarity(degree_norm, profile_degree)

    if start_norm and profile_start and start_norm == profile_start:
        score += 0.12
    if end_norm and profile_end and end_norm == profile_end:
        score += 0.12

    return score


def _education_identity(entry: Dict[str, Any]) -> str:
    parts = (
        _normalize_for_match(entry.get("school")),
        _normalize_for_match(entry.get("degree")),
        _normalize_for_match(entry.get("start_date")),
        _normalize_for_match(entry.get("end_date")),
    )
    key = "|".join(parts).strip("|")
    if key:
        return key
    return _normalize_for_match(entry.get("field_of_study"))


def _reconcile_education_section(cv_json: Dict[str, Any], profile_json: Dict[str, Any]) -> None:
    if not isinstance(cv_json, dict):
        return
    current_entries = cv_json.get("education")
    if not isinstance(current_entries, list):
        current_entries = []

    profile_education = _extract_profile_education(profile_json)
    if not profile_education:
        return

    reconciled: List[Dict[str, Any]] = []
    used_profile_indices: set = set()
    appended_count = 0

    for raw_entry in current_entries:
        if not isinstance(raw_entry, dict):
            continue
        entry = {
            "school": clean_text_field(raw_entry.get("school") or ""),
            "degree": clean_text_field(raw_entry.get("degree") or ""),
            "field_of_study": clean_text_field(raw_entry.get("field_of_study") or ""),
            "start_date": clean_text_field(raw_entry.get("start_date") or ""),
            "end_date": clean_text_field(raw_entry.get("end_date") or ""),
            "location": clean_text_field(raw_entry.get("location") or ""),
            "details": [],
        }

        details: List[str] = []
        for value in raw_entry.get("details") or []:
            if isinstance(value, str):
                text = clean_text_field(value, dedupe_narrative=True)
                if text:
                    details.append(text)
        entry["details"] = _dedup_preserve(details)[:4]

        best_idx = -1
        best_score = 0.0
        for idx, profile_entry in enumerate(profile_education):
            score = _score_profile_education_match(entry, profile_entry)
            if score > best_score:
                best_score = score
                best_idx = idx

        if best_idx >= 0 and best_score >= 0.45:
            used_profile_indices.add(best_idx)
            matched = profile_education[best_idx]
            for field in ("school", "degree", "field_of_study", "start_date", "end_date", "location"):
                if not entry.get(field) and matched.get(field):
                    entry[field] = matched[field]
            merged_details = _dedup_preserve((entry.get("details") or []) + (matched.get("details") or []))
            entry["details"] = merged_details[:4]

        if any(
            entry.get(field)
            for field in ("school", "degree", "field_of_study", "start_date", "end_date", "location")
        ) or entry["details"]:
            reconciled.append(entry)

    for idx, profile_entry in enumerate(profile_education):
        if idx in used_profile_indices:
            continue
        addition = {
            "school": profile_entry.get("school") or "",
            "degree": profile_entry.get("degree") or "",
            "field_of_study": profile_entry.get("field_of_study") or "",
            "start_date": profile_entry.get("start_date") or "",
            "end_date": profile_entry.get("end_date") or "",
            "location": profile_entry.get("location") or "",
            "details": profile_entry.get("details") or [],
        }
        if any(
            addition.get(field)
            for field in ("school", "degree", "field_of_study", "start_date", "end_date", "location")
        ) or addition["details"]:
            reconciled.append(addition)
            appended_count += 1

    deduped: List[Dict[str, Any]] = []
    seen_keys: set = set()
    for entry in reconciled:
        key = _education_identity(entry)
        if key and key in seen_keys:
            continue
        if key:
            seen_keys.add(key)
        deduped.append(entry)

    cv_json["education"] = deduped
    if appended_count:
        logger.warning("Education reconciliation appended %s missing profile entries.", appended_count)


def _extract_profile_languages(profile_json: Dict[str, Any]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    if not isinstance(profile_json, dict):
        return rows
    for item in profile_json.get("languages") or []:
        if not isinstance(item, dict):
            continue
        language = clean_text_field(item.get("language") or item.get("name") or "")
        level = clean_text_field(item.get("level") or item.get("proficiency") or "")
        certification = clean_text_field(
            item.get("certification")
            or item.get("certificate")
            or item.get("organization")
            or item.get("issuer")
            or ""
        )
        if not language:
            continue
        rows.append(
            {
                "language": language,
                "level": level,
                "certification": certification,
                "_language_norm": _normalize_for_match(language),
            }
        )
    return rows


def _reconcile_languages_section(cv_json: Dict[str, Any], profile_json: Dict[str, Any]) -> None:
    if not isinstance(cv_json, dict):
        return
    current_entries = cv_json.get("languages")
    if not isinstance(current_entries, list):
        current_entries = []

    profile_languages = _extract_profile_languages(profile_json)
    profile_map: Dict[str, Dict[str, str]] = {}
    profile_order: List[str] = []
    for entry in profile_languages:
        key = entry.get("_language_norm") or ""
        if not key:
            continue
        if key not in profile_map:
            profile_map[key] = {
                "language": entry.get("language") or "",
                "level": entry.get("level") or "",
                "certification": entry.get("certification") or "",
            }
            profile_order.append(key)
            continue
        existing = profile_map[key]
        if not existing.get("level") and entry.get("level"):
            existing["level"] = entry["level"]
        if not existing.get("certification") and entry.get("certification"):
            existing["certification"] = entry["certification"]
        if len(entry.get("language") or "") > len(existing.get("language") or ""):
            existing["language"] = entry.get("language") or existing.get("language") or ""

    reconciled: List[Dict[str, str]] = []
    seen: set = set()
    appended_count = 0

    for raw_entry in current_entries:
        if not isinstance(raw_entry, dict):
            continue
        language = clean_text_field(raw_entry.get("language") or raw_entry.get("name") or "")
        if not language:
            continue
        key = _normalize_for_match(language)
        if not key or key in seen:
            continue

        level = clean_text_field(raw_entry.get("level") or raw_entry.get("proficiency") or "")
        certification = clean_text_field(
            raw_entry.get("certification")
            or raw_entry.get("certificate")
            or raw_entry.get("organization")
            or raw_entry.get("issuer")
            or ""
        )

        profile_entry = profile_map.get(key)
        if profile_entry:
            language = profile_entry.get("language") or language
            level = level or profile_entry.get("level") or ""
            certification = certification or profile_entry.get("certification") or ""

        reconciled.append(
            {
                "language": language,
                "level": level,
                "certification": certification,
            }
        )
        seen.add(key)

    for key in profile_order:
        if key in seen:
            continue
        entry = profile_map[key]
        reconciled.append(
            {
                "language": entry.get("language") or "",
                "level": entry.get("level") or "",
                "certification": entry.get("certification") or "",
            }
        )
        seen.add(key)
        appended_count += 1

    cv_json["languages"] = reconciled[:4]
    if appended_count:
        logger.warning("Language reconciliation appended %s missing profile entries.", appended_count)


def reconcile_cv_sections_with_profile(cv_json: Dict[str, Any], profile_json: Dict[str, Any]) -> None:
    if not isinstance(cv_json, dict) or not isinstance(profile_json, dict):
        return
    _reconcile_experience_section(cv_json, profile_json)
    _reconcile_education_section(cv_json, profile_json)
    _reconcile_languages_section(cv_json, profile_json)


def coerce_generated_cv_payload(
    *,
    payload: Dict[str, Any],
    profile_json: Dict[str, Any],
    fallback_generator: Callable[[Dict[str, Any], str], Dict[str, Any]],
    critic_json: Optional[Dict[str, Any]] = None,
    job_title: str = "",
    company: str = "",
    profile_name: str = "",
    profile_email: str = "",
    profile_phone: str = "",
    profile_linkedin: str = "",
    language_code: str = "fr",
    keyword_alignment_fn: Optional[Callable[[Dict[str, Any], Optional[Dict[str, Any]]], None]] = None,
    offer_adaptation_fn: Optional[Callable[[Dict[str, Any], Optional[Dict[str, Any]]], None]] = None,
) -> Dict[str, Any]:
    """Merge partial/invalid generated payload onto a valid skeleton.

    This ensures the output always has valid structure even when
    the LLM produces incomplete or malformed JSON.

    Args:
        payload: Generated CV JSON (may be partial)
        profile_json: Source profile data
        fallback_generator: Function to generate fallback CV JSON
        critic_json: Optional critic analysis
        job_title: Target job title
        company: Target company
        profile_name: Profile name for fallback
        profile_email: Profile email for fallback
        profile_phone: Profile phone for fallback
        profile_linkedin: Profile LinkedIn for fallback
        language_code: Language code for labels
        keyword_alignment_fn: Optional function to apply keyword alignment
        offer_adaptation_fn: Optional function to enforce offer adaptation

    Returns:
        Merged and validated CV JSON
    """
    # Generate deterministic base
    base = fallback_generator(profile_json, "")
    if not isinstance(base, dict):
        base = {}
    if not isinstance(payload, dict):
        payload = {}

    merged: Dict[str, Any] = dict(base)

    # Merge top-level text fields
    for key in ("schema_version", "summary", "target_job_title", "target_company"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            merged[key] = value.strip()

    # Merge contact
    incoming_contact = payload.get("contact")
    contact = dict(merged.get("contact") or {}) if isinstance(merged.get("contact"), dict) else {}
    if isinstance(incoming_contact, dict):
        for field in ("full_name", "email", "phone", "linkedin_url", "location"):
            value = incoming_contact.get(field)
            if isinstance(value, str) and value.strip():
                contact[field] = value.strip()
    merged["contact"] = contact

    # Merge list sections
    list_sections = (
        "skills",
        "experience",
        "education",
        "projects",
        "languages",
        "certifications",
        "ats_keywords",
    )
    for key in list_sections:
        value = payload.get(key)
        if isinstance(value, list) and value:
            merged[key] = value

    # Merge render hints
    render_hints = payload.get("render_hints")
    if isinstance(render_hints, dict) and render_hints:
        merged["render_hints"] = render_hints

    # Apply fallbacks
    apply_contact_fallback(
        merged,
        profile_json,
        profile_name=profile_name,
        profile_email=profile_email,
        profile_phone=profile_phone,
        profile_linkedin=profile_linkedin,
    )
    apply_target_fallback(merged, job_title=job_title, company=company)

    # Sanitize
    sanitize_cv_json_output(merged, language_code=language_code)
    reconcile_cv_sections_with_profile(merged, profile_json)

    # Apply keyword alignment if provided
    if keyword_alignment_fn:
        keyword_alignment_fn(merged, critic_json)

    # Apply offer adaptation if provided
    if offer_adaptation_fn:
        offer_adaptation_fn(merged, critic_json)

    # Re-sanitize after optional post-merge transformations.
    sanitize_cv_json_output(merged, language_code=language_code)
    reconcile_cv_sections_with_profile(merged, profile_json)

    return merged


def extract_experience_highlights(description: str) -> List[str]:
    """Extract bullet-point highlights from experience description.

    Args:
        description: Experience description text

    Returns:
        List of highlight strings
    """
    if not description:
        return []

    highlights: List[str] = []
    for part in re.split(r"[\r\n]+", description):
        cleaned = part.strip(" -*\t")
        if cleaned:
            highlights.append(cleaned)

    return _dedup_preserve(highlights)[:3]


def rank_experiences_by_relevance(
    experiences: List[Dict[str, Any]],
    offer_keywords: List[str],
    job_title: str = "",
) -> List[Dict[str, Any]]:
    """Rank experiences by relevance to job offer.

    Args:
        experiences: List of experience dicts
        offer_keywords: Keywords from job offer
        job_title: Target job title

    Returns:
        Experiences sorted by relevance score
    """
    from .keyword_alignment import normalize_keyword_for_match

    if not experiences or not offer_keywords:
        return experiences

    ranked: List[Tuple[float, int, Dict[str, Any]]] = []
    role_norm = normalize_keyword_for_match(job_title)
    normalized_keywords = [
        normalize_keyword_for_match(item) for item in offer_keywords[:20]
    ]
    normalized_keywords = [item for item in normalized_keywords if item]

    for idx, item in enumerate(experiences):
        if not isinstance(item, dict):
            continue
        blob = " ".join(
            str(item.get(field) or "")
            for field in ("title", "company", "description", "summary")
        )
        norm_blob = normalize_keyword_for_match(blob)
        score = 0.0
        for kw in normalized_keywords:
            if kw in norm_blob:
                score += 2.0 if " " in kw else 1.0
        if role_norm and role_norm in norm_blob:
            score += 2.5
        ranked.append((score, -idx, item))

    ranked.sort(key=lambda payload: (-payload[0], payload[1]))
    return [payload[2] for payload in ranked]


# =============================================================================
# Sprint 8.3: CV Offer Adaptation Enforcement (extracted from CVGenerationWorker)
# =============================================================================


def enforce_cv_offer_adaptation(
    cv_json: Dict[str, Any],
    *,
    job_title: str = "",
    company: str = "",
    aligned_terms: List[str],
    missing_summary_terms: List[str],
    missing_experience_terms: List[str],
    language_code: str = "fr",
) -> Dict[str, Any]:
    """Enforce CV adaptation to job offer requirements.

    This function ensures the CV summary and experience sections
    contain references to the target job title, company, and aligned keywords.

    Args:
        cv_json: CV JSON dictionary (modified in place)
        job_title: Target job title
        company: Target company name
        aligned_terms: List of offer-aligned keyword terms
        missing_summary_terms: Terms missing from summary
        missing_experience_terms: Terms missing from experience
        language_code: Language code for generated text

    Returns:
        The modified cv_json
    """
    if not isinstance(cv_json, dict):
        return cv_json

    is_en = language_code == "en"

    # Enforce job title and company in summary
    summary = str(cv_json.get("summary") or "").strip()
    summary_norm = normalize_keyword_for_match(summary)
    summary_additions: List[str] = []

    if job_title and normalize_keyword_for_match(job_title) not in summary_norm:
        summary_additions.append(
            f"Target role: {job_title}." if is_en else f"Poste cible: {job_title}."
        )

    if company and normalize_keyword_for_match(company) not in summary_norm:
        summary_additions.append(
            f"Target company: {company}." if is_en else f"Entreprise cible: {company}."
        )

    # Add missing aligned terms to summary
    missing_summary_terms = missing_summary_terms[:3]
    if missing_summary_terms:
        summary_additions.append(
            f"Offer-aligned strengths: {', '.join(missing_summary_terms)}."
            if is_en
            else f"Forces alignees offre: {', '.join(missing_summary_terms)}."
        )

    if summary_additions:
        summary = (
            f"{summary} {' '.join(summary_additions)}".strip()
            if summary
            else " ".join(summary_additions)
        )
        cv_json["summary"] = clean_narrative_text(summary)

    # Add missing keywords to first experience entry
    experience_entries = [
        item for item in (cv_json.get("experience") or []) if isinstance(item, dict)
    ]
    if experience_entries and missing_experience_terms:
        sentence = (
            f"Applied keywords relevant to the offer: {', '.join(missing_experience_terms[:2])}."
            if is_en
            else f"Mots-cles appliques et pertinents pour l'offre: {', '.join(missing_experience_terms[:2])}."
        )
        target_entry = experience_entries[0]
        highlights = target_entry.get("highlights")
        if not isinstance(highlights, list):
            highlights = []
        highlights.append(sentence)
        target_entry["highlights"] = _dedup_preserve(
            [item for item in highlights if isinstance(item, str) and item.strip()]
        )[:4]

    return cv_json
