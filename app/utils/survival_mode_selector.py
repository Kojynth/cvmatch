"""
Survival Mode Selector Module 

Centralizes survival mode detection, model selection, and quality-first
policies for low-memory scenarios. This module extracts survival mode logic
from QwenManager to provide reusable functions.

Key features:
- Survival mode detection (explicit env opt-in only)
- Stage-aware model selection (writer stages have higher quality requirements)
- Memory-aware model ranking (fits within available RAM/VRAM)
- Quality-first policies (prefer quality over speed when possible)

Survival mode is designed to allow CV generation to complete even when
system memory is constrained, by selecting smaller models that fit within
available resources while maintaining acceptable output quality.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, TYPE_CHECKING

try:
    from ..logging.safe_logger import get_safe_logger
    from ..config import DEFAULT_PII_CONFIG
    logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

# Try to import model size estimation
try:
    from .gpu_memory_budget import estimate_model_size_gb
except ImportError:
    def estimate_model_size_gb(
        model_name: Optional[str] = None,
        model_id: Optional[str] = None,
    ) -> float:
        """Fallback model size estimator."""
        return 0.0


@dataclass
class SurvivalModelCandidate:
    """A candidate model for survival mode selection."""
    model_id: str
    model_path: str
    loader: str = "transformers"
    metadata: Dict[str, Any] = field(default_factory=dict)
    required_vram_gb: float = 0.0
    required_ram_gb: float = 0.0
    quality_score: float = 0.0
    speed_rating: float = 0.0
    lowram_penalty: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "model_id": self.model_id,
            "model_path": self.model_path,
            "loader": self.loader,
            "metadata": self.metadata,
            "required_vram_gb": self.required_vram_gb,
            "required_ram_gb": self.required_ram_gb,
        }


@dataclass
class SurvivalConfig:
    """Configuration for survival mode behavior."""
    # Thresholds
    failure_threshold: int = 2
    writer_min_size_gb: float = 3.0

    # Behavior flags
    sticky: bool = True  # Keep survival mode after recovery
    ignore_selected_model: bool = True  # Override user's model selection

    # RAM fit ratios by lowram level
    ram_fit_ratio_normal: float = 1.15
    ram_fit_ratio_tight: float = 1.25
    ram_fit_ratio_critical: float = 1.15  # More aggressive for critical
    ram_fit_ratio_critical_writer: float = 1.15


# Writer stages that require higher quality models
WRITER_STAGES = frozenset({"draft", "final", "cover_letter", "cover_letter_critic"})

# Markers for tiny models that should be avoided for writer stages
TINY_MODEL_MARKERS = frozenset(("0.5b", "0.6b", "tiny"))

# Default size threshold for tiny model detection
TINY_MODEL_SIZE_THRESHOLD_GB = 1.0


def to_bool(value: Any, default: bool = False) -> bool:
    """Convert value to boolean with default fallback."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "y", "on")


def is_survival_mode_enabled(
    *,
    env_value: Optional[str] = None,
) -> bool:
    """
    Check if survival mode is enabled.

    Quality-first policy: survival is explicit env opt-in only.

    Args:
        env_value: Optional explicit env value (defaults to reading CVMATCH_SURVIVAL_MODE)

    Returns:
        True if survival mode is enabled
    """
    if env_value is None:
        env_value = os.getenv("CVMATCH_SURVIVAL_MODE")

    # Quality-first policy: survival is explicit env opt-in only.
    if env_value is None:
        return False

    return to_bool(env_value, False)


def is_writer_stage(stage: Optional[str]) -> bool:
    """
    Check if a stage is a writer stage requiring higher quality output.

    Writer stages include: draft, final, cover_letter, cover_letter_critic

    Args:
        stage: Stage name to check

    Returns:
        True if stage is a writer stage
    """
    stage_key = str(stage or "").strip().lower()
    return stage_key in WRITER_STAGES


def is_tiny_writer_candidate(
    model_id: str,
    model_path: str,
    *,
    size_threshold_gb: float = TINY_MODEL_SIZE_THRESHOLD_GB,
) -> bool:
    """
    Check if a model is too small for writer stages.

    Models under 1B parameters typically produce lower quality
    structured CV output and should be avoided for writer stages.

    Args:
        model_id: Model identifier
        model_path: Model path
        size_threshold_gb: Size threshold below which model is "tiny"

    Returns:
        True if model is considered too small for writer stages
    """
    try:
        size_hint = float(
            estimate_model_size_gb(model_name=model_path, model_id=model_id)
        )
    except Exception:
        size_hint = 0.0

    if size_hint > 0 and size_hint < size_threshold_gb:
        return True

    haystack = f"{model_id or ''} {model_path or ''}".lower()
    return any(token in haystack for token in TINY_MODEL_MARKERS)


