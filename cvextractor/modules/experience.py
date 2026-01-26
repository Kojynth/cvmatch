"""Extractor module for professional experience sections."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence

from app.utils.experience_extractor_enhanced import (
    EnhancedExperienceExtractor as LegacyExperienceExtractor,
)
from cvextractor.modules.base_extractor import BaseExtractor
from cvextractor.shared.config import load_section_config
from cvextractor.shared.heuristics import (
    DateSpan,
    SectionBounds,
    build_legacy_date_hits,
    detect_section_bounds,
    extract_date_spans,
)
from cvextractor.shared.experience_rules import (
    extract_basic_experiences,
    refine_experience_candidates,
)

if TYPE_CHECKING:  # pragma: no cover
    from cvextractor.pipeline.context import ExtractionContext


class ExperienceExtractor(BaseExtractor):
    """Bridge between the modular pipeline and the legacy experience extractor."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__("experience")
        self.config = config or load_section_config("experience")
        self._extractor = LegacyExperienceExtractor()
        self.section_keywords: Sequence[str] = tuple(
            self.config.get("section_keywords", ())
        )
        self.stop_keywords: Sequence[str] = tuple(self.config.get("stop_keywords", ()))
        self.min_date_confidence: float = float(
            self.config.get("min_date_confidence", 0.4)
        )
        self.date_window: int = int(self.config.get("date_window", 2))
        self.min_desc_tokens: int = int(self.config.get("min_description_tokens", 0))
        self.require_tri_signal: bool = bool(
            self.config.get("require_tri_signal", False)
        )
        self.max_items: Optional[int] = (
            int(self.config["max_items"])
            if self.config.get("max_items") is not None
            else None
        )
        self._diagnostics: Dict[str, Any] = {}

    def collect_raw(self, context: "ExtractionContext") -> Dict[str, Any]:
        lines = list(context.lines)
        bounds = detect_section_bounds(
            lines,
            self.section_keywords,
            stop_keywords=self.stop_keywords,
        )
        # Limit the detection window to the section, but keep original lines for legacy compatibility.
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
        legacy_date_hits = build_legacy_date_hits(date_spans)
        return {
            "lines": lines,
            "section_bounds": bounds,
            "date_spans": date_spans,
            "legacy_date_hits": legacy_date_hits,
        }

    def normalize(
        self, raw: Dict[str, Any], context: "ExtractionContext"
    ) -> List[Dict[str, Any]]:
        lines = raw.get("lines", [])
        bounds: Optional[SectionBounds] = raw.get("section_bounds")
        date_hits = raw.get("legacy_date_hits") or []

        modular_candidates: List[Dict[str, Any]] = []
        section_lines: Sequence[str]
        if isinstance(bounds, SectionBounds):
            section_lines = lines[bounds.start : bounds.end]
            offset = bounds.start
        else:
            section_lines = lines
            offset = 0

        candidates = extract_basic_experiences(
            section_lines,
            line_offset=offset,
            date_spans=raw.get("date_spans", []),
        )
        (
            candidate_payload,
            education_handoff,
            experience_metrics,
        ) = refine_experience_candidates(
            context.lines if hasattr(context, "lines") else lines,
            candidates,
            require_tri_signal=self.require_tri_signal,
            min_description_tokens=self.min_desc_tokens,
            max_items=self.max_items,
        )
        candidate_payloads = candidate_payload

        try:
            extraction = self._extractor.extract_experiences_with_gates(
                lines,
                section_bounds=(
                    bounds.as_tuple if isinstance(bounds, SectionBounds) else None
                ),
                date_hits=date_hits,
            )
        except Exception:  # pragma: no cover - defensive guard
            self.logger.exception("experience.extractor_failed")
            self._diagnostics = {
                "section_detected": isinstance(bounds, SectionBounds),
                "date_spans": len(raw.get("date_spans", [])),
                "date_hits": len(date_hits),
                "errored": True,
            }
            return []

        experiences = (
            extraction.get("experiences")
            if isinstance(extraction, dict)
            else extraction
        )
        payload = experiences or []

        self._diagnostics = {
            "section_detected": isinstance(bounds, SectionBounds),
            "section_bounds": (
                bounds.as_tuple if isinstance(bounds, SectionBounds) else None
            ),
            "date_spans": len(raw.get("date_spans", [])),
            "date_hits": len(date_hits),
            "legacy_method": (
                extraction.get("method") if isinstance(extraction, dict) else None
            ),
            "extracted_items": len(payload),
            "modular_candidates": experience_metrics.get("tri_signal_filtered", 0),
            "modular_payload": len(candidate_payloads),
            "modular_transfer_to_education": experience_metrics.get(
                "demoted_to_education", 0
            ),
            "modular_rebind_stats": experience_metrics.get("rebind_stats", {}),
            "modular_quality_issues": experience_metrics.get("quality_issues", []),
            "modular_pattern_diversity": experience_metrics.get("pattern_diversity"),
        }
        if payload:
            seen_keys = {
                (
                    item.get("title"),
                    item.get("company"),
                    item.get("dates"),
                )
                for item in payload
            }
            for candidate in candidate_payloads:
                key = (
                    candidate.get("title"),
                    candidate.get("company"),
                    candidate.get("dates"),
                )
                if key not in seen_keys:
                    payload.append(candidate)
                    seen_keys.add(key)
        elif candidate_payloads:
            payload = candidate_payloads
        return payload

    def diagnostics(self) -> Dict[str, Any]:
        """Expose heuristics information for integration tests."""
        return self._diagnostics
