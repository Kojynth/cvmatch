#!/usr/bin/env python3
"""
Intelligent Model Router and Language-Aware Selection
=====================================================

Provides intelligent routing and selection of AI models based on:
- Document language detection and analysis
- Task-specific requirements and constraints
- Model availability and performance profiles
- Resource constraints and optimization preferences

Features:
- Multi-language model routing with fallbacks
- Performance-aware model selection
- Resource-constrained optimization
- Task-specific model matching
- Graceful degradation strategies
"""

import json
import yaml
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union, Set
from dataclasses import dataclass, field, asdict
from enum import Enum
import logging

# Add project root to path
import sys

script_dir = Path(__file__).parent
project_root = script_dir.parent.parent
sys.path.insert(0, str(project_root))

try:
    from cvextractor.logging.pii_filters import create_pii_safe_logger
    from cvextractor.core.mode import AIMode, ModeContext
    from cvextractor.preprocessing.language_detector import LanguageDetector
except ImportError:
    create_pii_safe_logger = None
    AIMode = None
    ModeContext = None
    LanguageDetector = None

# Configure logger
logger = (
    create_pii_safe_logger(__name__)
    if create_pii_safe_logger
    else logging.getLogger(__name__)
)


class TaskType(Enum):
    """Types of AI tasks for model selection."""

    SECTION_CLASSIFICATION = "section_classification"
    NAMED_ENTITY_RECOGNITION = "named_entity_recognition"
    EMBEDDING_SIMILARITY = "embedding_similarity"
    ZERO_SHOT_CLASSIFICATION = "zero_shot_classification"
    TEXT_CLASSIFICATION = "text_classification"


class SelectionStrategy(Enum):
    """Model selection strategies."""

    PERFORMANCE_FIRST = "performance_first"
    SPEED_FIRST = "speed_first"
    MEMORY_FIRST = "memory_first"
    BALANCED = "balanced"
    CONSERVATIVE = "conservative"


class ResourceConstraint(Enum):
    """Resource constraint levels."""

    MINIMAL = "minimal"  # < 2GB RAM, CPU only
    STANDARD = "standard"  # 2-8GB RAM, optional GPU
    HIGH = "high"  # 8-16GB RAM, GPU preferred
    UNLIMITED = "unlimited"  # > 16GB RAM, multiple GPUs


@dataclass
class ModelCandidate:
    """Information about a candidate model for selection."""

    model_id: str
    task_types: List[TaskType]
    languages: List[str]
    performance_score: float = 0.0
    accuracy_score: float = 0.0
    speed_score: float = 0.0
    memory_score: float = 0.0
    resource_requirements: ResourceConstraint = ResourceConstraint.STANDARD
    is_available: bool = False
    is_loaded: bool = False
    load_time_estimate_ms: float = 0.0
    memory_usage_mb: float = 0.0
    quality_tier: str = "standard"  # basic, standard, premium


@dataclass
class RoutingRequest:
    """Request for model routing and selection."""

    task_type: TaskType
    document_text: str = ""
    detected_language: Optional[str] = None
    languages_supported: List[str] = field(default_factory=lambda: ["fr", "en"])
    selection_strategy: SelectionStrategy = SelectionStrategy.BALANCED
    resource_constraints: ResourceConstraint = ResourceConstraint.STANDARD
    performance_requirements: Dict[str, float] = field(default_factory=dict)
    force_model_id: Optional[str] = None
    exclude_models: List[str] = field(default_factory=list)


@dataclass
class RoutingResult:
    """Result of model routing and selection."""

    selected_model_id: Optional[str]
    selection_reason: str
    confidence_score: float = 0.0
    fallback_models: List[str] = field(default_factory=list)
    language_matched: bool = False
    performance_estimate: Dict[str, float] = field(default_factory=dict)
    resource_usage_estimate: Dict[str, float] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    routing_time_ms: float = 0.0


