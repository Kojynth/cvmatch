"""Helpers to render CVJSON into cv_data, markdown, and HTML."""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlparse
from typing import Any, Dict, List, Optional

from ..controllers.export_manager import ExportManager
from .language_policy import text_matches_target_language


_CONTACT_PLACEHOLDER_LABEL_RE = re.compile(r"^(?:lien|link)\s*\d*$", re.IGNORECASE)
_URL_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.\-]*://", re.IGNORECASE)
_PHONE_LIKE_RE = re.compile(r"^\+?[\d\s().\-]{6,}$")
_EMAIL_LIKE_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_SAFE_CONTACT_SCHEMES = {"http", "https", "mailto", "tel"}
_RENDER_POSITIONING_PATTERNS = {
    "fr": (
        re.compile(
            r"^\s*Atouts\s+pertinents(?:\s+pour\s+(?P<company>.+?))?\s*[:\-]\s*(?P<terms>.+?)\.\s*$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^\s*Profil\s+pertinent(?:\s+pour\s+(?P<company>.+?))?\s+gr(?:a|â)ce\s+[aà]\s+(?P<terms>.+?)\.\s*$",
            re.IGNORECASE,
        ),
    ),
    "en": (
        re.compile(
            r"^\s*Relevant\s+strengths(?:\s+for\s+(?P<company>.+?))?\s+include\s+(?P<terms>.+?)\.\s*$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^\s*Profile\s+aligned(?:\s+with\s+(?P<company>.+?))?\s+through\s+(?P<terms>.+?)\.\s*$",
            re.IGNORECASE,
        ),
    ),
}


def _restore_display_acronyms(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip()).strip()
    if not text:
        return ""
    return re.sub(
        r"\b(ai|ml|api|qa|sql|ui|ux|bi|it)\b",
        lambda match: str(match.group(1) or "").upper(),
        text,
        flags=re.IGNORECASE,
    )


