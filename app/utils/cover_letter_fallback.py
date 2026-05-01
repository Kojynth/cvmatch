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
    if "alternant" in norm and "qa" in norm:
        return "QA Engineer Apprentice"
    if "ingenieur qa" in norm and "alternance" in norm:
        return "QA Engineer Apprentice"
    replacements = (
        ("Alternant Ingénieur QA", "QA Engineer Apprentice"),
        ("Alternant Ingenieur QA", "QA Engineer Apprentice"),
        ("Alternant Ing?nieur QA", "QA Engineer Apprentice"),
        ("Ingénieur QA en alternance", "QA Engineer Apprentice"),
        ("Ingenieur QA en alternance", "QA Engineer Apprentice"),
        ("Ing?nieur QA en alternance", "QA Engineer Apprentice"),
        ("Stage Business Developer", "Business Development Intern"),
        ("Stage Sales Support Manager", "Sales Support Intern"),
    )
    for src, dst in replacements:
        if src.lower() in label.lower():
            return dst
    if label.lower().startswith("stage "):
        return f"{label[6:].strip()} Intern"
    return label


def _clean_company_label(company: str) -> str:
    label = str(company or "").strip()
    replacements = (
        ("LaPoste Santé et Autonomie", "La Poste Santé & Autonomie"),
        ("La Poste Santé et Autonomie", "La Poste Santé & Autonomie"),
        ("LaPoste Sant? et Autonomie", "La Poste Santé & Autonomie"),
        ("La Poste Sant? et Autonomie", "La Poste Santé & Autonomie"),
        ("LaPoste", "La Poste"),
        ("La Poste Sante", "La Poste Santé"),
        ("LaPoste Santé", "La Poste Santé"),
        ("Careside Filiale", "Careside"),
        ("(Careside)", "- Careside"),
        ("(Careside Filiale)", "- Careside"),
    )
    for src, dst in replacements:
        label = label.replace(src, dst)
    label = " ".join(label.split())
    label = label.replace(" - - ", " - ")
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


def _collect_offer_context_terms(offer_data: Optional[Dict[str, Any]]) -> List[str]:
    if not isinstance(offer_data, dict):
        return []
    fragments: List[str] = []
    for key in ("text", "description", "job_title", "company"):
        _collect_text_fragments(offer_data.get(key), fragments)
    analysis = offer_data.get("analysis")
    if isinstance(analysis, dict):
        for key in (
            "summary",
            "keywords",
            "skills",
            "tech_keywords",
            "responsibilities",
            "lexical_field",
            "tools",
        ):
            _collect_text_fragments(analysis.get(key), fragments)
    source = normalize_keyword_for_match(" ".join(fragments))
    if not source:
        return []

    phrase_map = (
        ("frontier ai", "frontier AI"),
        ("frontier model", "frontier models"),
        ("open model", "open model development"),
        ("open source", "open-source AI"),
        ("european", "a European AI context"),
        ("europe", "a European AI context"),
        ("research", "research"),
        ("enterprise deployment", "enterprise deployment"),
        ("human data", "human data workflows"),
        ("training data", "training data quality"),
        ("annotation", "annotation quality"),
        ("rubric", "rubric-based evaluation"),
        ("model evaluation", "model evaluation"),
        ("code review", "code review"),
        ("coding agent", "coding agents"),
    )
    terms: List[str] = []
    for needle, label in phrase_map:
        if needle in source:
            terms.append(label)
    return _dedup_preserve(terms)[:4]


def _has_qa_signal(profile_data: Any) -> bool:
    fragments: List[str] = []
    for attr in (
        "extracted_skills",
        "extracted_experiences",
        "extracted_projects",
        "extracted_certifications",
    ):
        _collect_text_fragments(getattr(profile_data, attr, None), fragments, max_chars=3000)
    source = normalize_keyword_for_match(" ".join(fragments))
    return any(
        token in source
        for token in (
            "qa",
            "quality assurance",
            "test",
            "testing",
            "validation",
            "defect",
            "regression",
        )
    )