def get_survival_config(
    *,
    custom_parameters: Optional[Dict[str, Any]] = None,
) -> SurvivalConfig:
    """
    Build survival configuration from custom parameters and environment.

    Args:
        custom_parameters: Optional custom configuration dict

    Returns:
        SurvivalConfig with resolved values
    """
    custom = custom_parameters or {}
    config = SurvivalConfig()

    # Failure threshold
    try:
        if "survival_failure_threshold" in custom:
            config.failure_threshold = max(1, int(custom.get("survival_failure_threshold")))
    except Exception:
        pass
    raw_env = os.getenv("CVMATCH_SURVIVAL_FAILURE_THRESHOLD")
    if raw_env is not None:
        try:
            config.failure_threshold = max(1, int(raw_env))
        except Exception:
            pass

    # Writer min size
    try:
        if "survival_writer_min_size_b" in custom:
            config.writer_min_size_gb = float(custom.get("survival_writer_min_size_b"))
    except Exception:
        pass
    raw_env = os.getenv("CVMATCH_SURVIVAL_WRITER_MIN_SIZE_B")
    if raw_env is not None:
        try:
            config.writer_min_size_gb = float(raw_env)
        except Exception:
            pass
    config.writer_min_size_gb = max(0.0, config.writer_min_size_gb)

    # Sticky flag
    if "survival_sticky" in custom:
        config.sticky = to_bool(custom.get("survival_sticky"), True)
    raw_env = os.getenv("CVMATCH_SURVIVAL_STICKY")
    if raw_env is not None:
        config.sticky = to_bool(raw_env, True)

    # Ignore selected model flag
    if "survival_ignore_selected_model" in custom:
        config.ignore_selected_model = to_bool(custom.get("survival_ignore_selected_model"), True)
    raw_env = os.getenv("CVMATCH_SURVIVAL_IGNORE_SELECTED_MODEL")
    if raw_env is not None:
        config.ignore_selected_model = to_bool(raw_env, True)

    return config


def get_ram_fit_ratio(
    *,
    lowram_level: str,
    is_writer_stage: bool = False,
    config: Optional[SurvivalConfig] = None,
) -> float:
    """
    Get RAM fit ratio based on lowram level and stage type.

    The fit ratio determines how much larger than available RAM
    a model can be while still being considered a valid candidate.
    A ratio of 1.15 means the model's required RAM can be up to
    15% more than available RAM.

    Args:
        lowram_level: Current lowram profile level ("normal", "tight", "critical")
        is_writer_stage: Whether this is a writer stage
        config: Optional survival config (uses defaults if None)

    Returns:
        RAM fit ratio for model selection
    """
    if config is None:
        config = SurvivalConfig()

    if lowram_level == "critical":
        if is_writer_stage:
            return config.ram_fit_ratio_critical_writer
        return config.ram_fit_ratio_critical
    elif lowram_level == "tight":
        return config.ram_fit_ratio_tight
    else:
        return config.ram_fit_ratio_normal


