"""Compatibility-safe round-trip helpers for profile JSON contracts."""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, Iterable, List

from ...utils.text_norm import normalize_text_for_ui
from .artifact_mappers import normalize_interests
from .personal_info import merge_personal_links, normalize_links


PERSONAL_INFO_FIELDS = ["full_name", "email", "phone", "linkedin_url", "location"]

SECTION_FIELDS: Dict[str, List[str]] = {
    "personal_info": PERSONAL_INFO_FIELDS,
    "experiences": [
        "title",
        "company",
        "start_date",
        "end_date",
        "location",
        "description",
        "source",
    ],
    "education": [
        "school",
        "degree",
        "field_of_study",
        "start_date",
        "end_date",
        "grade",
        "source",
    ],
    "skills": ["name", "level"],
    "soft_skills": ["name", "level"],
    "languages": ["language", "proficiency", "certification"],
    "projects": ["name", "url", "technologies", "description"],
    "certifications": ["name", "organization", "date", "url"],
    "publications": ["title", "authors", "journal", "date", "url"],
    "volunteering": ["organization", "role", "period", "description"],
    "awards": ["name", "organization", "date", "description"],
    "references": ["name", "title", "company", "email", "phone"],
    "interests": [],
}

PROFILE_SECTIONS = [
    "personal_info",
    "experiences",
    "education",
    "skills",
    "soft_skills",
    "languages",
    "projects",
    "certifications",
    "publications",
    "volunteering",
    "awards",
    "references",
    "interests",
]

LIST_SECTIONS = [section for section in PROFILE_SECTIONS if section != "personal_info"]

HEADER_TOKENS = {
    "experience",
    "experiences",
    "education",
    "formation",
    "formations",
    "competence",
    "competences",
    "skill",
    "skills",
    "project",
    "projects",
    "projet",
    "projets",
    "certification",
    "certifications",
    "language",
    "languages",
    "langue",
    "langues",
    "profil",
    "profile",
    "resume",
    "summary",
    "contact",
    "interet",
    "interets",
    "interest",
    "interests",
    "hobby",
    "hobbies",
    "award",
    "awards",
    "reference",
    "references",
    "volunteer",
    "volunteering",
    "publication",
    "publications",
}


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    try:
        return normalize_text_for_ui(text)
    except Exception:
        return text


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _normalize_for_match(text: Any) -> str:
    value = _clean_text(text)
    if not value:
        return ""
    lowered = value.lower()
    normalized = unicodedata.normalize("NFKD", lowered)
    stripped = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    stripped = re.sub(r"[^a-z0-9+./ ]+", " ", stripped)
    return " ".join(stripped.split())


def _looks_like_header(text: Any) -> bool:
    normalized = _normalize_for_match(text)
    if not normalized:
        return False
    if normalized in HEADER_TOKENS:
        return True
    raw = _clean_text(text)
    if raw and raw.isupper() and len(raw) <= 24:
        return True
    return False


def _too_long_inline(text: Any, max_len: int) -> bool:
    value = _clean_text(text)
    if not value:
        return False
    return len(value) > max_len or "\n" in value or "\r" in value


def build_empty_profile_json() -> Dict[str, Any]:
    data: Dict[str, Any] = {"schema_version": "profile.v1"}
    data["personal_info"] = {field: "" for field in PERSONAL_INFO_FIELDS}
    data["personal_info"]["links"] = []
    for section in LIST_SECTIONS:
        data[section] = []
    return data


def normalize_profile_json(data: Dict[str, Any]) -> Dict[str, Any]:
    normalized = build_empty_profile_json()
    if not isinstance(data, dict):
        return normalized

    normalized["schema_version"] = str(data.get("schema_version") or "profile.v1")

    personal = data.get("personal_info")
    if isinstance(personal, dict):
        for field in PERSONAL_INFO_FIELDS:
            value = _clean_text(personal.get(field))
            if value:
                normalized["personal_info"][field] = value
        normalized["personal_info"]["links"] = normalize_links(personal.get("links"))
    else:
        normalized["personal_info"]["links"] = normalize_links(data.get("links"))

    for section in LIST_SECTIONS:
        raw_items = data.get(section)
        if section == "interests":
            normalized["interests"] = normalize_interests(raw_items)
            continue

        items = []
        for item in _as_list(raw_items):
            if not isinstance(item, dict):
                continue
            cleaned = {}
            for field in SECTION_FIELDS[section]:
                value = _clean_text(item.get(field))
                if value:
                    cleaned[field] = value
            if cleaned:
                items.append(cleaned)
        normalized[section] = items

    return normalized


def _dedup_list(items: List[str]) -> List[str]:
    seen = set()
    output: List[str] = []
    for item in items:
        text = _clean_text(item)
        if not text:
            continue
        norm = text.lower()
        if norm in seen:
            continue
        seen.add(norm)
        output.append(text)
    return output


def _dedup_items(items: List[Dict[str, str]], key: str) -> List[Dict[str, str]]:
    seen = set()
    output: List[Dict[str, str]] = []
    for item in items:
        value = _clean_text(item.get(key))
        if not value:
            continue
        norm = value.lower()
        if norm in seen:
            continue
        seen.add(norm)
        output.append(item)
    return output