def _role_motivation_sentence(
    *,
    role_label: str,
    offer_focus: str,
    has_qa_signal: bool,
    is_en: bool,
) -> str:
    role_norm = normalize_keyword_for_match(role_label)
    quality_role = any(
        token in role_norm
        for token in ("quality", "data", "annotation", "evaluation", "review", "code")
    )
    if is_en:
        if "code" in role_norm and "data" in role_norm and "quality" in role_norm:
            role_focus = "code and data quality work"
        elif role_label and role_label != "the target role":
            role_focus = f"{role_label} work"
        else:
            role_focus = "the responsibilities of this role"
        if has_qa_signal and quality_role:
            return (
                f"I see this role as a natural move from software quality work toward {role_focus}: applying the same discipline of checking requirements, edge cases, inconsistencies, and outputs to a more AI-oriented review context."
            )
        return (
            f"I see this role as a concrete next step because it lets me apply my experience to {role_focus} in a more focused and useful way."
        )
    if "code" in role_norm and "data" in role_norm and "quality" in role_norm:
        role_focus = "la qualite des donnees et du code"
    elif role_label and role_label != "le poste vise":
        role_focus = f"des missions de {role_label}"
    else:
        role_focus = "les responsabilites du poste"
    if has_qa_signal and quality_role:
        return (
            f"Je vois ce poste comme une evolution naturelle de la qualite logicielle vers {role_focus} : appliquer la meme rigueur sur les exigences, les cas limites, les incoherences et les livrables dans un contexte de revue plus oriente IA."
        )
    return (
        f"Je vois ce poste comme une etape concrete parce qu'il me permet d'appliquer mon experience a {role_focus} de maniere plus ciblee et utile."
    )


