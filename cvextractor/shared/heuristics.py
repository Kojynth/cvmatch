"""Shared heuristics helpers for the modular CV extraction pipeline."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import (
    Any,
    Dict,
    Iterable,
    Iterator,
    List,
    Optional,
    Sequence,
    Set,
    Tuple,
    TypeVar,
)

from app.utils.robust_date_parser import ParsedDate, RobustDateParser

T = TypeVar("T")

_ROBUST_DATE_PARSER: Optional[RobustDateParser] = None


def _get_date_parser() -> RobustDateParser:
    """Lazily instantiate the heavy date parser so tests remain fast."""
    global _ROBUST_DATE_PARSER
    if _ROBUST_DATE_PARSER is None:
        _ROBUST_DATE_PARSER = RobustDateParser()
    return _ROBUST_DATE_PARSER


@dataclass(frozen=True)
class DateSpan:
    """Normalized representation of a date mention anchored to a CV line."""

    line_index: int
    text: str
    original_text: str
    start_year: Optional[int]
    start_month: Optional[int]
    end_year: Optional[int]
    end_month: Optional[int]
    is_current: bool
    confidence: float

    @classmethod
    def from_parsed(cls, parsed: ParsedDate, *, line_index: int) -> "DateSpan":
        """Create a span from the legacy `ParsedDate` payload."""
        normalized_text = (parsed.normalized_text or parsed.original_text or "").strip()
        return cls(
            line_index=line_index,
            text=normalized_text,
            original_text=(parsed.original_text or "").strip(),
            start_year=parsed.start_year,
            start_month=parsed.start_month,
            end_year=parsed.end_year,
            end_month=parsed.end_month,
            is_current=parsed.is_current,
            confidence=parsed.confidence or 0.0,
        )

    def to_legacy_hit(self) -> Dict[str, Any]:
        """Return the structure expected by the legacy experience extractor."""
        return {
            "line_idx": self.line_index,
            "date_text": self.text or self.original_text,
            "start": {
                "year": self.start_year,
                "month": self.start_month,
            },
            "end": {
                "year": self.end_year,
                "month": self.end_month,
            },
            "is_current": self.is_current,
            "confidence": self.confidence,
            "source_text": self.original_text,
        }


@dataclass(frozen=True)
class SectionBounds:
    """Indices delimiting a detected section in the source lines."""

    start: int
    end: int

    @property
    def as_tuple(self) -> Tuple[int, int]:
        return (self.start, self.end)


DEFAULT_SECTION_TOKENS: Set[str] = {
    "experience",
    "experiences",
    "experience professionnelle",
    "work experience",
    "professional experience",
    "education",
    "formation",
    "formations",
    "etudes",
    "projects",
    "project",
    "realisations",
    "skills",
    "competences",
    "languages",
    "langues",
    "certifications",
    "interests",
    "interets",
    "volunteering",
    "benevolat",
    "awards",
    "distinctions",
    "publications",
}


def sliding_window(sequence: Sequence[T], radius: int) -> Iterator[Sequence[T]]:
    """Yield windows of ``radius`` elements around each item."""
    if radius < 1:
        yield sequence
        return

    length = len(sequence)
    for index in range(length):
        start = max(0, index - radius)
        end = min(length, index + radius + 1)
        yield sequence[start:end]


def ensure_tuple(value: Iterable[T] | T | None) -> tuple[T, ...]:
    """Normalize values to tuples so heuristics can work with predictable types."""
    if value is None:
        return ()
    if isinstance(value, tuple):
        return value
    if isinstance(value, (list, set, frozenset)):
        return tuple(value)
    return (value,)


def has_min_length(value: Sequence[T] | None, minimum: int = 1) -> bool:
    """Guard for quick sanity checks on heuristic inputs."""
    if value is None:
        return False
    return len(value) >= minimum


def extract_date_spans(
    lines: Sequence[str],
    *,
    start_offset: int = 0,
    window: int = 2,
    min_confidence: float = 0.35,
    global_lines: Optional[Sequence[str]] = None,
) -> List[DateSpan]:
    """Detect date spans within the provided lines using the robust parser."""
    if not lines:
        return []

    parser = _get_date_parser()
    context_lines = list(global_lines) if global_lines is not None else list(lines)
    spans: List[DateSpan] = []
    seen: Set[Tuple[int, str]] = set()

    for relative_idx, raw_line in enumerate(lines):
        if not raw_line or not raw_line.strip():
            continue
        if _looks_like_section_heading(raw_line):
            continue

        absolute_idx = relative_idx + start_offset
        target_idx = absolute_idx if global_lines is not None else relative_idx
        parsed_dates = parser.parse_dates_from_text(
            raw_line,
            line_context=context_lines,
            target_line_idx=target_idx,
        )

        for parsed in parsed_dates:
            if parsed.confidence is not None and parsed.confidence < min_confidence:
                continue
            span = DateSpan.from_parsed(parsed, line_index=absolute_idx)
            if not span.text:
                continue
            key = (span.line_index, span.text.lower())
            if key in seen:
                continue
            seen.add(key)
            spans.append(span)

    return spans


def build_legacy_date_hits(spans: Sequence[DateSpan]) -> List[Dict[str, Any]]:
    """Translate detected spans into the structure expected by legacy extractors."""
    return [span.to_legacy_hit() for span in spans]


def detect_section_bounds(
    lines: Sequence[str],
    keywords: Iterable[str],
    *,
    stop_keywords: Iterable[str] | None = None,
    min_body_lines: int = 2,
) -> Optional[SectionBounds]:
    """Identify the bounds of a section based on keywords and heading heuristics."""
    normalized_keywords = _normalize_tokens(keywords)
    if not normalized_keywords:
        return None

    normalized_stops = _normalize_tokens(stop_keywords) or DEFAULT_SECTION_TOKENS
    start_idx: Optional[int] = None

    for index, line in enumerate(lines):
        token = _normalize_header(line)
        if not token:
            continue

        if token in normalized_keywords or any(
            keyword in token for keyword in normalized_keywords
        ):
            start_idx = index
            break

    if start_idx is None:
        return None

    end_idx = len(lines)
    for index in range(start_idx + 1, len(lines)):
        candidate = _normalize_header(lines[index])
        if not candidate:
            continue
        if candidate in normalized_stops and index - start_idx >= min_body_lines:
            end_idx = index
            break
        if (
            _looks_like_section_heading(lines[index])
            and index - start_idx >= min_body_lines
        ):
            end_idx = index
            break

    return SectionBounds(start=start_idx, end=end_idx)


def _normalize_tokens(values: Iterable[str] | None) -> Set[str]:
    tokens: Set[str] = set()
    if not values:
        return tokens
    for value in values:
        if not value:
            continue
        tokens.add(_normalize_header(value))
    return {token for token in tokens if token}


def _normalize_header(value: str) -> str:
    if not value:
        return ""
    cleaned = re.sub(r"[\W_]+", " ", value).strip()
    return cleaned.lower()


def _looks_like_section_heading(line: str) -> bool:
    if not line:
        return False

    stripped = line.strip()
    if not stripped:
        return False

    if stripped.endswith(":"):
        return True

    alpha_tokens = [token for token in re.split(r"\s+", stripped) if token]
    if not alpha_tokens:
        return False

    uppercase_tokens = sum(1 for token in alpha_tokens if token.isupper())
    if uppercase_tokens and uppercase_tokens / len(alpha_tokens) >= 0.6:
        return True

    return False