def pick_survival_model(
    *,
    available_ram_gb: float,
    available_vram_gb: float,
    model_candidates: List[Dict[str, Any]],
    stage_name: str = "",
    lowram_level: str = "normal",
    config: Optional[SurvivalConfig] = None,
    estimate_ram_fn: Optional[Callable[[str, str], float]] = None,
) -> Optional[SurvivalModelCandidate]:
    """
    Select the best model for survival mode given memory constraints.

    This function implements a quality-first model selection strategy:
    1. Filter out models that don't fit in available VRAM
    2. Filter out tiny models for writer stages
    3. Rank remaining models by quality, penalizing those above RAM threshold
    4. Select highest quality model that fits
    5. If no fitting model, fall back to smallest memory footprint

    Args:
        available_ram_gb: Available system RAM in GB
        available_vram_gb: Available GPU VRAM in GB
        model_candidates: List of model info dicts from model_manager
        stage_name: Current pipeline stage name
        lowram_level: Current lowram profile level
        config: Optional survival configuration
        estimate_ram_fn: Optional function to estimate RAM requirements

    Returns:
        Selected model candidate, or None if no suitable model found
    """
    if config is None:
        config = SurvivalConfig()

    writer_stage = is_writer_stage(stage_name)
    writer_floor_gb = config.writer_min_size_gb if writer_stage else 0.0

    fitting_ranked: List[Tuple[float, float, float, float, SurvivalModelCandidate]] = []
    all_ranked: List[Tuple[float, float, float, float, SurvivalModelCandidate]] = []

    for model_info in model_candidates:
        model_id = str(model_info.get("model_id") or model_info.get("id") or "")
        model_path = str(model_info.get("model_path") or model_info.get("path") or "")

        if not model_id:
            continue

        required_vram = float(model_info.get("vram_required") or model_info.get("required_vram") or 0)

        # Estimate RAM requirement
        if estimate_ram_fn:
            required_ram = estimate_ram_fn(model_path, model_id)
        else:
            # Simple estimate: 1.5x VRAM or base 2GB
            required_ram = max(2.0, required_vram * 1.5)

        # Skip tiny models for writer stages
        if writer_stage and is_tiny_writer_candidate(model_id, model_path):
            continue

        # Skip models below writer floor
        if writer_stage and writer_floor_gb > 0:
            try:
                model_size_hint = float(
                    estimate_model_size_gb(model_name=model_path, model_id=model_id)
                )
            except Exception:
                model_size_hint = 0.0
            if model_size_hint > 0 and model_size_hint < writer_floor_gb:
                continue

        # Skip models that clearly exceed VRAM
        if available_vram_gb > 0 and required_vram > (available_vram_gb + 0.5):
            # Keep CPU-compatible models (required_vram == 0)
            if required_vram > 0:
                continue

        metadata = model_info.get("metadata") or {}
        loader = model_info.get("loader") or "transformers"
        quality = float(model_info.get("quality_stars") or model_info.get("quality") or 0)
        speed = float(model_info.get("speed_rating") or model_info.get("speed") or 0)

        # Calculate lowram penalty
        lowram_penalty = 0.0
        if available_ram_gb > 0 and required_ram > available_ram_gb:
            lowram_penalty = required_ram - available_ram_gb

        # Penalize tiny models even for non-writer stages
        if not writer_stage and is_tiny_writer_candidate(model_id, model_path):
            lowram_penalty += 1.5

        candidate = SurvivalModelCandidate(
            model_id=model_id,
            model_path=model_path,
            loader=loader,
            metadata=metadata,
            required_vram_gb=required_vram,
            required_ram_gb=required_ram,
            quality_score=quality,
            speed_rating=speed,
            lowram_penalty=lowram_penalty,
        )

        all_ranked.append((required_vram, required_ram, lowram_penalty, quality, candidate))

        # Check if model fits within RAM constraints
        ram_fit_ratio = get_ram_fit_ratio(
            lowram_level=lowram_level,
            is_writer_stage=writer_stage,
            config=config,
        )
        ram_fits = available_ram_gb <= 0 or required_ram <= (available_ram_gb * ram_fit_ratio)

        if not ram_fits:
            continue

        # Add to fitting candidates (sorted by quality first, then penalties)
        fitting_ranked.append((
            -quality,  # Negative for descending sort
            lowram_penalty,
            required_vram,
            -speed,  # Negative for descending sort
            candidate,
        ))

    # Select best fitting model
    if fitting_ranked:
        fitting_ranked.sort(key=lambda item: (item[0], item[1], item[2], item[3]))
        return fitting_ranked[0][4]

    # Fallback: smallest memory footprint
    if not all_ranked:
        return None

    all_ranked.sort(key=lambda item: (item[0], item[1], item[2], -item[3]))
    return all_ranked[0][4]


def should_apply_survival_override(
    *,
    lowram_level: str,
    stage_name: str = "",
    current_model_id: str = "",
    config: Optional[SurvivalConfig] = None,
) -> bool:
    """
    Determine if survival mode override should be applied.

    Quality-first guard: in tight low RAM, keep the selected model as-is.

    Args:
        lowram_level: Current lowram profile level
        stage_name: Current pipeline stage
        current_model_id: Currently selected model ID
        config: Optional survival configuration

    Returns:
        True if override should be applied
    """
    if config is None:
        config = SurvivalConfig()

    if not config.ignore_selected_model:
        logger.info(
            "[SURVIVAL] Override disabled by config/env for stage '%s'; "
            "keeping selected model '%s'.",
            stage_name or "unknown",
            current_model_id or "unknown",
        )
        return False

    # Quality-first guard: in tight low RAM, keep the selected model as-is.
    if lowram_level == "tight":
        logger.info(
            "[SURVIVAL] Stage '%s' with lowram=tight: preserving model '%s'.",
            stage_name or "unknown",
            current_model_id or "unknown",
        )
        return False

    return True