class IntelligentModelRouter:
    """
    Intelligent model router with language awareness and performance optimization.

    Selects optimal models based on task requirements, language detection,
    resource constraints, and performance profiles. Provides fallback
    strategies and graceful degradation.
    """

    def __init__(
        self,
        config_file: Path = None,
        language_detector: LanguageDetector = None,
        enable_caching: bool = True,
    ):
        """
        Initialize intelligent model router.

        Args:
            config_file: Path to models configuration file
            language_detector: Language detection system
            enable_caching: Whether to cache routing decisions
        """
        self.config_file = config_file or Path("config") / "models.yaml"
        self.language_detector = language_detector or (
            LanguageDetector() if LanguageDetector else None
        )
        self.enable_caching = enable_caching

        # Load configuration
        self.model_config = self._load_model_config()
        self.model_candidates = self._build_model_candidates()

        # Routing cache
        self.routing_cache: Dict[str, RoutingResult] = {}

        # Language preferences and mappings
        self.language_preferences = self._build_language_preferences()

    def route_model(self, request: RoutingRequest) -> RoutingResult:
        """
        Route and select optimal model for the given request.

        Args:
            request: Routing request with task and constraints

        Returns:
            RoutingResult: Selected model and routing information
        """
        start_time = time.time()

        logger.info(f"Routing model for task: {request.task_type.value}")

        # Check cache first
        cache_key = self._generate_cache_key(request)
        if self.enable_caching and cache_key in self.routing_cache:
            cached_result = self.routing_cache[cache_key]
            logger.debug(f"Cache hit for routing request: {cache_key}")
            return cached_result

        # Detect language if not provided
        if not request.detected_language and request.document_text:
            request.detected_language = self._detect_language(request.document_text)

        # Filter candidates based on request
        candidates = self._filter_candidates(request)

        # Score and rank candidates
        scored_candidates = self._score_candidates(candidates, request)

        # Select best candidate
        result = self._select_best_candidate(scored_candidates, request)

        # Add timing information
        result.routing_time_ms = (time.time() - start_time) * 1000

        # Cache result
        if self.enable_caching:
            self.routing_cache[cache_key] = result

        logger.info(
            f"Model routing completed: {result.selected_model_id} (reason: {result.selection_reason})"
        )
        return result

    def get_available_models(
        self, task_type: TaskType = None, language: str = None
    ) -> List[ModelCandidate]:
        """
        Get list of available models with optional filtering.

        Args:
            task_type: Filter by specific task type
            language: Filter by supported language

        Returns:
            List[ModelCandidate]: Available model candidates
        """
        candidates = list(self.model_candidates.values())

        if task_type:
            candidates = [c for c in candidates if task_type in c.task_types]

        if language:
            candidates = [c for c in candidates if language in c.languages]

        return candidates

    def update_model_availability(
        self, model_id: str, is_available: bool, is_loaded: bool = False
    ):
        """Update model availability status."""
        if model_id in self.model_candidates:
            self.model_candidates[model_id].is_available = is_available
            self.model_candidates[model_id].is_loaded = is_loaded
            logger.debug(
                f"Updated model {model_id}: available={is_available}, loaded={is_loaded}"
            )

    def get_routing_statistics(self) -> Dict[str, Any]:
        """Get routing statistics and performance metrics."""
        if not self.routing_cache:
            return {"cache_entries": 0}

        successful_routes = [
            r for r in self.routing_cache.values() if r.selected_model_id
        ]
        failed_routes = [
            r for r in self.routing_cache.values() if not r.selected_model_id
        ]

        # Model selection frequency
        model_usage = {}
        for result in successful_routes:
            model_id = result.selected_model_id
            model_usage[model_id] = model_usage.get(model_id, 0) + 1

        # Language detection accuracy
        language_matches = [r for r in successful_routes if r.language_matched]

        return {
            "cache_entries": len(self.routing_cache),
            "successful_routes": len(successful_routes),
            "failed_routes": len(failed_routes),
            "success_rate": (
                len(successful_routes) / len(self.routing_cache)
                if self.routing_cache
                else 0
            ),
            "model_usage": model_usage,
            "language_match_rate": (
                len(language_matches) / len(successful_routes)
                if successful_routes
                else 0
            ),
            "avg_routing_time_ms": sum(
                r.routing_time_ms for r in self.routing_cache.values()
            )
            / len(self.routing_cache),
        }

    def _load_model_config(self) -> Dict[str, Any]:
        """Load model configuration from file."""
        if not self.config_file.exists():
            logger.warning(f"Model config not found: {self.config_file}")
            return {"model_candidates": {}, "language_routing": {}}

        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                if self.config_file.suffix.lower() == ".yaml":
                    return yaml.safe_load(f)
                else:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load model config: {e}")
            return {"model_candidates": {}, "language_routing": {}}

    def _build_model_candidates(self) -> Dict[str, ModelCandidate]:
        """Build model candidates from configuration."""
        candidates = {}

        config_candidates = self.model_config.get("model_candidates", {})

        for model_id, config in config_candidates.items():
            try:
                # Parse task types
                task_types = []
                for task_str in config.get("task_types", []):
                    try:
                        task_types.append(TaskType(task_str))
                    except ValueError:
                        logger.warning(f"Unknown task type: {task_str}")

                # Parse resource requirements
                resource_req = ResourceConstraint.STANDARD
                req_str = config.get("resource_requirements", "standard")
                try:
                    resource_req = ResourceConstraint(req_str)
                except ValueError:
                    logger.warning(f"Unknown resource requirement: {req_str}")

                candidate = ModelCandidate(
                    model_id=model_id,
                    task_types=task_types,
                    languages=config.get("languages", ["en"]),
                    performance_score=config.get("performance_profile", {}).get(
                        "overall_score", 0.5
                    ),
                    accuracy_score=config.get("performance_profile", {}).get(
                        "accuracy_score", 0.5
                    ),
                    speed_score=config.get("performance_profile", {}).get(
                        "speed_score", 0.5
                    ),
                    memory_score=config.get("performance_profile", {}).get(
                        "memory_score", 0.5
                    ),
                    resource_requirements=resource_req,
                    load_time_estimate_ms=config.get("performance_profile", {}).get(
                        "load_time_ms", 5000
                    ),
                    memory_usage_mb=config.get("performance_profile", {}).get(
                        "memory_usage_mb", 1000
                    ),
                    quality_tier=config.get("quality_tier", "standard"),
                )

                candidates[model_id] = candidate

            except Exception as e:
                logger.error(f"Failed to parse model candidate {model_id}: {e}")

        return candidates

    def _build_language_preferences(self) -> Dict[str, Dict[str, Any]]:
        """Build language preferences and routing rules."""
        language_config = self.model_config.get("language_routing", {})

        # Default preferences
        preferences = {
            "fr": {
                "primary_models": [],
                "fallback_models": [],
                "accuracy_weight": 0.4,
                "performance_weight": 0.3,
                "compatibility_weight": 0.3,
            },
            "en": {
                "primary_models": [],
                "fallback_models": [],
                "accuracy_weight": 0.3,
                "performance_weight": 0.4,
                "compatibility_weight": 0.3,
            },
        }

        # Update with configuration
        for lang, config in language_config.items():
            if lang in preferences:
                preferences[lang].update(config)
            else:
                preferences[lang] = config

        return preferences

    def _detect_language(self, text: str) -> Optional[str]:
        """Detect language of the given text."""
        if not self.language_detector:
            # Simple heuristic fallback
            french_indicators = [
                "expérience",
                "formation",
                "compétences",
                "éducation",
                "université",
            ]
            text_lower = text.lower()

            french_count = sum(
                1 for indicator in french_indicators if indicator in text_lower
            )
            if french_count >= 2:
                return "fr"
            else:
                return "en"

        try:
            result = self.language_detector.detect_language(text)
            if isinstance(result, dict) and "language" in result:
                return result["language"]
            elif isinstance(result, str):
                return result
        except Exception as e:
            logger.warning(f"Language detection failed: {e}")

        return "en"  # Default fallback

    def _filter_candidates(self, request: RoutingRequest) -> List[ModelCandidate]:
        """Filter candidates based on request criteria."""
        candidates = list(self.model_candidates.values())

        # Filter by task type
        candidates = [c for c in candidates if request.task_type in c.task_types]

        # Filter by forced model
        if request.force_model_id:
            candidates = [c for c in candidates if c.model_id == request.force_model_id]

        # Filter out excluded models
        if request.exclude_models:
            candidates = [
                c for c in candidates if c.model_id not in request.exclude_models
            ]

        # Filter by resource constraints
        suitable_resources = self._get_suitable_resource_levels(
            request.resource_constraints
        )
        candidates = [
            c for c in candidates if c.resource_requirements in suitable_resources
        ]

        # Filter by availability
        candidates = [c for c in candidates if c.is_available]

        return candidates

    def _get_suitable_resource_levels(
        self, constraint: ResourceConstraint
    ) -> List[ResourceConstraint]:
        """Get suitable resource levels for the given constraint."""
        levels = [
            ResourceConstraint.MINIMAL,
            ResourceConstraint.STANDARD,
            ResourceConstraint.HIGH,
            ResourceConstraint.UNLIMITED,
        ]

        # Return all levels up to and including the constraint
        constraint_index = levels.index(constraint)
        return levels[: constraint_index + 1]

    def _score_candidates(
        self, candidates: List[ModelCandidate], request: RoutingRequest
    ) -> List[Tuple[ModelCandidate, float]]:
        """Score candidates based on request criteria."""
        scored_candidates = []

        for candidate in candidates:
            score = self._calculate_candidate_score(candidate, request)
            scored_candidates.append((candidate, score))

        # Sort by score (highest first)
        scored_candidates.sort(key=lambda x: x[1], reverse=True)

        return scored_candidates

    def _calculate_candidate_score(
        self, candidate: ModelCandidate, request: RoutingRequest
    ) -> float:
        """Calculate score for a candidate based on request requirements."""
        score = 0.0
        weights = self._get_scoring_weights(request.selection_strategy)

        # Language match bonus
        language_score = 0.0
        if request.detected_language:
            if request.detected_language in candidate.languages:
                language_score = 1.0
            elif "en" in candidate.languages:  # English fallback
                language_score = 0.5

        # Performance scores
        performance_score = candidate.performance_score
        accuracy_score = candidate.accuracy_score
        speed_score = candidate.speed_score
        memory_score = candidate.memory_score

        # Quality tier bonus
        quality_bonus = {"basic": 0.0, "standard": 0.1, "premium": 0.2}.get(
            candidate.quality_tier, 0.0
        )

        # Loading bonus (already loaded models are preferred)
        loading_bonus = 0.15 if candidate.is_loaded else 0.0

        # Calculate weighted score
        score = (
            language_score * weights["language"]
            + performance_score * weights["performance"]
            + accuracy_score * weights["accuracy"]
            + speed_score * weights["speed"]
            + memory_score * weights["memory"]
            + quality_bonus * weights["quality"]
            + loading_bonus
        )

        # Resource constraint penalty
        if (
            candidate.resource_requirements == ResourceConstraint.UNLIMITED
            and request.resource_constraints != ResourceConstraint.UNLIMITED
        ):
            score *= 0.7  # Penalty for high resource models in constrained environments

        return score

    def _get_scoring_weights(self, strategy: SelectionStrategy) -> Dict[str, float]:
        """Get scoring weights based on selection strategy."""
        if strategy == SelectionStrategy.PERFORMANCE_FIRST:
            return {
                "language": 0.3,
                "performance": 0.3,
                "accuracy": 0.2,
                "speed": 0.1,
                "memory": 0.05,
                "quality": 0.05,
            }
        elif strategy == SelectionStrategy.SPEED_FIRST:
            return {
                "language": 0.25,
                "performance": 0.15,
                "accuracy": 0.15,
                "speed": 0.35,
                "memory": 0.05,
                "quality": 0.05,
            }
        elif strategy == SelectionStrategy.MEMORY_FIRST:
            return {
                "language": 0.25,
                "performance": 0.15,
                "accuracy": 0.15,
                "speed": 0.05,
                "memory": 0.35,
                "quality": 0.05,
            }
        elif strategy == SelectionStrategy.CONSERVATIVE:
            return {
                "language": 0.4,
                "performance": 0.2,
                "accuracy": 0.2,
                "speed": 0.05,
                "memory": 0.1,
                "quality": 0.05,
            }
        else:  # BALANCED
            return {
                "language": 0.3,
                "performance": 0.2,
                "accuracy": 0.2,
                "speed": 0.15,
                "memory": 0.1,
                "quality": 0.05,
            }

    def _select_best_candidate(
        self,
        scored_candidates: List[Tuple[ModelCandidate, float]],
        request: RoutingRequest,
    ) -> RoutingResult:
        """Select the best candidate from scored list."""
        if not scored_candidates:
            return RoutingResult(
                selected_model_id=None,
                selection_reason="No suitable models available",
                confidence_score=0.0,
                warnings=["No models match the specified criteria"],
            )

        # Get top candidate
        best_candidate, best_score = scored_candidates[0]

        # Build fallback list
        fallback_models = [
            candidate.model_id for candidate, _ in scored_candidates[1:5]
        ]  # Top 4 alternatives

        # Check language match
        language_matched = False
        if request.detected_language:
            language_matched = request.detected_language in best_candidate.languages

        # Generate selection reason
        selection_reason = self._generate_selection_reason(
            best_candidate, best_score, request
        )

        # Estimate performance
        performance_estimate = {
            "load_time_ms": best_candidate.load_time_estimate_ms,
            "inference_accuracy": best_candidate.accuracy_score,
            "inference_speed_score": best_candidate.speed_score,
        }

        # Estimate resource usage
        resource_usage_estimate = {
            "memory_mb": best_candidate.memory_usage_mb,
            "resource_level": best_candidate.resource_requirements.value,
        }

        # Generate warnings
        warnings = []
        if not language_matched and request.detected_language:
            warnings.append(
                f"No exact language match for '{request.detected_language}', using best available"
            )

        if best_score < 0.5:
            warnings.append("Selected model has low compatibility score")

        return RoutingResult(
            selected_model_id=best_candidate.model_id,
            selection_reason=selection_reason,
            confidence_score=best_score,
            fallback_models=fallback_models,
            language_matched=language_matched,
            performance_estimate=performance_estimate,
            resource_usage_estimate=resource_usage_estimate,
            warnings=warnings,
        )

    def _generate_selection_reason(
        self, candidate: ModelCandidate, score: float, request: RoutingRequest
    ) -> str:
        """Generate human-readable selection reason."""
        reasons = []

        if request.force_model_id:
            return f"Forced selection: {request.force_model_id}"

        if candidate.is_loaded:
            reasons.append("already loaded")

        if (
            request.detected_language
            and request.detected_language in candidate.languages
        ):
            reasons.append(f"supports {request.detected_language}")

        if candidate.quality_tier == "premium":
            reasons.append("premium quality")
        elif candidate.quality_tier == "standard":
            reasons.append("standard quality")

        strategy_reasons = {
            SelectionStrategy.PERFORMANCE_FIRST: "best performance",
            SelectionStrategy.SPEED_FIRST: "fastest inference",
            SelectionStrategy.MEMORY_FIRST: "lowest memory usage",
            SelectionStrategy.CONSERVATIVE: "most reliable",
            SelectionStrategy.BALANCED: "best overall balance",
        }

        if request.selection_strategy in strategy_reasons:
            reasons.append(strategy_reasons[request.selection_strategy])

        if not reasons:
            reasons.append("best available match")

        return f"Selected for: {', '.join(reasons)} (score: {score:.2f})"

    def _generate_cache_key(self, request: RoutingRequest) -> str:
        """Generate cache key for routing request."""
        # Use hash of key request attributes
        key_attrs = [
            request.task_type.value,
            request.detected_language or "unknown",
            request.selection_strategy.value,
            request.resource_constraints.value,
            request.force_model_id or "none",
            ",".join(sorted(request.exclude_models)),
        ]

        return "|".join(key_attrs)


