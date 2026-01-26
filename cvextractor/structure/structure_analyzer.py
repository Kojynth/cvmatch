"""
Section Structure Analyzer
==========================

Deterministic, auditable analysis of CV layout structure with:
- Contact block quarantine
- Education fragment consolidation
- Header guard enforcement
- Multi-column and RTL/CJK support
"""

import re
import math
from typing import List, Dict, Any, Tuple, Optional, Set
from dataclasses import dataclass
from collections import defaultdict
import logging

from ..core.types import CVSection, BoundingBox
from ..utils.log_safety import mask_all, create_safe_logger_wrapper
from ..metrics.instrumentation import get_metrics_collector


@dataclass
class StructureFlags:
    """Structure metadata for sections."""

    is_sidebar: bool = False
    is_timeline: bool = False
    column_id: int = 0
    reading_order: str = "ltr"  # ltr, rtl, ttb
    section_kind_guess: str = "unknown"
    guard_mask_ranges: List[Tuple[int, int]] = None
    is_quarantined: bool = False  # For contact blocks
    merge_candidate: bool = False  # For education fragments

    def __post_init__(self):
        if self.guard_mask_ranges is None:
            self.guard_mask_ranges = []


class SectionStructureAnalyzer:
    """Deterministic structure analysis for CV sections."""

    def __init__(
        self,
        max_cross_column_distance: int = 120,
        guard_max_lines: int = 6,
        edu_merge_max_gap: int = 3,
        edu_header_min_sim: float = 0.72,
        contact_density_threshold: float = 0.6,
        debug_mode: bool = False,
    ):
        self.max_cross_column_distance = max_cross_column_distance
        self.guard_max_lines = guard_max_lines
        self.edu_merge_max_gap = edu_merge_max_gap
        self.edu_header_min_sim = edu_header_min_sim
        self.contact_density_threshold = contact_density_threshold
        self.debug_mode = debug_mode

        # Create safe logger
        base_logger = logging.getLogger(__name__)
        self.logger = create_safe_logger_wrapper(base_logger)

        # Contact detection patterns
        self.contact_patterns = [
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",  # Email
            r"(?:\+33|0)[1-9](?:[.-]?\d{2}){4}",  # French phone
            r"(?:\+1-?)?(?:\(\d{3}\)|\d{3})[.-]?\d{3}[.-]?\d{4}",  # US phone
            r"https?://(?:[-\w.])+",  # URLs
            r"\b\d{1,5}\s+[A-Za-z\s]+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Rue)\b",  # Address
        ]

        # Education section headers (multilingual)
        self.education_headers = {
            "fr": [
                "formation",
                "éducation",
                "études",
                "parcours",
                "diplômes",
                "scolarité",
            ],
            "en": ["education", "academic", "studies", "qualifications", "degrees"],
            "es": ["educación", "formación", "estudios", "académico"],
            "de": ["bildung", "ausbildung", "studium", "qualifikationen"],
            "ar": ["تعليم", "تكوين", "دراسات"],  # RTL support
            "he": ["השכלה", "חינוך", "לימודים"],  # RTL support
            "zh": ["学历", "教育", "学习"],  # CJK support
            "ja": ["学歴", "教育", "学習"],  # CJK support
        }

    def analyze_structure(
        self, sections: List[CVSection], doc_id: str = "unknown"
    ) -> List[CVSection]:
        """
        Main entry point for structure analysis.

        Args:
            sections: Raw sections from segmentation
            doc_id: Document identifier for metrics

        Returns:
            Refined sections with structure flags
        """
        metrics = get_metrics_collector(doc_id)

        self.logger.info(
            f"STRUCTURE_ANALYSIS: starting | sections_count={len(sections)}"
        )

        # Step 1: Detect layout and assign column IDs
        sections_with_layout = self._detect_layout_structure(sections)

        # Step 2: Identify and quarantine contact blocks
        sections_with_quarantine = self._quarantine_contact_blocks(sections_with_layout)

        # Step 3: Consolidate education fragments
        sections_with_education = self._consolidate_education_fragments(
            sections_with_quarantine
        )

        # Step 4: Apply header guards with limits
        sections_with_guards = self._apply_header_guards(sections_with_education)

        # Step 5: Final validation and cleanup
        final_sections = self._validate_and_cleanup(sections_with_guards)

        # Log final metrics
        quarantined_count = sum(
            1
            for s in final_sections
            if getattr(s, "structure_flags", None) and s.structure_flags.is_quarantined
        )
        merged_count = len(sections) - len(final_sections)

        metrics.log_boundary_analysis(
            before_count=self._count_overlaps(sections),
            after_count=self._count_overlaps(final_sections),
        )

        self.logger.info(
            f"STRUCTURE_ANALYSIS: complete | "
            f"original={len(sections)} final={len(final_sections)} "
            f"quarantined={quarantined_count} merged={merged_count}"
        )

        return final_sections

    def _detect_layout_structure(self, sections: List[CVSection]) -> List[CVSection]:
        """Detect single/multi-column layout and reading order."""
        if not sections:
            return sections

        # Analyze bounding boxes to detect columns
        bboxes = []
        for section in sections:
            if hasattr(section, "bbox") and section.bbox:
                bboxes.append(
                    (
                        section.bbox.x,
                        section.bbox.y,
                        section.bbox.width,
                        section.bbox.height,
                    )
                )

        if not bboxes:
            # No spatial info, assume single column LTR
            for section in sections:
                section.structure_flags = StructureFlags(
                    column_id=0, reading_order="ltr", section_kind_guess="text_block"
                )
            return sections

        # Detect columns by x-coordinate clustering
        x_positions = [bbox[0] for bbox in bboxes]
        columns = self._detect_columns(x_positions)

        # Detect reading order (RTL/CJK heuristics)
        reading_order = self._detect_reading_order(sections)

        # Assign structure flags
        for i, section in enumerate(sections):
            if i < len(bboxes):
                x_pos = bboxes[i][0]
                column_id = self._assign_column(x_pos, columns)

                # Detect timeline/sidebar patterns
                is_timeline = self._is_timeline_section(section)
                is_sidebar = self._is_sidebar_section(section, bboxes[i], columns)

                section.structure_flags = StructureFlags(
                    is_sidebar=is_sidebar,
                    is_timeline=is_timeline,
                    column_id=column_id,
                    reading_order=reading_order,
                    section_kind_guess=self._guess_section_kind(section),
                )
            else:
                section.structure_flags = StructureFlags()

        self.logger.debug(
            f"LAYOUT_DETECTION: columns={len(columns)} reading_order={reading_order}"
        )
        return sections

    def _detect_columns(self, x_positions: List[float]) -> List[Tuple[float, float]]:
        """Detect column boundaries from x-positions."""
        if not x_positions:
            return [(0, 1000)]  # Default single column

        # Sort and find gaps larger than max_cross_column_distance
        sorted_x = sorted(set(x_positions))

        columns = []
        current_start = sorted_x[0]

        for i in range(1, len(sorted_x)):
            gap = sorted_x[i] - sorted_x[i - 1]
            if gap > self.max_cross_column_distance:
                # End current column, start new one
                columns.append((current_start, sorted_x[i - 1]))
                current_start = sorted_x[i]

        # Add final column
        columns.append((current_start, sorted_x[-1]))

        return columns if len(columns) > 1 else [(min(sorted_x), max(sorted_x))]

    def _detect_reading_order(self, sections: List[CVSection]) -> str:
        """Detect reading order from text content."""
        # Sample text from sections to detect language/script
        text_sample = ""
        for section in sections[:5]:  # Sample first few sections
            if hasattr(section, "text") and section.text:
                text_sample += section.text[:200] + " "

        # RTL script detection
        rtl_chars = re.findall(
            r"[\u0590-\u05FF\u0600-\u06FF\u0750-\u077F]", text_sample
        )
        if len(rtl_chars) > len(text_sample) * 0.1:  # 10% RTL threshold
            return "rtl"

        # CJK script detection
        cjk_chars = re.findall(
            r"[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]", text_sample
        )
        if len(cjk_chars) > len(text_sample) * 0.1:
            return "ttb"  # Top-to-bottom for CJK

        return "ltr"  # Default left-to-right

    def _quarantine_contact_blocks(self, sections: List[CVSection]) -> List[CVSection]:
        """Identify and quarantine contact/identity blocks."""
        contact_patterns_compiled = [
            re.compile(pattern, re.IGNORECASE) for pattern in self.contact_patterns
        ]

        for section in sections:
            if not hasattr(section, "text") or not section.text:
                continue

            # Calculate contact information density
            contact_matches = 0
            total_lines = max(1, len(section.text.split("\n")))

            for pattern in contact_patterns_compiled:
                matches = pattern.findall(section.text)
                contact_matches += len(matches)

            contact_density = contact_matches / total_lines

            # Quarantine if contact density exceeds threshold
            if contact_density >= self.contact_density_threshold:
                if not hasattr(section, "structure_flags"):
                    section.structure_flags = StructureFlags()
                section.structure_flags.is_quarantined = True
                section.structure_flags.section_kind_guess = "contact_block"

                self.logger.info(
                    f"CONTACT_QUARANTINE: section quarantined | "
                    f"density={contact_density:.3f} matches={contact_matches}"
                )

        return sections

    def _consolidate_education_fragments(
        self, sections: List[CVSection]
    ) -> List[CVSection]:
        """Merge adjacent education fragments split by formatting."""
        # Identify education sections
        education_indices = []
        for i, section in enumerate(sections):
            if self._is_education_section(section):
                education_indices.append(i)

        if len(education_indices) < 2:
            return sections  # Nothing to merge

        # Group adjacent education sections
        merge_groups = []
        current_group = [education_indices[0]]

        for i in range(1, len(education_indices)):
            curr_idx = education_indices[i]
            prev_idx = education_indices[i - 1]

            # Check if adjacent and within merge gap
            if (
                curr_idx - prev_idx <= self.edu_merge_max_gap + 1
                and self._should_merge_education_sections(
                    sections[prev_idx], sections[curr_idx]
                )
            ):
                current_group.append(curr_idx)
            else:
                if len(current_group) > 1:
                    merge_groups.append(current_group)
                current_group = [curr_idx]

        # Add final group if it has multiple sections
        if len(current_group) > 1:
            merge_groups.append(current_group)

        # Perform merges (in reverse order to maintain indices)
        for group in reversed(merge_groups):
            sections = self._merge_education_group(sections, group)

        return sections

    def _is_education_section(self, section: CVSection) -> bool:
        """Check if section is education-related."""
        if not hasattr(section, "text") or not section.text:
            return False

        text_lower = section.text.lower()

        # Check against education headers in all languages
        for lang_headers in self.education_headers.values():
            for header in lang_headers:
                if header in text_lower:
                    return True

        return False

    def _should_merge_education_sections(
        self, section1: CVSection, section2: CVSection
    ) -> bool:
        """Determine if two education sections should be merged."""
        if not (hasattr(section1, "text") and hasattr(section2, "text")):
            return False

        # Calculate header similarity
        header1 = self._extract_header(section1.text)
        header2 = self._extract_header(section2.text)

        similarity = self._calculate_header_similarity(header1, header2)

        return similarity >= self.edu_header_min_sim

    def _extract_header(self, text: str) -> str:
        """Extract likely header from section text."""
        lines = text.strip().split("\n")
        if lines:
            # Take first non-empty line as header
            for line in lines:
                if line.strip():
                    return line.strip().lower()
        return ""

    def _calculate_header_similarity(self, header1: str, header2: str) -> float:
        """Calculate similarity between two headers using Levenshtein-like metric."""
        if not header1 or not header2:
            return 0.0

        # Simple word overlap similarity
        words1 = set(header1.split())
        words2 = set(header2.split())

        if not words1 or not words2:
            return 0.0

        intersection = words1.intersection(words2)
        union = words1.union(words2)

        return len(intersection) / len(union) if union else 0.0

    def _merge_education_group(
        self, sections: List[CVSection], group_indices: List[int]
    ) -> List[CVSection]:
        """Merge a group of education sections."""
        if len(group_indices) < 2:
            return sections

        # Combine sections
        merged_section = sections[group_indices[0]]
        merged_texts = [
            sections[i].text for i in group_indices if hasattr(sections[i], "text")
        ]

        # Create merged content
        merged_section.text = "\n".join(merged_texts)

        # Update structure flags
        if not hasattr(merged_section, "structure_flags"):
            merged_section.structure_flags = StructureFlags()
        merged_section.structure_flags.section_kind_guess = "education_merged"

        # Remove merged sections (in reverse order)
        for idx in reversed(group_indices[1:]):
            sections.pop(idx)

        self.logger.info(f"EDU_MERGE: merged {len(group_indices)} sections into 1")
        return sections

    def _apply_header_guards(self, sections: List[CVSection]) -> List[CVSection]:
        """Apply header guard limits to prevent spillover."""
        for section in sections:
            if not hasattr(section, "structure_flags"):
                section.structure_flags = StructureFlags()

            # Apply guards based on section type
            if (
                hasattr(section, "text")
                and section.text
                and self._is_education_section(section)
            ):

                # Education sections get limited guards
                guard_ranges = self._calculate_guard_ranges(section)
                section.structure_flags.guard_mask_ranges = guard_ranges

        return sections

    def _calculate_guard_ranges(self, section: CVSection) -> List[Tuple[int, int]]:
        """Calculate guard mask ranges for a section."""
        if not hasattr(section, "text") or not section.text:
            return []

        lines = section.text.split("\n")
        guards = []

        # Find header lines and apply limited guards
        for i, line in enumerate(lines):
            if self._is_header_line(line):
                # Guard this line plus max_lines following
                guard_end = min(i + self.guard_max_lines, len(lines))
                guards.append((i, guard_end))

        return guards

    def _is_header_line(self, line: str) -> bool:
        """Check if line looks like a section header."""
        line = line.strip()
        if not line:
            return False

        # Heuristics for header detection
        # - All caps
        # - Contains education keywords
        # - Short line
        # - Has special formatting markers

        if line.isupper() and len(line) < 50:
            return True

        line_lower = line.lower()
        for lang_headers in self.education_headers.values():
            for header in lang_headers:
                if header in line_lower and len(line) < 100:
                    return True

        return False

    def _validate_and_cleanup(self, sections: List[CVSection]) -> List[CVSection]:
        """Final validation and cleanup of sections."""
        # Remove sections that are too small or empty
        valid_sections = []

        for section in sections:
            if self._is_valid_section(section):
                valid_sections.append(section)
            else:
                self.logger.debug(f"CLEANUP: removed invalid section")

        # Ensure all sections have structure flags
        for section in valid_sections:
            if not hasattr(section, "structure_flags"):
                section.structure_flags = StructureFlags()

        return valid_sections

    def _is_valid_section(self, section: CVSection) -> bool:
        """Check if section is valid and should be kept."""
        if not hasattr(section, "text") or not section.text:
            return False

        # Minimum text length
        if len(section.text.strip()) < 10:
            return False

        # Don't remove quarantined sections (they're still valid, just quarantined)
        return True

    def _count_overlaps(self, sections: List[CVSection]) -> int:
        """Count boundary overlaps in sections."""
        # Simplified overlap detection
        overlaps = 0

        for i in range(len(sections) - 1):
            section1 = sections[i]
            section2 = sections[i + 1]

            if (
                hasattr(section1, "bbox")
                and hasattr(section2, "bbox")
                and section1.bbox
                and section2.bbox
            ):

                # Check for spatial overlap
                if self._bboxes_overlap(section1.bbox, section2.bbox):
                    overlaps += 1

        return overlaps

    def _bboxes_overlap(self, bbox1: BoundingBox, bbox2: BoundingBox) -> bool:
        """Check if two bounding boxes overlap."""
        return not (
            bbox1.x + bbox1.width < bbox2.x
            or bbox2.x + bbox2.width < bbox1.x
            or bbox1.y + bbox1.height < bbox2.y
            or bbox2.y + bbox2.height < bbox1.y
        )

    def _assign_column(self, x_pos: float, columns: List[Tuple[float, float]]) -> int:
        """Assign column ID based on x position."""
        for i, (start, end) in enumerate(columns):
            if start <= x_pos <= end:
                return i
        return 0  # Default to first column

    def _is_timeline_section(self, section: CVSection) -> bool:
        """Detect timeline-style sections."""
        if not hasattr(section, "text") or not section.text:
            return False

        # Look for timeline indicators
        timeline_patterns = [
            r"\d{4}\s*[-–]\s*\d{4}",  # Year ranges
            r"\d{4}\s*[-–]\s*(?:present|current|now)",  # Ongoing dates
            r"●|•|\|",  # Timeline markers
        ]

        text = section.text
        for pattern in timeline_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True

        return False

    def _is_sidebar_section(
        self,
        section: CVSection,
        bbox: Tuple[float, float, float, float],
        columns: List[Tuple[float, float]],
    ) -> bool:
        """Detect sidebar sections based on position and size."""
        if len(columns) <= 1:
            return False

        x, y, width, height = bbox

        # Sidebar heuristics:
        # - Narrow width
        # - Positioned at edges
        # - Different column than main content

        avg_width = sum(end - start for start, end in columns) / len(columns)

        # Consider sidebar if significantly narrower than average
        if width < avg_width * 0.6:
            return True

        return False

    def _guess_section_kind(self, section: CVSection) -> str:
        """Guess section type from content."""
        if not hasattr(section, "text") or not section.text:
            return "unknown"

        text_lower = section.text.lower()

        # Education
        if self._is_education_section(section):
            return "education"

        # Experience keywords
        exp_keywords = [
            "experience",
            "work",
            "employment",
            "career",
            "job",
            "position",
            "expérience",
            "travail",
            "emploi",
            "poste",
            "fonction",
        ]
        if any(keyword in text_lower for keyword in exp_keywords):
            return "experience"

        # Skills
        skill_keywords = [
            "skills",
            "competences",
            "abilities",
            "technologies",
            "tools",
            "compétences",
            "capacités",
            "technologies",
            "outils",
        ]
        if any(keyword in text_lower for keyword in skill_keywords):
            return "skills"

        # Contact
        if any(
            re.search(pattern, section.text, re.IGNORECASE)
            for pattern in self.contact_patterns
        ):
            return "contact"

        return "text_block"


# Export main class
__all__ = ["SectionStructureAnalyzer", "StructureFlags"]
