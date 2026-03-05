"""
Stage Model Routing Module

Per-stage model routing and selection logic.
This module extracts stage-aware model selection from CVGenerationWorker
to provide consistent model routing across the pipeline.

Key features:
- Stage-to-model mapping
- Writer stage detection
- Model tier selection by stage
- Extractor vs writer model preferences
- Environment and custom parameter integration

These functions enable intelligent model selection without depending on
worker state, making them suitable for both in-process and subprocess
pipeline stages.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

try:
    from ..logging.safe_logger import get_safe_logger
    from ..config import DEFAULT_PII_CONFIG
    logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Writer stages require higher quality models
WRITER_STAGES: Set[str] = frozenset({
    "draft",
    "final",
    "cover_letter",
    "cover_letter_critic",
})

# Extractor stages can use smaller, faster models
EXTRACTOR_STAGES: Set[str] = frozenset({
    "offer_keywords",
    "profile_extraction",
})

# Critic stages - moderate quality requirements
CRITIC_STAGES: Set[str] = frozenset({
    "critic",
    "cv_critic",
})

# Default model preferences
DEFAULT_EXTRACTOR_MODEL = "qwen2-1.5b"
DEFAULT_WRITER_MODEL = "qwen2.5-7b"

# Environment variable names
ENV_STAGE_MODEL_ROUTING = "CVMATCH_ENABLE_STAGE_MODEL_ROUTING"
ENV_KEEP_SELECTED_MODEL = "CVMATCH_KEEP_SELECTED_STAGE_MODEL"
ENV_PREFER_SMALL_EXTRACTOR = "CVMATCH_PREFER_SMALL_EXTRACTOR_MODEL"


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class StageModelConfig:
    """Configuration for stage model routing."""
    enabled: bool = True
    keep_selected_model: bool = True
    prefer_small_extractor: bool = False
    extractor_model_id: str = DEFAULT_EXTRACTOR_MODEL
    writer_model_id: str = ""  # Empty means use current/default
    lowram_level: str = "normal"

    @classmethod
    def from_env_and_custom(
        cls,
        custom_parameters: Optional[Dict[str, Any]] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> "StageModelConfig":
        """
        Build configuration from environment and custom parameters.

        Args:
            custom_parameters: Custom parameters dictionary
            env: Environment variables (defaults to os.environ)

        Returns:
            Configured StageModelConfig
        """
        custom = custom_parameters or {}
        env_dict = env if env is not None else dict(os.environ)

        def _to_bool(value: Any, default: bool = False) -> bool:
            if value is None:
                return default
            if isinstance(value, bool):
                return value
            return str(value).strip().lower() in ("1", "true", "yes", "y", "on")

        # Check if routing is enabled
        enabled = _to_bool(env_dict.get(ENV_STAGE_MODEL_ROUTING), True)

        # Keep selected model preference
        keep_selected = _to_bool(custom.get("keep_selected_stage_model"), True)
        env_keep = env_dict.get(ENV_KEEP_SELECTED_MODEL)
        if env_keep is not None:
            keep_selected = _to_bool(env_keep, True)

        # Prefer small extractor
        prefer_small = _to_bool(custom.get("prefer_small_extractor_model"), False)
        env_small = env_dict.get(ENV_PREFER_SMALL_EXTRACTOR)
        if env_small is not None:
            prefer_small = _to_bool(env_small, False)

        # Extractor model ID
        extractor_model = str(
            custom.get("extractor_model_id")
            or custom.get("pipeline_extractor_model_id")
            or DEFAULT_EXTRACTOR_MODEL
        ).strip()

        # Writer model ID
        writer_model = str(
            custom.get("writer_model_id")
            or custom.get("pipeline_writer_model_id")
            or ""
        ).strip()

        return cls(
            enabled=enabled,
            keep_selected_model=keep_selected,
            prefer_small_extractor=prefer_small,
            extractor_model_id=extractor_model,
            writer_model_id=writer_model,
        )


@dataclass
class StageModelResolution:
    """Result of stage model resolution."""
    model_id: Optional[str] = None
    reason: str = ""
    stage: str = ""
    is_explicit: bool = False
    requires_switch: bool = False


# ---------------------------------------------------------------------------
# Stage Classification
# ---------------------------------------------------------------------------

def is_writer_stage(stage: str) -> bool:
    """
    Check if a stage is a writer stage (requires higher quality model).

    Args:
        stage: Pipeline stage name

    Returns:
        True if this is a writer stage
    """
    return str(stage or "").strip().lower() in WRITER_STAGES


def is_extractor_stage(stage: str) -> bool:
    """
    Check if a stage is an extractor stage (can use smaller model).

    Args:
        stage: Pipeline stage name

    Returns:
        True if this is an extractor stage
    """
    return str(stage or "").strip().lower() in EXTRACTOR_STAGES


def is_critic_stage(stage: str) -> bool:
    """
    Check if a stage is a critic stage.

    Args:
        stage: Pipeline stage name

    Returns:
        True if this is a critic stage
    """
    return str(stage or "").strip().lower() in CRITIC_STAGES


def get_stage_model_tier(stage: str) -> str:
    """
    Get the model tier recommendation for a stage.

    Args:
        stage: Pipeline stage name

    Returns:
        Tier name: "writer", "extractor", or "critic"
    """
    stage_key = str(stage or "").strip().lower()
    if stage_key in WRITER_STAGES:
        return "writer"
    if stage_key in EXTRACTOR_STAGES:
        return "extractor"
    if stage_key in CRITIC_STAGES:
        return "critic"
    return "writer"  # Default to writer tier for unknown stages


# ---------------------------------------------------------------------------
# Model Resolution
# ---------------------------------------------------------------------------

def resolve_stage_model_override(
    stage: str,
    *,
    config: Optional[StageModelConfig] = None,
    custom_parameters: Optional[Dict[str, Any]] = None,
    current_model_id: str = "",
    validate_model_fn: Optional[Callable[[str], bool]] = None,
) -> StageModelResolution:
    """
    Resolve the model override for a pipeline stage.

    This is the main entry point for stage model routing. It determines
    which model should be used for a given stage based on:
    1. Explicit stage model configuration
    2. Stage tier (extractor vs writer)
    3. Current model and keep_selected preference
    4. Memory pressure level

    Args:
        stage: Pipeline stage name
        config: Stage model configuration
        custom_parameters: Additional custom parameters
        current_model_id: Currently loaded model ID
        validate_model_fn: Optional function to validate model exists

    Returns:
        StageModelResolution with the resolved model
    """
    stage_key = str(stage or "").strip().lower()
    if not stage_key:
        return StageModelResolution(reason="empty_stage")

    # Build config if not provided
    if config is None:
        config = StageModelConfig.from_env_and_custom(custom_parameters)

    if not config.enabled:
        return StageModelResolution(
            reason="routing_disabled",
            stage=stage_key,
        )

    custom = custom_parameters or {}

    # Check for explicit stage model override
    explicit_model = (
        custom.get(f"stage_model_{stage_key}")
        or custom.get(f"stage_model_id_{stage_key}")
    )

    if explicit_model:
        candidate = str(explicit_model).strip()
        if candidate:
            if validate_model_fn and not validate_model_fn(candidate):
                logger.warning(
                    "Unknown stage model override '%s' for stage '%s'.",
                    candidate,
                    stage_key,
                )
                return StageModelResolution(
                    reason="explicit_invalid",
                    stage=stage_key,
                )
            return StageModelResolution(
                model_id=candidate,
                reason="explicit_override",
                stage=stage_key,
                is_explicit=True,
                requires_switch=candidate != current_model_id,
            )

    # Handle extractor stages
    if stage_key in {"offer_keywords", "critic"}:
        should_use_extractor = (
            config.lowram_level == "critical"
            or config.prefer_small_extractor
        )

        if config.keep_selected_model and current_model_id and not should_use_extractor:
            return StageModelResolution(
                model_id=current_model_id,
                reason="keep_selected",
                stage=stage_key,
                requires_switch=False,
            )

        candidate = config.extractor_model_id or current_model_id
        if candidate:
            if validate_model_fn and not validate_model_fn(candidate):
                return StageModelResolution(
                    reason="extractor_invalid",
                    stage=stage_key,
                )
            return StageModelResolution(
                model_id=candidate,
                reason="extractor_stage",
                stage=stage_key,
                requires_switch=candidate != current_model_id,
            )

    # Handle writer stages
    if stage_key in WRITER_STAGES:
        candidate = config.writer_model_id or current_model_id
        if candidate:
            if validate_model_fn and not validate_model_fn(candidate):
                return StageModelResolution(
                    reason="writer_invalid",
                    stage=stage_key,
                )
            return StageModelResolution(
                model_id=candidate,
                reason="writer_stage",
                stage=stage_key,
                requires_switch=candidate != current_model_id,
            )

    # No override needed
    return StageModelResolution(
        reason="no_override",
        stage=stage_key,
    )


# ---------------------------------------------------------------------------
# Memory-Aware Routing
# ---------------------------------------------------------------------------

def get_min_model_size_for_stage(stage: str) -> float:
    """
    Get minimum model size in GB for a stage.

    Args:
        stage: Pipeline stage name

    Returns:
        Minimum model size in GB
    """
    if is_writer_stage(stage):
        return 1.5
    return 1.0


def get_ram_fit_ratio_for_stage(stage: str) -> float:
    """
    Get RAM fit ratio for a stage.

    Writer stages need more headroom for quality.

    Args:
        stage: Pipeline stage name

    Returns:
        RAM fit ratio (model must fit within available_ram * ratio)
    """
    if is_writer_stage(stage):
        return 1.25
    return 1.10


def should_use_quality_preference(stage: str) -> bool:
    """
    Determine if quality should be preferred over speed for a stage.

    Args:
        stage: Pipeline stage name

    Returns:
        True if quality should be prioritized
    """
    return is_writer_stage(stage) or is_critic_stage(stage)


# ---------------------------------------------------------------------------
# Stage Model Application
# ---------------------------------------------------------------------------

@dataclass
class ModelSwitchResult:
    """Result of a model switch operation."""
    success: bool
    previous_model_id: str = ""
    new_model_id: str = ""
    switched: bool = False
    error: Optional[str] = None


def should_switch_model(
    resolution: StageModelResolution,
    current_model_id: str,
) -> bool:
    """
    Determine if a model switch is needed.

    Args:
        resolution: Stage model resolution
        current_model_id: Currently loaded model ID

    Returns:
        True if model switch is needed
    """
    if not resolution.model_id:
        return False
    return resolution.model_id != current_model_id


def format_stage_model_log(
    stage: str,
    previous_model: str,
    new_model: str,
) -> str:
    """
    Format a log message for stage model switch.

    Args:
        stage: Pipeline stage name
        previous_model: Previous model ID
        new_model: New model ID

    Returns:
        Formatted log message
    """
    prev = previous_model or "auto"
    return f"[MODEL] Stage {stage}: {prev} -> {new_model}"


# ---------------------------------------------------------------------------
# Stage Runtime Tracking
# ---------------------------------------------------------------------------

@dataclass
class StageRuntimeContext:
    """Runtime context for stage execution."""
    stage: str
    model_id: str = ""
    is_writer: bool = False
    is_extractor: bool = False
    model_tier: str = "writer"
    quality_preferred: bool = True
    min_model_size_gb: float = 1.0
    ram_fit_ratio: float = 1.10

    @classmethod
    def for_stage(cls, stage: str, model_id: str = "") -> "StageRuntimeContext":
        """
        Create runtime context for a stage.

        Args:
            stage: Pipeline stage name
            model_id: Optional model ID

        Returns:
            Configured StageRuntimeContext
        """
        stage_key = str(stage or "").strip().lower()
        return cls(
            stage=stage_key,
            model_id=model_id,
            is_writer=is_writer_stage(stage_key),
            is_extractor=is_extractor_stage(stage_key),
            model_tier=get_stage_model_tier(stage_key),
            quality_preferred=should_use_quality_preference(stage_key),
            min_model_size_gb=get_min_model_size_for_stage(stage_key),
            ram_fit_ratio=get_ram_fit_ratio_for_stage(stage_key),
        )


# ---------------------------------------------------------------------------
# Utility Functions
# ---------------------------------------------------------------------------

def parse_bool_env(
    env_name: str,
    default: bool = False,
    env: Optional[Dict[str, str]] = None,
) -> bool:
    """
    Parse a boolean environment variable.

    Args:
        env_name: Environment variable name
        default: Default value if not set
        env: Environment dict (defaults to os.environ)

    Returns:
        Boolean value
    """
    env_dict = env if env is not None else dict(os.environ)
    value = env_dict.get(env_name)
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "y", "on", "auto")


def is_stage_model_routing_enabled(
    env: Optional[Dict[str, str]] = None,
) -> bool:
    """
    Check if stage model routing is enabled.

    Args:
        env: Environment dict (defaults to os.environ)

    Returns:
        True if routing is enabled
    """
    return parse_bool_env(ENV_STAGE_MODEL_ROUTING, default=True, env=env)


def get_stage_model_env_overrides(
    env: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """
    Get all stage model environment overrides.

    Args:
        env: Environment dict (defaults to os.environ)

    Returns:
        Dictionary of stage to model ID overrides
    """
    env_dict = env if env is not None else dict(os.environ)
    overrides = {}

    # Look for CVMATCH_STAGE_MODEL_<STAGE> patterns
    prefix = "CVMATCH_STAGE_MODEL_"
    for key, value in env_dict.items():
        if key.upper().startswith(prefix):
            stage = key[len(prefix):].lower()
            if stage and value:
                overrides[stage] = value

    return overrides
