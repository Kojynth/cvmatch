"""Extractor for structured contact information."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional, Tuple

from cvextractor.modules.base_extractor import BaseExtractor
from cvextractor.shared.config import load_section_config
from cvextractor.shared.heuristics import ensure_tuple

if TYPE_CHECKING:  # pragma: no cover - typing only
    from cvextractor.pipeline.context import ExtractionContext


class ContactInfoExtractor(BaseExtractor):
    """Capture contact signals from the header section of the CV."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__("contact")
        self.config = config or load_section_config("contact")
        self.scan_limit = int(self.config.get("scan_header_lines", 8))
        self.separator_tokens = ensure_tuple(
            self.config.get("separator_tokens", ("|", "•", "·", "/", ";"))
        )
        self.label_keywords = {
            token.lower() for token in self.config.get("label_keywords", [])
        }
        self.email_pattern = re.compile(
            r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
        )
        self.phone_pattern = re.compile(r"\+?\d[\d\s\.\-]{7,}\d")
        self.url_pattern = re.compile(r"https?://[^\s]+", re.IGNORECASE)

    def collect_raw(self, context: "ExtractionContext") -> Dict[str, Any]:
        scanned = [line.strip() for line in context.lines[: self.scan_limit]]
        return {"header_lines": [line for line in scanned if line]}

    def normalize(
        self, raw: Dict[str, Any], context: "ExtractionContext"
    ) -> List[Dict[str, str]]:
        header_lines: List[str] = raw.get("header_lines", [])
        entries: List[Dict[str, str]] = []

        for line in header_lines:
            entries.extend(self._extract_entries_from_line(line))

        # Deduplicate values by type
        seen: Dict[str, set] = {
            "email": set(),
            "phone": set(),
            "url": set(),
            "other": set(),
        }
        deduped: List[Dict[str, str]] = []

        for entry in entries:
            etype = entry.get("type", "other")
            value = entry.get("value")
            if not value:
                continue
            if value in seen.setdefault(etype, set()):
                continue
            seen[etype].add(value)
            deduped.append(entry)

        return deduped

    def post_process(
        self, data: List[Dict[str, str]], context: "ExtractionContext"
    ) -> List[Dict[str, str]]:
        return data

    def _extract_entries_from_line(self, line: str) -> Iterable[Dict[str, str]]:
        # First look for explicit structured tokens (email, phone, url)
        entries: List[Dict[str, str]] = []

        for email in self.email_pattern.findall(line):
            entries.append({"type": "email", "value": email})

        for phone in self.phone_pattern.findall(line):
            cleaned = re.sub(r"\s+", " ", phone).strip()
            entries.append({"type": "phone", "value": cleaned})

        for url in self.url_pattern.findall(line):
            entries.append({"type": "url", "value": url.rstrip(".,;")})

        separators = "|".join(re.escape(token) for token in self.separator_tokens)
        segments = re.split(separators, line) if separators else [line]

        for segment in segments:
            cleaned = segment.strip(" •\t-")
            if not cleaned:
                continue
            lower = cleaned.lower()
            if any(keyword in lower for keyword in self.label_keywords):
                label, value = self._split_label_value(cleaned)
                if value:
                    entries.append({"type": label or "other", "value": value})
            elif cleaned and not any(cleaned == entry["value"] for entry in entries):
                entries.append({"type": "other", "value": cleaned})

        return entries

    def _split_label_value(self, text: str) -> Tuple[Optional[str], Optional[str]]:
        for separator in (":", "=", "-"):
            if separator in text:
                label, value = text.split(separator, 1)
                label = label.strip().lower()
                value = value.strip()
                if value:
                    return label, value
        return None, text.strip() if text.strip() else None
