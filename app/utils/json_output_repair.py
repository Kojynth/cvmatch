"""
JSON Output Repair Module 

Centralized JSON parsing and repair utilities for LLM outputs.
Extracted from llm_worker.py to improve maintainability.

Key features:
- Proper error logging (no silent failures)
- Multiple repair strategies
- Configurable strictness levels
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, List, Optional, Tuple, Type, Union

try:
    from pydantic import BaseModel, ValidationError
    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False
    BaseModel = None  # type: ignore
    ValidationError = Exception  # type: ignore

try:
    from ..logging.safe_logger import get_safe_logger
    from ..config import DEFAULT_PII_CONFIG
    logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


class JSONParseError(RuntimeError):
    """Raised when JSON parsing fails after all repair attempts."""

    def __init__(
        self,
        message: str,
        *,
        original_text: str = "",
        attempts: int = 0,
        last_error: str = "",
    ):
        super().__init__(message)
        self.original_text = original_text
        self.attempts = attempts
        self.last_error = last_error


def _extract_json_bounds(text: str) -> Tuple[int, int]:
    """Find the outermost JSON object or array bounds.

    Returns:
        Tuple of (start_index, end_index) or (-1, -1) if not found.
    """
    if not text:
        return -1, -1

    first_brace = text.find("{")
    first_bracket = text.find("[")

    # Determine which comes first
    if first_brace == -1 and first_bracket == -1:
        return -1, -1

    if first_brace == -1:
        start = first_bracket
        open_char, close_char = "[", "]"
    elif first_bracket == -1:
        start = first_brace
        open_char, close_char = "{", "}"
    else:
        if first_brace < first_bracket:
            start = first_brace
            open_char, close_char = "{", "}"
        else:
            start = first_bracket
            open_char, close_char = "[", "]"

    # Find matching closing character
    if open_char == "{":
        end = text.rfind("}")
    else:
        end = text.rfind("]")

    return start, end


def _repair_truncated_json(text: str) -> Optional[str]:
    """Attempt to repair truncated JSON output.

    Handles common LLM output issues:
    - Unclosed strings
    - Missing closing braces/brackets
    - Trailing commas
    """
    if not text:
        return None

    cleaned = text.strip()
    if not cleaned:
        return None

    start, _ = _extract_json_bounds(cleaned)
    if start == -1:
        return None

    candidate = cleaned[start:].rstrip()

    # Track string and structure state
    in_string = False
    escape = False
    stack: List[str] = []

    for ch in candidate:
        if escape:
            escape = False
            continue
        if ch == "\\" and in_string:
            escape = True
            continue
        if ch == '"':
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

    # Close unclosed strings
    if in_string:
        if candidate.endswith("\\"):
            candidate = candidate[:-1]
        candidate += '"'

    # Handle truncated values
    stripped = candidate.rstrip()
    if stripped.endswith(":"):
        candidate = stripped + " null"
    elif stripped.endswith(","):
        candidate = stripped[:-1]

    # Close unclosed structures
    if stack:
        closing = "".join("}" if opener == "{" else "]" for opener in reversed(stack))
        candidate += closing

    # Return only if we made changes
    if candidate == cleaned[start:].rstrip():
        return None

    return candidate


def _repair_common_issues(text: str) -> str:
    """Fix common JSON formatting issues from LLM outputs."""
    if not text:
        return text

    result = text

    # Remove JavaScript-style comments
    result = re.sub(r"//[^\n]*\n", "\n", result)
    result = re.sub(r"/\*.*?\*/", "", result, flags=re.DOTALL)

    # Fix trailing commas before closing braces/brackets
    result = re.sub(r",\s*([\]}])", r"\1", result)

    # Fix unquoted keys (simple cases only)
    result = re.sub(r'(?<=[{,])\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r' "\1":', result)

    return result


def _try_extract_json_from_markdown(text: str) -> Optional[str]:
    """Extract JSON from markdown code blocks."""
    if not text:
        return None

    # Try to find JSON in code blocks
    patterns = [
        r"```json\s*([\s\S]*?)\s*```",
        r"```\s*([\s\S]*?)\s*```",
        r"`([\s\S]*?)`",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            candidate = match.group(1).strip()
            if candidate.startswith(("{", "[")):
                return candidate

    return None


def parse_json_response(
    text: str,
    *,
    strict: bool = False,
    log_errors: bool = True,
    context: str = "",
) -> Dict[str, Any]:
    """Parse JSON from LLM output with repair capabilities.

    Args:
        text: Raw text output from LLM
        strict: If True, raise JSONParseError on failure instead of returning {}
        log_errors: If True, log parsing errors
        context: Optional context string for logging (e.g., "offer_keywords stage")

    Returns:
        Parsed JSON dict, or empty dict on failure (unless strict=True)

    Raises:
        JSONParseError: If strict=True and parsing fails
    """
    context_prefix = f"[{context}] " if context else ""
    attempts = 0
    last_error = ""

    if not text:
        if log_errors:
            logger.debug("%sEmpty input text for JSON parsing", context_prefix)
        if strict:
            raise JSONParseError(
                f"{context_prefix}Empty input text",
                original_text="",
                attempts=0,
                last_error="Empty input",
            )
        return {}

    cleaned = text.strip()

    # Attempt 1: Direct parse
    attempts += 1
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        last_error = str(exc)

    # Attempt 2: Extract JSON bounds
    attempts += 1
    start, end = _extract_json_bounds(cleaned)
    if start != -1 and end != -1 and end > start:
        candidate = cleaned[start:end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_error = str(exc)

    # Attempt 3: Try markdown extraction
    attempts += 1
    markdown_json = _try_extract_json_from_markdown(cleaned)
    if markdown_json:
        try:
            return json.loads(markdown_json)
        except json.JSONDecodeError as exc:
            last_error = str(exc)

    # Attempt 4: Common issue repairs
    attempts += 1
    repaired = _repair_common_issues(cleaned)
    if repaired != cleaned:
        try:
            return json.loads(repaired)
        except json.JSONDecodeError as exc:
            last_error = str(exc)

    # Attempt 5: Truncation repair
    attempts += 1
    truncation_repaired = _repair_truncated_json(cleaned)
    if truncation_repaired:
        try:
            return json.loads(truncation_repaired)
        except json.JSONDecodeError as exc:
            last_error = str(exc)

    # Attempt 6: Try external repair if available
    attempts += 1
    try:
        from .json_strict import attempt_json_repair
        external_repaired = attempt_json_repair(cleaned)
        if external_repaired:
            try:
                return json.loads(external_repaired)
            except json.JSONDecodeError as exc:
                last_error = str(exc)
    except ImportError:
        pass

    # All attempts failed
    if log_errors:
        snippet_len = 120
        snippet = cleaned[:snippet_len] if len(cleaned) > snippet_len else cleaned
        snippet = snippet.replace("\n", "\\n")
        logger.warning(
            "%sJSON parse failed after %d attempts. Last error: %s. Text snippet: %s",
            context_prefix,
            attempts,
            last_error,
            snippet,
        )

    if strict:
        raise JSONParseError(
            f"{context_prefix}JSON parsing failed after {attempts} attempts",
            original_text=text,
            attempts=attempts,
            last_error=last_error,
        )

    return {}


def validate_json_with_schema(
    payload: Dict[str, Any],
    schema_model: Type[BaseModel],
    *,
    coerce: bool = True,
    context: str = "",
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Validate parsed JSON against a Pydantic schema.

    Args:
        payload: Parsed JSON dictionary
        schema_model: Pydantic model class for validation
        coerce: If True, attempt to coerce invalid fields
        context: Optional context for logging

    Returns:
        Tuple of (validated_dict, error_message)
        - If successful: (validated_dict, None)
        - If failed: (None, error_message)
    """
    if not PYDANTIC_AVAILABLE:
        logger.warning("Pydantic not available for schema validation")
        return payload, None

    context_prefix = f"[{context}] " if context else ""

    try:
        validated = schema_model.model_validate(payload)
        return validated.model_dump(), None
    except ValidationError as exc:
        error_msg = str(exc)
        logger.debug(
            "%sSchema validation failed: %s",
            context_prefix,
            error_msg[:200],
        )
        return None, error_msg


