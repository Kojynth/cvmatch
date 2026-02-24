"""
CV Postprocessing Module (PR-07)

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
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

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

    cv_json["summary"] = clean_text_field(cv_json.get("summary") or "")
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
            "summary": clean_text_field(entry.get("summary") or ""),
        }
        highlights = []
        for item in entry.get("highlights", []) or []:
            if isinstance(item, str):
                text = clean_text_field(item)
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
            "description": clean_text_field(entry.get("description") or ""),
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
        if language:
            cleaned_languages.append({"language": language, "level": level})
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

    # Apply keyword alignment if provided
    if keyword_alignment_fn:
        keyword_alignment_fn(merged, critic_json)

    # Apply offer adaptation if provided
    if offer_adaptation_fn:
        offer_adaptation_fn(merged, critic_json)

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
        cv_json["summary"] = summary

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