def _dedup_complex_section(section: str, items: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen = set()
    output: List[Dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if section == "experiences":
            key = "|".join(
                _normalize_for_match(item.get(field))
                for field in ("title", "company", "start_date", "end_date")
            )
        else:
            key = "|".join(
                _normalize_for_match(item.get(field))
                for field in ("school", "degree", "start_date", "end_date")
            )
        if not key.strip("|"):
            continue
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def _is_reasonable_section_item(section: str, item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    if section == "experiences":
        title = _clean_text(item.get("title"))
        company = _clean_text(item.get("company"))
        if not any([title, company, _clean_text(item.get("description"))]):
            return False
        if _looks_like_header(title) or _looks_like_header(company):
            return False
        if _too_long_inline(title, 140) or _too_long_inline(company, 140):
            return False
        return True
    if section == "education":
        school = _clean_text(item.get("school"))
        degree = _clean_text(item.get("degree"))
        if not any([school, degree, _clean_text(item.get("field_of_study"))]):
            return False
        if _looks_like_header(school) or _looks_like_header(degree):
            return False
        if _too_long_inline(school, 140) or _too_long_inline(degree, 140):
            return False
        return True
    return True


def _merge_section_items(section: str, base_list: List[Any], overlay_list: List[Any]) -> List[Any]:
    if not overlay_list:
        return base_list
    if not base_list:
        return overlay_list
    if section == "interests":
        return _dedup_list(base_list + overlay_list)

    if section in {"experiences", "education"}:
        filtered_overlay = [
            item for item in overlay_list if _is_reasonable_section_item(section, item)
        ]
        if not filtered_overlay:
            return base_list
        combined = base_list + filtered_overlay
        return _dedup_complex_section(section, combined)

    key = "name"
    if section == "languages":
        key = "language"
    elif section == "publications":
        key = "title"
    elif section == "volunteering":
        key = "organization"
    return _dedup_items(base_list + overlay_list, key=key)


def merge_profile_json(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    base_norm = normalize_profile_json(base)
    overlay_norm = normalize_profile_json(overlay)

    merged = build_empty_profile_json()
    merged["schema_version"] = overlay_norm.get("schema_version") or base_norm.get(
        "schema_version"
    )

    for field in PERSONAL_INFO_FIELDS:
        merged["personal_info"][field] = (
            overlay_norm["personal_info"].get(field)
            or base_norm["personal_info"].get(field)
            or ""
        )
    merged["personal_info"]["links"] = merge_personal_links(
        normalize_links(base_norm.get("personal_info", {}).get("links")),
        normalize_links(overlay_norm.get("personal_info", {}).get("links")),
    )

    for section in LIST_SECTIONS:
        overlay_list = overlay_norm.get(section, [])
        base_list = base_norm.get(section, [])
        merged[section] = _merge_section_items(section, base_list, overlay_list)

    return merged


def has_profile_json_content(data: Dict[str, Any]) -> bool:
    if not isinstance(data, dict):
        return False
    personal = data.get("personal_info", {})
    if isinstance(personal, dict):
        if any(_clean_text(personal.get(field)) for field in PERSONAL_INFO_FIELDS):
            return True
        if normalize_links(personal.get("links")):
            return True
    for section in LIST_SECTIONS:
        items = data.get(section)
        if section == "interests":
            if normalize_interests(items):
                return True
            continue
        if isinstance(items, list) and any(isinstance(item, dict) and item for item in items):
            return True
    return False


def apply_profile_json_to_profile(profile: Any, data: Dict[str, Any]) -> None:
    raw_personal = data.get("personal_info") if isinstance(data, dict) else {}
    raw_links = None
    if isinstance(raw_personal, dict) and "links" in raw_personal:
        raw_links = raw_personal.get("links")
    elif isinstance(data, dict) and "links" in data:
        raw_links = data.get("links")
    incoming_links = normalize_links(raw_links)

    normalized = normalize_profile_json(data)
    if not hasattr(profile, "extracted_personal_info"):
        return

    existing_personal = getattr(profile, "extracted_personal_info", None) or {}
    merged_personal = dict(existing_personal)
    for field in PERSONAL_INFO_FIELDS:
        value = _clean_text(normalized["personal_info"].get(field))
        if value:
            merged_personal[field] = value
    if incoming_links:
        merged_personal["links"] = incoming_links
    else:
        existing_links = normalize_links(merged_personal.get("links"))
        if existing_links:
            merged_personal["links"] = existing_links
        else:
            merged_personal.pop("links", None)
    profile.extracted_personal_info = merged_personal

    attr_map = {
        "experiences": "extracted_experiences",
        "education": "extracted_education",
        "skills": "extracted_skills",
        "soft_skills": "extracted_soft_skills",
        "languages": "extracted_languages",
        "projects": "extracted_projects",
        "certifications": "extracted_certifications",
        "publications": "extracted_publications",
        "volunteering": "extracted_volunteering",
        "interests": "extracted_interests",
        "awards": "extracted_awards",
        "references": "extracted_references",
    }

    for section, attr in attr_map.items():
        value = normalized.get(section, [])
        if value:
            setattr(profile, attr, value)
