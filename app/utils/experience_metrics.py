"""
Experience Metrics - Comprehensive metrics tracking for experience extraction.

Provides detailed tracking of experience extraction quality including keep rates,
coverage, association rates, and rejection reasons with PII-safe logging.
"""

import time
from typing import Dict, Any, List, Optional, Set
from collections import defaultdict, Counter
from dataclasses import dataclass, field
from datetime import datetime

from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG
from ..utils.pii import validate_no_pii_leakage

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


@dataclass
class ExperienceMetrics:
    """Container for experience extraction metrics."""
    
    # Core counters
    exp_candidates: int = 0
    exp_kept: int = 0
    exp_rejected: int = 0
    
    # Quality metrics
    exp_keep_rate: float = 0.0
    exp_coverage: float = 0.0
    exp_assoc_rate: float = 0.0
    
    # Pattern metrics
    pattern_diversity: float = 0.0
    pattern_counts: Dict[str, int] = field(default_factory=dict)
    
    # Rejection tracking
    rejection_reasons: Dict[str, int] = field(default_factory=dict)
    
    # Date validation
    date_issues: Dict[str, int] = field(default_factory=dict)
    date_swaps: int = 0
    
    # Organization classification
    org_types: Dict[str, int] = field(default_factory=dict)
    
    # Employment context
    employment_keyword_hits: int = 0
    context_window_matches: int = 0
    
    # Processing metadata
    processing_start: Optional[float] = None
    processing_end: Optional[float] = None
    total_lines_processed: int = 0


