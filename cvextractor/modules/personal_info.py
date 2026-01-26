"""Extractor for personal information (email, phone, summary, etc.)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional

from cvextractor.modules.base_extractor import BaseExtractor
from cvextractor.shared.config import load_section_config
from cvextractor.shared.heuristics import has_min_length

if TYPE_CHECKING:  # pragma: no cover - used for type checking only
    from cvextractor.pipeline.context import ExtractionContext


class PersonalInfoExtractor(BaseExtractor):
    """Simple heuristics-driven extractor for personal information."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__("personal_info")
        self.config = config or load_section_config("personal_info")
        self.email_pattern = re.compile(
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
        )
        self.phone_patterns = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in [
                r"\+?\d[\d\s\.\-]{7,}\d",
                r"\b0[1-9](?:[\s\.\-]?\d{2}){4}\b",
            ]
        ]
        self.linkedin_pattern = re.compile(
            r"linkedin\.com/in/[a-zA-Z0-9\-_/]+", re.IGNORECASE
        )
        self.website_pattern = re.compile(
            r"https?://(?:www\.)?[a-zA-Z0-9\-\._]+\.[a-zA-Z]{2,}(?:/[^\s]*)?",
            re.IGNORECASE,
        )
        self.summary_keywords = {
            keyword.lower() for keyword in self.config.get("summary_keywords", [])
        }
        self.name_exclusion_keywords = {
            keyword.lower()
            for keyword in self.config.get("name_exclusion_keywords", [])
        }
        self.website_exclusions = set(self.config.get("website_exclusions", []))
        self.max_name_scan_lines = int(self.config.get("max_name_scan_lines", 5))

    def collect_raw(self, context: "ExtractionContext") -> Dict[str, Any]:
        text = "\n".join(context.lines)
        return {"text": text, "lines": list(context.lines)}

    def normalize(
        self, raw: Dict[str, Any], context: "ExtractionContext"
    ) -> Dict[str, Any]:
        text: str = raw.get("text", "")
        lines: List[str] = raw.get("lines", [])

        extracted: Dict[str, Optional[str]] = {
            "email": self._extract_first(self.email_pattern.findall(text)),
            "phone": self._extract_first(self._find_first_phone(text)),
            "linkedin_url": self._format_linkedin(
                self._extract_first(self.linkedin_pattern.findall(text))
            ),
            "website": self._extract_website(text),
            "full_name": self._extract_full_name(lines),
            "location": self._extract_location(text, lines),
            "summary": self._extract_summary(lines),
        }

        return extracted

    def post_process(
        self, data: Dict[str, Optional[str]], context: ExtractionContext
    ) -> Dict[str, Optional[str]]:
        return {key: (value if value else None) for key, value in data.items()}

    def _extract_first(self, values: Iterable[str]) -> Optional[str]:
        for value in values:
            if value:
                cleaned = value.strip()
                if cleaned:
                    return cleaned
        return None

    def _find_first_phone(self, text: str) -> Iterable[str]:
        for pattern in self.phone_patterns:
            match = pattern.findall(text)
            if match:
                return match
        return []

    def _format_linkedin(self, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        value = value.strip()
        if not value:
            return None
        if not value.lower().startswith("http"):
            return f"https://{value}"
        return value

    def _extract_website(self, text: str) -> Optional[str]:
        matches = self.website_pattern.findall(text)
        for match in matches:
            if all(exclusion not in match for exclusion in self.website_exclusions):
                return match.strip()
        return None

    def _extract_full_name(self, lines: List[str]) -> Optional[str]:
        scan_limit = min(self.max_name_scan_lines, len(lines))
        for line in (line.strip() for line in lines[:scan_limit]):
            if not line:
                continue
            lower = line.lower()
            if any(keyword in lower for keyword in self.name_exclusion_keywords):
                continue
            tokens = [token for token in line.replace("·", " ").split() if token]
            if 2 <= len(tokens) <= 4 and all(token[0].isalpha() for token in tokens):
                return " ".join(tokens)
        return None

    def _extract_location(self, text: str, lines: List[str]) -> Optional[str]:
        line_patterns = [
            re.compile(r"\b\d{5}\b"),
            re.compile(r"\b[A-Z][A-Za-zéèêàùïüç'\-]+\s+\d{4,5}\b"),
        ]
        for line in lines:
            cleaned = line.strip()
            if not cleaned:
                continue
            for pattern in line_patterns:
                if pattern.search(cleaned):
                    return cleaned

        location_patterns = [
            re.compile(r"\b\d{5}\s+[A-Z][\wéèêàùïüç'\- ]+\b", re.IGNORECASE),
            re.compile(r"\b[A-Z][\wéèêàùïüç'\- ]+\s+\d{5}\b", re.IGNORECASE),
            re.compile(
                r"\d+\s+(?:rue|avenue|boulevard|place)\s+[^\n,]+", re.IGNORECASE
            ),
        ]
        for pattern in location_patterns:
            match = pattern.search(text)
            if match:
                return match.group(0).replace("\n", " ").strip()
        return None

    def _extract_summary(self, lines: List[str]) -> Optional[str]:
        normalized_lines = [line.strip() for line in lines]
        for index, line in enumerate(normalized_lines):
            if not line:
                continue
            lower = line.lower()
            if any(keyword in lower for keyword in self.summary_keywords):
                snippet = normalized_lines[index + 1 : index + 4]
                snippet = [part for part in snippet if part]
                if has_min_length(snippet):
                    return " ".join(snippet)
        return None
