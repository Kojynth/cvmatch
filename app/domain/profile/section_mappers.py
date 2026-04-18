"""Compatibility-safe mappers for profile experience and education sections."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Tuple

from ...utils.text_norm import normalize_text_for_ui


DATE_RANGE_SPLIT = re.compile(r"\s*(?:-|\u2013|\u2014|to|au)\s*", re.IGNORECASE)


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


def _pick_first(data: Dict[str, Any], keys: Iterable[str]) -> str:
    for key in keys:
        value = _clean_text(data.get(key))
        if value:
            return value
    return ""


def _split_date_range(value: Any, *, single_date_is_end: bool = False) -> Tuple[str, str]:
    text = _clean_text(value)
    if not text:
        return "", ""
    parts = DATE_RANGE_SPLIT.split(text, maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    if single_date_is_end:
        return "", text
    return text, ""


def _normalize_date_value(value: Any) -> str:
    text = _clean_text(value)
    if not text:
        return ""

    try:
        from ...rules.date_normalize import _normalize_single_date, normalize_present_token
    except Exception:
        return text

    normalized_present = normalize_present_token(text)
    if str(normalized_present or "").strip().upper() == "PRESENT":
        return text

    if re.fullmatch(r"\d{4}", text):
        return text

    normalized = _normalize_single_date(text)
    normalized_text = _clean_text(normalized)
    if re.fullmatch(r"\d{4}-\d{2}", normalized_text):
        return f"{normalized_text[5:7]}/{normalized_text[:4]}"
    if re.fullmatch(r"\d{4}", normalized_text):
        return normalized_text
    return text


def map_experiences(raw_items: List[Any], source: str) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    for item in raw_items:
        if isinstance(item, dict):
            title = _pick_first(item, ["title", "position", "role", "job_title"])
            company = _pick_first(
                item,
                ["company", "employer", "organization", "institution", "enterprise"],
            )
            location = _pick_first(item, ["location", "city", "place"])
            description = _pick_first(
                item,
                ["description", "summary", "details", "responsibilities"],
            )
            if not description:
                achievements = item.get("achievements") or item.get("accomplishments")
                if isinstance(achievements, list):
                    description = "\n".join(
                        _clean_text(entry) for entry in achievements if _clean_text(entry)
                    )
                elif achievements:
                    description = _clean_text(achievements)

            start_date = _pick_first(
                item,
                ["start_date", "date_start", "begin_date", "from_date"],
            )
            end_date = _pick_first(
                item,
                ["end_date", "date_end", "finish_date", "to_date"],
            )
            if not start_date and not end_date:
                start_date, end_date = _split_date_range(
                    _pick_first(item, ["dates", "date_range", "period"]),
                    single_date_is_end=False,
                )
            start_date = _normalize_date_value(start_date)
            end_date = _normalize_date_value(end_date)

            if not any([title, company, description]):
                continue

            mapped = {
                "title": title,
                "company": company,
                "start_date": start_date,
                "end_date": end_date,
                "location": location,
                "description": description,
            }
            src_value = _clean_text(item.get("source") or source)
            if src_value:
                mapped["source"] = src_value
            items.append(mapped)
            continue

        text = _clean_text(item)
        if text:
            mapped = {"title": text}
            if source:
                mapped["source"] = source
            items.append(mapped)

    return items


def map_education(raw_items: List[Any], source: str) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        degree = _pick_first(item, ["degree", "diploma", "qualification", "title"])
        school = _pick_first(item, ["school", "institution", "university", "college"])
        field_of_study = _pick_first(
            item,
            ["field_of_study", "major", "specialization", "domain"],
        )
        grade = _pick_first(item, ["grade", "gpa", "mention"])
        start_date = _pick_first(
            item,
            ["start_date", "start_year", "date_start", "begin_date"],
        )
        end_date = _pick_first(
            item,
            ["end_date", "end_year", "date_end", "finish_date", "year"],
        )
        if not start_date and not end_date:
            start_date, end_date = _split_date_range(
                _pick_first(item, ["dates", "date_range", "period"]),
                single_date_is_end=True,
            )
        start_date = _normalize_date_value(start_date)
        end_date = _normalize_date_value(end_date)

        if not any([degree, school, field_of_study]):
            continue

        mapped = {
            "school": school,
            "degree": degree,
            "field_of_study": field_of_study,
            "start_date": start_date,
            "end_date": end_date,
            "grade": grade,
        }
        src_value = _clean_text(item.get("source") or source)
        if src_value:
            mapped["source"] = src_value
        items.append(mapped)

    return items
