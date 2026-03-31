"""Diagnostics helpers for postprocessed CV payload provenance."""

from __future__ import annotations

import copy
import json
import re
from typing import Any, Dict, Tuple


_TEXT_KEYS = ("summary", "target_job_title", "target_company")
_LIST_KEYS = (
    "skills",
    "experience",
    "education",
    "projects",
    "languages",
    "certifications",
    "ats_keywords",
)
_CONTACT_KEYS = ("full_name", "email", "phone", "linkedin_url", "location", "links")
_RETRY_LIST_LIMITS = {
    "skills": 5,
    "experience": 5,
    "education": 3,
    "projects": 3,
    "languages": 4,
    "certifications": 3,
    "ats_keywords": 18,
}
_FACT_VALIDATED_LIST_KEYS = {
    "skills",
    "experience",
    "education",
    "projects",
    "languages",
    "certifications",
}
_SECTION_TO_PROFILE_KEY = {
    "skills": "skills",
    "experience": "experiences",
    "education": "education",
    "projects": "projects",
    "languages": "languages",
    "certifications": "certifications",
}


def _is_meaningful(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(_is_meaningful(item) for item in value)
    if isinstance(value, dict):
        return any(_is_meaningful(item) for item in value.values())
    return value is not None


def _count_payload_signals(payload: Dict[str, Any]) -> Dict[str, int]:
    text_fields = sum(1 for key in _TEXT_KEYS if _is_meaningful(payload.get(key)))
    list_fields = sum(1 for key in _LIST_KEYS if _is_meaningful(payload.get(key)))

    contact_fields = 0
    contact = payload.get("contact")
    if isinstance(contact, dict):
        contact_fields = sum(1 for key in _CONTACT_KEYS if _is_meaningful(contact.get(key)))

    render_hints = 1 if _is_meaningful(payload.get("render_hints")) else 0

    return {
        "text_fields": text_fields,
        "list_fields": list_fields,
        "contact_fields": contact_fields,
        "render_hints": render_hints,
        "total_signals": text_fields + list_fields + contact_fields + render_hints,
    }


def classify_cv_payload_source(
    payload: Dict[str, Any],
    merged: Dict[str, Any],
) -> Tuple[str, Dict[str, int]]:
    """Classify how much the final CV comes from the raw LLM payload vs deterministic repair."""
    payload_stats = _count_payload_signals(payload if isinstance(payload, dict) else {})
    merged_stats = _count_payload_signals(merged if isinstance(merged, dict) else {})

    payload_signals = int(payload_stats.get("total_signals") or 0)
    merged_signals = int(merged_stats.get("total_signals") or 0)
    fill_ratio = float(payload_signals) / float(max(1, merged_signals))

    if payload_signals <= 1 or (payload_signals <= 2 and fill_ratio < 0.35):
        source = "postprocess_base_heavy"
    elif payload_signals >= 6 and fill_ratio >= 0.75:
        source = "llm_full"
    else:
        source = "llm_partial"

    stats = {
        "payload_text_fields": int(payload_stats.get("text_fields") or 0),
        "payload_list_fields": int(payload_stats.get("list_fields") or 0),
        "payload_contact_fields": int(payload_stats.get("contact_fields") or 0),
        "payload_render_hints": int(payload_stats.get("render_hints") or 0),
        "payload_total_signals": payload_signals,
        "merged_total_signals": merged_signals,
        "fill_ratio_pct": int(round(fill_ratio * 100.0)),
    }
    return source, stats


def is_sparse_generated_cv_payload(
    payload: Dict[str, Any],
    *,
    profile_json: Dict[str, Any] | None = None,
) -> bool:
    """Detect valid-but-underfilled LLM CV payloads.

    This is used to avoid treating a minimally valid JSON response as a
    successful final regeneration when the profile itself is much richer.
    """
    if not isinstance(payload, dict):
        return True

    payload_stats = _count_payload_signals(payload)
    payload_text = int(payload_stats.get("text_fields") or 0)
    payload_lists = int(payload_stats.get("list_fields") or 0)
    payload_total = int(payload_stats.get("total_signals") or 0)

    if payload_lists <= 1 and payload_total <= 8:
        return True
    if payload_lists == 0:
        return True

    profile_list_sections = 0
    if isinstance(profile_json, dict):
        for key in (
            "skills",
            "experiences",
            "education",
            "projects",
            "languages",
            "certifications",
        ):
            value = profile_json.get(key)
            if isinstance(value, list) and any(_is_meaningful(item) for item in value):
                profile_list_sections += 1

    if profile_list_sections >= 3 and payload_lists < 2:
        return True
    if profile_list_sections >= 4 and payload_text <= 3 and payload_lists <= 2:
        return True

    return False


def _item_signature(value: Any) -> str:
    try:
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        return str(value).strip().lower()
    except Exception:
        return str(value)


def _dedup_merge_items(
    current: Any,
    previous: Any,
    *,
    limit: int,
) -> list:
    merged: list = []
    seen: set[str] = set()
    for source in (current, previous):
        if not isinstance(source, list):
            continue
        for item in source:
            if not _is_meaningful(item):
                continue
            sig = _item_signature(item)
            if sig in seen:
                continue
            seen.add(sig)
            merged.append(copy.deepcopy(item))
            if len(merged) >= max(1, int(limit)):
                return merged
    return merged


def _collect_tokens(value: Any) -> list[str]:
    tokens: list[str] = []
    if isinstance(value, str):
        for token in re.split(r"[^a-z0-9]+", value.lower()):
            if len(token) >= 3:
                tokens.append(token)
        return tokens
    if isinstance(value, dict):
        for nested in value.values():
            tokens.extend(_collect_tokens(nested))
        return tokens
    if isinstance(value, list):
        for nested in value:
            tokens.extend(_collect_tokens(nested))
        return tokens
    return tokens


def _required_matches(token_count: int) -> int:
    if token_count <= 0:
        return 0
    if token_count <= 2:
        return 1
    if token_count <= 4:
        return 2
    return max(2, token_count // 2)


def _build_profile_section_cache(
    profile_json: Dict[str, Any] | None,
) -> tuple[Dict[str, list[str]], str]:
    if not isinstance(profile_json, dict):
        return {}, ""

    section_cache: Dict[str, list[str]] = {}
    for section_key, profile_key in _SECTION_TO_PROFILE_KEY.items():
        entries = profile_json.get(profile_key)
        texts: list[str] = []
        if isinstance(entries, list):
            for entry in entries:
                if not _is_meaningful(entry):
                    continue
                if isinstance(entry, str):
                    texts.append(entry.lower())
                else:
                    try:
                        texts.append(
                            json.dumps(entry, ensure_ascii=False, default=str).lower()
                        )
                    except Exception:
                        texts.append(str(entry).lower())
        section_cache[section_key] = texts

    try:
        profile_text = json.dumps(profile_json, ensure_ascii=False, default=str).lower()
    except Exception:
        profile_text = str(profile_json).lower()

    return section_cache, profile_text


def _item_supported_by_profile(
    section_key: str,
    item: Any,
    *,
    section_cache: Dict[str, list[str]],
    profile_text: str,
) -> bool:
    if section_key not in _FACT_VALIDATED_LIST_KEYS:
        return True
    if not _is_meaningful(item):
        return False

    tokens = list(dict.fromkeys(_collect_tokens(item)))
    if not tokens:
        return False
    required = _required_matches(len(tokens))

    section_texts = section_cache.get(section_key) or []
    if section_texts:
        for probe in section_texts:
            matches = sum(1 for token in tokens if token in probe)
            if matches >= required:
                return True
        return False

    # Soft fallback for sections where cross-section terms are common.
    if section_key in {"skills", "languages"} and profile_text:
        matches = sum(1 for token in tokens if token in profile_text)
        return matches >= required

    return False


def _validated_previous_list_items(
    section_key: str,
    value: Any,
    *,
    section_cache: Dict[str, list[str]],
    profile_text: str,
) -> list:
    if not isinstance(value, list):
        return []
    if section_key == "ats_keywords":
        return _dedup_merge_items([], value, limit=_RETRY_LIST_LIMITS.get(section_key, 10))

    validated: list = []
    for item in value:
        if _item_supported_by_profile(
            section_key,
            item,
            section_cache=section_cache,
            profile_text=profile_text,
        ):
            validated.append(copy.deepcopy(item))
    return _dedup_merge_items(
        [],
        validated,
        limit=_RETRY_LIST_LIMITS.get(section_key, 10),
    )


def compact_cv_payload_for_retry(payload: Any) -> Dict[str, Any]:
    """Keep only compact, useful sections for retry context prompts."""
    if not isinstance(payload, dict):
        return {}

    compact: Dict[str, Any] = {}

    for key in ("schema_version", "target_job_title", "target_company", "summary"):
        value = payload.get(key)
        if _is_meaningful(value):
            compact[key] = str(value).strip() if isinstance(value, str) else value

    contact = payload.get("contact")
    if isinstance(contact, dict):
        compact_contact: Dict[str, Any] = {}
        for key in _CONTACT_KEYS:
            value = contact.get(key)
            if _is_meaningful(value):
                compact_contact[key] = copy.deepcopy(value)
        if compact_contact:
            compact["contact"] = compact_contact

    for key in _LIST_KEYS:
        value = payload.get(key)
        if not isinstance(value, list):
            continue
        merged = _dedup_merge_items([], value, limit=_RETRY_LIST_LIMITS.get(key, 10))
        if merged:
            compact[key] = merged

    render_hints = payload.get("render_hints")
    if isinstance(render_hints, dict) and _is_meaningful(render_hints):
        compact["render_hints"] = copy.deepcopy(render_hints)

    return compact


def stabilize_sparse_payload_with_previous(
    payload: Dict[str, Any],
    *,
    previous_payload: Dict[str, Any] | None = None,
    profile_json: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Fill underfilled payload sections using the previous accepted candidate."""
    current = copy.deepcopy(payload) if isinstance(payload, dict) else {}
    previous = compact_cv_payload_for_retry(previous_payload)
    if not previous:
        return current
    section_cache, profile_text = _build_profile_section_cache(profile_json)

    for key in ("target_job_title", "target_company", "summary"):
        if not _is_meaningful(current.get(key)) and _is_meaningful(previous.get(key)):
            current[key] = copy.deepcopy(previous.get(key))

    prev_contact = previous.get("contact")
    if isinstance(prev_contact, dict):
        contact = current.get("contact")
        if not isinstance(contact, dict):
            contact = {}
            current["contact"] = contact
        for key in _CONTACT_KEYS:
            if (not _is_meaningful(contact.get(key))) and _is_meaningful(prev_contact.get(key)):
                contact[key] = copy.deepcopy(prev_contact.get(key))

    for key in _LIST_KEYS:
        prev_value = previous.get(key)
        if not _is_meaningful(prev_value):
            continue
        validated_prev_value = _validated_previous_list_items(
            key,
            prev_value,
            section_cache=section_cache,
            profile_text=profile_text,
        )
        if not _is_meaningful(validated_prev_value):
            continue
        current_value = current.get(key)
        if not _is_meaningful(current_value):
            current[key] = copy.deepcopy(validated_prev_value)
            continue
        if isinstance(current_value, list):
            if len(current_value) < 2 and len(validated_prev_value) > len(current_value):
                merged = _dedup_merge_items(
                    current_value,
                    validated_prev_value,
                    limit=_RETRY_LIST_LIMITS.get(key, 10),
                )
                if len(merged) > len(current_value):
                    current[key] = merged

    if not _is_meaningful(current.get("render_hints")) and _is_meaningful(previous.get("render_hints")):
        current["render_hints"] = copy.deepcopy(previous.get("render_hints"))

    if is_sparse_generated_cv_payload(current, profile_json=profile_json):
        for key in ("skills", "education", "projects", "languages", "certifications", "ats_keywords"):
            if _is_meaningful(current.get(key)):
                continue
            validated_prev_value = _validated_previous_list_items(
                key,
                previous.get(key),
                section_cache=section_cache,
                profile_text=profile_text,
            )
            if _is_meaningful(validated_prev_value):
                current[key] = copy.deepcopy(validated_prev_value)
            if not is_sparse_generated_cv_payload(current, profile_json=profile_json):
                break

    return current
