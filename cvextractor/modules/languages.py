"""Extractor for language proficiency information."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from cvextractor.modules.base_extractor import BaseExtractor
from cvextractor.shared.config import load_section_config
from cvextractor.shared.heuristics import ensure_tuple

if TYPE_CHECKING:  # pragma: no cover
    from cvextractor.pipeline.context import ExtractionContext


class LanguagesExtractor(BaseExtractor):
    """Detect spoken languages and their proficiency level."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__("languages")
        self.config = config or load_section_config("languages")
        self.section_keywords = {kw.lower() for kw in self.config.get("keywords", [])}
        self.level_markers = ensure_tuple(self.config.get("level_markers", ()))
        self.delimiters = ensure_tuple(
            self.config.get("delimiter_tokens", (",", "•", "|", "-"))
        )
        self._level_regex = (
            re.compile(
                r"|".join(re.escape(marker) for marker in self.level_markers),
                re.IGNORECASE,
            )
            if self.level_markers
            else None
        )

    def collect_raw(self, context: "ExtractionContext") -> Dict[str, Any]:
        return {"lines": list(context.lines)}

    def normalize(
        self, raw: Dict[str, Any], context: "ExtractionContext"
    ) -> List[Dict[str, str]]:
        lines: List[str] = raw.get("lines", [])
        sections = self._locate_sections(lines)
        languages: List[Dict[str, str]] = []
        seen: set = set()

        for section in sections:
            for candidate in self._tokenize(section):
                name, level = self._normalize_candidate(candidate)
                if not name:
                    continue
                key = (name.lower(), (level or "").lower())
                if key in seen:
                    continue
                seen.add(key)
                entry = {"name": name}
                if level:
                    entry["level"] = level
                languages.append(entry)

        return languages

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
        candidates: List[str] = []
        pattern = (
            re.compile("|".join(re.escape(delim) for delim in self.delimiters))
            if self.delimiters
            else None
        )
        for line in lines:
            parts = pattern.split(line) if pattern else [line]
            for part in parts:
                cleaned = part.strip(" •\t-—").strip()
                if cleaned:
                    candidates.append(cleaned)
        return candidates

    def _normalize_candidate(
        self, candidate: str
    ) -> Tuple[Optional[str], Optional[str]]:
        if not candidate:
            return None, None

        level = None
        if self._level_regex:
            match = self._level_regex.search(candidate)
            if match:
                level = match.group(0).strip()
                candidate = self._level_regex.sub("", candidate)

        tokens = [
            token.strip("()[] ").title() for token in candidate.split() if token.strip()
        ]
        if not tokens:
            return None, level

        name = " ".join(tokens)
        return name, level or None
