"""Foundation classes for the modular CV extraction pipeline."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Protocol, runtime_checkable

from app.logging.safe_logger import get_safe_logger

if False:  # pragma: no cover - for type checkers only
    from cvextractor.pipeline.context import ExtractionContext


@runtime_checkable
class SupportsDiagnostics(Protocol):
    """Optional hook for modules that expose diagnostics metadata."""

    def diagnostics(self) -> Dict[str, Any]:
        """Return diagnostics collected during the run."""


@dataclass
class ModuleRun:
    """Container for per-module results."""

    section: str
    payload: Any
    diagnostics: Dict[str, Any] = field(default_factory=dict)


class BaseExtractor(ABC):
    """Template method implementation for future extraction modules."""

    section: str

    def __init__(self, section: str, *, name: Optional[str] = None) -> None:
        self.section = section
        logger_name = name or f"cvextractor.modules.{section}"
        self.logger = get_safe_logger(logger_name)

    def run(self, context: "ExtractionContext") -> ModuleRun:
        """Execute the extraction flow for the module."""
        self.logger.debug("module.start", extra={"section": self.section})
        raw = self.collect_raw(context)
        normalized = self.normalize(raw, context)
        payload = self.post_process(normalized, context)

        diagnostics: Dict[str, Any] = {}
        if isinstance(self, SupportsDiagnostics):
            try:
                diagnostics = self.diagnostics() or {}
            except Exception:  # pragma: no cover - diagnostics are best effort
                self.logger.exception(
                    "module.diagnostics_failed", extra={"section": self.section}
                )

        self.logger.debug(
            "module.end",
            extra={"section": self.section, "has_payload": payload is not None},
        )
        return ModuleRun(section=self.section, payload=payload, diagnostics=diagnostics)

    @abstractmethod
    def collect_raw(self, context: "ExtractionContext") -> Any:
        """Collect domain specific raw data from the context."""

    def normalize(self, raw: Any, context: "ExtractionContext") -> Any:
        """Default normalization step."""
        return raw

    def post_process(self, data: Any, context: "ExtractionContext") -> Any:
        """Final adjustments before merging the payload into the pipeline result."""
        return data
