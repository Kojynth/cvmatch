"""Extractor for interests/hobbies sections."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from cvextractor.modules.base_extractor import BaseExtractor
from cvextractor.shared.config import load_section_config
from cvextractor.shared.heuristics import ensure_tuple

if TYPE_CHECKING:  # pragma: no cover - typing only
    from cvextractor.pipeline.context import ExtractionContext


class InterestsExtractor(BaseExtractor):
    """Extract bullet-like interests entries from contextual sections."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__("interests")
        self.config = config or load_section_config("interests")
        self.section_keywords = {
            keyword.lower() for keyword in self.config.get("section_keywords", [])
        }
        self.split_tokens = ensure_tuple(
            self.config.get("split_tokens", [",", "•", ";", "|", "-"])
        )
        self.max_items = int(self.config.get("max_items", 10))

    def collect_raw(self, context: "ExtractionContext") -> Dict[str, Any]:
        lines = list(context.lines)
        section_spans = self._locate_interest_sections(lines)
        return {"sections": section_spans}

    def normalize(
        self, raw: Dict[str, Any], context: "ExtractionContext"
    ) -> List[Dict[str, str]]:
        sections: List[List[str]] = raw.get("sections", [])
        items: List[str] = []

        for section in sections:
            items.extend(self._split_items(section))
            if len(items) >= self.max_items:
                break

        return [{"label": item} for item in items[: self.max_items]]

    def post_process(
        self, data: List[Dict[str, str]], context: "ExtractionContext"
    ) -> List[Dict[str, str]]:
        return data

    def _locate_interest_sections(self, lines: List[str]) -> List[List[str]]:
        collected: List[List[str]] = []
        current: List[str] = []
        capture = False

        for line in lines:
            stripped = line.strip()
            if not stripped:
                if capture and current:
                    collected.append(current)
                capture = False
                current = []
                continue

            lower = stripped.lower()
            if self.section_keywords and any(
                keyword in lower for keyword in self.section_keywords
            ):
                capture = True
                current = []
                continue

            if capture:
                current.append(stripped)

        if capture and current:
            collected.append(current)

        return collected

    def _split_items(self, lines: List[str]) -> List[str]:
        items: List[str] = []
        separators = "|".join(re.escape(token) for token in self.split_tokens)
        pattern = re.compile(separators) if separators else None

        for line in lines:
            candidate_segments = pattern.split(line) if pattern else [line]
            for candidate in candidate_segments:
                cleaned = candidate.strip(" •\t-").strip()
                if cleaned:
                    items.append(cleaned)

        return items
