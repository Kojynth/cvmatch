"""Compatibility-safe mapping for skills, soft skills, and languages."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Tuple

from ...utils.text_norm import normalize_text_for_ui


CEFR_RE = re.compile(r"\b(A1|A2|B1|B2|C1|C2)\b", re.IGNORECASE)
NATIVE_RE = re.compile(r"\b(native|natif)\b", re.IGNORECASE)


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


def parse_language_string(text: str) -> Tuple[str, str]:
    if not text:
        return "", ""
    level = ""
    level_match = CEFR_RE.search(text)
    if level_match:
        level = level_match.group(1).upper()
        text = CEFR_RE.sub("", text)
    elif NATIVE_RE.search(text):
        level = "Natif"
        text = NATIVE_RE.sub("", text)
    language = text.strip(" -:;|")
    return language, level


def map_skills(raw_skills: Any) -> List[Dict[str, str]]:
    flattened: List[Any] = []
    if isinstance(raw_skills, dict):
        for value in raw_skills.values():
            flattened.extend(_as_list(value))
    else:
        flattened = _as_list(raw_skills)

    items: List[Dict[str, str]] = []
    for entry in flattened:
        if isinstance(entry, dict):
            nested = entry.get("items") or entry.get("skills") or entry.get("skills_list")
            if nested:
                flattened.extend(_as_list(nested))
                continue
            name = _pick_first(entry, ["name", "skill"])
            level = _pick_first(entry, ["level", "proficiency", "skill_level"])
        else:
            name = _clean_text(entry)
            level = ""

        if not name:
            continue
        items.append({"name": name, "level": level})

    return _dedup_items(items, key="name")


def map_soft_skills(raw_soft_skills: Any) -> List[Dict[str, str]]:
    return map_skills(raw_soft_skills)


def map_languages(raw_languages: Any) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    for entry in _as_list(raw_languages):
        if isinstance(entry, dict):
            language = _pick_first(entry, ["language", "name"])
            proficiency = _pick_first(entry, ["proficiency", "level"])
            certification = _pick_first(
                entry,
                ["certification", "certificate", "organization", "issuer"],
            )
        else:
            language, proficiency = parse_language_string(_clean_text(entry))
            certification = ""

        if not language:
            continue
        items.append(
            {
                "language": language,
                "proficiency": proficiency,
                "certification": certification,
            }
        )

    return _dedup_items(items, key="language")
