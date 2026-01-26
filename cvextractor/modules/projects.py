"""Extractor for project summaries."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from cvextractor.modules.base_extractor import BaseExtractor
from cvextractor.shared.config import load_section_config
from cvextractor.shared.heuristics import ensure_tuple

if TYPE_CHECKING:  # pragma: no cover
    from cvextractor.pipeline.context import ExtractionContext


class ProjectsExtractor(BaseExtractor):
    """Capture personal or professional projects."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__("projects")
        self.config = config or load_section_config("projects")
        self.section_keywords = {kw.lower() for kw in self.config.get("keywords", [])}
        self.bullet_tokens = ensure_tuple(
            self.config.get("bullet_tokens", ("-", "•", "*"))
        )
        self.max_items = int(self.config.get("max_items", 8))

    def collect_raw(self, context: "ExtractionContext") -> Dict[str, Any]:
        return {"lines": list(context.lines)}

    def normalize(
        self, raw: Dict[str, Any], context: "ExtractionContext"
    ) -> List[Dict[str, str]]:
        lines: List[str] = raw.get("lines", [])
        sections = self._locate_sections(lines)
        projects: List[Dict[str, str]] = []

        for section in sections:
            for item in self._extract_items(section):
                if len(projects) >= self.max_items:
                    break
                projects.append(item)
            if len(projects) >= self.max_items:
                break

        return projects

    def post_process(
        self, data: List[Dict[str, str]], context: "ExtractionContext"
    ) -> List[Dict[str, str]]:
        return data

    def _locate_sections(self, lines: List[str]) -> List[List[str]]:
        sections: List[List[str]] = []
        current: List[str] = []
        capture = False

        for line in lines:
            stripped = line.strip()
            if not stripped:
                if capture and current:
                    sections.append(current)
                capture = False
                current = []
                continue

            lower = stripped.lower()
            if any(keyword in lower for keyword in self.section_keywords):
                capture = True
                current = []
                continue

            if capture:
                current.append(stripped)

        if capture and current:
            sections.append(current)

        return sections

    def _extract_items(self, lines: List[str]) -> List[Dict[str, str]]:
        items: List[Dict[str, str]] = []
        for line in lines:
            bullet = self._strip_bullet(line)
            if not bullet:
                continue
            title, summary = self._split_title_summary(bullet)
            item: Dict[str, str] = {"title": title}
            if summary:
                item["summary"] = summary
            items.append(item)
        return items

    def _strip_bullet(self, line: str) -> str:
        for bullet in self.bullet_tokens:
            if line.startswith(bullet):
                return line[len(bullet) :].strip()
        return line

    def _split_title_summary(self, text: str) -> tuple[str, Optional[str]]:
        parts = re.split(r"[:\-–]", text, maxsplit=1)
        if len(parts) == 2:
            title = parts[0].strip()
            summary = parts[1].strip()
            return title or text, summary or None
        return text.strip(), None
