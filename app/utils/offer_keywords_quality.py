"""Quality guards for offer-keywords payloads.

LLM output stays the primary source. This module only stabilizes weak outputs
to avoid empty keyword sets that degrade downstream CV alignment.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional

from .llm_worker_fallbacks import build_offer_keywords_fallback
from .offer_keywords_utils import dedup_preserve


LIST_KEYS: List[str] = [
    "keywords",
    "skills",
    "tools",
    "soft_skills",
    "responsibilities",
    "education",
    "certifications",
    "lexical_field",
]


def extract_offer_text_from_offer_data(offer_data: Optional[Mapping[str, Any]]) -> str:
    """Resolve canonical offer text from common source keys."""
    if not isinstance(offer_data, Mapping):
        return ""
    for key in ("text", "offer_text", "description", "job_description", "content", "raw_text"):
        value = offer_data.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def _as_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _signal_counts(payload: Mapping[str, Any]) -> Dict[str, int]:
    return {
        "keywords": len(_as_list(payload.get("keywords"))),
        "skills": len(_as_list(payload.get("skills"))),
        "tools": len(_as_list(payload.get("tools"))),
        "responsibilities": len(_as_list(payload.get("responsibilities"))),
    }


def is_offer_keywords_payload_weak(
    payload: Optional[Mapping[str, Any]],
    *,
    offer_text: str,
) -> bool:
    """Detect low-signal outputs likely to hurt adaptation quality."""
    if not isinstance(payload, Mapping):
        return True

    counts = _signal_counts(payload)
    short_offer = len((offer_text or "").strip()) < 120

    if short_offer:
        # For tiny offers, only require at least one actionable signal.
        return (counts["keywords"] + counts["skills"] + counts["tools"]) == 0

    # Normal offers should provide a minimum extraction footprint.
    if counts["keywords"] >= 6 and (counts["skills"] + counts["tools"]) >= 3:
        return False
    return True


def _merge_list(primary: Iterable[str], fallback: Iterable[str], *, max_items: int) -> List[str]:
    return dedup_preserve(list(primary) + list(fallback), max_items=max_items)


def stabilize_offer_keywords_payload(
    *,
    payload: Optional[Dict[str, Any]],
    offer_data: Optional[Mapping[str, Any]],
    language_code: str,
    reason: str = "",
    logger: Any = None,
) -> Dict[str, Any]:
    """Keep LLM output, but enrich weak lists from deterministic extraction."""
    from ..schemas.offer_keywords_schema import OfferKeywordsJSON

    base = dict(payload or {})
    offer_text = extract_offer_text_from_offer_data(offer_data)
    weak = is_offer_keywords_payload_weak(base, offer_text=offer_text)

    if not weak:
        try:
            return OfferKeywordsJSON.model_validate(base).model_dump()
        except Exception:
            pass

    fallback = build_offer_keywords_fallback(
        offer_data=offer_data,
        language_code=language_code,
        reason=reason or "offer_keywords_weak_payload",
        logger=logger,
    )

    merged: Dict[str, Any] = dict(base)
    merged["schema_version"] = "offer_keywords.v1"
    merged["language"] = str(merged.get("language") or fallback.get("language") or language_code or "fr")
    merged["job_title"] = str(merged.get("job_title") or fallback.get("job_title") or "")
    merged["company"] = str(merged.get("company") or fallback.get("company") or "")
    merged["seniority"] = str(merged.get("seniority") or fallback.get("seniority") or "")

    limits = {
        "keywords": 20,
        "skills": 12,
        "tools": 10,
        "soft_skills": 10,
        "responsibilities": 12,
        "education": 8,
        "certifications": 8,
        "lexical_field": 20,
    }

    for key in LIST_KEYS:
        merged[key] = _merge_list(
            _as_list(merged.get(key)),
            _as_list(fallback.get(key)),
            max_items=limits.get(key, 20),
        )

    merged["keyword_families"] = (
        merged.get("keyword_families")
        if isinstance(merged.get("keyword_families"), dict)
        else (fallback.get("keyword_families") if isinstance(fallback.get("keyword_families"), dict) else {})
    )

    try:
        parsed = OfferKeywordsJSON.model_validate(merged).model_dump()
    except Exception:
        parsed = merged

    if logger:
        counts = _signal_counts(parsed if isinstance(parsed, Mapping) else {})
        logger.info(
            "Offer keywords stabilized: weak=%s keywords=%s skills=%s tools=%s",
            weak,
            counts.get("keywords", 0),
            counts.get("skills", 0),
            counts.get("tools", 0),
        )
    return parsed
