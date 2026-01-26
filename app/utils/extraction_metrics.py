"""
Extraction Metrics Collection System

Provides comprehensive metrics collection for the enhanced extraction pipeline
to monitor performance, quality, and reliability.
"""

import time
import json
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


@dataclass
class ComponentMetrics:
    """Metrics for individual extraction components."""
    component_name: str
    processing_time_ms: float
    items_processed: int
    items_extracted: int
    success_rate: float
    confidence_average: float
    errors_count: int = 0
    warnings_count: int = 0


@dataclass
class ContactProtectionMetrics:
    """Metrics specific to contact/header line protection."""
    # Contact/Header Protection Metrics
    header_lines_blocked_in_exp: int = 0
    header_lines_blocked_in_edu: int = 0
    contact_lines_blocked_in_exp: int = 0
    contact_lines_blocked_in_edu: int = 0
    
    # Role @ Company Fallback Metrics
    email_like_company_rejected: int = 0
    domain_like_company_rejected: int = 0
    fallback_title_at_company_rejected: int = 0
    spaced_at_pattern_enforced: int = 0
    
    # Quality Control Metrics
    single_word_title_rejected: int = 0
    lowercase_title_rejected: int = 0
    no_supporting_signals_rejected: int = 0
    
    # Deduplication Metrics
    duplicate_candidates_dropped: int = 0
    duplicate_keys_seen: int = 0
    
    # Demotion Control Metrics
    demotions_blocked_domain_like: int = 0
    demotions_allowed_to_education: int = 0
    
    def get_blocked_operations_count(self) -> int:
        """Get total count of blocked operations (should be 0 under normal conditions)."""
        return (
            self.header_lines_blocked_in_exp +
            self.header_lines_blocked_in_edu +
            self.contact_lines_blocked_in_exp +
            self.contact_lines_blocked_in_edu +
            self.email_like_company_rejected +
            self.domain_like_company_rejected +
            self.fallback_title_at_company_rejected +
            self.demotions_blocked_domain_like
        )


@dataclass
class ExtractionSessionMetrics:
    """Metrics for a complete extraction session."""
    session_id: str
    timestamp: str
    document_type: str
    document_size_chars: int
    total_processing_time_ms: float
    
    # Component metrics
    component_metrics: List[ComponentMetrics]
    
    # Overall results
    total_items_extracted: int
    sections_processed: int
    pattern_diversity_score: float
    boundary_violations: int
    qa_interventions: int
    
    # Quality metrics
    average_confidence: float
    low_confidence_items: int
    empty_sections: int
    
    # Contact protection metrics
    contact_protection: ContactProtectionMetrics
    
    # Performance flags
    used_enhanced_pipeline: bool = False
    fallback_triggered: bool = False
    errors_encountered: int = 0


