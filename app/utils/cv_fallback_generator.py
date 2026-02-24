"""
CV Fallback Generator Module (Sprint 3)

Deterministic CV JSON generator used when LLM fails or produces invalid output.
Extracted from CVGenerationWorker._fallback_cv_json() in llm_worker.py.

Key features:
- Profile-to-CV JSON mapping without LLM dependency
- Keyword alignment to job offer
- Experience relevance ranking
- Bilingual support (FR/EN)

This module has zero LLM dependencies and provides reliable fallback output.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

try:
    from ..logging.safe_logger import get_safe_logger
    from ..config import DEFAULT_PII_CONFIG
    logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

from .keyword_alignment import (
    build_keyword_alignment,
    normalize_keyword_for_match,
)


def _dedup_preserve(items: List[str]) -> List[str]:
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


def _coerce_list(value: Any) -> List[Any]:
    """Coerce value to list."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def collect_candidate_keywords(
    profile_data: Any,
    *,
    max_items: int = 40,
) -> List[str]:
    """Collect searchable keywords from a user profile.

    Args:
        profile_data: UserProfile or ProfileWorkerData object
        max_items: Maximum number of terms to return

    Returns:
        Deduplicated list of candidate keywords
    """
    terms: List[str] = []

    def add_term(value: Any) -> None:
        if value is None:
            return
        if isinstance(value, str):
            trimmed = value.strip()
            if 1 < len(trimmed) <= 80:
                terms.append(trimmed)
            return
        if isinstance(value, list):
            for item in value:
                add_term(item)
        elif isinstance(value, dict):
            for key in ("name", "title", "skill", "technology", "tool"):
                add_term(value.get(key))

    # Extract from skills
    skills = getattr(profile_data, "extracted_skills", None) or []
    for entry in skills:
        if isinstance(entry, dict):
            items = (
                entry.get("items")
                or entry.get("skills_list")
                or entry.get("skills")
                or []
            )
            add_term(items)
        else:
            add_term(entry)

    # Extract from projects
    projects = getattr(profile_data, "extracted_projects", None) or []
    for entry in projects:
        if isinstance(entry, dict):
            add_term(entry.get("name"))
            add_term(entry.get("technologies"))
        else:
            add_term(entry)

    # Extract from certifications
    certifications = getattr(profile_data, "extracted_certifications", None) or []
    for entry in certifications:
        if isinstance(entry, dict):
            add_term(entry.get("name"))
        else:
            add_term(entry)

    # Extract from experiences
    experiences = getattr(profile_data, "extracted_experiences", None) or []
    for entry in experiences:
        if isinstance(entry, dict):
            add_term(entry.get("title"))
        else:
            add_term(entry)

    return _dedup_preserve(terms)[:max_items]


def rank_experiences_by_offer_relevance(
    experiences: List[Dict[str, Any]],
    offer_keywords: List[str],
    job_title: str = "",
) -> List[Dict[str, Any]]:
    """Rank experiences by relevance to job offer keywords.

    Args:
        experiences: List of experience dictionaries
        offer_keywords: Keywords from job offer analysis
        job_title: Target job title

    Returns:
        Experiences sorted by relevance score (most relevant first)
    """
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


def extract_experience_highlights(description: str) -> List[str]:
    """Extract bullet-point highlights from experience description.

    Args:
        description: Experience description text

    Returns:
        List of highlight strings (max 3)
    """
    if not description:
        return []

    highlights: List[str] = []
    for part in re.split(r"[\r\n]+", description):
        cleaned = part.strip(" -*\t")
        if cleaned:
            highlights.append(cleaned)

    return _dedup_preserve(highlights)[:3]


