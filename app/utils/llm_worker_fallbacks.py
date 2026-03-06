"""Fallback builders extracted from ``llm_worker``.

This module keeps deterministic fallback generation logic outside worker classes
to keep worker files focused on orchestration.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Mapping, Optional

from .cv_fallback_generator import generate_fallback_cv_json
from .offer_keywords_utils import dedup_preserve


def _extend_terms(target: List[str], value: Any) -> None:
    if value is None:
        return
    if isinstance(value, list):
        target.extend(str(item) for item in value if str(item).strip())
        return
    if isinstance(value, str):
        target.extend(part.strip() for part in re.split(r"[;,|]", value) if part.strip())


def _extract_offer_text_keywords(offer_text: str) -> List[str]:
    tokens: List[str] = []
    token_pattern = re.compile(r"[A-Za-z][A-Za-z0-9+.#/-]{2,}")
    stopwords = {
        "with",
        "from",
        "that",
        "this",
        "will",
        "your",
        "have",
        "for",
        "and",
        "the",
        "des",
        "avec",
        "pour",
        "dans",
        "vous",
        "nous",
        "une",
        "les",
        "aux",
        "sur",
        "job",
        "role",
        "poste",
        "offre",
        "company",
        "entreprise",
    }
    for token in token_pattern.findall(offer_text or ""):
        lowered = token.lower()
        if lowered in stopwords:
            continue
        tokens.append(token)
    return tokens


def build_offer_keywords_fallback(
    *,
    offer_data: Optional[Mapping[str, Any]],
    language_code: str,
    reason: str = "",
    logger: Any = None,
) -> Dict[str, Any]:
    from ..schemas.offer_keywords_schema import OfferKeywordsJSON

    job_title = ""
    company = ""
    extracted_keywords: List[str] = []
    extracted_skills: List[str] = []
    extracted_tools: List[str] = []
    extracted_lexical: List[str] = []

    if isinstance(offer_data, Mapping):
        job_title = str(offer_data.get("job_title") or "")
        company = str(offer_data.get("company") or "")

        analysis = offer_data.get("analysis")
        if isinstance(analysis, Mapping):
            for key in (
                "keywords",
                "skills",
                "tech_keywords",
                "tools",
                "responsibilities",
                "soft_keywords",
            ):
                _extend_terms(extracted_keywords, analysis.get(key))
            _extend_terms(extracted_skills, analysis.get("skills"))
            _extend_terms(extracted_tools, analysis.get("tools"))
            _extend_terms(extracted_lexical, analysis.get("lexical_field"))

        offer_text = str(offer_data.get("text") or "")
        if offer_text:
            extracted_keywords.extend(_extract_offer_text_keywords(offer_text))
        if job_title:
            extracted_keywords.extend(part for part in re.split(r"\s+", job_title) if part.strip())

    extracted_keywords = dedup_preserve(extracted_keywords, max_items=20)
    extracted_skills = (
        dedup_preserve(extracted_skills, max_items=8)
        if extracted_skills
        else extracted_keywords[:8]
    )
    extracted_tools = dedup_preserve(extracted_tools, max_items=8)
    extracted_lexical = dedup_preserve(extracted_lexical + extracted_keywords, max_items=20)

    payload: Dict[str, Any] = {
        "schema_version": "offer_keywords.v1",
        "language": str(language_code or "fr"),
        "job_title": job_title,
        "company": company,
        "seniority": "",
        "keywords": extracted_keywords,
        "skills": extracted_skills,
        "tools": extracted_tools,
        "soft_skills": [],
        "responsibilities": [],
        "education": [],
        "certifications": [],
        "lexical_field": extracted_lexical,
        "keyword_families": {},
    }

    try:
        parsed = OfferKeywordsJSON.model_validate(payload).model_dump()
    except Exception:
        parsed = payload

    if reason and logger:
        logger.warning("Fallback OfferKeywordsJSON used due to: %s", reason)
    return parsed


def build_cv_json_fallback(
    *,
    profile_json: Dict[str, Any],
    profile_data: Any,
    offer_data: Optional[Mapping[str, Any]],
    language_code: str,
    offer_keywords_collector: Optional[Callable[[], List[str]]] = None,
    reason: str = "",
    logger: Any = None,
) -> Dict[str, Any]:
    try:
        return generate_fallback_cv_json(
            profile_json=profile_json or {},
            profile_data=profile_data,
            offer_data=dict(offer_data or {}),
            language_code=language_code,
            offer_keywords_collector=offer_keywords_collector,
            reason=reason,
        )
    except Exception as exc:
        if logger:
            logger.warning("Advanced fallback CVJSON failed, using minimal fallback: %s", exc)
        from ..schemas.cv_schema import CVJSON

        payload = {
            "schema_version": "cv.v1",
            "target_job_title": "",
            "target_company": "",
            "contact": {},
            "summary": "",
            "skills": [],
            "experience": [],
            "education": [],
            "projects": [],
            "languages": [],
            "certifications": [],
            "ats_keywords": [],
            "render_hints": {
                "notes": "",
                "section_order": [],
                "emphasis": [],
                "tone": "",
            },
        }

        try:
            parsed = CVJSON.model_validate(payload).model_dump()
        except Exception:
            parsed = payload

        if reason and logger:
            logger.warning("Fallback CVJSON used due to: %s", reason)
        return parsed
