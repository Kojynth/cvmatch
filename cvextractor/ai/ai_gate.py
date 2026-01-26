"""
AI Gate with STRICT Mode and Health Check
=========================================

Enhanced AI gate with fail-fast behavior, health monitoring, and configurable modes.
Ensures no heuristic fallback occurs in STRICT mode when AI is required.
"""

import numpy as np
from typing import List, Dict, Any, Optional, NamedTuple, Union, Tuple
from dataclasses import dataclass
from enum import Enum
import logging
import time

from ..utils.log_safety import create_safe_logger_wrapper
from ..metrics.instrumentation import get_metrics_collector


class AIMode(Enum):
    """AI operation modes."""

    STRICT = "STRICT"  # AI required, fail-fast if unhealthy
    FIRST = "FIRST"  # Prefer AI, fallback to heuristics
    HYBRID = "HYBRID"  # Fuse AI strong hits with heuristics
    HEURISTIC = "HEURISTIC"  # Force heuristics only


class AIUnhealthyError(RuntimeError):
    """Raised when AI backend is unhealthy in STRICT mode."""

    pass


@dataclass
class HealthCheckResult:
    """Result of AI backend health check."""

    ok: bool
    reason: str
    median_conf: float = 0.0
    stdev_conf: float = 0.0
    response_time_ms: float = 0.0
    warmup_success: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "reason": self.reason,
            "median_conf": self.median_conf,
            "stdev_conf": self.stdev_conf,
            "response_time_ms": self.response_time_ms,
            "warmup_success": self.warmup_success,
        }


class GateDecision(NamedTuple):
    """AI gate decision result."""

    mode: str
    accepted: List[Any]
    weak: List[Any]
    reason: str = ""


class AIHealthMonitor:
    """Monitors AI backend health with deterministic checks."""

    def __init__(
        self,
        min_median_conf: float = 0.15,
        min_stdev_conf: float = 0.01,
        max_response_time_ms: float = 10000.0,
    ):
        self.min_median_conf = min_median_conf
        self.min_stdev_conf = min_stdev_conf
        self.max_response_time_ms = max_response_time_ms

        # Logger
        base_logger = logging.getLogger(__name__)
        self.logger = create_safe_logger_wrapper(base_logger)

    def healthcheck(self, model, tokenizer) -> HealthCheckResult:
        """
        Perform comprehensive health check on AI backend.

        Checks:
        - Model and tokenizer availability
        - Warmup batch processing
        - Confidence distribution sanity
        - Response time
        """
        start_time = time.time()

        # Check 1: Model and tokenizer availability
        if model is None or tokenizer is None:
            return HealthCheckResult(
                ok=False,
                reason="model_or_tokenizer_none",
                response_time_ms=(time.time() - start_time) * 1000,
            )

        try:
            # Check 2: Warmup batch with synthetic data
            synthetic_spans = [
                "Senior Software Engineer",  # Role
                "TechCorp Solutions Inc",  # Company
                "2019 - 2023",  # Date range
            ]

            # Predict on warmup batch
            warmup_start = time.time()
            try:
                predictions = model.predict(synthetic_spans)
                warmup_time = (time.time() - warmup_start) * 1000

                if not predictions:
                    return HealthCheckResult(
                        ok=False,
                        reason="empty_predictions",
                        response_time_ms=warmup_time,
                    )

                # Check 3: Extract confidences and validate
                confidences = []
                for pred in predictions:
                    if hasattr(pred, "conf"):
                        conf = pred.conf
                    elif hasattr(pred, "confidence"):
                        conf = pred.confidence
                    elif isinstance(pred, dict) and "confidence" in pred:
                        conf = pred["confidence"]
                    else:
                        # Try to extract confidence from prediction
                        conf = float(pred) if isinstance(pred, (int, float)) else 0.0

                    confidences.append(conf)

                # Check 4: Validate confidence values
                if not confidences:
                    return HealthCheckResult(
                        ok=False,
                        reason="no_confidence_values",
                        response_time_ms=warmup_time,
                    )

                # Convert to numpy for analysis
                conf_array = np.array(confidences, dtype=float)

                # Check for non-finite values
                if not np.all(np.isfinite(conf_array)):
                    return HealthCheckResult(
                        ok=False,
                        reason="non_finite_confidences",
                        response_time_ms=warmup_time,
                    )

                # Calculate statistics
                median_conf = float(np.median(conf_array))
                stdev_conf = float(np.std(conf_array))

                # Check 5: Response time
                total_time = (time.time() - start_time) * 1000
                if total_time > self.max_response_time_ms:
                    return HealthCheckResult(
                        ok=False,
                        reason=f"response_too_slow_{total_time:.1f}ms",
                        median_conf=median_conf,
                        stdev_conf=stdev_conf,
                        response_time_ms=total_time,
                    )

                # Check 6: Confidence distribution sanity
                conf_ok = (
                    median_conf >= self.min_median_conf
                    and stdev_conf >= self.min_stdev_conf
                )

                if not conf_ok:
                    return HealthCheckResult(
                        ok=False,
                        reason=f"poor_conf_distribution_med={median_conf:.3f}_std={stdev_conf:.3f}",
                        median_conf=median_conf,
                        stdev_conf=stdev_conf,
                        response_time_ms=total_time,
                        warmup_success=True,
                    )

                # All checks passed
                return HealthCheckResult(
                    ok=True,
                    reason="all_checks_passed",
                    median_conf=median_conf,
                    stdev_conf=stdev_conf,
                    response_time_ms=total_time,
                    warmup_success=True,
                )

            except Exception as model_error:
                return HealthCheckResult(
                    ok=False,
                    reason=f"model_prediction_error_{type(model_error).__name__}",
                    response_time_ms=(time.time() - start_time) * 1000,
                )

        except Exception as general_error:
            return HealthCheckResult(
                ok=False,
                reason=f"general_health_check_error_{type(general_error).__name__}",
                response_time_ms=(time.time() - start_time) * 1000,
            )


