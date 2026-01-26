"""Feature flag definitions for the CV extractor refactor scaffolding."""

from __future__ import annotations

import os
from typing import Set

from app import config as _root_config
from app.utils import feature_flags as _legacy_feature_flags

# Re-export legacy helpers so existing imports keep working.
_LEGACY_PUBLIC_SYMBOLS: Set[str] = {
    name for name in dir(_legacy_feature_flags) if not name.startswith("_")
}
for _name in _LEGACY_PUBLIC_SYMBOLS:
    globals()[_name] = getattr(_legacy_feature_flags, _name)


def _read_env_flag(name: str, default: bool = False) -> bool:
    """Read a boolean flag from the environment."""
    value = os.environ.get(name)
    if value is None:
        return default
    value_normalized = value.strip().lower()
    return value_normalized in {"1", "true", "yes", "on"}


_DEFAULT_PIPELINE_FLAG = True

# Environment takes precedence so QA can toggle without touching config.
ENABLE_CV_PIPELINE: bool = _read_env_flag(
    "ENABLE_CV_PIPELINE", _DEFAULT_PIPELINE_FLAG
)

# Fall back to persisted feature flag storage if no env override is set.
if not ENABLE_CV_PIPELINE:
    try:
        ENABLE_CV_PIPELINE = bool(
            _root_config.get_feature_flag(
                "enable_cv_pipeline", default=_DEFAULT_PIPELINE_FLAG
            )
        )
    except Exception:  # pragma: no cover - best effort guard
        ENABLE_CV_PIPELINE = _DEFAULT_PIPELINE_FLAG


def is_cv_pipeline_enabled() -> bool:
    """Return True when the modular CV extraction pipeline should be used."""
    return bool(ENABLE_CV_PIPELINE)


__all__ = sorted(
    set(_LEGACY_PUBLIC_SYMBOLS)
    | {"ENABLE_CV_PIPELINE", "is_cv_pipeline_enabled"}
)
