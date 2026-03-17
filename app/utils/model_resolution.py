"""
Model Resolution Module

Centralized model selection and ranking logic.
This module extracts model selection from QwenManager to provide
consistent model resolution across the pipeline.

Key features:
- Model candidate ranking by capability/memory
- Memory-aware model selection
- Fallback model determination
- Model compatibility checks
- Quality vs speed preference handling

These functions enable intelligent model selection without depending on
QwenManager state, making them suitable for both in-process and subprocess
pipeline stages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    from ..logging.safe_logger import get_safe_logger
    from ..config import DEFAULT_PII_CONFIG
    logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class ModelCandidate:
    """A model candidate for selection."""
    model_id: str
    model_path: str = ""
    required_ram_gb: float = 0.0
    required_vram_gb: float = 0.0
    quality_stars: float = 0.0
    speed_rating: float = 0.0
    estimated_size_gb: float = 0.0

    @property
    def fits_in_ram(self) -> bool:
        """Check if model fits in available RAM (placeholder)."""
        return True

    @property
    def fits_in_vram(self) -> bool:
        """Check if model fits in available VRAM (placeholder)."""
        return True


@dataclass
class ModelSelectionResult:
    """Result of model selection."""
    model_id: Optional[str] = None
    model_path: str = ""
    reason: str = ""
    quality_score: float = 0.0
    memory_fit: bool = True
    candidates_considered: int = 0


@dataclass
class MemoryBudget:
    """Memory budget for model selection."""
    available_ram_gb: float = 0.0
    available_vram_gb: float = 0.0
    ram_fit_ratio: float = 0.92
    vram_tolerance_gb: float = 0.5


# ---------------------------------------------------------------------------
# Model Size Estimation
# ---------------------------------------------------------------------------

def estimate_model_size_gb(
    *,
    model_name: str = "",
    model_id: str = "",
    parameters_b: Optional[float] = None,
) -> float:
    """
    Estimate model size in GB based on name or known parameters.

    Args:
        model_name: Model name/path
        model_id: Model ID
        parameters_b: Known parameters in billions (optional)

    Returns:
        Estimated size in GB
    """
    if parameters_b is not None and parameters_b > 0:
        # Rough estimate: 1B params ≈ 2GB at FP16, 1GB at INT8
        return parameters_b * 1.5  # Average assumption

    # Extract from model name
    combined = f"{model_name} {model_id}".lower()

    # Check for common size indicators
    size_patterns = [
        ("72b", 72.0),
        ("70b", 70.0),
        ("32b", 32.0),
        ("14b", 14.0),
        ("13b", 13.0),
        ("8b", 8.0),
        ("7b", 7.0),
        ("3b", 3.0),
        ("1.5b", 1.5),
        ("1b", 1.0),
        ("0.5b", 0.5),
        ("500m", 0.5),
    ]

    for pattern, params_b in size_patterns:
        if pattern in combined:
            return params_b * 1.5

    # Default fallback
    return 7.0  # Assume 7B model


def estimate_required_ram_gb(
    *,
    model_name: str = "",
    model_id: str = "",
    parameters_b: Optional[float] = None,
    overhead_factor: float = 1.10,
    overhead_constant: float = 0.8,
) -> float:
    """
    Estimate required RAM in GB for model loading.

    Args:
        model_name: Model name/path
        model_id: Model ID
        parameters_b: Known parameters in billions
        overhead_factor: Multiplicative overhead
        overhead_constant: Constant overhead in GB

    Returns:
        Estimated RAM requirement in GB
    """
    params_b = parameters_b
    if params_b is None:
        params_b = estimate_model_size_gb(
            model_name=model_name,
            model_id=model_id,
        ) / 1.5  # Reverse the size estimation

    gb_per_b = 2.0  # FP16 default
    return max(1.5, params_b * gb_per_b * overhead_factor + overhead_constant)


# ---------------------------------------------------------------------------
# Candidate Filtering
# ---------------------------------------------------------------------------

def filter_candidates_by_memory(
    candidates: List[ModelCandidate],
    budget: MemoryBudget,
) -> List[ModelCandidate]:
    """
    Filter model candidates by memory constraints.

    Args:
        candidates: List of model candidates
        budget: Memory budget constraints

    Returns:
        List of candidates that fit in memory
    """
    fitting = []
    fit_ratio = max(0.5, budget.ram_fit_ratio)

    for candidate in candidates:
        # Check RAM fit
        ram_fits = (
            budget.available_ram_gb <= 0
            or candidate.required_ram_gb <= budget.available_ram_gb * fit_ratio
        )

        # Check VRAM fit (with tolerance for CPU/disk offload)
        vram_fits = True
        if budget.available_vram_gb > 0 and candidate.required_vram_gb > 0:
            vram_fits = (
                candidate.required_vram_gb
                <= budget.available_vram_gb + budget.vram_tolerance_gb
            )

        if ram_fits and vram_fits:
            fitting.append(candidate)

    return fitting


def filter_candidates_by_size(
    candidates: List[ModelCandidate],
    min_size_gb: float = 0.0,
    max_size_gb: float = float("inf"),
) -> List[ModelCandidate]:
    """
    Filter model candidates by size constraints.

    Args:
        candidates: List of model candidates
        min_size_gb: Minimum model size in GB
        max_size_gb: Maximum model size in GB

    Returns:
        List of candidates within size range
    """
    return [
        c for c in candidates
        if min_size_gb <= c.estimated_size_gb <= max_size_gb
    ]


def filter_candidates_by_prefix(
    candidates: List[ModelCandidate],
    excluded_prefixes: Optional[List[str]] = None,
) -> List[ModelCandidate]:
    """
    Filter out candidates with excluded path prefixes.

    Args:
        candidates: List of model candidates
        excluded_prefixes: List of excluded path prefixes

    Returns:
        Filtered list of candidates
    """
    if not excluded_prefixes:
        return candidates

    blocked = [
        prefix.strip().lower()
        for prefix in excluded_prefixes
        if prefix and prefix.strip()
    ]

    if not blocked:
        return candidates

    return [
        c for c in candidates
        if not any(
            c.model_path.lower().startswith(prefix)
            for prefix in blocked
        )
    ]


# ---------------------------------------------------------------------------
# Candidate Ranking
# ---------------------------------------------------------------------------

def rank_candidates_by_quality(
    candidates: List[ModelCandidate],
    *,
    prefer_quality: bool = True,
) -> List[ModelCandidate]:
    """
    Rank model candidates by quality.

    Args:
        candidates: List of model candidates
        prefer_quality: Whether to prefer quality over speed

    Returns:
        Sorted list of candidates
    """
    if prefer_quality:
        # Quality first, then low RAM penalty, then low VRAM
        return sorted(
            candidates,
            key=lambda c: (
                -c.quality_stars,
                c.required_vram_gb,
                c.required_ram_gb,
                -c.speed_rating,
            ),
        )
    else:
        # VRAM first (fast loading), then RAM, then quality
        return sorted(
            candidates,
            key=lambda c: (
                c.required_vram_gb,
                c.required_ram_gb,
                -c.quality_stars,
                -c.speed_rating,
            ),
        )


def rank_candidates_with_penalty(
    candidates: List[ModelCandidate],
    budget: MemoryBudget,
    *,
    prefer_quality: bool = True,
) -> List[Tuple[float, ModelCandidate]]:
    """
    Rank candidates with memory penalty scores.

    Args:
        candidates: List of model candidates
        budget: Memory budget
        prefer_quality: Whether to prefer quality

    Returns:
        List of (penalty_score, candidate) tuples, sorted
    """
    scored = []

    for candidate in candidates:
        # Calculate RAM penalty
        lowram_penalty = 0.0
        if budget.available_ram_gb > 0:
            if candidate.required_ram_gb > budget.available_ram_gb:
                lowram_penalty = candidate.required_ram_gb - budget.available_ram_gb

        if prefer_quality:
            # Quality-first: prioritize quality, penalize memory overuse
            score = (
                -candidate.quality_stars,
                lowram_penalty,
                candidate.required_vram_gb,
                candidate.required_ram_gb,
                -candidate.speed_rating,
            )
        else:
            # Speed-first: prioritize low memory, then speed
            score = (
                candidate.required_vram_gb,
                candidate.required_ram_gb,
                lowram_penalty,
                -candidate.quality_stars,
                -candidate.speed_rating,
            )

        scored.append((score, candidate))

    scored.sort(key=lambda x: x[0])
    return [(0.0, c) for _, c in scored]  # Return with normalized scores


# ---------------------------------------------------------------------------
# Model Selection
# ---------------------------------------------------------------------------

def select_best_model(
    candidates: List[ModelCandidate],
    budget: MemoryBudget,
    *,
    prefer_quality: bool = True,
    min_size_gb: float = 0.0,
    excluded_prefixes: Optional[List[str]] = None,
    current_model_id: Optional[str] = None,
) -> ModelSelectionResult:
    """
    Select the best model from candidates based on constraints.

    This is the main entry point for model selection. It:
    1. Filters out excluded prefixes
    2. Filters by minimum size
    3. Filters by memory constraints
    4. Ranks by quality/speed preference
    5. Returns the best candidate

    Args:
        candidates: List of model candidates
        budget: Memory budget constraints
        prefer_quality: Whether to prefer quality over speed
        min_size_gb: Minimum model size in GB
        excluded_prefixes: Prefixes to exclude (e.g., blocked repos)
        current_model_id: Currently loaded model (excluded from selection)

    Returns:
        ModelSelectionResult with the best candidate
    """
    if not candidates:
        return ModelSelectionResult(reason="no_candidates")

    # Filter out current model
    filtered = [
        c for c in candidates
        if c.model_id != current_model_id
    ]

    if not filtered:
        return ModelSelectionResult(
            reason="all_excluded",
            candidates_considered=len(candidates),
        )

    # Filter by prefix
    filtered = filter_candidates_by_prefix(filtered, excluded_prefixes)
    if not filtered:
        return ModelSelectionResult(
            reason="all_blocked",
            candidates_considered=len(candidates),
        )

    # Filter by size
    if min_size_gb > 0:
        filtered = filter_candidates_by_size(filtered, min_size_gb=min_size_gb)
        if not filtered:
            return ModelSelectionResult(
                reason="all_too_small",
                candidates_considered=len(candidates),
            )

    # Filter by memory and get fitting candidates
    fitting = filter_candidates_by_memory(filtered, budget)

    if fitting:
        # Rank by quality/speed preference
        ranked = rank_candidates_by_quality(fitting, prefer_quality=prefer_quality)
        best = ranked[0]
        return ModelSelectionResult(
            model_id=best.model_id,
            model_path=best.model_path,
            reason="best_fit",
            quality_score=best.quality_stars,
            memory_fit=True,
            candidates_considered=len(candidates),
        )

    # No fitting candidates - select least bad option
    ranked_with_penalty = rank_candidates_with_penalty(
        filtered,
        budget,
        prefer_quality=prefer_quality,
    )

    if ranked_with_penalty:
        _, best = ranked_with_penalty[0]
        return ModelSelectionResult(
            model_id=best.model_id,
            model_path=best.model_path,
            reason="best_available",
            quality_score=best.quality_stars,
            memory_fit=False,
            candidates_considered=len(candidates),
        )

    return ModelSelectionResult(
        reason="no_suitable_model",
        candidates_considered=len(candidates),
    )


# ---------------------------------------------------------------------------
# Fallback Model Selection
# ---------------------------------------------------------------------------

def select_fallback_model(
    candidates: List[ModelCandidate],
    available_ram_gb: float,
    available_vram_gb: float = 0.0,
    *,
    min_size_gb: float = 0.0,
    excluded_prefixes: Optional[List[str]] = None,
    prefer_quality: bool = False,
    ram_fit_ratio: float = 0.92,
) -> ModelSelectionResult:
    """
    Select a fallback model for recovery scenarios.

    This is used when the primary model fails (OOM, access denied, etc.)
    and we need to find an alternative that fits in available memory.

    Args:
        candidates: List of model candidates
        available_ram_gb: Available RAM in GB
        available_vram_gb: Available VRAM in GB
        min_size_gb: Minimum model size (for quality floor)
        excluded_prefixes: Prefixes to exclude
        prefer_quality: Whether to prefer quality
        ram_fit_ratio: RAM fit ratio for filtering

    Returns:
        ModelSelectionResult with fallback model
    """
    budget = MemoryBudget(
        available_ram_gb=available_ram_gb,
        available_vram_gb=available_vram_gb,
        ram_fit_ratio=ram_fit_ratio,
    )

    return select_best_model(
        candidates,
        budget,
        prefer_quality=prefer_quality,
        min_size_gb=min_size_gb,
        excluded_prefixes=excluded_prefixes,
    )


# ---------------------------------------------------------------------------
# Model Path Utilities
# ---------------------------------------------------------------------------

def extract_repo_prefix(model_ref: Optional[str]) -> str:
    """
    Extract repository prefix from a model reference.

    For HuggingFace repos like "owner/model-name", returns "owner/".

    Args:
        model_ref: Model reference string

    Returns:
        Repository prefix or empty string
    """
    value = str(model_ref or "").strip().lower()
    if not value:
        return ""

    # HF repo ID looks like "owner/repo" (single slash, no drive letter/backslashes)
    if "\\" in value or ":" in value or value.count("/") != 1:
        return ""

    owner, _ = value.split("/", 1)
    owner = owner.strip()
    if not owner:
        return ""

    return f"{owner}/"


def is_model_access_restricted_error(message: str) -> bool:
    """
    Check if an error message indicates model access restriction.

    Args:
        message: Error message

    Returns:
        True if this is an access restricted error
    """
    lowered = str(message or "").lower()
    if not lowered:
        return False

    markers = (
        "you are trying to access a gated repo",
        "access to model",
        "is restricted",
        "cannot access gated repo",
        "401 client error",
        "401 unauthorized",
        "unauthorized",
    )
    return any(marker in lowered for marker in markers)


# ---------------------------------------------------------------------------
# Model Compatibility Checks
# ---------------------------------------------------------------------------

def is_model_compatible_with_stage(
    model_id: str,
    stage: str,
    *,
    min_quality_for_writer: float = 3.0,
    quality_stars: float = 0.0,
) -> bool:
    """
    Check if a model is compatible with a stage.

    Writer stages require higher quality models.

    Args:
        model_id: Model ID
        stage: Pipeline stage name
        min_quality_for_writer: Minimum quality for writer stages
        quality_stars: Model's quality rating

    Returns:
        True if model is compatible
    """
    from .stage_model_routing import is_writer_stage

    if is_writer_stage(stage):
        return quality_stars >= min_quality_for_writer

    # Non-writer stages accept any model
    return True


def get_model_quality_tier(quality_stars: float) -> str:
    """
    Get the quality tier for a model.

    Args:
        quality_stars: Quality rating (0-5)

    Returns:
        Tier name: "premium", "standard", or "economy"
    """
    if quality_stars >= 4.0:
        return "premium"
    elif quality_stars >= 3.0:
        return "standard"
    else:
        return "economy"


# ---------------------------------------------------------------------------
# Integration Helpers
# ---------------------------------------------------------------------------

def build_candidate_from_model_info(
    model_id: str,
    model_info: Any,
    *,
    estimate_size_fn: Optional[Callable[[str, str], float]] = None,
    estimate_ram_fn: Optional[Callable[[str, str], float]] = None,
) -> ModelCandidate:
    """
    Build a ModelCandidate from model info object.

    Args:
        model_id: Model ID
        model_info: Model info object (from model_manager)
        estimate_size_fn: Optional size estimation function
        estimate_ram_fn: Optional RAM estimation function

    Returns:
        ModelCandidate instance
    """
    model_path = str(getattr(model_info, "model_path", "") or "")
    quality_stars = float(getattr(model_info, "quality_stars", 0) or 0)
    speed_rating = float(getattr(model_info, "speed_rating", 0) or 0)
    vram_required = float(getattr(model_info, "vram_required", 0) or 0)

    # Estimate size and RAM
    if estimate_size_fn:
        estimated_size = estimate_size_fn(model_path, model_id)
    else:
        estimated_size = estimate_model_size_gb(
            model_name=model_path,
            model_id=model_id,
        )

    if estimate_ram_fn:
        required_ram = estimate_ram_fn(model_path, model_id)
    else:
        required_ram = estimate_required_ram_gb(
            model_name=model_path,
            model_id=model_id,
        )

    return ModelCandidate(
        model_id=model_id,
        model_path=model_path,
        required_ram_gb=required_ram,
        required_vram_gb=vram_required,
        quality_stars=quality_stars,
        speed_rating=speed_rating,
        estimated_size_gb=estimated_size,
    )


def get_available_model_candidates(
    available_model_ids: List[str],
    get_model_info_fn: Callable[[str], Any],
    *,
    exclude_current: Optional[str] = None,
) -> List[ModelCandidate]:
    """
    Get list of available model candidates.

    Args:
        available_model_ids: List of available model IDs
        get_model_info_fn: Function to get model info
        exclude_current: Optional model ID to exclude

    Returns:
        List of ModelCandidate instances
    """
    candidates = []

    for model_id in available_model_ids:
        if model_id == exclude_current:
            continue

        info = get_model_info_fn(model_id)
        if not info:
            continue

        candidate = build_candidate_from_model_info(model_id, info)
        candidates.append(candidate)

    return candidates
