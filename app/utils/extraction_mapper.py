"""
Compatibility wrapper exposing the modular extraction mapping pipeline and
legacy helpers kept for historical tests.
"""

from __future__ import annotations

import re
from typing import Iterable, List, Optional

from ..config import DEFAULT_PII_CONFIG
from ..logging.safe_logger import get_safe_logger
from .interest_deduplicator import get_interest_deduplicator
from .title_cleaner import TitleCleaner
from .mapping import (
    ExperienceEducationMapper,
    MappingOrchestrator,
    QAEngine,
    SkillsMapper,
)

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)

# ---------------------------------------------------------------------------
# Legacy compatibility helpers (interests)
# ---------------------------------------------------------------------------

_CATEGORY_LABELS = {
    "sports": "Sports",
    "arts": "Arts",
    "technologie": "Tech",
    "social": "Community",
    "voyage": "Culture",
    "cuisine": "Culture",
}

_CURRENT_END_TOKENS = {
    "present",
    "présent",
    "en cours",
    "current",
    "aujourd'hui",
    "a ce jour",
    "ce jour",
}


def _iter_clean_interests(interests: Iterable[str]) -> List[str]:
    """Return a cleaned list of textual interests (legacy helper)."""
    cleaned: List[str] = []
    for value in interests or []:
        if isinstance(value, str):
            candidate = value.strip()
            if candidate:
                cleaned.append(candidate)
    return cleaned


def deduplicate_interests(interests: Iterable[str]) -> List[str]:
    """Legacy API: return canonical interests without duplicates."""
    deduplicator = get_interest_deduplicator()
    deduped = deduplicator.deduplicate_interests(_iter_clean_interests(interests))
    return [item.canonical.title() for item in deduped]


def normalize_and_cap_interests(interests: Iterable[str], max_categories: int = 5) -> List[str]:
    """Legacy API: normalize interests and cap them by thematic buckets."""
    deduplicator = get_interest_deduplicator()
    cleaned = _iter_clean_interests(interests)
    if not cleaned:
        return []

    deduped = deduplicator.deduplicate_interests(cleaned)
    if not deduped:
        return []

    limited = deduplicator.limit_interests_count(deduped, max_count=max_categories)

    buckets: List[str] = []
    seen_labels = set()

    for interest in limited:
        category = interest.category or ""
        label = _CATEGORY_LABELS.get(category, interest.canonical.title())
        key = label.lower()
        if key not in seen_labels:
            buckets.append(label)
            seen_labels.add(key)
        if len(buckets) >= max_categories:
            break

    for interest in limited:
        if len(buckets) >= max_categories:
            break
        label = interest.canonical.title()
        key = label.lower()
        if key not in seen_labels:
            buckets.append(label)
            seen_labels.add(key)

    return buckets[:max_categories]


# ---------------------------------------------------------------------------
# Legacy compatibility helpers (experiences)
# ---------------------------------------------------------------------------

class ExperienceNormalizer:
    """Simplified legacy experience normalizer with date/company extraction."""

    DATE_PATTERN = re.compile(
        r"(?P<start>\d{1,2}/\d{4})\s*[-\u2013]\s*(?P<end>[\w/.']+)",
        re.IGNORECASE,
    )
    COMPANY_PATTERN = re.compile(r"\b(?:chez|at)\s+(?P<company>[\w&.'\- ]+)", re.IGNORECASE)

    def normalize_experience(self, experience: Optional[dict]) -> dict:
        data = dict(experience or {})
        title = str(data.get("title", "") or "").strip()
        description = str(data.get("description", "") or "").strip()
        company = str(data.get("company", "") or "").strip()

        overflow: List[str] = []
        start_date: Optional[str] = None
        end_date: Optional[str] = data.get("end_date")

        if title:
            match = self.DATE_PATTERN.search(title)
            if match:
                start_date = match.group("start").strip()
                raw_end = match.group("end").strip()
                lowered_end = raw_end.lower()
                if lowered_end in _CURRENT_END_TOKENS:
                    end_date = None
                else:
                    end_date = raw_end
                before = title[: match.start()].rstrip(" -\u2013")
                after = title[match.end():].lstrip(" -\u2013")
                if after:
                    overflow.append(after)
                title = before

        if not company and title:
            match = self.COMPANY_PATTERN.search(title)
            if match:
                company = match.group("company").strip(" -\u2013,")
                before = title[: match.start()].rstrip(" -\u2013,")
                after = title[match.end():].lstrip(" -\u2013,")
                if after:
                    overflow.append(after)
                title = before

        clean_title = " ".join(title.split())

        if overflow:
            overflow_text = " ".join(segment.strip() for segment in overflow if segment.strip())
            if overflow_text:
                description = f"{description}\n{overflow_text}".strip()

        normalized = dict(data)
        if clean_title:
            normalized["title"] = clean_title
        if company:
            normalized["company"] = company
        if start_date:
            normalized["start_date"] = start_date
        if "end_date" not in normalized or normalized["end_date"] is None:
            normalized["end_date"] = end_date
        if description:
            normalized["description"] = description

        return normalized


# ---------------------------------------------------------------------------
# Orchestrator wiring
# ---------------------------------------------------------------------------

class ExtractionMapper:
    """Thin facade kept for backward compatibility."""

    def __init__(self) -> None:
        self.skills_mapper = SkillsMapper()
        self.experience_mapper = ExperienceEducationMapper()
        self.qa_engine = QAEngine()
        logger.info("ExtractionMapper compatibility wrapper initialised")


extraction_mapper = ExtractionMapper()
mapping_orchestrator = MappingOrchestrator(extraction_mapper, logger)


def apply_smart_mapping(data: dict) -> dict:
    """Delegate smart mapping to the modular orchestrator."""
    return mapping_orchestrator.apply(data)


__all__ = [
    "ExperienceNormalizer",
    "TitleCleaner",
    "deduplicate_interests",
    "normalize_and_cap_interests",
    "extraction_mapper",
    "mapping_orchestrator",
    "apply_smart_mapping",
]
