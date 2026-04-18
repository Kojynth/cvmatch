"""
CV Fallback Generator Module 

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
from .language_policy import (
    detect_language_from_text_default,
    is_mixed_or_mismatched_language,
    normalize_language_code,
)


_FIRST_PERSON_HINTS = {
    "fr": (
        r"\bje\b",
        r"\bj['’]",
        r"\bmon\b",
        r"\bma\b",
        r"\bmes\b",
        r"\bnous\b",
        r"\bnotre\b",
        r"\bnos\b",
        r"\bmes missions\b",
        r"\bj'interviens\b",
        r"\bj'assure\b",
    ),
    "en": (
        r"\bi\b",
        r"\bmy\b",
        r"\bme\b",
        r"\bwe\b",
        r"\bour\b",
        r"\bmy responsibilities\b",
        r"\bi worked\b",
        r"\bi supported\b",
    ),
}

_SUMMARY_ACTION_REJECTORS = {
    "fr": {
        "concevoir",
        "executer",
        "rediger",
        "suivre",
        "proposer",
        "automatiser",
        "consolider",
        "fiabiliser",
        "assurer",
        "realiser",
        "gerer",
        "coordonner",
    },
    "en": {
        "design",
        "build",
        "write",
        "track",
        "execute",
        "support",
        "lead",
        "manage",
        "deliver",
        "develop",
        "coordinate",
        "improve",
    },
}


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


def _contains_first_person_reference(text: Any, *, language_code: str) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False
    target = normalize_language_code(language_code)
    patterns = _FIRST_PERSON_HINTS.get(target, ()) + _FIRST_PERSON_HINTS.get("en", ())
    lowered = raw.lower()
    return any(re.search(pattern, lowered) for pattern in patterns)


def _normalize_contact_links(raw_links: Any) -> List[Dict[str, str]]:
    links: List[Dict[str, str]] = []
    seen = set()
    for entry in _coerce_list(raw_links):
        label = ""
        url = ""
        if isinstance(entry, dict):
            label = str(
                entry.get("label") or entry.get("platform") or entry.get("name") or ""
            ).strip()
            url = str(entry.get("url") or entry.get("link") or "").strip()
        else:
            url = str(entry or "").strip()
        if not url:
            continue
        if not re.match(r"^https?://", url, flags=re.IGNORECASE) and re.match(
            r"^[a-z0-9][a-z0-9.-]+\.[a-z]{2,}(?:[/?#].*)?$",
            url,
            flags=re.IGNORECASE,
        ):
            url = f"https://{url}"
        if not label:
            label = f"Lien {len(links) + 1}"
        key = (label.lower(), url.lower())
        if key in seen:
            continue
        seen.add(key)
        links.append({"label": label, "url": url})
    return links


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
    normalized = normalize_keyword_for_match(text)
    if not normalized or len(normalized) < 50:
        return False

    company_norm = normalize_keyword_for_match(company)
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


def _build_action_summary(
    *,
    title: str,
    company: str,
    description: str,
    highlights: List[str],
    is_en: bool,
    language_code: str,
) -> str:
    for item in highlights:
        text = str(item or "").strip()
        if not text:
            continue
        if _is_cross_language_narrative(text, language_code=language_code):
            continue
        if _looks_like_company_description(text, company):
            continue
        return _trim_text(text, 280)

    if (
        description
        and not _is_cross_language_narrative(description, language_code=language_code)
        and not _looks_like_company_description(description, company)
    ):
        return _trim_text(description, 280)

    title_text = str(title or "").strip()
    if title_text and _is_cross_language_label(title_text, language_code=language_code):
        title_text = ""
    if not title_text:
        if is_en:
            return "Delivered key contributions in this role."
        return "Contributions principales realisees sur ce poste."
    if is_en:
        return _trim_text(f"Delivered key contributions as {title_text}.", 140)
    return _trim_text(f"Contributions principales realisees en tant que {title_text}.", 160)


def _is_cross_language_narrative(text: Any, *, language_code: str) -> bool:
    value = str(text or "").strip()
    if not value:
        return False
    if len(value) < 40 and len(value.split()) < 8:
        return False
    target = normalize_language_code(language_code)
    return is_mixed_or_mismatched_language(value, target)


def _is_cross_language_label(text: Any, *, language_code: str) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False

    target = normalize_language_code(language_code)
    ascii_folded = (
        raw.encode("ascii", "ignore").decode("ascii", errors="ignore").lower()
    )
    tokens = [token for token in re.findall(r"[a-z]+", ascii_folded) if token]
    if not tokens:
        return False

    technical_singletons = {
        "sql",
        "python",
        "java",
        "c",
        "csharp",
        "react",
        "node",
        "api",
        "qa",
        "ui",
        "ux",
        "git",
        "aws",
        "gcp",
        "azure",
        "etl",
        "elt",
        "powerbi",
        "tableau",
        "looker",
    }
    if len(tokens) == 1 and tokens[0] in technical_singletons:
        return False

    fr_markers = {
        "alternant",
        "ingenieur",
        "qualite",
        "stagiaire",
        "rediger",
        "suivre",
        "anomalies",
        "plans",
        "tests",
        "bilans",
        "recettes",
        "concevoir",
        "executer",
        "missions",
        "developpeur",
        "management",
        "systemes",
        "donnees",
        "ecole",
        "superieure",
        "certification",
    }
    en_markers = {
        "engineer",
        "apprentice",
        "developer",
        "manager",
        "specialist",
        "analyst",
        "lead",
        "quality",
        "business",
        "designer",
        "operations",
        "sales",
        "intern",
        "testing",
        "support",
    }

    if target == "en" and set(tokens) & fr_markers:
        return True
    if target == "fr" and set(tokens) & en_markers:
        return True

    if any(ord(ch) > 127 for ch in raw) and len(tokens) >= 2:
        detected = detect_language_from_text_default(raw)
        if detected != target:
            return True

    if len(tokens) >= 3:
        detected = detect_language_from_text_default(raw)
        if detected != target:
            return True

    return False


def _build_generic_profile_summary(
    *,
    is_en: bool,
    language_code: str,
    profile_summary: str,
    experience_titles: List[str],
    skill_items: List[str],
) -> str:
    def _is_summary_focus_term(text: str) -> bool:
        candidate = str(text or "").strip().strip(".,;:")
        if not candidate:
            return False
        if _contains_first_person_reference(candidate, language_code=language_code):
            return False
        token_count = len(re.findall(r"[A-Za-zÀ-ÿ0-9+#]+", candidate))
        if token_count == 0 or token_count > 4:
            return False
        lowered_tokens = [
            token.lower()
            for token in re.findall(r"[A-Za-zÀ-ÿ]+", candidate)
            if token
        ]
        if lowered_tokens and lowered_tokens[0] in _SUMMARY_ACTION_REJECTORS.get(
            normalize_language_code(language_code),
            set(),
        ):
            return False
        return True

    def _join_focus_terms(terms: List[str]) -> str:
        cleaned_terms = [str(item or "").strip() for item in terms if str(item or "").strip()]
        if len(cleaned_terms) == 1 and re.fullmatch(r"[A-Z0-9+#]{2,}", cleaned_terms[0]):
            return ""
        if not cleaned_terms:
            return ""
        if len(cleaned_terms) == 1:
            return cleaned_terms[0]
        conjunction = "and" if is_en else "et"
        if len(cleaned_terms) == 2:
            return f"{cleaned_terms[0]} {conjunction} {cleaned_terms[1]}"
        return ", ".join(cleaned_terms[:-1]) + f" {conjunction} {cleaned_terms[-1]}"

    titles = _dedup_preserve(
        [
            str(title or "").strip()
            for title in experience_titles
            if str(title or "").strip()
            and not _is_cross_language_label(
                title,
                language_code=language_code,
            )
        ]
    )
    focus_terms = _dedup_preserve(
        [
            str(item or "").strip()
            for item in skill_items
            if str(item or "").strip()
            and _is_summary_focus_term(str(item or "").strip())
            and not _is_cross_language_label(
                item,
                language_code=language_code,
            )
        ]
    )[:4]

    lead_title = titles[0] if titles else ""
    focus_phrase = _join_focus_terms(focus_terms[:3])

    if is_en:
        if lead_title and focus_phrase:
            summary = f"{lead_title} with hands-on experience in {focus_phrase}."
        elif lead_title:
            summary = (
                f"{lead_title} with experience across technical and operational environments."
            )
        elif focus_phrase:
            summary = f"Professional background with experience in {focus_phrase}."
        else:
            summary = "Professional background across technical and operational environments."
    else:
        if lead_title and focus_phrase:
            summary = f"{lead_title} avec une expérience en {focus_phrase}."
        elif lead_title:
            summary = (
                f"{lead_title} avec une expérience dans des environnements techniques et opérationnels."
            )
        elif focus_phrase:
            summary = f"Parcours avec une expérience en {focus_phrase}."
        else:
            summary = "Parcours au sein d'environnements techniques et opérationnels."

    return _trim_text(summary, 260)


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


def extract_experience_highlights(description: str, company: str = "") -> List[str]:
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
        raw = part.strip(" -*\t")
        if not raw:
            continue
        for sentence in re.split(r"(?<=[.!?])\s+", raw):
            cleaned = sentence.strip(" -*\t")
            if not cleaned:
                continue
            if _looks_like_company_description(cleaned, company):
                continue
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
    preserve_foreign_text: bool = False,
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

    # Build skills section
    skill_items: List[str] = []
    for item in profile_json.get("skills", []) or []:
        if isinstance(item, dict):
            name = item.get("name") or item.get("skill")
        else:
            name = item
        text = str(name or "").strip()
        if text and (
            preserve_foreign_text
            or not _is_cross_language_label(text, language_code=language_code)
        ):
            skill_items.append(text)

    if keyword_mapping:
        skill_items = _dedup_preserve(list(keyword_mapping.values()) + skill_items)
    elif matched_terms:
        skill_items = _dedup_preserve(matched_terms + skill_items)
    else:
        skill_items = _dedup_preserve(skill_items)
    skill_items = skill_items[:12]

    experience_titles = [
        str(item.get("title") or "").strip()
        for item in (profile_json.get("experiences", []) or [])
        if isinstance(item, dict)
    ]

    # Build summary text
    terms_preview = ", ".join(matched_terms[:4]) if matched_terms else ""
    if job_title or company:
        role_label = job_title or ("the role" if is_en else "le poste")
        company_label = company or ("the company" if is_en else "l'entreprise")
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
        if profile_summary and not _is_cross_language_narrative(
            profile_summary,
            language_code=language_code,
        ):
            summary = f"{summary} {_trim_text(profile_summary, 180)}".strip()
    else:
        summary = _build_generic_profile_summary(
            is_en=is_en,
            language_code=language_code,
            profile_summary=profile_summary,
            experience_titles=experience_titles,
            skill_items=skill_items,
        )

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
        company_name = str(item.get("company") or "").strip()
        title_text = str(item.get("title") or "").strip()
        highlights = extract_experience_highlights(desc, company=company_name)
        clean_highlights = [
            _trim_text(text, 220)
            for text in highlights
            if str(text or "").strip()
            and (
                preserve_foreign_text
                or (
                    not _is_cross_language_narrative(
                        text,
                        language_code=language_code,
                    )
                    and not _is_cross_language_label(
                        text,
                        language_code=language_code,
                    )
                )
            )
        ][:4]
        summary_text = _build_action_summary(
            title=title_text,
            company=company_name,
            description=desc,
            highlights=clean_highlights,
            is_en=is_en,
            language_code=language_code,
        )
        mapped = {
            "title": title_text,
            "company": company_name,
            "start_date": str(item.get("start_date") or ""),
            "end_date": str(item.get("end_date") or ""),
            "location": str(item.get("location") or ""),
            "summary": summary_text,
            "highlights": clean_highlights,
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
                details.extend(
                    str(x).strip()
                    for x in raw
                    if str(x).strip()
                    and (
                        preserve_foreign_text
                        or not _is_cross_language_narrative(
                            x,
                            language_code=language_code,
                        )
                    )
                )
            elif isinstance(raw, str) and raw.strip():
                if preserve_foreign_text or not _is_cross_language_narrative(
                    raw,
                    language_code=language_code,
                ):
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
        certification = str(
            item.get("certification")
            or item.get("certificate")
            or item.get("organization")
            or item.get("issuer")
            or ""
        ).strip()
        if lang:
            language_items.append(
                {
                    "language": lang,
                    "level": level,
                    "certification": certification,
                }
            )
    language_items = language_items[:4]

    # Build projects section
    project_items: List[Dict[str, Any]] = []
    for item in profile_json.get("projects", []) or []:
        if not isinstance(item, dict):
            continue
        mapped = {
            "name": str(item.get("name") or ""),
            "description": (
                ""
                if (
                    not preserve_foreign_text
                    and (
                        _is_cross_language_narrative(
                            item.get("description") or "",
                            language_code=language_code,
                        )
                        or _is_cross_language_label(
                            item.get("description") or "",
                            language_code=language_code,
                        )
                    )
                )
                else str(item.get("description") or "")
            ),
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
        if mapped.get("name") and (
            preserve_foreign_text
            or not _is_cross_language_label(
                mapped.get("name"),
                language_code=language_code,
            )
        ):
            cert_items.append(mapped)
    cert_items = cert_items[:4]

    # Build ATS keywords
    ats_keywords: List[str] = _dedup_preserve(offer_keywords)[:15]

    # Assemble final payload
    contact_payload = {
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
    }
    contact_links = _normalize_contact_links(personal.get("links"))
    if contact_links:
        contact_payload["links"] = contact_links

    payload = {
        "schema_version": "cv.v1",
        "target_job_title": job_title,
        "target_company": company,
        "contact": contact_payload,
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
    preserve_foreign_text: bool = False,
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
        preserve_foreign_text=preserve_foreign_text,
    )
