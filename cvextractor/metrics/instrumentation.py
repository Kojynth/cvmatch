"""
Extraction Metrics Instrumentation
==================================

Comprehensive metrics collection and decision logging for CV extraction pipeline.
Provides per-run counters, structured decision logs, and audit trails.
"""

import json
import time
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Dict, List, Any, Optional, Union
from pathlib import Path
from collections import defaultdict, Counter
import logging

from ..utils.log_safety import mask_all


@dataclass
class ExtractionMetrics:
    """Comprehensive extraction metrics for audit and optimization."""

    # Core quality metrics (targets in comments)
    quality_score: float = 0.0  # target ≥ 0.75
    assoc_rate: float = 0.0  # target ≥ 0.70
    exp_coverage: float = 0.0  # target ≥ 0.25
    edu_keep_rate: float = 0.0  # target ≥ 0.20

    # Pattern analysis
    pattern_diversity: float = 0.0
    foreign_density: float = 0.0

    # Boundary analysis
    boundary_overlap_count_before: int = 0
    boundary_overlap_count_after: int = 0  # target = 0

    # Routing metrics
    reclass_to_cert: int = 0
    reclass_to_interests: int = 0
    reclass_to_education: int = 0
    reclass_to_projects: int = 0

    # Education deduplication
    edu_dedup_counts: Dict[str, int] = None
    edu_oscillation_detected: bool = False

    # Gate performance
    exp_gate_pass_rate: float = 0.0
    ai_gate_health_score: float = 0.0
    heuristic_fallback_triggered: bool = False

    # AI mode tracking
    extraction_mode: str = "unknown"  # AI_STRICT, HEURISTIC_ONLY, HYBRID, etc.

    # Processing statistics
    total_sections_found: int = 0
    total_items_extracted: int = 0
    total_processing_time_seconds: float = 0.0

    # Error tracking
    critical_errors: int = 0
    warnings_count: int = 0
    pii_leakage_detected: bool = False

    def __post_init__(self):
        if self.edu_dedup_counts is None:
            self.edu_dedup_counts = {}

    def meets_success_criteria(self) -> bool:
        """Check if metrics meet all success criteria."""
        return (
            self.quality_score >= 0.75
            and self.assoc_rate >= 0.70
            and self.exp_coverage >= 0.25
            and self.edu_keep_rate >= 0.20
            and self.boundary_overlap_count_after == 0
            and not self.pii_leakage_detected
        )

    def get_failure_reasons(self) -> List[str]:
        """Get list of specific criteria failures."""
        failures = []

        if self.quality_score < 0.75:
            failures.append(f"quality_score={self.quality_score:.3f} < 0.75")
        if self.assoc_rate < 0.70:
            failures.append(f"assoc_rate={self.assoc_rate:.3f} < 0.70")
        if self.exp_coverage < 0.25:
            failures.append(f"exp_coverage={self.exp_coverage:.3f} < 0.25")
        if self.edu_keep_rate < 0.20:
            failures.append(f"edu_keep_rate={self.edu_keep_rate:.3f} < 0.20")
        if self.boundary_overlap_count_after > 0:
            failures.append(
                f"boundary_overlap_count={self.boundary_overlap_count_after} > 0"
            )
        if self.pii_leakage_detected:
            failures.append("pii_leakage_detected=True")

        return failures


