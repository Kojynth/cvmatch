"""Helpers to render CVJSON into cv_data, markdown, and HTML."""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional

from ..controllers.export_manager import ExportManager
from .language_policy import text_matches_target_language


def _normalize_description_line(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    text = re.sub(r"[\W_]+", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


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
        for seen in seen_norms:
            if norm == seen:
                duplicate = True
                break
            if len(norm) >= 40 and norm in seen:
                duplicate = True
                break
            if len(seen) >= 40 and seen in norm:
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
        summary = item.get("summary")
        if isinstance(summary, str) and summary.strip():
            cleaned_summary = _strip_ats_unsafe_bullet_markers(summary)
            normalized_summary = re.sub(
                r"\s+",
                " ",
                str(cleaned_summary or "").strip().lower(),
            )
            if cleaned_summary and text_matches_target_language(
                cleaned_summary,
                lang or "fr",
            ) and normalized_summary not in {
                "delivered key contributions in this role.",
                "contributions principales realisees sur ce poste.",
            } and not normalized_summary.startswith("delivered key contributions as "):
                description.append(cleaned_summary)
        for highlight in item.get("highlights", []) or []:
            if isinstance(highlight, str) and highlight.strip():
                cleaned_highlight = _strip_ats_unsafe_bullet_markers(highlight)
                if cleaned_highlight and text_matches_target_language(
                    cleaned_highlight,
                    lang or "fr",
                ):
                    description.append(cleaned_highlight)
        description = _dedupe_description_lines(description)[:4]
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
        certifications_section.append(
            {
                "name": item.get("name") or "",
                "organization": item.get("organization") or "",
                "date": item.get("date") or "",
                "url": item.get("url") or "",
            }
        )

    return {
        "name": contact.get("full_name") or "",
        "email": contact.get("email") or "",
        "phone": contact.get("phone") or "",
        "linkedin_url": contact.get("linkedin_url") or "",
        "location": contact.get("location") or "",
        "links": contact_links,
        "job_title": cv_json.get("target_job_title") or "",
        "company": cv_json.get("target_company") or "",
        "profile_summary": (
            cv_json.get("summary") or ""
            if text_matches_target_language(cv_json.get("summary") or "", lang or "fr")
            else ""
        ),
        "experience": experience_section,
        "education": education_section,
        "skills": skills_section,
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
    if job_title or company:
        title_line = " | ".join([part for part in [job_title, company] if part])
        lines.append(f"## {title_line}")

    contact_labels = {
        "email": "Email" if data.get("language") == "en" else "Email",
        "phone": "Phone" if data.get("language") == "en" else "Telephone",
        "linkedin": "LinkedIn",
        "location": "Location" if data.get("language") == "en" else "Localisation",
    }
    contact_lines: List[str] = []
    if data.get("email"):
        contact_lines.append(f"- {contact_labels['email']}: {data['email']}")
    if data.get("phone"):
        contact_lines.append(f"- {contact_labels['phone']}: {data['phone']}")
    if data.get("linkedin_url"):
        contact_lines.append(f"- {contact_labels['linkedin']}: {data['linkedin_url']}")
    if data.get("location"):
        contact_lines.append(f"- {contact_labels['location']}: {data['location']}")
    for link in data.get("links") or []:
        if not isinstance(link, dict):
            continue
        label = str(link.get("label") or "Lien").strip()
        url = str(link.get("url") or "").strip()
        if url:
            contact_lines.append(f"- {label}: {url}")
    if contact_lines:
        lines.append(f"## {labels['contact']}")
        lines.extend(contact_lines)

    summary = data.get("profile_summary") or ""
    if summary:
        lines.append("")
        lines.append(f"## {labels['profile']}")
        lines.append(summary.strip())

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