def _company_motivation_sentence(
    *,
    company_label: str,
    offer_focus: str,
    company_context: str = "",
    is_en: bool,
) -> str:
    if is_en:
        role_focus = f"work involving {offer_focus}" if offer_focus else ""
        if company_context and offer_focus:
            return (
                f"{company_label} stands out to me because its work is connected to {company_context}. What attracts me to this role is the chance to contribute to {role_focus} in that concrete context."
            )
        if company_context:
            return (
                f"{company_label} stands out to me because its work is connected to {company_context}. I want to contribute in a role where careful review and practical delivery matter."
            )
        if offer_focus:
            return (
                f"What interests me about {company_label} is the role's focus on {role_focus}: it matches the kind of concrete work where I can combine practical delivery, careful checks, and useful documentation."
            )
        return (
            f"What interests me about {company_label} is the opportunity to contribute in a concrete team context where careful review and useful documentation matter."
        )
    role_focus = f"des travaux impliquant {offer_focus}" if offer_focus else ""
    if company_context and offer_focus:
        return (
            f"{company_label} m'interesse parce que son travail est lie a {company_context}. Ce qui m'attire dans ce poste, c'est la possibilite de contribuer a {role_focus} dans ce contexte concret."
        )
    if company_context:
        return (
            f"{company_label} m'interesse parce que son travail est lie a {company_context}. Je souhaite contribuer dans un poste ou la revue attentive et la livraison concrete comptent."
        )
    if offer_focus:
        return (
            f"Ce qui m'interesse chez {company_label}, c'est le focus du poste sur {role_focus} : il correspond a un cadre concret ou je peux combiner livraison pratique, verification attentive et documentation utile."
        )
    return (
        f"Ce qui m'interesse chez {company_label}, c'est la possibilite de contribuer a une equipe concrete ou l'execution rigoureuse et la documentation utile comptent reellement."
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

    matched_preview = _join_terms_natural(
        matched_terms,
        max_items=4,
        conjunction=conjunction,
        language_code=language_code,
    )

    # Rank experiences for mention
    exp_preview = ""
    experience_detail = ""
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
            experience_detail = "; ".join(details[:3])

    projects = getattr(profile_data, "extracted_projects", None) or []
    featured_project = _select_featured_project(projects)
    project_name = _first_text(featured_project, "name", "title") if featured_project else ""
    project_terms = _collect_entry_terms(featured_project, max_items=5) if featured_project else []
    project_terms_text = _join_terms_natural(
        project_terms,
        max_items=5,
        conjunction=conjunction,
        language_code=language_code,
    )
    offer_focus = _join_terms_natural(
        offer_keywords,
        max_items=4,
        conjunction=conjunction,
        language_code=language_code,
    )
    company_context = _join_terms_natural(
        _collect_offer_context_terms(offer_data),
        max_items=3,
        conjunction=conjunction,
        language_code=language_code,
    )
    motivation_sentence = _company_motivation_sentence(
        company_label=company_label,
        offer_focus=offer_focus,
        company_context=company_context,
        is_en=is_en,
    )
    role_motivation = _role_motivation_sentence(
        role_label=role_label,
        offer_focus=offer_focus,
        has_qa_signal=_has_qa_signal(profile_data),
        is_en=is_en,
    )

    # Build the letter
    if is_en:
        profile_signal = matched_preview
        opening_signal = (
            f"My profile includes relevant evidence in {profile_signal}."
            if profile_signal
            else "The role connects with my documented background and project work."
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
            experience_sentence = (
                f"{experience_intro}, my work includes {experience_detail}. "
                "These responsibilities are relevant because they require working from stated requirements, handling concrete constraints, and communicating outcomes clearly.\n\n"
            )
        elif include_experience_paragraph and exp_preview:
            experience_sentence = (
                f"My background includes {exp_preview}. These experiences helped me build a practical approach to execution, validation, and communication against stated requirements.\n\n"
            )
        else:
            experience_sentence = ""

        if project_name and project_terms_text:
            project_sentence = (
                f"I also developed {project_name} with {project_terms_text}. This strengthened my ability to build practical solutions and validate outputs before delivery.\n\n"
            )
        elif project_name:
            project_sentence = (
                f"I also developed {project_name}, which strengthened my practical approach to implementation and validation.\n\n"
            )
        else:
            project_sentence = ""

        if offer_focus and profile_signal:
            contribution_sentence = (
                f"I would bring relevant evidence in {profile_signal}, with a focus on consistent review, factual accuracy, and useful documentation."
            )
        elif offer_focus:
            contribution_sentence = (
                "I would approach those expectations with consistent review, factual accuracy, and useful documentation."
            )
        elif profile_signal:
            contribution_sentence = (
                f"I would bring relevant evidence in {profile_signal}, with a focus on consistent review, factual accuracy, and useful documentation."
            )
        else:
            contribution_sentence = (
                "I would be interested in contributing with a careful, evidence-based approach focused on consistent review and useful documentation."
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
            f"{motivation_sentence} {role_motivation}\n\n"
            f"{contribution_sentence} I would welcome the opportunity to discuss how my background can support {company_label}.\n\n"
            "Sincerely,\n\n"
            f"{closing_name}"
        ).strip()

    # French version
    profile_signal = matched_preview
    keywords_sentence = (
        f"Mon profil presente des elements pertinents autour de {profile_signal}."
        if profile_signal
        else "Le poste fait echo a mon parcours documente et a mes projets."
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
        experience_sentence = (
            f"{experience_intro}, mes travaux couvrent {experience_detail}. "
            "Ces responsabilites sont pertinentes car elles demandent de travailler a partir d'exigences formulees, de gerer des contraintes concretes et de communiquer clairement les resultats.\n\n"
        )
    elif include_experience_paragraph and exp_preview:
        experience_sentence = (
            f"Mon parcours inclut {exp_preview}. Ces experiences m'ont aide a construire une approche pratique de l'execution, de la validation et de la communication face aux exigences formulees.\n\n"
        )
    else:
        experience_sentence = ""

    if project_name and project_terms_text:
        project_sentence = (
            f"J'ai aussi developpe {project_name} avec {project_terms_text}. Ce projet a renforce ma capacite a construire des solutions concretes et a verifier les livrables avant diffusion.\n\n"
        )
    elif project_name:
        project_sentence = (
            f"J'ai aussi developpe {project_name}, ce qui a renforce mon approche pratique de l'implementation et de la validation.\n\n"
        )
    else:
        project_sentence = ""

    if offer_focus and profile_signal:
        contribution_sentence = (
            f"J'apporte des elements pertinents autour de {profile_signal}, avec une attention particuliere a la revue constante, a l'exactitude factuelle et a une documentation utile."
        )
    elif offer_focus:
        contribution_sentence = (
            "Je l'aborderais avec une attention particuliere a la revue constante, a l'exactitude factuelle et a une documentation utile."
        )
    elif profile_signal:
        contribution_sentence = (
            f"J'apporte des elements pertinents autour de {profile_signal}, avec une attention particuliere a la revue constante, a l'exactitude factuelle et a une documentation utile."
        )
    else:
        contribution_sentence = (
            "Je souhaite contribuer avec une approche rigoureuse et fondee sur les elements disponibles, attentive a la revue constante et a une documentation utile."
        )

    if not include_experience_paragraph and not project_sentence:
        experience_sentence = (
            "J'ai developpe une experience concrete sur des sujets utiles pour ce poste. "
            "Je peux contribuer rapidement avec une execution fiable et orientee resultats.\n\n"
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
        f"{motivation_sentence} {role_motivation}\n\n"
        f"{contribution_sentence} Je reste disponible pour echanger sur la maniere dont mon parcours peut soutenir {company_label}.\n\n"
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

    role_label = job_title or ("the target role" if is_en else "le poste vise")
    company_label = company or ("your company" if is_en else "votre entreprise")

    matched_preview = _join_terms_natural(
        matched_terms or [],
        max_items=4,
        conjunction=conjunction,
        language_code=language_code,
    )
    offer_preview = _join_terms_natural(
        offer_keywords or [],
        max_items=4,
        conjunction=conjunction,
        language_code=language_code,
    )

    if is_en:
        if matched_preview:
            keywords_sentence = (
                f"My profile includes relevant evidence in {matched_preview}."
            )
        elif offer_preview:
            keywords_sentence = (
                f"I understand that the role emphasizes {offer_preview}, and I would approach it with careful, evidence-based execution."
            )
        else:
            keywords_sentence = (
                "I would approach the role with consistent review, factual accuracy, and useful documentation."
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
            f"{_company_motivation_sentence(company_label=company_label, offer_focus=offer_preview, is_en=True)}\n\n"
            "I would welcome the opportunity to discuss how my background can support "
            f"{company_label} with a reliable and evidence-based contribution.\n\n"
            "Sincerely,\n\n"
            f"{closing_name}"
        ).strip()

    # French version
    if matched_preview:
        keywords_sentence = (
            f"Mon profil presente des elements pertinents autour de {matched_preview}."
        )
    elif offer_preview:
        keywords_sentence = (
            f"Je comprends que le poste met l'accent sur {offer_preview}, et je l'aborderais avec une execution rigoureuse fondee sur les elements disponibles."
        )
    else:
        keywords_sentence = (
            "J'aborderais le poste avec une revue constante, une exactitude factuelle et une documentation utile."
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
        f"{_company_motivation_sentence(company_label=company_label, offer_focus=offer_preview, is_en=False)}\n\n"
        f"Je reste disponible pour echanger sur la maniere dont mon parcours peut soutenir {company_label}.\n\n"
        "Cordialement,\n\n"
        f"{closing_name}"
    ).strip()
