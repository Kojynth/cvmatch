"""PII-safe logging helpers for LinkedIn extraction."""

from __future__ import annotations

from typing import Any, Dict

from ...logging.safe_logger import get_safe_logger
from ...config import DEFAULT_PII_CONFIG

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


class LinkedInLogger:
    """Thin façade around the existing safe logger."""

    def log_summary(self, payload: Dict[str, Any]) -> None:
        logger.info("[LinkedIn] Extraction summary placeholder: %s", list(payload.keys()))


__all__ = ["LinkedInLogger"]
