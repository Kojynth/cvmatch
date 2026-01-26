"""Extractor for skill lists."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from cvextractor.modules.base_extractor import BaseExtractor
from cvextractor.shared.config import load_section_config
from cvextractor.shared.heuristics import ensure_tuple

if TYPE_CHECKING:  # pragma: no cover
    from cvextractor.pipeline.context import ExtractionContext


class SkillsExtractor(BaseExtractor):
    """Parse core and technical skills listed in the CV."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__("skills")
        self.config = config or load_section_config("skills")
        self.section_keywords = {kw.lower() for kw in self.config.get("keywords", [])}
        self.delimiters = ensure_tuple(
            self.config.get("delimiter_tokens", (",", ";", "|", "•"))
        )
        pattern = (
            "|".join(re.escape(delim) for delim in self.delimiters)
            if self.delimiters
            else None
        )
        self._split_pattern = re.compile(pattern) if pattern else None

    def collect_raw(self, context: "ExtractionContext") -> Dict[str, Any]:
        return {"lines": list(context.lines)}

    def normalize(
        self, raw: Dict[str, Any], context: "ExtractionContext"
    ) -> List[Dict[str, str]]:
        lines: List[str] = raw.get("lines", [])
        sections = self._locate_sections(lines)
        skills: List[Dict[str, str]] = []
        seen: set = set()

        for section in sections:
            for skill in self._tokenize(section):
                normalized = skill.strip()
                if not normalized:
                    continue
                key = normalized.lower()
                if key in seen:
                    continue
                seen.add(key)
                skills.append({"name": normalized})

        return skills

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

    def _tokenize(self, lines: List[str]) -> List[str]:
        tokens: List[str] = []
        for line in lines:
            parts = self._split_pattern.split(line) if self._split_pattern else [line]
            for part in parts:
                cleaned = part.strip(" •\t-—").strip()
                if cleaned:
                    tokens.append(self._normalize_token(cleaned))
        return tokens

    @staticmethod
    def _normalize_token(token: str) -> str:
        token = token.replace("/", " / ").replace("_", " ")
        normalized = " ".join(
            segment.capitalize() if segment.isalpha() else segment
            for segment in token.split()
        )
        return normalized.strip()
