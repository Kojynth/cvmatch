"""Targeted second-pass LLM retry for offer-keywords extraction."""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, Mapping, Optional

from .offer_keywords_quality import (
    extract_offer_text_from_offer_data,
    is_offer_keywords_payload_weak,
)
from .offer_enrichment import prepare_offer_text


def _trim_text(value: Any, max_chars: int) -> str:
    text = "" if value is None else str(value).strip()
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _build_retry_messages(
    *,
    base_messages: Mapping[str, str],
    offer_data: Optional[Mapping[str, Any]],
    language_code: str,
    previous_payload: Mapping[str, Any],
) -> Dict[str, str]:
    raw_offer_text = extract_offer_text_from_offer_data(offer_data)
    job_title = str((offer_data or {}).get("job_title") or "")
    company = str((offer_data or {}).get("company") or "")
    previous_block = _trim_text(json.dumps(dict(previous_payload or {}), ensure_ascii=False), 1400)
    base_user = _trim_text((base_messages or {}).get("user", ""), 1400)
    offer_text = prepare_offer_text(
        dict(offer_data or {}),
        max_chars=3400,
        keywords=[job_title, company],
    ) or raw_offer_text

    system_prompt = (
        "You extract ATS-focused offer keywords. Return JSON only matching the schema. "
        "Prioritize precision and coverage from JOB_OFFER_TEXT. "
        "Do not invent terms that are not supported by text evidence."
    )

    user_prompt = f"""
LANGUAGE: {language_code}
JOB_TITLE: {job_title}
COMPANY: {company}
JOB_OFFER_TEXT:
{_trim_text(offer_text, 3400)}

BASE_PROMPT_CONTEXT:
{base_user}

PREVIOUS_WEAK_OUTPUT_JSON:
{previous_block}

RETRY TARGET:
- Improve extraction coverage while staying factual.
- Ensure non-empty actionable output when offer text is substantive.
- Prefer at least: keywords>=8, skills>=4, tools>=2 when evidence exists.
- Prioritize requirement-heavy sections first: role summary, responsibilities,
  requirements, stack/tools, "about you", and ideal profile.
- Down-rank company marketing, culture, benefits, remote policy, and hiring
  process unless they contain a real domain term needed for context.

OUTPUT RULES:
- Return JSON only.
- Keep lists concise and deduplicated.
- Prefer MULTI-WORD phrases ("test automation", "code review", "API design")
  over bare single tokens. Only emit a bare token when it is an acronym
  (SQL, REST, API, ML, AI) or a proper noun (Docker, Python, Kubernetes).
- skills = hard skills/tech stack.
- tools = software/framework/platform names.
- responsibilities = short action phrases.
""".strip()

    return {"system": system_prompt, "user": user_prompt}


def run_offer_keywords_second_pass(
    *,
    base_messages: Mapping[str, str],
    current_payload: Mapping[str, Any],
    offer_data: Optional[Mapping[str, Any]],
    language_code: str,
    qwen_manager: Any,
    parse_json_response: Callable[[str], Dict[str, Any]],
    progress_callback: Optional[Any] = None,
    logger: Any = None,
) -> Optional[Dict[str, Any]]:
    """Retry extraction with a stronger targeted prompt when output is weak."""
    offer_text = extract_offer_text_from_offer_data(offer_data)
    if not is_offer_keywords_payload_weak(current_payload, offer_text=offer_text):
        return dict(current_payload or {})

    from ..schemas.offer_keywords_schema import OfferKeywordsJSON
    from .json_strict import JsonStrictError, generate_json_with_schema

    messages = _build_retry_messages(
        base_messages=base_messages,
        offer_data=offer_data,
        language_code=language_code,
        previous_payload=current_payload,
    )

    role_params = {
        "temperature": 0.0,
        "top_p": 0.9,
        "top_k": 40,
        "max_input_tokens": 2600,
        "max_new_tokens": 850,
        "max_total_tokens": 3450,
    }

    try:
        strict_retry = generate_json_with_schema(
            role="offer_critic",
            schema_model=OfferKeywordsJSON,
            messages=messages,
            qwen_manager=qwen_manager,
            retries=2,
            progress_callback=progress_callback,
            role_params=role_params,
        )
        if not is_offer_keywords_payload_weak(strict_retry, offer_text=offer_text):
            if logger:
                logger.info("Offer keywords second-pass strict retry succeeded.")
            return strict_retry
    except JsonStrictError as exc:
        if logger:
            logger.warning("Offer keywords second-pass strict retry failed: %s", exc)
    except Exception as exc:
        if logger:
            logger.warning("Offer keywords second-pass strict retry error: %s", exc)

    try:
        raw = qwen_manager.generate_structured_json(
            messages["system"],
            messages["user"],
            progress_callback,
            generation_overrides={
                "temperature": 0.0,
                "top_p": 0.9,
                "top_k": 40,
                "max_new_tokens": 850,
                "do_sample": False,
                "repetition_penalty": 1.05,
            },
            role="offer_critic",
        )
        payload = parse_json_response(raw)
        if not payload:
            return None

        try:
            payload = OfferKeywordsJSON.model_validate(payload).model_dump()
        except Exception:
            pass

        if not is_offer_keywords_payload_weak(payload, offer_text=offer_text):
            if logger:
                logger.info("Offer keywords second-pass non-strict retry succeeded.")
            return payload
    except Exception as exc:
        if logger:
            logger.warning("Offer keywords second-pass non-strict retry error: %s", exc)

    return None
