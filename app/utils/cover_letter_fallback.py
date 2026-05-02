"""
Cover Letter Fallback Generator Module 

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

import re
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
from .language_policy import language_token_scores, normalize_language_code
from ..domain.generation.tool_signals import collect_named_tool_hints


_TERM_BLOCKLIST = {
    "summary",
    "profile",
    "candidate",
    "skill",
    "skills",
    "competence",
    "competences",
    "experience",
    "experiences",
    "project",
    "projects",
    "certification",
    "certifications",
    "education",
    "language",
    "languages",
    "responsibility",
    "responsibilities",
    "keyword",
    "keywords",
    "tool",
    "tools",
    "technology",
    "technologies",
    "seek",
    "seeking",
    "organiser",
    "organize",
    "organizer",
    "transverse",
    "transverses",
    "implicit",
    "implicite",
    "implicites",
    "recruiter",
    "recruteur",
    "clearly",
    "concretely",
    "directly",
    "easily",
    "efficiently",
    "effectively",
    "especially",
    "highly",
    "mostly",
    "particularly",
    "proactively",
    "quickly",
    "really",
    "seamlessly",
    "strongly",
    "very",
}

_TERM_CANONICAL_CASE = {
    "api": "API",
    "rest": "REST",
    "rest api": "REST API",
    "json": "JSON",
    "sql": "SQL",
    "llm": "LLM",
    "ai": "AI",
    "ml": "ML",
    "qa": "QA",
    "ui": "UI",
    "ux": "UX",
    "ci": "CI",
    "cd": "CD",
    "ci cd": "CI/CD",
    "python": "Python",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "github": "GitHub",
    "gitlab": "GitLab",
    "postgresql": "PostgreSQL",
    "mongodb": "MongoDB",
    "pytest": "pytest",
    "git": "Git",
    "linux": "Linux",
    "unix": "Unix",
    "unix terminal": "Unix terminal",
    "prompt engineering": "prompt engineering",
    "codex": "Codex",
    "claude": "Claude",
    "claude code": "Claude Code",
    "code agents": "coding agents",
}


def _strip_term_prefix(text: str) -> str:
    value = str(text or "").strip()
    value = re.sub(
        r"^(?:d['’]|de|du|des|le|la|les|of|for|with|sur|en|pour)\s+",
        "",
        value,
        flags=re.IGNORECASE,
    )
    return value.strip(" \t\r\n,;:")


def _has_cross_language_noise(text: str, language_code: str) -> bool:
    target = normalize_language_code(language_code)
    norm = normalize_keyword_for_match(text)
    if not norm:
        return True
    tokens = set(norm.split())
    if target == "en":
        french_noise = {
            "du",
            "des",
            "les",
            "pour",
            "avec",
            "chez",
            "recruteur",
            "implicite",
            "implicites",
            "transverse",
            "transverses",
            "organiser",
        }
        return bool(tokens & french_noise)
    if target == "fr":
        english_noise = {"seeking", "recruiter"}
        return bool(tokens & english_noise)
    return False


def _clean_sentence_term(term: Any, *, language_code: str = "") -> str:
    text = re.sub(r"\s+", " ", str(term or "").strip(" \t\r\n,;:"))
    text = _strip_term_prefix(text)
    if not text or "..." in text or "…" in text:
        return ""
    if len(text) > 64:
        return ""
    if language_code and _has_cross_language_noise(text, language_code):
        return ""
    norm = normalize_keyword_for_match(text)
    if not norm or norm in _TERM_BLOCKLIST:
        return ""
    tokens = norm.split()
    if len(tokens) == 1 and len(tokens[0]) < 3:
        return ""
    return _TERM_CANONICAL_CASE.get(norm, text)


def _clean_sentence_terms(
    terms: List[str],
    *,
    max_items: int = 5,
    language_code: str = "",
) -> List[str]:
    cleaned = [
        _clean_sentence_term(term, language_code=language_code)
        for term in terms or []
    ]
    return _dedup_preserve([term for term in cleaned if term])[:max_items]


def _coerce_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _first_text(value: Any, *keys: str) -> str:
    if isinstance(value, dict):
        for key in keys:
            text = str(value.get(key) or "").strip()
            if text:
                return text
    return ""


def _collect_entry_terms(entry: Any, *, max_items: int = 6) -> List[str]:
    terms: List[str] = []

    def add(raw: Any) -> None:
        if raw is None:
            return
        if isinstance(raw, str):
            text = raw.strip()
            if text and len(text) <= 80:
                terms.append(text)
            return
        if isinstance(raw, list):
            for item in raw:
                add(item)
            return
        if isinstance(raw, dict):
            for key in ("name", "title", "skill", "technology", "tool", "label"):
                add(raw.get(key))

    if isinstance(entry, dict):
        for key in ("technologies", "tools", "skills", "items", "skills_list"):
            add(entry.get(key))
        if len(terms) < max_items:
            add(collect_named_tool_hints(entry, max_items=max_items))
    return _dedup_preserve(terms)[:max_items]


def _text_matches_language(text: str, language_code: str) -> bool:
    target = normalize_language_code(language_code)
    if target not in {"en", "fr"}:
        return True
    fr_score, en_score, token_count = language_token_scores(text)
    if token_count < 5:
        return True
    if target == "en":
        return not (fr_score >= 2 and fr_score > en_score)
    if target == "fr":
        return not (en_score >= 2 and en_score > fr_score)
    return True


def _without_clipped_tail(text: str, max_chars: int) -> str:
    value = str(text or "").strip()
    if not value or "..." in value or "…" in value:
        return ""
    if len(value) <= max_chars:
        return value
    sentences = re.split(r"(?<=[.!?])\s+", value)
    for sentence in sentences:
        candidate = sentence.strip()
        if 24 <= len(candidate) <= max_chars:
            return candidate
    return ""


def _entry_details(
    entry: Any,
    *,
    max_items: int = 3,
    max_chars: int = 180,
    language_code: str = "",
) -> List[str]:
    values: List[str] = []
    seen: set[str] = set()
    if not isinstance(entry, dict):
        return values
    for key in ("achievements", "highlights", "responsibilities", "description", "details"):
        if key == "description" and values:
            continue
        raw = entry.get(key)
        for item in _coerce_list(raw):
            text = str(item or "").strip()
            if not text:
                continue
            text = _without_clipped_tail(text, max_chars)
            if not text:
                continue
            if language_code and not _text_matches_language(text, language_code):
                continue
            norm = normalize_keyword_for_match(text)
            if norm in seen:
                continue
            seen.add(norm)
            values.append(text)
            if len(values) >= max_items:
                return values
    return values


def _english_role_label(title: str) -> str:
    label = str(title or "").strip()
    norm = normalize_keyword_for_match(label)
    if not label:
        return ""
    if norm.startswith("stage "):
        return f"{label[6:].strip()} Intern"
    if norm.startswith("alternant "):
        return f"{label[10:].strip()} Apprentice"
    if norm.endswith(" en alternance"):
        cleaned = re.sub(r"\s+en\s+alternance\s*$", "", label, flags=re.IGNORECASE)
        return f"{cleaned.strip()} Apprentice" if cleaned.strip() else label
    return label


def _clean_company_label(company: str) -> str:
    label = str(company or "").strip()
    label = re.sub(r"\s+", " ", label)
    label = re.sub(r"\s*-\s*", " - ", label)
    label = re.sub(r"(?:\s+-){2,}", " -", label)
    return label.strip(" -")


def _format_experience_label(title: str, company: str, *, is_en: bool) -> str:
    title_value = _english_role_label(title) if is_en else str(title or "").strip()
    company_value = _clean_company_label(company)
    if title_value and company_value:
        return f"{title_value} ({company_value})"
    return title_value or company_value


def _subject_with_offer_company(
    *,
    role_label: str,
    company: str,
    language_code: str,
) -> str:
    company_name = str(company or "").strip()
    role = str(role_label or "").strip()
    if language_code == "en":
        subject = f"Application - {role}" if role else "Application"
        return (
            f"Subject: {subject} ({company_name})"
            if company_name
            else f"Subject: {subject}"
        )

    subject = f"Candidature - {role}" if role else "Candidature"
    return (
        f"Objet: {subject} ({company_name})"
        if company_name
        else f"Objet: {subject}"
    )


def _rank_experience_labels(
    experiences: List[Dict[str, Any]],
    offer_keywords: List[str],
    job_title: str = "",
    *,
    max_results: int = 2,
    language_code: str = "en",
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

        label = _format_experience_label(
            title,
            company_exp,
            is_en=str(language_code or "").lower().startswith("en"),
        )

        if label:
            ranked.append((score, idx, label))

    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in ranked[:max_results]]


def _select_primary_experience(
    experiences: List[Dict[str, Any]],
    offer_keywords: List[str],
    job_title: str,
    *,
    language_code: str,
) -> Optional[Dict[str, Any]]:
    if not experiences:
        return None
    labels = _rank_experience_labels(
        experiences,
        offer_keywords,
        job_title,
        max_results=1,
        language_code=language_code,
    )
    if labels:
        label_key = normalize_keyword_for_match(labels[0])
        for entry in experiences:
            label = _format_experience_label(
                str(entry.get("title") or ""),
                str(entry.get("company") or ""),
                is_en=str(language_code or "").lower().startswith("en"),
            )
            if normalize_keyword_for_match(label) == label_key:
                return entry
    return experiences[0]


def _select_featured_project(projects: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for project in projects:
        if isinstance(project, dict) and str(project.get("name") or "").strip():
            return project
    return None


def _join_terms(
    terms: List[str],
    *,
    max_items: int = 5,
    language_code: str = "",
) -> str:
    values = _clean_sentence_terms(
        terms,
        max_items=max_items,
        language_code=language_code,
    )
    return ", ".join(values[:max_items])


def _join_natural(items: List[str], *, conjunction: str) -> str:
    values = [str(item or "").strip() for item in items or [] if str(item or "").strip()]
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    if len(values) == 2:
        return f"{values[0]} {conjunction} {values[1]}"
    if conjunction == "and":
        return f"{', '.join(values[:-1])}, and {values[-1]}"
    return f"{', '.join(values[:-1])}, {conjunction} {values[-1]}"


def _join_terms_natural(
    terms: List[str],
    *,
    max_items: int = 5,
    conjunction: str,
    language_code: str = "",
) -> str:
    return _join_natural(
        _clean_sentence_terms(
            terms,
            max_items=max_items,
            language_code=language_code,
        ),
        conjunction=conjunction,
    )


def _collect_text_fragments(value: Any, output: List[str], *, max_chars: int = 5000) -> None:
    if len(" ".join(output)) >= max_chars:
        return
    if value is None:
        return
    if isinstance(value, str):
        text = value.strip()
        if text:
            output.append(text[:max_chars])
        return
    if isinstance(value, dict):
        for item in value.values():
            _collect_text_fragments(item, output, max_chars=max_chars)
            if len(" ".join(output)) >= max_chars:
                break
        return
    if isinstance(value, list):
        for item in value:
            _collect_text_fragments(item, output, max_chars=max_chars)
            if len(" ".join(output)) >= max_chars:
                break


def _project_reference_sentence(
    *,
    project_name: str,
    project_terms: List[str],
    language_code: str,
    conjunction: str,
    is_en: bool,
) -> str:
    if not project_name:
        return ""
    terms_text = _join_terms_natural(
        project_terms,
        max_items=4,
        conjunction=conjunction,
        language_code=language_code,
    )
    if is_en:
        if terms_text:
            return (
                f"My project work also includes {project_name}, where I worked with {terms_text}.\n\n"
            )
        return (
            f"My project work also includes {project_name}, which is another example of how I approach practical work.\n\n"
        )

    if terms_text:
        return (
            f"Mes projets incluent également {project_name}, avec un travail autour de {terms_text}.\n\n"
        )
    return (
        f"Mes projets incluent également {project_name}, qui illustre aussi ma manière d'aborder un travail concret.\n\n"
    )


def _format_experience_details(details: List[str], *, is_en: bool) -> str:
    cleaned = [str(item or "").strip() for item in details or [] if str(item or "").strip()]
    if not cleaned:
        return ""
    action_verbs = {
        "analyzed",
        "analysed",
        "built",
        "contributed",
        "coordinated",
        "created",
        "designed",
        "developed",
        "documented",
        "implemented",
        "improved",
        "managed",
        "performed",
        "reviewed",
        "tested",
        "validated",
        "worked",
    }
    sentences: List[str] = []
    fragments: List[str] = []
    for item in cleaned[:3]:
        norm = normalize_keyword_for_match(item)
        first = norm.split()[0] if norm.split() else ""
        looks_like_sentence = first in action_verbs or norm.startswith(
            ("i ", "this ", "the ", "my ", "we ", "j ", "je ", "ce ", "cela ")
        )
        if looks_like_sentence:
            sentence_body = item.rstrip(".!?")
            if is_en and first in action_verbs and not norm.startswith(("i ", "we ")):
                sentence_body = "I " + sentence_body[:1].lower() + sentence_body[1:]
            sentence = sentence_body + "."
            sentences.append(sentence)
        else:
            fragments.append(item.rstrip("."))
    output: List[str] = []
    if fragments:
        if is_en:
            output.append(f"This included {_join_natural(fragments, conjunction='and')}.")
        else:
            output.append(f"Cela incluait {_join_natural(fragments, conjunction='et')}.")
    output.extend(sentences)
    return " ".join(output)


def _company_motivation_sentence(
    *,
    company_label: str,
    is_en: bool,
) -> str:
    if is_en:
        return (
            f"What interests me about {company_label} is the opportunity to contribute to the priorities described in this role."
        )
    return (
        f"Ce qui m'intéresse chez {company_label}, c'est la possibilité de contribuer aux priorités décrites dans ce poste."
    )


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
    language_code = normalize_language_code(language_code)
    if language_code not in {"en", "fr"}:
        logger.warning(
            "Deterministic cover letter fallback skipped for unsupported language: %s",
            language_code,
        )
        return ""
    is_en = language_code == "en"
    conjunction = "and" if is_en else "et"

    # Extract offer metadata
    job_title = ""
    company = ""
    if isinstance(offer_data, dict):
        job_title = str(offer_data.get("job_title") or "").strip()
        company = str(offer_data.get("company") or "").strip()

    name = str(getattr(profile_data, "name", "") or "").strip()

    role_label = job_title or ("the target role" if is_en else "le poste visé")
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

    matched_preview = _join_terms_natural(
        matched_terms,
        max_items=4,
        conjunction=conjunction,
        language_code=language_code,
    )

    # Rank experiences for mention
    exp_preview = ""
    experience_detail = ""
    experience_details: List[str] = []
    primary_experience: Optional[Dict[str, Any]] = None
    if include_experience_paragraph:
        experiences = getattr(profile_data, "extracted_experiences", None) or []
        exp_labels = _rank_experience_labels(
            experiences,
            offer_keywords,
            job_title,
            language_code=language_code,
        )
        exp_preview = _join_natural(exp_labels, conjunction=conjunction)
        primary_experience = _select_primary_experience(
            experiences,
            offer_keywords,
            job_title,
            language_code=language_code,
        )
        if primary_experience:
            details = _entry_details(
                primary_experience,
                max_items=3,
                max_chars=170,
                language_code=language_code,
            )
            experience_details = details
            experience_detail = "; ".join(details[:3])

    projects = getattr(profile_data, "extracted_projects", None) or []
    featured_project = _select_featured_project(projects)
    project_name = _first_text(featured_project, "name", "title") if featured_project else ""
    project_terms = _collect_entry_terms(featured_project, max_items=5) if featured_project else []
    motivation_sentence = _company_motivation_sentence(
        company_label=company_label,
        is_en=is_en,
    )

    # Build the letter
    if is_en:
        profile_signal = matched_preview
        opening_signal = (
            f"My profile includes experience related to {profile_signal}."
            if profile_signal
            else "My background gives me a basis to contribute to this role."
        )

        experience_intro = exp_preview
        if primary_experience:
            role = _english_role_label(str(primary_experience.get("title") or ""))
            company_exp = _clean_company_label(
                str(primary_experience.get("company") or "")
            )
            if role and company_exp:
                experience_intro = f"As a {role} at {company_exp}"
            elif role:
                experience_intro = f"As a {role}"

        if include_experience_paragraph and exp_preview and experience_detail:
            details_sentence = _format_experience_details(experience_details, is_en=True)
            experience_sentence = (
                f"{experience_intro}, I have worked on responsibilities relevant to this application. "
                f"{details_sentence} "
                "This experience strengthened my ability to work with clear objectives, practical constraints, and careful communication.\n\n"
            )
        elif include_experience_paragraph and exp_preview:
            experience_sentence = (
                f"My background includes {exp_preview}, which gives me experience I can bring to the role.\n\n"
            )
        else:
            experience_sentence = ""

        project_sentence = _project_reference_sentence(
            project_name=project_name,
            project_terms=project_terms,
            language_code=language_code,
            conjunction=conjunction,
            is_en=True,
        )

        if profile_signal:
            contribution_sentence = (
                f"I can bring {profile_signal} together with a careful and practical way of working."
            )
        else:
            contribution_sentence = (
                "I can bring a careful and practical way of working, with attention to the team's concrete needs."
            )

        closing_name = name or "Candidate"
        subject_line = _subject_with_offer_company(
            role_label=role_label,
            company=company,
            language_code="en",
        )
        return (
            f"{subject_line}\n\n"
            "Dear Hiring Manager,\n\n"
            f"I am applying for the {role_label} position at {company_label}. "
            f"{opening_signal}\n\n"
            f"{experience_sentence}"
            f"{project_sentence}"
            f"{motivation_sentence}\n\n"
            f"{contribution_sentence} I would welcome the opportunity to discuss how my background can support {company_label}.\n\n"
            "Sincerely,\n\n"
            f"{closing_name}"
        ).strip()

    # French version
    profile_signal = matched_preview
    keywords_sentence = (
        f"Mon profil présente une expérience en lien avec {profile_signal}."
        if profile_signal
        else "Mon parcours me donne une base pertinente pour contribuer à ce poste."
    )

    experience_intro = exp_preview
    if primary_experience:
        role = str(primary_experience.get("title") or "").strip()
        company_exp = _clean_company_label(str(primary_experience.get("company") or ""))
        if role and company_exp:
            experience_intro = f"En tant que {role} chez {company_exp}"
        elif role:
            experience_intro = f"En tant que {role}"

    if include_experience_paragraph and exp_preview and experience_detail:
        details_sentence = _format_experience_details(experience_details, is_en=False)
        experience_sentence = (
            f"{experience_intro}, j'ai travaillé sur des responsabilités pertinentes pour cette candidature. "
            f"{details_sentence} "
            "Cette expérience a renforcé ma capacité à travailler avec des objectifs clairs, des contraintes concrètes et une communication précise.\n\n"
        )
    elif include_experience_paragraph and exp_preview:
        experience_sentence = (
            f"Mon parcours inclut {exp_preview}, une expérience que je peux mettre au service du poste.\n\n"
        )
    else:
        experience_sentence = ""

    project_sentence = _project_reference_sentence(
        project_name=project_name,
        project_terms=project_terms,
        language_code=language_code,
        conjunction=conjunction,
        is_en=False,
    )

    if profile_signal:
        contribution_sentence = (
            f"Je peux apporter {profile_signal}, avec une manière de travailler attentive et concrète."
        )
    else:
        contribution_sentence = (
            "Je souhaite contribuer avec une manière de travailler attentive, concrète et utile aux besoins de l'équipe."
        )

    if not include_experience_paragraph and not project_sentence:
        experience_sentence = (
            "Mon parcours présente des points utiles pour cette candidature. "
            "Je peux contribuer avec une approche attentive et concrète.\n\n"
        )

    closing_name = name or "Candidat"
    subject_line = _subject_with_offer_company(
        role_label=role_label,
        company=company,
        language_code="fr",
    )
    return (
        f"{subject_line}\n\n"
        "Madame, Monsieur,\n\n"
        f"Je vous adresse ma candidature pour le poste {role_label} au sein de {company_label}. "
        f"{keywords_sentence}\n\n"
        f"{experience_sentence}"
        f"{project_sentence}"
        f"{motivation_sentence}\n\n"
        f"{contribution_sentence} Je reste disponible pour échanger sur la manière dont mon parcours peut soutenir {company_label}.\n\n"
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
    language_code = normalize_language_code(language_code)
    if language_code not in {"en", "fr"}:
        logger.warning(
            "Simple deterministic cover letter fallback skipped for unsupported language: %s",
            language_code,
        )
        return ""
    is_en = language_code == "en"
    conjunction = "and" if is_en else "et"

    role_label = job_title or ("the target role" if is_en else "le poste visé")
    company_label = company or ("your company" if is_en else "votre entreprise")

    matched_preview = _join_terms_natural(
        matched_terms or [],
        max_items=4,
        conjunction=conjunction,
        language_code=language_code,
    )

    if is_en:
        if matched_preview:
            keywords_sentence = (
                f"My profile includes experience related to {matched_preview}."
            )
        else:
            keywords_sentence = (
                "My background gives me a basis to contribute to this role."
            )
        closing_name = profile_name or "Candidate"
        subject_line = _subject_with_offer_company(
            role_label=role_label,
            company=company,
            language_code="en",
        )
        return (
            f"{subject_line}\n\n"
            "Dear Hiring Manager,\n\n"
            f"I am applying for the {role_label} position at {company_label}. "
            f"{keywords_sentence}\n\n"
            f"{_company_motivation_sentence(company_label=company_label, is_en=True)}\n\n"
            "I would welcome the opportunity to discuss how my background can support "
            f"{company_label} with a careful and practical contribution.\n\n"
            "Sincerely,\n\n"
            f"{closing_name}"
        ).strip()

    # French version
    if matched_preview:
        keywords_sentence = (
            f"Mon profil présente une expérience en lien avec {matched_preview}."
        )
    else:
        keywords_sentence = (
            "Mon parcours me donne une base pertinente pour contribuer à ce poste."
        )
    closing_name = profile_name or "Candidat"
    subject_line = _subject_with_offer_company(
        role_label=role_label,
        company=company,
        language_code="fr",
    )
    return (
        f"{subject_line}\n\n"
        "Madame, Monsieur,\n\n"
        f"Je vous adresse ma candidature pour le poste {role_label} au sein de {company_label}. "
        f"{keywords_sentence}\n\n"
        f"{_company_motivation_sentence(company_label=company_label, is_en=False)}\n\n"
        f"Je reste disponible pour échanger sur la manière dont mon parcours peut soutenir {company_label}.\n\n"
        "Cordialement,\n\n"
        f"{closing_name}"
    ).strip()
