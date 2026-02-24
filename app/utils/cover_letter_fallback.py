"""
Cover Letter Fallback Generator Module (Sprint 3)

Deterministic cover letter generator used when LLM fails or produces invalid output.
Extracted and unified from CVGenerationWorker and CoverLetterGenerationWorker.

Key features:
- Profile-to-cover-letter generation without LLM dependency
- Keyword alignment to job offer
- Experience relevance ranking
- Bilingual support (FR/EN)

This module has zero LLM dependencies and provides reliable fallback output.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

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
from .cv_fallback_generator import collect_candidate_keywords, _dedup_preserve


def _rank_experience_labels(
    experiences: List[Dict[str, Any]],
    offer_keywords: List[str],
    job_title: str = "",
    *,
    max_results: int = 2,
) -> List[str]:
    """Rank experiences and return formatted labels for the most relevant ones.

    Args:
        experiences: List of experience dictionaries
        offer_keywords: Keywords from job offer analysis
        job_title: Target job title
        max_results: Maximum number of labels to return

    Returns:
        List of formatted experience labels (e.g., "Data Analyst (Google)")
    """
    if not experiences:
        return []

    role_norm = normalize_keyword_for_match(job_title)
    normalized_keywords = [
        normalize_keyword_for_match(item) for item in offer_keywords[:12]
    ]
    normalized_keywords = [item for item in normalized_keywords if item]

    ranked: List[Tuple[float, int, str]] = []

    for idx, item in enumerate(experiences):
        if not isinstance(item, dict):
            continue

        title = str(item.get("title") or "").strip()
        company_exp = str(item.get("company") or "").strip()
        description = str(item.get("description") or "").strip()
        blob = " ".join([title, company_exp, description])
        norm_blob = normalize_keyword_for_match(blob)

        score = 0.0
        for kw in normalized_keywords:
            if kw in norm_blob:
                score += 2.0 if " " in kw else 1.0
        if role_norm and role_norm in norm_blob:
            score += 2.5

        # Build display label
        label = ""
        if title and company_exp:
            label = f"{title} ({company_exp})"
        elif title:
            label = title
        elif company_exp:
            label = company_exp

        if label:
            ranked.append((score, -idx, label))

    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in ranked[:max_results]]


def generate_fallback_cover_letter(
    *,
    profile_data: Any,
    offer_data: Optional[Dict[str, Any]] = None,
    language_code: str = "fr",
    offer_keywords_collector: Optional[Callable[[], List[str]]] = None,
    include_experience_paragraph: bool = True,
    reason: str = "",
) -> str:
    """Generate a deterministic fallback cover letter from profile data.

    This function creates a professional cover letter without LLM dependency.
    It aligns profile content with job offer keywords when available.

    Args:
        profile_data: UserProfile or ProfileWorkerData object
        offer_data: Job offer dictionary (optional)
        language_code: Target language ("fr" or "en")
        offer_keywords_collector: Optional function to collect offer keywords
        include_experience_paragraph: Whether to include experience paragraph
        reason: Reason for fallback (for logging)

    Returns:
        Cover letter string
    """
    is_en = language_code == "en"

    # Extract offer metadata
    job_title = ""
    company = ""
    if isinstance(offer_data, dict):
        job_title = str(offer_data.get("job_title") or "").strip()
        company = str(offer_data.get("company") or "").strip()

    name = str(getattr(profile_data, "name", "") or "").strip()

    role_label = job_title or ("the target role" if is_en else "le poste vise")
    company_label = company or ("your company" if is_en else "votre entreprise")

    # Collect offer keywords
    offer_keywords: List[str] = []
    if offer_keywords_collector:
        try:
            offer_keywords = offer_keywords_collector()[:12]
        except Exception:
            offer_keywords = []

    # Build keyword alignment
    candidate_terms = collect_candidate_keywords(profile_data)
    mapping = build_keyword_alignment(candidate_terms, offer_keywords)
    matched_terms = _dedup_preserve(list(mapping.values()))

    # Fallback: direct matching if alignment failed
    if not matched_terms and offer_keywords:
        offer_norm = {normalize_keyword_for_match(item) for item in offer_keywords}
        for term in candidate_terms:
            if normalize_keyword_for_match(term) in offer_norm:
                matched_terms.append(term)
        matched_terms = _dedup_preserve(matched_terms)

    matched_preview = ", ".join(matched_terms[:4]) if matched_terms else ""

    # Rank experiences for mention
    exp_preview = ""
    if include_experience_paragraph:
        experiences = getattr(profile_data, "extracted_experiences", None) or []
        exp_labels = _rank_experience_labels(experiences, offer_keywords, job_title)
        exp_preview = ", ".join(exp_labels)

    # Build the letter
    if is_en:
        keywords_sentence = (
            f"My profile is aligned with your priorities, especially {matched_preview}."
            if matched_preview
            else "My profile is aligned with the key requirements of the role."
        )

        if include_experience_paragraph and exp_preview:
            experience_sentence = (
                f"I gained relevant experience in roles such as {exp_preview}. "
                "I can contribute quickly with a structured and reliable execution style.\n\n"
            )
        elif include_experience_paragraph:
            experience_sentence = (
                "I have built practical experience across projects and responsibilities "
                "relevant to this role. I can contribute quickly with a structured and reliable "
                "execution style.\n\n"
            )
        else:
            experience_sentence = ""

        closing_name = name or "Candidate"
        return (
            f"Subject: Application - {role_label}\n\n"
            "Dear Hiring Manager,\n\n"
            f"I am applying for the {role_label} position at {company_label}. "
            f"{keywords_sentence}\n\n"
            f"{experience_sentence}"
            f"I would welcome the opportunity to discuss how my background can support {company_label}.\n\n"
            "Sincerely,\n\n"
            f"{closing_name}"
        ).strip()

    # French version
    keywords_sentence = (
        f"Mon profil est aligne avec vos priorites, en particulier {matched_preview}."
        if matched_preview
        else "Mon profil est aligne avec les besoins cles du poste."
    )

    if include_experience_paragraph and exp_preview:
        experience_sentence = (
            f"J'ai acquis une experience pertinente sur des roles comme {exp_preview}. "
            "Je peux contribuer rapidement avec une execution fiable et orientee resultats.\n\n"
        )
    elif include_experience_paragraph:
        experience_sentence = (
            "J'ai developpe une experience concrete sur des sujets utiles pour ce poste. "
            "Je peux contribuer rapidement avec une execution fiable et orientee resultats.\n\n"
        )
    else:
        experience_sentence = ""

    closing_name = name or "Candidat"
    return (
        f"Objet: Candidature - {role_label}\n\n"
        "Madame, Monsieur,\n\n"
        f"Je vous adresse ma candidature pour le poste {role_label} au sein de {company_label}. "
        f"{keywords_sentence}\n\n"
        f"{experience_sentence}"
        f"Je reste disponible pour echanger sur la maniere dont mon parcours peut soutenir {company_label}.\n\n"
        "Cordialement,\n\n"
        f"{closing_name}"
    ).strip()


def generate_fallback_cover_letter_simple(
    *,
    profile_name: str = "",
    job_title: str = "",
    company: str = "",
    language_code: str = "fr",
    offer_keywords: Optional[List[str]] = None,
    matched_terms: Optional[List[str]] = None,
    reason: str = "",
) -> str:
    """Simplified fallback generator without profile_data object.

    Use this when you only have basic info and pre-computed matched terms.

    Args:
        profile_name: Profile name
        job_title: Target job title
        company: Target company
        language_code: Target language
        offer_keywords: Optional list of offer keywords
        matched_terms: Pre-computed matched terms
        reason: Reason for fallback

    Returns:
        Cover letter string
    """
    is_en = language_code == "en"

    role_label = job_title or ("the target role" if is_en else "le poste vise")
    company_label = company or ("your company" if is_en else "votre entreprise")

    matched_preview = ""
    if matched_terms:
        matched_preview = ", ".join(matched_terms[:4])

    if is_en:
        keywords_sentence = (
            f"My profile is aligned with your priorities, especially {matched_preview}."
            if matched_preview
            else "My profile is aligned with the key requirements of the role."
        )
        closing_name = profile_name or "Candidate"
        return (
            f"Subject: Application - {role_label}\n\n"
            "Dear Hiring Manager,\n\n"
            f"I am applying for the {role_label} position at {company_label}. "
            f"{keywords_sentence}\n\n"
            f"I would welcome the opportunity to discuss how my background can support {company_label}.\n\n"
            "Sincerely,\n\n"
            f"{closing_name}"
        ).strip()

    # French version
    keywords_sentence = (
        f"Mon profil est aligne avec vos priorites, en particulier {matched_preview}."
        if matched_preview
        else "Mon profil est aligne avec les besoins cles du poste."
    )
    closing_name = profile_name or "Candidat"
    return (
        f"Objet: Candidature - {role_label}\n\n"
        "Madame, Monsieur,\n\n"
        f"Je vous adresse ma candidature pour le poste {role_label} au sein de {company_label}. "
        f"{keywords_sentence}\n\n"
        f"Je reste disponible pour echanger sur la maniere dont mon parcours peut soutenir {company_label}.\n\n"
        "Cordialement,\n\n"
        f"{closing_name}"
    ).strip()