def create_default_routing_config(output_file: Path = None) -> None:
    """Create default routing configuration."""
    if output_file is None:
        output_file = Path("config") / "routing_config.yaml"

    default_config = {
        "language_routing": {
            "fr": {
                "primary_models": ["deberta-v3-large-french"],
                "fallback_models": ["camembert-base", "distilbert-multilingual"],
                "accuracy_weight": 0.4,
                "performance_weight": 0.3,
                "compatibility_weight": 0.3,
            },
            "en": {
                "primary_models": ["deberta-v3-large"],
                "fallback_models": ["distilbert-base-uncased", "roberta-base"],
                "accuracy_weight": 0.3,
                "performance_weight": 0.4,
                "compatibility_weight": 0.3,
            },
        },
        "task_routing": {
            "section_classification": {
                "preferred_models": ["deberta-v3-large-french", "deberta-v3-large"],
                "min_accuracy": 0.75,
                "max_latency_ms": 2000,
            },
            "named_entity_recognition": {
                "preferred_models": ["camembert-ner", "distilbert-multilingual-ner"],
                "min_accuracy": 0.80,
                "max_latency_ms": 1500,
            },
        },
        "resource_constraints": {
            "minimal": {
                "max_memory_mb": 2048,
                "cpu_only": True,
                "max_load_time_ms": 10000,
            },
            "standard": {
                "max_memory_mb": 8192,
                "gpu_optional": True,
                "max_load_time_ms": 30000,
            },
            "high": {
                "max_memory_mb": 16384,
                "gpu_preferred": True,
                "max_load_time_ms": 60000,
            },
        },
    }

    # Ensure output directory exists
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Write configuration
    with open(output_file, "w", encoding="utf-8") as f:
        yaml.dump(
            default_config, f, indent=2, default_flow_style=False, allow_unicode=True
        )

    print(f"Default routing configuration created: {output_file}")


