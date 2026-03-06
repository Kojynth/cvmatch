"""Stage attempts and timeout configuration helpers."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional


DEFAULT_STAGE_ATTEMPTS: Dict[str, int] = {
    "offer_keywords": 2,
    "draft": 3,
    "critic": 2,
    "final": 3,
    "cover_letter": 2,
    "cover_letter_critic": 2,
}


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def resolve_stage_attempts(
    stage: str,
    *,
    survival_mode: bool = False,
    custom_parameters: Optional[Mapping[str, Any]] = None,
    env: Optional[Mapping[str, str]] = None,
    defaults: Optional[Mapping[str, int]] = None,
) -> int:
    stage_key = str(stage or "").strip().lower()
    table = dict(defaults or DEFAULT_STAGE_ATTEMPTS)
    attempts = _safe_int(table.get(stage_key, 2), 2)

    if survival_mode:
        attempts = max(attempts, 3)

    custom = dict(custom_parameters or {})
    custom_key = f"stage_attempts_{stage_key}"
    if custom_key in custom:
        attempts = max(1, _safe_int(custom.get(custom_key), attempts))
    elif "stage_attempts" in custom:
        attempts = max(1, _safe_int(custom.get("stage_attempts"), attempts))

    env_map = dict(env or {})
    env_key = f"CVMATCH_STAGE_ATTEMPTS_{stage_key.upper()}"
    if env_key in env_map:
        attempts = max(1, _safe_int(env_map.get(env_key), attempts))
    if "CVMATCH_STAGE_ATTEMPTS" in env_map:
        attempts = max(1, _safe_int(env_map.get("CVMATCH_STAGE_ATTEMPTS"), attempts))
    return max(1, attempts)


def resolve_stage_timeout_seconds(
    *,
    custom_parameters: Optional[Mapping[str, Any]] = None,
    env: Optional[Mapping[str, str]] = None,
    default: int = 0,
) -> int:
    custom = dict(custom_parameters or {})
    env_map = dict(env or {})
    timeout = _safe_int(default, 0)
    if "stage_timeout_seconds" in custom:
        timeout = _safe_int(custom.get("stage_timeout_seconds"), timeout)
    if "CVMATCH_STAGE_TIMEOUT_SECONDS" in env_map:
        timeout = _safe_int(env_map.get("CVMATCH_STAGE_TIMEOUT_SECONDS"), timeout)
    return max(0, timeout)

