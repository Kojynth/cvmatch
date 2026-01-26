"""Data container describing the inputs for the modular pipeline."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping, MutableMapping, Optional, Sequence


@dataclass(frozen=True)
class ExtractionContext:
    """Immutable view of the data passed to pipeline modules."""

    lines: Sequence[str]
    sections: Optional[Mapping[str, Any]] = None
    metadata: Optional[Mapping[str, Any]] = None
    language: Optional[str] = None
    source: Optional[str] = None

    def with_updates(
        self,
        *,
        sections: Optional[Mapping[str, Any]] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        language: Optional[str] = None,
    ) -> "ExtractionContext":
        """Return a copy of the context with updated fields."""
        return replace(
            self,
            sections=sections if sections is not None else self.sections,
            metadata=metadata if metadata is not None else self.metadata,
            language=language if language is not None else self.language,
        )

    def get_section(self, name: str, default: Any = None) -> Any:
        """Safe accessor for optional sections."""
        if not self.sections:
            return default
        return self.sections.get(name, default)

    def derive_metadata(self) -> MutableMapping[str, Any]:
        """Return a mutable copy of the metadata, creating an empty dict if needed."""
        if self.metadata is None:
            return {}
        if isinstance(self.metadata, dict):
            return dict(self.metadata)
        return {key: self.metadata[key] for key in self.metadata}
