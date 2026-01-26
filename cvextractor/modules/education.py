"""Extractor module for education sections."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence

from app.utils.education_extractor_enhanced import (
    EducationExtractor as LegacyEducationExtractor,
)
from cvextractor.modules.base_extractor import BaseExtractor
from cvextractor.shared.config import load_section_config
from cvextractor.shared.heuristics import (
    DateSpan,
    SectionBounds,
    detect_section_bounds,
    extract_date_spans,
)
from cvextractor.shared.experience_rules import (
    as_payload,
    extract_basic_education,
    refine_education_candidates,
)

if TYPE_CHECKING:  # pragma: no cover
    from cvextractor.pipeline.context import ExtractionContext


class EducationExtractor(BaseExtractor):
    """Bridge between the modular pipeline and the legacy education extractor."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__("education")
        self.config = config or load_section_config("education")
        self._extractor = LegacyEducationExtractor()
        self.section_keywords: Sequence[str] = tuple(
            self.config.get("section_keywords", ())
        )
        self.stop_keywords: Sequence[str] = tuple(self.config.get("stop_keywords", ()))
        self.min_date_confidence: float = float(
            self.config.get("min_date_confidence", 0.35)
        )
        self.date_window: int = int(self.config.get("date_window", 2))
        self._diagnostics: Dict[str, Any] = {}

    def collect_raw(self, context: "ExtractionContext") -> Dict[str, Any]:
        lines = list(context.lines)
        bounds = detect_section_bounds(
            lines,
            self.section_keywords,
            stop_keywords=self.stop_keywords,
        )
        section_lines = (
            lines[bounds.start : bounds.end]
            if isinstance(bounds, SectionBounds)
            else lines
        )
        date_spans: List[DateSpan] = extract_date_spans(
            section_lines,
            start_offset=bounds.start if isinstance(bounds, SectionBounds) else 0,
            window=self.date_window,
            min_confidence=self.min_date_confidence,
            global_lines=lines,
        )
        return {
            "lines": lines,
            "section_bounds": bounds,
            "date_spans": date_spans,
        }

    def normalize(
        self, raw: Dict[str, Any], context: "ExtractionContext"
    ) -> List[Dict[str, Any]]:
        lines = raw.get("lines", [])
        bounds: Optional[SectionBounds] = raw.get("section_bounds")

        if isinstance(bounds, SectionBounds):
            section_lines: Sequence[str] = lines[bounds.start : bounds.end]
            offset = bounds.start
        else:
            section_lines = lines
            offset = 0

        candidates = extract_basic_education(
            section_lines,
            line_offset=offset,
            date_spans=raw.get("date_spans", []),
        )
        modular_candidates = refine_education_candidates(
            candidates,
            max_items=self.config.get("max_items"),
        )
        candidate_payload = as_payload(modular_candidates)

        try:
            result = self._extractor.extract_education_two_pass(
                lines,
                section_bounds=(
                    bounds.as_tuple if isinstance(bounds, SectionBounds) else None
                ),
            )
        except Exception:  # pragma: no cover - defensive guard
            self.logger.exception("education.extractor_failed")
            self._diagnostics = {
                "section_detected": isinstance(bounds, SectionBounds),
                "date_spans": len(raw.get("date_spans", [])),
                "errored": True,
            }
            return []

        items = result.get("items", []) if isinstance(result, dict) else []
        payload = items or []

        self._diagnostics = {
            "section_detected": isinstance(bounds, SectionBounds),
            "section_bounds": (
                bounds.as_tuple if isinstance(bounds, SectionBounds) else None
            ),
            "date_spans": len(raw.get("date_spans", [])),
            "metrics": result.get("metrics") if isinstance(result, dict) else None,
            "extracted_items": len(payload),
            "modular_candidates": len(modular_candidates),
            "modular_payload": len(candidate_payload),
        }
        if not payload and candidate_payload:
            payload = candidate_payload
        return payload

    def diagnostics(self) -> Dict[str, Any]:
        """Expose heuristics information for integration tests."""
        return self._diagnostics
