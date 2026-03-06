"""
Generation Role Parameters Module 

Centralized generation parameter configuration by role/stage.
This module extracts role-based parameter logic from QwenManager
to provide consistent generation settings across the pipeline.

Key features:
- Role-based parameter definitions (extractor, critic, generator)
- Stage-to-role mapping
- Parameter validation and clamping
- Override application

These settings control LLM generation behavior without depending on
worker state, making them suitable for both in-process and subprocess
pipeline stages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

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

@dataclass(frozen=True)
class GenerationParams:
    """Immutable generation parameters for LLM inference."""
    temperature: float = 0.2
    top_p: float = 0.9
    top_k: int = 50
    max_input_tokens: int = 2400
    max_new_tokens: int = 1024
    max_total_tokens: int = 4096
    repetition_penalty: float = 1.05
    do_sample: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for LLM API calls."""
        return {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "top_k": self.top_k,
            "max_input_tokens": self.max_input_tokens,
            "max_new_tokens": self.max_new_tokens,
            "max_total_tokens": self.max_total_tokens,
            "repetition_penalty": self.repetition_penalty,
            "do_sample": self.do_sample,
        }


@dataclass
class RoleParamsConfig:
    """Configuration for role-based generation parameters."""
    extractor: GenerationParams = field(default_factory=lambda: ROLE_PARAMS_EXTRACTOR)
    critic: GenerationParams = field(default_factory=lambda: ROLE_PARAMS_CRITIC)
    offer_critic: GenerationParams = field(default_factory=lambda: ROLE_PARAMS_OFFER_CRITIC)
    generator: GenerationParams = field(default_factory=lambda: ROLE_PARAMS_GENERATOR)
    cover_letter: GenerationParams = field(default_factory=lambda: ROLE_PARAMS_COVER_LETTER)

    def get_params(self, role: str) -> GenerationParams:
        """Get parameters for a specific role."""
        role_key = str(role or "").strip().lower()
        if role_key in ("extractor", "offer_keywords"):
            return self.extractor
        elif role_key in ("critic", "cv_critic"):
            return self.critic
        elif role_key in ("offer_critic", "cover_letter_critic"):
            return self.offer_critic
        elif role_key in ("cover_letter", "letter"):
            return self.cover_letter
        else:
            return self.generator


# ---------------------------------------------------------------------------
# Default Role Parameters
# ---------------------------------------------------------------------------

ROLE_PARAMS_EXTRACTOR = GenerationParams(
    temperature=0.0,
    top_p=0.9,
    top_k=50,
    max_input_tokens=3000,
    max_new_tokens=700,
    max_total_tokens=3700,
    repetition_penalty=1.05,
    do_sample=False,  # Deterministic for extraction
)

ROLE_PARAMS_CRITIC = GenerationParams(
    temperature=0.2,
    top_p=0.9,
    top_k=50,
    max_input_tokens=2800,
    max_new_tokens=900,
    max_total_tokens=3700,
    repetition_penalty=1.05,
    do_sample=True,
)

ROLE_PARAMS_OFFER_CRITIC = GenerationParams(
    temperature=0.1,
    top_p=0.9,
    top_k=50,
    max_input_tokens=2200,
    max_new_tokens=600,
    max_total_tokens=2800,
    repetition_penalty=1.05,
    do_sample=True,
)

ROLE_PARAMS_GENERATOR = GenerationParams(
    temperature=0.46,
    top_p=0.92,
    top_k=60,
    max_input_tokens=2600,
    max_new_tokens=2200,
    max_total_tokens=5200,
    repetition_penalty=1.06,
    do_sample=True,
)

ROLE_PARAMS_COVER_LETTER = GenerationParams(
    temperature=0.46,
    top_p=0.92,
    top_k=60,
    max_input_tokens=2600,
    max_new_tokens=1200,
    max_total_tokens=5200,
    repetition_penalty=1.08,
    do_sample=True,
)

# Default role parameters dictionary (for compatibility)
DEFAULT_ROLE_PARAMS: Dict[str, Dict[str, Any]] = {
    "extractor": ROLE_PARAMS_EXTRACTOR.to_dict(),
    "critic": ROLE_PARAMS_CRITIC.to_dict(),
    "offer_critic": ROLE_PARAMS_OFFER_CRITIC.to_dict(),
    "generator": ROLE_PARAMS_GENERATOR.to_dict(),
    "cover_letter": ROLE_PARAMS_COVER_LETTER.to_dict(),
}