def generate_fallback_cv_json(
    *,
    profile_json: Dict[str, Any],
    profile_data: Any,
    offer_data: Optional[Dict[str, Any]] = None,
    language_code: str = "fr",
    offer_keywords_collector: Optional[Callable[[], List[str]]] = None,
    reason: str = "",
) -> Dict[str, Any]:
    """Generate a deterministic fallback CV JSON from profile data.

    This function creates a valid CV JSON structure without LLM dependency.
    It aligns profile content with job offer keywords when available.

    Args:
        profile_json: Extracted profile data as JSON
        profile_data: UserProfile or ProfileWorkerData object
        offer_data: Job offer dictionary (optional)
        language_code: Target language ("fr" or "en")
        offer_keywords_collector: Optional function to collect offer keywords
        reason: Reason for fallback (for logging)

    Returns:
        Valid CV JSON dictionary matching CVJSON schema
    """
    profile_json = profile_json if isinstance(profile_json, dict) else {}
    personal = profile_json.get("personal_info")
    if not isinstance(personal, dict):
        personal = {}

    is_en = language_code == "en"
    skills_label = "Skills" if is_en else "Competences"

    # Extract offer metadata
    job_title = ""
    company = ""
    if isinstance(offer_data, dict):
        job_title = str(offer_data.get("job_title") or "").strip()
        company = str(offer_data.get("company") or "").strip()

    # Collect offer keywords
    offer_keywords: List[str] = []
    if offer_keywords_collector:
        try:
            offer_keywords = offer_keywords_collector()[:20]
        except Exception:
            offer_keywords = []

    # Build keyword alignment
    candidate_terms = collect_candidate_keywords(profile_data)
    keyword_mapping = build_keyword_alignment(candidate_terms, offer_keywords)
    matched_terms = _dedup_preserve(list(keyword_mapping.values()))

    # Fallback: direct matching if alignment failed
    if not matched_terms and offer_keywords:
        offer_norm = {normalize_keyword_for_match(item) for item in offer_keywords}
        for term in candidate_terms:
            if normalize_keyword_for_match(term) in offer_norm:
                matched_terms.append(term)
        matched_terms = _dedup_preserve(matched_terms)

    # Extract profile summary
    profile_summary = ""
    for key in ("summary", "headline", "about"):
        value = personal.get(key)
        if isinstance(value, str) and value.strip():
            profile_summary = value.strip()
            break

    # Build summary text
    role_label = job_title or ("the target role" if is_en else "le poste vise")
    company_label = company or ("the target company" if is_en else "l'entreprise cible")
    terms_preview = ", ".join(matched_terms[:4]) if matched_terms else ""

    if is_en:
        if terms_preview:
            summary = (
                f"Application for {role_label} at {company_label}, with hands-on "
                f"experience in {terms_preview}."
            )
        else:
            summary = (
                f"Application for {role_label} at {company_label}, with practical "
                "experience aligned to the job requirements."
            )
    else:
        if terms_preview:
            summary = (
                f"Candidature au poste {role_label} chez {company_label}, avec une "
                f"experience concrete en {terms_preview}."
            )
        else:
            summary = (
                f"Candidature au poste {role_label} chez {company_label}, avec un "
                "parcours aligne sur les besoins du poste."
            )

    if profile_summary:
        summary = f"{summary} {_trim_text(profile_summary, 180)}".strip()

    # Build skills section
    skill_items: List[str] = []
    for item in profile_json.get("skills", []) or []:
        if isinstance(item, dict):
            name = item.get("name") or item.get("skill")
        else:
            name = item
        text = str(name or "").strip()
        if text:
            skill_items.append(text)

    if keyword_mapping:
        skill_items = _dedup_preserve(list(keyword_mapping.values()) + skill_items)
    elif matched_terms:
        skill_items = _dedup_preserve(matched_terms + skill_items)
    else:
        skill_items = _dedup_preserve(skill_items)
    skill_items = skill_items[:12]

    # Build experience section
    experience_items: List[Dict[str, Any]] = []
    source_experiences = [
        item
        for item in (profile_json.get("experiences", []) or [])
        if isinstance(item, dict)
    ]

    # Rank experiences by relevance if we have offer keywords
    if source_experiences and offer_keywords:
        source_experiences = rank_experiences_by_offer_relevance(
            source_experiences, offer_keywords, job_title
        )

    for item in source_experiences:
        if not isinstance(item, dict):
            continue
        desc = str(item.get("description") or "").strip()
        highlights = extract_experience_highlights(desc)
        summary_text = desc[:280] if desc else ""
        mapped = {
            "title": str(item.get("title") or ""),
            "company": str(item.get("company") or ""),
            "start_date": str(item.get("start_date") or ""),
            "end_date": str(item.get("end_date") or ""),
            "location": str(item.get("location") or ""),
            "summary": summary_text,
            "highlights": highlights,
        }
        if any(
            mapped.get(k)
            for k in ("title", "company", "start_date", "end_date", "location", "summary")
        ) or mapped.get("highlights"):
            experience_items.append(mapped)
    experience_items = experience_items[:4]

    # Build education section
    education_items: List[Dict[str, Any]] = []
    for item in profile_json.get("education", []) or []:
        if not isinstance(item, dict):
            continue
        details: List[str] = []
        for key in ("details", "description"):
            raw = item.get(key)
            if isinstance(raw, list):
                details.extend(str(x).strip() for x in raw if str(x).strip())
            elif isinstance(raw, str) and raw.strip():
                details.append(raw.strip())
        grade = str(item.get("grade") or "").strip()
        if grade:
            details.append(grade)
        details = _dedup_preserve(details)[:4]
        mapped = {
            "school": str(item.get("school") or ""),
            "degree": str(item.get("degree") or ""),
            "field_of_study": str(item.get("field_of_study") or ""),
            "start_date": str(item.get("start_date") or ""),
            "end_date": str(item.get("end_date") or ""),
            "location": str(item.get("location") or ""),
            "details": details,
        }
        if any(
            mapped.get(k)
            for k in (
                "school",
                "degree",
                "field_of_study",
                "start_date",
                "end_date",
                "location",
            )
        ) or mapped.get("details"):
            education_items.append(mapped)
    education_items = education_items[:3]

    # Build languages section
    language_items: List[Dict[str, Any]] = []
    for item in profile_json.get("languages", []) or []:
        if not isinstance(item, dict):
            continue
        lang = str(item.get("language") or "").strip()
        level = str(item.get("level") or item.get("proficiency") or "").strip()
        if lang:
            language_items.append({"language": lang, "level": level})
    language_items = language_items[:4]

    # Build projects section
    project_items: List[Dict[str, Any]] = []
    for item in profile_json.get("projects", []) or []:
        if not isinstance(item, dict):
            continue
        mapped = {
            "name": str(item.get("name") or ""),
            "description": str(item.get("description") or ""),
            "technologies": str(item.get("technologies") or ""),
            "url": str(item.get("url") or ""),
        }
        if any(mapped.values()):
            project_items.append(mapped)
    project_items = project_items[:3]

    # Build certifications section
    cert_items: List[Dict[str, Any]] = []
    for item in profile_json.get("certifications", []) or []:
        if not isinstance(item, dict):
            continue
        mapped = {
            "name": str(item.get("name") or ""),
            "organization": str(item.get("organization") or ""),
            "date": str(item.get("date") or ""),
            "url": str(item.get("url") or ""),
        }
        if mapped.get("name"):
            cert_items.append(mapped)
    cert_items = cert_items[:4]

    # Build ATS keywords
    ats_keywords: List[str] = _dedup_preserve(offer_keywords)[:15]

    # Assemble final payload
    payload = {
        "schema_version": "cv.v1",
        "target_job_title": job_title,
        "target_company": company,
        "contact": {
            "full_name": str(
                personal.get("full_name") or getattr(profile_data, "name", "") or ""
            ),
            "email": str(
                personal.get("email") or getattr(profile_data, "email", "") or ""
            ),
            "phone": str(
                personal.get("phone") or getattr(profile_data, "phone", "") or ""
            ),
            "linkedin_url": str(
                personal.get("linkedin_url")
                or getattr(profile_data, "linkedin_url", "")
                or ""
            ),
            "location": str(personal.get("location") or ""),
        },
        "summary": summary,
        "skills": (
            [{"category": skills_label, "items": skill_items}] if skill_items else []
        ),
        "experience": experience_items,
        "education": education_items,
        "projects": project_items,
        "languages": language_items,
        "certifications": cert_items,
        "ats_keywords": ats_keywords,
        "render_hints": {
            "notes": "deterministic_fallback",
            "section_order": [
                "contact",
                "summary",
                "experience",
                "skills",
                "education",
            ],
            "emphasis": ["reliability"],
            "tone": "professional",
        },
    }

    # Validate against schema if available
    try:
        from ..schemas.cv_schema import CVJSON
        parsed = CVJSON.model_validate(payload).model_dump()
    except Exception:
        parsed = payload

    if reason:
        logger.warning("Fallback CVJSON used due to: %s", reason)

    return parsed


