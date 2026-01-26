"""HTML parser that uses external selector configuration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import json
from bs4 import BeautifulSoup, Tag


@dataclass(slots=True)
class SelectorConfig:
    selectors: Dict[str, Any]
    mappings: Dict[str, Any]

    @classmethod
    def from_files(cls, selectors_path: Path, mappings_path: Path) -> "SelectorConfig":
        return cls(
            selectors=json.loads(selectors_path.read_text(encoding="utf-8")),
            mappings=json.loads(mappings_path.read_text(encoding="utf-8")),
        )

    def section(self, name: str) -> Dict[str, Any]:
        return self.selectors.get(name, {})


class LinkedInParser:
    """Parses LinkedIn profile HTML using declarative selectors."""

    def __init__(self, selectors: SelectorConfig) -> None:
        self.config = selectors

    def parse(self, html: str) -> Dict[str, Any]:
        soup = BeautifulSoup(html, "html.parser")
        payload: Dict[str, Any] = {
            "profile": self._extract_profile(soup),
            "experience": self._extract_collection(soup, "experience"),
            "education": self._extract_collection(soup, "education"),
            "skills": self._extract_collection(soup, "skills"),
            "languages": self._extract_collection(soup, "languages"),
            "recommendations": self._extract_collection(soup, "recommendations"),
        }
        payload["about"] = self._first_text(soup, self.config.section("about").get("text"))
        return payload

    def _extract_profile(self, soup: BeautifulSoup) -> Dict[str, Optional[str]]:
        section = self.config.section("profile")
        return {
            "name": self._first_text(soup, section.get("name")),
            "headline": self._first_text(soup, section.get("headline")),
            "location": self._first_text(soup, section.get("location")),
        }

    def _extract_collection(self, soup: BeautifulSoup, section_name: str) -> List[Dict[str, Any]]:
        section = self.config.section(section_name)
        container = self._first_element(soup, section.get("container"))
        if container is None:
            return []
        items_selector = section.get("item")
        if not items_selector:
            return []
        records: List[Dict[str, Any]] = []
        for element in container.select(items_selector):
            record: Dict[str, Any] = {}
            for field, selector in section.items():
                if field in {"container", "item"}:
                    continue
                record[field] = self._first_text(element, selector)
            if any(value for value in record.values()):
                records.append(record)
        return records

    @staticmethod
    def _first_text(root: BeautifulSoup | Tag, selector: Optional[str]) -> Optional[str]:
        element = LinkedInParser._first_element(root, selector)
        if element is None:
            return None
        text = element.get_text(" ", strip=True)
        return text or None

    @staticmethod
    def _first_element(root: BeautifulSoup | Tag, selector: Optional[str]) -> Optional[Tag]:
        if not selector:
            return None
        matches: Iterable[Tag] = root.select(selector)
        return next(iter(matches), None)


__all__ = ["LinkedInParser", "SelectorConfig"]
