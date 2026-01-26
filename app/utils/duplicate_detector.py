"""
Duplicate detection system for extraction candidates.
Prevents loop issues and repeated false insertions across extraction passes.
"""

import hashlib
import json
from typing import Dict, Any, List, Set, Optional, Tuple
from dataclasses import dataclass
from ..logging.safe_logger import get_safe_logger, DEFAULT_PII_CONFIG
from .extraction_metrics import get_metrics_collector

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


@dataclass
class CandidateKey:
    """Structured key for candidate deduplication."""
    title: str
    company: str
    start_date: str
    end_date: str
    source_line_ids: Tuple[int, ...]
    
    def to_hash(self) -> str:
        """Generate stable hash for this candidate."""
        # Normalize values for consistent hashing
        normalized = {
            'title': self._normalize_text(self.title),
            'company': self._normalize_text(self.company),
            'start_date': self._normalize_date(self.start_date),
            'end_date': self._normalize_date(self.end_date),
            'source_lines': sorted(self.source_line_ids) if self.source_line_ids else []
        }
        
        # Create stable JSON representation
        stable_json = json.dumps(normalized, sort_keys=True, ensure_ascii=False)
        
        # Generate SHA-256 hash
        hash_obj = hashlib.sha256(stable_json.encode('utf-8'))
        return hash_obj.hexdigest()
    
    def _normalize_text(self, text: str) -> str:
        """Normalize text for consistent comparison."""
        if not text:
            return ""
        return text.lower().strip()
    
    def _normalize_date(self, date: str) -> str:
        """Normalize date for consistent comparison."""
        if not date:
            return ""
        # Simple normalization - remove common variations
        return date.lower().strip().replace(' ', '')


