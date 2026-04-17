"""Secure local API-key helpers.

This module preserves the historical import path used by tests and callers while
moving the operational boundary toward `app.infra.security`.
"""

from __future__ import annotations

import os
from pathlib import Path


SERVICE_NAME = "cvmatch"
LEGACY_ENV_PREFIX = "CVMATCH_"
LEGACY_PATHS = (
    Path.home() / ".cvmatch" / "api_keys.env",
    Path("config") / "api_keys.local",
)


class SecureStorageUnavailableError(RuntimeError):
    """Raised when a secure local key store is unavailable."""


def _normalize_name(source_name: str) -> str:
    normalized = str(source_name or "").strip()
    if not normalized:
        raise ValueError("source_name must not be empty")
    return normalized


def _import_keyring():
    try:
        import keyring  # type: ignore
    except Exception:
        return None
    return keyring


def _legacy_env_name(source_name: str) -> str:
    return f"{LEGACY_ENV_PREFIX}{source_name.upper()}"


def _read_legacy(source_name: str) -> str | None:
    env_name = _legacy_env_name(_normalize_name(source_name))
    env_value = str(os.getenv(env_name) or "").strip()
    if env_value:
        return env_value

    for path in LEGACY_PATHS:
        if not path.exists():
            continue
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                if "=" not in line or line.lstrip().startswith("#"):
                    continue
                key, value = line.split("=", 1)
                if key.strip() == env_name:
                    cleaned = value.strip().strip('"').strip("'")
                    if cleaned:
                        return cleaned
        except Exception:
            continue
    return None


def get_api_key(source_name: str) -> str | None:
    source_name = _normalize_name(source_name)
    keyring_module = _import_keyring()
    if keyring_module is None:
        return None

    try:
        value = keyring_module.get_password(SERVICE_NAME, source_name)
    except Exception:
        return None

    cleaned = str(value or "").strip()
    if cleaned:
        return cleaned

    # Plaintext fallbacks are intentionally ignored in normal operation.
    return None


def set_api_key(source_name: str, value: str) -> None:
    source_name = _normalize_name(source_name)
    cleaned = str(value or "").strip()
    if not cleaned:
        raise ValueError("value must not be empty")

    keyring_module = _import_keyring()
    if keyring_module is None:
        raise SecureStorageUnavailableError(
            "Secure key store unavailable. Install and configure keyring."
        )

    try:
        keyring_module.set_password(SERVICE_NAME, source_name, cleaned)
    except Exception as exc:
        raise SecureStorageUnavailableError(
            f"Unable to store secret securely: {exc}"
        ) from exc
