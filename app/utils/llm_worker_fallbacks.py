"""Fallback builders extracted from ``llm_worker``.

This module keeps deterministic fallback generation logic outside worker classes
to keep worker files focused on orchestration.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Mapping, Optional

from ..domain.generation.tool_signals import extract_named_tool_hints_from_text
from .cv_fallback_generator import generate_fallback_cv_json
from .offer_keywords_utils import dedup_preserve
from .offer_enrichment import prepare_offer_text


_TOOL_PATTERNS: Dict[str, re.Pattern[str]] = {
    "Snowflake": re.compile(r"\bsnowflake\b", re.IGNORECASE),
    "dbt": re.compile(r"\bdbt\b", re.IGNORECASE),
    "AWS": re.compile(r"\baws\b|\bamazon web services\b", re.IGNORECASE),
    "Airflow": re.compile(r"\bairflow\b", re.IGNORECASE),
    "IICS": re.compile(r"\biics\b", re.IGNORECASE),
    "Python": re.compile(r"\bpython\b", re.IGNORECASE),
    "SQL": re.compile(r"\bsql\b", re.IGNORECASE),
    "Git": re.compile(r"\bgit\b", re.IGNORECASE),
    "GitHub": re.compile(r"\bgithub\b", re.IGNORECASE),
    "Linux": re.compile(r"\blinux\b", re.IGNORECASE),
    "GitHub Actions": re.compile(r"\bgithub actions\b", re.IGNORECASE),
    "Terraform": re.compile(r"\bterraform\b", re.IGNORECASE),
    "Vector Databases": re.compile(r"\bvector databases?\b", re.IGNORECASE),
    "ML Workflows": re.compile(r"\bmachine learning workflows?\b", re.IGNORECASE),
    "ETL": re.compile(r"\betl\b", re.IGNORECASE),
    "ELT": re.compile(r"\belt\b", re.IGNORECASE),
}

_KEYWORD_FAMILY_HINTS: Dict[str, List[str]] = {
    "cloud": ["AWS", "Azure", "GCP", "cloud"],
    "data warehousing": ["Snowflake", "data warehouse", "warehousing"],
    "etl/elt": ["ETL", "ELT", "dbt", "IICS", "data ingestion"],
    "orchestration": ["Airflow", "orchestration", "monitoring"],
    "generative ai": ["Generative AI", "GenAI", "Vector Databases", "AI ready data"],
    "platform engineering": ["GitHub Actions", "CI/CD", "Terraform", "infrastructure as code"],
}


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
        "about",
        "believe",
        "power",
        "technology",
        "technologies",
        "designed",
        "integrate",
        "seamlessly",
        "dynamic",
        "collaborative",
        "passionate",
        "future",
        "innovation",
        "culture",
        "benefits",
        "remote",
        "policy",
        "hiring",
        "process",
    }
    for token in token_pattern.findall(offer_text or ""):
        lowered = token.lower()
        if lowered in stopwords:
            continue
        tokens.append(token)
    return tokens


def _extract_offer_text_tools(offer_text: str) -> List[str]:
    text = str(offer_text or "")
    tools: List[str] = extract_named_tool_hints_from_text(
        text,
        explicit_context=False,
        max_items=12,
    )
    for label, pattern in _TOOL_PATTERNS.items():
        if pattern.search(text):
            tools.append(label)
    return dedup_preserve(tools, max_items=10)


def _extract_keyword_families(
    offer_text: str,
    tools: List[str],
) -> Dict[str, List[str]]:
    families: Dict[str, List[str]] = {}
    haystack = str(offer_text or "")
    tool_set = {str(item or "").strip().lower() for item in tools if str(item or "").strip()}

    for family, hints in _KEYWORD_FAMILY_HINTS.items():
        matched: List[str] = []
        for hint in hints:
            hint_text = str(hint or "").strip()
            if not hint_text:
                continue
            if hint_text.lower() in tool_set or re.search(rf"\b{re.escape(hint_text)}\b", haystack, re.IGNORECASE):
                matched.append(hint_text)
        deduped = dedup_preserve(matched, max_items=6)
        if deduped:
            families[family] = deduped
    return families


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
    extracted_families: Dict[str, List[str]] = {}

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

        offer_text = prepare_offer_text(
            dict(offer_data),
            max_chars=3200,
            keywords=[job_title, company],
        ) or str(offer_data.get("text") or "")
        if offer_text:
            extracted_keywords.extend(_extract_offer_text_keywords(offer_text))
            extracted_tools.extend(_extract_offer_text_tools(offer_text))
        if job_title:
            extracted_keywords.extend(part for part in re.split(r"\s+", job_title) if part.strip())

    extracted_keywords = dedup_preserve(extracted_keywords, max_items=20)
    extracted_skills = (
        dedup_preserve(extracted_skills, max_items=8)
        if extracted_skills
        else extracted_keywords[:8]
    )
    extracted_tools = dedup_preserve(extracted_tools, max_items=8)
    if extracted_tools:
        extracted_skills = dedup_preserve(
            [*extracted_skills, *extracted_tools],
            max_items=10,
        )
    extracted_lexical = dedup_preserve(extracted_lexical + extracted_keywords, max_items=20)
    if isinstance(offer_data, Mapping):
        extracted_families = _extract_keyword_families(
            str(offer_data.get("text") or ""),
            extracted_tools,
        )

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
        "keyword_families": extracted_families,
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
