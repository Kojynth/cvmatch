"""
Boundary guards and header conflict detection for CV extraction.
Implements the header-conflict kill radius and cross-column distance checks.
Includes boundary normalization for handling composite tuples safely.

ENHANCED: Content validation, contact detection, and PII-safe instrumentation.
"""

import re
import hashlib
from enum import Enum, auto
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple, Set, Union, Iterable
from ..config import EXPERIENCE_CONF
from ..logging.safe_logger import get_safe_logger, DEFAULT_PII_CONFIG

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)

class ContaminationType(Enum):
    HEADER_POLLUTION = auto()
    BULLET_CONTAMINATION = auto()
    FORMATTING_ARTIFACTS = auto()
    CROSS_SECTION_LEAK = auto()
    OTHER = auto()

@dataclass
class BoundaryViolation:
    violation_type: ContaminationType
    field_name: str
    details: str = ""
    confidence: float = 1.0

@dataclass
class AnalyzedBlock:
    text: str
    block_type: str
    proximity_score: float = 1.0

class ResidualLedger:
    """Track line ownership between multiple consumers (legacy helper)."""

    def __init__(self) -> None:
        self._ownership: Dict[int, str] = {}

    def consume_lines(self, consumer_id: str, lines: Iterable[int]) -> None:
        for line in lines or []:
            if line in self._ownership and self._ownership[line] != consumer_id:
                raise ValueError("Line ownership overlap detected")
            self._ownership[line] = consumer_id

    def get_line_owner(self, line: int) -> Optional[str]:
        return self._ownership.get(line)

    def get_consumed_lines(self, consumer_id: str) -> List[int]:
        return [line for line, owner in sorted(self._ownership.items()) if owner == consumer_id]

    def release_lines(self, consumer_id: str, lines: Optional[Iterable[int]] = None) -> None:
        if lines is None:
            lines = [line for line, owner in self._ownership.items() if owner == consumer_id]
        for line in list(lines):
            if self._ownership.get(line) == consumer_id:
                self._ownership.pop(line, None)

    def get_residual_lines(self, total_line_count: int) -> List[int]:
        return [idx for idx in range(total_line_count) if idx not in self._ownership]

def assert_no_overlap(boundaries: Iterable[Dict[str, int]]) -> None:
    """Raise if boundaries overlap (legacy helper for tests)."""
    sorted_bounds = sorted(
        [b for b in boundaries or [] if isinstance(b, dict)],
        key=lambda item: (item.get('start', 0), item.get('end', 0)),
    )
    for prev, current in zip(sorted_bounds, sorted_bounds[1:]):
        if current.get('start', 0) < prev.get('end', 0):
            raise AssertionError("Boundary overlap detected")

