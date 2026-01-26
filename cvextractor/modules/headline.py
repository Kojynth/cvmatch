"""Extractor for candidate professional headline."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from cvextractor.modules.base_extractor import BaseExtractor
from cvextractor.shared.config import load_section_config
from cvextractor.shared.heuristics import has_min_length

if TYPE_CHECKING:  # pragma: no cover - typing helper
    from cvextractor.pipeline.context import ExtractionContext


class HeadlineExtractor(BaseExtractor):
    """Identify a short professional headline near the top of the document."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__("headline")
        self.config = config or load_section_config("headline")
        self.max_scan_lines = int(self.config.get("max_scan_lines", 10))
        self.stop_keywords = {
            token.lower() for token in self.config.get("stop_keywords", [])
        }
        self.min_words = int(self.config.get("min_words", 2))
        self.max_words = int(self.config.get("max_words", 16))

    def collect_raw(self, context: "ExtractionContext") -> Dict[str, Any]:
        return {
            "lines": [line.strip() for line in context.lines[: self.max_scan_lines]],
            "personal_info": (context.metadata or {}).get("personal_info", {}),
        }

    def normalize(
        self, raw: Dict[str, Any], context: "ExtractionContext"
    ) -> Optional[str]:
        lines: List[str] = [line for line in raw.get("lines", []) if line]
        personal_info: Dict[str, Any] = raw.get("personal_info") or {}
        name = personal_info.get("full_name")

        if not lines:
            return None

        for index, line in enumerate(lines):
            if index == 0:
                continue
            lower = line.lower()
            if any(stop in lower for stop in self.stop_keywords):
                break
            tokens = line.replace("·", " ").split()
            if not has_min_length(tokens, self.min_words):
                continue
            if len(tokens) > self.max_words:
                continue
            if name and line.strip().lower() == str(name).strip().lower():
                continue
            return line.strip()

        return None
