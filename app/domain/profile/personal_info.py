"""Compatibility-safe personal-info mapping and link normalization."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List

from ...utils.text_norm import normalize_text_for_ui


PERSONAL_INFO_FIELDS = ["full_name", "email", "phone", "linkedin_url", "location"]


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


def normalize_link_url(value: Any) -> str:
    url = _clean_text(value)
    if not url:
        return ""
    lowered = url.lower()
    if lowered.startswith(("http://", "https://")):
        return url
    if lowered.startswith("www."):
        return f"https://{url}"
    if re.match(r"^[a-z0-9][a-z0-9.-]+\.[a-z]{2,}(?:[/?#].*)?$", lowered):
        return f"https://{url}"
    return url


def normalize_links(raw_links: Any) -> List[Dict[str, str]]:
    links: List[Dict[str, str]] = []
    seen = set()
    for entry in _as_list(raw_links):
        label = ""
        url = ""
        if isinstance(entry, dict):
            label = _clean_text(
                entry.get("label") or entry.get("platform") or entry.get("name")
            )
            url = normalize_link_url(entry.get("url") or entry.get("link"))
        else:
            url = normalize_link_url(entry)

        if not url:
            continue
        key = (label.lower(), url.lower())
        if key in seen:
            continue
        seen.add(key)
        item = {"url": url}
        if label:
            item["label"] = label
        links.append(item)
    return links


def merge_personal_links(
    base_links: List[Dict[str, str]],
    overlay_links: List[Dict[str, str]],
) -> List[Dict[str, str]]:
    if overlay_links:
        return normalize_links(overlay_links + (base_links or []))
    return normalize_links(base_links)


def extract_personal_info(payload: Dict[str, Any]) -> Dict[str, Any]:
    candidates = [
        payload.get("personal_info"),
        payload.get("contact_info"),
        payload.get("contact"),
        payload.get("basic_info"),
        payload.get("profile"),
    ]
    personal: Dict[str, Any] = {}
    for item in candidates:
        if isinstance(item, dict):
            personal = item
            break

    data: Dict[str, Any] = {field: "" for field in PERSONAL_INFO_FIELDS}
    data["links"] = []
    if not personal:
        data["links"] = normalize_links(payload.get("links"))
        return data

    data["full_name"] = _pick_first(personal, ["full_name", "name", "fullname"])
    data["email"] = _pick_first(personal, ["email", "mail"])
    data["phone"] = _pick_first(personal, ["phone", "telephone", "tel"])
    data["linkedin_url"] = _pick_first(
        personal,
        ["linkedin_url", "linkedin", "url", "profile_url"],
    )
    data["location"] = _pick_first(
        personal,
        ["location", "city", "address", "city_country"],
    )
    data["links"] = normalize_links(personal.get("links"))
    if not data["links"]:
        data["links"] = normalize_links(payload.get("links"))
    if not data["links"]:
        fallback_links: List[Dict[str, str]] = []
        github = _pick_first(personal, ["github_url", "github", "github_profile"])
        portfolio = _pick_first(
            personal,
            ["portfolio_url", "portfolio", "website", "site_web"],
        )
        if github:
            fallback_links.append({"label": "GitHub", "url": github})
        if portfolio:
            fallback_links.append({"label": "Portfolio", "url": portfolio})
        data["links"] = normalize_links(fallback_links)
    return data
