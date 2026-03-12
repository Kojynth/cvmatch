"""
Pipeline Diagnostics Module

Centralized logging and diagnostics for the CV generation pipeline.
Extracted from llm_worker.py for better maintainability.

Key features:
- Structured stage progress logging
- Performance timing utilities
- Error classification and reporting
- Debug output helpers
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    from ..logging.safe_logger import get_safe_logger
    from ..config import DEFAULT_PII_CONFIG
    logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


@dataclass
class StageResult:
    """Result of a pipeline stage execution."""

    stage_name: str
    success: bool
    duration_seconds: float = 0.0
    attempt: int = 1
    max_attempts: int = 1
    output: Any = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/serialization."""
        return {
            "stage": self.stage_name,
            "success": self.success,
            "duration_seconds": round(self.duration_seconds, 3),
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
            "error": self.error,
            "error_type": self.error_type,
            "metadata": self.metadata,
        }


@dataclass
class PipelineTimings:
    """Timing information for pipeline execution."""

    total_seconds: float = 0.0
    stage_timings: Dict[str, float] = field(default_factory=dict)
    stage_attempts: Dict[str, int] = field(default_factory=dict)

    def record_stage(
        self,
        stage_name: str,
        duration_seconds: float,
        attempt: int = 1,
    ) -> None:
        """Record timing for a stage."""
        self.stage_timings[stage_name] = duration_seconds
        self.stage_attempts[stage_name] = attempt
        self.total_seconds = sum(self.stage_timings.values())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            "total_seconds": round(self.total_seconds, 3),
            "stages": {
                name: {
                    "duration_seconds": round(self.stage_timings[name], 3),
                    "attempts": self.stage_attempts.get(name, 1),
                }
                for name in self.stage_timings
            },
        }


class StageTimer:
    """Context manager for timing stage execution."""

    def __init__(self, stage_name: str):
        self.stage_name = stage_name
        self.start_time: float = 0.0
        self.duration_seconds: float = 0.0

    def __enter__(self) -> "StageTimer":
        self.start_time = time.time()
        return self

    def __exit__(self, *args) -> None:
        self.duration_seconds = time.time() - self.start_time

    @property
    def elapsed(self) -> float:
        """Get elapsed time since start."""
        return time.time() - self.start_time


def classify_error(error_message: str) -> Tuple[str, str]:
    """Classify an error message into category and type.

    Args:
        error_message: Error message string

    Returns:
        Tuple of (error_category, error_type)
        Categories: "memory", "timeout", "parse", "network", "unknown"
    """
    lowered = str(error_message or "").lower()

    # Memory-related errors
    memory_markers = (
        "out of memory",
        "cuda out of memory",
        "cpu-only device map",
        "hybrid-only policy",
        "insufficient for mixed placement",
        "oom",
        "memory error",
        "memoryerror",
        "vram",
        "ram insufficient",
        "commit insufficient",
    )
    if any(marker in lowered for marker in memory_markers):
        if "cuda" in lowered or "vram" in lowered:
            return "memory", "gpu_oom"
        return "memory", "system_oom"

    # Timeout errors
    timeout_markers = ("timeout", "timed out", "time limit")
    if any(marker in lowered for marker in timeout_markers):
        return "timeout", "generation_timeout"

    # JSON/parsing errors
    parse_markers = (
        "json",
        "parse",
        "decode",
        "invalid syntax",
        "unexpected token",
    )
    if any(marker in lowered for marker in parse_markers):
        return "parse", "json_parse_error"

    # Network errors
    network_markers = (
        "connection",
        "network",
        "unreachable",
        "refused",
        "timeout",
        "http",
    )
    if any(marker in lowered for marker in network_markers):
        return "network", "connection_error"

    # Model loading errors
    model_markers = (
        "model not found",
        "cannot load",
        "load failed",
        "model unavailable",
    )
    if any(marker in lowered for marker in model_markers):
        return "model", "model_load_error"

    return "unknown", "unclassified_error"


def format_stage_progress(
    stage_name: str,
    attempt: int,
    max_attempts: int,
    *,
    status: str = "running",
    detail: str = "",
) -> str:
    """Format a stage progress message.

    Args:
        stage_name: Name of the stage
        attempt: Current attempt number
        max_attempts: Maximum attempts allowed
        status: Status string (running, success, failed, retrying)
        detail: Optional detail message

    Returns:
        Formatted progress string
    """
    base = f"[{stage_name}] {status.upper()}"
    if max_attempts > 1:
        base = f"[{stage_name}] ({attempt}/{max_attempts}) {status.upper()}"
    if detail:
        base = f"{base}: {detail}"
    return base


