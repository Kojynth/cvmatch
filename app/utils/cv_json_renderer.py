"""Helpers to render CVJSON into cv_data, markdown, and HTML."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..controllers.export_manager import ExportManager


def cv_json_to_cv_data(
    cv_json: Dict[str, Any], language: Optional[str] = None
) -> Dict[str, Any]:
    contact = cv_json.get("contact") or {}
    lang = (language or "").strip().lower()
    is_en = lang.startswith("en")
    labels = {
        "contact": "Contact" if is_en else "Contact",
        "profile": "Profile" if is_en else "Profil",
        "experience": "Experience" if is_en else "Experience",
        "skills": "Skills" if is_en else "Competences",
        "education": "Education" if is_en else "Formation",
        "projects": "Projects" if is_en else "Projets",
        "languages": "Languages" if is_en else "Langues",
        "certifications": "Certifications" if is_en else "Certifications",
        "interests": "Interests" if is_en else "Centres d'interet",
    }
    skills_section: List[Dict[str, Any]] = []
    for category in cv_json.get("skills", []) or []:
        if not isinstance(category, dict):
            continue
        items = [item for item in (category.get("items") or []) if isinstance(item, str)]
        skills_section.append(
            {
                "category": category.get("category") or "Skills",
                "skills_list": [{"name": item, "level": None} for item in items],
            }
        )

    experience_section = []
    for item in cv_json.get("experience", []) or []:
        if not isinstance(item, dict):
            continue
        description: List[str] = []
        summary = item.get("summary")
        if isinstance(summary, str) and summary.strip():
            description.append(summary.strip())
        for highlight in item.get("highlights", []) or []:
            if isinstance(highlight, str) and highlight.strip():
                description.append(highlight.strip())
        experience_section.append(
            {
                "title": item.get("title") or "",
                "company": item.get("company") or "",
                "start_date": item.get("start_date") or "",
                "end_date": item.get("end_date") or "",
                "location": item.get("location") or "",
                "description": description,
            }
        )

    education_section = []
    for item in cv_json.get("education", []) or []:
        if not isinstance(item, dict):
            continue
        year = item.get("end_date") or item.get("start_date") or ""
        education_section.append(
            {
                "degree": item.get("degree") or "",
                "institution": item.get("school") or "",
                "year": year,
                "description": item.get("details") or [],
            }
        )

    languages_section = []
    for item in cv_json.get("languages", []) or []:
        if not isinstance(item, dict):
            continue
        languages_section.append(
            {
                "name": item.get("language") or "",
                "level": item.get("level") or "",
            }
        )

    projects_section = []
    for item in cv_json.get("projects", []) or []:
        if not isinstance(item, dict):
            continue
        projects_section.append(
            {
                "name": item.get("name") or "",
                "description": item.get("description") or "",
                "technologies": item.get("technologies") or "",
                "url": item.get("url") or "",
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
        "job_title": cv_json.get("target_job_title") or "",
        "company": cv_json.get("target_company") or "",
        "profile_summary": cv_json.get("summary") or "",
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
    if job_title:
        lines.append(f"## {job_title}")

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
            lines.append(f"### {name}".strip())
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
