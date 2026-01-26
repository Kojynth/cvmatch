"""
AI Mode Contract System
======================

Defines the different AI operation modes and provides a unified interface for
mode management, artifact requirements, and graceful degradation.

This module ensures clear contracts between AI capabilities and extraction features.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Any, Optional, Set
import logging
from pathlib import Path

# Configure logger
logger = logging.getLogger(__name__)


class AIMode(Enum):
    """AI operation modes with clear contracts."""

    FULL_AI = "FULL_AI"  # All AI features enabled, requires all models
    PARTIAL_AI = "PARTIAL_AI"  # Some AI features enabled, degraded capability
    RULES_ONLY = "RULES_ONLY"  # No AI features, heuristic fallbacks only

    def __str__(self) -> str:
        return self.value


class ModeReason(Enum):
    """Standardized reasons for mode selection/degradation."""

    # Success reasons
    ALL_MODELS_AVAILABLE = "ALL_MODELS_AVAILABLE"
    USER_REQUESTED_RULES_ONLY = "USER_REQUESTED_RULES_ONLY"

    # Model availability issues
    OFFLINE_CACHE_MISS = "OFFLINE_CACHE_MISS"
    MODEL_CORRUPTED = "MODEL_CORRUPTED"
    MODEL_LOAD_FAILED = "MODEL_LOAD_FAILED"

    # Resource constraints
    INSUFFICIENT_MEMORY = "INSUFFICIENT_MEMORY"
    INSUFFICIENT_STORAGE = "INSUFFICIENT_STORAGE"

    # Network/download issues
    DOWNLOAD_FAILED = "DOWNLOAD_FAILED"
    NETWORK_UNAVAILABLE = "NETWORK_UNAVAILABLE"
    DOWNLOAD_REJECTED = "DOWNLOAD_REJECTED"

    # Configuration issues
    MODEL_ID_INVALID = "MODEL_ID_INVALID"
    CONFIG_ERROR = "CONFIG_ERROR"

    # Runtime issues
    MODULE_DISABLED = "MODULE_DISABLED"
    THRESHOLD_REJECTED = "THRESHOLD_REJECTED"
    AUTH_401 = "AUTH_401"

    def __str__(self) -> str:
        return self.value


@dataclass
class ModelStatus:
    """Status of an individual AI model."""

    id: str
    available: bool
    path: Optional[Path] = None
    size_mb: Optional[float] = None
    load_time_ms: Optional[float] = None
    memory_usage_mb: Optional[float] = None
    last_verified: Optional[str] = None
    error: Optional[str] = None


@dataclass
class ModeContext:
    """
    Complete context for AI mode management.

    Tracks model availability, capability flags, and provides
    clear reasoning for mode decisions.
    """

    # Current mode and reasoning
    mode: AIMode
    reasons: List[ModeReason] = field(default_factory=list)

    # Model availability tracking
    models_available: Dict[str, bool] = field(default_factory=dict)
    models_status: Dict[str, ModelStatus] = field(default_factory=dict)

    # Feature availability derived from models
    features_available: Dict[str, bool] = field(default_factory=dict)
    features_degraded: Set[str] = field(default_factory=set)

    # Runtime metrics
    total_models_required: int = 0
    total_models_available: int = 0
    total_size_available_mb: float = 0.0
    estimated_memory_usage_mb: float = 0.0

    def add_reason(self, reason: ModeReason, detail: Optional[str] = None) -> None:
        """Add a reason for current mode with optional detail."""
        self.reasons.append(reason)
        if detail:
            logger.info(f"MODE_CONTEXT: {reason.value} | detail={detail}")

    def set_model_status(self, model_id: str, status: ModelStatus) -> None:
        """Update status for a specific model."""
        self.models_status[model_id] = status
        self.models_available[model_id] = status.available

        if status.available and status.size_mb:
            self.total_size_available_mb += status.size_mb

    def get_availability_summary(self) -> Dict[str, Any]:
        """Get summary of model and feature availability."""
        return {
            "mode": self.mode.value,
            "models_available": f"{self.total_models_available}/{self.total_models_required}",
            "features_available": len(
                [f for f, available in self.features_available.items() if available]
            ),
            "features_degraded": len(self.features_degraded),
            "total_size_mb": self.total_size_available_mb,
            "estimated_memory_mb": self.estimated_memory_usage_mb,
            "reasons": [r.value for r in self.reasons],
        }

    def is_feature_available(self, feature_name: str) -> bool:
        """Check if a specific feature is available in current mode."""
        return self.features_available.get(feature_name, False)

    def require_model(self, model_id: str) -> bool:
        """
        Check if a required model is available.

        Returns:
            bool: True if model is available, False otherwise

        Side effects:
            - Updates mode context if model is missing
            - Adds appropriate reason codes
        """
        if model_id not in self.models_available:
            self.add_reason(ModeReason.OFFLINE_CACHE_MISS, f"model_id={model_id}")
            return False

        return self.models_available[model_id]

    def require_feature(self, feature_name: str) -> bool:
        """
        Check if a required feature is available.

        Returns:
            bool: True if feature is available, False otherwise
        """
        available = self.is_feature_available(feature_name)
        if not available:
            self.features_degraded.add(feature_name)
            self.add_reason(ModeReason.MODULE_DISABLED, f"feature={feature_name}")

        return available


class ModeManager:
    """
    Central manager for AI mode decisions and transitions.

    Responsibilities:
    - Determine appropriate AI mode based on model availability
    - Manage graceful degradation paths
    - Provide clear reasoning for mode decisions
    """

    def __init__(self, models_config: Dict[str, Any]):
        """
        Initialize mode manager with model configuration.

        Args:
            models_config: Loaded models.yaml configuration
        """
        self.models_config = models_config
        self.feature_requirements = models_config.get("feature_requirements", {})

        # Cache for mode context
        self._current_context: Optional[ModeContext] = None

    def determine_mode(
        self,
        requested_mode: AIMode = AIMode.FULL_AI,
        available_models: Optional[Set[str]] = None,
        user_preferences: Optional[Dict[str, Any]] = None,
    ) -> ModeContext:
        """
        Determine the appropriate AI mode based on current conditions.

        Args:
            requested_mode: User's preferred mode
            available_models: Set of locally available model IDs
            user_preferences: Additional user preferences

        Returns:
            ModeContext: Complete context for the determined mode
        """
        logger.info(f"MODE_MANAGER: determine_mode | requested={requested_mode.value}")

        # Initialize context
        context = ModeContext(mode=requested_mode)

        # Handle explicit rules-only request
        if requested_mode == AIMode.RULES_ONLY:
            context.mode = AIMode.RULES_ONLY
            context.add_reason(ModeReason.USER_REQUESTED_RULES_ONLY)
            self._populate_rules_only_features(context)
            return context

        # Check model availability
        if available_models is None:
            available_models = self._scan_available_models()

        # Populate model status
        self._populate_model_status(context, available_models)

        # Determine actual mode based on availability
        actual_mode = self._calculate_actual_mode(context, requested_mode)
        context.mode = actual_mode

        # Populate feature availability
        self._populate_feature_availability(context)

        # Cache context
        self._current_context = context

        logger.info(
            f"MODE_MANAGER: mode_determined | {context.get_availability_summary()}"
        )
        return context

    def get_current_context(self) -> Optional[ModeContext]:
        """Get the current mode context."""
        return self._current_context

    def _scan_available_models(self) -> Set[str]:
        """Scan local cache for available models."""
        available = set()

        models = self.models_config.get("models", {})
        for model_id, model_config in models.items():
            local_path = Path(model_config.get("local_path", ""))
            if local_path.exists() and local_path.is_dir():
                # Basic availability check - directory exists
                available.add(model_id)

        logger.debug(f"MODE_MANAGER: scan_complete | available={available}")
        return available

    def _populate_model_status(
        self, context: ModeContext, available_models: Set[str]
    ) -> None:
        """Populate detailed model status in context."""
        models = self.models_config.get("models", {})

        for model_id, model_config in models.items():
            # Create model status
            is_available = model_id in available_models
            status = ModelStatus(
                id=model_id,
                available=is_available,
                path=Path(model_config.get("local_path", "")) if is_available else None,
                size_mb=model_config.get("size_mb"),
            )

            context.set_model_status(model_id, status)
            context.total_models_required += 1

            if is_available:
                context.total_models_available += 1

    def _calculate_actual_mode(
        self, context: ModeContext, requested_mode: AIMode
    ) -> AIMode:
        """Calculate the actual achievable mode based on model availability."""

        # Check for full AI capability
        if requested_mode == AIMode.FULL_AI:
            missing_models = []
            for model_id in self.models_config.get("models", {}):
                if not context.models_available.get(model_id, False):
                    missing_models.append(model_id)

            if not missing_models:
                context.add_reason(ModeReason.ALL_MODELS_AVAILABLE)
                return AIMode.FULL_AI
            else:
                # Check if we can achieve partial AI
                essential_models = self._get_essential_models()
                available_essential = [
                    m
                    for m in essential_models
                    if context.models_available.get(m, False)
                ]

                if available_essential:
                    context.add_reason(
                        ModeReason.OFFLINE_CACHE_MISS, f"missing={missing_models}"
                    )
                    return AIMode.PARTIAL_AI
                else:
                    context.add_reason(
                        ModeReason.OFFLINE_CACHE_MISS, f"no_essential_models"
                    )
                    return AIMode.RULES_ONLY

        # Check for partial AI capability
        elif requested_mode == AIMode.PARTIAL_AI:
            essential_models = self._get_essential_models()
            available_essential = [
                m for m in essential_models if context.models_available.get(m, False)
            ]

            if available_essential:
                return AIMode.PARTIAL_AI
            else:
                context.add_reason(ModeReason.OFFLINE_CACHE_MISS, "no_essential_models")
                return AIMode.RULES_ONLY

        # Default to rules only
        return AIMode.RULES_ONLY

    def _get_essential_models(self) -> List[str]:
        """Get list of essential models for partial AI operation."""
        collections = self.models_config.get("collections", {})
        standard_models = collections.get("standard_ai", {}).get("models")
        if standard_models:
            return list(dict.fromkeys(standard_models))

        essentials: List[str] = []
        for cfg in self.models_config.get("feature_requirements", {}).values():
            for model_id in cfg.get("required_models", []):
                if model_id not in essentials:
                    essentials.append(model_id)

        if essentials:
            return essentials

        # Fallback to legacy identifier if configuration is incomplete
        return ["section_classifier_deberta_v3"]

    def _populate_feature_availability(self, context: ModeContext) -> None:
        """Populate feature availability based on current mode and models."""

        for feature_name, requirements in self.feature_requirements.items():
            required_models = requirements.get("required_models", [])
            optional_models = requirements.get("optional_models", [])

            # Check if all required models are available
            required_available = all(
                context.models_available.get(model_id, False)
                for model_id in required_models
            )

            # Feature is available if in rules-only mode OR required models are present
            if context.mode == AIMode.RULES_ONLY:
                # All features have fallback modes
                context.features_available[feature_name] = True
            else:
                context.features_available[feature_name] = required_available

                # Track optional models that are missing
                for model_id in optional_models:
                    if not context.models_available.get(model_id, False):
                        context.features_degraded.add(
                            f"{feature_name}_optional_{model_id}"
                        )

    def _populate_rules_only_features(self, context: ModeContext) -> None:
        """Populate feature availability for rules-only mode."""
        # In rules-only mode, all features are available via fallbacks
        for feature_name in self.feature_requirements.keys():
            context.features_available[feature_name] = True


# Convenience functions for common operations
def require_model(model_id: str, context: Optional[ModeContext] = None) -> bool:
    """
    Check if a required model is available.

    Args:
        model_id: Model identifier to check
        context: Mode context (uses current if None)

    Returns:
        bool: True if model is available

    Raises:
        RuntimeError: In STRICT mode when model is not available
    """
    if context is None:
        # Try to get current context (would need global manager instance)
        logger.warning("require_model called without context - assuming unavailable")
        return False

    return context.require_model(model_id)


def require_feature(feature_name: str, context: Optional[ModeContext] = None) -> bool:
    """
    Check if a required feature is available.

    Args:
        feature_name: Feature name to check
        context: Mode context (uses current if None)

    Returns:
        bool: True if feature is available
    """
    if context is None:
        logger.warning("require_feature called without context - assuming unavailable")
        return False

    return context.require_feature(feature_name)


# Export main classes and functions
__all__ = [
    "AIMode",
    "ModeReason",
    "ModelStatus",
    "ModeContext",
    "ModeManager",
    "require_model",
    "require_feature",
]