class ExperienceMetricsTracker:
    """Thread-safe tracker for experience extraction metrics."""
    
    def __init__(self):
        self.metrics = ExperienceMetrics()
        self.session_id = f"exp_metrics_{int(time.time())}"
        self.logger = get_safe_logger(f"{__name__}.Tracker", cfg=DEFAULT_PII_CONFIG)
        
        # PII-safe text samples for debugging (hashed)
        self._debug_samples: Dict[str, List[str]] = defaultdict(list)
        
        # Start processing timer
        self.metrics.processing_start = time.time()
    
    def start_processing(self, total_lines: int = 0):
        """Initialize processing metrics."""
        self.metrics.processing_start = time.time()
        self.metrics.total_lines_processed = total_lines
        self.logger.info(f"EXP_METRICS: processing started | session={self.session_id} | lines={total_lines}")
    
    def record_candidate(self, text: str, pattern_type: str = "unknown", context: Optional[Dict] = None):
        """Record a candidate experience for processing."""
        self.metrics.exp_candidates += 1
        
        # Track pattern type
        self.metrics.pattern_counts[pattern_type] = self.metrics.pattern_counts.get(pattern_type, 0) + 1
        
        # Store PII-safe debug sample
        if len(self._debug_samples[pattern_type]) < 3:  # Limit samples
            safe_text = validate_no_pii_leakage(text[:100], DEFAULT_PII_CONFIG.HASH_SALT)
            self._debug_samples[pattern_type].append(safe_text)
        
        self.logger.debug(f"EXP_CANDIDATE: pattern={pattern_type} candidates={self.metrics.exp_candidates}")
    
    def record_kept(self, confidence_score: float = 0.0, org_type: str = "unknown", 
                   has_employment_keywords: bool = False, date_info: Optional[Dict] = None):
        """Record a kept experience."""
        self.metrics.exp_kept += 1
        
        # Track organization type
        self.metrics.org_types[org_type] = self.metrics.org_types.get(org_type, 0) + 1
        
        # Track employment keyword presence
        if has_employment_keywords:
            self.metrics.employment_keyword_hits += 1
        
        # Track date information
        if date_info:
            if date_info.get('date_swap', False) or date_info.get('date_swapped', False):
                self.metrics.date_swaps += 1
            
            for issue in date_info.get('issues', []):
                self.metrics.date_issues[issue] = self.metrics.date_issues.get(issue, 0) + 1
        
        self.logger.debug(f"EXP_KEPT: kept={self.metrics.exp_kept} confidence={confidence_score:.2f} org_type={org_type}")
    
    def record_rejected(self, reason: str, confidence_score: float = 0.0, 
                       additional_reasons: List[str] = None):
        """Record a rejected experience candidate."""
        self.metrics.exp_rejected += 1
        
        # Track primary reason
        self.metrics.rejection_reasons[reason] = self.metrics.rejection_reasons.get(reason, 0) + 1
        
        # Track additional reasons
        if additional_reasons:
            for add_reason in additional_reasons:
                reason_key = f"{reason}+{add_reason}"
                self.metrics.rejection_reasons[reason_key] = self.metrics.rejection_reasons.get(reason_key, 0) + 1
        
        self.logger.debug(f"EXP_REJECTED: rejected={self.metrics.exp_rejected} reason={reason} confidence={confidence_score:.2f}")
    
    def record_context_match(self, window_size: int = 2):
        """Record successful context window match."""
        self.metrics.context_window_matches += 1
        self.logger.debug(f"EXP_CONTEXT: matches={self.metrics.context_window_matches} window={window_size}")
    
    def calculate_rates(self):
        """Calculate derived metrics rates."""
        total_recorded = self.metrics.exp_candidates
        observed_events = self.metrics.exp_kept + self.metrics.exp_rejected
        total = max(total_recorded, observed_events)
        self.metrics.exp_candidates = total
        
        if total > 0:
            self.metrics.exp_keep_rate = self.metrics.exp_kept / total
            
            # Coverage: percentage of lines that yielded experiences  
            if self.metrics.total_lines_processed > 0:
                self.metrics.exp_coverage = self.metrics.exp_kept / self.metrics.total_lines_processed
            
            # Association rate: percentage with employment keywords
            if self.metrics.exp_kept > 0:
                self.metrics.exp_assoc_rate = self.metrics.employment_keyword_hits / self.metrics.exp_kept
        
        # Pattern diversity: number of unique patterns / total patterns
        unique_patterns = len(self.metrics.pattern_counts)
        if unique_patterns > 0:
            total_patterns = sum(self.metrics.pattern_counts.values())
            self.metrics.pattern_diversity = unique_patterns / total_patterns if total_patterns > 0 else 0.0
        
        self.logger.debug(f"EXP_RATES: keep={self.metrics.exp_keep_rate:.3f} coverage={self.metrics.exp_coverage:.3f} assoc={self.metrics.exp_assoc_rate:.3f}")
    
    def finalize_processing(self):
        """Finalize processing and calculate final metrics."""
        self.metrics.processing_end = time.time()
        self.calculate_rates()
        
        processing_time = self.metrics.processing_end - (self.metrics.processing_start or self.metrics.processing_end)
        
        self.logger.info(f"EXP_METRICS: processing completed | "
                        f"session={self.session_id} | "
                        f"time={processing_time:.2f}s | "
                        f"candidates={self.metrics.exp_candidates} | "
                        f"kept={self.metrics.exp_kept} | "
                        f"rejected={self.metrics.exp_rejected}")
    
    def get_summary(self) -> Dict[str, Any]:
        """Get comprehensive metrics summary (PII-safe)."""
        self.calculate_rates()
        
        summary = {
            'session_id': self.session_id,
            'core_metrics': {
                'exp_candidates': self.metrics.exp_candidates,
                'exp_kept': self.metrics.exp_kept,
                'exp_rejected': self.metrics.exp_rejected,
                'exp_keep_rate': round(self.metrics.exp_keep_rate, 3),
                'exp_coverage': round(self.metrics.exp_coverage, 3),
                'exp_assoc_rate': round(self.metrics.exp_assoc_rate, 3)
            },
            'quality_metrics': {
                'pattern_diversity': round(self.metrics.pattern_diversity, 3),
                'employment_keyword_hits': self.metrics.employment_keyword_hits,
                'context_window_matches': self.metrics.context_window_matches,
                'date_swaps': self.metrics.date_swaps
            },
            'rejection_analysis': dict(self.metrics.rejection_reasons),
            'organization_types': dict(self.metrics.org_types),
            'date_issues': dict(self.metrics.date_issues),
            'pattern_distribution': dict(self.metrics.pattern_counts),
            'processing': {
                'total_lines': self.metrics.total_lines_processed,
                'processing_time': (self.metrics.processing_end - self.metrics.processing_start) 
                                  if self.metrics.processing_end and self.metrics.processing_start else 0.0
            }
        }
        
        return summary
    
    def log_summary(self, level: str = "INFO"):
        """Log comprehensive summary with appropriate level."""
        summary = self.get_summary()
        core = summary['core_metrics']
        quality = summary['quality_metrics']
        
        # Core metrics log
        self.logger.info(f"EXP_SUMMARY: candidates={core['exp_candidates']} "
                        f"kept={core['exp_kept']} "
                        f"rejected={core['exp_rejected']} "
                        f"keep_rate={core['exp_keep_rate']} "
                        f"coverage={core['exp_coverage']} "
                        f"assoc_rate={core['exp_assoc_rate']}")
        
        # Quality metrics
        if quality['pattern_diversity'] > 0:
            self.logger.info(f"EXP_QUALITY: pattern_diversity={quality['pattern_diversity']} "
                            f"employment_hits={quality['employment_keyword_hits']} "
                            f"context_matches={quality['context_window_matches']} "
                            f"date_swaps={quality['date_swaps']}")
        
        # Rejection reasons (top 5)
        if self.metrics.rejection_reasons:
            top_reasons = dict(Counter(self.metrics.rejection_reasons).most_common(5))
            self.logger.info(f"EXP_REJECT_REASONS: {top_reasons}")
        
        # Organization types if diverse
        if len(self.metrics.org_types) > 1:
            self.logger.info(f"EXP_ORG_TYPES: {dict(self.metrics.org_types)}")
        
        # Alerts for concerning patterns
        self._check_and_alert(core, quality)
    
    def _check_and_alert(self, core: Dict, quality: Dict):
        """Check metrics and generate alerts for concerning patterns."""
        
        # Low keep rate alert
        if core['exp_keep_rate'] < 0.20 and core['exp_candidates'] >= 5:
            self.logger.warning(f"EXP_ALERT: Low keep rate {core['exp_keep_rate']:.3f} < 0.20 "
                              f"with {core['exp_candidates']} candidates")
        
        # Zero coverage alert
        if core['exp_coverage'] == 0.0 and self.metrics.total_lines_processed > 0:
            self.logger.warning(f"EXP_ALERT: Zero coverage with {self.metrics.total_lines_processed} lines processed")
        
        # Low association rate alert  
        if core['exp_assoc_rate'] < 0.30 and core['exp_kept'] >= 3:
            self.logger.warning(f"EXP_ALERT: Low association rate {core['exp_assoc_rate']:.3f} < 0.30 "
                              f"(experiences without employment keywords)")
        
        # Pattern diversity alert
        if quality['pattern_diversity'] < 0.20 and core['exp_kept'] >= 3:
            self.logger.warning(f"EXP_ALERT: Low pattern diversity {quality['pattern_diversity']:.3f} "
                              f"(may indicate overfitting)")
        
        # High rejection rate with specific reasons
        if core['exp_rejected'] > core['exp_kept'] * 3:  # 3:1 rejection ratio
            top_reason = max(self.metrics.rejection_reasons.items(), key=lambda x: x[1], default=("unknown", 0))
            self.logger.warning(f"EXP_ALERT: High rejection rate {core['exp_rejected']}:{core['exp_kept']} "
                              f"top_reason={top_reason[0]}({top_reason[1]})")


