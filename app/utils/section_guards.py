"""
Section guards for experience and education extraction.
Prevents contact/header lines from being consumed by EXP/EDU pipelines.
"""

from typing import List, Dict, Any, Optional, Tuple, Set
from ..logging.safe_logger import get_safe_logger, DEFAULT_PII_CONFIG
from .contact_line_detector import ContactLineDetector, ContactLineResult
from .extraction_metrics import get_metrics_collector
from cvextractor.core.types import TextLine

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


class SectionGuards:
    """Guards to protect contact/header lines from section extraction."""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = dict(config or {})
        self.contact_detector = ContactLineDetector(self.config.get('contact_detector', {}))
        self.metrics = get_metrics_collector()
        
        # Configuration
        self.guard_enabled = self.config.get('enable_section_guards', True)
        self.strict_header_block = self.config.get('strict_header_block_protection', True)
        
        logger.debug(f"SECTION_GUARDS: initialized | enabled={self.guard_enabled}")
    
    def apply_contact_flags(self, text_lines: List[str]) -> List[TextLine]:
        """
        Apply contact detection flags to text lines.
        
        Args:
            text_lines: Raw text lines
            
        Returns:
            List of TextLine objects with contact flags
        """
        if not self.guard_enabled:
            # Return basic TextLine objects without protection
            return [TextLine(text=line, line_idx=i) for i, line in enumerate(text_lines)]
        
        # Detect contact lines
        contact_results = self.contact_detector.detect_contact_lines(text_lines)
        
        # Convert to TextLine objects with flags
        protected_lines = []
        for i, line in enumerate(text_lines):
            contact_result = contact_results[i] if i < len(contact_results) else ContactLineResult(
                line_idx=i, is_contact=False, header_block=False, contact_types=[], confidence=0.0
            )
            
            text_line = TextLine(
                text=line,
                line_idx=i,
                is_contact=contact_result.is_contact,
                header_block=contact_result.header_block,
                contact_types=contact_result.contact_types,
                confidence=contact_result.confidence
            )
            
            protected_lines.append(text_line)
        
        # Log protection summary
        protected_count = sum(1 for line in protected_lines if line.is_protected())
        contact_count = sum(1 for line in protected_lines if line.is_contact)
        header_count = sum(1 for line in protected_lines if line.header_block)
        
        logger.info(f"CONTACT_FLAGS: applied | lines={len(text_lines)} "
                   f"protected={protected_count} contact={contact_count} header_block={header_count}")
        
        return protected_lines
    
    def filter_experience_candidates(self, candidates: List[Dict[str, Any]], 
                                   protected_lines: List[TextLine]) -> List[Dict[str, Any]]:
        """
        Filter experience candidates to remove those using protected lines.
        
        Args:
            candidates: List of experience candidates
            protected_lines: List of TextLine objects with protection flags
            
        Returns:
            List of filtered candidates
        """
        if not self.guard_enabled:
            return candidates
        
        filtered_candidates = []
        blocked_count = 0
        
        for candidate in candidates:
            if self._candidate_uses_protected_lines(candidate, protected_lines):
                blocked_count += 1
                
                # Record metrics based on protection type
                source_line_idx = candidate.get('source_line_idx', -1)
                if 0 <= source_line_idx < len(protected_lines):
                    line = protected_lines[source_line_idx]
                    if line.header_block:
                        self.metrics.block_header_line_in_exp(source_line_idx, "header_block")
                    if line.is_contact:
                        contact_type = ', '.join(line.contact_types) if line.contact_types else 'unknown'
                        self.metrics.block_contact_line_in_exp(source_line_idx, contact_type)
                
                logger.debug(f"EXP_GUARD: blocked_candidate | line={source_line_idx} "
                           f"reason={'header' if line.header_block else 'contact'}")
            else:
                filtered_candidates.append(candidate)
        
        logger.info(f"EXP_GUARDS: filtered | input={len(candidates)} output={len(filtered_candidates)} "
                   f"blocked={blocked_count}")
        
        return filtered_candidates
    
    def filter_education_candidates(self, candidates: List[Dict[str, Any]], 
                                  protected_lines: List[TextLine]) -> List[Dict[str, Any]]:
        """
        Filter education candidates to remove those using protected lines.
        
        Args:
            candidates: List of education candidates
            protected_lines: List of TextLine objects with protection flags
            
        Returns:
            List of filtered candidates
        """
        if not self.guard_enabled:
            return candidates
        
        filtered_candidates = []
        blocked_count = 0
        
        for candidate in candidates:
            if self._candidate_uses_protected_lines(candidate, protected_lines):
                blocked_count += 1
                
                # Record metrics based on protection type
                source_line_idx = candidate.get('source_line_idx', -1)
                if 0 <= source_line_idx < len(protected_lines):
                    line = protected_lines[source_line_idx]
                    if line.header_block:
                        self.metrics.block_header_line_in_edu(source_line_idx, "header_block")
                    if line.is_contact:
                        contact_type = ', '.join(line.contact_types) if line.contact_types else 'unknown'
                        self.metrics.block_contact_line_in_edu(source_line_idx, contact_type)
                
                logger.debug(f"EDU_GUARD: blocked_candidate | line={source_line_idx} "
                           f"reason={'header' if line.header_block else 'contact'}")
            else:
                filtered_candidates.append(candidate)
        
        logger.info(f"EDU_GUARDS: filtered | input={len(candidates)} output={len(filtered_candidates)} "
                   f"blocked={blocked_count}")
        
        return filtered_candidates
    
    def _candidate_uses_protected_lines(self, candidate: Dict[str, Any], 
                                      protected_lines: List[TextLine]) -> bool:
        """Check if candidate uses any protected lines."""
        
        # Check single source line
        source_line_idx = candidate.get('source_line_idx')
        if source_line_idx is not None and 0 <= source_line_idx < len(protected_lines):
            if protected_lines[source_line_idx].is_protected():
                return True
        
        # Check multiple source lines
        source_line_ids = candidate.get('source_line_ids', [])
        for line_idx in source_line_ids:
            if 0 <= line_idx < len(protected_lines):
                if protected_lines[line_idx].is_protected():
                    return True
        
        # Check line range consumption
        start_line = candidate.get('start_line_idx')
        end_line = candidate.get('end_line_idx') 
        if start_line is not None and end_line is not None:
            for line_idx in range(start_line, min(end_line + 1, len(protected_lines))):
                if protected_lines[line_idx].is_protected():
                    return True
        
        return False
    
    def get_protected_line_indices(self, protected_lines: List[TextLine]) -> Set[int]:
        """Get set of all protected line indices."""
        return {line.line_idx for line in protected_lines if line.is_protected()}
    
    def get_contact_line_indices(self, protected_lines: List[TextLine]) -> Set[int]:
        """Get set of contact line indices."""
        return {line.line_idx for line in protected_lines if line.is_contact}
    
    def get_header_block_indices(self, protected_lines: List[TextLine]) -> Set[int]:
        """Get set of header block line indices."""
        return {line.line_idx for line in protected_lines if line.header_block}
    
    def validate_extraction_bounds(self, section_bounds: Tuple[int, int], 
                                 protected_lines: List[TextLine]) -> Tuple[int, int]:
        """
        Validate and adjust extraction bounds to avoid protected lines.
        
        Args:
            section_bounds: Original (start, end) bounds
            protected_lines: List of protected lines
            
        Returns:
            Adjusted (start, end) bounds
        """
        if not self.guard_enabled or not self.strict_header_block:
            return section_bounds
        
        start_idx, end_idx = section_bounds
        
        # Adjust start to skip header blocks at beginning
        while start_idx <= end_idx and start_idx < len(protected_lines):
            if protected_lines[start_idx].header_block:
                start_idx += 1
                logger.debug(f"BOUNDS_ADJUST: skipped_header_start | new_start={start_idx}")
            else:
                break
        
        # Ensure we still have valid bounds
        if start_idx > end_idx:
            logger.warning(f"BOUNDS_INVALID: start > end after adjustment | start={start_idx} end={end_idx}")
            return section_bounds  # Return original bounds as fallback
        
        return start_idx, end_idx
    
    def create_protection_summary(self, protected_lines: List[TextLine]) -> Dict[str, Any]:
        """Create summary of line protection status."""
        total_lines = len(protected_lines)
        protected_count = sum(1 for line in protected_lines if line.is_protected())
        contact_count = sum(1 for line in protected_lines if line.is_contact)
        header_count = sum(1 for line in protected_lines if line.header_block)
        
        # Contact type distribution
        contact_type_counts = {}
        for line in protected_lines:
            if line.is_contact:
                for contact_type in line.contact_types:
                    contact_type_counts[contact_type] = contact_type_counts.get(contact_type, 0) + 1
        
        return {
            'total_lines': total_lines,
            'protected_lines': protected_count,
            'contact_lines': contact_count,
            'header_block_lines': header_count,
            'protection_rate': protected_count / max(1, total_lines),
            'contact_type_distribution': contact_type_counts,
            'guards_enabled': self.guard_enabled
        }


# Module-level convenience functions
_global_guards: Optional[SectionGuards] = None


def get_section_guards(config: Dict[str, Any] = None) -> SectionGuards:
    """Get or create the global section guards instance."""
    global _global_guards
    
    if _global_guards is None:
        _global_guards = SectionGuards(config)
    
    return _global_guards


def apply_contact_protection(text_lines: List[str]) -> List[TextLine]:
    """Convenience function to apply contact protection flags."""
    guards = get_section_guards()
    return guards.apply_contact_flags(text_lines)


def filter_exp_candidates_safe(candidates: List[Dict[str, Any]], 
                              protected_lines: List[TextLine]) -> List[Dict[str, Any]]:
    """Convenience function to filter experience candidates."""
    guards = get_section_guards()
    return guards.filter_experience_candidates(candidates, protected_lines)


def filter_edu_candidates_safe(candidates: List[Dict[str, Any]], 
                              protected_lines: List[TextLine]) -> List[Dict[str, Any]]:
    """Convenience function to filter education candidates."""
    guards = get_section_guards()
    return guards.filter_education_candidates(candidates, protected_lines)