def generate_fallback_cv_json_simple(
    *,
    profile_json: Dict[str, Any],
    profile_name: str = "",
    profile_email: str = "",
    profile_phone: str = "",
    profile_linkedin: str = "",
    job_title: str = "",
    company: str = "",
    language_code: str = "fr",
    offer_keywords: Optional[List[str]] = None,
    reason: str = "",
) -> Dict[str, Any]:
    """Simplified fallback generator without profile_data object.

    Use this when you only have profile_json and basic contact info.

    Args:
        profile_json: Extracted profile data as JSON
        profile_name: Profile name
        profile_email: Profile email
        profile_phone: Profile phone
        profile_linkedin: Profile LinkedIn URL
        job_title: Target job title
        company: Target company
        language_code: Target language
        offer_keywords: Optional list of offer keywords
        reason: Reason for fallback

    Returns:
        Valid CV JSON dictionary
    """
    # Create a minimal profile-like object
    class MinimalProfile:
        def __init__(self):
            self.name = profile_name
            self.email = profile_email
            self.phone = profile_phone
            self.linkedin_url = profile_linkedin
            # Extract skills from profile_json for keyword collection
            self.extracted_skills = profile_json.get("skills", [])
            self.extracted_projects = profile_json.get("projects", [])
            self.extracted_certifications = profile_json.get("certifications", [])
            self.extracted_experiences = profile_json.get("experiences", [])

    profile_data = MinimalProfile()

    offer_data = {"job_title": job_title, "company": company} if job_title or company else None

    def keywords_collector() -> List[str]:
        return offer_keywords or []

    return generate_fallback_cv_json(
        profile_json=profile_json,
        profile_data=profile_data,
        offer_data=offer_data,
        language_code=language_code,
        offer_keywords_collector=keywords_collector if offer_keywords else None,
        reason=reason,
    )
