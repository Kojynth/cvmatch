"""
Unified Model Loader with Auto-Download Capability
==================================================

Provides unified loading of AI models with automatic download capability,
integrity verification, and intelligent caching. Integrates with the mode
management system for graceful degradation.
"""

import time
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, Callable, Union, Set, List
import logging
from dataclasses import dataclass

from .model_downloader import ModelDownloader, DownloadProgress, ModelDownloadError
from ..core.mode import AIMode, ModeContext, ModeManager, ModeReason, ModelStatus

# Configure logger
logger = logging.getLogger(__name__)


@dataclass
class LoadResult:
    """Result of model loading operation."""

    success: bool
    model: Any = None
    error: Optional[str] = None
    load_time_ms: float = 0.0
    memory_usage_mb: float = 0.0
    from_cache: bool = True


class MissingArtifactError(Exception):
    """Raised when required model artifact is not available."""

    pass


class ModelLoader:
    """
    Unified model loader with intelligent download and caching capabilities.

    Features:
    - Automatic model downloading when AI mode selected
    - Integrity verification and caching
    - Integration with mode management system
    - Graceful degradation and error handling
    - Memory and performance optimization
    """

    def __init__(
        self,
        models_config_path: Union[str, Path] = "config/models.yaml",
        cache_dir: Optional[Path] = None,
        auto_download: bool = True,
        progress_callback: Optional[Callable[[DownloadProgress], None]] = None,
    ):
        """
        Initialize model loader.

        Args:
            models_config_path: Path to models.yaml configuration
            cache_dir: Override default cache directory
            auto_download: Enable automatic downloading when models missing
            progress_callback: Callback for download progress updates
        """
        self.models_config_path = Path(models_config_path)
        self.auto_download = auto_download
        self.progress_callback = progress_callback

        # Load configuration
        self.models_config = self._load_models_config()

        # Set up cache directory
        self.cache_dir = cache_dir or Path(".cache/models")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Initialize components
        self.downloader = ModelDownloader(
            self.models_config,
            progress_callback=progress_callback,
            cache_dir=self.cache_dir,
        )

        self.mode_manager = ModeManager(self.models_config)

        # Loaded models cache
        self._loaded_models: Dict[str, Any] = {}
        self._load_results: Dict[str, LoadResult] = {}

        # Current mode context
        self._current_context: Optional[ModeContext] = None

    def initialize_for_mode(
        self,
        requested_mode: AIMode = AIMode.FULL_AI,
        prompt_user_for_download: bool = True,
    ) -> ModeContext:
        """
        Initialize models for the requested AI mode.

        Args:
            requested_mode: Desired AI operation mode
            prompt_user_for_download: Whether to prompt user for download consent

        Returns:
            ModeContext: Final mode context based on available models

        Raises:
            ModelDownloadError: If download fails and mode cannot be achieved
        """
        logger.info(f"MODEL_LOADER: initialize_mode | requested={requested_mode.value}")

        # Scan for available models
        available_models = self._scan_available_models()
        logger.debug(f"MODEL_LOADER: available_models | {available_models}")

        # Determine initial mode based on availability
        context = self.mode_manager.determine_mode(
            requested_mode=requested_mode, available_models=available_models
        )

        # Handle download logic for AI modes
        if (
            requested_mode in [AIMode.FULL_AI, AIMode.PARTIAL_AI]
            and context.mode == AIMode.RULES_ONLY
        ):
            if self.auto_download and self._should_attempt_download(
                context, prompt_user_for_download
            ):
                context = self._attempt_model_downloads(context, requested_mode)

        # Cache context
        self._current_context = context

        logger.info(
            f"MODEL_LOADER: mode_initialized | {context.get_availability_summary()}"
        )
        return context

    def load_artifact(self, model_id: str, force_reload: bool = False) -> Any:
        """
        Load a specific model artifact.

        Args:
            model_id: Model identifier from models.yaml
            force_reload: Force reload even if already cached

        Returns:
            Loaded model object

        Raises:
            MissingArtifactError: If model not available and cannot be downloaded
        """
        logger.debug(f"MODEL_LOADER: load_artifact | model_id={model_id}")

        # Check cache first
        if not force_reload and model_id in self._loaded_models:
            logger.debug(f"MODEL_LOADER: cache_hit | model_id={model_id}")
            return self._loaded_models[model_id]

        # Get model configuration
        model_config = self._get_model_config(model_id)
        if not model_config:
            raise MissingArtifactError(f"Model '{model_id}' not found in configuration")

        # Check if model is available locally
        if not self._is_model_available(model_id):
            if self.auto_download:
                logger.info(f"MODEL_LOADER: auto_download | model_id={model_id}")
                try:
                    success = self.downloader.download_model(model_id)
                    if not success:
                        raise MissingArtifactError(
                            f"Failed to download model '{model_id}'"
                        )
                except ModelDownloadError as e:
                    raise MissingArtifactError(f"Download failed for '{model_id}': {e}")
            else:
                raise MissingArtifactError(
                    f"Model '{model_id}' not available locally and auto-download disabled"
                )

        # Load the model
        load_result = self._load_model_impl(model_id, model_config)

        if load_result.success:
            # Cache successful load
            self._loaded_models[model_id] = load_result.model
            self._load_results[model_id] = load_result

            # Update model status in context
            if self._current_context:
                status = ModelStatus(
                    id=model_id,
                    available=True,
                    path=Path(model_config["local_path"]),
                    size_mb=model_config.get("size_mb"),
                    load_time_ms=load_result.load_time_ms,
                    memory_usage_mb=load_result.memory_usage_mb,
                )
                self._current_context.set_model_status(model_id, status)

            logger.info(
                f"MODEL_LOADER: load_success | model_id={model_id} "
                f"time={load_result.load_time_ms:.1f}ms "
                f"memory={load_result.memory_usage_mb:.1f}MB"
            )

            return load_result.model
        else:
            raise MissingArtifactError(
                f"Failed to load model '{model_id}': {load_result.error}"
            )

    def get_current_context(self) -> Optional[ModeContext]:
        """Get current mode context."""
        return self._current_context

    def is_model_available(self, model_id: str) -> bool:
        """Check if model is available locally."""
        return self._is_model_available(model_id)

    def get_load_statistics(self) -> Dict[str, Any]:
        """Get loading statistics for all models."""
        stats = {
            "models_loaded": len(self._loaded_models),
            "total_load_time_ms": sum(
                r.load_time_ms for r in self._load_results.values()
            ),
            "total_memory_mb": sum(
                r.memory_usage_mb for r in self._load_results.values()
            ),
            "cache_hits": sum(1 for r in self._load_results.values() if r.from_cache),
            "models": {},
        }

        for model_id, result in self._load_results.items():
            stats["models"][model_id] = {
                "load_time_ms": result.load_time_ms,
                "memory_usage_mb": result.memory_usage_mb,
                "from_cache": result.from_cache,
            }

        return stats

    def _load_models_config(self) -> Dict[str, Any]:
        """Load models configuration from YAML file."""
        if not self.models_config_path.exists():
            raise FileNotFoundError(
                f"Models configuration not found: {self.models_config_path}"
            )

        with open(self.models_config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _scan_available_models(self) -> Set[str]:
        """Scan local cache for available models."""
        available = set()

        models = self.models_config.get("models", {})
        for model_id, model_config in models.items():
            if self._is_model_available(model_id):
                available.add(model_id)

        return available

    def _is_model_available(self, model_id: str) -> bool:
        """Check if model is available locally with all required files."""
        model_config = self._get_model_config(model_id)
        if not model_config:
            return False

        local_path = Path(model_config.get("local_path", ""))
        if not local_path.exists():
            return False

        # Check all required files
        file_list = model_config.get("file_list", [])
        for filename in file_list:
            file_path = local_path / filename
            if not file_path.exists():
                return False

        return True

    def _get_model_config(self, model_id: str) -> Optional[Dict[str, Any]]:
        """Get model configuration."""
        models = self.models_config.get("models", {})
        return models.get(model_id)

    def _should_attempt_download(self, context: ModeContext, prompt_user: bool) -> bool:
        """Determine if we should attempt to download missing models."""
        # For now, always attempt download if auto_download is enabled
        # In a real UI implementation, this would show a user prompt
        if prompt_user:
            logger.info(
                "MODEL_LOADER: auto_download_enabled | models will be downloaded automatically"
            )
            return True

        return self.auto_download

    def _attempt_model_downloads(
        self, context: ModeContext, requested_mode: AIMode
    ) -> ModeContext:
        """Attempt to download missing models to achieve requested mode."""
        logger.info(f"MODEL_LOADER: download_attempt | mode={requested_mode.value}")

        # Determine which models we need for the requested mode
        required_models = self._get_required_models_for_mode(requested_mode)
        missing_models = [
            m for m in required_models if not context.models_available.get(m, False)
        ]

        if not missing_models:
            logger.info("MODEL_LOADER: no_missing_models | download not needed")
            return context

        # Attempt downloads
        download_results = {}
        for model_id in missing_models:
            try:
                logger.info(f"MODEL_LOADER: downloading | model_id={model_id}")
                success = self.downloader.download_model(model_id)
                download_results[model_id] = success

                if success:
                    # Update context with newly available model
                    model_config = self._get_model_config(model_id)
                    status = ModelStatus(
                        id=model_id,
                        available=True,
                        path=Path(model_config["local_path"]),
                        size_mb=model_config.get("size_mb"),
                    )
                    context.set_model_status(model_id, status)

            except ModelDownloadError as e:
                logger.error(
                    f"MODEL_LOADER: download_failed | model_id={model_id} error={e}"
                )
                download_results[model_id] = False
                context.add_reason(ModeReason.DOWNLOAD_FAILED, f"model_id={model_id}")

        # Re-evaluate mode based on new availability
        successful_downloads = [m for m, success in download_results.items() if success]
        if successful_downloads:
            # Rescan available models
            available_models = self._scan_available_models()

            # Re-determine mode
            updated_context = self.mode_manager.determine_mode(
                requested_mode=requested_mode, available_models=available_models
            )

            # Preserve download-related reasons
            for reason in context.reasons:
                if reason not in updated_context.reasons:
                    updated_context.reasons.append(reason)

            logger.info(
                f"MODEL_LOADER: download_complete | downloaded={successful_downloads} "
                f"final_mode={updated_context.mode.value}"
            )

            return updated_context

        logger.warning("MODEL_LOADER: download_failed | no_models_downloaded")
        context.add_reason(ModeReason.DOWNLOAD_FAILED, "all_downloads_failed")
        return context

    def _get_required_models_for_mode(self, mode: AIMode) -> List[str]:
        """Get list of models required for a specific mode."""
        if mode == AIMode.RULES_ONLY:
            return []

        all_models = list(self.models_config.get("models", {}).keys())

        if mode == AIMode.FULL_AI:
            return all_models
        if mode == AIMode.PARTIAL_AI:
            essential_models = self.mode_manager._get_essential_models()
            return [m for m in essential_models if m in all_models]

        return []

    def _load_model_impl(
        self, model_id: str, model_config: Dict[str, Any]
    ) -> LoadResult:
        """
        Actual model loading implementation.

        This method handles the specifics of loading different types of models.
        """
        start_time = time.time()

        try:
            purpose = model_config.get("purpose")
            local_path = Path(model_config["local_path"])

            if purpose == "zero_shot":
                model = self._load_zero_shot_model(local_path)
            elif purpose == "ner":
                model = self._load_ner_model(local_path)
            elif purpose == "embedding":
                model = self._load_embedding_model(local_path)
            else:
                raise ValueError(f"Unknown model purpose: {purpose}")

            load_time_ms = (time.time() - start_time) * 1000
            memory_usage_mb = self._estimate_model_memory(model)

            return LoadResult(
                success=True,
                model=model,
                load_time_ms=load_time_ms,
                memory_usage_mb=memory_usage_mb,
                from_cache=False,
            )

        except Exception as e:
            load_time_ms = (time.time() - start_time) * 1000
            logger.error(f"MODEL_LOADER: load_failed | model_id={model_id} error={e}")

            return LoadResult(success=False, error=str(e), load_time_ms=load_time_ms)

    def _load_zero_shot_model(self, local_path: Path):
        """Load zero-shot classification model."""
        try:
            from transformers import pipeline

            return pipeline(
                "zero-shot-classification",
                model=str(local_path),
                local_files_only=True,
                return_all_scores=True,
            )
        except ImportError:
            raise ImportError("transformers library required for zero-shot models")

    def _load_ner_model(self, local_path: Path):
        """Load NER model."""
        try:
            from transformers import pipeline

            return pipeline(
                "ner",
                model=str(local_path),
                local_files_only=True,
                aggregation_strategy="simple",
            )
        except ImportError:
            raise ImportError("transformers library required for NER models")

    def _load_embedding_model(self, local_path: Path):
        """Load sentence embedding model."""
        try:
            from sentence_transformers import SentenceTransformer

            return SentenceTransformer(str(local_path), local_files_only=True)
        except ImportError:
            raise ImportError(
                "sentence-transformers library required for embedding models"
            )

    def _estimate_model_memory(self, model) -> float:
        """Estimate memory usage of loaded model in MB."""
        # Basic estimation - could be improved with actual memory profiling
        try:
            if hasattr(model, "model") and hasattr(model.model, "num_parameters"):
                # Transformer model - rough estimation
                num_params = model.model.num_parameters()
                return (num_params * 4) / (
                    1024 * 1024
                )  # 4 bytes per parameter (float32)
            else:
                # Fallback estimation
                return 512.0  # Default estimate
        except:
            return 512.0


# Convenience functions
def load_model_for_feature(
    feature_name: str, models_config_path: str = "config/models.yaml"
) -> Any:
    """
    Load the required model for a specific feature.

    Args:
        feature_name: Feature name (e.g., "section_classification")
        models_config_path: Path to models configuration

    Returns:
        Loaded model or None if not available

    Raises:
        MissingArtifactError: If required model not available
    """
    # Load configuration to determine required model
    with open(models_config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    feature_requirements = config.get("feature_requirements", {})
    if feature_name not in feature_requirements:
        raise ValueError(f"Unknown feature: {feature_name}")

    required_models = feature_requirements[feature_name].get("required_models", [])
    if not required_models:
        raise ValueError(f"No required models specified for feature: {feature_name}")

    # Load the first required model (could be enhanced to load all)
    loader = ModelLoader(models_config_path)
    return loader.load_artifact(required_models[0])


# Export main classes
__all__ = [
    "ModelLoader",
    "LoadResult",
    "MissingArtifactError",
    "load_model_for_feature",
]
