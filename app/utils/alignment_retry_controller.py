"""
Alignment Retry Controller Module (Sprint 6)

Controls the alignment retry loop for CV generation. When the initial CV
doesn't have sufficient keyword alignment with the job offer, this module
manages the retry process to improve coverage.

Key features:
- Retry budget calculation from config/env
- Missing keyword extraction from alignment audit
- Critic JSON augmentation with alignment feedback
- Alignment threshold management
- Retry decision logic

The retry loop works by:
1. Generating a CV and scoring its alignment with offer keywords
2. If alignment is insufficient, extracting missing keywords
3. Augmenting the critic JSON with the missing keywords
4. Regenerating the CV with enhanced feedback
5. Repeating until alignment is sufficient or retry budget exhausted
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    from ..logging.safe_logger import get_safe_logger
    from ..config import DEFAULT_PII_CONFIG
    logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

# Import from existing modules
from .offer_keywords_utils import dedup_preserve


# Default alignment thresholds
DEFAULT_ALIGNMENT_THRESHOLDS = {
    "exact_keyword_min": 60.0,
    "lexical_family_min": 50.0,
    "overall_min": 55.0,
}

# Default retry settings
DEFAULT_RETRY_ATTEMPTS = 3
MAX_RETRY_ATTEMPTS = 3
MIN_RETRY_ATTEMPTS = 0


@dataclass
class AlignmentRetryConfig:
    """Configuration for alignment retry behavior."""
    # Retry limits
    max_attempts: int = DEFAULT_RETRY_ATTEMPTS

    # Keyword limits
    max_missing_keywords: int = 16
    max_critic_keywords: int = 20

    # Threshold overrides (None means use defaults)
    exact_keyword_min: Optional[float] = None
    lexical_family_min: Optional[float] = None
    overall_min: Optional[float] = None


@dataclass
class AlignmentRetryState:
    """Tracks state during alignment retry loop."""
    retry_count: int = 0
    best_score: float = 0.0
    best_cv_json: Optional[Dict[str, Any]] = None
    best_alignment_audit: Optional[Dict[str, Any]] = None
    current_critic_json: Dict[str, Any] = field(default_factory=dict)

    # Tracking
    scores_history: List[float] = field(default_factory=list)
    improvements: List[float] = field(default_factory=list)


def get_alignment_retry_attempts(
    *,
    custom_parameters: Optional[Dict[str, Any]] = None,
    env_value: Optional[str] = None,
) -> int:
    """
    Get the number of alignment retry attempts allowed.

    Quality-first default: allow up to 3 refinement retries.

    Args:
        custom_parameters: Optional custom configuration dict
        env_value: Optional env value override (CVMATCH_ALIGNMENT_RETRY_ATTEMPTS)

    Returns:
        Number of retry attempts (0-3)
    """
    custom = custom_parameters or {}
    attempts = DEFAULT_RETRY_ATTEMPTS

    # Check custom parameters
    if "alignment_retry_attempts" in custom:
        try:
            attempts = int(custom.get("alignment_retry_attempts"))
        except Exception:
            attempts = DEFAULT_RETRY_ATTEMPTS

    # Check environment variable
    if env_value is None:
        env_value = os.getenv("CVMATCH_ALIGNMENT_RETRY_ATTEMPTS")

    if env_value is not None:
        try:
            attempts = int(env_value)
        except Exception:
            pass

    return max(MIN_RETRY_ATTEMPTS, min(MAX_RETRY_ATTEMPTS, attempts))


def get_alignment_thresholds(
    *,
    custom_parameters: Optional[Dict[str, Any]] = None,
    config: Optional[AlignmentRetryConfig] = None,
) -> Dict[str, float]:
    """
    Get alignment score thresholds.

    Args:
        custom_parameters: Optional custom configuration dict
        config: Optional retry config with threshold overrides

    Returns:
        Dict with exact_keyword_min, lexical_family_min, overall_min
    """
    thresholds = dict(DEFAULT_ALIGNMENT_THRESHOLDS)

    # Apply config overrides
    if config:
        if config.exact_keyword_min is not None:
            thresholds["exact_keyword_min"] = config.exact_keyword_min
        if config.lexical_family_min is not None:
            thresholds["lexical_family_min"] = config.lexical_family_min
        if config.overall_min is not None:
            thresholds["overall_min"] = config.overall_min

    # Apply custom parameter overrides
    custom = custom_parameters or {}
    threshold_keys = ["exact_keyword_min", "lexical_family_min", "overall_min"]

    for key in threshold_keys:
        param_key = f"alignment_threshold_{key}"
        if param_key in custom:
            try:
                thresholds[key] = float(custom.get(param_key))
            except Exception:
                pass

    # Clamp values
    for key in threshold_keys:
        thresholds[key] = max(0.0, min(100.0, float(thresholds[key])))

    return thresholds


def is_alignment_sufficient(
    alignment_audit: Dict[str, Any],
    *,
    thresholds: Optional[Dict[str, float]] = None,
) -> bool:
    """
    Check if alignment audit meets minimum thresholds.

    Args:
        alignment_audit: Alignment audit from scoring
        thresholds: Optional threshold overrides

    Returns:
        True if alignment is sufficient
    """
    if not isinstance(alignment_audit, dict):
        return False

    # Check the 'sufficient' flag if present
    if "sufficient" in alignment_audit:
        return bool(alignment_audit.get("sufficient"))

    # Otherwise check against thresholds
    if thresholds is None:
        thresholds = DEFAULT_ALIGNMENT_THRESHOLDS

    exact_score = float(alignment_audit.get("exact_keyword_score") or 0.0)
    family_score = float(alignment_audit.get("lexical_family_score") or 0.0)
    overall_score = float(alignment_audit.get("overall_score") or 0.0)

    exact_min = thresholds.get("exact_keyword_min", DEFAULT_ALIGNMENT_THRESHOLDS["exact_keyword_min"])
    family_min = thresholds.get("lexical_family_min", DEFAULT_ALIGNMENT_THRESHOLDS["lexical_family_min"])
    overall_min = thresholds.get("overall_min", DEFAULT_ALIGNMENT_THRESHOLDS["overall_min"])

    return (
        exact_score >= exact_min
        and family_score >= family_min
        and overall_score >= overall_min
    )


def build_alignment_missing_keywords(
    audit: Dict[str, Any],
    *,
    max_items: int = 16,
) -> List[str]:
    """
    Extract missing keywords from an alignment audit.

    Combines:
    1. Exact missing terms
    2. Missing keyword family keys
    3. Top terms from missing families

    Args:
        audit: Alignment audit dictionary
        max_items: Maximum keywords to return

    Returns:
        List of missing keywords
    """
    if not isinstance(audit, dict):
        return []

    merged: List[str] = []

    # Add exact missing terms
    exact_missing = audit.get("exact_missing_terms")
    if isinstance(exact_missing, list):
        merged.extend(str(item).strip() for item in exact_missing if str(item).strip())

    # Add missing family keys and their top terms
    families = audit.get("keyword_families")
    missing_families = audit.get("missing_keyword_families")

    if isinstance(families, dict) and isinstance(missing_families, list):
        for family in missing_families:
            family_key = str(family or "").strip()
            if not family_key:
                continue
            merged.append(family_key)

            # Add top 3 terms from the family
            values = families.get(family_key)
            if isinstance(values, list):
                merged.extend(
                    str(item).strip()
                    for item in values[:3]
                    if str(item).strip()
                )

    return dedup_preserve([item for item in merged if item])[:max(1, int(max_items))]


def augment_critic_with_alignment_feedback(
    critic_json: Dict[str, Any],
    audit: Dict[str, Any],
    *,
    max_keywords: int = 20,
) -> Dict[str, Any]:
    """
    Augment critic JSON with missing keywords from alignment audit.

    This creates a new critic JSON with enhanced missing_keywords list
    that includes both the original critic's missing keywords and
    the keywords identified as missing by the alignment audit.

    Args:
        critic_json: Original critic JSON
        audit: Alignment audit with missing terms/families
        max_keywords: Maximum missing keywords to include

    Returns:
        New critic JSON with augmented missing_keywords
    """
    payload = dict(critic_json) if isinstance(critic_json, dict) else {}

    # Start with existing missing keywords
    existing_missing = payload.get("missing_keywords")
    merged_missing: List[str] = []

    if isinstance(existing_missing, list):
        merged_missing.extend(
            str(item).strip() for item in existing_missing if str(item).strip()
        )

    # Add alignment missing keywords
    alignment_missing = build_alignment_missing_keywords(audit)
    merged_missing.extend(alignment_missing)

    payload["missing_keywords"] = dedup_preserve(merged_missing)[:max_keywords]

    return payload


def should_retry_alignment(
    current_audit: Dict[str, Any],
    retry_count: int,
    retry_budget: int,
    *,
    thresholds: Optional[Dict[str, float]] = None,
) -> bool:
    """
    Determine if alignment retry should be attempted.

    Args:
        current_audit: Current alignment audit
        retry_count: Number of retries already attempted
        retry_budget: Maximum retries allowed
        thresholds: Optional threshold overrides

    Returns:
        True if retry should be attempted
    """
    # Check budget
    if retry_count >= retry_budget:
        return False

    # Check if already sufficient
    if is_alignment_sufficient(current_audit, thresholds=thresholds):
        return False

    return True


def should_accept_retry_result(
    candidate_audit: Dict[str, Any],
    current_audit: Dict[str, Any],
    *,
    require_improvement: bool = False,
) -> bool:
    """
    Determine if a retry result should be accepted.

    A retry result is accepted if:
    1. It achieves sufficient alignment, OR
    2. Its overall score is >= current score

    Args:
        candidate_audit: Audit from the retry attempt
        current_audit: Current best audit
        require_improvement: If True, require score improvement

    Returns:
        True if retry result should be accepted
    """
    candidate_sufficient = is_alignment_sufficient(candidate_audit)
    if candidate_sufficient:
        return True

    candidate_score = float(candidate_audit.get("overall_score") or 0.0)
    current_score = float(current_audit.get("overall_score") or 0.0)

    if require_improvement:
        return candidate_score > current_score
    else:
        return candidate_score >= current_score


def log_alignment_retry_result(
    retry_count: int,
    retry_budget: int,
    audit: Dict[str, Any],
    *,
    accepted: bool = True,
) -> None:
    """
    Log alignment retry result for monitoring.

    Args:
        retry_count: Current retry number
        retry_budget: Total retry budget
        audit: Alignment audit from the retry
        accepted: Whether the result was accepted
    """
    exact = float(audit.get("exact_keyword_score") or 0.0)
    family = float(audit.get("lexical_family_score") or 0.0)
    overall = float(audit.get("overall_score") or 0.0)
    sufficient = bool(audit.get("sufficient"))

    status = "accepted" if accepted else "rejected"

    logger.info(
        "CV alignment retry %s/%s %s: exact=%.1f family=%.1f overall=%.1f sufficient=%s",
        retry_count,
        retry_budget,
        status,
        exact,
        family,
        overall,
        sufficient,
    )


def create_retry_state(
    initial_cv_json: Dict[str, Any],
    initial_audit: Dict[str, Any],
    critic_json: Dict[str, Any],
) -> AlignmentRetryState:
    """
    Create initial retry state.

    Args:
        initial_cv_json: Initial generated CV JSON
        initial_audit: Initial alignment audit
        critic_json: Initial critic JSON

    Returns:
        AlignmentRetryState initialized with current values
    """
    initial_score = float(initial_audit.get("overall_score") or 0.0)

    return AlignmentRetryState(
        retry_count=0,
        best_score=initial_score,
        best_cv_json=initial_cv_json,
        best_alignment_audit=initial_audit,
        current_critic_json=dict(critic_json) if isinstance(critic_json, dict) else {},
        scores_history=[initial_score],
        improvements=[],
    )


def update_retry_state(
    state: AlignmentRetryState,
    candidate_cv_json: Dict[str, Any],
    candidate_audit: Dict[str, Any],
    *,
    accepted: bool,
) -> None:
    """
    Update retry state after a retry attempt.

    Args:
        state: Current retry state (modified in place)
        candidate_cv_json: CV JSON from retry attempt
        candidate_audit: Alignment audit from retry attempt
        accepted: Whether the result was accepted
    """
    candidate_score = float(candidate_audit.get("overall_score") or 0.0)
    state.scores_history.append(candidate_score)
    state.improvements.append(candidate_score - state.best_score)

    if accepted:
        state.best_cv_json = candidate_cv_json
        state.best_alignment_audit = candidate_audit
        state.best_score = candidate_score

    state.retry_count += 1


def get_retry_summary(state: AlignmentRetryState) -> Dict[str, Any]:
    """
    Get a summary of the retry process.

    Args:
        state: Final retry state

    Returns:
        Summary dict with retry statistics
    """
    return {
        "total_retries": state.retry_count,
        "final_score": state.best_score,
        "initial_score": state.scores_history[0] if state.scores_history else 0.0,
        "total_improvement": (
            state.best_score - state.scores_history[0]
            if state.scores_history
            else 0.0
        ),
        "scores_history": list(state.scores_history),
        "improvements": list(state.improvements),
        "sufficient": is_alignment_sufficient(state.best_alignment_audit or {}),
    }


class AlignmentRetryController:
    """
    Controller for managing alignment retry loop.

    This class encapsulates the retry logic and provides a clean
    interface for the pipeline orchestrator.
    """

    def __init__(
        self,
        *,
        config: Optional[AlignmentRetryConfig] = None,
        custom_parameters: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize retry controller.

        Args:
            config: Optional retry configuration
            custom_parameters: Optional custom parameters from QwenManager
        """
        self._config = config or AlignmentRetryConfig()
        self._custom_parameters = custom_parameters or {}
        self._retry_budget = get_alignment_retry_attempts(
            custom_parameters=custom_parameters,
        )
        self._thresholds = get_alignment_thresholds(
            custom_parameters=custom_parameters,
            config=config,
        )

    @property
    def retry_budget(self) -> int:
        """Get the retry budget."""
        return self._retry_budget

    @property
    def thresholds(self) -> Dict[str, float]:
        """Get alignment thresholds."""
        return dict(self._thresholds)

    def is_sufficient(self, audit: Dict[str, Any]) -> bool:
        """Check if alignment is sufficient."""
        return is_alignment_sufficient(audit, thresholds=self._thresholds)

    def should_retry(
        self,
        current_audit: Dict[str, Any],
        retry_count: int,
    ) -> bool:
        """Check if retry should be attempted."""
        return should_retry_alignment(
            current_audit,
            retry_count,
            self._retry_budget,
            thresholds=self._thresholds,
        )

    def augment_critic(
        self,
        critic_json: Dict[str, Any],
        audit: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Augment critic with alignment feedback."""
        return augment_critic_with_alignment_feedback(
            critic_json,
            audit,
            max_keywords=self._config.max_critic_keywords,
        )

    def should_accept(
        self,
        candidate_audit: Dict[str, Any],
        current_audit: Dict[str, Any],
    ) -> bool:
        """Check if retry result should be accepted."""
        return should_accept_retry_result(candidate_audit, current_audit)

    def run_retry_loop(
        self,
        initial_cv_json: Dict[str, Any],
        initial_audit: Dict[str, Any],
        critic_json: Dict[str, Any],
        generate_fn: Callable[[Dict[str, Any]], Tuple[Dict[str, Any], Dict[str, Any]]],
        *,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
        """
        Run the alignment retry loop.

        Args:
            initial_cv_json: Initial generated CV JSON
            initial_audit: Initial alignment audit
            critic_json: Initial critic JSON
            generate_fn: Function to generate CV (takes critic_json, returns (cv_json, audit))
            progress_callback: Optional progress callback

        Returns:
            Tuple of (final_cv_json, final_audit, final_critic_json)
        """
        state = create_retry_state(initial_cv_json, initial_audit, critic_json)

        while self.should_retry(state.best_alignment_audit or {}, state.retry_count):
            if progress_callback:
                progress_callback(
                    f"[ALIGN] Coverage insuffisante, regeneration final "
                    f"({state.retry_count + 1}/{self._retry_budget})..."
                )

            # Augment critic with alignment feedback
            state.current_critic_json = self.augment_critic(
                state.current_critic_json,
                state.best_alignment_audit or {},
            )

            try:
                candidate_cv, candidate_audit = generate_fn(state.current_critic_json)
            except Exception as exc:
                logger.warning(
                    "Alignment retry failed at attempt %s/%s: %s",
                    state.retry_count + 1,
                    self._retry_budget,
                    exc,
                )
                break

            accepted = self.should_accept(
                candidate_audit,
                state.best_alignment_audit or {},
            )

            log_alignment_retry_result(
                state.retry_count + 1,
                self._retry_budget,
                candidate_audit,
                accepted=accepted,
            )

            update_retry_state(state, candidate_cv, candidate_audit, accepted=accepted)

        if not self.is_sufficient(state.best_alignment_audit or {}):
            logger.warning(
                "CV alignment remains below threshold after retries: "
                "exact=%.1f family=%.1f overall=%.1f",
                float((state.best_alignment_audit or {}).get("exact_keyword_score") or 0.0),
                float((state.best_alignment_audit or {}).get("lexical_family_score") or 0.0),
                float((state.best_alignment_audit or {}).get("overall_score") or 0.0),
            )

        return (
            state.best_cv_json or initial_cv_json,
            state.best_alignment_audit or initial_audit,
            state.current_critic_json,
        )