def _normalize_description_line(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    text = re.sub(r"[\W_]+", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _split_summary_sentences(value: Any) -> List[str]:
    raw = str(value or "").strip()
    if not raw:
        return []
    return [
        re.sub(r"\s+", " ", sentence).strip()
        for sentence in re.split(r"(?<=[.!?])\s+", raw)
        if str(sentence or "").strip()
    ]


def _normalize_sentence_key(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip()).strip()
    if not text:
        return ""
    text = re.sub(r"[.!?]+$", "", text)
    return text.casefold()


def _match_render_positioning_sentence(
    value: Any,
    *,
    language_code: str,
) -> re.Match[str] | None:
    text = re.sub(r"\s+", " ", str(value or "").strip()).strip()
    if not text:
        return None
    lang_key = "en" if str(language_code or "").lower().startswith("en") else "fr"
    for pattern in _RENDER_POSITIONING_PATTERNS.get(lang_key, ()):
        match = pattern.match(text)
        if match:
            return match
    return None


def _strip_render_positioning_sentences(value: Any, *, language_code: str) -> str:
    kept: List[str] = []
    for sentence in _split_summary_sentences(value):
        if _match_render_positioning_sentence(sentence, language_code=language_code):
            continue
        kept.append(sentence)
    return " ".join(kept).strip()


def _text_contains_sentence(text: Any, sentence: Any) -> bool:
    target = _normalize_sentence_key(sentence)
    if not target:
        return False
    return any(
        _normalize_sentence_key(item) == target
        for item in _split_summary_sentences(text)
    )


def _dedupe_sentences(text: Any) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    deduped: List[str] = []
    seen: set[str] = set()
    for cleaned in _split_summary_sentences(raw):
        if not cleaned:
            continue
        norm = _normalize_sentence_key(cleaned)
        if norm in seen:
            continue
        seen.add(norm)
        deduped.append(cleaned)
    return " ".join(deduped).strip()


def _build_render_positioning_sentence(
    terms: str,
    *,
    company: str = "",
    language_code: str = "fr",
) -> str:
    cleaned_terms = re.sub(r"\s+", " ", str(terms or "").strip(" ,;:-"))
    company_name = _restore_display_acronyms(str(company or "").strip(" ,;:-"))
    if not cleaned_terms:
        return ""
    is_en = str(language_code or "").lower().startswith("en")
    if is_en:
        if company_name:
            return f"Profile aligned with {company_name} through {cleaned_terms}."
        return f"Profile aligned through {cleaned_terms}."
    if company_name:
        return f"Profil pertinent pour {company_name} grâce à {cleaned_terms}."
    return f"Profil pertinent grâce à {cleaned_terms}."


def _extract_render_positioning_sentence(value: Any, *, language_code: str) -> str:
    for sentence in _split_summary_sentences(value):
        match = _match_render_positioning_sentence(
            sentence,
            language_code=language_code,
        )
        if not match:
            continue
        return _build_render_positioning_sentence(
            match.group("terms") or "",
            company=match.group("company") or "",
            language_code=language_code,
        )
    return ""


def _strip_ats_unsafe_bullet_markers(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"^[\s\-\*\u2022\u25aa\u279c\u2713\u25ba\u25b8\u25e6\u2023]+", "", text)
    return text.strip()


def _dedupe_description_lines(lines: List[str]) -> List[str]:
    deduped: List[str] = []
    seen_norms: List[str] = []
    for raw in lines or []:
        text = str(raw or "").strip()
        if not text:
            continue
        norm = _normalize_description_line(text)
        if not norm:
            continue
        duplicate = False
        for idx, seen in enumerate(seen_norms):
            if norm == seen:
                duplicate = True
                break
            if len(norm) >= 24 and norm in seen:
                duplicate = True
                break
            if len(seen) >= 24 and seen in norm:
                deduped[idx] = text
                seen_norms[idx] = norm
                duplicate = True
                break
        if duplicate:
            continue
        deduped.append(text)
        seen_norms.append(norm)
    return deduped


def _normalize_language_key(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    folded = (
        unicodedata.normalize("NFKD", text)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
        .strip()
    )
    if not folded:
        return ""
    folded = re.sub(r"[^a-z0-9+#]+", " ", folded).strip()
    aliases = {
        "en": "english",
        "eng": "english",
        "english": "english",
        "anglais": "english",
        "fr": "french",
        "fra": "french",
        "french": "french",
        "francais": "french",
        "de": "german",
        "ger": "german",
        "german": "german",
        "allemand": "german",
        "es": "spanish",
        "spa": "spanish",
        "spanish": "spanish",
        "espagnol": "spanish",
        "it": "italian",
        "ita": "italian",
        "italian": "italian",
        "italien": "italian",
        "pt": "portuguese",
        "por": "portuguese",
        "portuguese": "portuguese",
        "portugais": "portuguese",
        "ja": "japanese",
        "jp": "japanese",
        "jpn": "japanese",
        "japanese": "japanese",
        "japonais": "japanese",
        "zh": "chinese",
        "cn": "chinese",
        "chinese": "chinese",
        "chinois": "chinese",
        "mandarin": "chinese",
        "ru": "russian",
        "rus": "russian",
        "russian": "russian",
        "russe": "russian",
        "ar": "arabic",
        "ara": "arabic",
        "arabic": "arabic",
        "arabe": "arabic",
    }
    if folded in aliases:
        return aliases[folded]
    compact = folded.replace(" ", "")
    if compact in aliases:
        return aliases[compact]
    if compact.startswith("fran") and compact.endswith("ais"):
        return "french"
    if compact.startswith("angl"):
        return "english"
    if compact.startswith("japon"):
        return "japanese"
    if compact.startswith("allem"):
        return "german"
    if compact.startswith("espagn"):
        return "spanish"
    return folded


def _display_language_name(value: Any, *, is_en: bool) -> str:
    raw = str(value or "").strip()
    key = _normalize_language_key(raw)
    labels_en = {
        "english": "English",
        "french": "French",
        "german": "German",
        "spanish": "Spanish",
        "italian": "Italian",
        "portuguese": "Portuguese",
        "japanese": "Japanese",
        "chinese": "Chinese",
        "russian": "Russian",
        "arabic": "Arabic",
    }
    labels_fr = {
        "english": "Anglais",
        "french": "Français",
        "german": "Allemand",
        "spanish": "Espagnol",
        "italian": "Italien",
        "portuguese": "Portugais",
        "japanese": "Japonais",
        "chinese": "Chinois",
        "russian": "Russe",
        "arabic": "Arabe",
    }
    if key in labels_en:
        return labels_en[key] if is_en else labels_fr[key]
    return raw


def _display_language_level(value: Any, *, is_en: bool) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    cefr_match = re.search(r"\b([ABC][12])\b", raw.upper())
    if not cefr_match:
        return raw
    level = cefr_match.group(1)
    fr_label = {
        "A1": "Débutant",
        "A2": "Élémentaire",
        "B1": "Intermédiaire",
        "B2": "Intermédiaire supérieur",
        "C1": "Avancé",
        "C2": "Maîtrise",
    }
    en_label = {
        "A1": "Beginner",
        "A2": "Elementary",
        "B1": "Intermediate",
        "B2": "Upper-intermediate",
        "C1": "Advanced",
        "C2": "Proficient",
    }
    label = en_label[level] if is_en else fr_label[level]
    return f"{level} - {label}"


def _clean_render_summary(value: Any, *, language_code: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        from .cv_summary_adaptation import (
            strip_deterministic_summary_appendices,
            strip_positioning_sentences,
        )

        text = strip_deterministic_summary_appendices(text)
        text = strip_positioning_sentences(text, language_code=language_code)
    except Exception:
        pass
    text = _strip_render_positioning_sentences(text, language_code=language_code)
    text = re.sub(r"\s+", " ", text).strip()
    return _dedupe_sentences(text)


def _build_target_role_line(
    job_title: Any,
    company: Any,
    *,
    is_en: bool,
) -> str:
    parts = [_restore_display_acronyms(str(part or "").strip()) for part in (job_title, company)]
    parts = [part for part in parts if part]
    if not parts:
        return ""
    joined = " | ".join(parts)
    prefix = "Target role" if is_en else "Poste vise"
    return f"{prefix}: {joined}"


def _normalize_contact_href(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if _EMAIL_LIKE_RE.match(text):
        return f"mailto:{text}"
    if text.lower().startswith("mailto:"):
        return text
    if text.lower().startswith("tel:"):
        return text
    if _PHONE_LIKE_RE.match(text):
        digits = re.sub(r"[^\d+]+", "", text)
        return f"tel:{digits}" if digits else ""
    if _URL_SCHEME_RE.match(text):
        parsed = urlparse(text)
        if parsed.scheme.lower() not in _SAFE_CONTACT_SCHEMES:
            return ""
        return text
    return f"https://{text.lstrip('/')}"


def _display_contact_value(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    href = _normalize_contact_href(text)
    if href.startswith("mailto:"):
        return href[len("mailto:") :]
    if href.startswith("tel:"):
        return text
    parsed = urlparse(href)
    display = f"{parsed.netloc}{parsed.path}".strip("/")
    if parsed.query:
        display = f"{display}?{parsed.query}" if display else parsed.query
    return display or text


def _normalize_contact_label(label: Any, url: Any, *, idx: int, is_en: bool) -> str:
    raw_label = str(label or "").strip()
    href = _normalize_contact_href(url)
    parsed = urlparse(href) if href else None
    host = parsed.netloc.lower() if parsed else ""
    if href.startswith("mailto:"):
        return "Email"
    if href.startswith("tel:"):
        return "Phone" if is_en else "Telephone"
    if "linkedin.com" in host:
        return "LinkedIn"
    if "github.com" in host:
        return "GitHub"
    if not raw_label or _CONTACT_PLACEHOLDER_LABEL_RE.match(raw_label):
        if host:
            host_label = host.replace("www.", "").split(".")[0].strip()
            return host_label.capitalize() if host_label else f"Link {idx}"
        return f"Link {idx}" if is_en else f"Lien {idx}"
    return raw_label


def _build_contact_methods(
    *,
    email: Any,
    phone: Any,
    linkedin_url: Any,
    location: Any,
    links: List[Dict[str, str]],
    is_en: bool,
) -> List[Dict[str, str]]:
    methods: List[Dict[str, str]] = []
    seen: set[str] = set()

    def _append(kind: str, label: str, value: Any, href: Any = "") -> None:
        display_value = str(value or "").strip()
        resolved_href = str(href or "").strip() or _normalize_contact_href(display_value)
        if not display_value:
            return
        if kind != "location" and not resolved_href:
            return
        dedupe_key = (resolved_href or display_value).strip().lower()
        if dedupe_key and dedupe_key in seen:
            return
        if dedupe_key:
            seen.add(dedupe_key)
        methods.append(
            {
                "kind": kind,
                "label": label,
                "value": display_value,
                "display_value": _display_contact_value(display_value),
                "href": resolved_href,
            }
        )

    _append("email", "Email", email)
    _append("phone", "Phone" if is_en else "Telephone", phone)
    _append("linkedin", "LinkedIn", linkedin_url)

    for idx, link in enumerate(links or [], start=1):
        if not isinstance(link, dict):
            continue
        url = str(link.get("url") or "").strip()
        if not url:
            continue
        label = _normalize_contact_label(link.get("label"), url, idx=idx, is_en=is_en)
        kind = label.lower().replace(" ", "_")
        _append(kind, label, url)

    location_text = str(location or "").strip()
    if location_text:
        methods.append(
            {
                "kind": "location",
                "label": "Location" if is_en else "Localisation",
                "value": location_text,
                "display_value": location_text,
                "href": "",
            }
        )

    return methods


def cv_json_to_cv_data(
    cv_json: Dict[str, Any], language: Optional[str] = None
) -> Dict[str, Any]:
    contact = cv_json.get("contact")
    if not isinstance(contact, dict):
        contact = {}
    contact_links: List[Dict[str, str]] = []
    raw_contact_links = contact.get("links")
    if isinstance(raw_contact_links, list):
        for idx, entry in enumerate(raw_contact_links, start=1):
            label = ""
            url = ""
            if isinstance(entry, dict):
                label = str(
                    entry.get("label") or entry.get("platform") or f"Lien {idx}"
                ).strip()
                url = str(entry.get("url") or entry.get("link") or "").strip()
            elif isinstance(entry, str):
                label = f"Lien {idx}"
                url = entry.strip()
            if not url:
                continue
            contact_links.append({"label": label or f"Lien {idx}", "url": url})
    lang = (language or "").strip().lower()
    is_en = lang.startswith("en")
    labels = {
        "contact": "Contact" if is_en else "Contact",
        "profile": "Profile" if is_en else "Profil",
        "experience": "Experience" if is_en else "Experience",
        "skills": "Skills" if is_en else "Compétences",
        "education": "Education" if is_en else "Formation",
        "projects": "Projects" if is_en else "Projets",
        "languages": "Languages" if is_en else "Langues",
        "certifications": "Certifications" if is_en else "Certifications",
        "interests": "Interests" if is_en else "Centres d'intérêt",
    }

    def _entry_recency_rank(entry: Dict[str, Any]) -> int:
        def _rank(raw: Any) -> int:
            text = str(raw or "").strip()
            if not text:
                return 0
            lowered = text.casefold()
            if any(token in lowered for token in ("present", "current", "en cours", "aujourd")):
                return 999912
            month_year = re.search(r"\b(?P<m>0[1-9]|1[0-2])/(?P<y>\d{4})\b", text)
            if month_year:
                return int(month_year.group("y")) * 100 + int(month_year.group("m"))
            year = re.search(r"\b(?P<y>19\d{2}|20\d{2})\b", text)
            if year:
                return int(year.group("y")) * 100 + 12
            return 0

        if not isinstance(entry, dict):
            return 0
        return _rank(entry.get("end_date")) or _rank(entry.get("start_date")) or _rank(entry.get("year"))
    skills_section: List[Dict[str, Any]] = []
    for category in cv_json.get("skills", []) or []:
        if not isinstance(category, dict):
            continue
        items = [
            item
            for item in (category.get("items") or [])
            if isinstance(item, str)
            and item.strip()
            and text_matches_target_language(item, lang or "fr")
        ]
        skills_section.append(
            {
                "category": category.get("category") or "Skills",
                "skills_list": [{"name": item, "level": None} for item in items],
            }
        )

    experience_section = []
    for item in sorted(
        [item for item in (cv_json.get("experience") or []) if isinstance(item, dict)],
        key=_entry_recency_rank,
        reverse=True,
    ):
        description: List[str] = []

        def _append_experience_line(value: Any) -> None:
            cleaned = _strip_ats_unsafe_bullet_markers(value)
            normalized = re.sub(
                r"\s+",
                " ",
                str(cleaned or "").strip().lower(),
            )
            if not cleaned:
                return
            if not text_matches_target_language(cleaned, lang or "fr"):
                return
            if normalized in {
                "delivered key contributions in this role.",
                "contributions principales realisees sur ce poste.",
            }:
                return
            if normalized.startswith("delivered key contributions as "):
                return
            description.append(cleaned)

        summary = item.get("summary")
        if isinstance(summary, str) and summary.strip():
            _append_experience_line(summary)
        for highlight in item.get("highlights", []) or []:
            if isinstance(highlight, str) and highlight.strip():
                _append_experience_line(highlight)
        raw_description = item.get("description")
        if isinstance(raw_description, str) and raw_description.strip():
            _append_experience_line(raw_description)
        elif isinstance(raw_description, list):
            for value in raw_description:
                if isinstance(value, str) and value.strip():
                    _append_experience_line(value)
        description = _dedupe_description_lines(description)[:6]
        experience_section.append(
            {
                "title": item.get("title") or "",
                "company": item.get("company") or "",
                "start_date": item.get("start_date") or "",
                "end_date": item.get("end_date") or "",
                "duration": item.get("duration") or "",
                "location": re.sub(
                    r"\s+-\s+",
                    ", ",
                    str(item.get("location") or ""),
                ),
                "description": description,
            }
        )

    education_section = []
    for item in sorted(
        [item for item in (cv_json.get("education") or []) if isinstance(item, dict)],
        key=_entry_recency_rank,
        reverse=True,
    ):
        year = item.get("end_date") or item.get("start_date") or ""
        details = [
            detail
            for detail in (item.get("details") or [])
            if isinstance(detail, str)
            and detail.strip()
            and text_matches_target_language(detail, lang or "fr")
        ]
        education_section.append(
            {
                "degree": item.get("degree") or "",
                "institution": item.get("school") or "",
                "year": year,
                "description": details,
            }
        )

    languages_section = []
    for item in cv_json.get("languages", []) or []:
        if not isinstance(item, dict):
            continue
        language_name = _display_language_name(item.get("language") or "", is_en=is_en)
        level_name = _display_language_level(item.get("level") or "", is_en=is_en)
        certification = str(item.get("certification") or "").strip()
        if certification:
            level_name = f"{level_name} ({certification})" if level_name else certification
        languages_section.append(
            {
                "name": language_name,
                "level": level_name,
                "certification": certification,
            }
        )

    projects_section = []
    for item in cv_json.get("projects", []) or []:
        if not isinstance(item, dict):
            continue
        projects_section.append(
            {
                "name": item.get("name") or "",
                "description": (
                    item.get("description") or ""
                    if text_matches_target_language(
                        item.get("description") or "",
                        lang or "fr",
                    )
                    else ""
                ),
                "technologies": item.get("technologies") or "",
                "url": item.get("url") or "",
                "duration": item.get("duration") or "",
            }
        )

    certifications_section = []
    for item in cv_json.get("certifications", []) or []:
        if not isinstance(item, dict):
            continue
        cert_name = item.get("name") or ""
        try:
            from .certification_normalizer import normalize_certification_text

            cert_name = normalize_certification_text(str(cert_name or ""))
        except Exception:
            cert_name = str(cert_name or "").strip()
        certifications_section.append(
            {
                "name": cert_name,
                "organization": item.get("organization") or "",
                "date": item.get("date") or "",
                "url": item.get("url") or "",
            }
        )

    soft_skills_section: List[str] = []
    for item in cv_json.get("soft_skills", []) or []:
        if isinstance(item, dict):
            name = str(item.get("name") or item.get("label") or "").strip()
        else:
            name = str(item or "").strip()
        if name and text_matches_target_language(name, lang or "fr"):
            soft_skills_section.append(name)

    cleaned_summary = _clean_render_summary(
        cv_json.get("summary") or "",
        language_code=lang or "fr",
    )
    positioning_summary = _extract_render_positioning_sentence(
        cv_json.get("summary") or "",
        language_code=lang or "fr",
    )
    contact_methods = _build_contact_methods(
        email=contact.get("email") or "",
        phone=contact.get("phone") or "",
        linkedin_url=contact.get("linkedin_url") or "",
        location=contact.get("location") or "",
        links=contact_links,
        is_en=is_en,
    )
    job_title = cv_json.get("target_job_title") or ""
    company = _restore_display_acronyms(cv_json.get("target_company") or "")
    target_role_line = _build_target_role_line(job_title, company, is_en=is_en)

    return {
        "name": contact.get("full_name") or "",
        "email": contact.get("email") or "",
        "phone": contact.get("phone") or "",
        "linkedin_url": contact.get("linkedin_url") or "",
        "location": contact.get("location") or "",
        "links": contact_links,
        "contact_methods": contact_methods,
        "job_title": job_title,
        "company": company,
        "target_role_line": target_role_line,
        "profile_summary": (
            cleaned_summary
            if cleaned_summary and text_matches_target_language(cleaned_summary, lang or "fr")
            else ""
        ),
        "profile_positioning_sentence": (
            positioning_summary
            if positioning_summary
            and text_matches_target_language(positioning_summary, lang or "fr")
            and not _text_contains_sentence(cleaned_summary, positioning_summary)
            else ""
        ),
        "experience": experience_section,
        "education": education_section,
        "skills": skills_section,
        "soft_skills": _dedupe_description_lines(soft_skills_section),
        "languages": languages_section,
        "projects": projects_section,
        "certifications": certifications_section,
        "interests": cv_json.get("interests") or [],
        "labels": labels,
        "language": "en" if is_en else "fr",
    }


def cv_json_to_markdown(cv_json: Dict[str, Any], language: Optional[str] = None) -> str:
    data = cv_json_to_cv_data(cv_json, language=language)
    lines: List[str] = []

    labels = data.get("labels") or {}
    labels = {
        "contact": labels.get("contact") or "Contact",
        "profile": labels.get("profile") or "Profile",
        "experience": labels.get("experience") or "Experience",
        "skills": labels.get("skills") or "Skills",
        "education": labels.get("education") or "Education",
        "projects": labels.get("projects") or "Projects",
        "languages": labels.get("languages") or "Languages",
        "certifications": labels.get("certifications") or "Certifications",
    }

    name = data.get("name") or ""
    if name:
        lines.append(f"# {name}")

    job_title = data.get("job_title") or ""
    company = data.get("company") or ""
    target_role_line = data.get("target_role_line") or ""
    if target_role_line:
        lines.append(f"## {target_role_line}")
    elif job_title or company:
        title_line = " | ".join([part for part in [job_title, company] if part])
        lines.append(f"## {title_line}")

    contact_labels = {
        "email": "Email" if data.get("language") == "en" else "Email",
        "phone": "Phone" if data.get("language") == "en" else "Telephone",
        "linkedin": "LinkedIn",
        "location": "Location" if data.get("language") == "en" else "Localisation",
    }
    contact_lines: List[str] = []
    for method in data.get("contact_methods") or []:
        if not isinstance(method, dict):
            continue
        label = str(method.get("label") or "").strip()
        value = str(method.get("display_value") or method.get("value") or "").strip()
        if label and value:
            contact_lines.append(f"- {label}: {value}")
    if contact_lines:
        lines.append(f"## {labels['contact']}")
        lines.extend(contact_lines)

    summary = data.get("profile_summary") or ""
    positioning = data.get("profile_positioning_sentence") or ""
    if summary:
        lines.append("")
        lines.append(f"## {labels['profile']}")
        lines.append(summary.strip())
        if positioning:
            lines.append(positioning.strip())
    elif positioning:
        lines.append("")
        lines.append(f"## {labels['profile']}")
        lines.append(positioning.strip())

    if data.get("experience"):
        lines.append("")
        lines.append(f"## {labels['experience']}")
        for exp in data["experience"]:
            title = exp.get("title") or ""
            company = exp.get("company") or ""
            period = " - ".join(
                [part for part in [exp.get("start_date"), exp.get("end_date")] if part]
            )
            duration = exp.get("duration") or ""
            if period and duration:
                period = f"{period} ({duration})"
            elif duration:
                period = str(duration)
            lines.append(f"### {title}".strip())
            meta = " | ".join([part for part in [company, period] if part])
            if meta:
                lines.append(f"**{meta}**")
            for item in exp.get("description") or []:
                lines.append(f"- {item}")

    if data.get("skills"):
        lines.append("")
        lines.append(f"## {labels['skills']}")
        for block in data["skills"]:
            category = block.get("category") or labels["skills"]
            items = block.get("skills_list") or []
            names = [item.get("name") for item in items if isinstance(item, dict)]
            if names:
                lines.append(f"- {category}: {', '.join(names)}")
        soft_skills = [item for item in data.get("soft_skills") or [] if isinstance(item, str)]
        if soft_skills:
            prefix = "Strengths" if data.get("language") == "en" else "Atouts"
            lines.append(f"- {prefix}: {', '.join(soft_skills)}")

    if data.get("education"):
        lines.append("")
        lines.append(f"## {labels['education']}")
        for edu in data["education"]:
            degree = edu.get("degree") or ""
            school = edu.get("institution") or ""
            year = edu.get("year") or ""
            header = " | ".join([part for part in [degree, school, year] if part])
            if header:
                lines.append(f"**{header}**")
            for detail in edu.get("description") or []:
                lines.append(f"- {detail}")

    if data.get("projects"):
        lines.append("")
        lines.append(f"## {labels['projects']}")
        for proj in data["projects"]:
            name = proj.get("name") or ""
            duration = proj.get("duration") or ""
            header = f"### {name}"
            if duration:
                header += f"  _{duration}_"
            lines.append(header.strip())
            desc = proj.get("description") or ""
            if desc:
                lines.append(desc)

    if data.get("languages"):
        lines.append("")
        lines.append(f"## {labels['languages']}")
        for lang in data["languages"]:
            name = lang.get("name") or ""
            level = lang.get("level") or ""
            if name and level:
                lines.append(f"- {name}: {level}")
            elif name:
                lines.append(f"- {name}")

    if data.get("certifications"):
        lines.append("")
        lines.append(f"## {labels['certifications']}")
        for cert in data["certifications"]:
            name = cert.get("name") or ""
            org = cert.get("organization") or ""
            date = cert.get("date") or ""
            header = " | ".join([part for part in [name, org, date] if part])
            if header:
                lines.append(f"- {header}")

    return "\n".join(lines).strip() + "\n"


def cv_json_to_html(
    cv_json: Dict[str, Any], template: str = "modern", language: Optional[str] = None
) -> str:
    data = cv_json_to_cv_data(cv_json, language=language)
    export_manager = ExportManager()
    try:
        return export_manager.generate_html(data, template)
    except Exception:
        # Fallback: minimal HTML rendering.
        markdown = cv_json_to_markdown(cv_json, language=language)
        html_lines = ["<html><body>"]
        for line in markdown.splitlines():
            if line.startswith("# "):
                html_lines.append(f"<h1>{line[2:].strip()}</h1>")
            elif line.startswith("## "):
                html_lines.append(f"<h2>{line[3:].strip()}</h2>")
            elif line.startswith("### "):
                html_lines.append(f"<h3>{line[4:].strip()}</h3>")
            elif line.startswith("- "):
                html_lines.append(f"<p>{line[2:].strip()}</p>")
            elif line.startswith("**") and line.endswith("**"):
                html_lines.append(f"<p><strong>{line[2:-2]}</strong></p>")
            elif line.strip():
                html_lines.append(f"<p>{line}</p>")
        html_lines.append("</body></html>")
        return "\n".join(html_lines)