# ---------------------------------------------------------------------------
# Stage-to-Role Mapping
# ---------------------------------------------------------------------------

STAGE_TO_ROLE_MAP: Dict[str, str] = {
    # Extractor stages
    "offer_keywords": "extractor",
    "profile_extraction": "extractor",
    # Critic stages
    "critic": "critic",
    "cv_critic": "critic",
    "cover_letter_critic": "offer_critic",
    # Generator stages
    "draft": "generator",
    "final": "generator",
    "cv_json": "generator",
    # Cover letter stages
    "cover_letter": "cover_letter",
    "letter": "cover_letter",
}


def get_role_for_stage(stage: str) -> str:
    """
    Map a pipeline stage to its generation role.

    Args:
        stage: Pipeline stage name

    Returns:
        Role name (extractor, critic, generator, etc.)
    """
    stage_key = str(stage or "").strip().lower()
    return STAGE_TO_ROLE_MAP.get(stage_key, "generator")


def get_params_for_stage(
    stage: str,
    *,
    config: Optional[RoleParamsConfig] = None,
) -> GenerationParams:
    """
    Get generation parameters for a pipeline stage.

    Args:
        stage: Pipeline stage name
        config: Optional custom configuration

    Returns:
        GenerationParams for the stage
    """
    role = get_role_for_stage(stage)
    cfg = config or RoleParamsConfig()
    return cfg.get_params(role)


# ---------------------------------------------------------------------------
# Parameter Validation and Clamping
# ---------------------------------------------------------------------------

def clamp_temperature(value: Any, min_val: float = 0.0, max_val: float = 2.0) -> float:
    """
    Clamp temperature value to valid range.

    Args:
        value: Temperature value to clamp
        min_val: Minimum allowed value
        max_val: Maximum allowed value

    Returns:
        Clamped temperature value
    """
    try:
        temp = float(value)
    except (ValueError, TypeError):
        temp = 0.2  # Default
    return max(min_val, min(max_val, temp))


def clamp_top_p(value: Any, min_val: float = 0.1, max_val: float = 0.99) -> float:
    """
    Clamp top_p value to valid range.

    Args:
        value: top_p value to clamp
        min_val: Minimum allowed value
        max_val: Maximum allowed value

    Returns:
        Clamped top_p value
    """
    try:
        top_p = float(value)
    except (ValueError, TypeError):
        top_p = 0.9  # Default
    return max(min_val, min(max_val, top_p))


def clamp_top_k(value: Any, min_val: int = 1, max_val: int = 100) -> int:
    """
    Clamp top_k value to valid range.

    Args:
        value: top_k value to clamp
        min_val: Minimum allowed value
        max_val: Maximum allowed value

    Returns:
        Clamped top_k value
    """
    try:
        top_k = int(value)
    except (ValueError, TypeError):
        top_k = 50  # Default
    return max(min_val, min(max_val, top_k))


def clamp_max_tokens(
    value: Any,
    min_val: int = 64,
    max_val: int = 8192,
    default: int = 1024,
) -> int:
    """
    Clamp max tokens value to valid range.

    Args:
        value: max tokens value to clamp
        min_val: Minimum allowed value
        max_val: Maximum allowed value
        default: Default value if invalid

    Returns:
        Clamped max tokens value
    """
    try:
        tokens = int(value)
    except (ValueError, TypeError):
        tokens = default
    return max(min_val, min(max_val, tokens))


def clamp_repetition_penalty(
    value: Any,
    min_val: float = 1.0,
    max_val: float = 2.0,
) -> float:
    """
    Clamp repetition penalty to valid range.

    Args:
        value: Repetition penalty value to clamp
        min_val: Minimum allowed value
        max_val: Maximum allowed value

    Returns:
        Clamped repetition penalty value
    """
    try:
        penalty = float(value)
    except (ValueError, TypeError):
        penalty = 1.05  # Default
    return max(min_val, min(max_val, penalty))


# ---------------------------------------------------------------------------
# Override Application
# ---------------------------------------------------------------------------

