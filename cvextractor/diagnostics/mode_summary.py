"""
Mode Summary Reporting System
============================

Provides comprehensive status reporting for AI extraction operations,
including mode decisions, model availability, and extraction metrics.
This gives operators clear visibility into system behavior and helps
with troubleshooting.
"""

import json
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Any, Optional, Set
from pathlib import Path

from ..core.mode import AIMode, ModeContext, ModeReason
from ..logging.pii_filters import redact


@dataclass
class SectionMetrics:
    """Metrics for a specific CV section extraction."""

    section_name: str
    items_found: int = 0
    items_kept: int = 0
    keep_rate: float = 0.0
    ai_gate_passed: int = 0
    ai_gate_total: int = 0
    gate_pass_rate: float = 0.0
    rescue_applied: bool = False
    rescue_improved: bool = False
    processing_time_ms: float = 0.0
    errors: List[str] = field(default_factory=list)


@dataclass
class ExtractionMetrics:
    """Overall extraction metrics."""

    total_processing_time_ms: float = 0.0
    total_lines_processed: int = 0
    total_sections_detected: int = 0
    total_fields_extracted: int = 0
    high_confidence_fields: int = 0
    completion_rate: float = 0.0

    # Model-specific metrics
    models_loaded: int = 0
    total_model_load_time_ms: float = 0.0
    total_model_memory_mb: float = 0.0

    # Section-level metrics
    sections: Dict[str, SectionMetrics] = field(default_factory=dict)


@dataclass
class ModeSummary:
    """
    Complete summary of AI mode operation and extraction results.

    This provides a comprehensive view of:
    - AI path usage and mode decisions
    - Model availability and loading status
    - Section-by-section extraction metrics
    - Error conditions and recovery actions
    """

    # Session identification
    session_id: str
    timestamp: str
    document_id: str = "unknown"

    # AI Mode information
    ai_path_used: bool = False
    mode: str = AIMode.RULES_ONLY.value
    reasons: List[str] = field(default_factory=list)

    # Model status
    models_required: int = 0
    models_available: int = 0
    models_loaded: int = 0
    models_failed: List[str] = field(default_factory=list)

    # Feature availability
    features_available: Dict[str, bool] = field(default_factory=dict)
    features_degraded: Set[str] = field(default_factory=set)

    # Extraction metrics
    metrics: ExtractionMetrics = field(default_factory=lambda: ExtractionMetrics())

    # Warnings and errors
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        # Convert to dict and handle special types
        result = asdict(self)

        # Convert set to list for JSON serialization
        result["features_degraded"] = list(self.features_degraded)

        return result

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def to_human_readable(self) -> str:
        """Convert to human-readable string format."""
        lines = []

        # Header
        lines.append("=" * 60)
        lines.append("AI EXTRACTION MODE SUMMARY")
        lines.append("=" * 60)

        # Basic info
        lines.append(f"Session ID: {self.session_id}")
        lines.append(f"Timestamp: {self.timestamp}")
        lines.append(f"Document: {redact(self.document_id)}")
        lines.append("")

        # AI Mode status
        lines.append("AI MODE STATUS:")
        lines.append(f"  AI Path Used: {'YES' if self.ai_path_used else 'NO'}")
        lines.append(f"  Operation Mode: {self.mode}")

        if self.reasons:
            lines.append("  Reasons:")
            for reason in self.reasons:
                lines.append(f"    - {reason}")
        lines.append("")

        # Model status
        lines.append("MODEL STATUS:")
        lines.append(f"  Required: {self.models_required}")
        lines.append(f"  Available: {self.models_available}")
        lines.append(f"  Loaded: {self.models_loaded}")

        if self.models_failed:
            lines.append("  Failed models:")
            for model in self.models_failed:
                lines.append(f"    - {model}")
        lines.append("")

        # Feature status
        lines.append("FEATURE STATUS:")
        available_features = [
            f for f, available in self.features_available.items() if available
        ]
        degraded_features = list(self.features_degraded)

        lines.append(f"  Available: {len(available_features)}")
        for feature in available_features:
            lines.append(f"    - {feature}")

        if degraded_features:
            lines.append(f"  Degraded: {len(degraded_features)}")
            for feature in degraded_features:
                lines.append(f"    - {feature}")
        lines.append("")

        # Extraction metrics
        lines.append("EXTRACTION METRICS:")
        lines.append(
            f"  Processing Time: {self.metrics.total_processing_time_ms:.1f}ms"
        )
        lines.append(f"  Lines Processed: {self.metrics.total_lines_processed}")
        lines.append(f"  Sections Detected: {self.metrics.total_sections_detected}")
        lines.append(f"  Fields Extracted: {self.metrics.total_fields_extracted}")
        lines.append(f"  High Confidence: {self.metrics.high_confidence_fields}")
        lines.append(f"  Completion Rate: {self.metrics.completion_rate:.1%}")
        lines.append("")

        # Section details
        if self.metrics.sections:
            lines.append("SECTION DETAILS:")
            for section_name, section_metrics in self.metrics.sections.items():
                lines.append(f"  {section_name.upper()}:")
                lines.append(
                    f"    Items: {section_metrics.items_kept}/{section_metrics.items_found}"
                )
                lines.append(f"    Keep Rate: {section_metrics.keep_rate:.1%}")
                if section_metrics.ai_gate_total > 0:
                    lines.append(
                        f"    Gate Pass Rate: {section_metrics.gate_pass_rate:.1%}"
                    )
                if section_metrics.rescue_applied:
                    rescue_status = (
                        "improved"
                        if section_metrics.rescue_improved
                        else "no improvement"
                    )
                    lines.append(f"    Rescue Applied: {rescue_status}")
                if section_metrics.errors:
                    lines.append(f"    Errors: {len(section_metrics.errors)}")
            lines.append("")

        # Warnings and errors
        if self.warnings:
            lines.append("WARNINGS:")
            for warning in self.warnings:
                lines.append(f"  - {redact(warning)}")
            lines.append("")

        if self.errors:
            lines.append("ERRORS:")
            for error in self.errors:
                lines.append(f"  - {redact(error)}")
            lines.append("")

        lines.append("=" * 60)

        return "\n".join(lines)