def parse_and_validate(
    text: str,
    schema_model: Type[BaseModel],
    *,
    strict: bool = False,
    context: str = "",
) -> Tuple[Dict[str, Any], Optional[str]]:
    """Combined parse and validate operation.

    Args:
        text: Raw LLM output
        schema_model: Pydantic model for validation
        strict: Raise on parse failure
        context: Logging context

    Returns:
        Tuple of (parsed_dict, error_message)
    """
    payload = parse_json_response(text, strict=strict, context=context)

    if not payload:
        return {}, "Empty or invalid JSON"

    validated, error = validate_json_with_schema(
        payload, schema_model, context=context
    )

    if validated is not None:
        return validated, None

    return payload, error


def summarize_json_for_log(text: str, max_chars: int = 180) -> str:
    """Create a log-safe summary of JSON text."""
    if not text:
        return ""
    snippet = text.strip()
    snippet = snippet.replace("\r", "").replace("\n", "\\n").replace("\t", "\\t")
    if len(snippet) > max_chars:
        snippet = snippet[:max_chars] + "..."
    # Replace non-printable characters
    return re.sub(r"[^ -~]", "?", snippet)


def diagnose_json_issues(text: str) -> Dict[str, Any]:
    """Diagnose potential issues with JSON text for debugging.

    Returns a dict with diagnostic information:
    - length: text length
    - starts_valid: whether it starts with { or [
    - ends_valid: whether it ends with } or ]
    - brace_balance: { count minus } count
    - bracket_balance: [ count minus ] count
    - quote_count: number of double quotes
    - has_trailing_comma: whether there's a trailing comma
    """
    if not text:
        return {"length": 0, "error": "Empty text"}

    stripped = text.strip()

    return {
        "length": len(stripped),
        "starts_valid": stripped.startswith(("{", "[")),
        "ends_valid": stripped.endswith(("}", "]")),
        "brace_balance": stripped.count("{") - stripped.count("}"),
        "bracket_balance": stripped.count("[") - stripped.count("]"),
        "quote_count": stripped.count('"'),
        "has_trailing_comma": bool(re.search(r",\s*[\]}]", stripped)),
        "line_count": stripped.count("\n") + 1,
    }
