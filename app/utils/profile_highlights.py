"""Utility helpers to derive structured highlights and letter fallbacks."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _first_sentence_from_master(profile: Any) -> str:
    """Return the first meaningful sentence from the stored master CV."""
    if profile is None:
        return ""
    content = getattr(profile, "master_cv_content", None) or ""
    for line in content.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and len(stripped) > 25:
            return stripped
    return ""


def resolve_cover_letter_language(
    profile: Any,
    offer_data: Optional[Dict[str, Any]],
    default: str = "fr",
) -> str:
    """Resolve the target language for cover-letter generation."""
    candidate = None
    if isinstance(offer_data, dict):
        analysis = offer_data.get("analysis")
        if isinstance(analysis, dict):
            language = analysis.get("language") or analysis.get("lang")
            if isinstance(language, str) and language.strip():
                candidate = language
        if candidate is None:
            raw = offer_data.get("language") if offer_data else None
            if isinstance(raw, str) and raw.strip():
                candidate = raw
    if candidate is None:
        preferred = getattr(profile, "preferred_language", None)
        if isinstance(preferred, str) and preferred.strip():
            candidate = preferred
    if candidate is None:
        candidate = default
    normalized = str(candidate).strip().lower()
    if normalized.startswith("en"):
        return "en"
    if normalized.startswith("fr"):
        return "fr"
    return default


def collect_profile_highlights(
    profile: Any,
    max_experiences: int = 3,
    max_skills: int = 12,
    max_languages: int = 4,
    max_soft_skills: int = 6,
) -> Dict[str, List[str]]:
    """Summarize key profile elements for prompts and fallbacks."""
    highlights: Dict[str, List[str] | str] = {
        "summary": "",
        "experiences": [],
        "skills": [],
        "languages": [],
        "soft_skills": [],
    }

    if profile is None:
        return highlights  # type: ignore[return-value]

    personal_info = getattr(profile, "extracted_personal_info", None) or {}
    if isinstance(personal_info, dict):
        summary = personal_info.get("summary")
        if isinstance(summary, str) and summary.strip():
            highlights["summary"] = summary.strip()
    if not highlights["summary"]:
        highlights["summary"] = _first_sentence_from_master(profile)

    experiences = getattr(profile, "extracted_experiences", None) or []
    if isinstance(experiences, list):
        for exp in experiences[:max_experiences]:
            if not isinstance(exp, dict):
                continue
            title = exp.get("title") or exp.get("job_title") or "Experience"
            company = exp.get("company") or exp.get("employer") or ""
            period = exp.get("period") or exp.get("dates") or ""
            line = title
            if company:
                line += f" chez {company}"
            if period:
                line += f" ({period})"
            highlight = ""
            achievements = exp.get("achievements")
            if isinstance(achievements, list) and achievements:
                first_item = achievements[0]
                if isinstance(first_item, str):
                    highlight = first_item
            elif isinstance(exp.get("description"), list) and exp.get("description"):
                first_desc = exp["description"][0]
                if isinstance(first_desc, str):
                    highlight = first_desc
            if highlight:
                line += f" : {highlight}"
            highlights["experiences"].append(line)

    skills = getattr(profile, "extracted_skills", None) or []
    skill_names: List[str] = []
    if isinstance(skills, list):
        for entry in skills:
            if isinstance(entry, dict):
                items = entry.get("items") or entry.get("skills_list") or []
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict):
                            name = item.get("name")
                            if isinstance(name, str):
                                skill_names.append(name)
                        elif isinstance(item, str):
                            skill_names.append(item)
            elif isinstance(entry, str):
                skill_names.append(entry)
    highlights["skills"] = skill_names[:max_skills]

    languages = getattr(profile, "extracted_languages", None) or []
    language_parts: List[str] = []
    if isinstance(languages, list):
        for lang in languages[:max_languages]:
            if isinstance(lang, dict):
                label = lang.get("language") or lang.get("name")
                level = lang.get("level")
                if isinstance(label, str) and isinstance(level, str):
                    language_parts.append(f"{label} ({level})")
                elif isinstance(label, str):
                    language_parts.append(label)
            elif isinstance(lang, str):
                language_parts.append(lang)
    highlights["languages"] = language_parts

    soft_skills = getattr(profile, "extracted_soft_skills", None) or []
    soft_skill_names: List[str] = []
    if isinstance(soft_skills, list):
        for entry in soft_skills:
            if isinstance(entry, dict):
                items = entry.get("items") or entry.get("skills_list") or []
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict):
                            name = item.get("name")
                            if isinstance(name, str):
                                soft_skill_names.append(name)
                        elif isinstance(item, str):
                            soft_skill_names.append(item)
            elif isinstance(entry, str):
                soft_skill_names.append(entry)
    highlights["soft_skills"] = soft_skill_names[:max_soft_skills]

    return highlights  # type: ignore[return-value]


def build_cover_letter_from_highlights(
    profile: Any,
    offer_data: Optional[Dict[str, Any]],
    highlights: Dict[str, List[str] | str],
    keywords: Optional[List[str]] = None,
    language: Optional[str] = None,
) -> str:
    """Compose a cover letter string from collected highlights."""
    offer = offer_data if isinstance(offer_data, dict) else {}
    resolved_language = language or resolve_cover_letter_language(profile, offer_data)
    lang_key = (resolved_language or "fr").strip().lower()
    language_key = "en" if lang_key.startswith("en") else "fr"

    default_job_title = "this role" if language_key == "en" else "ce poste"
    default_company = "your company" if language_key == "en" else "votre entreprise"
    name = getattr(profile, "name", None) or ("Candidate" if language_key == "en" else "Candidat")
    job_title = offer.get("job_title") or default_job_title
    company = offer.get("company") or default_company

    summary_default = (
        "Motivated professional ready to create impact quickly."
        if language_key == "en"
        else "Professionnel motive pret a contribuer rapidement."
    )
    summary_value = highlights.get("summary") if isinstance(highlights, dict) else None
    summary_text = summary_default
    if isinstance(summary_value, str) and summary_value.strip():
        summary_text = summary_value.strip()

    subject_line = (
        f"Subject: Application for the {job_title} position"
        if language_key == "en"
        else f"Objet: Candidature pour le poste de {job_title}"
    )
    greeting = "Dear Hiring Manager," if language_key == "en" else "Madame, Monsieur,"
    intro_line = (
        f"{summary_text} I am eager to bring this expertise to {company}."
        if language_key == "en"
        else f"{summary_text} Je souhaite mettre cette expertise au service de {company}."
    )
    experience_heading = "Relevant experience:" if language_key == "en" else "Experiences pertinentes :"
    default_experience_line = (
        "- Highlight a key experience that matches the role."
        if language_key == "en"
        else "- Selectionnez une experience cle adaptee au poste."
    )

    skills_template = "Key skills: {}." if language_key == "en" else "Competences majeures : {}."
    soft_skills_template = "Strengths: {}." if language_key == "en" else "Qualites personnelles : {}."
    languages_template = "Languages: {}." if language_key == "en" else "Langues : {}."
    keywords_template = (
        "I am comfortable with {}." if language_key == "en" else "Je maitrise notamment {}."
    )
    default_fragment = (
        "My skills and mindset align well with the expectations outlined in the job description."
        if language_key == "en"
        else "Mes competences et mon sens du travail en equipe correspondent aux attentes de votre annonce."
    )

    parts: List[str] = [subject_line, "", greeting, "", intro_line, "", experience_heading]

    experiences = highlights.get("experiences") if isinstance(highlights, dict) else []
    if isinstance(experiences, list) and experiences:
        parts.extend(f"- {line}" for line in experiences if isinstance(line, str))
    else:
        parts.append(default_experience_line)

    fragments: List[str] = []
    skills = highlights.get("skills") if isinstance(highlights, dict) else []
    if isinstance(skills, list) and skills:
        skill_items = [str(item) for item in skills[:8] if isinstance(item, str)]
        if skill_items:
            fragments.append(skills_template.format(", ".join(skill_items)))
    soft_skills = highlights.get("soft_skills") if isinstance(highlights, dict) else []
    if isinstance(soft_skills, list) and soft_skills:
        soft_items = [str(item) for item in soft_skills[:8] if isinstance(item, str)]
        if soft_items:
            fragments.append(soft_skills_template.format(", ".join(soft_items)))
    languages_list = highlights.get("languages") if isinstance(highlights, dict) else []
    if isinstance(languages_list, list) and languages_list:
        lang_items = [str(item) for item in languages_list[:6] if isinstance(item, str)]
        if lang_items:
            fragments.append(languages_template.format(", ".join(lang_items)))

    extracted_keywords = keywords
    if extracted_keywords is None and isinstance(offer, dict):
        analysis_value = offer.get("analysis")
        if isinstance(analysis_value, dict):
            collected: List[str] = []
            for key in ("keywords", "skills", "tech_keywords", "soft_keywords", "tools"):
                value = analysis_value.get(key)
                if isinstance(value, list):
                    collected.extend(str(item) for item in value if item)
                elif isinstance(value, str):
                    collected.extend(part.strip() for part in value.split(",") if part.strip())
            if collected:
                extracted_keywords = collected
    if isinstance(extracted_keywords, list) and extracted_keywords:
        keyword_items = [str(item) for item in extracted_keywords if isinstance(item, str)]
        if keyword_items:
            fragments.append(keywords_template.format(", ".join(keyword_items[:8])))

    if fragments:
        parts.extend(["", " ".join(fragments)])
    else:
        parts.extend(["", default_fragment])

    if language_key == "en":
        closing_section = [
            "",
            "I would welcome the opportunity to discuss how I can support your goals in more detail.",
            "Thank you for your consideration. I am available for an interview at your convenience.",
            "",
            "Sincerely,",
            name,
        ]
    else:
        closing_section = [
            "",
            "Je serais heureux de vous exposer de vive voix la valeur que je peux apporter a vos projets.",
            "Je reste a votre disposition pour un entretien et vous remercie pour votre consideration.",
            "",
            "Cordialement,",
            name,
        ]

    parts.extend(closing_section)
    return "\n".join(section for section in parts if section is not None)