class ModeSummaryReporter:
    """
    Central reporter for mode summaries and extraction metrics.

    Collects metrics throughout the extraction process and generates
    comprehensive summaries for operators and debugging.
    """

    def __init__(self, session_id: Optional[str] = None):
        """
        Initialize mode summary reporter.

        Args:
            session_id: Optional session identifier
        """
        self.session_id = session_id or self._generate_session_id()
        self.start_time = time.time()

        # Current summary being built
        self._current_summary: Optional[ModeSummary] = None

        # Metrics collection
        self._section_metrics: Dict[str, SectionMetrics] = {}
        self._warnings: List[str] = []
        self._errors: List[str] = []

    def start_extraction(self, document_id: str, mode_context: ModeContext) -> None:
        """
        Start a new extraction session.

        Args:
            document_id: Identifier for the document being processed
            mode_context: Current AI mode context
        """
        self._current_summary = ModeSummary(
            session_id=self.session_id,
            timestamp=datetime.now().isoformat(),
            document_id=document_id,
            ai_path_used=(mode_context.mode != AIMode.RULES_ONLY),
            mode=mode_context.mode.value,
            reasons=[r.value for r in mode_context.reasons],
            models_required=mode_context.total_models_required,
            models_available=mode_context.total_models_available,
            features_available=mode_context.features_available.copy(),
            features_degraded=mode_context.features_degraded.copy(),
        )

    def record_section_metrics(
        self, section_name: str, metrics: SectionMetrics
    ) -> None:
        """Record metrics for a specific section."""
        self._section_metrics[section_name] = metrics

    def record_warning(self, warning: str) -> None:
        """Record a warning message."""
        self._warnings.append(warning)

    def record_error(self, error: str) -> None:
        """Record an error message."""
        self._errors.append(error)

    def record_model_load(
        self,
        model_id: str,
        success: bool,
        load_time_ms: float = 0.0,
        memory_mb: float = 0.0,
    ) -> None:
        """Record model loading result."""
        if not self._current_summary:
            return

        if success:
            self._current_summary.models_loaded += 1
            self._current_summary.metrics.models_loaded += 1
            self._current_summary.metrics.total_model_load_time_ms += load_time_ms
            self._current_summary.metrics.total_model_memory_mb += memory_mb
        else:
            self._current_summary.models_failed.append(model_id)

    def finalize_extraction(
        self,
        total_lines: int = 0,
        total_sections: int = 0,
        total_fields: int = 0,
        high_confidence_fields: int = 0,
    ) -> ModeSummary:
        """
        Finalize extraction and generate complete summary.

        Args:
            total_lines: Total lines processed
            total_sections: Total sections detected
            total_fields: Total fields extracted
            high_confidence_fields: Number of high-confidence fields

        Returns:
            ModeSummary: Complete extraction summary
        """
        if not self._current_summary:
            raise RuntimeError("No active extraction session")

        # Calculate total processing time
        total_time_ms = (time.time() - self.start_time) * 1000

        # Update extraction metrics
        self._current_summary.metrics.total_processing_time_ms = total_time_ms
        self._current_summary.metrics.total_lines_processed = total_lines
        self._current_summary.metrics.total_sections_detected = total_sections
        self._current_summary.metrics.total_fields_extracted = total_fields
        self._current_summary.metrics.high_confidence_fields = high_confidence_fields

        # Calculate completion rate
        if total_fields > 0:
            self._current_summary.metrics.completion_rate = min(
                1.0, total_fields / 20.0
            )  # Assume 20 total possible fields

        # Add section metrics
        self._current_summary.metrics.sections = self._section_metrics.copy()

        # Add warnings and errors
        self._current_summary.warnings = self._warnings.copy()
        self._current_summary.errors = self._errors.copy()

        return self._current_summary

    def get_current_summary(self) -> Optional[ModeSummary]:
        """Get current summary (may be incomplete)."""
        return self._current_summary

    def _generate_session_id(self) -> str:
        """Generate unique session ID."""
        import uuid

        return f"cvmatch_{int(time.time())}_{str(uuid.uuid4())[:8]}"