class DuplicateDetector:
    """Detects and manages duplicate candidates across extraction passes."""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.seen_keys: Set[str] = set()
        self.key_details: Dict[str, Dict[str, Any]] = {}
        self.metrics = get_metrics_collector()
        
        # Configuration
        self.max_passes = self.config.get('max_extraction_passes', 3)
        self.min_title_length = self.config.get('min_title_length', 2)
        self.min_company_length = self.config.get('min_company_length', 2)
        
        logger.debug(f"DUPLICATE_DETECTOR: initialized | max_passes={self.max_passes}")
    
    def create_candidate_key(self, candidate: Dict[str, Any]) -> Optional[CandidateKey]:
        """
        Create a structured key from a candidate for deduplication.
        
        Args:
            candidate: Candidate dictionary with title, company, dates, etc.
            
        Returns:
            CandidateKey object or None if candidate is invalid
        """
        title = candidate.get('title', '').strip()
        company = candidate.get('company', '').strip()
        
        # Validate minimum requirements
        if len(title) < self.min_title_length or len(company) < self.min_company_length:
            logger.debug(f"DUPLICATE_KEY: candidate_too_short | title_len={len(title)} company_len={len(company)}")
            return None
        
        # Extract source line IDs
        source_line_ids = []
        if 'source_line_idx' in candidate:
            source_line_ids.append(candidate['source_line_idx'])
        if 'source_line_ids' in candidate:
            source_line_ids.extend(candidate['source_line_ids'])
        
        return CandidateKey(
            title=title,
            company=company,
            start_date=candidate.get('start_date', ''),
            end_date=candidate.get('end_date', ''),
            source_line_ids=tuple(sorted(set(source_line_ids)))
        )
    
    def is_duplicate(self, candidate: Dict[str, Any], pass_number: int = 1) -> Tuple[bool, Optional[str]]:
        """
        Check if candidate is a duplicate of previously seen item.
        
        Args:
            candidate: Candidate to check
            pass_number: Current extraction pass number
            
        Returns:
            (is_duplicate, key_hash) tuple
        """
        candidate_key = self.create_candidate_key(candidate)
        if not candidate_key:
            return False, None
        
        key_hash = candidate_key.to_hash()
        
        if key_hash in self.seen_keys:
            # Record duplicate detection
            self.metrics.drop_duplicate_candidate(key_hash, f"pass_{pass_number}")
            
            # Log details for debugging
            existing_details = self.key_details.get(key_hash, {})
            logger.debug(f"DUPLICATE_DETECTED: pass={pass_number} | "
                        f"title='[REDACTED]' company='[REDACTED]' "
                        f"first_seen_pass={existing_details.get('first_pass', 'unknown')}")
            
            return True, key_hash
        
        # Record as new key
        self.seen_keys.add(key_hash)
        self.key_details[key_hash] = {
            'first_pass': pass_number,
            'title_len': len(candidate_key.title),
            'company_len': len(candidate_key.company),
            'source_line_count': len(candidate_key.source_line_ids)
        }
        
        logger.debug(f"DUPLICATE_NEW: pass={pass_number} key='{key_hash[:8]}...' | "
                    f"title_len={len(candidate_key.title)} company_len={len(candidate_key.company)}")
        
        return False, key_hash
    
    def filter_duplicates(self, candidates: List[Dict[str, Any]], pass_number: int = 1) -> List[Dict[str, Any]]:
        """
        Filter out duplicate candidates from a list.
        
        Args:
            candidates: List of candidates to filter
            pass_number: Current extraction pass number
            
        Returns:
            List of unique candidates
        """
        if not candidates:
            return candidates
        
        unique_candidates = []
        duplicates_found = 0
        
        for candidate in candidates:
            is_duplicate, key_hash = self.is_duplicate(candidate, pass_number)
            
            if not is_duplicate:
                # Add key hash to candidate for tracking
                candidate['_dedup_key'] = key_hash
                unique_candidates.append(candidate)
            else:
                duplicates_found += 1
        
        logger.info(f"DUPLICATE_FILTER: pass={pass_number} | "
                   f"input={len(candidates)} output={len(unique_candidates)} "
                   f"duplicates_removed={duplicates_found}")
        
        return unique_candidates
    
    def should_continue_extraction(self, current_pass: int, new_items_count: int) -> bool:
        """
        Determine if extraction should continue to next pass.
        
        Args:
            current_pass: Current pass number (1-based)
            new_items_count: Number of new items found in this pass
            
        Returns:
            True if extraction should continue
        """
        # Stop if max passes reached
        if current_pass >= self.max_passes:
            logger.info(f"EXTRACTION_STOP: max_passes_reached | pass={current_pass}")
            return False
        
        # Stop if no new items found (zero-yield pass)
        if new_items_count == 0:
            logger.info(f"EXTRACTION_STOP: zero_yield_pass | pass={current_pass}")
            return False
        
        # Continue extraction
        logger.debug(f"EXTRACTION_CONTINUE: pass={current_pass} new_items={new_items_count}")
        return True
    
    def get_deduplication_stats(self) -> Dict[str, Any]:
        """Get statistics about deduplication process."""
        return {
            'total_unique_keys': len(self.seen_keys),
            'duplicates_blocked': self.metrics.contact_protection.duplicate_candidates_dropped,
            'pass_distribution': self._get_pass_distribution(),
            'avg_source_lines': self._get_avg_source_lines()
        }
    
    def _get_pass_distribution(self) -> Dict[str, int]:
        """Get distribution of candidates by first-seen pass."""
        distribution = {}
        for details in self.key_details.values():
            pass_num = details.get('first_pass', 'unknown')
            key = f"pass_{pass_num}"
            distribution[key] = distribution.get(key, 0) + 1
        return distribution
    
    def _get_avg_source_lines(self) -> float:
        """Get average number of source lines per candidate."""
        if not self.key_details:
            return 0.0
        
        total_lines = sum(details.get('source_line_count', 0) for details in self.key_details.values())
        return total_lines / len(self.key_details)
    
    def reset(self):
        """Reset the detector state for a new document."""
        self.seen_keys.clear()
        self.key_details.clear()
        logger.debug("DUPLICATE_DETECTOR: reset_for_new_document")
    
    def export_seen_keys(self) -> List[str]:
        """Export seen keys for debugging or analysis."""
        return list(self.seen_keys)


# Module-level convenience functions
_global_detector: Optional[DuplicateDetector] = None


def get_duplicate_detector(config: Dict[str, Any] = None) -> DuplicateDetector:
    """Get or create the global duplicate detector instance."""
    global _global_detector
    
    if _global_detector is None:
        _global_detector = DuplicateDetector(config)
    
    return _global_detector


def reset_duplicate_detector():
    """Reset the global duplicate detector."""
    global _global_detector
    if _global_detector:
        _global_detector.reset()


def is_candidate_duplicate(candidate: Dict[str, Any], pass_number: int = 1) -> bool:
    """Convenience function to check if candidate is duplicate."""
    detector = get_duplicate_detector()
    is_duplicate, _ = detector.is_duplicate(candidate, pass_number)
    return is_duplicate


def filter_duplicate_candidates(candidates: List[Dict[str, Any]], pass_number: int = 1) -> List[Dict[str, Any]]:
    """Convenience function to filter duplicate candidates."""
    detector = get_duplicate_detector()
    return detector.filter_duplicates(candidates, pass_number)