def get_survival_gpu_budget_cap_gb(
    *,
    total_vram_gb: float,
    lowram_level: str = "normal",
) -> float:
    """
    Get the GPU budget cap for survival mode based on VRAM and RAM status.

    This determines the maximum VRAM that should be used for model loading
    in survival mode, leaving headroom for generation.

    Args:
        total_vram_gb: Total GPU VRAM in GB
        lowram_level: Current lowram profile level

    Returns:
        Maximum VRAM to use in GB
    """
    total_vram = float(total_vram_gb or 0.0)

    if total_vram <= 0:
        return 3.5 if lowram_level == "critical" else 4.0

    if total_vram <= 6.5:
        return 3.5 if lowram_level == "critical" else 4.0
    elif total_vram <= 8.5:
        return 4.5 if lowram_level in {"tight", "critical"} else 5.0
    elif total_vram <= 12.0:
        return 6.5
    else:
        return min(8.0, total_vram * 0.7)


def is_memory_pressure_failure(reason: str) -> bool:
    """
    Check if a failure reason indicates memory pressure.

    Used to determine if survival mode should be triggered after a failure.

    Args:
        reason: Failure reason string

    Returns:
        True if failure is memory-related
    """
    lowered = str(reason or "").lower()
    if not lowered:
        return False

    markers = (
        "memoryerror",
        "out of memory",
        "cuda out of memory",
        "fichier de pagination",
        "pagefile",
        "os error 1455",
        "mémoire système insuffisante",
        "memoire systeme insuffisante",
        "commit windows insuffisant",
        "insufficient windows commit memory",
        "commit memory",
        "lowram",
        "vram insuffisante",
        "oom",
    )
    return any(marker in lowered for marker in markers)


def format_survival_mode_log(
    *,
    action: str,
    stage_name: str = "",
    current_model_id: str = "",
    selected_model_id: str = "",
    lowram_level: str = "normal",
    available_ram_gb: float = 0.0,
    available_vram_gb: float = 0.0,
) -> str:
    """
    Format a survival mode log message.

    Args:
        action: Action being taken (e.g., "override", "skip", "apply")
        stage_name: Current pipeline stage
        current_model_id: Currently selected model ID
        selected_model_id: Model ID being switched to
        lowram_level: Current lowram profile level
        available_ram_gb: Available system RAM
        available_vram_gb: Available GPU VRAM

    Returns:
        Formatted log message
    """
    parts = [f"[SURVIVAL] {action}"]

    if stage_name:
        parts.append(f"stage={stage_name}")

    if current_model_id:
        parts.append(f"current={current_model_id}")

    if selected_model_id:
        parts.append(f"selected={selected_model_id}")

    if lowram_level != "normal":
        parts.append(f"lowram={lowram_level}")

    if available_ram_gb > 0:
        parts.append(f"ram={available_ram_gb:.1f}GB")

    if available_vram_gb > 0:
        parts.append(f"vram={available_vram_gb:.1f}GB")

    return " ".join(parts)


class SurvivalModeTracker:
    """
    Tracks survival mode state across the application lifecycle.

    This class manages consecutive failure counting, survival mode
    activation, and recovery tracking.
    """

    def __init__(
        self,
        *,
        config: Optional[SurvivalConfig] = None,
    ):
        """
        Initialize survival mode tracker.

        Args:
            config: Optional survival configuration
        """
        self._config = config or SurvivalConfig()
        self._consecutive_failures: int = 0
        self._survival_mode_forced: bool = False
        self._survival_last_reason: str = ""

    def record_failure(self, reason: str) -> None:
        """
        Record a failure event.

        Args:
            reason: Failure reason string
        """
        self._consecutive_failures += 1
        logger.warning(
            "Failure recorded (%s consecutive): %s",
            self._consecutive_failures,
            str(reason or "")[:240],
        )

        # Check if we should force survival mode
        if self._consecutive_failures >= self._config.failure_threshold:
            if is_memory_pressure_failure(reason):
                self._survival_mode_forced = True
                self._survival_last_reason = reason

    def record_success(self, reason: str = "") -> None:
        """
        Record a success event.

        Args:
            reason: Success reason string
        """
        self._consecutive_failures = 0

        if not self._config.sticky:
            self._survival_mode_forced = False
            self._survival_last_reason = ""

        if reason:
            logger.info("Reset failure counter after success: %s", reason)

    @property
    def consecutive_failures(self) -> int:
        """Get current consecutive failure count."""
        return self._consecutive_failures

    @property
    def is_forced(self) -> bool:
        """Check if survival mode has been forced by failures."""
        return self._survival_mode_forced

    @property
    def last_reason(self) -> str:
        """Get the last failure reason that triggered survival mode."""
        return self._survival_last_reason

    def reset(self) -> None:
        """Reset all tracking state."""
        self._consecutive_failures = 0
        self._survival_mode_forced = False
        self._survival_last_reason = ""