class ModeSummaryManager:
    """
    Manager for mode summaries with persistence and reporting capabilities.

    Handles:
    - Summary generation and formatting
    - Persistence to files
    - Historical tracking
    - Operator notifications
    """

    def __init__(
        self,
        output_dir: Optional[Path] = None,
        enable_file_output: bool = True,
        enable_console_output: bool = True,
    ):
        """
        Initialize mode summary manager.

        Args:
            output_dir: Directory for summary output files
            enable_file_output: Whether to write summaries to files
            enable_console_output: Whether to print summaries to console
        """
        self.output_dir = output_dir or Path("logs/mode_summaries")
        self.enable_file_output = enable_file_output
        self.enable_console_output = enable_console_output

        # Ensure output directory exists
        if self.enable_file_output:
            self.output_dir.mkdir(parents=True, exist_ok=True)

        # Summary history
        self._summary_history: List[ModeSummary] = []

    def report_summary(self, summary: ModeSummary, show_details: bool = True) -> None:
        """
        Report a mode summary using configured outputs.

        Args:
            summary: Mode summary to report
            show_details: Whether to show detailed metrics
        """
        # Add to history
        self._summary_history.append(summary)

        # Console output
        if self.enable_console_output:
            print("\n" + summary.to_human_readable())

        # File output
        if self.enable_file_output:
            self._write_summary_to_file(summary)

    def _write_summary_to_file(self, summary: ModeSummary) -> None:
        """Write summary to JSON and text files."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_short = summary.session_id.split("_")[-1]  # Last part of session ID

        # JSON output
        json_file = self.output_dir / f"summary_{timestamp}_{session_short}.json"
        with open(json_file, "w", encoding="utf-8") as f:
            f.write(summary.to_json())

        # Human-readable output
        txt_file = self.output_dir / f"summary_{timestamp}_{session_short}.txt"
        with open(txt_file, "w", encoding="utf-8") as f:
            f.write(summary.to_human_readable())

    def get_summary_history(self, limit: Optional[int] = None) -> List[ModeSummary]:
        """Get summary history, optionally limited to recent entries."""
        if limit:
            return self._summary_history[-limit:]
        return self._summary_history.copy()

    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics across all summaries."""
        if not self._summary_history:
            return {}

        total_summaries = len(self._summary_history)
        ai_path_used = sum(1 for s in self._summary_history if s.ai_path_used)

        # Mode distribution
        mode_counts = {}
        for summary in self._summary_history:
            mode_counts[summary.mode] = mode_counts.get(summary.mode, 0) + 1

        # Average metrics
        avg_processing_time = (
            sum(s.metrics.total_processing_time_ms for s in self._summary_history)
            / total_summaries
        )
        avg_fields_extracted = (
            sum(s.metrics.total_fields_extracted for s in self._summary_history)
            / total_summaries
        )

        return {
            "total_extractions": total_summaries,
            "ai_path_usage_rate": (
                ai_path_used / total_summaries if total_summaries > 0 else 0
            ),
            "mode_distribution": mode_counts,
            "average_processing_time_ms": avg_processing_time,
            "average_fields_extracted": avg_fields_extracted,
        }


# Global manager instance
_global_manager: Optional[ModeSummaryManager] = None


def get_mode_summary_manager() -> ModeSummaryManager:
    """Get global mode summary manager."""
    global _global_manager

    if _global_manager is None:
        _global_manager = ModeSummaryManager()

    return _global_manager


def create_mode_summary_reporter(
    session_id: Optional[str] = None,
) -> ModeSummaryReporter:
    """Create a new mode summary reporter."""
    return ModeSummaryReporter(session_id)


# Export main classes
__all__ = [
    "SectionMetrics",
    "ExtractionMetrics",
    "ModeSummary",
    "ModeSummaryReporter",
    "ModeSummaryManager",
    "get_mode_summary_manager",
    "create_mode_summary_reporter",
]