def apply_overrides(
    base_params: GenerationParams,
    overrides: Optional[Dict[str, Any]] = None,
) -> GenerationParams:
    """
    Apply override values to base generation parameters.

    Args:
        base_params: Base GenerationParams to modify
        overrides: Dictionary of override values

    Returns:
        New GenerationParams with overrides applied
    """
    if not overrides:
        return base_params

    return GenerationParams(
        temperature=clamp_temperature(
            overrides.get("temperature", base_params.temperature)
        ),
        top_p=clamp_top_p(
            overrides.get("top_p", base_params.top_p)
        ),
        top_k=clamp_top_k(
            overrides.get("top_k", base_params.top_k)
        ),
        max_input_tokens=clamp_max_tokens(
            overrides.get("max_input_tokens", base_params.max_input_tokens),
            default=base_params.max_input_tokens,
        ),
        max_new_tokens=clamp_max_tokens(
            overrides.get("max_new_tokens", base_params.max_new_tokens),
            default=base_params.max_new_tokens,
        ),
        max_total_tokens=clamp_max_tokens(
            overrides.get("max_total_tokens", base_params.max_total_tokens),
            max_val=16384,
            default=base_params.max_total_tokens,
        ),
        repetition_penalty=clamp_repetition_penalty(
            overrides.get("repetition_penalty", base_params.repetition_penalty)
        ),
        do_sample=bool(
            overrides.get("do_sample", base_params.do_sample)
        ) if "do_sample" in overrides else (
            clamp_temperature(overrides.get("temperature", base_params.temperature)) > 0.0
        ),
    )


def get_generation_kwargs(
    stage: str,
    *,
    overrides: Optional[Dict[str, Any]] = None,
    config: Optional[RoleParamsConfig] = None,
) -> Dict[str, Any]:
    """
    Get generation kwargs for LLM API calls.

    This is the main entry point for getting generation parameters
    for a pipeline stage with optional overrides.

    Args:
        stage: Pipeline stage name
        overrides: Optional override values
        config: Optional custom configuration

    Returns:
        Dictionary of generation kwargs for LLM API
    """
    base_params = get_params_for_stage(stage, config=config)
    final_params = apply_overrides(base_params, overrides)

    return {
        "max_new_tokens": final_params.max_new_tokens,
        "temperature": final_params.temperature,
        "top_p": final_params.top_p,
        "top_k": final_params.top_k,
        "do_sample": final_params.do_sample,
        "repetition_penalty": final_params.repetition_penalty,
    }


# ---------------------------------------------------------------------------
# Slow Mode / Memory Constrained Settings
# ---------------------------------------------------------------------------

def get_slow_mode_caps(
    base_params: GenerationParams,
    *,
    memory_constrained: bool = False,
    strict_json: bool = False,
) -> GenerationParams:
    """
    Apply caps for slow mode or memory constrained scenarios.

    Args:
        base_params: Base parameters
        memory_constrained: Whether memory is constrained
        strict_json: Whether strict JSON mode is active

    Returns:
        GenerationParams with appropriate caps applied
    """
    max_new_tokens = base_params.max_new_tokens

    if strict_json:
        max_new_tokens = min(max_new_tokens, 900)

    if memory_constrained:
        max_new_tokens = min(max_new_tokens, 1100)

    return GenerationParams(
        temperature=base_params.temperature,
        top_p=base_params.top_p,
        top_k=base_params.top_k,
        max_input_tokens=base_params.max_input_tokens,
        max_new_tokens=max_new_tokens,
        max_total_tokens=base_params.max_total_tokens,
        repetition_penalty=base_params.repetition_penalty,
        do_sample=base_params.do_sample,
    )


def calculate_effective_max_tokens(
    max_new_tokens: int,
    input_length: int,
    max_total_tokens: int,
    *,
    safety_margin: int = 64,
) -> int:
    """
    Calculate effective max tokens based on input length.

    Args:
        max_new_tokens: Requested max new tokens
        input_length: Length of input in tokens
        max_total_tokens: Maximum total context length
        safety_margin: Safety margin to avoid overflow

    Returns:
        Effective max new tokens
    """
    available = max_total_tokens - input_length - safety_margin
    return max(64, min(max_new_tokens, available))
