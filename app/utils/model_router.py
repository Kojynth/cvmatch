"""
Model Router
============

Routes CV generation to the most appropriate implementation
based on model configuration and available hardware.
"""

from typing import Any, Dict, Optional, Callable
from loguru import logger

from .profile_highlights import collect_profile_highlights, build_cover_letter_from_highlights, resolve_cover_letter_language
try:
    from .model_config_manager import model_config_manager
except Exception:
    model_config_manager = None  # Fallback if unavailable during import
    logger = logger


class ModelRouter:




    """Orchestrates generation (heavy LLM, adaptive worker, lightweight)."""

    def __init__(self):
        # Lazy loading to avoid circular imports
        self._qwen_manager = None
        self._lightweight = None
        self._adaptive = None
        self._last_model_config = None

    def _get_qwen_manager(self):
        if self._qwen_manager is None:
            from ..workers.llm_worker import QwenManager
            self._qwen_manager = QwenManager()
        return self._qwen_manager

    def _get_lightweight(self):
        if self._lightweight is None:
            from .lightweight_model import LightweightCVGenerator
            self._lightweight = LightweightCVGenerator()
        return self._lightweight

    def _get_adaptive(self):
        if self._adaptive is None:
            from ..workers.adaptive_llm_worker import AdaptiveQwenManager
            self._adaptive = AdaptiveQwenManager()
        return self._adaptive

    def _load_selected_model_config(self):
        """Refresh the selected model configuration and sync Qwen manager."""
        if model_config_manager is None:
            return None
        try:
            config = model_config_manager.get_current_config()
            self._last_model_config = config
            if self._qwen_manager is not None:
                try:
                    self._qwen_manager._load_selected_model_config()
                except Exception as exc:  # pragma: no cover - best effort
                    logger.warning(f"Unable to refresh Qwen manager: {exc}")
            return config
        except Exception as exc:
            logger.warning(f"Model configuration unavailable: {exc}")
            return self._last_model_config

    def generate_cv(
        self,
        prompt: str,
        profile: Any,
        offer_data: Dict[str, Any],
        template: str,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        """Generate a CV via the best available backend."""

        config = self._load_selected_model_config()
        model_id = getattr(config, "model_id", None) if config else None
        language = resolve_cover_letter_language(profile, offer_data)

        # 1) Primary LLM (e.g. Qwen)
        try:
            if model_id and any(k in model_id.lower() for k in ["qwen", "qwen2", "qwen2.5"]):
                qwen = self._get_qwen_manager()
                if progress_callback:
                    progress_callback("[ModelRouter] Using configured Qwen model...")
                return qwen.generate_cv(prompt, progress_callback)
        except Exception as exc:
            logger.error(f"Qwen generation error - falling back to adaptive: {exc}")

        # 2) Adaptive worker
        try:
            adaptive = self._get_adaptive()
            if progress_callback:
                progress_callback("[ModelRouter] Adaptive mode engaged...")
            return adaptive.generate_cv_adaptive(
                prompt,
                progress_callback,
                profile=profile,
                offer_data=offer_data,
            )
        except Exception as exc:
            logger.error(f"Adaptive generation error - falling back to lightweight: {exc}")

        # 3) Lightweight template engine
        lightweight = self._get_lightweight()
        if progress_callback:
            progress_callback("[ModelRouter] Lightweight fallback in use...")
        try:
            return lightweight.generate_cv(profile, offer_data, template, progress_callback)
        except Exception as exc:
            logger.error(f"Lightweight generator error: {exc}")
            return "# CV - Generation unavailable\n\nPlease retry after restarting."

    def generate_cover_letter(
        self,
        prompt: str,
        profile: Any,
        offer_data: Dict[str, Any],
        template: str,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        """Generate a cover letter using the best available backend."""

        config = self._load_selected_model_config()
        model_id = getattr(config, "model_id", None) if config else None
        language = resolve_cover_letter_language(profile, offer_data)

        try:
            if model_id and any(k in model_id.lower() for k in ["qwen", "qwen2", "qwen2.5"]):
                qwen = self._get_qwen_manager()
                if progress_callback:
                    progress_callback("[ModelRouter] Cover letter via Qwen...")
                return qwen.generate_cover_letter(
                    prompt,
                    progress_callback,
                    profile=profile,
                    offer_data=offer_data,
                )
        except Exception as exc:
            logger.error(f"Cover letter via Qwen failed: {exc}")

        if progress_callback:
            progress_callback("[ModelRouter] Cover letter fallback in use...")
        highlights = collect_profile_highlights(profile)
        return build_cover_letter_from_highlights(profile, offer_data, highlights, language=language)

    def _build_cover_letter_fallback(self, profile: Any, offer_data: Dict[str, Any]) -> str:
        """Generate a structured cover letter when no LLM output is available."""
        highlights = collect_profile_highlights(profile)
        language = resolve_cover_letter_language(profile, offer_data)
        return build_cover_letter_from_highlights(profile, offer_data, highlights, language=language)


