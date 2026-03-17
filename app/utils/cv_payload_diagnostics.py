"""Diagnostics helpers for postprocessed CV payload provenance."""

from __future__ import annotations

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