@dataclass
class DecisionLog:
    """Structured log entry for individual extraction decisions."""

    doc_id: str
    page: int
    block_id: str
    rule_id: str
    scores: Dict[str, float]
    thresholds: Dict[str, float]
    decision: str  # accepted, rejected, routed_to_X
    reason: str
    timestamp: str = None
    extraction_mode: str = "unknown"

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with PII masking."""
        return mask_all(asdict(self))


class MetricsCollector:
    """Centralized metrics collection and decision logging."""

    def __init__(self, doc_id: str, mask_pii: bool = True):
        self.doc_id = doc_id
        self.mask_pii = mask_pii
        self.metrics = ExtractionMetrics()
        self.decision_logs: List[DecisionLog] = []
        self.start_time = time.time()

        # Counters for specific tracking
        self.gate_decisions = Counter()
        self.routing_decisions = Counter()
        self.error_counts = Counter()

        # Logger for metrics
        self.logger = logging.getLogger(f"{__name__}.{doc_id}")

    def log_decision(
        self,
        page: int,
        block_id: str,
        rule_id: str,
        scores: Dict[str, float],
        thresholds: Dict[str, float],
        decision: str,
        reason: str,
        extraction_mode: str = "unknown",
    ):
        """Log a structured extraction decision."""
        log_entry = DecisionLog(
            doc_id=self.doc_id,
            page=page,
            block_id=block_id,
            rule_id=rule_id,
            scores=scores,
            thresholds=thresholds,
            decision=decision,
            reason=reason,
            extraction_mode=extraction_mode,
        )

        self.decision_logs.append(log_entry)

        # Update counters
        self.gate_decisions[decision] += 1

        # Log for immediate debugging
        if self.mask_pii:
            safe_log = log_entry.to_dict()
            self.logger.debug(f"DECISION: {safe_log}")
        else:
            self.logger.debug(f"DECISION: {asdict(log_entry)}")

    def log_routing_decision(
        self, from_section: str, to_section: str, reason: str, count: int = 1
    ):
        """Log section routing decisions."""
        self.routing_decisions[f"{from_section}→{to_section}"] += count

        # Update specific metrics
        if to_section == "certifications":
            self.metrics.reclass_to_cert += count
        elif to_section == "interests":
            self.metrics.reclass_to_interests += count
        elif to_section == "education":
            self.metrics.reclass_to_education += count
        elif to_section == "projects":
            self.metrics.reclass_to_projects += count

        self.logger.info(
            f"ROUTING: {from_section}→{to_section} | reason={reason} | count={count}"
        )

    def log_boundary_analysis(self, before_count: int, after_count: int):
        """Log boundary overlap analysis."""
        self.metrics.boundary_overlap_count_before = before_count
        self.metrics.boundary_overlap_count_after = after_count

        self.logger.info(
            f"BOUNDARIES: overlap_before={before_count} overlap_after={after_count}"
        )

    def log_education_dedup(self, phase: str, before_count: int, after_count: int):
        """Log education deduplication metrics."""
        self.metrics.edu_dedup_counts[phase] = {
            "before": before_count,
            "after": after_count,
            "removed": before_count - after_count,
        }

        # Check for oscillation
        if len(self.metrics.edu_dedup_counts) >= 3:
            counts = [
                phase_data["after"]
                for phase_data in self.metrics.edu_dedup_counts.values()
            ]
            if self._detect_oscillation(counts):
                self.metrics.edu_oscillation_detected = True
                self.logger.warning(
                    f"EDU_DEDUP: oscillation detected | counts={counts}"
                )

        self.logger.info(f"EDU_DEDUP: phase={phase} | {before_count}→{after_count}")

    def log_ai_gate_health(self, health_score: float, mode: str):
        """Log AI gate health and mode."""
        self.metrics.ai_gate_health_score = health_score
        self.metrics.extraction_mode = mode

        if mode == "HEURISTIC_ONLY":
            self.metrics.heuristic_fallback_triggered = True

        self.logger.info(f"AI_GATE: health={health_score:.3f} mode={mode}")

    def log_error(self, error_type: str, message: str, critical: bool = False):
        """Log errors and warnings."""
        self.error_counts[error_type] += 1

        if critical:
            self.metrics.critical_errors += 1
            self.logger.error(f"CRITICAL: {error_type} | {message}")
        else:
            self.metrics.warnings_count += 1
            self.logger.warning(f"WARNING: {error_type} | {message}")

    def check_pii_leakage(self, text_samples: List[str]):
        """Check for PII leakage in output."""
        from ..utils.log_safety import validate_no_pii_leakage

        for i, sample in enumerate(text_samples):
            if isinstance(sample, str):
                pii_found = validate_no_pii_leakage(sample)
                if pii_found:
                    self.metrics.pii_leakage_detected = True
                    self.log_error(
                        "pii_leakage",
                        f"Found PII types: {pii_found} in sample {i}",
                        critical=True,
                    )

    def calculate_final_metrics(
        self,
        total_sections: int,
        total_items: int,
        associations_found: int,
        associations_expected: int,
        experience_coverage: float,
        education_kept: int,
        education_total: int,
    ):
        """Calculate final quality metrics."""
        self.metrics.total_sections_found = total_sections
        self.metrics.total_items_extracted = total_items
        self.metrics.total_processing_time_seconds = time.time() - self.start_time

        # Calculate rates
        if associations_expected > 0:
            self.metrics.assoc_rate = associations_found / associations_expected
        else:
            self.metrics.assoc_rate = 0.0

        self.metrics.exp_coverage = experience_coverage

        if education_total > 0:
            self.metrics.edu_keep_rate = education_kept / education_total
        else:
            self.metrics.edu_keep_rate = 0.0

        # Calculate gate pass rate
        total_gate_decisions = sum(self.gate_decisions.values())
        if total_gate_decisions > 0:
            passed_decisions = self.gate_decisions.get("accepted", 0)
            self.metrics.exp_gate_pass_rate = passed_decisions / total_gate_decisions

        # Calculate overall quality score (weighted average)
        weights = {"assoc": 0.3, "coverage": 0.3, "edu": 0.2, "gate": 0.2}
        self.metrics.quality_score = (
            weights["assoc"] * self.metrics.assoc_rate
            + weights["coverage"] * self.metrics.exp_coverage
            + weights["edu"] * self.metrics.edu_keep_rate
            + weights["gate"] * self.metrics.exp_gate_pass_rate
        )

        self.logger.info(f"FINAL_METRICS: {asdict(self.metrics)}")

    def _detect_oscillation(self, counts: List[int], window: int = 3) -> bool:
        """Detect oscillation in count sequences."""
        if len(counts) < window:
            return False

        # Check for alternating pattern in last 'window' counts
        recent = counts[-window:]
        return len(set(recent)) <= 2 and recent[0] != recent[-1]

    def export_metrics(self, output_path: Optional[Path] = None) -> Dict[str, Any]:
        """Export all metrics and decision logs."""
        export_data = {
            "doc_id": self.doc_id,
            "metrics": asdict(self.metrics),
            "decision_logs": [log.to_dict() for log in self.decision_logs],
            "gate_decisions": dict(self.gate_decisions),
            "routing_decisions": dict(self.routing_decisions),
            "error_counts": dict(self.error_counts),
            "export_timestamp": datetime.now().isoformat(),
            "success_criteria_met": self.metrics.meets_success_criteria(),
            "failure_reasons": self.metrics.get_failure_reasons(),
        }

        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)

        return export_data

    def get_summary_report(self) -> str:
        """Generate human-readable summary report."""
        report_lines = [
            f"=== Extraction Metrics Report for {self.doc_id} ===",
            f"Quality Score: {self.metrics.quality_score:.3f} (target ≥ 0.75)",
            f"Association Rate: {self.metrics.assoc_rate:.3f} (target ≥ 0.70)",
            f"Experience Coverage: {self.metrics.exp_coverage:.3f} (target ≥ 0.25)",
            f"Education Keep Rate: {self.metrics.edu_keep_rate:.3f} (target ≥ 0.20)",
            f"Boundary Overlaps: {self.metrics.boundary_overlap_count_after} (target = 0)",
            f"",
            f"Extraction Mode: {self.metrics.extraction_mode}",
            f"AI Gate Health: {self.metrics.ai_gate_health_score:.3f}",
            f"Heuristic Fallback: {self.metrics.heuristic_fallback_triggered}",
            f"",
            f"Processing: {self.metrics.total_processing_time_seconds:.2f}s, "
            f"{self.metrics.total_sections_found} sections, {self.metrics.total_items_extracted} items",
            f"Errors: {self.metrics.critical_errors} critical, {self.metrics.warnings_count} warnings",
            f"PII Leakage: {self.metrics.pii_leakage_detected}",
            f"",
            f"Success Criteria: {'✅ PASSED' if self.metrics.meets_success_criteria() else '❌ FAILED'}",
        ]

        if not self.metrics.meets_success_criteria():
            report_lines.extend(
                [
                    f"Failure Reasons:",
                    *[f"  - {reason}" for reason in self.metrics.get_failure_reasons()],
                ]
            )

        return "\n".join(report_lines)


# Global registry for active collectors
_active_collectors: Dict[str, MetricsCollector] = {}


def get_metrics_collector(doc_id: str, mask_pii: bool = True) -> MetricsCollector:
    """Get or create metrics collector for document."""
    if doc_id not in _active_collectors:
        _active_collectors[doc_id] = MetricsCollector(doc_id, mask_pii)
    return _active_collectors[doc_id]


def finalize_metrics_collector(doc_id: str) -> Optional[Dict[str, Any]]:
    """Finalize and remove metrics collector, returning final export."""
    if doc_id in _active_collectors:
        collector = _active_collectors.pop(doc_id)
        return collector.export_metrics()
    return None


# Export main classes and functions
__all__ = [
    "ExtractionMetrics",
    "DecisionLog",
    "MetricsCollector",
    "get_metrics_collector",
    "finalize_metrics_collector",
]
