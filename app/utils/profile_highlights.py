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
    from .cover_letter_fallback import generate_fallback_cover_letter

    offer = offer_data if isinstance(offer_data, dict) else {}
    resolved_language = language or resolve_cover_letter_language(profile, offer)

    def keyword_collector() -> List[str]:
        if isinstance(keywords, list):
            return [str(item) for item in keywords if str(item or "").strip()]
        analysis_value = offer.get("analysis") if isinstance(offer, dict) else None
        if not isinstance(analysis_value, dict):
            return []
        collected: List[str] = []
        for key in ("keywords", "skills", "tech_keywords", "soft_keywords", "tools"):
            value = analysis_value.get(key)
            if isinstance(value, list):
                collected.extend(str(item) for item in value if str(item or "").strip())
            elif isinstance(value, str):
                collected.extend(part.strip() for part in value.split(",") if part.strip())
        return collected

    return generate_fallback_cover_letter(
        profile_data=profile,
        offer_data=offer,
        language_code=resolved_language,
        offer_keywords_collector=keyword_collector,
        include_experience_paragraph=True,
        reason="profile_highlights_fallback",
    )

