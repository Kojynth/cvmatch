"""Helpers to aggregate and merge offer keyword payloads."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence


DEFAULT_OFFER_KEY_FIELDS: Sequence[str] = (
    "keywords",
    "skills",
    "tools",
    "soft_skills",
    "responsibilities",
    "education",
    "certifications",
    "lexical_field",
)

DEFAULT_ANALYSIS_KEY_FIELDS: Sequence[str] = (
    "keywords",
    "skills",
    "tech_keywords",
    "soft_keywords",
    "soft_skills",
    "skills_required",
    "tools",
    "responsibilities",
    "education",
    "certifications",
    "lexical_field",
)


def dedup_preserve(items: Iterable[str], *, max_items: Optional[int] = None) -> List[str]:
    seen = set()
    output: List[str] = []
    for raw in items or []:
        text = str(raw or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(text)
        if max_items is not None and len(output) >= int(max_items):
            break
    return output


def _extend_from_value(target: List[str], value: Any) -> None:
    if value is None:
        return
    if isinstance(value, list):
        target.extend(str(item) for item in value if str(item).strip())
        return
    if isinstance(value, str):
        if "," in value:
            target.extend(part.strip() for part in value.split(",") if part.strip())
        elif value.strip():
            target.append(value.strip())


def normalize_keyword_families(
    value: Any,
    *,
    max_values_per_family: int = 12,
) -> Dict[str, List[str]]:
    if not isinstance(value, Mapping):
        return {}

    normalized: Dict[str, List[str]] = {}
    for raw_key, raw_values in value.items():
        family_key = str(raw_key or "").strip()
        if not family_key:
            continue
        terms: List[str] = []
        _extend_from_value(terms, raw_values)
        terms = dedup_preserve(terms, max_items=max_values_per_family)
        if not terms:
            continue
        normalized[family_key] = terms
    return normalized


def collect_offer_keywords_from_source(
    source: Optional[Mapping[str, Any]],
    *,
    keys: Sequence[str],
    include_keyword_families: bool = True,
    include_family_keys: bool = True,
    include_job_title: bool = False,
    max_items: int = 60,
) -> List[str]:
    if not isinstance(source, Mapping):
        return []

    keywords: List[str] = []
    for key in keys:
        _extend_from_value(keywords, source.get(key))

    if include_keyword_families:
        families = normalize_keyword_families(source.get("keyword_families"))
        for family_key, family_values in families.items():
            if include_family_keys and family_key.strip():
                keywords.append(family_key.strip())
            keywords.extend(family_values)

    if include_job_title:
        job_title = str(source.get("job_title") or "").strip()
        if job_title:
            # Preserve the phrase atom FIRST (R2 invariant, AGENTS.md
            # "Positioning keywords prefer phrases"): "Software Engineer, QA"
            # is a skill-shaped multi-word compound; splitting it into bare
            # tokens like "QA", "Engineer" destroys the atom. Tokens are
            # appended after as fallback candidates.
            keywords.append(job_title)
            for part in job_title.split():
                cleaned = part.strip(" ,;:-")
                if len(cleaned) >= 3:
                    keywords.append(cleaned)

    return dedup_preserve(keywords, max_items=max_items)


def merge_offer_keywords_into_analysis(
    analysis: Optional[Mapping[str, Any]],
    offer_keywords: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    merged: Dict[str, Any] = dict(analysis or {})
    if not isinstance(offer_keywords, Mapping):
        return merged

    payload = dict(offer_keywords)
    merged["offer_keywords_llm"] = payload

    def merge_list_field(key: str, value: Any) -> None:
        items: List[str] = []
        _extend_from_value(items, merged.get(key))
        _extend_from_value(items, value)
        deduped = dedup_preserve(items)
        if deduped:
            merged[key] = deduped

    merge_list_field("keywords", payload.get("keywords"))
    merge_list_field("skills", payload.get("skills"))
    merge_list_field("soft_keywords", payload.get("soft_skills"))
    merge_list_field("tools", payload.get("tools"))
    merge_list_field("responsibilities", payload.get("responsibilities"))
    merge_list_field("education", payload.get("education"))
    merge_list_field("certifications", payload.get("certifications"))
    merge_list_field("lexical_field", payload.get("lexical_field"))

    incoming_families = normalize_keyword_families(payload.get("keyword_families"))
    if incoming_families:
        existing_families = normalize_keyword_families(merged.get("keyword_families"))
        for family_key, family_values in incoming_families.items():
            current_values = existing_families.get(family_key) or []
            existing_families[family_key] = dedup_preserve(
                current_values + family_values,
                max_items=12,
            )
            merge_list_field("keywords", family_values)
            merge_list_field("lexical_field", family_values)
        if existing_families:
            merged["keyword_families"] = existing_families

    language = payload.get("language")
    if isinstance(language, str) and language.strip():
        merged.setdefault("language", language.strip())

    seniority = payload.get("seniority")
    if isinstance(seniority, str) and seniority.strip():
        merged["seniority"] = seniority.strip()

    return merged
