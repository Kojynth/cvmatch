"""Result dataclasses for the modular extraction pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ModuleReport:
    """Introspection data for individual module runs."""

    name: str
    section: str
    status: str
    diagnostics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModuleError:
    """Captured error produced by a module run."""

    name: str
    section: str
    message: str


@dataclass
class PipelineResult:
    """Aggregated output of the extraction pipeline."""

    payload: Dict[str, Any]
    used_legacy: bool
    modules: List[ModuleReport] = field(default_factory=list)
    errors: List[ModuleError] = field(default_factory=list)
    diagnostics: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def legacy(
        cls, payload: Dict[str, Any], diagnostics: Optional[Dict[str, Any]] = None
    ) -> "PipelineResult":
        """Convenience constructor for legacy fallback results."""
        return cls(
            payload=payload,
            used_legacy=True,
            diagnostics=diagnostics or {},
        )
