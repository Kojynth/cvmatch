"""Shared helpers to start migrating experience and education extraction logic."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from app.utils.boundary_guards import tri_signal_validator
from app.utils.education_extractor_enhanced import levenshtein_distance
from app.utils.experience_extractor_enhanced import (
    EnhancedExperienceExtractor as LegacyExperienceExtractor,
)
from app.utils.experience_filters import (
    calculate_pattern_diversity,
    normalize_text_for_matching,
)

from cvextractor.shared.heuristics import DateSpan


@dataclass(frozen=True)
class ExperienceCandidate:
    """Lightweight representation of an extracted experience item."""

    title: str
    company: str
    dates_text: Optional[str]
    line_index: int
    confidence: float
    tri_signal: Optional[Dict[str, object]] = None
    description: Optional[str] = None

    def to_payload(self) -> Dict[str, object]:
        """Return a dict compatible with the legacy extractor payload."""
        return {
            "title": self.title,
            "company": self.company,
            "dates": self.dates_text,
            "line_idx": self.line_index,
            "confidence": self.confidence,
            "tri_signal_validation": self.tri_signal,
            "description": self.description,
        }

    def with_tri_signal(self, result: Dict[str, object]) -> "ExperienceCandidate":
        """Attach tri-signal diagnostics to the candidate."""
        if not result:
            return self
        bonus = 0.1 if result.get("passes") else 0.0
        return replace(
            self, tri_signal=result, confidence=min(1.0, self.confidence + bonus)
        )


@dataclass(frozen=True)
class EducationCandidate:
    """Lightweight representation of an extracted education item."""

    degree: str
    school: Optional[str]
    dates_text: Optional[str]
    line_index: int
    confidence: float
    source_text: Optional[str] = None

    def to_payload(self) -> Dict[str, object]:
        """Return a dict compatible with the legacy extractor payload."""
        return {
            "degree": self.degree,
            "school": self.school,
            "dates": self.dates_text,
            "line_idx": self.line_index,
            "confidence": self.confidence,
            "source_text": self.source_text,
        }


EXPERIENCE_PIPED_PATTERN = re.compile(
    r"""
    ^
    (?P<dates>(?:[^\|]{4,40}))            # dates or descriptor before first pipe
    \s*\|\s*
    (?P<company>[^|]{2,80})               # company name between pipes
    \s*\|\s*
    (?P<title>.+?)                        # title after second pipe
    $
    """,
    re.VERBOSE,
)

EXPERIENCE_DASH_PATTERN = re.compile(
    r"""
    ^
    (?P<company>[^-]{2,80}?)
    \s*[-–—]\s*
    (?P<title>[^-]{2,120}?)
    (?:\s*\((?P<dates>[^)]+)\))?
    $
    """,
    re.VERBOSE,
)

EDUCATION_PATTERN = re.compile(
    r"""
    ^
    (?P<degree>[^-]{3,120}?)
    \s*[-–—]\s*
    (?P<school>[^-]{2,120}?)
    (?:\s*\((?P<dates>[^)]+)\))?
    $
    """,
    re.VERBOSE,
)

_LEGACY_EXPERIENCE_GATES = LegacyExperienceExtractor()


def _find_dates_for_line(line_index: int, spans: Sequence[DateSpan]) -> Optional[str]:
    for span in spans:
        if span.line_index == line_index:
            return span.text or span.original_text
    return None


def extract_basic_experiences(
    lines: Sequence[str],
    *,
    line_offset: int = 0,
    date_spans: Sequence[DateSpan] | None = None,
) -> List[ExperienceCandidate]:
    """Best-effort extraction for experience items using simple heuristics."""
    date_spans = date_spans or ()
    candidates: List[ExperienceCandidate] = []

    for rel_index, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line:
            continue

        absolute_index = rel_index + line_offset
        dates_text = _find_dates_for_line(absolute_index, date_spans)
        description = _collect_description(lines, rel_index)

        match = EXPERIENCE_PIPED_PATTERN.match(line)
        if match:
            candidate = ExperienceCandidate(
                title=match.group("title").strip(),
                company=match.group("company").strip(),
                dates_text=dates_text or match.group("dates").strip(),
                line_index=absolute_index,
                confidence=0.6,
                description=description,
            )
            candidates.append(candidate)
            continue

        match = EXPERIENCE_DASH_PATTERN.match(line)
        if match:
            candidate = ExperienceCandidate(
                title=match.group("title").strip(),
                company=match.group("company").strip(),
                dates_text=dates_text or (match.group("dates") or "").strip() or None,
                line_index=absolute_index,
                confidence=0.4,
                description=description,
            )
            candidates.append(candidate)

    return [
        candidate for candidate in candidates if candidate.title and candidate.company
    ]


def extract_basic_education(
    lines: Sequence[str],
    *,
    line_offset: int = 0,
    date_spans: Sequence[DateSpan] | None = None,
) -> List[EducationCandidate]:
    """Best-effort extraction for education items using simple heuristics."""
    date_spans = date_spans or ()
    candidates: List[EducationCandidate] = []

    for rel_index, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line:
            continue

        absolute_index = rel_index + line_offset
        dates_text = _find_dates_for_line(absolute_index, date_spans)

        match = EDUCATION_PATTERN.match(line)
        if not match:
            continue

        candidate = EducationCandidate(
            degree=match.group("degree").strip(),
            school=(match.group("school") or "").strip() or None,
            dates_text=dates_text or (match.group("dates") or "").strip() or None,
            line_index=absolute_index,
            confidence=0.5,
            source_text=line,
        )
        candidates.append(candidate)

    return [candidate for candidate in candidates if candidate.degree]


def refine_experience_candidates(
    all_lines: Sequence[str],
    candidates: Sequence[ExperienceCandidate],
    *,
    require_tri_signal: bool = True,
    min_description_tokens: int = 0,
    max_items: Optional[int] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    """Run tri-signal validation, deduplication, and apply legacy quality gates."""
    seen: set[Tuple[str, str, str]] = set()
    refined_candidates: List[ExperienceCandidate] = []

    for candidate in candidates:
        tri_signal_result = tri_signal_validator.validate_tri_signal_linkage(
            list(all_lines), candidate.line_index, entities=None
        )
        candidate_with_tri = candidate.with_tri_signal(tri_signal_result)

        if require_tri_signal and not tri_signal_result.get("passes", False):
            continue

        if min_description_tokens > 0:
            token_count = len((candidate_with_tri.description or "").split())
            if token_count < min_description_tokens:
                continue

        key = (
            _normalized(candidate_with_tri.title),
            _normalized(candidate_with_tri.company),
            _normalized(candidate_with_tri.dates_text or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        refined_candidates.append(candidate_with_tri)

    refined_candidates.sort(key=lambda item: item.confidence, reverse=True)
    if max_items is not None and max_items > 0:
        refined_candidates = refined_candidates[:max_items]

    payloads: List[Dict[str, Any]] = []
    dropped_for_company: List[Dict[str, Any]] = []
    for candidate in refined_candidates:
        payload = candidate.to_payload()
        if not (payload.get("company") or "").strip():
            dropped_for_company.append(payload)
            continue
        payloads.append(payload)

    if not payloads:
        diagnostics = {
            "tri_signal_filtered": len(refined_candidates),
            "rebind_stats": {},
            "quality_issues": [],
            "demoted_to_education": 0,
            "pattern_diversity": 0.0,
        }
        return [], dropped_for_company, diagnostics

    try:
        rebind_result = _LEGACY_EXPERIENCE_GATES._apply_organization_rebinding(
            payloads, list(all_lines), entities=None
        )
        survivors = rebind_result["experiences"]
        survivor_ids = {id(item) for item in survivors}
        rebinding_demotions = [
            exp
            for exp in payloads
            if id(exp) not in survivor_ids and exp.get("target_section")
        ]
    except KeyError:
        survivors = payloads
        rebinding_demotions = []
        rebind_result = {
            "experiences": survivors,
            "stats": {"attempts": 0, "successes": 0, "school_demotions": 0},
        }

    quality_result = _LEGACY_EXPERIENCE_GATES._apply_quality_assessment(
        survivors, list(all_lines)
    )

    final_payloads = quality_result["final_experiences"]
    qa_demotions = [
        demotion["experience"]
        for demotion in quality_result["demotions"]
        if demotion.get("target_section") == "education"
    ]

    handoff_to_education = [
        exp for exp in rebinding_demotions if exp.get("target_section") == "education"
    ]
    handoff_to_education.extend(qa_demotions)
    handoff_to_education.extend(dropped_for_company)

    diagnostics = {
        "tri_signal_filtered": len(payloads),
        "rebind_stats": rebind_result["stats"],
        "quality_issues": quality_result["quality_issues"],
        "demoted_to_education": len(handoff_to_education),
        "pattern_diversity": calculate_pattern_diversity(
            {"experiences": final_payloads}
        ),
    }

    return final_payloads, handoff_to_education, diagnostics


def refine_education_candidates(
    candidates: Sequence[EducationCandidate],
    *,
    max_items: Optional[int] = None,
    similarity_threshold: int = 3,
) -> List[EducationCandidate]:
    """Deduplicate and cap education results based on textual similarity."""
    refined: List[EducationCandidate] = []

    for candidate in candidates:
        merged = False
        for index, existing in enumerate(refined):
            if _are_education_similar(existing, candidate, similarity_threshold):
                if candidate.confidence > existing.confidence:
                    refined[index] = candidate
                merged = True
                break
        if not merged:
            refined.append(candidate)

    refined.sort(key=lambda item: item.confidence, reverse=True)

    if max_items is not None and max_items > 0:
        refined = refined[:max_items]

    return refined


def as_payload(
    candidates: Sequence[ExperienceCandidate | EducationCandidate],
) -> List[Dict[str, object]]:
    """Convert any candidate list to payload dictionaries."""
    return [candidate.to_payload() for candidate in candidates]


def _normalized(value: str) -> str:
    if not value:
        return ""
    return normalize_text_for_matching(value)


def _collect_description(lines: Sequence[str], start_index: int) -> Optional[str]:
    """Collect a short description snippet following the experience anchor line."""
    for rel_offset in range(1, 3):
        idx = start_index + rel_offset
        if idx >= len(lines):
            break
        candidate_line = lines[idx].strip()
        if not candidate_line:
            continue
        return candidate_line
    return None


def _are_education_similar(
    left: EducationCandidate,
    right: EducationCandidate,
    threshold: int,
) -> bool:
    left_degree = _normalized(left.degree)
    right_degree = _normalized(right.degree)
    left_school = _normalized(left.school or "")
    right_school = _normalized(right.school or "")

    if left_school and right_school:
        school_distance = levenshtein_distance(left_school, right_school)
        if school_distance <= threshold:
            return True

    degree_distance = levenshtein_distance(left_degree, right_degree)
    if degree_distance <= threshold:
        return True

    return False