class ExtractionMetricsCollector:
    """Collects and manages extraction metrics."""
    
    def __init__(self, session_id: str = None):
        self.session_id = session_id or f"session_{int(time.time())}"
        self.start_time = time.time()
        self.component_metrics: List[ComponentMetrics] = []
        self.session_metrics: Optional[ExtractionSessionMetrics] = None
        self.contact_protection = ContactProtectionMetrics()
        self.logger = get_safe_logger(f"{__name__}.{self.session_id}", cfg=DEFAULT_PII_CONFIG)
        
    def start_component_timing(self, component_name: str) -> str:
        """Start timing a component operation."""
        timing_id = f"{component_name}_{int(time.time() * 1000)}"
        self._component_timings = getattr(self, '_component_timings', {})
        self._component_timings[timing_id] = {
            'component_name': component_name,
            'start_time': time.time()
        }
        return timing_id
    
    def end_component_timing(self, timing_id: str, items_processed: int = 0, 
                           items_extracted: int = 0, confidence_scores: List[float] = None) -> ComponentMetrics:
        """End timing a component and record metrics."""
        if not hasattr(self, '_component_timings') or timing_id not in self._component_timings:
            self.logger.warning(f"METRICS: timing_id not found | timing_id={timing_id}")
            return None
            
        timing_info = self._component_timings.pop(timing_id)
        processing_time = (time.time() - timing_info['start_time']) * 1000  # Convert to ms
        
        confidence_scores = confidence_scores or []
        confidence_avg = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.0
        success_rate = items_extracted / items_processed if items_processed > 0 else 0.0
        
        metrics = ComponentMetrics(
            component_name=timing_info['component_name'],
            processing_time_ms=processing_time,
            items_processed=items_processed,
            items_extracted=items_extracted,
            success_rate=success_rate,
            confidence_average=confidence_avg
        )
        
        self.component_metrics.append(metrics)
        self.logger.info(f"COMPONENT_METRICS: {timing_info['component_name']} | "
                        f"time={processing_time:.1f}ms extracted={items_extracted}/{items_processed} "
                        f"success_rate={success_rate:.3f}")
        
        return metrics
    
    def record_session_metrics(self, document_type: str, document_size: int,
                             total_items: int, sections_count: int,
                             pattern_diversity: float, boundary_violations: int = 0,
                             qa_interventions: int = 0, average_confidence: float = 0.0,
                             low_confidence_items: int = 0, empty_sections: int = 0,
                             used_enhanced_pipeline: bool = False, fallback_triggered: bool = False,
                             errors_count: int = 0) -> ExtractionSessionMetrics:
        """Record overall session metrics."""
        
        total_time = (time.time() - self.start_time) * 1000  # Convert to ms
        
        self.session_metrics = ExtractionSessionMetrics(
            session_id=self.session_id,
            timestamp=datetime.now().isoformat(),
            document_type=document_type,
            document_size_chars=document_size,
            total_processing_time_ms=total_time,
            component_metrics=self.component_metrics,
            total_items_extracted=total_items,
            sections_processed=sections_count,
            pattern_diversity_score=pattern_diversity,
            boundary_violations=boundary_violations,
            qa_interventions=qa_interventions,
            average_confidence=average_confidence,
            low_confidence_items=low_confidence_items,
            empty_sections=empty_sections,
            contact_protection=self.contact_protection,
            used_enhanced_pipeline=used_enhanced_pipeline,
            fallback_triggered=fallback_triggered,
            errors_encountered=errors_count
        )
        
        self.logger.info(f"SESSION_METRICS: {self.session_id} | "
                        f"time={total_time:.1f}ms items={total_items} "
                        f"diversity={pattern_diversity:.3f} enhanced={used_enhanced_pipeline}")
        
        return self.session_metrics
    
    def export_metrics(self, output_path: str = None) -> Dict[str, Any]:
        """Export metrics to JSON format."""
        if not self.session_metrics:
            self.logger.warning("METRICS_EXPORT: no session metrics recorded")
            return {}
        
        metrics_dict = asdict(self.session_metrics)
        
        if output_path:
            try:
                output_file = Path(output_path)
                output_file.parent.mkdir(parents=True, exist_ok=True)
                
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(metrics_dict, f, indent=2, ensure_ascii=False)
                
                self.logger.info(f"METRICS_EXPORT: exported to {output_path}")
            except Exception as e:
                self.logger.error(f"METRICS_EXPORT: failed to export | error={e}")
        
        return metrics_dict
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get a performance summary for the session."""
        if not self.session_metrics:
            return {"error": "No metrics recorded"}
        
        component_summary = {}
        for comp in self.component_metrics:
            component_summary[comp.component_name] = {
                "processing_time_ms": comp.processing_time_ms,
                "success_rate": comp.success_rate,
                "items_extracted": comp.items_extracted,
                "confidence_avg": comp.confidence_average
            }
        
        return {
            "session_id": self.session_metrics.session_id,
            "total_time_ms": self.session_metrics.total_processing_time_ms,
            "total_items": self.session_metrics.total_items_extracted,
            "pattern_diversity": self.session_metrics.pattern_diversity_score,
            "used_enhanced_pipeline": self.session_metrics.used_enhanced_pipeline,
            "fallback_triggered": self.session_metrics.fallback_triggered,
            "blocked_operations": self.contact_protection.get_blocked_operations_count(),
            "component_performance": component_summary
        }
    
    # Contact/Header Protection Metrics Methods
    def block_header_line_in_exp(self, line_idx: int, reason: str = ""):
        """Record header line blocked from experience extraction."""
        self.contact_protection.header_lines_blocked_in_exp += 1
        self.logger.debug(f"METRICS: header_blocked_exp | line={line_idx} reason='{reason}'")
    
    def block_contact_line_in_exp(self, line_idx: int, contact_type: str = ""):
        """Record contact line blocked from experience extraction."""
        self.contact_protection.contact_lines_blocked_in_exp += 1
        self.logger.debug(f"METRICS: contact_blocked_exp | line={line_idx} type='{contact_type}'")
    
    def block_header_line_in_edu(self, line_idx: int, reason: str = ""):
        """Record header line blocked from education extraction."""
        self.contact_protection.header_lines_blocked_in_edu += 1
        self.logger.debug(f"METRICS: header_blocked_edu | line={line_idx} reason='{reason}'")
    
    def block_contact_line_in_edu(self, line_idx: int, contact_type: str = ""):
        """Record contact line blocked from education extraction."""
        self.contact_protection.contact_lines_blocked_in_edu += 1
        self.logger.debug(f"METRICS: contact_blocked_edu | line={line_idx} type='{contact_type}'")
    
    # Role @ Company Fallback Metrics
    def reject_email_like_company(self, company: str, reason: str = ""):
        """Record rejection of email-like company."""
        self.contact_protection.email_like_company_rejected += 1
        self.logger.debug(f"METRICS: email_company_rejected | company='[REDACTED]' reason='{reason}'")
    
    def reject_domain_like_company(self, company: str, reason: str = ""):
        """Record rejection of domain-like company."""
        self.contact_protection.domain_like_company_rejected += 1
        self.logger.debug(f"METRICS: domain_company_rejected | company='[REDACTED]' reason='{reason}'")
    
    def reject_fallback_title_company(self, title: str, company: str, reason: str = ""):
        """Record rejection of title@company fallback."""
        self.contact_protection.fallback_title_at_company_rejected += 1
        self.logger.debug(f"METRICS: fallback_rejected | title='[REDACTED]' company='[REDACTED]' reason='{reason}'")
    
    def enforce_spaced_at_pattern(self, original_pattern: str):
        """Record enforcement of spaced @ pattern."""
        self.contact_protection.spaced_at_pattern_enforced += 1
        self.logger.debug(f"METRICS: spaced_at_enforced | original='{original_pattern}'")
    
    # Quality Control Metrics
    def reject_single_word_title(self, title: str):
        """Record rejection of single-word title."""
        self.contact_protection.single_word_title_rejected += 1
        self.logger.debug(f"METRICS: single_word_title_rejected | title='[REDACTED]'")
    
    def reject_lowercase_title(self, title: str):
        """Record rejection of all-lowercase title."""
        self.contact_protection.lowercase_title_rejected += 1
        self.logger.debug(f"METRICS: lowercase_title_rejected | title='[REDACTED]'")
    
    def reject_no_supporting_signals(self, title: str, company: str):
        """Record rejection due to lack of supporting signals."""
        self.contact_protection.no_supporting_signals_rejected += 1
        self.logger.debug(f"METRICS: no_signals_rejected | title='[REDACTED]' company='[REDACTED]'")
    
    # Deduplication Metrics
    def drop_duplicate_candidate(self, key_hash: str, reason: str = ""):
        """Record dropping of duplicate candidate."""
        self.contact_protection.duplicate_candidates_dropped += 1
        self.logger.debug(f"METRICS: duplicate_dropped | hash='{key_hash[:8]}...' reason='{reason}'")
    
    def record_duplicate_key(self, key_hash: str):
        """Record seeing a duplicate key."""
        self.contact_protection.duplicate_keys_seen += 1
        self.logger.debug(f"METRICS: duplicate_key_seen | hash='{key_hash[:8]}...'")
    
    # Demotion Control Metrics
    def block_demotion_domain_like(self, company: str, reason: str = ""):
        """Record blocked demotion due to domain-like company."""
        self.contact_protection.demotions_blocked_domain_like += 1
        self.logger.debug(f"METRICS: demotion_blocked | company='[REDACTED]' reason='{reason}'")
    
    def allow_demotion_to_education(self, title: str, reason: str = ""):
        """Record allowed demotion to education."""
        self.contact_protection.demotions_allowed_to_education += 1
        self.logger.debug(f"METRICS: demotion_allowed | title='[REDACTED]' reason='{reason}'")
    
    def log_contact_protection_summary(self):
        """Log summary of contact protection metrics."""
        blocked_ops = self.contact_protection.get_blocked_operations_count()
        
        if blocked_ops > 0:
            self.logger.warning(f"CONTACT_PROTECTION_ALERT: blocked_operations={blocked_ops} "
                              f"| This indicates potential contact/header misclassification issues")
        else:
            self.logger.info("CONTACT_PROTECTION_HEALTHY: zero_blocked_operations (normal state)")
    
    def get_contact_protection_health(self) -> Dict[str, Any]:
        """Get health status for contact protection system."""
        blocked_ops = self.contact_protection.get_blocked_operations_count()
        
        return {
            'status': 'healthy' if blocked_ops == 0 else 'issues_detected',
            'blocked_operations': blocked_ops,
            'header_blocks': (self.contact_protection.header_lines_blocked_in_exp + 
                            self.contact_protection.header_lines_blocked_in_edu),
            'contact_blocks': (self.contact_protection.contact_lines_blocked_in_exp +
                             self.contact_protection.contact_lines_blocked_in_edu),
            'company_rejections': (self.contact_protection.email_like_company_rejected +
                                 self.contact_protection.domain_like_company_rejected),
            'fallback_rejections': self.contact_protection.fallback_title_at_company_rejected,
            'duplicate_drops': self.contact_protection.duplicate_candidates_dropped
        }


# Global metrics collector instance
_global_collector: Optional[ExtractionMetricsCollector] = None


def get_metrics_collector(session_id: str = None) -> ExtractionMetricsCollector:
    """Get or create a metrics collector instance."""
    global _global_collector
    
    if _global_collector is None or (session_id and _global_collector.session_id != session_id):
        _global_collector = ExtractionMetricsCollector(session_id)
    
    return _global_collector


def reset_metrics_collector():
    """Reset the global metrics collector."""
    global _global_collector
    _global_collector = None