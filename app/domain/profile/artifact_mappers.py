"""Compatibility-safe mapping for projects and other profile artifacts."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

from ...utils.text_norm import normalize_text_for_ui


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


def _pick_first(data: Dict[str, Any], keys: Iterable[str]) -> str:
    for key in keys:
        value = _clean_text(data.get(key))
        if value:
            return value
    return ""


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


def map_projects(raw_items: List[Any]) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        name = _pick_first(item, ["name", "title"])
        url = _pick_first(item, ["url", "link"])
        technologies = item.get("technologies") or item.get("tech_stack") or item.get("skills")
        if isinstance(technologies, list):
            technologies = ", ".join(
                _clean_text(entry) for entry in technologies if _clean_text(entry)
            )
        description = _pick_first(item, ["description", "summary", "details"])
        if not any([name, description, url]):
            continue
        items.append(
            {
                "name": name,
                "url": _clean_text(url),
                "technologies": _clean_text(technologies),
                "description": description,
            }
        )
    return items


def map_certifications(raw_items: List[Any]) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            text = _clean_text(item)
            if text:
                items.append({"name": text})
            continue
        name = _pick_first(item, ["name", "title"])
        organization = _pick_first(item, ["organization", "issuer", "company"])
        date = _pick_first(item, ["date", "issued_date", "year"])
        url = _pick_first(item, ["url", "link"])
        if not name:
            continue
        items.append(
            {
                "name": name,
                "organization": organization,
                "date": date,
                "url": url,
            }
        )
    return items


def map_publications(raw_items: List[Any]) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            text = _clean_text(item)
            if text:
                items.append({"title": text})
            continue
        title = _pick_first(item, ["title", "name"])
        authors = _pick_first(item, ["authors", "author"])
        journal = _pick_first(item, ["journal", "conference", "publisher"])
        date = _pick_first(item, ["date", "year"])
        url = _pick_first(item, ["url", "link"])
        if not title:
            continue
        items.append(
            {
                "title": title,
                "authors": authors,
                "journal": journal,
                "date": date,
                "url": url,
            }
        )
    return items


def map_volunteering(raw_items: List[Any]) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        organization = _pick_first(item, ["organization", "company", "institution"])
        role = _pick_first(item, ["role", "title", "position"])
        period = _pick_first(item, ["period", "dates", "date_range"])
        if not period:
            start_date = _pick_first(item, ["start_date", "date_start"])
            end_date = _pick_first(item, ["end_date", "date_end"])
            if start_date or end_date:
                period = " - ".join(part for part in [start_date, end_date] if part)
        description = _pick_first(item, ["description", "summary", "details"])
        if not any([organization, role, description]):
            continue
        items.append(
            {
                "organization": organization,
                "role": role,
                "period": period,
                "description": description,
            }
        )
    return items


def map_awards(raw_items: List[Any]) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            text = _clean_text(item)
            if text:
                items.append({"name": text})
            continue
        name = _pick_first(item, ["name", "title"])
        organization = _pick_first(item, ["organization", "issuer", "company"])
        date = _pick_first(item, ["date", "year"])
        description = _pick_first(item, ["description", "summary"])
        if not name:
            continue
        items.append(
            {
                "name": name,
                "organization": organization,
                "date": date,
                "description": description,
            }
        )
    return items


def map_references(raw_items: List[Any]) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        name = _pick_first(item, ["name", "author"])
        title = _pick_first(item, ["title", "role", "relationship"])
        company = _pick_first(item, ["company", "organization", "employer"])
        email = _pick_first(item, ["email", "mail"])
        phone = _pick_first(item, ["phone", "telephone", "tel"])
        if not name and not title and not company:
            continue
        items.append(
            {
                "name": name,
                "title": title,
                "company": company,
                "email": email,
                "phone": phone,
            }
        )
    return items


def normalize_interests(raw_items: Any) -> List[str]:
    interests: List[str] = []
    for item in _as_list(raw_items):
        if isinstance(item, dict):
            label = _pick_first(item, ["name", "label"])
            if label:
                interests.append(label)
            continue
        text = _clean_text(item)
        if text:
            interests.extend(part.strip() for part in text.split(",") if part.strip())
    return _dedup_list(interests)