def main():
    """Main entry point for model routing testing."""
    import argparse

    parser = argparse.ArgumentParser(description="Test intelligent model routing")
    parser.add_argument(
        "--task",
        choices=[t.value for t in TaskType],
        default="section_classification",
        help="Task type to route",
    )
    parser.add_argument(
        "--text",
        type=str,
        default="Ingénieur logiciel avec 5 ans d'expérience",
        help="Sample text for language detection",
    )
    parser.add_argument(
        "--strategy",
        choices=[s.value for s in SelectionStrategy],
        default="balanced",
        help="Selection strategy",
    )
    parser.add_argument(
        "--constraint",
        choices=[c.value for c in ResourceConstraint],
        default="standard",
        help="Resource constraint level",
    )
    parser.add_argument(
        "--create-config", action="store_true", help="Create default routing config"
    )

    args = parser.parse_args()

    if args.create_config:
        create_default_routing_config()
        return

    # Initialize router
    router = IntelligentModelRouter()

    # Create routing request
    request = RoutingRequest(
        task_type=TaskType(args.task),
        document_text=args.text,
        selection_strategy=SelectionStrategy(args.strategy),
        resource_constraints=ResourceConstraint(args.constraint),
    )

    # Route model
    result = router.route_model(request)

    # Display results
    print(f"\nModel Routing Results:")
    print(f"Selected Model: {result.selected_model_id}")
    print(f"Selection Reason: {result.selection_reason}")
    print(f"Confidence Score: {result.confidence_score:.2f}")
    print(f"Language Matched: {result.language_matched}")

    if result.fallback_models:
        print(f"Fallback Models: {', '.join(result.fallback_models)}")

    if result.warnings:
        print(f"Warnings:")
        for warning in result.warnings:
            print(f"  - {warning}")

    # Show available models
    print(f"\nAvailable Models for {args.task}:")
    available = router.get_available_models(TaskType(args.task))
    for candidate in available[:5]:  # Show top 5
        print(f"  - {candidate.model_id} (languages: {', '.join(candidate.languages)})")


if __name__ == "__main__":
    main()