class EnhancedAIGate:
    """Enhanced AI gate with strict mode and health monitoring."""

    def __init__(
        self,
        ai_mode: AIMode = AIMode.STRICT,
        soft_threshold: float = 0.30,
        hard_threshold: float = 0.45,
        health_check_enabled: bool = True,
        debug_mode: bool = False,
    ):
        self.ai_mode = ai_mode
        self.soft_threshold = soft_threshold
        self.hard_threshold = hard_threshold
        self.health_check_enabled = health_check_enabled
        self.debug_mode = debug_mode

        # Health monitor
        self.health_monitor = AIHealthMonitor()

        # Logger
        base_logger = logging.getLogger(__name__)
        self.logger = create_safe_logger_wrapper(base_logger)

        # Cache for health check results
        self._last_health_check: Optional[HealthCheckResult] = None
        self._health_check_cache_time = 0
        self._health_check_cache_duration = 300  # 5 minutes

    def gate_candidates(
        self, candidates: List[Any], model, tokenizer, doc_id: str = "unknown"
    ) -> GateDecision:
        """
        Main gating function with health check and mode enforcement.

        Args:
            candidates: Candidate items to gate
            model: AI model instance
            tokenizer: Tokenizer instance
            doc_id: Document ID for metrics

        Returns:
            GateDecision with mode, accepted/weak candidates, and reason

        Raises:
            AIUnhealthyError: In STRICT mode when AI is unhealthy
        """
        metrics = get_metrics_collector(doc_id)

        self.logger.info(
            f"AI_GATE: starting | mode={self.ai_mode.value} candidates={len(candidates)}"
        )

        # Step 1: Health check (if enabled and not cached)
        health_result = None
        if self.health_check_enabled:
            health_result = self._get_cached_health_check(model, tokenizer)
            metrics.log_ai_gate_health(
                health_score=health_result.median_conf if health_result.ok else 0.0,
                mode=self.ai_mode.value,
            )

        # Step 2: Mode-specific handling
        if self.ai_mode == AIMode.STRICT:
            return self._handle_strict_mode(candidates, model, health_result)

        elif self.ai_mode == AIMode.FIRST:
            return self._handle_first_mode(candidates, model, health_result)

        elif self.ai_mode == AIMode.HYBRID:
            return self._handle_hybrid_mode(candidates, model, health_result)

        elif self.ai_mode == AIMode.HEURISTIC:
            return self._handle_heuristic_mode(candidates)

        else:
            raise ValueError(f"Unknown AI mode: {self.ai_mode}")

    def _get_cached_health_check(self, model, tokenizer) -> HealthCheckResult:
        """Get cached health check result or perform new check."""
        current_time = time.time()

        # Use cached result if still valid
        if (
            self._last_health_check
            and current_time - self._health_check_cache_time
            < self._health_check_cache_duration
        ):
            return self._last_health_check

        # Perform new health check
        self.logger.debug("AI_GATE: performing health check")
        health_result = self.health_monitor.healthcheck(model, tokenizer)

        # Cache result
        self._last_health_check = health_result
        self._health_check_cache_time = current_time

        self.logger.info(f"AI_GATE: health_check | {health_result.to_dict()}")
        return health_result

    def _handle_strict_mode(
        self, candidates: List[Any], model, health_result: Optional[HealthCheckResult]
    ) -> GateDecision:
        """Handle STRICT mode: AI required, fail-fast if unhealthy."""
        # Check health
        if health_result and not health_result.ok:
            error_msg = f"AI backend unhealthy in STRICT mode: {health_result.reason}"
            self.logger.error(f"AI_GATE: {error_msg}")
            raise AIUnhealthyError(error_msg)

        # Proceed with AI gating
        try:
            accepted, weak = self._perform_ai_gating(candidates, model)

            self.logger.info(
                f"AI_GATE: STRICT mode success | accepted={len(accepted)} weak={len(weak)}"
            )
            return GateDecision(
                mode="AI_STRICT",
                accepted=accepted,
                weak=weak,
                reason="strict_mode_success",
            )

        except Exception as e:
            error_msg = f"AI gating failed in STRICT mode: {e}"
            self.logger.error(f"AI_GATE: {error_msg}")
            raise AIUnhealthyError(error_msg)

    def _handle_first_mode(
        self, candidates: List[Any], model, health_result: Optional[HealthCheckResult]
    ) -> GateDecision:
        """Handle FIRST mode: Prefer AI, fallback to heuristics."""
        # Try AI first
        if not health_result or health_result.ok:
            try:
                accepted, weak = self._perform_ai_gating(candidates, model)
                self.logger.info(
                    f"AI_GATE: FIRST mode AI success | accepted={len(accepted)} weak={len(weak)}"
                )
                return GateDecision(
                    mode="AI_FIRST",
                    accepted=accepted,
                    weak=weak,
                    reason="ai_first_success",
                )
            except Exception as e:
                self.logger.warning(
                    f"AI_GATE: AI failed in FIRST mode, falling back to heuristics: {e}"
                )

        # Fallback to heuristics
        self.logger.info("AI_GATE: FIRST mode fallback to heuristics")
        return GateDecision(
            mode="HEURISTIC_ONLY",
            accepted=[],
            weak=[],
            reason=f"ai_unavailable_{health_result.reason if health_result else 'unknown'}",
        )

    def _handle_hybrid_mode(
        self, candidates: List[Any], model, health_result: Optional[HealthCheckResult]
    ) -> GateDecision:
        """Handle HYBRID mode: Fuse AI strong hits with heuristics."""
        accepted = []
        weak = []

        # Try AI gating if healthy
        if health_result and health_result.ok:
            try:
                ai_accepted, ai_weak = self._perform_ai_gating(candidates, model)
                accepted.extend(ai_accepted)
                weak.extend(ai_weak)
                self.logger.info(
                    f"AI_GATE: HYBRID mode AI component | accepted={len(ai_accepted)} weak={len(ai_weak)}"
                )
            except Exception as e:
                self.logger.warning(f"AI_GATE: AI component failed in HYBRID mode: {e}")

        # Add heuristic component (placeholder for now)
        # In real implementation, this would call heuristic gating
        self.logger.info("AI_GATE: HYBRID mode includes heuristic component")

        return GateDecision(
            mode="HYBRID_FUSION",
            accepted=accepted,
            weak=weak,
            reason="hybrid_ai_and_heuristics",
        )

    def _handle_heuristic_mode(self, candidates: List[Any]) -> GateDecision:
        """Handle HEURISTIC mode: Force heuristics only."""
        self.logger.info("AI_GATE: HEURISTIC mode - skipping AI entirely")
        return GateDecision(
            mode="HEURISTIC_ONLY", accepted=[], weak=[], reason="forced_heuristic_mode"
        )

    def _perform_ai_gating(
        self, candidates: List[Any], model
    ) -> Tuple[List[Any], List[Any]]:
        """Perform actual AI prediction and gating."""
        if not candidates:
            return [], []

        # Prepare candidate texts for prediction
        candidate_texts = []
        for candidate in candidates:
            if hasattr(candidate, "text"):
                candidate_texts.append(candidate.text)
            elif isinstance(candidate, str):
                candidate_texts.append(candidate)
            else:
                candidate_texts.append(str(candidate))

        # Get AI predictions
        predictions = model.predict(candidate_texts)

        # Apply thresholds
        accepted = []
        weak = []

        for i, prediction in enumerate(predictions):
            if i < len(candidates):
                candidate = candidates[i]

                # Extract confidence
                if hasattr(prediction, "conf"):
                    conf = prediction.conf
                elif hasattr(prediction, "confidence"):
                    conf = prediction.confidence
                elif isinstance(prediction, dict) and "confidence" in prediction:
                    conf = prediction["confidence"]
                else:
                    conf = (
                        float(prediction)
                        if isinstance(prediction, (int, float))
                        else 0.0
                    )

                # Apply thresholds
                if conf >= self.hard_threshold:
                    accepted.append(candidate)
                elif conf >= self.soft_threshold:
                    weak.append(candidate)
                # Below soft threshold: rejected (not included)

        return accepted, weak