# Global tracker instance for singleton pattern
_metrics_tracker = None

def get_experience_metrics_tracker() -> ExperienceMetricsTracker:
    """Get singleton experience metrics tracker."""
    global _metrics_tracker
    if _metrics_tracker is None:
        _metrics_tracker = ExperienceMetricsTracker()
    return _metrics_tracker


def reset_experience_metrics():
    """Reset metrics tracker (useful for testing)."""
    global _metrics_tracker
    _metrics_tracker = ExperienceMetricsTracker()


# Convenience functions for easy integration
def record_exp_candidate(text: str, pattern_type: str = "unknown", context: Optional[Dict] = None):
    """Record experience candidate."""
    get_experience_metrics_tracker().record_candidate(text, pattern_type, context)


def record_exp_kept(confidence_score: float = 0.0, org_type: str = "unknown", 
                   has_employment_keywords: bool = False, date_info: Optional[Dict] = None):
    """Record kept experience."""
    get_experience_metrics_tracker().record_kept(confidence_score, org_type, has_employment_keywords, date_info)


def record_exp_rejected(reason: str, confidence_score: float = 0.0, additional_reasons: List[str] = None):
    """Record rejected experience."""
    get_experience_metrics_tracker().record_rejected(reason, confidence_score, additional_reasons)


def get_experience_summary() -> Dict[str, Any]:
    """Get current experience metrics summary."""
    return get_experience_metrics_tracker().get_summary()


def log_experience_summary(level: str = "INFO"):
    """Log experience metrics summary."""
    get_experience_metrics_tracker().log_summary(level)