def log_stage_start(
    stage_name: str,
    attempt: int = 1,
    max_attempts: int = 1,
    *,
    model_id: str = "",
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """Log the start of a pipeline stage.

    Args:
        stage_name: Name of the stage
        attempt: Current attempt number
        max_attempts: Maximum attempts
        model_id: Model being used
        extra: Additional context to log
    """
    context = {
        "stage": stage_name,
        "attempt": attempt,
        "max_attempts": max_attempts,
    }
    if model_id:
        context["model"] = model_id
    if extra:
        context.update(extra)

    logger.info(
        "Stage started: %s (attempt %d/%d)",
        stage_name,
        attempt,
        max_attempts,
        extra={"pipeline": context},
    )


def log_stage_complete(
    stage_name: str,
    duration_seconds: float,
    *,
    success: bool = True,
    attempt: int = 1,
    output_summary: Optional[Dict[str, Any]] = None,
) -> None:
    """Log the completion of a pipeline stage.

    Args:
        stage_name: Name of the stage
        duration_seconds: Time taken
        success: Whether stage succeeded
        attempt: Attempt number that completed
        output_summary: Summary of output (avoid sensitive data)
    """
    status = "completed" if success else "failed"
    context = {
        "stage": stage_name,
        "status": status,
        "duration_seconds": round(duration_seconds, 3),
        "attempt": attempt,
    }
    if output_summary:
        context["output_summary"] = output_summary

    log_fn = logger.info if success else logger.warning
    log_fn(
        "Stage %s: %s in %.2fs (attempt %d)",
        status,
        stage_name,
        duration_seconds,
        attempt,
        extra={"pipeline": context},
    )


def log_stage_retry(
    stage_name: str,
    attempt: int,
    max_attempts: int,
    error: str,
    *,
    wait_seconds: float = 0.0,
) -> None:
    """Log a stage retry attempt.

    Args:
        stage_name: Name of the stage
        attempt: Failed attempt number
        max_attempts: Maximum attempts
        error: Error that triggered retry
        wait_seconds: Wait time before retry
    """
    error_category, error_type = classify_error(error)
    context = {
        "stage": stage_name,
        "attempt": attempt,
        "max_attempts": max_attempts,
        "error": error[:200] if error else "",
        "error_category": error_category,
        "error_type": error_type,
        "wait_seconds": round(wait_seconds, 1),
    }

    logger.warning(
        "Stage retry: %s attempt %d/%d failed (%s), retrying in %.1fs",
        stage_name,
        attempt,
        max_attempts,
        error_type,
        wait_seconds,
        extra={"pipeline": context},
    )


def log_pipeline_summary(
    timings: PipelineTimings,
    *,
    success: bool = True,
    stages_completed: List[str] = None,
    stages_failed: List[str] = None,
) -> None:
    """Log pipeline execution summary.

    Args:
        timings: Pipeline timing information
        success: Whether pipeline completed successfully
        stages_completed: List of completed stages
        stages_failed: List of failed stages
    """
    context = {
        "success": success,
        "total_seconds": round(timings.total_seconds, 3),
        "stages_completed": stages_completed or [],
        "stages_failed": stages_failed or [],
        "timings": timings.to_dict(),
    }

    status = "completed" if success else "failed"
    log_fn = logger.info if success else logger.error

    log_fn(
        "Pipeline %s in %.2fs (%d stages)",
        status,
        timings.total_seconds,
        len(timings.stage_timings),
        extra={"pipeline": context},
    )


def summarize_json_output(
    payload: Dict[str, Any],
    *,
    include_keys: Optional[List[str]] = None,
    max_list_items: int = 3,
) -> Dict[str, Any]:
    """Create a log-safe summary of JSON output.

    Reduces large payloads to key statistics without sensitive data.

    Args:
        payload: JSON payload to summarize
        include_keys: Specific keys to include
        max_list_items: Maximum items to show from lists

    Returns:
        Summary dict safe for logging
    """
    if not isinstance(payload, dict):
        return {"type": type(payload).__name__}

    summary: Dict[str, Any] = {}

    # Default keys to summarize
    keys = include_keys or [
        "schema_version",
        "skills",
        "experience",
        "education",
        "languages",
        "certifications",
        "ats_keywords",
    ]

    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        if isinstance(value, list):
            summary[f"{key}_count"] = len(value)
        elif isinstance(value, str):
            summary[f"{key}_length"] = len(value)
        elif isinstance(value, dict):
            summary[f"{key}_keys"] = list(value.keys())[:max_list_items]
        else:
            summary[key] = value

    return summary


def create_progress_callback(
    base_callback: Optional[Callable[[str], None]],
    stage_name: str,
) -> Callable[[str], None]:
    """Create a prefixed progress callback for a stage.

    Args:
        base_callback: Original callback function
        stage_name: Stage name to prefix

    Returns:
        Wrapped callback with stage prefix
    """
    if not base_callback:
        return lambda msg: None

    def _prefixed_callback(message: str) -> None:
        prefixed = f"[{stage_name}] {message}"
        base_callback(prefixed)

    return _prefixed_callback