# Convenience functions for backward compatibility
def gate_candidates(
    candidates: List[Any],
    model,
    tokenizer,
    ai_mode: Union[str, AIMode] = AIMode.STRICT,
    soft_threshold: float = 0.30,
    hard_threshold: float = 0.45,
    doc_id: str = "unknown",
) -> GateDecision:
    """
    Convenience function for gating candidates.

    Args:
        candidates: Items to gate
        model: AI model
        tokenizer: Tokenizer
        ai_mode: AI operation mode
        soft_threshold: Soft confidence threshold
        hard_threshold: Hard confidence threshold
        doc_id: Document ID for metrics

    Returns:
        GateDecision
    """
    # Convert string mode to enum
    if isinstance(ai_mode, str):
        ai_mode = AIMode(ai_mode.upper())

    gate = EnhancedAIGate(
        ai_mode=ai_mode, soft_threshold=soft_threshold, hard_threshold=hard_threshold
    )

    return gate.gate_candidates(candidates, model, tokenizer, doc_id)


# Mock model for testing
class MockAIModel:
    """Mock AI model for testing and offline scenarios."""

    def __init__(self, healthy: bool = True, response_time: float = 0.1):
        self.healthy = healthy
        self.response_time = response_time

    def predict(self, texts: List[str]) -> List[Dict[str, float]]:
        """Mock prediction with configurable behavior."""
        import time
        import random

        time.sleep(self.response_time)

        if not self.healthy:
            raise RuntimeError("Mock model is unhealthy")

        predictions = []
        for text in texts:
            # Generate mock confidence based on text length and content
            base_conf = min(0.8, len(text) / 100.0)
            noise = random.uniform(-0.2, 0.2)
            conf = max(0.0, min(1.0, base_conf + noise))

            predictions.append({"confidence": conf})

        return predictions


# Export main classes and functions
__all__ = [
    "AIMode",
    "AIUnhealthyError",
    "HealthCheckResult",
    "GateDecision",
    "AIHealthMonitor",
    "EnhancedAIGate",
    "gate_candidates",
    "MockAIModel",
]
