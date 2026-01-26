"""Strict JSON generation helper using LM Format Enforcer."""

from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, Optional, Type

from pydantic import BaseModel, ValidationError

from ..config import DEFAULT_PII_CONFIG
from ..logging.safe_logger import get_safe_logger

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


class JsonStrictError(RuntimeError):
    """Raised when strict JSON generation fails or LMFE is unavailable."""


def ensure_lmfe_available() -> None:
    try:
        import lmformatenforcer  # noqa: F401
    except Exception as exc:
        raise JsonStrictError(
            "LM Format Enforcer is required for strict JSON generation."
        ) from exc


def build_lmfe_generation_kwargs(tokenizer: Any, schema: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from lmformatenforcer import JsonSchemaParser
        from lmformatenforcer.integrations import transformers as lmfe_transformers
    except Exception as exc:
        raise JsonStrictError(
            "LM Format Enforcer not available for transformers integration."
        ) from exc

    parser = JsonSchemaParser(schema)

    if hasattr(lmfe_transformers, "build_logits_processor"):
        processor = lmfe_transformers.build_logits_processor(tokenizer, parser)
        return {"logits_processor": [processor]}

    if hasattr(lmfe_transformers, "build_token_enforcer"):
        processor = lmfe_transformers.build_token_enforcer(tokenizer, parser)
        return {"logits_processor": [processor]}

    if hasattr(lmfe_transformers, "build_prefix_allowed_tokens_fn"):
        fn = lmfe_transformers.build_prefix_allowed_tokens_fn(tokenizer, parser)
        return {"prefix_allowed_tokens_fn": fn}

    if hasattr(lmfe_transformers, "build_transformers_prefix_allowed_tokens_fn"):
        fn = lmfe_transformers.build_transformers_prefix_allowed_tokens_fn(
            tokenizer, parser
        )
        return {"prefix_allowed_tokens_fn": fn}

    raise JsonStrictError("Unsupported LMFE transformers integration.")


def _summarize_output_for_log(text: str, max_chars: int = 180) -> str:
    if not text:
        return ""
    snippet = text.strip()
    snippet = snippet.replace("\r", "").replace("\n", "\\n").replace("\t", "\\t")
    if len(snippet) > max_chars:
        snippet = snippet[:max_chars] + "..."
    return re.sub(r"[^ -~]", "?", snippet)


def generate_json_with_schema(
    *,
    role: str,
    schema_model: Type[BaseModel],
    messages: Dict[str, str],
    qwen_manager: Any,
    retries: int = 3,
    progress_callback: Optional[Any] = None,
    role_params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    ensure_lmfe_available()

    system_prompt = (messages or {}).get("system") or ""
    user_prompt = (messages or {}).get("user") or ""
    if not system_prompt or not user_prompt:
        raise JsonStrictError("Missing system/user prompt for strict JSON generation.")

    def _summarize_params(params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not isinstance(params, dict):
            return {}
        keys = (
            "max_input_tokens",
            "max_new_tokens",
            "max_total_tokens",
            "temperature",
            "top_p",
            "top_k",
        )
        return {key: params.get(key) for key in keys if key in params}

    schema = schema_model.model_json_schema()
    last_error = ""
    retry_role_params: Optional[Dict[str, Any]] = None
    retry_hint = ""
    base_params: Dict[str, Any] = {}
    resolver = getattr(qwen_manager, "_resolve_role_params", None)
    if callable(resolver):
        try:
            base_params = resolver(role, role_params)
        except Exception:
            base_params = {}
    if not base_params and role_params:
        base_params = dict(role_params)
    base_input = int(base_params.get("max_input_tokens") or 0) or None
    base_new = int(base_params.get("max_new_tokens") or 0) or None
    base_total = int(base_params.get("max_total_tokens") or 0) or None
    if not base_total and base_input and base_new:
        base_total = base_input + base_new

    logger.info(
        "Strict JSON start: role=%s schema=%s retries=%s system_len=%s user_len=%s",
        role,
        getattr(schema_model, "__name__", "unknown"),
        retries,
        len(system_prompt),
        len(user_prompt),
    )
    if base_params:
        logger.info(
            "Strict JSON base params: role=%s params=%s",
            role,
            _summarize_params(base_params),
        )

    start_ts = time.time()

    for attempt in range(1, max(retries, 1) + 1):
        if progress_callback:
            progress_callback(f"[JSON] {role} attempt {attempt}/{retries}...")

        if last_error:
            prompt_suffix = (
                "\n\nPrevious output was invalid:\n"
                f"{last_error}\n\nReturn JSON only that matches the schema."
            )
        else:
            prompt_suffix = ""

        if retry_hint:
            prompt_suffix = f"{prompt_suffix}\n\n{retry_hint}".strip()

        attempt_params = retry_role_params or role_params
        if attempt_params:
            logger.info(
                "Strict JSON attempt: role=%s attempt=%s/%s params=%s",
                role,
                attempt,
                retries,
                _summarize_params(attempt_params),
            )
        output = qwen_manager.generate_structured_json_lmfe(
            system_prompt=system_prompt,
            user_prompt=f"{user_prompt}{prompt_suffix}",
            schema=schema,
            role=role,
            progress_callback=progress_callback,
            role_params=attempt_params,
        )

        if not output or not output.strip():
            logger.warning("Strict JSON empty output: role=%s attempt=%s", role, attempt)
            last_error = "Empty output."
            continue

        stripped = output.strip()
        logger.info(
            "Strict JSON output received: role=%s attempt=%s len=%s",
            role,
            attempt,
            len(stripped),
        )
        try:
            payload = json.loads(stripped)
        except Exception as exc:
            meta = ""
            if stripped:
                ends_with = stripped[-1]
                brace_delta = stripped.count("{") - stripped.count("}")
                bracket_delta = stripped.count("[") - stripped.count("]")
                quote_count = stripped.count('"')
                line_count = stripped.count("\n") + 1
                meta = (
                    f" len={len(stripped)} endswith={ends_with} brace_delta={brace_delta}"
                    f" bracket_delta={bracket_delta} quotes={quote_count} lines={line_count}"
                )
                if not stripped.endswith(("}", "]")) or brace_delta != 0:
                    retry_hint = (
                        "Output was truncated. Return a shorter JSON: "
                        "limit list sizes and keep string values concise."
                    )
                    if base_total and base_input:
                        reduced_input = max(512, int(base_input * 0.85))
                        new_max = max(64, base_total - reduced_input)
                        retry_role_params = {
                            **(role_params or {}),
                            "max_input_tokens": reduced_input,
                            "max_new_tokens": new_max,
                            "max_total_tokens": base_total,
                        }
                        logger.warning(
                            "Strict JSON retry params adjusted: role=%s attempt=%s params=%s",
                            role,
                            attempt,
                            _summarize_params(retry_role_params),
                        )
            last_error = f"Invalid JSON: {exc}{meta}"
            logger.warning(
                "Strict JSON parse failed: role=%s attempt=%s error=%s",
                role,
                attempt,
                last_error,
            )
            if stripped:
                head = _summarize_output_for_log(stripped[:240], 240)
                tail = _summarize_output_for_log(stripped[-240:], 240)
                logger.warning(
                    "Strict JSON output snippet: role=%s attempt=%s head=%s tail=%s",
                    role,
                    attempt,
                    head,
                    tail,
                )
            continue

        try:
            parsed = schema_model.model_validate(payload)
            elapsed = time.time() - start_ts
            logger.info(
                "Strict JSON success: role=%s attempt=%s elapsed=%.2fs",
                role,
                attempt,
                elapsed,
            )
            return parsed.model_dump()
        except ValidationError as exc:
            last_error = str(exc)
            logger.warning(
                "Strict JSON validation failed: role=%s attempt=%s error=%s",
                role,
                attempt,
                last_error,
            )
            continue

    elapsed = time.time() - start_ts
    logger.warning(
        "Strict JSON failed: role=%s elapsed=%.2fs error=%s",
        role,
        elapsed,
        last_error,
    )
    raise JsonStrictError(
        f"Strict JSON generation failed for role '{role}' after {retries} attempts. {last_error}"
    )