def merge_overlapping_boundaries(boundaries: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge overlapping boundaries while preserving original metadata."""
    sorted_bounds = sorted(
        [b for b in boundaries or [] if isinstance(b, dict)],
        key=lambda item: item.get('start', 0),
    )
    if not sorted_bounds:
        return []

    merged: List[Dict[str, Any]] = []
    current = dict(sorted_bounds[0])

    for boundary in sorted_bounds[1:]:
        if boundary.get('start', 0) <= current.get('end', 0):
            current['end'] = max(current.get('end', 0), boundary.get('end', 0))
        else:
            merged.append(current)
            current = dict(boundary)

    merged.append(current)
    return merged

# Global section ID counter for monotonic section tracking
_section_id_counter = 0

def generate_section_id(section_type: str, start_idx: int, end_idx: int) -> str:
    """Generate a monotonic section ID for tracking."""
    global _section_id_counter
    _section_id_counter += 1
    return f"{section_type}_{start_idx}_{end_idx}_id{_section_id_counter}"

def validate_section_content(text_lines: List[str], start_idx: int, end_idx: int,
                            section_type: str, section_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Validate that section content matches the expected section type.

    Samples 3 lines from the target span to detect contact headers or misaligned content.

    Args:
        text_lines: List of all text lines
        start_idx: Section start index
        end_idx: Section end index
        section_type: Expected section type
        section_id: Optional section identifier for logging

    Returns:
        Dict with validation results and sample analysis
    """
    validation_result = {
        'is_valid': True,
        'section_id': section_id or generate_section_id(section_type, start_idx, end_idx),
        'section_type': section_type,
        'abs_range': (start_idx, end_idx),
        'sample_lines_hash': None,
        'issues': [],
        'confidence': 1.0
    }

    # Ensure indices are within bounds
    if start_idx < 0 or end_idx > len(text_lines) or start_idx >= end_idx:
        validation_result['is_valid'] = False
        validation_result['issues'].append('invalid_range')
        return validation_result

    # Sample 3 lines from the section (beginning, middle, end)
    sample_indices = []
    section_size = end_idx - start_idx

    if section_size >= 3:
        sample_indices = [start_idx, start_idx + section_size // 2, end_idx - 1]
    elif section_size == 2:
        sample_indices = [start_idx, end_idx - 1]
    elif section_size == 1:
        sample_indices = [start_idx]

    sample_lines = []
    for idx in sample_indices:
        if idx < len(text_lines):
            sample_lines.append(text_lines[idx].strip())

    # Create PII-safe hash of sample content
    sample_content = ' | '.join(sample_lines)
    validation_result['sample_lines_hash'] = hashlib.md5(sample_content.encode()).hexdigest()[:8]

    # Contact header detection patterns
    contact_patterns = [
        r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b',  # Email
        r'\+?\d[\d\s\(\)\-\.]{7,19}',  # Phone numbers
        r'\b\d{1,5}\s+[a-zA-Z\s,]+\s+\d{5}\b',  # Address patterns
        r'\b(?:rue|avenue|boulevard|place|cours|chemin)\s+[a-zA-Z\s\d]+\b',  # French addresses
        r'\b\d{5}\s+[a-zA-Z\s]+\b',  # Postal code + city
    ]

    name_patterns = [
        r'^[A-Z][a-z]+\s+[A-Z][a-z]+$',  # FirstName LastName
        r'^[A-Z\s]{10,}$',  # ALL CAPS names
    ]

    # Check for contact-like content
    contact_score = 0
    for line in sample_lines:
        for pattern in contact_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                contact_score += 1

        for pattern in name_patterns:
            if re.match(pattern, line.strip()):
                contact_score += 0.5

    # If sample looks like contact info, flag as invalid for experience extraction
    if contact_score >= 1.5 and section_type.lower() in ['experience', 'experiences', 'work']:
        validation_result['is_valid'] = False
        validation_result['issues'].append('contact_header_detected')
        validation_result['confidence'] = max(0.0, 1.0 - (contact_score * 0.3))

        logger.warning(f"CONTENT_VALIDATION: contact_header_in_experience | "
                      f"section_id={validation_result['section_id']} "
                      f"contact_score={contact_score} "
                      f"sample_hash={validation_result['sample_lines_hash']}")

    # Check for empty or minimal content
    non_empty_lines = [line for line in sample_lines if line.strip()]
    if len(non_empty_lines) == 0:
        validation_result['is_valid'] = False
        validation_result['issues'].append('empty_content')
    elif len(non_empty_lines) == 1 and len(non_empty_lines[0]) < 10:
        validation_result['issues'].append('minimal_content')
        validation_result['confidence'] *= 0.7

    # Log validation results with PII-safe data
    logger.debug(f"CONTENT_VALIDATION: section_validation | "
                f"section_id={validation_result['section_id']} "
                f"section_type={section_type} "
                f"abs_range=[{start_idx}-{end_idx}] "
                f"sample_hash={validation_result['sample_lines_hash']} "
                f"is_valid={validation_result['is_valid']} "
                f"issues={validation_result['issues']} "
                f"confidence={validation_result['confidence']:.2f}")

    return validation_result

def request_boundary_correction(boundary_guards_instance, text_lines: List[str],
                               failed_validation: Dict[str, Any]) -> Optional[Tuple[int, int, str]]:
    """
    Request a corrected boundary range when validation fails.

    Args:
        boundary_guards_instance: BoundaryGuards instance for re-analysis
        text_lines: List of text lines
        failed_validation: Failed validation result

    Returns:
        Corrected boundary tuple or None if correction not possible
    """
    section_type = failed_validation['section_type']
    original_start, original_end = failed_validation['abs_range']

    logger.info(f"BOUNDARY_CORRECTION: requesting_correction | "
               f"section_id={failed_validation['section_id']} "
               f"original_range=[{original_start}-{original_end}] "
               f"issues={failed_validation['issues']}")

    # Simple correction strategy: skip contact-like lines at the beginning
    if 'contact_header_detected' in failed_validation['issues']:
        # Try to skip the first few lines that look like contact info
        corrected_start = original_start
        contact_patterns = [
            r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b',
            r'\+?\d[\d\s\(\)\-\.]{7,19}',
            r'^[A-Z][a-z]+\s+[A-Z][a-z]+$',
        ]

        for i in range(original_start, min(original_start + 5, original_end, len(text_lines))):
            line = text_lines[i].strip()
            is_contact_like = any(re.search(pattern, line, re.IGNORECASE) for pattern in contact_patterns)

            if not is_contact_like:
                corrected_start = i
                break
            else:
                logger.debug(f"BOUNDARY_CORRECTION: skipping_contact_line | line_idx={i}")

        if corrected_start > original_start and corrected_start < original_end:
            corrected_boundary = (corrected_start, original_end, section_type)
            logger.info(f"BOUNDARY_CORRECTION: correction_applied | "
                       f"original=[{original_start}-{original_end}] "
                       f"corrected=[{corrected_start}-{original_end}]")
            return corrected_boundary

    return None

def normalize_boundaries(obj: Any) -> List[Tuple[int, int, str]]:
    """
    Normalize boundary objects to standard format: [(start, end, section_type), ...].
    
    Handles both plain boundary lists and composite tuples (boundaries, metrics, flags).
    Detects and resolves boundary overlaps by header strength and density.
    
    Args:
        obj: Boundary data - either list of tuples or composite structure
        
    Returns:
        List of normalized (start_idx, end_idx, section_type) tuples with overlaps resolved
        
    Raises:
        ValueError: If boundary format is invalid or contains non-numeric indices
    """
    if obj is None:
        return []
    
    # Handle composite tuple: (boundaries_list, metrics, flags)
    if isinstance(obj, tuple) and len(obj) >= 3:
        boundaries_candidate = obj[0]
        logger.debug(f"BOUNDARY_NORM: unwrapping composite tuple, found {type(boundaries_candidate)}")
        obj = boundaries_candidate
    
    # Ensure we have a list-like object
    if not isinstance(obj, (list, tuple)):
        logger.warning(f"BOUNDARY_NORM: invalid boundary type {type(obj)}, returning empty list")
        return []
    
    normalized = []
    for i, boundary in enumerate(obj):
        try:
            # Validate boundary shape
            if not isinstance(boundary, (tuple, list)) or len(boundary) < 2:
                logger.warning(f"BOUNDARY_NORM: skipping invalid boundary at index {i}: {boundary}")
                continue
                
            # Extract and validate indices
            start_idx = boundary[0] 
            end_idx = boundary[1]
            
            if not isinstance(start_idx, (int, float)) or not isinstance(end_idx, (int, float)):
                logger.warning(f"BOUNDARY_NORM: skipping non-numeric boundary at index {i}: {boundary}")
                continue
            
            # Convert to integers
            start_idx = int(start_idx)
            end_idx = int(end_idx)
            
            # Validate indices make sense
            if start_idx < 0 or end_idx < start_idx:
                logger.warning(f"BOUNDARY_NORM: skipping invalid range at index {i}: {start_idx}-{end_idx}")
                continue
                
            # Extract section type
            section_type = boundary[2] if len(boundary) >= 3 else "unknown"
            section_type = str(section_type) if section_type else "unknown"
            
            normalized.append((start_idx, end_idx, section_type))
            
        except Exception as e:
            logger.warning(f"BOUNDARY_NORM: error processing boundary at index {i}: {e}")
            continue
    
    # Phase 2: Merge adjacent homonymous sections to reduce over-segmentation
    if len(normalized) > 1:
        normalized = merge_adjacent_homonymous_sections(normalized)
    
    # Phase 3: Detect and resolve overlaps
    if len(normalized) <= 1:
        logger.debug(f"BOUNDARY_NORM: no overlaps possible with {len(normalized)} boundaries")
        return normalized
    sorted_boundaries = sorted(normalized, key=lambda x: (x[0], x[1]))
    overlap_count_before = sum(
        1 for current, nxt in zip(sorted_boundaries, sorted_boundaries[1:]) if current[1] > nxt[0]
    )
    merged: List[Tuple[int, int, str]] = []
    for boundary in sorted_boundaries:
        merged.append(boundary)
        idx = len(merged) - 1
        while idx > 0 and merged[idx - 1][1] > merged[idx][0]:
            previous = merged[idx - 1]
            current = merged[idx]
            resolved = resolve_boundary_overlap(previous, current)
            merged[idx - 1] = resolved['primary']
            secondary = resolved.get('secondary')
            if secondary:
                merged[idx] = secondary
            else:
                merged.pop(idx)
                idx -= 1
                continue
            idx -= 1
    merged.sort(key=lambda x: (x[0], x[1]))
    overlap_count_after = sum(
        1 for current, nxt in zip(merged, merged[1:]) if current[1] > nxt[0]
    )
    logger.info(
        f"BOUNDARY_NORM: processed {len(obj or [])} -> {len(normalized)} -> {len(merged)} | "
        f"overlaps_before={overlap_count_before} overlaps_after={overlap_count_after} | merge_phase=enhanced"
    )
    return merged

def merge_adjacent_homonymous_sections(boundaries: List[Tuple[int, int, str]],
                                     max_gap: int = 3) -> List[Tuple[int, int, str]]:
    """
    Merge adjacent sections of the same type that are close together.

    ENHANCED: More stable merge logic with section strength consideration and
    stronger validation to prevent weak sections from merging.

    Args:
        boundaries: List of (start_idx, end_idx, section_type) tuples
        max_gap: Maximum gap in lines to consider sections as adjacent

    Returns:
        List of merged boundaries with adjacent homonymous sections consolidated
    """
    if len(boundaries) <= 1:
        return boundaries

    # Sort boundaries by start index
    sorted_boundaries = sorted(boundaries, key=lambda x: (x[0], x[1]))
    merged = []

    # Section strength mapping for merge decisions
    section_strength = {
        'experiences': 9, 'experience': 9, 'work': 9, 'employment': 9,
        'education': 8, 'formation': 8, 'academic': 8,
        'skills': 7, 'competences': 7, 'abilities': 7,
        'projects': 6, 'projets': 6,
        'certifications': 5, 'certificates': 5,
        'languages': 4, 'langues': 4,
        'interests': 3, 'interets': 3, 'hobbies': 3,
        'personal_info': 2, 'contact': 2,
        'unknown': 1
    }

    i = 0
    while i < len(sorted_boundaries):
        current_start, current_end, current_type = sorted_boundaries[i]
        current_size = current_end - current_start

        # Look for adjacent sections of the same type
        j = i + 1
        merge_candidates = []

        while j < len(sorted_boundaries):
            next_start, next_end, next_type = sorted_boundaries[j]
            next_size = next_end - next_start
            gap = next_start - current_end

            # Enhanced merge conditions
            types_match = current_type.lower() == next_type.lower()
            gap_acceptable = gap <= max_gap

            # Additional merge criteria
            combined_size = current_size + next_size + gap
            size_reasonable = combined_size <= 50  # Prevent overly large merged sections

            # Don't merge very small sections with very large ones (likely misclassified)
            size_ratio = max(current_size, next_size) / max(min(current_size, next_size), 1)
            size_compatible = size_ratio <= 5.0

            # Check section strength
            strength = section_strength.get(current_type.lower(), 1)
            should_merge = (types_match and gap_acceptable and
                          size_reasonable and size_compatible and
                          strength >= 3)  # Only merge reasonably strong sections

            if should_merge:
                merge_candidates.append(j)
                logger.debug(f"BOUNDARY_MERGE: merge_candidate | "
                           f"current=[{current_start}-{current_end}] next=[{next_start}-{next_end}] "
                           f"gap={gap} size_ratio={size_ratio:.1f} strength={strength}")

                # Extend current section to include the next one
                current_end = max(current_end, next_end)
                j += 1
            else:
                # No more adjacent sections of same type or merge criteria not met
                if types_match and not gap_acceptable:
                    logger.debug(f"BOUNDARY_MERGE: gap_too_large | gap={gap} max_gap={max_gap}")
                elif types_match and not size_compatible:
                    logger.debug(f"BOUNDARY_MERGE: size_incompatible | size_ratio={size_ratio:.1f}")
                break

        # Add the merged (or original) section
        merged.append((current_start, current_end, current_type))

        # Log merge details if any merging occurred
        if merge_candidates:
            logger.info(f"BOUNDARY_MERGE: merged_section | "
                       f"type={current_type} "
                       f"original_range=[{sorted_boundaries[i][0]}-{sorted_boundaries[i][1]}] "
                       f"final_range=[{current_start}-{current_end}] "
                       f"merged_count={len(merge_candidates)}")

        i = j  # Skip all merged sections

    merge_count = len(boundaries) - len(merged)
    if merge_count > 0:
        logger.info(f"BOUNDARY_MERGE: consolidated {len(boundaries)} → {len(merged)} sections | "
                   f"merged_count={merge_count}")

    return merged

def validate_boundary_indices(boundaries: List[Tuple[int, int, str]], max_lines: int = None) -> List[Tuple[int, int, str]]:
    """
    Validate boundary indices are within acceptable ranges.
    
    Args:
        boundaries: List of boundary tuples
        max_lines: Optional maximum line count for validation
        
    Returns:
        List of validated boundaries (invalid ones removed)
    """
    validated = []
    
    for start_idx, end_idx, section_type in boundaries:
        # Basic range validation
        if start_idx < 0:
            logger.warning(f"BOUNDARY_VALID: negative start index {start_idx}, skipping")
            continue
            
        if end_idx < start_idx:
            logger.warning(f"BOUNDARY_VALID: end before start {start_idx}-{end_idx}, skipping") 
            continue
            
        # Optional max lines validation
        if max_lines and (start_idx >= max_lines or end_idx > max_lines):
            logger.warning(f"BOUNDARY_VALID: indices beyond max_lines {max_lines}: {start_idx}-{end_idx}, skipping")
            continue
            
        validated.append((start_idx, end_idx, section_type))
    
    return validated

def resolve_boundary_overlap(boundary1: Tuple[int, int, str], boundary2: Tuple[int, int, str]) -> Dict[str, Any]:
    """
    Resolve overlap between two boundaries based on header strength and content density.
    
    Args:
        boundary1: First boundary tuple (start, end, section_type)
        boundary2: Second boundary tuple (start, end, section_type)
        
    Returns:
        Dict with 'primary' boundary (kept), 'secondary' boundary (adjusted or removed),
        and 'secondary_kept' flag indicating if secondary was preserved
    """
    start1, end1, type1 = boundary1
    start2, end2, type2 = boundary2
    
    # Calculate overlap region
    overlap_start = max(start1, start2)
    overlap_end = min(end1, end2)
    overlap_size = max(0, overlap_end - overlap_start)
    
    # Header strength scoring (based on section importance)
    section_priority = {
        'experiences': 9, 'experience': 9, 'work': 9, 'employment': 9,
        'education': 8, 'formation': 8, 'academic': 8,
        'skills': 7, 'competences': 7, 'abilities': 7,
        'projects': 6, 'projets': 6,
        'certifications': 5, 'certificates': 5,
        'languages': 4, 'langues': 4,
        'interests': 3, 'interets': 3, 'hobbies': 3,
        'personal_info': 2, 'contact': 2,
        'unknown': 1
    }
    
    strength1 = section_priority.get(type1.lower(), 1)
    strength2 = section_priority.get(type2.lower(), 1)
    
    # Calculate density (size as proxy for content density)
    density1 = end1 - start1
    density2 = end2 - start2
    
    logger.debug(f"OVERLAP_RESOLVE: {type1}({strength1}, {density1}) vs {type2}({strength2}, {density2}) | "
                f"overlap={overlap_size}")
    
    # Resolution strategy
    if strength1 > strength2:
        # Boundary1 has higher priority - keep it, adjust boundary2
        primary = boundary1
        if start2 >= end1:
            # No actual overlap after sorting, keep both
            secondary = boundary2
            secondary_kept = True
        else:
            # Shrink boundary2 to non-overlapping region
            adjusted_start2 = max(start2, end1)
            if adjusted_start2 < end2:
                secondary = (adjusted_start2, end2, type2)
                secondary_kept = True
            else:
                secondary = None
                secondary_kept = False
                
    elif strength2 > strength1:
        # Boundary2 has higher priority - keep it, adjust boundary1  
        primary = boundary2
        adjusted_end1 = min(end1, start2)
        if adjusted_end1 > start1:
            secondary = (start1, adjusted_end1, type1)
            secondary_kept = True
        else:
            secondary = None
            secondary_kept = False
            
    else:
        # Equal priority - use density as tiebreaker
        if density1 >= density2:
            primary = boundary1
            adjusted_start2 = max(start2, end1)
            secondary = (adjusted_start2, end2, type2) if adjusted_start2 < end2 else None
            secondary_kept = secondary is not None
        else:
            primary = boundary2
            adjusted_end1 = min(end1, start2)
            secondary = (start1, adjusted_end1, type1) if adjusted_end1 > start1 else None
            secondary_kept = secondary is not None
    
    result = {
        'primary': primary,
        'secondary': secondary,
        'secondary_kept': secondary_kept,
        'overlap_size': overlap_size,
        'resolution_reason': f"strength_{strength1}vs{strength2}_density_{density1}vs{density2}"
    }
    
    logger.debug(f"OVERLAP_RESOLVE: result={result['resolution_reason']} | "
                f"kept={result['primary']} | secondary_kept={result['secondary_kept']}")
    
    return result

class BoundaryGuards:
    """Implements boundary detection and header conflict guards for extraction."""
    
    def __init__(self, config: Dict[str, Any] = None, **legacy_kwargs):
        self.config = config or EXPERIENCE_CONF

        raw_threshold = legacy_kwargs.pop('confidence_threshold', 0.7)
        try:
            raw_threshold = float(raw_threshold)
        except (TypeError, ValueError):
            raw_threshold = 0.7
        self.confidence_threshold = max(0.0, min(1.0, raw_threshold))

        self.max_violations = legacy_kwargs.pop('max_violations', None)
        custom_severity = legacy_kwargs.pop('violation_weights', None)
        self.violation_severity = custom_severity or {
            ContaminationType.HEADER_POLLUTION: 0.95,
            ContaminationType.BULLET_CONTAMINATION: 0.80,
            ContaminationType.FORMATTING_ARTIFACTS: 0.75,
            ContaminationType.CROSS_SECTION_LEAK: 0.70,
            ContaminationType.OTHER: 0.50,
        }
        if legacy_kwargs:
            logger.debug("BOUNDARY_GUARDS: ignored legacy kwargs=%s", sorted(legacy_kwargs.keys()))

        self.education_headers = [
            "FORMATION", "ÉDUCATION", "EDUCATION", "DIPLÔMES", "DIPLOMES",
            "ÉTUDES", "ETUDES", "ACADEMIC", "ACADEMICS", "SCHOOLING",
            "DEGREE", "DEGREES", "QUALIFICATION", "QUALIFICATIONS"
        ]
        self.timeline_indicators = [
            r"\d{4}[-–—]\d{4}", r"\d{2}/\d{4}[-–—]\d{2}/\d{4}",
            r"depuis", r"until", r"to", r"from", r"→", r"▶", r"►"
        ]


    def check_header_conflict_killradius(self, text_lines: List[str], 
                                        target_line_idx: int) -> Tuple[bool, Optional[str], int]:
        """
        Check if education headers appear within kill radius of target line.
        
        Args:
            text_lines: List of text lines
            target_line_idx: Index of target line for experience extraction
            
        Returns:
            (has_conflict, conflicting_header, distance)
        """
        kill_radius = self.config["header_conflict_killradius_lines"]
        
        start_idx = max(0, target_line_idx - kill_radius)
        end_idx = min(len(text_lines), target_line_idx + kill_radius + 1)
        
        for i in range(start_idx, end_idx):
            if i >= len(text_lines):
                continue
                
            line = text_lines[i].strip().upper()
            
            for header in self.education_headers:
                if header in line:
                    distance = abs(i - target_line_idx)
                    logger.debug(f"HEADER_CONFLICT: detected | line={i} header='{header}' "
                               f"distance={distance} target_line={target_line_idx}")
                    return True, header, distance
                    
        return False, None, -1
        
    def check_cross_column_distance(self, entity1_line: int, entity2_line: int) -> bool:
        """
        Check if two entities are too far apart in column layout.
        
        Args:
            entity1_line: Line index of first entity
            entity2_line: Line index of second entity
            
        Returns:
            True if entities can be linked (within distance threshold)
        """
        max_distance = self.config["max_cross_column_distance_lines"]
        distance = abs(entity1_line - entity2_line)
        
        can_link = distance <= max_distance
        
        if not can_link:
            logger.debug(f"CROSS_COLUMN: distance_exceeded | entity1_line={entity1_line} "
                        f"entity2_line={entity2_line} distance={distance} max={max_distance}")
                        
        return can_link
        
    def detect_timeline_block(self, text_lines: List[str], 
                             start_idx: int, end_idx: int) -> Tuple[bool, float]:
        """
        Detect if a block of text appears to be a timeline or sidebar.
        
        Args:
            text_lines: List of text lines
            start_idx: Start index of block
            end_idx: End index of block
            
        Returns:
            (is_timeline, density_score)
        """
        if not self.config.get("sidebar_timeline_exclusion", True):
            return False, 0.0
            
        window_size = self.config["timeline_window_size"]
        density_threshold = self.config["timeline_density_threshold"]
        
        timeline_tokens = 0
        total_tokens = 0
        
        # Analyze in sliding windows
        for window_start in range(start_idx, max(start_idx, end_idx - window_size + 1)):
            window_end = min(window_start + window_size, end_idx, len(text_lines))
            
            for i in range(window_start, window_end):
                if i >= len(text_lines):
                    continue
                    
                line = text_lines[i]
                tokens = line.split()
                total_tokens += len(tokens)
                
                # Count timeline indicators
                for pattern in self.timeline_indicators:
                    timeline_tokens += len(re.findall(pattern, line, re.IGNORECASE))
                
                # Count date tokens and connectors
                for token in tokens:
                    if re.match(r'\d{4}|\d{1,2}/\d{4}', token):
                        timeline_tokens += 1
                    elif token.lower() in ['to', 'from', 'until', 'depuis', 'until', '→', '▶', '►', '-', '–', '—']:
                        timeline_tokens += 1
                        
        density = timeline_tokens / total_tokens if total_tokens > 0 else 0.0
        is_timeline = density > density_threshold
        
        if is_timeline:
            logger.debug(f"TIMELINE_BLOCK: detected | start_idx={start_idx} end_idx={end_idx} "
                        f"density={density:.3f} threshold={density_threshold}")
                        
        return is_timeline, density
        
    def should_terminate_window_expansion(self, text_lines: List[str], 
                                        current_window_start: int,
                                        current_window_end: int,
                                        proposed_expansion_line: int) -> Tuple[bool, List[str]]:
        """
        Determine if window expansion should be terminated based on boundary guards.
        
        Args:
            text_lines: List of text lines
            current_window_start: Current window start index
            current_window_end: Current window end index  
            proposed_expansion_line: Line index of proposed expansion
            
        Returns:
            (should_terminate, termination_reasons)
        """
        reasons = []
        
        # Check header conflict kill radius
        has_header_conflict, header, distance = self.check_header_conflict_killradius(
            text_lines, proposed_expansion_line
        )
        
        if has_header_conflict:
            reasons.append(f"header_conflict_{header.lower()}_distance_{distance}")
            
        # Check if expansion crosses into timeline block
        is_timeline, density = self.detect_timeline_block(
            text_lines, 
            min(current_window_start, proposed_expansion_line),
            max(current_window_end, proposed_expansion_line)
        )
        
        if is_timeline:
            reasons.append(f"timeline_block_density_{density:.3f}")
            
        # Check cross-column distance from window center
        window_center = (current_window_start + current_window_end) // 2
        if not self.check_cross_column_distance(window_center, proposed_expansion_line):
            reasons.append("cross_column_distance_exceeded")
            
        should_terminate = len(reasons) > 0
        
        if should_terminate:
            logger.info(f"BOUNDARY_GUARD: terminating_expansion | "
                       f"window=[{current_window_start}, {current_window_end}] "
                       f"proposed_line={proposed_expansion_line} reasons={reasons}")
                       
        return should_terminate, reasons

class TriSignalValidator:
    """Validates tri-signal linkage requirements for experiences."""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or EXPERIENCE_CONF
        
    def validate_tri_signal_linkage(self, text_lines: List[str],
                                  target_line_idx: int,
                                  entities: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Validate that at least 2 of {date, org, role} are present within tri_signal_window.
        
        Args:
            text_lines: List of text lines
            target_line_idx: Index of target line
            entities: Optional list of NER entities with line_idx
            
        Returns:
            Dict with validation results and signal details
        """
        window = self.config["tri_signal_window"]
        min_signals = self.config["tri_signal_min_signals"]
        require_date = self.config["tri_signal_require_date"]
        
        start_idx = max(0, target_line_idx - window)
        end_idx = min(len(text_lines), target_line_idx + window + 1)
        
        signals_found = {
            'date': [],
            'org': [],
            'role': []
        }
        
        # Analyze lines in window
        for i in range(start_idx, end_idx):
            if i >= len(text_lines):
                continue
                
            line = text_lines[i]
            
            # Date detection
            date_patterns = [
                r'\b\d{4}\b',
                r'\b\d{1,2}/\d{4}\b',
                r'\b\d{1,2}/\d{2}/\d{4}\b',
                r'\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{4}\b',
                r'\b(?:janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s+\d{4}\b'
            ]
            
            for pattern in date_patterns:
                matches = re.findall(pattern, line, re.IGNORECASE)
                for match in matches:
                    signals_found['date'].append({
                        'line_idx': i,
                        'text': match,
                        'pattern': pattern
                    })
            
            # Organization detection (basic patterns)
            org_indicators = ['chez', 'at', 'company', 'corp', 'inc', 'ltd', 'sarl', 'sas']
            for indicator in org_indicators:
                if indicator.lower() in line.lower():
                    signals_found['org'].append({
                        'line_idx': i,
                        'text': line.strip()[:50],  # First 50 chars
                        'indicator': indicator
                    })
                    break  # Avoid double counting
                    
            # Role detection (basic patterns)  
            role_indicators = ['developer', 'engineer', 'manager', 'analyst', 'consultant', 
                             'développeur', 'ingénieur', 'responsable', 'chef', 'directeur']
            for indicator in role_indicators:
                if indicator.lower() in line.lower():
                    signals_found['role'].append({
                        'line_idx': i,
                        'text': line.strip()[:50],
                        'indicator': indicator
                    })
                    break
        
        # Use NER entities if available
        if entities:
            for entity in entities:
                entity_line = entity.get('line_idx', -1)
                if start_idx <= entity_line < end_idx:
                    label = entity.get('label', '').upper()
                    text = entity.get('text', '')
                    
                    if label == 'ORG':
                        signals_found['org'].append({
                            'line_idx': entity_line,
                            'text': text,
                            'source': 'ner'
                        })
                    elif label in ['PER', 'MISC'] and any(role in text.lower() 
                                                        for role in ['developer', 'engineer', 'manager']):
                        signals_found['role'].append({
                            'line_idx': entity_line,
                            'text': text,
                            'source': 'ner'
                        })
        
        # Count unique signals
        signal_counts = {
            'date': len(set(s['line_idx'] for s in signals_found['date'])),
            'org': len(set(s['line_idx'] for s in signals_found['org'])),  
            'role': len(set(s['line_idx'] for s in signals_found['role']))
        }
        
        total_signals = sum(1 for count in signal_counts.values() if count > 0)
        has_date = signal_counts['date'] > 0
        
        # Validation
        passes_tri_signal = (
            total_signals >= min_signals and
            (not require_date or has_date)
        )
        
        logger.debug(f"TRI_SIGNAL: validation | target_line={target_line_idx} "
                    f"signals={signal_counts} total={total_signals} "
                    f"min_required={min_signals} has_date={has_date} "
                    f"passes={passes_tri_signal}")
        
        return {
            'passes': passes_tri_signal,
            'total_signals': total_signals,
            'signal_counts': signal_counts,
            'signals_found': signals_found,
            'has_date': has_date,
            'window_analyzed': [start_idx, end_idx]
        }

# Global instances
boundary_guards = BoundaryGuards()
tri_signal_validator = TriSignalValidator()

def _bg_analyze_content_blocks(self, text: str) -> List[AnalyzedBlock]:
    blocks: List[AnalyzedBlock] = []
    if not text:
        return blocks
    normalized = text or ""
    normalized = normalized.replace("\r", "")
    for chunk in normalized.split("\n\n"):
        chunk = chunk.strip()
        if not chunk:
            continue
        block_type = 'header' if chunk.isupper() else 'content'
        proximity = 0.9 if block_type == 'header' else 0.75
        blocks.append(AnalyzedBlock(text=chunk, block_type=block_type, proximity_score=proximity))
    return blocks

def _bg_detect_violations(self, field: str, value: str, context_lines: Iterable[str]) -> List[BoundaryViolation]:
    violations: List[BoundaryViolation] = []
    text_value = (value or "").strip()
    if not text_value:
        return violations

    threshold = getattr(self, "confidence_threshold", 0.7)
    severity_map = getattr(self, "violation_severity", {})
    limit = getattr(self, "max_violations", None)

    def register(violation_type: ContaminationType, details: str = "") -> None:
        severity = severity_map.get(violation_type, 0.5)
        if severity < threshold:
            return
        violation = BoundaryViolation(violation_type, field, details=details, confidence=severity)
        violations.append(violation)

    lower = text_value.lower()

    if any(header.lower() in lower for header in self.education_headers) and field != 'education':
        register(ContaminationType.HEADER_POLLUTION, details=text_value[:80])
        if limit is not None and len(violations) >= limit:
            return violations

    bullet_chars = {"•", "●", "○", "◦", "·", "-", "*", "►", "▪"}
    if text_value[:1] in bullet_chars or any(ch in text_value for ch in bullet_chars):
        register(ContaminationType.BULLET_CONTAMINATION)
        if limit is not None and len(violations) >= limit:
            return violations

    if any(char in text_value for char in ('', '​', ' ', '')):
        register(ContaminationType.FORMATTING_ARTIFACTS)
        if limit is not None and len(violations) >= limit:
            return violations

    if field == 'job_title' and any(token in lower for token in ("degree", "diplôme", "licence")):
        register(ContaminationType.CROSS_SECTION_LEAK)
        if limit is not None and len(violations) >= limit:
            return violations

    return violations

def _bg_clean_field_value(self, value: str, violations: Iterable[BoundaryViolation]) -> str:
    cleaned = value or ""
    for bullet in ("•", "●", "○", "◦", "·", "*", "►", "▪"):
        cleaned = cleaned.replace(bullet, "")
    cleaned = cleaned.replace('', '').replace('​', '').replace(' ', '')
    return ' '.join(cleaned.strip().split())

def _bg_validate_extraction(self, extracted: Dict[str, Any], source_text: str) -> Dict[str, Any]:
    cleaned = {}
    violation_list: List[BoundaryViolation] = []
    for field, val in (extracted or {}).items():
        violations = _bg_detect_violations(self, field, val, [])
        violation_list.extend(violations)
        cleaned[field] = _bg_clean_field_value(self, val, violations)
    return {
        'cleaned_data': cleaned,
        'violations': violation_list,
        'violation_count': len(violation_list),
        'contamination_score': min(len(violation_list) / max(len(extracted or {}), 1), 1.0),
    }

BoundaryGuards.analyze_content_blocks = _bg_analyze_content_blocks
BoundaryGuards.detect_violations = _bg_detect_violations
BoundaryGuards.clean_field_value = _bg_clean_field_value
BoundaryGuards.validate_extraction = _bg_validate_extraction
