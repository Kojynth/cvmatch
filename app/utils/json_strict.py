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


def _attempt_truncated_json_repair(text: str) -> Optional[str]:
    """Best-effort repair for truncated JSON output.

    This only runs after json.loads fails, so it should be conservative.
    It tries to close open strings/braces/brackets and remove trailing commas.
    """
    if not text:
        return None
    cleaned = text.strip()
    if not cleaned:
        return None
    first_obj = cleaned.find("{")
    first_arr = cleaned.find("[")
    starts = [idx for idx in (first_obj, first_arr) if idx >= 0]
    if not starts:
        return None
    start_idx = min(starts)
    original = cleaned[start_idx:].rstrip()

    in_string = False
    escape = False
    stack = []
    for ch in original:
        if escape:
            escape = False
            continue
        if ch == "\\" and in_string:
            escape = True
            continue
        if ch == "\"":
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            stack.append("{")
        elif ch == "[":
            stack.append("[")
        elif ch == "}" and stack and stack[-1] == "{":
            stack.pop()
        elif ch == "]" and stack and stack[-1] == "[":
            stack.pop()

    candidate = original.rstrip()
    if in_string:
        if candidate.endswith("\\"):
            candidate = candidate[:-1]
        candidate += "\""

    stripped = candidate.rstrip()
    if stripped.endswith(":"):
        candidate = stripped + " null"
    elif stripped.endswith(","):
        candidate = stripped[:-1]

    if stack:
        closing = "".join("}" if opener == "{" else "]" for opener in reversed(stack))
        candidate += closing

    if candidate == original:
        return None
    return candidate


def attempt_json_repair(text: str) -> Optional[str]:
    """Public wrapper for best-effort JSON repair."""
    return _attempt_truncated_json_repair(text)


def _coerce_critic_payload(payload: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return None
    changed = False

    scorecard = payload.get("scorecard")
    if not isinstance(scorecard, dict):
        scorecard = {}
        payload["scorecard"] = scorecard
        changed = True

    def _coerce_int(value: Any, default: int) -> int:
        try:
            return int(value)
        except Exception:
            return default

    for key in ("ats_keyword_coverage", "clarity", "evidence_metrics", "consistency"):
        if key not in scorecard:
            scorecard[key] = 50
            changed = True
        else:
            coerced = _coerce_int(scorecard.get(key), 50)
            if scorecard.get(key) != coerced:
                scorecard[key] = coerced
                changed = True

    if not isinstance(payload.get("rewrite_prompt"), str):
        value = payload.get("rewrite_prompt")
        payload["rewrite_prompt"] = "" if value is None else str(value)
        changed = True

    for key in ("issues", "missing_keywords", "rewrite_plan", "must_keep_facts"):
        value = payload.get(key)
        if value is None:
            payload[key] = []
            changed = True
        elif not isinstance(value, list):
            payload[key] = [value]
            changed = True

    issues = []
    allowed_severity = {"blocker", "high", "medium", "low"}
    allowed_category = {
        "ATS",
        "structure",
        "evidence",
        "relevance",
        "style",
        "consistency",
        "formatting",
        "language",
    }
    for entry in payload.get("issues") or []:
        if not isinstance(entry, dict):
            changed = True
            continue
        issue = dict(entry)
        if issue.get("severity") not in allowed_severity:
            issue["severity"] = "low"
            changed = True
        if issue.get("category") not in allowed_category:
            issue["category"] = "relevance"
            changed = True
        for field in ("problem", "evidence", "fix"):
            if not isinstance(issue.get(field), str):
                value = issue.get(field)
                issue[field] = "" if value is None else str(value)
                changed = True
        issues.append(issue)
    payload["issues"] = issues

    if changed:
        logger.warning("Strict JSON critic payload coerced to required fields.")
    return payload


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
        payload = None
        try:
            payload = json.loads(stripped)
        except Exception as exc:
            repaired = _attempt_truncated_json_repair(stripped)
            if repaired:
                try:
                    payload = json.loads(repaired)
                    stripped = repaired
                    logger.warning(
                        "Strict JSON repaired output: role=%s attempt=%s", role, attempt
                    )
                except Exception:
                    payload = None
            if payload is None:
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
                            target_new = base_new or max(256, base_total - base_input)
                            target_new = max(256, int(target_new * 0.7))
                            cap_new = 1200 if role == "generator" else 1600
                            new_max = min(target_new, cap_new)
                            reduced_total = min(base_total, reduced_input + new_max)
                            retry_role_params = {
                                **(role_params or {}),
                                "max_input_tokens": reduced_input,
                                "max_new_tokens": new_max,
                                "max_total_tokens": reduced_total,
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

        if role == "critic":
            coerced = _coerce_critic_payload(payload)
            if coerced is not None:
                payload = coerced
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
