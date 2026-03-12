"""
QwenManager
===========

Gestionnaire pour les modèles IA (Qwen, etc.). Nommé QwenManager car historique.
Extrait de llm_worker.py pour réduire la taille du fichier principal.
"""
import inspect
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    from ..config import DEFAULT_PII_CONFIG
    from ..logging.safe_logger import get_safe_logger

    logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)
except ImportError:
    import logging

    logger = logging.getLogger(__name__)

try:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from transformers.utils import logging as transformers_logging

    transformers_logging.set_verbosity_error()
    os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
    os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"
    os.environ["TRANSFORMERS_VERBOSITY"] = "error"
    alloc_conf = str(os.getenv("PYTORCH_ALLOC_CONF") or "").strip()
    if not alloc_conf:
        os.environ["PYTORCH_ALLOC_CONF"] = "expandable_segments:True"
    elif "expandable_segments" not in alloc_conf.lower():
        os.environ["PYTORCH_ALLOC_CONF"] = f"{alloc_conf},expandable_segments:True"

    TRANSFORMERS_AVAILABLE = True
    TORCH_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Dépendances IA non disponibles ({e}) - Mode simulation activé")
    TRANSFORMERS_AVAILABLE = False
    TORCH_AVAILABLE = False

    class MockTorch:
        device = lambda x: None
        cuda = type("cuda", (), {"is_available": lambda: False, "empty_cache": lambda: None})()
        no_grad = lambda: type("context", (), {"__enter__": lambda self: None, "__exit__": lambda self, *args: None})()
        float16 = "float16"
        float32 = "float32"

    torch = MockTorch()

from ..utils.generation_role_params import DEFAULT_ROLE_PARAMS as DEFAULT_ROLE_PARAMS_EXTRACTED
from ..utils.gpu_memory_budget import build_max_memory_map_detailed as build_max_memory_map_util
from ..utils.gpu_memory_budget import estimate_model_size_gb as estimate_model_size_gb_budget
from ..utils.gpu_memory_budget import get_vram_headroom_gb as get_vram_headroom_util
from ..utils.language_policy import normalize_language_code as normalize_language_code_policy
from ..utils.memory_preflight_check import check_memory_before_load as check_memory_before_load_preflight
from ..utils.model_registry import model_registry
from ..utils.model_resolution import ModelCandidate
from ..utils.model_resolution import select_fallback_model as select_fallback_model_util
from ..utils.qwen_memory_manager import QwenMemoryManager
from ..utils.survival_mode_selector import (
    get_survival_config,
    is_memory_pressure_failure,
)
from ..utils.survival_mode_selector import is_writer_stage as is_writer_stage_survival
from ..utils.survival_mode_selector import (
    pick_survival_model,
)
from ..utils.worker_base import trim_text as trim_text_worker

try:
    from ..utils.gpu_utils import gpu_manager
except ImportError:
    class MockGPUManager:
        gpu_info = {"available": False}

        def recommend_quantization(self, *args, **kwargs):
            return {
                "device": "cpu",
                "dtype": "float32",
                "load_in_8bit": False,
                "load_in_4bit": False,
                "reason": "Mock mode",
            }

        def optimize_for_inference(self):
            pass

        def get_memory_stats(self):
            return {"gpu_available": False}

    gpu_manager = MockGPUManager()

try:
    from ..utils.model_optimizer import model_optimizer
except ImportError:
    class MockModelOptimizer:
        def check_hf_xet_status(self):
            return {"optimizations_active": False}

        def optimize_model_download(self, model_name, progress_callback=None, force_download=False):
            if progress_callback:
                progress_callback("Téléchargement standard...")
            return model_name

    model_optimizer = MockModelOptimizer()


# Module-level aliases used by QwenManager
_normalize_language = normalize_language_code_policy
_estimate_model_size_gb = estimate_model_size_gb_budget
_trim_text = trim_text_worker


class QwenManager:
    """Gestionnaire pour les modèles IA avec support multi-modèles."""
    _instance = None

    _model = None

    _tokenizer = None

    _device = None

    _current_model_path = None

    # Delegate to extracted generation_role_params module

    DEFAULT_ROLE_PARAMS = DEFAULT_ROLE_PARAMS_EXTRACTED
    UNIVERSAL_WRITER_RECIPE: Dict[str, Dict[str, Any]] = {
        "generator": {
            "temperature": 0.36,
            "top_p": 0.92,
            "top_k": 60,
            "max_input_tokens": 2600,
            "max_new_tokens": 2200,
            "max_total_tokens": 5200,
            "repetition_penalty": 1.06,
            "do_sample": True,
        },
        "cover_letter": {
            "temperature": 0.36,
            "top_p": 0.92,
            "top_k": 60,
            "max_input_tokens": 2600,
            "max_new_tokens": 1200,
            "max_total_tokens": 5200,
            "repetition_penalty": 1.08,
            "do_sample": True,
        },
    }

    def __new__(cls, model_version: str = "base"):
        """Singleton pour éviter de recharger le modèle."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, model_version: str = "base"):

        if hasattr(self, "_initialized"):
            return

        self.model_version = model_version
        self.model_loaded = False
        self.model_name = "Qwen/Qwen2.5-7B-Instruct"  # Par défaut
        self._selected_model_id = "qwen2-7b"
        self.current_loader = "transformers"
        self.custom_parameters: Dict[str, Any] = {}
        self.role_params: Dict[str, Any] = {}
        self._llama_cpp_server = None
        self._optimization_config = None
        self._current_model_path = None
        self._last_max_memory_map_details: Dict[str, Any] = {}
        self._runtime_custom_overrides: Dict[str, Any] = {}
        self._runtime_force_hybrid_load: bool = False
        self._runtime_memory_pressure: Dict[str, Any] = {}
        self._last_generation_error: str = ""
        self._meta_recovery_mode: bool = False
        self._ram_assist_mode: bool = False
        self._hybrid_cpu_reload_active: bool = False

        self._runtime_stage_name: str = ""

        # Sprint 8.1: Delegate memory management to QwenMemoryManager

        self._memory_manager: Optional[QwenMemoryManager] = None

        self.last_model_resolution_note: Optional[str] = None
        self._initialized = True

        # Charger la configuration du modèle sélectionné
        self._load_selected_model_config()

        # Initialize memory manager after custom_parameters are set

        self._memory_manager = QwenMemoryManager(custom_parameters=self.custom_parameters)

    def _load_selected_model_config(self):
        """Charge la configuration du modèle sélectionné par l'utilisateur."""
        try:
            from ..utils.model_config_manager import model_config_manager
            from ..utils.model_manager import model_manager

            self.last_model_resolution_note = None

            # Récupérer le modèle sélectionné
            config = model_config_manager.get_current_config()
            self.custom_parameters = getattr(config, "custom_parameters", None) or {}

            # Toujours tenter le modele choisi par l'utilisateur, meme si incompatible

            if config.model_id not in getattr(model_manager, "available_models", []):
                self.last_model_resolution_note = (
                    f"Warning: modele '{config.model_id}' incompatible selon le garde-fou. "
                    "Tentative de chargement quand meme."
                )
                logger.warning(self.last_model_resolution_note)

            model_info = model_manager.get_model_info(config.model_id)

            if model_info:
                self._selected_model_id = str(config.model_id or "").strip()
                self.model_name = model_info.model_path
                self.current_model_id = config.model_id
                self.current_loader = getattr(model_info, "loader", "transformers") or "transformers"

                self.role_params = (getattr(model_info, "metadata", None) or {}).get("role_params", {})

                if getattr(model_info, "quantization", "") == "nf4":
                    self.custom_parameters.setdefault("force_4bit_nf4", True)

                if self._is_repo_auth_required_without_token(self.model_name):
                    note = (
                        f"[MODEL_ACCESS] '{config.model_id}' requires HF auth token. "
                        "Keeping selected model (no automatic model fallback)."
                    )
                    self.last_model_resolution_note = note
                    logger.warning(note)

                logger.info(f"Configuration modèle: {config.model_id} -> {self.model_name}")
            else:
                logger.warning(f"Modele {config.model_id} non trouve, utilisation du registre dynamique")

                fallback = model_registry.select_profile(
                    {
                        "available": model_manager.gpu_info.get("available", False),
                        "vram_gb": model_manager.gpu_info.get("vram_gb", 0),
                        "ram_gb": getattr(model_manager, "system_ram_gb", 0),
                    }
                )

                if fallback:
                    self._selected_model_id = str(fallback.key or "").strip()
                    self.model_name = fallback.model_id
                    self.current_model_id = fallback.key
                    self.current_loader = getattr(fallback, "loader", None) or "transformers"

                    self.role_params = (getattr(fallback, "extra", None) or {}).get("role_params", {})

                    if getattr(fallback, "quantization", "") == "nf4":
                        self.custom_parameters.setdefault("force_4bit_nf4", True)
                    logger.info(f"Fallback registre -> {fallback.key} ({self.model_name})")
                else:
                    logger.warning("Aucun profil registre disponible, conservation du modèle par défaut")

        except ImportError:
            logger.warning("Configuration centralisée non disponible, modèle par défaut")
        except Exception as e:
            logger.error(f"Erreur chargement config modèle: {e}")

    @staticmethod
    def _has_hf_auth_token() -> bool:

        token_candidates = (
            os.getenv("HF_TOKEN"),
            os.getenv("HUGGINGFACE_HUB_TOKEN"),
            os.getenv("HF_API_TOKEN"),
        )

        return any(str(token or "").strip() for token in token_candidates)

    def _is_repo_auth_required_without_token(self, model_ref: Optional[str]) -> bool:

        repo = str(model_ref or "").strip().lower()

        if not repo:
            return False

        # Local paths / GGUF files are not gated by HF auth.

        if "\\" in repo or ":" in repo or repo.endswith(".gguf"):
            return False

        if self._has_hf_auth_token():
            return False

        gated_prefixes = ("meta-llama/",)

        return any(repo.startswith(prefix) for prefix in gated_prefixes)

    def apply_model_profile(self, model_id: str, *, reason: str = "") -> bool:
        """Applique explicitement un profil de modèle (utile pour routage par stage)."""
        target_id = str(model_id or "").strip()

        if not target_id:
            return False

        selected_id = self._get_selected_model_id()
        if (
            self._is_selected_model_lock_enabled()
            and selected_id
            and target_id.lower() != selected_id.lower()
        ):
            logger.info(
                "[MODEL_LOCK] Ignored model switch to '%s' (selected='%s', reason=%s)",
                target_id,
                selected_id,
                reason or "-",
            )
            return False

        from ..utils.model_manager import model_manager

        model_info = model_manager.get_model_info(target_id)

        if not model_info:
            raise ValueError(f"Unknown model profile: {target_id}")

        current_id = str(getattr(self, "current_model_id", "") or "")

        if current_id == target_id:
            return False

        target_model_path = str(getattr(model_info, "model_path", "") or "")

        if self.model_loaded and self._current_model_path and self._current_model_path != target_model_path:
            self.unload_model(reason=f"switch model -> {target_id}")

        self.model_name = target_model_path

        self.current_model_id = target_id

        self.current_loader = getattr(model_info, "loader", "transformers") or "transformers"

        self.role_params = (getattr(model_info, "metadata", None) or {}).get("role_params", {})

        if getattr(model_info, "quantization", "") == "nf4":
            self.custom_parameters.setdefault("force_4bit_nf4", True)

        note = f"[MODEL_SWITCH] {current_id or 'unknown'} -> {target_id}" + (f" ({reason})" if reason else "")

        self.last_model_resolution_note = note

        logger.info(note)

        return True

    def set_runtime_stage(self, stage: Optional[str]) -> None:

        stage_key = str(stage or "").strip().lower()

        self._runtime_stage_name = stage_key

    def _get_runtime_stage_name(self) -> str:

        stage_key = str(getattr(self, "_runtime_stage_name", "") or "").strip().lower()

        if stage_key:
            return stage_key

        return str(os.getenv("CVMATCH_STAGE_NAME", "") or "").strip().lower()

    def _is_writer_stage(self, stage: Optional[str] = None) -> bool:
        """Delegate to survival_mode_selector utility."""
        stage_key = str(stage or self._get_runtime_stage_name()).strip()

        return is_writer_stage_survival(stage_key)

    def _get_survival_writer_min_size_gb(self) -> float:

        custom = self.custom_parameters or {}

        default_floor = 3.0

        try:
            if "survival_writer_min_size_b" in custom:
                default_floor = float(custom.get("survival_writer_min_size_b"))

        except Exception:
            pass

        raw_env = os.getenv("CVMATCH_SURVIVAL_WRITER_MIN_SIZE_B")

        if raw_env is not None:
            try:
                default_floor = float(raw_env)

            except Exception:
                pass

        return max(0.0, default_floor)

    def _is_extractor_stage(self, stage: Optional[str] = None) -> bool:
        stage_key = str(stage or self._get_runtime_stage_name()).strip().lower()
        return stage_key in {"offer_keywords", "profile_extraction"}

    def _get_global_fallback_min_size_gb(self) -> float:
        custom = self.custom_parameters or {}
        default_floor = 1.5

        try:
            if "fallback_min_size_b" in custom:
                default_floor = float(custom.get("fallback_min_size_b"))
        except Exception:
            pass

        raw_env = os.getenv("CVMATCH_FALLBACK_MIN_SIZE_B")
        if raw_env is not None:
            try:
                default_floor = float(raw_env)
            except Exception:
                pass

        return max(0.0, default_floor)

    def _get_global_fallback_max_size_gb(self) -> float:
        custom = self.custom_parameters or {}
        default_ceiling = 0.0

        try:
            if "fallback_max_size_b" in custom:
                default_ceiling = float(custom.get("fallback_max_size_b"))
        except Exception:
            pass

        raw_env = os.getenv("CVMATCH_FALLBACK_MAX_SIZE_B")
        if raw_env is not None:
            try:
                default_ceiling = float(raw_env)
            except Exception:
                pass

        # Optional global small-footprint mode: avoid large fallback candidates.
        small_mode = self._to_bool(
            os.getenv("CVMATCH_SMALL_MODELS_ONLY"),
            self._to_bool(custom.get("small_models_only"), False),
        )
        if small_mode and default_ceiling <= 0:
            default_ceiling = 2.0

        return max(0.0, default_ceiling)

    def _build_fallback_min_size_candidates(self, stage: Optional[str] = None) -> List[float]:
        stage_key = str(stage or self._get_runtime_stage_name()).strip().lower()
        global_floor = self._get_global_fallback_min_size_gb()
        candidates: List[float] = []

        if self._is_writer_stage(stage_key):
            writer_floor = max(global_floor, self._get_survival_writer_min_size_gb())
            candidates.extend([writer_floor, global_floor])
        elif self._is_extractor_stage(stage_key):
            candidates.append(global_floor)
        else:
            candidates.append(global_floor)

        deduped: List[float] = []
        seen: set = set()
        for value in candidates:
            key = round(float(value), 3)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(float(value))
        return deduped

    def _resolve_fallback_candidate(
        self,
        available_ram_gb: float,
        available_vram_gb: float = 0.0,
        *,
        stage: Optional[str] = None,
        excluded_repo_prefixes: Optional[List[str]] = None,
        prefer_quality: Optional[bool] = None,
        ram_fit_ratio: float = 0.92,
        require_memory_fit: bool = True,
    ) -> Optional[Dict[str, str]]:
        stage_key = str(stage or self._get_runtime_stage_name()).strip().lower()
        prefer_quality_value = self._is_writer_stage(stage_key) if prefer_quality is None else bool(prefer_quality)

        fallback = None
        for min_size in self._build_fallback_min_size_candidates(stage_key):
            fallback = self._pick_fallback_model_for_memory(
                available_ram_gb,
                available_vram_gb,
                min_model_size_gb=min_size,
                excluded_repo_prefixes=excluded_repo_prefixes,
                prefer_quality=prefer_quality_value,
                ram_fit_ratio=ram_fit_ratio,
                require_memory_fit=require_memory_fit,
            )
            if fallback and fallback.get("model_id") and fallback.get("model_path"):
                return fallback

        return None

    def _resolve_role_params(self, role: str, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:

        defaults = dict(self.DEFAULT_ROLE_PARAMS.get(role, {}))
        model_overrides = self.role_params.get(role, {}) if self.role_params else {}
        merged = {**defaults, **model_overrides}
        if self._is_universal_writer_recipe_enabled():
            role_key = str(role or "").strip().lower()
            if role_key in ("generator", "cover_letter", "letter"):
                recipe = self.UNIVERSAL_WRITER_RECIPE.get(
                    "cover_letter" if role_key in ("cover_letter", "letter") else "generator",
                    {},
                )
                if recipe:
                    merged.update(recipe)
        if overrides:
            merged.update(overrides)
        return merged

    @staticmethod
    def _to_bool(value: Any, default: bool = False) -> bool:

        if value is None:
            return default
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("1", "true", "yes", "y", "on")

    def _is_universal_writer_recipe_enabled(self) -> bool:
        custom = self.custom_parameters or {}
        env_value = os.getenv("CVMATCH_UNIVERSAL_MINISTRAL_RECIPE")
        if env_value is not None:
            return self._to_bool(env_value, True)
        return self._to_bool(custom.get("universal_ministral_recipe"), True)

    def _allow_model_fallback(self) -> bool:
        # Product policy: never auto-switch to a smaller/different model.
        # Keep user's selected model and rely on subprocess/offload recovery paths.
        return False

    def _is_selected_model_lock_enabled(self) -> bool:
        custom = self.custom_parameters or {}
        keep_selected = self._to_bool(custom.get("keep_selected_stage_model"), True)
        env_keep = os.getenv("CVMATCH_KEEP_SELECTED_STAGE_MODEL")
        if env_keep is not None:
            keep_selected = self._to_bool(env_keep, True)
        if not self._allow_model_fallback():
            keep_selected = True
        return bool(keep_selected)

    def _get_selected_model_id(self) -> str:
        selected = str(getattr(self, "_selected_model_id", "") or "").strip()
        if selected:
            return selected
        return str(getattr(self, "current_model_id", "") or "").strip()

    def _enforce_selected_model_lock(self, *, reason: str = "") -> None:
        if not self._is_selected_model_lock_enabled():
            return
        selected_id = self._get_selected_model_id()
        current_id = str(getattr(self, "current_model_id", "") or "").strip()
        if not selected_id:
            return
        if current_id.lower() == selected_id.lower():
            return
        try:
            from ..utils.model_manager import model_manager

            info = model_manager.get_model_info(selected_id)
            if not info:
                return
            self.model_name = str(getattr(info, "model_path", "") or self.model_name)
            self.current_model_id = selected_id
            self.current_loader = getattr(info, "loader", "transformers") or "transformers"
            self.role_params = (getattr(info, "metadata", None) or {}).get("role_params", {})
            note = (
                f"[MODEL_LOCK] Restored selected model '{selected_id}' (was '{current_id or 'unknown'}')"
                + (f" ({reason})" if reason else "")
            )
            self.last_model_resolution_note = note
            logger.warning(note)
        except Exception:
            pass

    def _get_effective_custom_parameters(self) -> Dict[str, Any]:
        """Return custom parameters merged with non-persistent runtime overrides."""
        merged = dict(self.custom_parameters or {})
        runtime = getattr(self, "_runtime_custom_overrides", None) or {}
        for key, value in runtime.items():
            merged[key] = value
        if getattr(self, "_meta_recovery_mode", False):
            # Avoid disk/meta sharding after a meta tensor failure.
            merged["disk_offload"] = False
            merged["offload_state_dict"] = False
            merged["disable_torch_compile"] = True
        if getattr(self, "_ram_assist_mode", False) and self._prefer_ram_offload_mode():
            # RAM-assist keeps the selected model and shifts pressure to host RAM.
            merged["disk_offload"] = False
            merged["offload_state_dict"] = False
            merged["disable_torch_compile"] = True
            try:
                cpu_pct = float(merged.get("max_memory_cpu_percent") or 0.0)
            except Exception:
                cpu_pct = 0.0
            if cpu_pct < 92.0:
                merged["max_memory_cpu_percent"] = 92
            try:
                headroom = float(merged.get("cpu_headroom_gb") or 2.0)
            except Exception:
                headroom = 2.0
            if headroom > 0.75:
                merged["cpu_headroom_gb"] = 0.75
        return merged

    def _prefer_ram_offload_mode(self) -> bool:
        custom = self.custom_parameters or {}
        env_value = os.getenv("CVMATCH_PREFER_RAM_OFFLOAD")
        if env_value is not None:
            return self._to_bool(env_value, False)
        return self._to_bool(custom.get("prefer_ram_offload"), False)

    def _apply_ram_budget_floor(self) -> None:
        """Raise CPU budget to keep 7B alive on RAM before failing on VRAM."""
        if not self._prefer_ram_offload_mode():
            return
        runtime = self._runtime_custom_overrides

        try:
            cpu_pct = float(runtime.get("max_memory_cpu_percent") or self.custom_parameters.get("max_memory_cpu_percent") or 0.0)
        except Exception:
            cpu_pct = 0.0
        floor = 95.0 if getattr(self, "_ram_assist_mode", False) else 92.0
        if cpu_pct < floor:
            runtime["max_memory_cpu_percent"] = int(floor)

        try:
            headroom = float(runtime.get("cpu_headroom_gb") or self.custom_parameters.get("cpu_headroom_gb") or 2.0)
        except Exception:
            headroom = 2.0
        cap = 0.5
        if headroom > cap:
            runtime["cpu_headroom_gb"] = cap

        runtime["disk_offload"] = False
        runtime["offload_state_dict"] = False
        runtime["disable_torch_compile"] = True

    def _activate_ram_assist_mode(self, *, reason: str = "", progress_callback=None) -> None:
        if not self._prefer_ram_offload_mode():
            logger.info("RAM assist ignored: prefer_ram_offload is disabled.")
            return
        if getattr(self, "_ram_assist_mode", False):
            return
        self._ram_assist_mode = True
        self._runtime_force_hybrid_load = True
        self._apply_ram_budget_floor()
        note = (
            "[RECOVERY] RAM assist enabled - keeping selected model and increasing CPU RAM budget "
            "(disk offload disabled)."
        )
        if reason:
            note = f"{note} Reason={reason}."
        self.last_model_resolution_note = note
        logger.warning(note)
        if progress_callback:
            try:
                progress_callback(note)
            except Exception:
                pass

    @staticmethod
    def _is_meta_tensor_error(error: Any) -> bool:
        lowered = str(error or "").strip().lower()
        return "meta tensor" in lowered or "cannot copy out of meta tensor" in lowered

    def _activate_meta_recovery_mode(self, *, reason: str = "", progress_callback=None) -> None:
        if getattr(self, "_meta_recovery_mode", False):
            return
        self._meta_recovery_mode = True
        self._runtime_force_hybrid_load = True
        self._apply_ram_budget_floor()
        note = (
            "[RECOVERY] Meta tensor failure detected - reloading current model with RAM-first policy "
            "(no disk offload)."
        )
        if reason:
            note = f"{note} Stage={reason}."
        self.last_model_resolution_note = note
        logger.warning(note)
        if progress_callback:
            try:
                progress_callback(note)
            except Exception:
                pass

    def _get_lowram_profile(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Delegate to QwenMemoryManager for LowRAM profile."""
        if self._memory_manager is None:
            # Fallback if memory manager not yet initialized

            return {"level": "normal", "platform": os.name, "reason": "memory_manager_not_ready"}

        return self._memory_manager.get_lowram_profile(force_refresh=force_refresh)

    def _collect_memory_pressure_snapshot(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Collect RAM/commit/VRAM signals for non-survival runtime tuning."""
        profile = self._get_lowram_profile(force_refresh=force_refresh) or {}
        lowram_level = str(profile.get("level") or "normal").strip().lower()
        ram_available_gb = float(profile.get("ram_available_gb") or 0.0)
        effective_available_gb = float(profile.get("effective_available_gb") or 0.0)
        commit_available_gb = float(profile.get("commit_available_gb") or 0.0)
        free_vram_gb = float(self._get_free_vram_gb() or 0.0)
        total_vram_gb = float(self._get_total_vram_gb() or 0.0)
        vram_free_ratio = (free_vram_gb / total_vram_gb) if total_vram_gb > 0 else 0.0
        stage_name = self._get_runtime_stage_name()
        writer_stage = self._is_writer_stage(stage_name)

        pressure_level = lowram_level if lowram_level in {"tight", "critical"} else "normal"
        if pressure_level == "normal":
            if (
                (effective_available_gb > 0 and effective_available_gb < 4.0)
                or (ram_available_gb > 0 and ram_available_gb < 3.0)
                or (commit_available_gb > 0 and commit_available_gb < 5.0)
                or (total_vram_gb > 0 and vram_free_ratio < 0.28)
            ):
                pressure_level = "elevated"
        if pressure_level == "elevated":
            if (commit_available_gb > 0 and commit_available_gb < 3.5) or (
                total_vram_gb > 0 and free_vram_gb < 1.2
            ):
                pressure_level = "tight"

        return {
            "pressure_level": pressure_level,
            "lowram_level": lowram_level,
            "ram_available_gb": ram_available_gb,
            "effective_available_gb": effective_available_gb,
            "commit_available_gb": commit_available_gb,
            "free_vram_gb": free_vram_gb,
            "total_vram_gb": total_vram_gb,
            "vram_free_ratio": vram_free_ratio,
            "stage_name": stage_name,
            "writer_stage": writer_stage,
        }

    def _apply_non_survival_memory_tuning(self, progress_callback=None) -> None:
        """Apply generic memory-pressure tuning without enabling survival mode."""
        self._runtime_custom_overrides = {}
        self._runtime_force_hybrid_load = False
        self._runtime_memory_pressure = {}

        if self._is_survival_mode():
            return
        if not isinstance(self._optimization_config, dict):
            return
        if str(self._optimization_config.get("device") or "cpu") != "cuda":
            return

        snapshot = self._collect_memory_pressure_snapshot(force_refresh=True)
        self._runtime_memory_pressure = dict(snapshot)
        pressure = str(snapshot.get("pressure_level") or "normal")
        if pressure not in {"elevated", "tight", "critical"}:
            return

        writer_stage = bool(snapshot.get("writer_stage"))
        target_util = 0.72
        target_max_len = 3072 if writer_stage else 2048
        gpu_percent = 68 if writer_stage else 62
        cpu_percent = 85
        cpu_headroom = 2.0

        if pressure == "tight":
            target_util = 0.64 if writer_stage else 0.60
            target_max_len = 2048 if writer_stage else 1536
            gpu_percent = 62 if writer_stage else 55
            cpu_percent = 78
            cpu_headroom = 2.5
        elif pressure == "critical":
            target_util = 0.58 if writer_stage else 0.55
            target_max_len = 1536 if writer_stage else 1024
            gpu_percent = 58 if writer_stage else 50
            cpu_percent = 72
            cpu_headroom = 3.0

        try:
            current_util = float(self._optimization_config.get("gpu_memory_utilization") or 0.0)
        except Exception:
            current_util = 0.0
        if current_util <= 0 or current_util > target_util:
            self._optimization_config["gpu_memory_utilization"] = target_util

        try:
            current_max_len = int(self._optimization_config.get("max_model_len") or 0)
        except Exception:
            current_max_len = 0
        if current_max_len <= 0 or current_max_len > target_max_len:
            self._optimization_config["max_model_len"] = target_max_len

        self._runtime_custom_overrides.update(
            {
                "max_memory_gpu_percent": gpu_percent,
                "max_memory_cpu_percent": cpu_percent,
                "cpu_headroom_gb": cpu_headroom,
                "disk_offload": False if self._prefer_ram_offload_mode() else True,
                "offload_state_dict": False if self._prefer_ram_offload_mode() else True,
                "disable_torch_compile": pressure in {"tight", "critical"},
            }
        )
        self._runtime_force_hybrid_load = pressure in {"tight", "critical"}

        base_reason = str(self._optimization_config.get("reason") or "auto")
        self._optimization_config["reason"] = (
            f"{base_reason} + pressure({pressure}, max_len={target_max_len}, gpu_util={target_util:.2f})"
        )

        logger.info(
            "Runtime memory-pressure tuning applied: pressure=%s stage=%s ram=%.1fGB commit=%.1fGB free_vram=%.1fGB "
            "max_len=%s gpu_util=%.2f gpu%%=%s cpu%%=%s force_hybrid=%s",
            pressure,
            snapshot.get("stage_name") or "-",
            float(snapshot.get("ram_available_gb") or 0.0),
            float(snapshot.get("commit_available_gb") or 0.0),
            float(snapshot.get("free_vram_gb") or 0.0),
            int(self._optimization_config.get("max_model_len") or 0),
            float(self._optimization_config.get("gpu_memory_utilization") or 0.0),
            gpu_percent,
            cpu_percent,
            self._runtime_force_hybrid_load,
        )
        if progress_callback:
            try:
                progress_callback(
                    f"[MEMORY] Pressure={pressure}: tuning max_len={target_max_len}, gpu_util={target_util:.2f}"
                )
            except Exception:
                pass

    def _is_lowram_tight_or_critical(self) -> bool:
        """Delegate to QwenMemoryManager."""
        if self._memory_manager is None:
            return False

        return self._memory_manager.is_lowram_tight_or_critical()

    def _get_runtime_memory_mode(self) -> str:
        """Delegate to QwenMemoryManager."""
        if self._memory_manager is None:
            return "CPU/Unknown"

        return self._memory_manager.get_runtime_memory_mode()

    def _get_survival_max_model_len(self) -> int:

        lowram_level = str(self._get_lowram_profile().get("level") or "normal")

        total_vram = self._get_total_vram_gb()

        stage_name = self._get_runtime_stage_name()

        writer_stage = self._is_writer_stage(stage_name)

        if lowram_level == "critical":
            # Keep more context for writer stages; quality matters more than speed.

            return 1536 if writer_stage else 1024

        if lowram_level == "tight":
            return 2048 if writer_stage else 1536

        if total_vram > 0 and total_vram <= 6.5:
            return 2048 if writer_stage else 1536

        return 2048

    def _is_survival_mode(self) -> bool:

        raw_env = os.getenv("CVMATCH_SURVIVAL_MODE")

        # Quality-first policy: survival is explicit env opt-in only.

        if raw_env is None:
            return False

        return self._to_bool(raw_env, False)

    @staticmethod
    def _is_memory_pressure_failure_reason(reason: str) -> bool:
        """Delegate to survival_mode_selector utility."""
        return is_memory_pressure_failure(reason)

    @staticmethod
    def _is_download_or_cache_failure_reason(reason: str) -> bool:
        lowered = str(reason or "").strip().lower()
        if not lowered:
            return False

        markers = (
            "not enough free disk space",
            "no space left on device",
            "disk quota exceeded",
            "insufficient disk space",
            "model download blocked by policy",
            "allowed llm families",
            "filenotfounderror",
            "no such file or directory",
            "errno 28",
            "os error 28",
            "safetensors",
            "model-0000",
            "\\snapshots\\",
            "file reconstruction error",
            "internal writer error",
            "failed to send data",
            "receiver dropped",
            "snapshot_download",
            "cache_dir",
        )
        return any(marker in lowered for marker in markers)

    def _record_failure(self, reason: str) -> None:
        """Delegate to QwenMemoryManager for failure tracking."""
        if self._memory_manager is not None:
            self._memory_manager.record_failure(reason)

        else:
            logger.warning("Failure recorded (no memory manager): %s", str(reason or "")[:240])

    def _record_success(self, reason: str = "") -> None:
        """Delegate to QwenMemoryManager for success tracking."""
        if self._memory_manager is not None:
            self._memory_manager.record_success(reason)

    def _set_last_generation_error(self, reason: str) -> None:
        self._last_generation_error = str(reason or "").strip()

    def _clear_last_generation_error(self) -> None:
        self._last_generation_error = ""

    def get_last_generation_error(self, *, clear: bool = False) -> str:
        message = str(getattr(self, "_last_generation_error", "") or "").strip()
        if clear:
            self._last_generation_error = ""
        return message

    def _get_survival_gpu_budget_cap_gb(self, total_vram_gb: float) -> float:

        total_vram = float(total_vram_gb or 0.0)

        lowram_level = str(self._get_lowram_profile().get("level") or "normal")

        if total_vram <= 0:
            return 3.5 if lowram_level == "critical" else 4.0

        if total_vram <= 6.5:
            abs_cap = 3.5 if lowram_level == "critical" else 4.0

        elif total_vram <= 8.5:
            abs_cap = 4.5 if lowram_level in {"tight", "critical"} else 5.0

        elif total_vram <= 12.0:
            abs_cap = 6.5

        else:
            abs_cap = 8.0

        percent_cap = 0.55 if lowram_level in {"tight", "critical"} else 0.60

        return min(abs_cap, total_vram * percent_cap)

    def _pick_survival_model_override(
        self, available_ram_gb: float, available_vram_gb: float
    ) -> Optional[Dict[str, Any]]:
        """Delegate to survival_mode_selector utility."""
        try:
            from ..utils.model_manager import model_manager

        except Exception:
            return None

        # Build candidate list from model_manager

        model_ids = list(getattr(model_manager, "available_models", []) or [])

        if not model_ids:
            model_ids = list(getattr(model_manager, "_models_map", {}).keys())

        model_candidates: List[Dict[str, Any]] = []

        for model_id in model_ids:
            info = model_manager.get_model_info(model_id)

            if not info:
                continue

            model_candidates.append(
                {
                    "model_id": model_id,
                    "model_path": str(getattr(info, "model_path", "") or ""),
                    "loader": getattr(info, "loader", "transformers") or "transformers",
                    "metadata": getattr(info, "metadata", None) or {},
                    "vram_required": float(getattr(info, "vram_required", 0) or 0),
                    "quality_stars": float(getattr(info, "quality_stars", 0) or 0),
                    "speed_rating": float(getattr(info, "speed_rating", 0) or 0),
                }
            )

        if not model_candidates:
            return None

        # Get context for survival model selection

        stage_name = self._get_runtime_stage_name()

        lowram_level = str(self._get_lowram_profile().get("level") or "normal")

        config = get_survival_config(custom_parameters=self.custom_parameters)

        # Define RAM estimation callback

        def estimate_ram_fn(model_path: str, model_id: str) -> float:

            return self._estimate_required_ram_gb(
                model_name=model_path,
                model_id=model_id,
            )

        # Delegate to survival_mode_selector

        result = pick_survival_model(
            available_ram_gb=available_ram_gb,
            available_vram_gb=available_vram_gb,
            model_candidates=model_candidates,
            stage_name=stage_name,
            lowram_level=lowram_level,
            config=config,
            estimate_ram_fn=estimate_ram_fn,
        )

        return result.to_dict() if result else None

    def _apply_survival_model_override(self, progress_callback=None) -> None:
        if not self._is_survival_mode():
            return

        custom = self.custom_parameters or {}
        ignore_selected = True
        if "survival_ignore_selected_model" in custom:
            ignore_selected = self._to_bool(custom.get("survival_ignore_selected_model"), True)

        raw_env = os.getenv("CVMATCH_SURVIVAL_IGNORE_SELECTED_MODEL")
        if raw_env is not None:
            ignore_selected = self._to_bool(raw_env, True)
        if not ignore_selected:
            logger.info(
                "[SURVIVAL] Override disabled by config/env for stage '%s'; keeping selected model '%s'.",
                self._get_runtime_stage_name() or "unknown",
                str(getattr(self, "current_model_id", "") or "unknown"),
            )

            return

        try:
            import psutil
            available_ram_gb = psutil.virtual_memory().available / (1024**3)
        except Exception:
            available_ram_gb = 0.0
        available_vram_gb = self._get_free_vram_gb()

        lowram_level = str(self._get_lowram_profile().get("level") or "normal")

        stage_name = self._get_runtime_stage_name()

        current_id = str(getattr(self, "current_model_id", "") or "")

        # Quality-first guard: in tight low RAM, keep the selected model as-is.

        if lowram_level == "tight":
            logger.info(
                "[SURVIVAL] Stage '%s' with lowram=tight: preserving model '%s'.",
                stage_name or "unknown",
                current_id or "unknown",
            )

            return

        choice = self._pick_survival_model_override(
            available_ram_gb=available_ram_gb,
            available_vram_gb=available_vram_gb,
        )
        if not choice:
            return

        next_id = str(choice.get("model_id") or "")
        if not next_id or current_id == next_id:
            return

        self.model_name = str(choice.get("model_path") or self.model_name)
        self.current_model_id = next_id
        self.current_loader = str(choice.get("loader") or "transformers")
        metadata = choice.get("metadata")
        if isinstance(metadata, dict):
            self.role_params = metadata.get("role_params") or self.role_params

        note = (
            f"[SURVIVAL] Mode actif: override modele '{current_id or 'inconnu'}' -> "
            f"'{self.current_model_id}' (ram_dispo={available_ram_gb:.1f}GB, "
            f"vram_dispo={available_vram_gb:.1f}GB)."
        )
        self.last_model_resolution_note = note
        logger.warning(note)
        if progress_callback:
            try:
                progress_callback(note)
            except Exception:
                pass

    def _should_unload_between_stages(self) -> bool:
        if self._is_survival_mode():
            return True
        env_flag = os.getenv("CVMATCH_UNLOAD_BETWEEN_STAGES")
        if env_flag is not None:
            return env_flag.strip().lower() in ("1", "true", "yes", "y")
        custom = self.custom_parameters or {}
        if "unload_between_stages" in custom:
            return bool(custom.get("unload_between_stages"))
        return self._is_survival_mode()

    def _should_unload_after_generation(self) -> bool:
        if self._is_survival_mode():
            return True
        env_flag = os.getenv("CVMATCH_UNLOAD_AFTER_RUN")
        if env_flag is not None:
            return env_flag.strip().lower() in ("1", "true", "yes", "y")

        custom = self.custom_parameters or {}
        if "unload_after_run" in custom:
            return bool(custom.get("unload_after_run"))

        # Check recycle policy via memory manager

        if self._memory_manager is not None and self._memory_manager.should_recycle_model():
            return True

        if self._is_survival_mode():
            return True

        # Auto mode: si la marge VRAM est faible en fin de run, on libère le modèle.
        if not TORCH_AVAILABLE or not torch.cuda.is_available():
            return False
        free_vram = self._get_free_vram_gb()
        if free_vram <= 0:
            return False
        headroom = self._get_vram_headroom_gb(free_vram_gb=free_vram)
        return free_vram < max(1.0, headroom)

    @staticmethod
    def _get_total_vram_gb() -> float:

        total_vram = 0.0
        try:
            total_vram = float(getattr(gpu_manager, "gpu_info", {}).get("total_memory_gb", 0) or 0)

        except Exception:
            total_vram = 0.0
        if total_vram > 0:
            return total_vram
        try:
            total_vram = float(getattr(gpu_manager, "gpu_info", {}).get("vram_gb", 0) or 0)

        except Exception:
            total_vram = 0.0
        if total_vram > 0:
            return total_vram
        if TORCH_AVAILABLE and torch.cuda.is_available():
            try:
                if hasattr(torch.cuda, "mem_get_info"):
                    _, total_bytes = torch.cuda.mem_get_info()
                    return total_bytes / (1024**3)
            except Exception:
                pass
        return 0.0

    def _get_vram_mode(self) -> str:
        env_mode = os.getenv("CVMATCH_VRAM_MODE")
        if env_mode:
            mode = env_mode.strip().lower()
            if mode in {"auto", "low", "med", "high"}:
                return mode
        custom_mode = (self.custom_parameters or {}).get("vram_mode")
        if isinstance(custom_mode, str):
            mode = custom_mode.strip().lower()
            if mode in {"auto", "low", "med", "high"}:
                return mode
        return "auto"

    def _is_low_vram_mode(self) -> bool:
        mode = self._get_vram_mode()
        if mode == "low":
            return True
        if mode in {"med", "high"}:
            return False
        total_vram = self._get_total_vram_gb()
        return total_vram > 0 and total_vram <= 8.0

    def _is_med_vram_mode(self) -> bool:
        mode = self._get_vram_mode()
        if mode == "med":
            return True
        if mode in {"low", "high"}:
            return False
        total_vram = self._get_total_vram_gb()
        return total_vram > 8.0 and total_vram <= 12.0

    def _get_recycle_every_runs(self) -> int:
        if self._is_survival_mode():
            return 1
        env_value = os.getenv("CVMATCH_RECYCLE_EVERY_RUNS")
        if env_value is not None:
            try:
                return max(0, int(env_value))
            except Exception:
                return 0
        custom = self.custom_parameters or {}
        if "recycle_every_runs" in custom:
            try:
                return max(0, int(custom.get("recycle_every_runs")))
            except Exception:
                return 0
        if self._is_low_vram_mode():
            return 1
        if self._is_med_vram_mode():
            return 2
        return 0

    def mark_run_completed(self) -> None:
        """Delegate to QwenMemoryManager for run tracking."""
        if self._memory_manager is not None:
            self._memory_manager.mark_run_completed()

    def generate_structured_json_lmfe(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: Dict[str, Any],
        role: str,
        progress_callback=None,
        role_params: Optional[Dict[str, Any]] = None,
    ) -> str:

        from ..utils.json_strict import JsonStrictError, build_lmfe_generation_kwargs

        if getattr(self, "current_loader", "transformers") != "transformers":
            raise JsonStrictError("Strict JSON requires transformers (in-process) loader.")

        if not self.model_loaded:
            self.load_model(
                progress_callback,
                allow_fallback=self._allow_model_fallback(),
            )

        if not TRANSFORMERS_AVAILABLE or self._model is None or self._tokenizer is None:
            raise JsonStrictError("Transformers model not available for strict JSON.")

        params = self._resolve_role_params(role, role_params)

        max_input_tokens = int(params.get("max_input_tokens") or 2048)

        max_new_tokens = int(params.get("max_new_tokens") or 512)

        max_total_tokens = int(params.get("max_total_tokens") or 0) or None

        temperature = float(params.get("temperature") or 0.2)

        top_p = float(params.get("top_p") or 0.9)

        top_k = int(params.get("top_k") or 50)

        formatted_prompt = self._build_generic_prompt(system_prompt, user_prompt)

        inputs = self._tokenizer(
            formatted_prompt,
            return_tensors="pt",
            truncation=True,
            max_length=max_input_tokens,
        ).to(self._device)

        input_len = int(inputs.input_ids.shape[1])

        if max_total_tokens:
            max_new_tokens = max(1, min(max_new_tokens, max_total_tokens - input_len))

        slow_device = self._detect_slow_device()

        if slow_device:
            max_new_tokens = min(max_new_tokens, 900)

        lmfe_kwargs = build_lmfe_generation_kwargs(self._tokenizer, schema)

        use_cache = self._resolve_kv_cache(progress_callback)

        if not use_cache:
            if role == "generator":
                max_new_tokens = min(max_new_tokens, 1100)

            else:
                max_new_tokens = min(max_new_tokens, 900)

        if slow_device:
            logger.info("Strict JSON slow mode: cap max_new_tokens=%s", max_new_tokens)

        if not use_cache:
            logger.info(
                "Strict JSON no-cache mode: role=%s cap max_new_tokens=%s",
                role,
                max_new_tokens,
            )

        with torch.no_grad():
            generate_kwargs = {
                "max_new_tokens": max_new_tokens,
                "temperature": max(temperature, 0.0),
                "top_p": top_p,
                "top_k": top_k,
                "do_sample": temperature > 0.0,
                "repetition_penalty": 1.05,
                "pad_token_id": self._tokenizer.eos_token_id,
                "eos_token_id": self._tokenizer.eos_token_id,
                "use_cache": use_cache,
                **lmfe_kwargs,
            }

            outputs = self._model.generate(**inputs, **generate_kwargs)

        generated_text = self._tokenizer.decode(
            outputs[0][inputs.input_ids.shape[1] :],
            skip_special_tokens=True,
        )

        return self._extract_structured_content(generated_text)

    def _check_first_download(self, progress_callback=None):
        """Vérifie si c'est le premier téléchargement du modèle."""
        try:
            from pathlib import Path

            # Chemins de cache possibles
            cache_paths = [
                Path.home() / ".cache" / "huggingface" / "transformers",
                Path.home() / ".cache" / "huggingface" / "hub",
            ]

            model_cached = False
            for cache_path in cache_paths:
                if cache_path.exists():
                    # Chercher des traces du modèle dans le cache
                    for item in cache_path.iterdir():
                        if self.model_name.split("/")[-1].lower() in item.name.lower():
                            model_cached = True
                            break
                if model_cached:
                    break

            if not model_cached and progress_callback:
                model_display_name = getattr(self, "current_model_id", self.model_name.split("/")[-1])

                progress_callback(f"⏳ Premier téléchargement de {model_display_name}")
                progress_callback("📥 Le téléchargement peut prendre plusieurs minutes selon votre connexion...")
                progress_callback("💾 Le modèle sera mis en cache pour les prochaines utilisations")

        except Exception as e:
            logger.warning(f"Impossible de vérifier le cache: {e}")

    def _estimate_required_ram_gb(
        self,
        *,
        model_name: Optional[str] = None,
        model_id: Optional[str] = None,
        optimization: Optional[Dict[str, Any]] = None,
    ) -> float:
        """Heuristique: estime la RAM (GB) requise pour charger le modèle."""
        opt = dict(optimization or (self._optimization_config or {}))

        # If no runtime optimization is set yet, infer quantization from model config.

        if not opt:
            custom = self.custom_parameters or {}

            if self._to_bool(custom.get("force_4bit_nf4"), False):
                opt["load_in_4bit"] = True

            else:
                try:
                    from ..utils.model_manager import model_manager

                    info = model_manager.get_model_info(str(model_id or getattr(self, "current_model_id", "") or ""))

                except Exception:
                    info = None

                quant = str(getattr(info, "quantization", "") or "").strip().lower()

                if quant in {"nf4", "int4", "4bit", "gguf_q4"}:
                    opt["load_in_4bit"] = True

                elif quant in {"int8", "8bit"}:
                    opt["load_in_8bit"] = True

        dtype = opt.get("dtype")
        params_b = _estimate_model_size_gb(
            model_name or self.model_name,
            model_id or getattr(self, "current_model_id", None),
        )

        if opt.get("load_in_4bit"):
            gb_per_b = 0.5
        elif opt.get("load_in_8bit"):
            gb_per_b = 1.0
        else:
            dtype_str = str(dtype).lower() if dtype is not None else ""
            is_fp16_family = dtype in (
                getattr(torch, "float16", None),
                getattr(torch, "bfloat16", None),
            )
            if is_fp16_family or "float16" in dtype_str or "bfloat16" in dtype_str:
                gb_per_b = 2.0
            else:
                gb_per_b = 4.0

        overhead_factor = 1.10
        overhead_constant = 0.8
        return max(1.5, params_b * gb_per_b * overhead_factor + overhead_constant)

    def _pick_fallback_model_for_memory(
        self,
        available_ram_gb: float,
        available_vram_gb: float = 0.0,
        *,
        min_model_size_gb: float = 0.0,
        excluded_repo_prefixes: Optional[List[str]] = None,
        prefer_quality: bool = False,
        ram_fit_ratio: float = 0.92,
        require_memory_fit: bool = False,
    ) -> Optional[Dict[str, str]]:
        """Delegate to model_resolution utility for fallback model selection.



        Builds ModelCandidate list from model_manager, then uses the

        select_fallback_model utility for memory-aware selection.

        """
        try:
            from ..utils.model_manager import model_manager

        except Exception:
            return None

        current_id = getattr(self, "current_model_id", None)

        model_ids = [mid for mid in getattr(model_manager, "available_models", []) if mid and mid != current_id]

        if not model_ids:
            return None

        # Build ModelCandidate list

        candidates: List[ModelCandidate] = []

        for model_id in model_ids:
            info = model_manager.get_model_info(model_id)

            if not info:
                continue

            model_path = str(getattr(info, "model_path", "") or "")

            candidates.append(
                ModelCandidate(
                    model_id=model_id,
                    model_path=model_path,
                    required_ram_gb=self._estimate_required_ram_gb(model_name=model_path, model_id=model_id),
                    required_vram_gb=float(getattr(info, "vram_required", 0) or 0),
                    quality_stars=float(getattr(info, "quality_stars", 0) or 0),
                    speed_rating=float(getattr(info, "speed_rating", 0) or 0),
                    estimated_size_gb=float(_estimate_model_size_gb(model_name=model_path, model_id=model_id)),
                )
            )

        max_model_size_gb = self._get_global_fallback_max_size_gb()
        if max_model_size_gb > 0:
            candidates = [
                candidate
                for candidate in candidates
                if float(getattr(candidate, "estimated_size_gb", 0.0) or 0.0)
                <= max_model_size_gb
            ]
            if not candidates:
                logger.warning(
                    "Fallback model size cap filtered all candidates (max=%.2fB).",
                    max_model_size_gb,
                )
                return None

        result = select_fallback_model_util(
            candidates,
            available_ram_gb,
            available_vram_gb,
            min_size_gb=min_model_size_gb,
            excluded_prefixes=excluded_repo_prefixes,
            prefer_quality=prefer_quality,
            ram_fit_ratio=ram_fit_ratio,
        )

        if result.model_id:
            if require_memory_fit and not bool(getattr(result, "memory_fit", True)):
                return None
            return {"model_id": result.model_id, "model_path": result.model_path}

        return None

    @staticmethod
    def _is_model_access_restricted_error(message: str) -> bool:

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

    @staticmethod
    def _extract_repo_prefix(model_ref: Optional[str]) -> str:

        value = str(model_ref or "").strip().lower()

        if not value:
            return ""

        # Heuristic: HF repo id looks like "owner/repo" (single slash, no drive letter/backslashes).

        if "\\" in value or ":" in value or value.count("/") != 1:
            return ""

        owner, _ = value.split("/", 1)

        owner = owner.strip()

        if not owner:
            return ""

        return f"{owner}/"

    def _check_memory_before_load(self) -> tuple:
        """Delegate to memory_preflight_check utility.



        Returns:

            tuple: (can_proceed: bool, error_message: str or None)

        """
        try:
            effective_custom = self._get_effective_custom_parameters()

            stage_attempt = 1

            try:
                stage_attempt = max(1, int(os.getenv("CVMATCH_STAGE_ATTEMPT", "1")))

            except Exception:
                stage_attempt = 1

            result = check_memory_before_load_preflight(
                model_name=self.model_name,
                model_id=getattr(self, "current_model_id", None),
                device=(self._optimization_config or {}).get("device", "cpu"),
                custom_parameters=effective_custom,
                optimization_config=self._optimization_config,
                is_survival_mode=self._is_survival_mode(),
                stage_name=self._get_runtime_stage_name(),
                stage_attempt=stage_attempt,
            )

            return (result.can_proceed, result.error_message)

        except Exception as e:
            logger.warning(f"Erreur vérification mémoire: {e}")

            return True, None

    @staticmethod
    def _get_free_vram_gb() -> float:

        if not TORCH_AVAILABLE or not torch.cuda.is_available():
            return 0.0
        try:
            if hasattr(torch.cuda, "mem_get_info"):
                free_bytes, _ = torch.cuda.mem_get_info()
                return free_bytes / (1024**3)
        except Exception:
            pass
        try:
            if hasattr(gpu_manager, "get_available_vram"):
                return float(gpu_manager.get_available_vram())
        except Exception:
            pass
        return 0.0

    def _get_vram_headroom_gb(
        self,
        free_vram_gb: Optional[float] = None,
        total_vram_gb: Optional[float] = None,
        custom_parameters: Optional[Dict[str, Any]] = None,
    ) -> float:
        """Delegate to gpu_memory_budget utility for VRAM headroom calculation.



        Headroom ensures stability during generation by reserving VRAM

        for KV cache and other temporary allocations.

        """
        effective_custom = (
            custom_parameters
            if isinstance(custom_parameters, dict)
            else self._get_effective_custom_parameters()
        )

        return get_vram_headroom_util(
            custom_parameters=effective_custom,
            free_vram_gb=free_vram_gb,
            total_vram_gb=total_vram_gb,
            survival_mode=self._is_survival_mode(),
        )

    def _should_disable_kv_cache(self) -> bool:
        if not TORCH_AVAILABLE or not torch.cuda.is_available():
            return False
        if self._is_survival_mode():
            return True
        custom = self.custom_parameters or {}
        try:
            threshold = float(custom.get("disable_kv_cache_below_gb", 0) or 0)
        except Exception:
            threshold = 0.0
        if threshold <= 0:
            try:
                total_vram = float(getattr(gpu_manager, "gpu_info", {}).get("total_memory_gb", 0) or 0)
            except Exception:
                total_vram = 0.0
            if self._is_low_vram_mode() and total_vram > 0:
                threshold = max(1.8, min(3.0, total_vram * 0.28))
            elif total_vram > 0:
                threshold = max(1.0, min(2.5, total_vram * 0.12))
            else:
                threshold = 1.5
        free_vram = self._get_free_vram_gb()
        return free_vram > 0 and free_vram < threshold

    def _detect_slow_device(self) -> bool:
        """Return True if the active device is CPU-based or non-CUDA.



        Checks both ``self._device.type`` and the model's ``hf_device_map``

        (for multi-GPU / CPU-offload configurations).  Used to select conservative

        token budgets and longer timeouts.

        """
        slow_device = False

        try:
            if getattr(self._device, "type", None) == "cpu":
                slow_device = True

        except Exception:
            pass

        try:
            device_map = getattr(self._model, "hf_device_map", None)

            if isinstance(device_map, dict) and device_map:
                for value in device_map.values():
                    resolved = self._normalize_device_target(value)

                    if resolved is None:
                        continue

                    if resolved.type != "cuda":
                        slow_device = True

                        break

        except Exception:
            pass

        return slow_device

    def _resolve_kv_cache(self, progress_callback=None) -> bool:
        """Return False (and log a VRAM warning) if the KV cache should be disabled.



        Wraps ``_should_disable_kv_cache`` with a user-visible progress callback

        and structured logger warning.  Returns True when cache is safe to use.

        """
        try:
            if getattr(self._device, "type", None) == "cuda" and self._should_disable_kv_cache():
                free_vram = self._get_free_vram_gb()

                note = f"[WARN] VRAM faible ({free_vram:.1f}GB) : KV cache désactivé."

                logger.warning(note)

                if progress_callback:
                    progress_callback(note)

                return False

        except Exception:
            pass

        return True

    def _build_max_memory_map(self) -> Optional[Dict[Union[int, str], str]]:
        """Delegate to gpu_memory_budget utility for max_memory map computation."""
        # Gather context for the utility function
        effective_custom = self._get_effective_custom_parameters()

        try:
            total_vram = float(gpu_manager.gpu_info.get("total_memory_gb", 0) or 0)

        except Exception:
            total_vram = 0.0

        lowram_level = str(self._get_lowram_profile().get("level") or "normal")

        is_survival = self._is_survival_mode()

        # Get headroom and survival cap

        free_vram_gb = 0.0

        try:
            if TORCH_AVAILABLE and torch.cuda.is_available() and hasattr(torch.cuda, "mem_get_info"):
                free_bytes, _ = torch.cuda.mem_get_info()

                free_vram_gb = free_bytes / (1024**3)

        except Exception:
            free_vram_gb = total_vram

        headroom_gb = self._get_vram_headroom_gb(
            free_vram_gb=free_vram_gb,
            total_vram_gb=total_vram,
            custom_parameters=effective_custom,
        )

        survival_cap_gb = 0.0

        if is_survival:
            survival_cap_gb = self._get_survival_gpu_budget_cap_gb(total_vram or free_vram_gb)

        # Delegate to utility

        result = build_max_memory_map_util(
            custom_parameters=effective_custom,
            is_survival_mode=is_survival,
            lowram_level=lowram_level,
            total_vram_gb=total_vram,
            free_vram_gb=free_vram_gb,
            headroom_gb=headroom_gb,
            survival_cap_gb=survival_cap_gb,
        )

        # Store details for diagnostics

        self._last_max_memory_map_details = result.details

        return result.memory_map

    @staticmethod
    def _patch_bitsandbytes_params4bit() -> None:

        try:
            import bitsandbytes as bnb
        except Exception:
            return

        params_cls = getattr(getattr(bnb, "nn", None), "Params4bit", None)
        if params_cls is None:
            return

        if getattr(params_cls, "_cvmatch_patched", False):
            return

        has_arg = False
        try:
            sig = inspect.signature(params_cls.__new__)
            has_arg = "_is_hf_initialized" in sig.parameters
        except Exception:
            code = getattr(params_cls.__new__, "__code__", None)
            if code and "_is_hf_initialized" in code.co_varnames:
                has_arg = True

        if has_arg:
            return

        original_new = params_cls.__new__

        def _patched_new(cls, *args, **kwargs):
            kwargs.pop("_is_hf_initialized", None)
            return original_new(cls, *args, **kwargs)

        params_cls.__new__ = staticmethod(_patched_new)
        params_cls._cvmatch_patched = True
        logger.warning("Patched bitsandbytes Params4bit for _is_hf_initialized compat.")

    @staticmethod
    def _normalize_device_target(target: Any) -> Optional["torch.device"]:

        if not TORCH_AVAILABLE:
            return None
        if isinstance(target, torch.device):
            return target
        if isinstance(target, int):
            return torch.device(f"cuda:{target}")
        if isinstance(target, str):
            if target in ("cpu", "mps", "meta"):
                return torch.device("cpu")
            if target.startswith("cuda"):
                return torch.device(target)
            if target == "disk":
                return torch.device("cpu")
        return None

    @staticmethod
    def _fmt_bytes(value: Optional[int]) -> str:

        if value is None:
            return "n/a"

        return f"{value / (1024 ** 3):.2f}GB"

    @staticmethod
    def _log_cuda_mem(label: str) -> None:

        if os.getenv("CVMATCH_VRAM_DEBUG", "").strip() != "1":
            return
        if not TORCH_AVAILABLE or not torch.cuda.is_available():
            return

        free_bytes = total_bytes = None
        allocated = reserved = None
        max_allocated = max_reserved = None
        try:
            free_bytes, total_bytes = torch.cuda.mem_get_info()
        except Exception:
            pass
        try:
            allocated = torch.cuda.memory_allocated()
        except Exception:
            pass
        try:
            reserved = torch.cuda.memory_reserved()
        except Exception:
            pass
        try:
            max_allocated = torch.cuda.max_memory_allocated()
        except Exception:
            pass
        try:
            max_reserved = torch.cuda.max_memory_reserved()
        except Exception:
            pass

        logger.info(
            "VRAM[%s]: free=%s total=%s alloc=%s reserved=%s max_alloc=%s max_reserved=%s",
            label,
            QwenManager._fmt_bytes(free_bytes),
            QwenManager._fmt_bytes(total_bytes),
            QwenManager._fmt_bytes(allocated),
            QwenManager._fmt_bytes(reserved),
            QwenManager._fmt_bytes(max_allocated),
            QwenManager._fmt_bytes(max_reserved),
        )
        if allocated is not None and reserved is not None and reserved >= allocated:
            cached = reserved - allocated
            logger.info(
                "VRAM[%s] cache=%s (PyTorch allocator cache, expected while process stays alive)",
                label,
                QwenManager._fmt_bytes(cached),
            )

    def _resolve_input_device(self) -> Optional["torch.device"]:
        """Pick the input device matching the model's device map."""
        if not TORCH_AVAILABLE or self._model is None:
            return None

        try:
            embeddings = self._model.get_input_embeddings()
            if embeddings is not None and hasattr(embeddings, "weight"):
                weight = embeddings.weight
                if weight is not None and hasattr(weight, "device"):
                    device = weight.device
                    if hasattr(device, "type") and device.type != "meta":
                        return device
        except Exception:
            pass

        device_map = getattr(self._model, "hf_device_map", None)
        if isinstance(device_map, dict) and device_map:
            preferred_keys = (
                "model.embed_tokens",
                "model.decoder.embed_tokens",
                "transformer.wte",
                "model.wte",
                "gpt_neox.embed_in",
                "embed_tokens",
                "wte",
            )
            target = None
            for key in preferred_keys:
                if key in device_map:
                    target = device_map[key]
                    break
            if target is None:
                for key, value in device_map.items():
                    if "embed" in key.lower():
                        target = value
                        break
            if target is None:
                for value in device_map.values():
                    if value not in ("disk", "meta"):
                        target = value
                        break
            resolved = self._normalize_device_target(target)
            if resolved is not None:
                return resolved

        try:
            return torch.device("cuda" if torch.cuda.is_available() else "cpu")
        except Exception:
            return None

    def _summarize_device_map(self) -> Dict[str, int]:
        """Return a compact device map summary for logging."""
        summary: Dict[str, int] = {}
        device_map = getattr(self._model, "hf_device_map", None)
        if not isinstance(device_map, dict) or not device_map:
            return summary
        for value in device_map.values():
            resolved = self._normalize_device_target(value)
            if resolved is None:
                key = str(value)
            else:
                key = str(resolved) if resolved.type == "cuda" else resolved.type
            summary[key] = summary.get(key, 0) + 1
        return summary

    def _load_llama_cpp_model(self, progress_callback=None) -> None:
        """Démarre (si besoin) un serveur llama.cpp local pour un modèle GGUF."""
        try:
            import os

            from ..utils.llama_cpp_server import LlamaCppServer, LlamaCppServerConfig

        except Exception as exc:
            raise RuntimeError("Support llama.cpp indisponible (dépendances manquantes).") from exc

        model_path_value = (
            (self.custom_parameters or {}).get("llama_cpp_model_path")
            or os.getenv("CVMATCH_LLAMA_CPP_MODEL_PATH")
            or self.model_name
        )
        model_path = Path(str(model_path_value)).expanduser()
        if not model_path.is_absolute():
            repo_root = Path(__file__).resolve().parents[2]
            model_path = repo_root / model_path

        binary_override = (
            (self.custom_parameters or {}).get("llama_cpp_binary_path")
            or (self.custom_parameters or {}).get("llama_cpp_binary")
            or os.getenv("CVMATCH_LLAMA_CPP_BINARY")
            or os.getenv("CVMATCH_LLAMA_CPP_BIN")
        )
        binary_path = Path(str(binary_override)).expanduser() if binary_override else None

        try:
            port = int(
                (self.custom_parameters or {}).get("llama_cpp_port") or os.getenv("CVMATCH_LLAMA_CPP_PORT") or 8080
            )

        except Exception:
            port = 8080
        try:
            ctx_size = int(
                (self.custom_parameters or {}).get("llama_cpp_ctx_size") or os.getenv("CVMATCH_LLAMA_CPP_CTX") or 4096
            )

        except Exception:
            ctx_size = 4096
        try:
            threads = int(
                (self.custom_parameters or {}).get("llama_cpp_threads")
                or os.getenv("CVMATCH_LLAMA_CPP_THREADS")
                or (os.cpu_count() or 4)
            )

        except Exception:
            threads = os.cpu_count() or 4

        cfg = LlamaCppServerConfig(
            model_path=model_path,
            port=port,
            ctx_size=ctx_size,
            threads=threads,
            binary_path=binary_path,
        )

        existing = getattr(self, "_llama_cpp_server", None)

        if existing and getattr(existing, "config", None) == cfg and (existing.is_alive() or existing.is_ready()):
            self.model_loaded = True
            self._current_model_path = self.model_name
            return

        if existing:
            try:
                existing.stop()
            except Exception:
                pass

        server = LlamaCppServer(cfg)
        if progress_callback:
            progress_callback("🦙 Démarrage du serveur llama.cpp...")
        server.start(timeout_s=45.0)
        self._llama_cpp_server = server

        self.model_loaded = True
        self._current_model_path = self.model_name
        self._model = None
        self._tokenizer = None
        try:
            self._device = torch.device("cpu") if TORCH_AVAILABLE else None
        except Exception:
            self._device = None

        if progress_callback:
            progress_callback("✅ llama.cpp prêt !")

    def _llama_cpp_chat(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ) -> str:
        server = getattr(self, "_llama_cpp_server", None)
        if server is None:
            raise RuntimeError("llama.cpp server non initialisé")
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return server.chat(
            messages=messages,
            max_tokens=int(max_tokens),
            temperature=float(temperature),
            top_p=float(top_p),
        )

    # ------------------------------------------------------------------

    # Private helpers extracted from load_model

    # ------------------------------------------------------------------

    def _load_tokenizer(self, model_path: Optional[str], model_display_name: str, progress_callback=None) -> str:
        """Load the tokenizer with protobuf / sentencepiece / force-download fallbacks.



        Returns the (possibly updated) model_ref string so that a force-download

        path chosen during the last except branch is propagated back to load_model.

        """
        if progress_callback:
            progress_callback(f"[TOK] Chargement du tokenizer {model_display_name}...")

        model_ref = model_path or self.model_name

        try:
            self._tokenizer = AutoTokenizer.from_pretrained(
                model_ref,
                trust_remote_code=True,
                use_fast=True,
            )

        except ImportError as e:
            # Certains tokenizers (ex: SentencePiece -> conversion fast) requierent protobuf.

            msg = str(e).lower()

            if "protobuf" in msg or "protob" in msg:
                if progress_callback:
                    progress_callback(
                        "[WARN] Dependances manquantes (protobuf). Fallback: tokenizer lent (use_fast=False)..."
                    )

                try:
                    self._tokenizer = AutoTokenizer.from_pretrained(
                        model_ref,
                        trust_remote_code=True,
                        use_fast=False,
                    )

                except ImportError as e2:
                    msg2 = str(e2).lower()

                    if "sentencepiece" in msg2:
                        raise RuntimeError(
                            "Le tokenizer necessite 'sentencepiece'. Installez: pip install sentencepiece protobuf"
                        ) from e2

                    raise

            elif "sentencepiece" in msg:
                raise RuntimeError(
                    "Le tokenizer necessite 'sentencepiece'. Installez: pip install sentencepiece"
                ) from e

            else:
                raise

        except Exception as e:
            msg = str(e).lower()

            if any(token in msg for token in ("vocabulary", "sentencepiece", "tokenizer")):
                logger.warning("Tokenizer load failed, retrying with use_fast=False: %s", e)

                try:
                    self._tokenizer = AutoTokenizer.from_pretrained(
                        model_ref,
                        trust_remote_code=True,
                        use_fast=False,
                    )

                except Exception as e2:
                    forced_path = None

                    try:
                        forced_path = model_optimizer.optimize_model_download(
                            self.model_name,
                            progress_callback=progress_callback,
                            force_download=True,
                        )

                    except Exception as force_exc:
                        logger.warning(
                            "Force download failed after tokenizer error: %s",
                            force_exc,
                        )

                    if forced_path:
                        model_ref = forced_path

                        self._tokenizer = AutoTokenizer.from_pretrained(
                            model_ref,
                            trust_remote_code=True,
                            use_fast=False,
                        )

                    else:
                        raise e2

            else:
                raise

        return model_ref

    @staticmethod
    def _resolve_bool_setting(custom_value: Any, env_value: Optional[str], default: bool) -> bool:

        if env_value is not None:
            return str(env_value).strip().lower() in ("1", "true", "yes", "y", "on")

        if custom_value is None:
            return default

        if isinstance(custom_value, bool):
            return custom_value

        return str(custom_value).strip().lower() in ("1", "true", "yes", "y", "on")

    def _resolve_force_gpu_mode(
        self,
        effective_custom: Dict[str, Any],
        *,
        meta_recovery_mode: bool,
    ) -> bool:
        """Hybrid-only policy: never force strict CUDA-only model placement."""
        force_gpu_env = os.getenv("CVMATCH_FORCE_GPU")
        requested_force_gpu = False
        if force_gpu_env is not None:
            requested_force_gpu = force_gpu_env.strip() == "1"
        elif "force_cuda" in effective_custom:
            requested_force_gpu = self._to_bool(effective_custom.get("force_cuda"), False)

        if requested_force_gpu:
            logger.info("Hybrid-only policy active: ignoring force_cuda/CVMATCH_FORCE_GPU strict request.")

        return False

    def _is_memory_recovery_attempt(self) -> bool:
        """Return True when current load happens after a memory-related failure."""
        try:
            stage_attempt = max(1, int(os.getenv("CVMATCH_STAGE_ATTEMPT", "1")))
        except Exception:
            stage_attempt = 1
        if stage_attempt > 1:
            return True

        try:
            failures = int(getattr(self._memory_manager, "consecutive_failures", 0) or 0)
        except Exception:
            failures = 0
        if failures > 0:
            return True

        if bool(getattr(self, "_ram_assist_mode", False)):
            return True
        if bool(getattr(self, "_meta_recovery_mode", False)):
            return True
        return False

    def _should_auto_enable_disk_offload_for_4bit(self) -> Tuple[bool, str]:
        """Enable disk offload automatically for 4-bit loads after memory failures."""
        disable_auto = self._resolve_bool_setting(
            (self.custom_parameters or {}).get("disable_auto_disk_offload_4bit"),
            os.getenv("CVMATCH_DISABLE_AUTO_DISK_OFFLOAD_4BIT"),
            False,
        )
        if disable_auto:
            return False, "disabled_by_config"
        if not self._is_memory_recovery_attempt():
            return False, "first_attempt_no_recovery"

        details = (
            dict(self._last_max_memory_map_details)
            if isinstance(getattr(self, "_last_max_memory_map_details", None), dict)
            else {}
        )
        clamp_reason = str(details.get("gpu_clamp_reason") or "").strip()
        if clamp_reason:
            return True, f"gpu_budget_clamped:{clamp_reason}"

        free_vram_gb = float(self._get_free_vram_gb() or 0.0)
        total_vram_gb = float(self._get_total_vram_gb() or 0.0)
        ratio = (free_vram_gb / total_vram_gb) if total_vram_gb > 0 else 0.0
        try:
            free_threshold_gb = float(
                os.getenv("CVMATCH_AUTO_DISK_OFFLOAD_4BIT_FREE_VRAM_GB", "8.5")
            )
        except Exception:
            free_threshold_gb = 8.5
        try:
            ratio_threshold = float(
                os.getenv("CVMATCH_AUTO_DISK_OFFLOAD_4BIT_FREE_RATIO", "0.72")
            )
        except Exception:
            ratio_threshold = 0.72

        if free_vram_gb > 0 and free_vram_gb <= max(1.0, free_threshold_gb):
            return True, f"free_vram_below_threshold:{free_vram_gb:.2f}GB"
        if total_vram_gb > 0 and ratio > 0 and ratio <= max(0.10, ratio_threshold):
            return True, f"free_ratio_below_threshold:{ratio:.2f}"
        return False, ""

    def _resolve_disk_offload_enabled(
        self,
        effective_custom: Dict[str, Any],
        *,
        using_4bit: bool,
    ) -> bool:
        """Resolve disk offload policy for model loading."""
        disk_offload_enabled = self._resolve_bool_setting(
            effective_custom.get("disk_offload"),
            os.getenv("CVMATCH_DISK_OFFLOAD"),
            True,
        )

        if self._is_survival_mode():
            disk_offload_enabled = True

        if using_4bit:
            force_disk = self._resolve_bool_setting(
                effective_custom.get("force_disk_offload"),
                os.getenv("CVMATCH_FORCE_DISK_OFFLOAD"),
                False,
            )
            auto_disk, auto_reason = self._should_auto_enable_disk_offload_for_4bit()
            if force_disk:
                disk_offload_enabled = True
                logger.info("4-bit mode: disk offload forced ON by config.")
            elif auto_disk:
                disk_offload_enabled = True
                logger.warning(
                    "4-bit mode: auto-enabling disk offload on recovery path (%s).",
                    auto_reason,
                )
            elif disk_offload_enabled:
                logger.warning(
                    "4-bit mode: disk offload disabled by default to avoid meta tensor failures."
                )
                disk_offload_enabled = False

        return disk_offload_enabled

    def _build_model_load_kwargs(self) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
        """Build device/offload/quantization kwargs for AutoModelForCausalLM.from_pretrained.



        Returns:

            (model_kwargs, auto_kwargs) where auto_kwargs is the fallback dict used

            when force_gpu is True but the strict GPU load fails with OOM.

        """
        model_kwargs: Dict[str, Any] = {
            "trust_remote_code": True,
            "torch_dtype": self._optimization_config["dtype"],
        }
        effective_custom = self._get_effective_custom_parameters()
        meta_recovery_mode = bool(getattr(self, "_meta_recovery_mode", False))
        using_4bit = bool(
            (self._optimization_config or {}).get("load_in_4bit")
            or effective_custom.get("force_4bit_nf4")
            or (self.custom_parameters or {}).get("force_4bit_nf4")
        )

        if (
            self._optimization_config["device"] == "cuda"
            and using_4bit
            and self._prefer_ram_offload_mode()
            and (bool(getattr(self, "_ram_assist_mode", False)) or meta_recovery_mode)
        ):
            self._apply_ram_budget_floor()
            effective_custom = self._get_effective_custom_parameters()

        if self._is_survival_mode():
            model_kwargs["attn_implementation"] = "sdpa"

        force_gpu = False

        auto_kwargs: Optional[Dict[str, Any]] = None

        offload_folder_resolved: Optional[str] = None

        if self._optimization_config["device"] == "cuda":
            model_kwargs["device_map"] = "auto"

            max_memory = self._build_max_memory_map()

            if max_memory:
                model_kwargs["max_memory"] = max_memory

                model_kwargs["low_cpu_mem_usage"] = True

                details = getattr(self, "_last_max_memory_map_details", None)

                if details:
                    logger.info(
                        "Max memory map active: %s (details=%s)",
                        max_memory,
                        details,
                    )

                else:
                    logger.info("Max memory map active: %s", max_memory)

            else:
                logger.warning("Max memory map not set (device_map=auto). Offload disabled.")

            disk_offload_enabled = self._resolve_disk_offload_enabled(
                effective_custom,
                using_4bit=using_4bit,
            )

            if disk_offload_enabled:
                custom_offload_folder = effective_custom.get("offload_folder")

                env_offload_folder = os.getenv("CVMATCH_OFFLOAD_FOLDER")

                raw_offload_folder = env_offload_folder or custom_offload_folder

                if raw_offload_folder:
                    offload_dir = Path(str(raw_offload_folder))

                else:
                    offload_dir = Path.cwd() / "logs" / "hf_offload"

                try:
                    offload_dir.mkdir(parents=True, exist_ok=True)

                    offload_folder_resolved = str(offload_dir)

                    offload_state_default = False if using_4bit else True
                    offload_state_dict = self._resolve_bool_setting(
                        effective_custom.get("offload_state_dict"),
                        os.getenv("CVMATCH_OFFLOAD_STATE_DICT"),
                        offload_state_default,
                    )

                    if self._is_survival_mode():
                        offload_state_dict = True

                    model_kwargs["offload_folder"] = offload_folder_resolved

                    model_kwargs["offload_state_dict"] = offload_state_dict

                    logger.info(
                        "Disk offload enabled: folder=%s offload_state_dict=%s",
                        offload_folder_resolved,
                        offload_state_dict,
                    )

                except Exception as offload_exc:
                    logger.warning(
                        "Disk offload setup failed, continuing without it: %s",
                        offload_exc,
                    )

            else:
                logger.info("Disk offload disabled by config.")

            force_gpu = self._resolve_force_gpu_mode(
                effective_custom,
                meta_recovery_mode=meta_recovery_mode,
            )

        else:
            model_kwargs["device_map"] = None

        # Ajout de la quantisation si necessaire

        if self._optimization_config.get("load_in_8bit") or self._optimization_config.get("load_in_4bit"):
            try:
                import bitsandbytes  # noqa: F401

                self._patch_bitsandbytes_params4bit()

            except Exception as e:
                raise RuntimeError(
                    "Quantisation 4-bit/8-bit demandee mais 'bitsandbytes' n'est pas utilisable sur cette machine. "
                    "Installez une version compatible (CUDA) ou choisissez un modele/quantification plus leger."
                ) from e

        if self._optimization_config.get("load_in_8bit"):
            model_kwargs["load_in_8bit"] = True

        elif self._optimization_config.get("load_in_4bit"):
            quantization_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_use_double_quant=True,
                bnb_4bit_quant_type="nf4",
                llm_int8_enable_fp32_cpu_offload=True,
            )

            model_kwargs["quantization_config"] = quantization_config

        if model_kwargs.get("device_map") == "auto" and model_kwargs.get("max_memory"):
            logger.info("Hybrid load: device_map=auto with CPU offload enabled.")

        elif model_kwargs.get("device_map") == "auto":
            logger.info("device_map=auto without max_memory (no offload).")

        return model_kwargs, auto_kwargs

    def _retry_cuda_first_after_cpu_only(
        self,
        *,
        progress_callback=None,
        allow_fallback: bool = False,
    ):
        """Retry one load forcing CUDA-first when auto placement resolved to CPU-only."""
        previous_force_cuda = self._runtime_custom_overrides.get("force_cuda")
        had_force_cuda = "force_cuda" in self._runtime_custom_overrides
        previous_runtime_hybrid = bool(self._runtime_force_hybrid_load)
        self._runtime_custom_overrides["force_cuda"] = True
        self._runtime_force_hybrid_load = False
        self._hybrid_cpu_reload_active = True
        try:
            self.unload_model(reason="cpu_only_device_map")
            return self.load_model(progress_callback, allow_fallback=allow_fallback)
        finally:
            if had_force_cuda:
                self._runtime_custom_overrides["force_cuda"] = previous_force_cuda
            else:
                self._runtime_custom_overrides.pop("force_cuda", None)
            self._runtime_force_hybrid_load = previous_runtime_hybrid
            self._hybrid_cpu_reload_active = False

    def _finalize_model_load(
        self,
        model_display_name: str,
        last_load_kwargs: Dict[str, Any],
        progress_callback=None,
    ) -> None:
        """Log post-load device map, configure device, apply eval + torch.compile, and emit success callback.



        Args:

            model_display_name: Human-readable model name for log/progress messages.

            last_load_kwargs: The kwargs actually used in the successful from_pretrained call.

            progress_callback: Optional callable for progress messages.

        """
        if self._optimization_config["device"] == "cuda":
            logger.info(
                "Model load kwargs applied: device_map=%s max_memory=%s low_cpu_mem_usage=%s offload_folder=%s offload_state_dict=%s",
                last_load_kwargs.get("device_map"),
                last_load_kwargs.get("max_memory"),
                bool(last_load_kwargs.get("low_cpu_mem_usage")),
                last_load_kwargs.get("offload_folder"),
                last_load_kwargs.get("offload_state_dict"),
            )

        # Configuration pour CPU si nécessaire

        if self._optimization_config["device"] == "cpu":
            self._model = self._model.to("cpu")

            self._device = torch.device("cpu")

        else:
            resolved_device = self._resolve_input_device()

            self._device = resolved_device or torch.device("cuda")

            logger.info("Device map resolved input device: %s", self._device)

        device_summary = self._summarize_device_map()

        if device_summary:
            logger.info("Device map summary: %s", device_summary)

            if self._optimization_config["device"] == "cuda":
                has_cuda = any(str(key).startswith("cuda") for key in device_summary.keys())

                if not has_cuda:
                    free_vram = 0.0

                    try:
                        free_vram = float(gpu_manager.get_available_vram())

                    except Exception:
                        free_vram = 0.0

                    logger.warning(
                        "GPU available but model loaded on CPU (free VRAM %.2fGB).",
                        free_vram,
                    )

                    if progress_callback:
                        progress_callback("[WARN] GPU VRAM low; model loaded on CPU.")

        # Mode évaluation pour l'inférence

        self._model.eval()

        # Optimisations post-chargement

        disable_compile = False

        if os.getenv("CVMATCH_DISABLE_TORCH_COMPILE", "").strip() in ("1", "true", "yes", "y"):
            disable_compile = True

        if (self.custom_parameters or {}).get("disable_torch_compile"):
            disable_compile = True

        if self._is_survival_mode():
            disable_compile = True

        if (self._optimization_config or {}).get("load_in_4bit"):
            disable_compile = True

        if disable_compile:
            logger.info("Skip torch.compile: disabled by policy/config.")

        elif hasattr(torch, "compile") and self._device.type == "cuda":
            should_compile = True

            device_map = getattr(self._model, "hf_device_map", None)

            if isinstance(device_map, dict) and device_map:
                for value in device_map.values():
                    resolved = self._normalize_device_target(value)

                    if resolved is None:
                        continue

                    if resolved.type != "cuda":
                        should_compile = False

                        break

            if not should_compile:
                logger.info("Skip torch.compile: device_map includes CPU/disk.")

            else:
                try:
                    self._model = torch.compile(self._model, mode="reduce-overhead")

                    logger.info("Modèle compilé avec torch.compile")

                except Exception as e:
                    logger.warning(f"Compilation échouée: {e}")

        self.model_loaded = True

        self._current_model_path = self.model_name

        if self._memory_manager is not None:
            self._memory_manager.reset_run_counter()

        self._log_cuda_mem("after_load")

        # Stats mémoire finales

        memory_stats = gpu_manager.get_memory_stats()

        logger.info(f"Modèle {model_display_name} chargé - Mémoire utilisée: {memory_stats}")

        if progress_callback:
            progress_callback(f"✅ Modèle {model_display_name} chargé avec succès !")

    def _build_load_error_diagnostic(self, error_msg: str, error_code: Any) -> Tuple[str, str]:
        """Build a structured diagnostic text and a user-visible hint from a model-load error.



        Args:

            error_msg: String representation of the caught exception.

            error_code: Windows error code (winerror) or empty string.



        Returns:

            (diagnostic_text, hint) â€” both are plain strings; hint may be empty.

        """
        diagnostic_lines: List[str] = []

        diagnostic_lines.append(f"- model_id: {getattr(self, 'current_model_id', None)}")

        diagnostic_lines.append(f"- model_name: {getattr(self, 'model_name', None)}")

        try:
            opt = dict(self._optimization_config or {})

            dtype = opt.get("dtype")

            if dtype is not None:
                opt["dtype"] = str(dtype)

            diagnostic_lines.append(f"- optimization: {opt}")

        except Exception:
            pass

        try:
            import psutil  # type: ignore

            mem = psutil.virtual_memory()

            diagnostic_lines.append(f"- ram_total_gb: {mem.total / (1024**3):.1f}")

            diagnostic_lines.append(f"- ram_available_gb: {mem.available / (1024**3):.1f}")

        except Exception:
            pass

        try:
            diagnostic_lines.append(f"- torch_available: {TORCH_AVAILABLE}")

            if TORCH_AVAILABLE:
                diagnostic_lines.append(f"- torch_cuda_available: {torch.cuda.is_available()}")

        except Exception:
            pass

        try:
            diagnostic_lines.append(f"- gpu_info: {getattr(gpu_manager, 'gpu_info', None)}")

            if hasattr(gpu_manager, "get_available_vram"):
                diagnostic_lines.append(f"- vram_available_gb: {gpu_manager.get_available_vram():.1f}")

        except Exception:
            pass

        hint = ""

        lowered = error_msg.lower()

        if "cuda out of memory" in lowered or "out of memory" in lowered:
            hint = (
                "Piste: mémoire GPU/RAM insuffisante. "
                "Ajustez le budget mémoire GPU/CPU ou choisissez un modèle plus léger."
            )

        elif "protobuf" in lowered or "protob" in lowered:
            hint = (
                "Piste: dépendance manquante 'protobuf'. Installez: pip install protobuf "
                "(et souvent aussi: pip install sentencepiece), puis redémarrez l'application."
            )

        elif "sentencepiece" in lowered:
            hint = (
                "Piste: dépendance manquante 'sentencepiece'. Installez: pip install sentencepiece "
                "(et parfois aussi: pip install protobuf), puis redémarrez l'application."
            )

        elif "_is_hf_initialized" in lowered or "params4bit" in lowered:
            hint = (
                "Piste: bitsandbytes trop ancien/incompatible pour la quantisation 4-bit. "
                "Mettez a jour bitsandbytes (CUDA) ou changez de quantification."
            )

        elif "bitsandbytes" in lowered:
            hint = (
                "Piste: 'bitsandbytes' manquant/incompatible. Réinstallez bitsandbytes (CUDA) "
                "ou choisissez un modèle CPU plus petit."
            )

        elif "automatic conversion of the weights" in lowered or ("conversion" in lowered and "weights" in lowered):
            hint = (
                "Piste: conversion des poids echouee (cache potentiellement corrompu). "
                "Supprimez le snapshot du modele dans le cache HF puis relancez, "
                "ou forcez un telechargement complet."
            )

        diagnostic_text = "\n".join(diagnostic_lines) if diagnostic_lines else "N/A"

        return diagnostic_text, hint

    @staticmethod
    def _load_model_attempt(
        model_ref: str,
        kwargs: Dict[str, Any],
        *,
        model_name: str,
        model_optimizer,
        progress_callback,
        device: str = "cpu",
        skip_conversion_retry: bool = False,
    ) -> Tuple[Any, str, Dict[str, Any]]:
        """Try AutoModelForCausalLM.from_pretrained with graceful kwarg-stripping fallbacks.



        Returns ``(model, final_model_ref, last_load_kwargs)``.  ``final_model_ref`` may

        differ from the input when a forced re-download redirects to a new local path.

        ``skip_conversion_retry`` prevents the weight-conversion retry branch from running

        (used on the OOM-fallback second attempt when the first attempt already succeeded).

        """
        last_load_kwargs: Dict[str, Any] = {}

        conversion_done: bool = False

        try:
            last_load_kwargs = dict(kwargs)

            model = AutoModelForCausalLM.from_pretrained(model_ref, **kwargs)

            return model, model_ref, last_load_kwargs

        except Exception as exc:
            msg = str(exc)

            lowered_msg = msg.lower()

            if "unexpected keyword argument" in lowered_msg and (
                "offload_state_dict" in lowered_msg or "offload_folder" in lowered_msg
            ):

                logger.warning("Transformers version does not support disk offload kwargs; retrying without them.")

                alt_kwargs = dict(kwargs)

                alt_kwargs.pop("offload_state_dict", None)

                alt_kwargs.pop("offload_folder", None)

                last_load_kwargs = dict(alt_kwargs)

                return (
                    AutoModelForCausalLM.from_pretrained(model_ref, **alt_kwargs),
                    model_ref,
                    last_load_kwargs,
                )

            if "unexpected keyword argument" in lowered_msg and "attn_implementation" in lowered_msg:
                logger.warning("Transformers version does not support attn_implementation; retrying without it.")

                alt_kwargs = dict(kwargs)

                alt_kwargs.pop("attn_implementation", None)

                last_load_kwargs = dict(alt_kwargs)

                return (
                    AutoModelForCausalLM.from_pretrained(model_ref, **alt_kwargs),
                    model_ref,
                    last_load_kwargs,
                )

            if (
                not skip_conversion_retry
                and not conversion_done
                and ("automatic conversion of the weights" in lowered_msg or "conversion" in lowered_msg)
            ):

                conversion_done = True

                logger.warning(
                    "Weight conversion failed; forcing re-download and retrying: %s",
                    msg,
                )

                try:
                    forced_path = model_optimizer.optimize_model_download(
                        model_name,
                        progress_callback=progress_callback,
                        force_download=True,
                    )

                    if forced_path:
                        model_ref = forced_path

                except Exception as force_exc:
                    logger.warning("Force download failed: %s", force_exc)

                alt_kwargs = dict(kwargs)

                alt_kwargs.pop("low_cpu_mem_usage", None)

                alt_kwargs.setdefault("use_safetensors", False)

                try:
                    last_load_kwargs = dict(alt_kwargs)

                    return (
                        AutoModelForCausalLM.from_pretrained(
                            model_ref,
                            **alt_kwargs,
                        ),
                        model_ref,
                        last_load_kwargs,
                    )

                except Exception:
                    alt_kwargs.pop("use_safetensors", None)

                    last_load_kwargs = dict(alt_kwargs)

                    return (
                        AutoModelForCausalLM.from_pretrained(
                            model_ref,
                            **alt_kwargs,
                        ),
                        model_ref,
                        last_load_kwargs,
                    )

            if "unrecognized model in" in lowered_msg and "model_type" in lowered_msg:
                logger.warning(
                    "Model config appears incomplete/corrupted; forcing re-download and retry: %s",
                    msg,
                )
                forced_path = None
                try:
                    forced_path = model_optimizer.optimize_model_download(
                        model_name,
                        progress_callback=progress_callback,
                        force_download=True,
                    )
                except Exception as force_exc:
                    logger.warning("Force download failed for unrecognized model retry: %s", force_exc)

                if forced_path:
                    model_ref = forced_path

                alt_kwargs = dict(kwargs)
                last_load_kwargs = dict(alt_kwargs)
                return (
                    AutoModelForCausalLM.from_pretrained(model_ref, **alt_kwargs),
                    model_ref,
                    last_load_kwargs,
                )

            if (
                ("filenotfounderror" in lowered_msg or "no such file or directory" in lowered_msg)
                and ("safetensors" in lowered_msg or "model-" in lowered_msg)
            ):
                logger.warning(
                    "Model shard appears missing/corrupted; forcing re-download and retry: %s",
                    msg,
                )
                forced_path = None
                try:
                    forced_path = model_optimizer.optimize_model_download(
                        model_name,
                        progress_callback=progress_callback,
                        force_download=True,
                    )
                except Exception as force_exc:
                    logger.warning(
                        "Force download failed for missing-shard retry: %s",
                        force_exc,
                    )

                if forced_path:
                    model_ref = forced_path

                alt_kwargs = dict(kwargs)
                last_load_kwargs = dict(alt_kwargs)
                return (
                    AutoModelForCausalLM.from_pretrained(model_ref, **alt_kwargs),
                    model_ref,
                    last_load_kwargs,
                )

            if "Device cuda:0 is not recognized" in msg or "Device 0 is not recognized" in msg:
                logger.warning(
                    "Retry model load with alternate max_memory keys: %s",
                    msg,
                )

                alt_kwargs = dict(kwargs)

                max_memory = alt_kwargs.get("max_memory")

                if max_memory:
                    alt_memory: Dict[Union[int, str], str] = {}

                    for key, value in max_memory.items():
                        if isinstance(key, int):
                            alt_memory[f"cuda:{key}"] = value

                        elif isinstance(key, str) and key.startswith("cuda:"):
                            suffix = key.split(":", 1)[1]

                            try:
                                alt_memory[int(suffix)] = value

                            except Exception:
                                alt_memory[key] = value

                        else:
                            alt_memory[key] = value

                    alt_kwargs["max_memory"] = alt_memory

                    logger.info(
                        "Retrying model load with normalized max_memory keys: %s",
                        alt_memory,
                    )

                    try:
                        last_load_kwargs = dict(alt_kwargs)

                        return (
                            AutoModelForCausalLM.from_pretrained(model_ref, **alt_kwargs),
                            model_ref,
                            last_load_kwargs,
                        )

                    except Exception:
                        logger.warning("Normalized max_memory keys still failed; retrying without max_memory.")

                        alt_kwargs.pop("max_memory", None)

                        alt_kwargs.pop("low_cpu_mem_usage", None)

                        last_load_kwargs = dict(alt_kwargs)

                        return (
                            AutoModelForCausalLM.from_pretrained(model_ref, **alt_kwargs),
                            model_ref,
                            last_load_kwargs,
                        )

                raise

            if (
                "meta tensors" in lowered_msg
                or "meta tensor" in lowered_msg
                or "cannot copy out of meta tensor" in lowered_msg
            ):
                if device == "cuda" and kwargs.get("max_memory"):
                    hybrid_kwargs = dict(kwargs)
                    # Keep hybrid GPU+RAM placement but relax low_cpu_mem_usage; this
                    # often avoids full CPU fallback after meta-tensor initialization.
                    hybrid_kwargs["device_map"] = "auto"
                    hybrid_kwargs["low_cpu_mem_usage"] = False
                    hybrid_kwargs.pop("offload_folder", None)
                    hybrid_kwargs.pop("offload_state_dict", None)
                    max_memory = hybrid_kwargs.get("max_memory")
                    if isinstance(max_memory, dict):
                        has_cpu_key = any(str(key).strip().lower() == "cpu" for key in max_memory.keys())
                        if not has_cpu_key:
                            patched_memory = dict(max_memory)
                            patched_memory["cpu"] = "1024MiB"
                            hybrid_kwargs["max_memory"] = patched_memory
                            logger.warning(
                                "Meta retry: injected minimum CPU budget into max_memory map: %s",
                                patched_memory,
                            )
                    logger.warning(
                        "Retry model load in hybrid GPU+RAM mode after meta tensor error: %s",
                        msg,
                    )
                    try:
                        last_load_kwargs = dict(hybrid_kwargs)
                        return (
                            AutoModelForCausalLM.from_pretrained(model_ref, **hybrid_kwargs),
                            model_ref,
                            last_load_kwargs,
                        )
                    except Exception as hybrid_exc:
                        logger.warning(
                            "Hybrid retry after meta tensor error failed; preserving max_memory and bubbling up: %s",
                            hybrid_exc,
                        )
                        raise

                removed_map = kwargs.get("max_memory")

                logger.warning(
                    "Retry model load without max_memory after meta tensor error: %s (removed_map=%s)",
                    msg,
                    removed_map,
                )

                alt_kwargs = dict(kwargs)

                alt_kwargs.pop("max_memory", None)

                alt_kwargs.pop("low_cpu_mem_usage", None)

                try:
                    last_load_kwargs = dict(alt_kwargs)

                    return (
                        AutoModelForCausalLM.from_pretrained(model_ref, **alt_kwargs),
                        model_ref,
                        last_load_kwargs,
                    )

                except Exception:
                    if device == "cuda":
                        alt_kwargs["device_map"] = {"": 0}

                    last_load_kwargs = dict(alt_kwargs)

                    return (
                        AutoModelForCausalLM.from_pretrained(model_ref, **alt_kwargs),
                        model_ref,
                        last_load_kwargs,
                    )

            raise

    def load_model(self, progress_callback=None, allow_fallback: bool = False):
        """Charge le modèle sélectionné avec optimisations automatiques."""
        if allow_fallback and not self._allow_model_fallback():
            allow_fallback = False
        if allow_fallback:
            try:
                if self._is_selected_model_lock_enabled():
                    allow_fallback = False
                    logger.info(
                        "Model fallback disabled because selected-model lock is active."
                    )
            except Exception:
                pass

        if self._is_selected_model_lock_enabled():
            self._enforce_selected_model_lock(reason="load_model")
        else:
            try:
                self._apply_survival_model_override(progress_callback=progress_callback)

            except Exception as exc:
                logger.warning("Unable to apply survival model override: %s", exc)

        # Backend llama.cpp (GGUF): ne dépend pas de Transformers et gère son propre chargement.

        if getattr(self, "current_loader", "transformers") == "llama_cpp":
            self._load_llama_cpp_model(progress_callback)

            return

        # Vérifier si le modèle actuel est différent de celui demandé

        if self.model_loaded and self._model is not None and self._current_model_path == self.model_name:
            logger.info(f"Modèle {self.model_name} déjà chargé en mémoire")

            return

        try:
            failures = self._memory_manager.consecutive_failures if self._memory_manager else 0

            logger.info(
                "Model load policy: vram_mode=%s low_mode=%s med_mode=%s survival_mode=%s recycle_every_runs=%s failures=%s",
                self._get_vram_mode(),
                self._is_low_vram_mode(),
                self._is_med_vram_mode(),
                self._is_survival_mode(),
                self._get_recycle_every_runs(),
                failures,
            )

        except Exception:
            pass

        # Ã‰vite de garder des références partielles après un échec précédent.

        if not self.model_loaded and (self._model is not None or self._tokenizer is not None):
            logger.warning("Stale model references detected before load; forcing cleanup.")

            self._model = None

            self._tokenizer = None

            self._device = None

            self._current_model_path = None

            self.cleanup_memory()

        # Si on change de modèle, nettoyer l'ancien

        if self.model_loaded and self._current_model_path != self.model_name:
            logger.info(f"Changement de modèle: {self._current_model_path} -> {self.model_name}")

            # Relâcher d'abord les références Python puis vider les caches CUDA.

            self.model_loaded = False

            self._model = None

            self._tokenizer = None

            self._device = None

            self._current_model_path = None

            self.cleanup_memory()

        if not TRANSFORMERS_AVAILABLE:
            logger.warning("Transformers non disponible - Mode simulation")

            time.sleep(2)

            self.model_loaded = True

            self._current_model_path = self.model_name

            return

        try:
            # Vérifier si c'est le premier téléchargement

            self._check_first_download(progress_callback)

            if progress_callback:
                progress_callback("🔍 Détection du matériel disponible...")

            # Vérifier les optimisations hf_xet

            xet_status = model_optimizer.check_hf_xet_status()

            if xet_status["optimizations_active"]:
                logger.info("✅ Optimisations hf_xet actives pour téléchargements rapides")

            # Optimisation matérielle automatique

            model_size_gb = _estimate_model_size_gb(
                getattr(self, "model_name", None),
                getattr(self, "current_model_id", None),
            )

            try:
                self._optimization_config = gpu_manager.recommend_quantization(model_size_gb=model_size_gb)

            except TypeError:
                # Compat/mode mock

                self._optimization_config = gpu_manager.recommend_quantization()

            gpu_manager.optimize_for_inference()

            if TORCH_AVAILABLE and torch.cuda.is_available():
                try:
                    free_bytes, total_bytes = torch.cuda.mem_get_info()

                    logger.info(
                        "GPU memory before load: free=%.2fGB total=%.2fGB",
                        free_bytes / (1024**3),
                        total_bytes / (1024**3),
                    )

                except Exception:
                    pass

            self._log_cuda_mem("before_load")

            if self.custom_parameters.get("force_4bit_nf4"):
                self._optimization_config["load_in_4bit"] = True

                self._optimization_config["load_in_8bit"] = False

                self._optimization_config["dtype"] = torch.float16

                self._optimization_config["quantization"] = "nf4"

                self._optimization_config["reason"] = "Forced 4-bit NF4"

            if self._is_survival_mode():
                lowram_level = str(self._get_lowram_profile().get("level") or "normal")

                survival_max_len = self._get_survival_max_model_len()

                current_max_len = int(self._optimization_config.get("max_model_len") or 0)

                if current_max_len <= 0 or current_max_len > survival_max_len:
                    self._optimization_config["max_model_len"] = survival_max_len

                try:
                    current_util = float(self._optimization_config.get("gpu_memory_utilization") or 0.0)

                except Exception:
                    current_util = 0.0

                target_util = 0.55 if lowram_level in {"tight", "critical"} else 0.60

                if current_util <= 0 or current_util > target_util:
                    self._optimization_config["gpu_memory_utilization"] = target_util

                self._optimization_config["lowram_level"] = lowram_level

                self._optimization_config["reason"] = (
                    f"{self._optimization_config.get('reason', 'auto')} + survival(max_model_len={survival_max_len}, lowram={lowram_level})"
                )

            try:
                self._apply_non_survival_memory_tuning(progress_callback=progress_callback)

            except Exception as tuning_exc:
                logger.warning("Non-survival memory tuning failed: %s", tuning_exc)

            logger.info(f"Configuration optimale: {self._optimization_config['reason']}")

            # Vérification mémoire avant chargement (évite les crashs Access Violation)

            can_proceed, memory_error = self._check_memory_before_load()

            if not can_proceed:
                logger.error(memory_error)

                if progress_callback:
                    progress_callback(f"❌ {memory_error}")

                if (
                    not allow_fallback
                    and not self._ram_assist_mode
                    and self._prefer_ram_offload_mode()
                ):
                    self._activate_ram_assist_mode(
                        reason="preload_memory_check",
                        progress_callback=progress_callback,
                    )
                    try:
                        self.cleanup_memory()
                    except Exception:
                        pass
                    return self.load_model(progress_callback, allow_fallback=False)

                if allow_fallback:
                    try:
                        import psutil  # type: ignore

                        mem = psutil.virtual_memory()

                        available_ram_gb = mem.available / (1024**3)

                    except Exception:
                        available_ram_gb = 0.0

                    try:
                        available_vram_gb = self._get_free_vram_gb()

                    except Exception:
                        available_vram_gb = 0.0

                    stage_name = self._get_runtime_stage_name()
                    writer_stage = self._is_writer_stage(stage_name)
                    fallback = self._resolve_fallback_candidate(
                        available_ram_gb,
                        available_vram_gb,
                        stage=stage_name,
                        prefer_quality=writer_stage,
                        ram_fit_ratio=1.25 if writer_stage else 1.10,
                        require_memory_fit=writer_stage,
                    )

                    if fallback and fallback.get("model_id") and fallback.get("model_path"):
                        previous_id = getattr(self, "current_model_id", None)

                        previous_model = self.model_name

                        self.model_name = fallback["model_path"]

                        self.current_model_id = fallback["model_id"]

                        self.model_loaded = False

                        self._model = None

                        self._tokenizer = None

                        self._device = None

                        self._current_model_path = None

                        self._optimization_config = None

                        note = (
                            f"[WARN] Mémoire insuffisante (RAM/VRAM) pour '{previous_id or previous_model}'. "
                            f"Fallback vers '{self.current_model_id}' "
                            f"(ram_dispo={available_ram_gb:.1f}GB, vram_dispo={available_vram_gb:.1f}GB)."
                        )

                        self.last_model_resolution_note = note

                        logger.warning(note)

                        if progress_callback:
                            progress_callback(note)

                        try:
                            self.cleanup_memory()

                        except Exception:
                            pass

                        return self.load_model(progress_callback, allow_fallback=False)

                raise MemoryError(memory_error)

            # Telechargement optimise du modele si necessaire

            model_display_name = getattr(self, "current_model_id", self.model_name.split("/")[-1])

            model_path = self.model_name

            if progress_callback:
                progress_callback(f"[DL] Verification/telechargement du modele {model_display_name}...")

            try:
                model_path = model_optimizer.optimize_model_download(
                    self.model_name,
                    progress_callback=progress_callback,
                )

            except Exception as e:
                logger.warning(f"Telechargement optimise echoue, fallback standard: {e}")

                if self._is_download_or_cache_failure_reason(str(e)):
                    raise RuntimeError(f"Model download/cache failure: {e}") from e

                model_path = self.model_name

            # Load tokenizer (sets self._tokenizer, returns final model_ref for possible force-download path)

            model_ref = self._load_tokenizer(model_path, model_display_name, progress_callback)

            if progress_callback:
                progress_callback(
                    f"[MODEL] Chargement du modele {model_display_name} ({self._optimization_config['reason']})..."
                )

            # Build model-loading kwargs (device/offload/quantization strategy)

            model_kwargs, auto_kwargs = self._build_model_load_kwargs()

            # Chargement du modele

            _device = self._optimization_config.get("device", "cpu")

            last_load_kwargs: Dict[str, Any] = {}

            conversion_done = False

            try:
                self._model, model_ref, last_load_kwargs = self._load_model_attempt(
                    model_ref,
                    model_kwargs,
                    model_name=self.model_name,
                    model_optimizer=model_optimizer,
                    progress_callback=progress_callback,
                    device=_device,
                )

                conversion_done = True

            except Exception as exc:
                lowered = str(exc).lower()

                if auto_kwargs and ("cuda out of memory" in lowered or "out of memory" in lowered):
                    logger.warning(
                        "Forced GPU load failed (OOM). Retrying with device_map=auto and max_memory=%s.",
                        auto_kwargs.get("max_memory"),
                    )

                    try:
                        self.cleanup_memory()

                    except Exception:
                        pass

                    self._model, model_ref, last_load_kwargs = self._load_model_attempt(
                        model_ref,
                        auto_kwargs,
                        model_name=self.model_name,
                        model_optimizer=model_optimizer,
                        progress_callback=progress_callback,
                        device=_device,
                        skip_conversion_retry=conversion_done,
                    )

                else:
                    raise

            self._finalize_model_load(model_display_name, last_load_kwargs, progress_callback)

            if self._optimization_config.get("device") == "cuda":
                try:
                    device_summary = self._summarize_device_map()
                except Exception:
                    device_summary = {}
                try:
                    resolved_input_device = self._resolve_input_device()
                except Exception:
                    resolved_input_device = None

                has_cuda_map = any(
                    str(key).startswith("cuda") for key in (device_summary or {}).keys()
                )
                resolved_is_cuda = bool(
                    resolved_input_device is not None
                    and getattr(resolved_input_device, "type", "") == "cuda"
                )

                # Only fail when we can confirm CPU-only placement.
                # Some loaders do not always expose hf_device_map reliably.
                cpu_only_confirmed = False
                if device_summary:
                    cpu_only_confirmed = (not has_cuda_map) and (not resolved_is_cuda)
                else:
                    cpu_only_confirmed = not resolved_is_cuda

                if cpu_only_confirmed:
                    raise RuntimeError(
                        "CUDA model resolved to CPU-only device map in hybrid-only policy. "
                        "Free VRAM/RAM budget is insufficient for mixed placement."
                    )

        except Exception as e:
            error_msg = str(e)

            error_code = getattr(e, "winerror", None) or ""

            lowered = error_msg.lower()

            if "cpu-only device map in hybrid-only policy" in lowered:
                try:
                    self.unload_model(reason="cpu_only_hybrid_policy_error")
                except Exception:
                    pass

            self._record_failure(f"load_model: {error_msg[:240]}")

            if (
                not allow_fallback
                and not self._ram_assist_mode
                and self._prefer_ram_offload_mode()
                and (
                    self._is_meta_tensor_error(error_msg)
                    or "out of memory" in lowered
                    or "cuda out of memory" in lowered
                    or self._is_memory_pressure_failure_reason(error_msg)
                )
            ):
                self._activate_ram_assist_mode(
                    reason="load_exception",
                    progress_callback=progress_callback,
                )
                try:
                    self.cleanup_memory()
                except Exception:
                    pass
                return self.load_model(progress_callback, allow_fallback=False)

            # If selected repo is gated/unavailable, switch to an open fallback model.

            if allow_fallback and self._is_model_access_restricted_error(error_msg):
                try:
                    import psutil  # type: ignore

                    mem = psutil.virtual_memory()

                    available_ram_gb = mem.available / (1024**3)

                except Exception:
                    available_ram_gb = 0.0

                try:
                    available_vram_gb = self._get_free_vram_gb()

                except Exception:
                    available_vram_gb = 0.0

                blocked_prefix = self._extract_repo_prefix(self.model_name)

                stage_name = self._get_runtime_stage_name()

                writer_stage = self._is_writer_stage(stage_name)

                fallback = self._resolve_fallback_candidate(
                    available_ram_gb,
                    available_vram_gb,
                    stage=stage_name,
                    excluded_repo_prefixes=[blocked_prefix] if blocked_prefix else None,
                    prefer_quality=writer_stage,
                    ram_fit_ratio=1.25 if writer_stage else 1.10,
                    require_memory_fit=writer_stage,
                )

                if fallback and fallback.get("model_id") and fallback.get("model_path"):
                    previous_id = getattr(self, "current_model_id", None)

                    previous_model = self.model_name

                    self.model_name = fallback["model_path"]

                    self.current_model_id = fallback["model_id"]

                    self.model_loaded = False

                    self._model = None

                    self._tokenizer = None

                    self._device = None

                    self._current_model_path = None

                    self._optimization_config = None

                    note = (
                        f"[WARN] Acces refuse au modele '{previous_id or previous_model}' "
                        f"(repo prive/gated). Fallback automatique vers '{self.current_model_id}' "
                        f"(ram_dispo={available_ram_gb:.1f}GB, vram_dispo={available_vram_gb:.1f}GB)."
                    )

                    self.last_model_resolution_note = note

                    logger.warning(note)

                    if progress_callback:
                        progress_callback(note)

                    try:
                        self.cleanup_memory()

                    except Exception:
                        pass

                    return self.load_model(progress_callback, allow_fallback=True)
            # If model download/cache fails, try a smaller fallback model first.

            if allow_fallback and self._is_download_or_cache_failure_reason(error_msg):
                try:
                    import psutil  # type: ignore

                    mem = psutil.virtual_memory()

                    available_ram_gb = mem.available / (1024**3)

                except Exception:
                    available_ram_gb = 0.0

                try:
                    available_vram_gb = self._get_free_vram_gb()

                except Exception:
                    available_vram_gb = 0.0

                stage_name = self._get_runtime_stage_name()

                fallback = self._resolve_fallback_candidate(
                    available_ram_gb,
                    available_vram_gb,
                    stage=stage_name,
                    prefer_quality=False,
                    ram_fit_ratio=1.10,
                    require_memory_fit=True,
                )

                if fallback and fallback.get("model_id") and fallback.get("model_path"):
                    previous_id = getattr(self, "current_model_id", None)

                    previous_model = self.model_name

                    self.model_name = fallback["model_path"]

                    self.current_model_id = fallback["model_id"]

                    self.model_loaded = False

                    self._model = None

                    self._tokenizer = None

                    self._device = None

                    self._current_model_path = None

                    self._optimization_config = None

                    note = (
                        f"[WARN] Echec telechargement/cache pour '{previous_id or previous_model}'. "
                        f"Fallback vers '{self.current_model_id}' "
                        f"(ram_dispo={available_ram_gb:.1f}GB, vram_dispo={available_vram_gb:.1f}GB)."
                    )

                    self.last_model_resolution_note = note

                    logger.warning(note)

                    if progress_callback:
                        progress_callback(note)

                    try:
                        self.cleanup_memory()

                    except Exception:
                        pass

                    return self.load_model(progress_callback, allow_fallback=False)

            # Si le chargement a échoué en OOM, tenter un fallback automatique (une seule fois).

            if allow_fallback and (
                isinstance(e, MemoryError)
                or "out of memory" in lowered
                or "cuda out of memory" in lowered
                or self._is_memory_pressure_failure_reason(error_msg)
            ):

                try:
                    import psutil  # type: ignore

                    mem = psutil.virtual_memory()

                    available_ram_gb = mem.available / (1024**3)

                except Exception:
                    available_ram_gb = 0.0

                try:
                    available_vram_gb = self._get_free_vram_gb()

                except Exception:
                    available_vram_gb = 0.0

                stage_name = self._get_runtime_stage_name()
                writer_stage = self._is_writer_stage(stage_name)
                fallback = self._resolve_fallback_candidate(
                    available_ram_gb,
                    available_vram_gb,
                    stage=stage_name,
                    prefer_quality=writer_stage,
                    ram_fit_ratio=1.25 if writer_stage else 1.10,
                    require_memory_fit=writer_stage,
                )

                if fallback and fallback.get("model_id") and fallback.get("model_path"):
                    previous_id = getattr(self, "current_model_id", None)

                    previous_model = self.model_name

                    self.model_name = fallback["model_path"]

                    self.current_model_id = fallback["model_id"]

                    self.model_loaded = False

                    self._model = None

                    self._tokenizer = None

                    self._device = None

                    self._current_model_path = None

                    self._optimization_config = None

                    note = (
                        f"[WARN] OOM lors du chargement de '{previous_id or previous_model}'. "
                        f"Fallback vers '{self.current_model_id}' "
                        f"(ram_dispo={available_ram_gb:.1f}GB, vram_dispo={available_vram_gb:.1f}GB)."
                    )

                    self.last_model_resolution_note = note

                    logger.warning(note)

                    if progress_callback:
                        progress_callback(note)

                    try:
                        self.cleanup_memory()

                    except Exception:
                        pass

                    return self.load_model(progress_callback, allow_fallback=False)

            if isinstance(e, MemoryError) or "out of memory" in lowered or "cuda out of memory" in lowered:
                # Ã‰vite de conserver des références partielles après un échec OOM.

                self.model_loaded = False

                self._model = None

                self._tokenizer = None

                self._device = None

                self._current_model_path = None

                try:
                    self.cleanup_memory()

                except Exception:
                    pass

            # Détecter ACCESS_VIOLATION ou cache corrompu (Windows)

            is_access_violation = (
                "-1073741819" in error_msg
                or "0xC0000005" in error_msg
                or "Access" in error_msg
                and "Violation" in error_msg
                or error_code == 1314  # WinError 1314 - symlink permission
            )

            if is_access_violation:
                logger.error(
                    "Cache modèle probablement corrompu (ACCESS_VIOLATION). "
                    "Exécutez: python scripts/fix_model_cache.py"
                )

                if progress_callback:
                    progress_callback("❌ Cache modèle corrompu détecté")

                    progress_callback("💡 Exécutez: python scripts/fix_model_cache.py")

            diagnostic_text, hint = self._build_load_error_diagnostic(error_msg, error_code)

            logger.error(f"Erreur chargement modèle: {e}")

            if progress_callback:
                progress_callback("❌ Erreur chargement modèle (voir diagnostic)")

                if hint:
                    progress_callback(f"💡 {hint}")

            raise RuntimeError(
                f"Erreur chargement modèle: {e}\n\nDiagnostic:\n{diagnostic_text}" + (f"\n\n{hint}" if hint else "")
            ) from e

    @staticmethod
    def _compute_cv_max_tokens(model_name_lower: str, is_cpu: bool) -> int:
        """Return max_new_tokens budget for CV generation based on model size and device.



        Smaller models and CPU inference use lower token caps to avoid memory

        pressure and keep generation times reasonable.

        """
        # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

        # Configuration max_new_tokens par modèle et device

        # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

        # Règle : Les petits modèles CPU génèrent moins de tokens pour éviter

        # les blocages mémoire et accélérer la génération.

        #

        # MODÃˆLE                    | CPU tokens | GPU tokens | RAM requise

        # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

        # Qwen2.5-0.5B / TinyLlama  |    512     |   1024     |   1.5 GB

        # Qwen3-1.7B                |    768     |   1536     |   4.0 GB

        # Phi-3-Mini (3.8B)         |    768     |   1536     |   8.0 GB

        # Qwen3-4B                  |   1024     |   2048     |   8.0 GB

        # Mistral-7B / Qwen3-8B     |   1024     |   2048     |  16.0 GB

        # Qwen3-14B                 |   1536     |   2048     |  32.0 GB

        # Qwen3-32B                 |   2048     |   2048     |  64.0 GB

        # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

        if any(x in model_name_lower for x in ["0.6", "0.5", "tiny", "1.1b"]):
            return 512 if is_cpu else 1024

        if any(x in model_name_lower for x in ["1.7", "1.5"]):
            return 768 if is_cpu else 1536

        if any(x in model_name_lower for x in ["phi-3", "phi3", "mini"]):
            return 768 if is_cpu else 1536

        if any(x in model_name_lower for x in ["3b", "4b"]):
            return 1024 if is_cpu else 2048

        if any(x in model_name_lower for x in ["7b", "8b", "mistral"]):
            return 1024 if is_cpu else 2048

        if "14b" in model_name_lower:
            return 1536 if is_cpu else 2048

        if "32b" in model_name_lower:
            return 2048

        # Unknown model â€” safe defaults

        return 1024 if is_cpu else 2048

    def _generate_cv_via_llama_cpp(self, prompt: str, progress_callback=None) -> str:
        """Generate a CV using the active llama.cpp backend."""
        try:
            if progress_callback:
                progress_callback("🦙 Génération du CV via llama.cpp...")

            system_prompt = self._cv_system_prompt()

            user_prompt = self._cv_user_prompt(prompt)

            model_hint = str(self.model_name or "").lower()

            max_tokens = 1024

            if any(x in model_hint for x in ["0.6", "0.5", "tiny", "1.1b"]):
                max_tokens = 512

            elif any(x in model_hint for x in ["1.7", "1.5"]):
                max_tokens = 768

            try:
                ctx_size = int(getattr(getattr(self._llama_cpp_server, "config", None), "ctx_size", 4096))

            except Exception:
                ctx_size = 4096

            max_tokens = min(int(max_tokens), max(256, int(ctx_size // 2)))

            generated_text = self._llama_cpp_chat(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=max_tokens,
                temperature=0.7,
                top_p=0.9,
            )

            cv_content = self._extract_cv_content(generated_text)

            if progress_callback:
                progress_callback("✨ CV généré !")

            return cv_content

        except Exception as e:
            logger.error(f"Erreur generation CV (llama.cpp): {e}")

            raise RuntimeError(f"CV generation failed (llama.cpp): {e}") from e

    @staticmethod
    def _parse_generation_overrides(
        overrides: Dict[str, Any],
    ) -> Tuple[int, float, float, int, float, bool]:
        """Parse and clamp raw generation override dict into typed generation params.



        Returns:

            (max_new_tokens, temperature, top_p, top_k, repetition_penalty, do_sample)

        """
        try:
            requested_max_new_tokens = int(overrides.get("max_new_tokens") or 768)

        except Exception:
            requested_max_new_tokens = 768

        requested_max_new_tokens = max(128, requested_max_new_tokens)

        try:
            temperature = float(overrides.get("temperature") if "temperature" in overrides else 0.2)

        except Exception:
            temperature = 0.2

        temperature = max(0.0, min(1.0, temperature))

        try:
            top_p = float(overrides.get("top_p") if "top_p" in overrides else 0.9)

        except Exception:
            top_p = 0.9

        top_p = max(0.1, min(0.99, top_p))

        try:
            top_k = int(overrides.get("top_k") if "top_k" in overrides else 50)

        except Exception:
            top_k = 50

        top_k = max(1, min(200, top_k))

        try:
            repetition_penalty = float(
                overrides.get("repetition_penalty") if "repetition_penalty" in overrides else 1.05
            )

        except Exception:
            repetition_penalty = 1.05

        repetition_penalty = max(1.0, min(1.3, repetition_penalty))

        if "do_sample" in overrides:
            do_sample = bool(overrides.get("do_sample"))

        else:
            do_sample = temperature > 0.0

        return requested_max_new_tokens, temperature, top_p, top_k, repetition_penalty, do_sample

    def generate_cv(self, prompt: str, progress_callback=None, allow_fallback: bool = False) -> str:
        """Génère un CV basé sur le prompt avec Qwen2.5-32B."""
        if not self.model_loaded:
            self.load_model(progress_callback, allow_fallback=allow_fallback)

        if getattr(self, "current_loader", "transformers") != "llama_cpp" and self._should_use_chunked_generation(
            prompt
        ):

            return self._generate_cv_chunked(prompt, progress_callback)

        if getattr(self, "current_loader", "transformers") == "llama_cpp":
            return self._generate_cv_via_llama_cpp(prompt, progress_callback)

        if not TRANSFORMERS_AVAILABLE or self._model is None:
            raise RuntimeError("CV generation failed: model backend unavailable")

        try:
            if progress_callback:
                progress_callback("📝 Préparation du prompt optimisé...")

            # Template de prompt optimisé pour Qwen2.5

            formatted_prompt = self._build_cv_prompt(prompt)

            model_name_lower = self.model_name.lower()

            is_cpu = self._optimization_config.get("device") == "cpu"

            max_tokens = self._compute_cv_max_tokens(model_name_lower, is_cpu)

            # Budget tokens: adapter le prompt et la génération selon la limite réelle du modèle.

            # Récupérer max_position_embeddings depuis la config du modèle chargé.

            model_max_positions = 4096  # Valeur par défaut sécurisée

            try:
                if hasattr(self._model, "config") and hasattr(self._model.config, "max_position_embeddings"):
                    model_max_positions = int(self._model.config.max_position_embeddings)

                    logger.debug(f"Capacité modèle détectée: max_position_embeddings={model_max_positions}")

            except Exception as cfg_err:
                logger.warning(f"Impossible de lire max_position_embeddings: {cfg_err}")

            try:
                opt_max_len = int((self._optimization_config or {}).get("max_model_len") or 0)

            except Exception:
                opt_max_len = 0

            # Utiliser le minimum entre la config utilisateur et les capacités réelles du modèle

            max_total_len = min(opt_max_len or model_max_positions, model_max_positions)

            max_new_tokens_cap = min(max_tokens, max_total_len // 2)

            prompt_max_len = max(256, max_total_len - max_new_tokens_cap - 64)

            inputs = self._tokenizer(
                formatted_prompt,
                return_tensors="pt",
                truncation=True,
                max_length=prompt_max_len,
            ).to(self._device)

            input_len = int(inputs.input_ids.shape[1])

            allowed_new_tokens = max_total_len - input_len - 32

            if allowed_new_tokens > 0:
                max_tokens = min(max_tokens, max_new_tokens_cap, allowed_new_tokens)

            else:
                max_tokens = min(max_tokens, max_new_tokens_cap)

            device_label = "CPU" if is_cpu else "GPU"

            logger.info(f"Mode {device_label}: génération avec max_tokens={max_tokens} pour {self.model_name}")

            if progress_callback:
                progress_callback(f"🤖 Génération du CV (~{max_tokens} tokens max)...")

            use_cache = True

            if not is_cpu and self._should_disable_kv_cache():
                free_vram = self._get_free_vram_gb()

                use_cache = False

                note = f"[WARN] VRAM faible ({free_vram:.1f}GB) : KV cache désactivé."

                logger.warning(note)

                if progress_callback:
                    progress_callback(note)

            if TORCH_AVAILABLE and torch.cuda.is_available():
                try:
                    torch.cuda.empty_cache()

                except Exception:
                    pass

            if TORCH_AVAILABLE and torch.cuda.is_available():
                if os.getenv("CVMATCH_VRAM_DEBUG", "").strip() == "1":
                    try:
                        torch.cuda.reset_peak_memory_stats()

                    except Exception:
                        pass

            self._log_cuda_mem("pre_generate")

            # Génération avec paramètres optimisés

            with torch.no_grad():
                outputs = self._model.generate(
                    **inputs,
                    max_new_tokens=max_tokens,
                    temperature=0.7,
                    top_p=0.9,
                    top_k=50,
                    do_sample=True,
                    repetition_penalty=1.1,
                    pad_token_id=self._tokenizer.eos_token_id,
                    eos_token_id=self._tokenizer.eos_token_id,
                    use_cache=use_cache,
                )

            # Décodage de la réponse avec protection contre les débordements

            output_len = outputs[0].shape[0]

            input_slice_end = min(inputs.input_ids.shape[1], output_len)

            if output_len <= input_slice_end:
                # Aucun nouveau token généré - fallback

                logger.warning(f"Aucun nouveau token généré (output_len={output_len}, input_len={input_slice_end})")

                generated_text = ""

            else:
                generated_text = self._tokenizer.decode(outputs[0][input_slice_end:], skip_special_tokens=True)

            self._log_cuda_mem("post_generate")

            # Nettoyage et extraction du CV

            cv_content = self._extract_cv_content(generated_text)

            if progress_callback:
                progress_callback("✨ CV généré avec succès !")

            logger.info(f"CV généré - Longueur: {len(cv_content)} caractères")

            return cv_content

        except Exception as e:
            logger.error(f"Erreur generation CV: {e}")

            self._record_failure(f"generate_cv: {str(e)[:240]}")

            lowered = str(e).lower()

            if "meta tensor" in lowered or "cannot copy out of meta tensor" in lowered:
                logger.warning("Generation meta tensor detected; unloading model for safe reload.")

                try:
                    self.unload_model(reason="generation meta tensor")

                except Exception:
                    pass

            if "out of memory" in lowered or "cuda out of memory" in lowered:
                logger.warning("Generation OOM detected; unloading model to recover VRAM.")

                try:
                    self.unload_model(reason="generation OOM")

                except Exception:
                    pass

            raise RuntimeError(f"CV generation failed: {e}") from e

    def generate_structured_json(
        self,
        system_prompt: str,
        user_prompt: str,
        progress_callback=None,
        generation_overrides: Optional[Dict[str, Any]] = None,
        role: Optional[str] = None,
    ) -> str:
        """Generate a structured JSON payload using the active LLM.

        When ``role`` is provided, role parameters are applied before overrides.
        """
        self._clear_last_generation_error()

        if not self.model_loaded:
            self.load_model(
                progress_callback,
                allow_fallback=self._allow_model_fallback(),
            )

        overrides = dict(generation_overrides) if isinstance(generation_overrides, dict) else {}
        meta_recovery_retry = self._to_bool(overrides.pop("_meta_recovery_retry", False), False)
        role_key = str(role or "").strip().lower()
        parsed_overrides: Dict[str, Any] = dict(overrides)
        if role_key:
            parsed_overrides = self._resolve_role_params(role_key, overrides)

        requested_max_new_tokens, temperature, top_p, top_k, repetition_penalty, do_sample = (
            self._parse_generation_overrides(parsed_overrides)
        )

        if getattr(self, "current_loader", "transformers") == "llama_cpp":
            try:
                if progress_callback:
                    progress_callback("[LLM] Structured JSON via llama.cpp...")

                try:
                    ctx_size = int(getattr(getattr(self._llama_cpp_server, "config", None), "ctx_size", 4096))

                except Exception:
                    ctx_size = 4096

                max_tokens = max(256, int(min(requested_max_new_tokens, ctx_size // 2)))

                generated_text = self._llama_cpp_chat(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    top_p=top_p,
                )

                return self._extract_structured_content(generated_text)

            except Exception as e:
                logger.error(f"Erreur génération JSON (llama.cpp): {e}")
                self._set_last_generation_error(f"structured_json_llama_cpp: {e}")

                return ""

        if not TRANSFORMERS_AVAILABLE or self._model is None:
            self._set_last_generation_error("structured_json: model backend unavailable")
            return ""

        try:
            if progress_callback:
                progress_callback("[LLM] Generating structured JSON...")

            formatted_prompt = self._build_generic_prompt(system_prompt, user_prompt)

            desired_new_tokens = requested_max_new_tokens

            try:
                opt_max_len = int((self._optimization_config or {}).get("max_model_len") or 0)

            except Exception:
                opt_max_len = 0

            max_total_len = min(opt_max_len or 4096, 4096)

            max_new_tokens_cap = min(desired_new_tokens, max_total_len // 2)

            prompt_max_len = max(256, max_total_len - max_new_tokens_cap - 64)

            prompt_max_len = min(prompt_max_len, 3072)

            inputs = self._tokenizer(
                formatted_prompt,
                return_tensors="pt",
                truncation=True,
                max_length=prompt_max_len,
            ).to(self._device)

            input_len = int(inputs.input_ids.shape[1])

            allowed_new_tokens = max_total_len - input_len - 32

            if allowed_new_tokens > 0:
                max_new_tokens = min(desired_new_tokens, max_new_tokens_cap, allowed_new_tokens)

            else:
                max_new_tokens = max_new_tokens_cap

            slow_device = self._detect_slow_device()

            if slow_device:
                max_new_tokens = min(max_new_tokens, 700)

            use_cache = self._resolve_kv_cache(progress_callback)

            if not use_cache:
                max_new_tokens = min(max_new_tokens, 900)

            if slow_device:
                logger.info(
                    "Structured JSON slow mode: cap max_new_tokens=%s", max_new_tokens
                )

            if not use_cache:
                logger.info(
                    "Structured JSON no-cache mode: cap max_new_tokens=%s", max_new_tokens
                )

            if TORCH_AVAILABLE and torch.cuda.is_available():
                try:
                    torch.cuda.empty_cache()

                except Exception:
                    pass

            with torch.no_grad():
                generate_kwargs = {
                    "max_new_tokens": max_new_tokens,
                    "temperature": temperature,
                    "do_sample": do_sample,
                    "repetition_penalty": repetition_penalty,
                    "pad_token_id": self._tokenizer.eos_token_id,
                    "eos_token_id": self._tokenizer.eos_token_id,
                    "use_cache": use_cache,
                }

                if do_sample:
                    generate_kwargs["top_p"] = top_p

                    generate_kwargs["top_k"] = top_k

                outputs = self._model.generate(
                    **inputs,
                    **generate_kwargs,
                )

            generated_text = self._tokenizer.decode(
                outputs[0][inputs.input_ids.shape[1] :],
                skip_special_tokens=True,
            )

            return self._extract_structured_content(generated_text)

        except Exception as e:
            logger.error(f"Structured JSON generation error: {e}")
            self._set_last_generation_error(f"structured_json: {e}")

            self._record_failure(f"structured_json: {str(e)[:240]}")

            if self._is_meta_tensor_error(e):
                if not meta_recovery_retry:
                    logger.warning(
                        "Structured JSON meta tensor error detected; retrying once with safer reload policy."
                    )
                    try:
                        self._activate_meta_recovery_mode(
                            reason="structured_json",
                            progress_callback=progress_callback,
                        )
                        self.unload_model(reason="structured json meta tensor")
                        self.load_model(
                            progress_callback,
                            allow_fallback=self._allow_model_fallback(),
                        )
                        retry_overrides = dict(overrides)
                        retry_overrides["_meta_recovery_retry"] = True
                        return self.generate_structured_json(
                            system_prompt=system_prompt,
                            user_prompt=user_prompt,
                            progress_callback=progress_callback,
                            generation_overrides=retry_overrides,
                            role=role,
                        )
                    except Exception as retry_exc:
                        logger.error("Structured JSON retry after meta tensor failed: %s", retry_exc)
                logger.warning(
                    "Structured JSON meta tensor error detected; unloading model for safe reload."
                )
                try:
                    self.unload_model(reason="structured json meta tensor")
                except Exception:
                    pass

            lowered = str(e).lower()
            if "out of memory" in lowered or "cuda out of memory" in lowered:
                logger.warning("Structured JSON OOM detected; unloading model to recover VRAM.")

                try:
                    self.unload_model(reason="structured json OOM")

                except Exception:
                    pass

            return ""

    @staticmethod
    def _cv_system_prompt() -> str:

        return """Tu es un recruteur senior (HR) et expert ATS + redaction de CV.
Ta mission: produire un CV pre-rempli, parfaitement adapte a l'offre cible, que le candidat pourra relire et corriger.


Contraintes absolues:
- N'invente jamais de faits (dates, entreprises, diplomes, competences, outils, certifications, niveaux, liens).
- Utilise uniquement les informations presentes dans les DONNEES CANDIDAT fournies.
- Si une information manque, laisse le champ vide (pas de placeholder, pas d'hypothese).
- Pour l'identite et les contacts, utilise les donnees du candidat quand disponibles, sinon laisse vide.
- Adapte le contenu a l'offre (mots-cles, priorisation) sans inventer: tu peux reformuler et utiliser des synonymes si le sens reste vrai et verifiable.
- N'ajoute pas de competences non presentes dans les donnees (tu peux changer la formulation, pas le fond).
- L'offre cible est prioritaire pour la structure et les mots-cles (si valides).
- Format de sortie: uniquement du Markdown, sans explications, en respectant strictement la structure demandee.
- Style: concis, orienté impact, resultats mesurables quand disponibles."""
    @staticmethod
    def _cv_user_prompt(base_prompt: str) -> str:

        return f"""{base_prompt}



Genere le CV final en Markdown uniquement, conforme a la structure imposee."""
    def _build_cv_prompt(self, base_prompt: str) -> str:
        """Construit un prompt optimisé selon le type de modèle.



        Les modèles Qwen/Mistral/Phi supportent les tags <|im_start|>/<|im_end|>
        tandis que TinyLlama et autres modèles simples utilisent un format basique.
        """
        system_prompt = self._cv_system_prompt()
        user_prompt = self._cv_user_prompt(base_prompt)

        # Détecter le type de modèle pour adapter le format du prompt

        model_lower = self.model_name.lower() if hasattr(self, "model_name") else ""

        # Modèles supportant les tags ChatML (<|im_start|>/<|im_end|>)
        supports_chatml = any(x in model_lower for x in ["qwen", "mistral", "phi"])

        if supports_chatml:
            # Format ChatML pour Qwen/Mistral/Phi
            formatted_prompt = f"<|im_start|>system\n{system_prompt}<|im_end|>\n<|im_start|>user\n{user_prompt}<|im_end|>\n<|im_start|>assistant\n"
        else:
            # Format simple pour TinyLlama et autres modèles basiques
            # Ces modèles ne comprennent pas les tags ChatML
            formatted_prompt = f"""Instructions: {system_prompt}



{user_prompt}


CV en Markdown:
"""
        return formatted_prompt

    @staticmethod
    def _cv_section_system_prompt(language_code: str) -> str:

        if language_code == "en":
            return (
                "You are a senior recruiter and ATS expert. "
                "Use ONLY the candidate data provided. Do not invent facts. "
                "Output ONLY the requested section in Markdown."
            )
        return (
            "Tu es un recruteur senior et expert ATS. "
            "Utilise UNIQUEMENT les données candidat fournies. "
            "N'invente aucun fait. "
            "Retourne UNIQUEMENT la section demandée en Markdown."
        )

    @staticmethod
    def _extract_prompt_block(text: str, start_marker: str, end_marker: str) -> str:

        if not text:
            return ""
        start = text.find(start_marker)
        if start == -1:
            return ""
        end = text.find(end_marker, start + len(start_marker))
        if end == -1:
            end = len(text)
        return text[start:end].strip()

    def _extract_autocheck_feedback(self, base_prompt: str) -> str:
        feedback = self._extract_prompt_block(
            base_prompt,
            "AUTO-CHECK FEEDBACK",
            "CURRENT CV",
        )
        if feedback:
            return feedback
        return self._extract_prompt_block(
            base_prompt,
            "AUTO-CHECK FEEDBACK",
            "Regenerate the full CV",
        )

    def _extract_current_cv_block(self, base_prompt: str) -> str:
        block = self._extract_prompt_block(
            base_prompt,
            "CURRENT CV (markdown):",
            "Regenerate the full CV",
        )
        return block

    @staticmethod
    def _normalize_heading(text: str) -> str:

        if not text:
            return ""
        normalized = unicodedata.normalize("NFKD", text)
        normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
        normalized = re.sub(r"\s+", " ", normalized.lower()).strip()
        return normalized

    @staticmethod
    def _parse_markdown_sections(cv_markdown: str) -> Dict[str, str]:

        sections: Dict[str, str] = {}
        current_title = ""
        buffer: List[str] = []
        for raw_line in (cv_markdown or "").splitlines():
            line = raw_line.strip()
            if line.startswith("## "):
                if current_title:
                    sections[current_title] = "\n".join(buffer).strip()
                current_title = line[3:].strip()
                buffer = []
                continue
            if current_title:
                buffer.append(raw_line)
        if current_title:
            sections[current_title] = "\n".join(buffer).strip()
        return sections

    def _find_section_text(self, sections: Dict[str, str], keywords: List[str]) -> str:
        if not sections:
            return ""
        normalized_keywords = [self._normalize_heading(k) for k in keywords if k]
        for title, body in sections.items():
            title_norm = self._normalize_heading(title)
            for keyword in normalized_keywords:
                if keyword and keyword in title_norm:
                    return body or ""
        return ""

    @staticmethod
    def _parse_candidate_sections(candidate_block: str) -> Dict[str, Dict[str, str]]:

        header_map = {
            "CONTACT (profil):": "contact",
            "INFOS COMPLEMENTAIRES (profil detaille):": "extra",
            "RESUME (profil detaille):": "summary",
            "LIENS (profil detaille):": "links",
            "EXPERIENCES (profil detaille):": "experience",
            "FORMATION (profil detaille):": "education",
            "COMPETENCES (profil detaille):": "skills",
            "SOFT SKILLS (profil detaille):": "soft_skills",
            "PROJETS (profil detaille):": "projects",
            "CERTIFICATIONS (profil detaille):": "certifications",
            "VOLONTARIAT (profil detaille):": "volunteering",
            "LANGUES (profil detaille):": "languages",
            "CENTRES D'INTERET (profil detaille):": "interests",
            "LETTRE DE MOTIVATION TYPE (profil):": "cover_letter",
            "CV DE REFERENCE (texte brut, pour details):": "master_cv",
        }

        sections: Dict[str, Dict[str, str]] = {}
        current_key: Optional[str] = None
        for raw_line in (candidate_block or "").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line in header_map:
                current_key = header_map[line]
                sections[current_key] = {"header": line, "text": ""}
                continue
            if current_key:
                existing = sections[current_key].get("text", "")
                sections[current_key]["text"] = (existing + "\n" + raw_line).strip()
        return sections

    @staticmethod
    def _build_section_context(
        sections: Dict[str, Dict[str, str]],
        keys: List[str],
        max_chars: int = 1800,
    ) -> str:
        parts: List[str] = []
        for key in keys:
            data = sections.get(key)
            if not data:
                continue
            header = data.get("header") or ""
            text = data.get("text") or ""
            if not text.strip():
                continue
            parts.append(f"{header}\n{text}".strip())
        combined = "\n\n".join(parts).strip()
        if max_chars > 0:
            combined = _trim_text(combined, max_chars)
        return combined

    @staticmethod
    def _normalize_section_output(text: str, title: str, placeholder: str) -> str:

        content = (text or "").strip()
        if "<|im_end|>" in content:
            content = content.split("<|im_end|>")[0].strip()
        if not content:
            return f"## {title}\n{placeholder}"
        lines = [line.rstrip() for line in content.splitlines() if line.strip()]
        if lines and lines[0].lstrip().startswith("#"):
            lines.pop(0)
        body = "\n".join(lines).strip()
        if not body:
            body = placeholder
        return f"## {title}\n{body}".strip()

    def _should_use_chunked_generation(self, base_prompt: str) -> bool:
        env_flag = os.getenv("CVMATCH_CHUNKED_CV")
        if env_flag is not None:
            return env_flag.strip().lower() in ("1", "true", "yes", "y")

        custom = self.custom_parameters or {}
        if "chunked_generation" in custom:
            return bool(custom.get("chunked_generation"))

        try:
            total_vram = float(getattr(gpu_manager, "gpu_info", {}).get("total_memory_gb", 0) or 0)
        except Exception:
            total_vram = 0.0

        model_hint = str(self.model_name or "").lower()
        if total_vram and total_vram <= 12 and ("7b" in model_hint or "8b" in model_hint):
            return True

        free_vram = self._get_free_vram_gb()

        if free_vram > 0 and free_vram < max(2.0, self._get_vram_headroom_gb(free_vram_gb=free_vram)):
            return True
        return False

    def _generate_text_with_prompt(
        self,
        formatted_prompt: str,
        max_tokens: int,
        temperature: float,
        top_p: float,
        do_sample: bool,
        progress_callback=None,
    ) -> str:
        if not TRANSFORMERS_AVAILABLE or self._model is None or self._tokenizer is None:
            return ""

        model_max_positions = 4096
        try:
            if hasattr(self._model, "config") and hasattr(self._model.config, "max_position_embeddings"):
                model_max_positions = int(self._model.config.max_position_embeddings)
        except Exception:
            pass

        try:
            opt_max_len = int((self._optimization_config or {}).get("max_model_len") or 0)
        except Exception:
            opt_max_len = 0
        max_total_len = min(opt_max_len or model_max_positions, model_max_positions)
        max_new_tokens_cap = min(max_tokens, max_total_len // 2)
        prompt_max_len = max(256, max_total_len - max_new_tokens_cap - 64)

        inputs = self._tokenizer(
            formatted_prompt,
            return_tensors="pt",
            truncation=True,
            max_length=prompt_max_len,
        ).to(self._device)

        input_len = int(inputs.input_ids.shape[1])
        allowed_new_tokens = max_total_len - input_len - 32
        if allowed_new_tokens > 0:
            max_tokens = min(max_tokens, max_new_tokens_cap, allowed_new_tokens)
        else:
            max_tokens = min(max_tokens, max_new_tokens_cap)

        use_cache = True
        if getattr(self._device, "type", None) == "cuda" and self._should_disable_kv_cache():
            free_vram = self._get_free_vram_gb()
            use_cache = False
            note = f"[WARN] VRAM faible ({free_vram:.1f}GB) : KV cache désactivé."
            logger.warning(note)
            if progress_callback:
                progress_callback(note)

        if TORCH_AVAILABLE and torch.cuda.is_available():
            try:
                torch.cuda.empty_cache()
            except Exception:
                pass
        if TORCH_AVAILABLE and torch.cuda.is_available():
            if os.getenv("CVMATCH_VRAM_DEBUG", "").strip() == "1":
                try:
                    torch.cuda.reset_peak_memory_stats()
                except Exception:
                    pass
        self._log_cuda_mem("pre_generate")

        with torch.no_grad():
            outputs = self._model.generate(
                **inputs,
                max_new_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                top_k=50,
                do_sample=do_sample,
                repetition_penalty=1.05,
                pad_token_id=self._tokenizer.eos_token_id,
                eos_token_id=self._tokenizer.eos_token_id,
                use_cache=use_cache,
            )

        self._log_cuda_mem("post_generate")
        return self._tokenizer.decode(
            outputs[0][inputs.input_ids.shape[1] :],
            skip_special_tokens=True,
        )

    @staticmethod
    def _build_cv_section_plan(language_code: str) -> List[Dict[str, Any]]:
        """Return the ordered list of CV section descriptors for chunked generation.



        Each descriptor specifies the section key, display title, candidate data

        keys to include, max token budget, and generation guidance string.

        """
        en = language_code == "en"

        return [
            {
                "key": "summary",
                "title": "Professional Summary" if en else "Profil professionnel",
                "data_keys": ["summary", "experience", "skills"],
                "max_tokens": 192,
                "include_offer": True,
                "include_identity": False,
                "guidance": (
                    "3-4 lines, concise, aligned to the target role."
                    if en
                    else "3-4 lignes, concises, alignees au poste cible."
                ),
            },
            {
                "key": "experience",
                "title": "Work Experience" if en else "Experience professionnelle",
                "data_keys": ["experience", "volunteering"],
                "max_tokens": 700,
                "include_offer": True,
                "include_identity": False,
                "guidance": (
                    "For each role: 3-5 impact bullets. No invented facts."
                    if en
                    else "Pour chaque poste: 3-5 puces orientées impact. N'invente rien."
                ),
            },
            {
                "key": "projects",
                "title": "Projects" if en else "Projets",
                "data_keys": ["projects"],
                "max_tokens": 360,
                "include_offer": True,
                "include_identity": False,
                "guidance": (
                    "1-2 sentences per project, focus on outcomes."
                    if en
                    else "1-2 phrases par projet, focus sur les résultats."
                ),
            },
            {
                "key": "education",
                "title": "Education" if en else "Formation",
                "data_keys": ["education"],
                "max_tokens": 260,
                "include_offer": False,
                "include_identity": False,
                "guidance": (
                    "Degree | School | Year, add details if relevant."
                    if en
                    else "Diplome | Etablissement | Annee, details si pertinent."
                ),
            },
            {
                "key": "skills",
                "title": "Skills" if en else "Competences",
                "data_keys": ["skills", "soft_skills"],
                "max_tokens": 260,
                "include_offer": True,
                "include_identity": False,
                "guidance": (
                    "Bullet list, prioritize offer keywords."
                    if en
                    else "Liste en puces, priorise les mots-cles de l'offre."
                ),
            },
            {
                "key": "languages",
                "title": "Languages" if en else "Langues",
                "data_keys": ["languages"],
                "max_tokens": 140,
                "include_offer": False,
                "include_identity": False,
                "guidance": "- Language: Level" if en else "- Langue: Niveau",
            },
            {
                "key": "certifications",
                "title": "Certifications (optional)" if en else "Certifications (optionnel)",
                "data_keys": ["certifications"],
                "max_tokens": 140,
                "include_offer": False,
                "include_identity": False,
                "guidance": (
                    "List only confirmed certifications." if en else "Liste uniquement les certifications confirmées."
                ),
            },
            {
                "key": "interests",
                "title": "Interests (optional)" if en else "Centres d'interet (optionnel)",
                "data_keys": ["interests"],
                "max_tokens": 120,
                "include_offer": False,
                "include_identity": False,
                "guidance": "Short bullet list." if en else "Liste courte en puces.",
            },
        ]

    def _generate_cv_chunked(self, base_prompt: str, progress_callback=None) -> str:

        lang_match = re.search(r"LANGUE:\s*([a-zA-Z-]+)", base_prompt or "")

        language_code = _normalize_language(lang_match.group(1)) if lang_match else "fr"

        placeholder = "[TO COMPLETE]" if language_code == "en" else "[A COMPLETER]"

        if progress_callback:
            progress_callback("[LOW VRAM] Generation en sections (mode fragmenté)...")

        offer_block = self._extract_prompt_block(base_prompt, "OFFRE CIBLE:", "IDENTITE CANDIDAT")

        if offer_block:
            offer_block = _trim_text(offer_block, 1400)

        identity_block = self._extract_prompt_block(base_prompt, "IDENTITE CANDIDAT", "DONNEES CANDIDAT")

        candidate_block = self._extract_prompt_block(base_prompt, "DONNEES CANDIDAT", "SORTIE OBLIGATOIRE")

        if candidate_block:
            lines = candidate_block.splitlines()

            candidate_block = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""

        candidate_sections = self._parse_candidate_sections(candidate_block)

        feedback_block = self._extract_autocheck_feedback(base_prompt)

        if feedback_block:
            feedback_block = _trim_text(feedback_block, 900)

        current_cv_block = self._extract_current_cv_block(base_prompt)

        current_cv_sections = self._parse_markdown_sections(current_cv_block) if current_cv_block else {}

        if language_code == "en":
            header = "# [Your First Name] [Your Last Name]\n## <Target role>\n"

            contact_title = "Contact"

            contact_block = (
                f"## {contact_title}\n"
                "- Email: [Your Email]\n"
                "- Phone: [Your Phone]\n"
                "- LinkedIn: [Your LinkedIn]\n"
                "- Location: [Your City, Country]\n"
            )

        else:
            header = "# [Votre Prenom] [Votre Nom]\n## <Titre du poste cible>\n"

            contact_title = "Informations de contact"

            contact_block = (
                f"## {contact_title}\n"
                "- Email: [Votre Email]\n"
                "- Telephone: [Votre Telephone]\n"
                "- LinkedIn: [Votre LinkedIn]\n"
                "- Localisation: [Votre Ville, Pays]\n"
            )

        section_plan = self._build_cv_section_plan(language_code)

        output_parts: List[str] = [header.strip(), contact_block.strip()]

        system_prompt = self._cv_section_system_prompt(language_code)

        for section in section_plan:
            context = self._build_section_context(
                candidate_sections,
                section["data_keys"],
                max_chars=1200,
            )

            if not context:
                output_parts.append(f"## {section['title']}\n{placeholder}")

                continue

            prompt_parts = []

            if section.get("include_offer") and offer_block:
                prompt_parts.append(offer_block)

            if section.get("include_identity") and identity_block:
                prompt_parts.append(identity_block)

            if feedback_block:
                prompt_parts.append("AUTO-CHECK FEEDBACK (apply if relevant):")

                prompt_parts.append(feedback_block)

            if current_cv_sections:
                current_section = self._find_section_text(
                    current_cv_sections,
                    [section["title"], section["key"]],
                )

                if current_section:
                    prompt_parts.append("SECTION COURANTE (brouillon):")

                    prompt_parts.append(_trim_text(current_section, 900))

            prompt_parts.append("DONNEES CANDIDAT (section cible):")

            prompt_parts.append(context)

            prompt_parts.append(
                f"SECTION A GENERER: {section['title']}\n"
                f"CONSIGNES: {section['guidance']}\n"
                f"Sortie: uniquement cette section en Markdown, commence par '## {section['title']}'."
            )

            user_prompt = "\n\n".join(part for part in prompt_parts if part).strip()

            formatted_prompt = self._build_generic_prompt(system_prompt, user_prompt)

            raw = self._generate_text_with_prompt(
                formatted_prompt,
                max_tokens=section["max_tokens"],
                temperature=0.6,
                top_p=0.9,
                do_sample=True,
                progress_callback=progress_callback,
            )

            output_parts.append(self._normalize_section_output(raw, section["title"], placeholder))

        return "\n\n".join(part for part in output_parts if part).strip()

    def _build_generic_prompt(self, system_prompt: str, user_prompt: str) -> str:
        """Build a generic prompt with ChatML when supported."""
        model_lower = self.model_name.lower() if hasattr(self, "model_name") else ""
        supports_chatml = any(x in model_lower for x in ["qwen", "mistral", "phi"])

        if supports_chatml:
            return (
                f"<|im_start|>system\n{system_prompt}<|im_end|>\n"
                f"<|im_start|>user\n{user_prompt}<|im_end|>\n"
                f"<|im_start|>assistant\n"
            )

        return f"Instructions: {system_prompt}\n\n{user_prompt}\n\nAnswer:\n"

    @staticmethod
    def _strip_generation_artifacts(text: str) -> str:
        """Strip whitespace and Qwen end-of-turn token from raw model output."""
        content = text.strip()

        if "<|im_end|>" in content:
            content = content.split("<|im_end|>")[0]

        return content.strip()

    @staticmethod
    def _extract_cv_content(generated_text: str) -> str:
        """Extrait et nettoie le contenu du CV généré."""
        content = QwenManager._strip_generation_artifacts(generated_text)

        # S'assurer que le contenu commence par un titre

        if not content.startswith("#"):
            lines = content.split("\n")

            for i, line in enumerate(lines):
                if line.strip().startswith("#"):
                    content = "\n".join(lines[i:])

                    break

        return content

    def generate_cover_letter(
        self,
        prompt: str,
        progress_callback=None,
        *,
        _meta_recovery_retry: bool = False,
        _oom_recovery_retry: bool = False,
    ) -> str:
        """Génère une lettre de motivation avec Qwen2.5-32B."""
        self._clear_last_generation_error()

        if not self.model_loaded:
            self.load_model(
                progress_callback,
                allow_fallback=False,
            )

        if getattr(self, "current_loader", "transformers") == "llama_cpp":
            try:
                if progress_callback:
                    progress_callback("🦙 Génération de la lettre via llama.cpp...")

                system_prompt = self._letter_system_prompt()
                user_prompt = self._letter_user_prompt(prompt)
                params = self._resolve_role_params("cover_letter")
                temperature = float(params.get("temperature") or 0.36)
                top_p = float(params.get("top_p") or 0.92)
                max_new_tokens = int(params.get("max_new_tokens") or 1200)

                try:
                    ctx_size = int(getattr(getattr(self._llama_cpp_server, "config", None), "ctx_size", 4096))
                except Exception:
                    ctx_size = 4096
                max_tokens = max(256, int(min(max_new_tokens, ctx_size // 2)))

                generated_text = self._llama_cpp_chat(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    top_p=top_p,
                )
                letter_content = self._extract_letter_content(generated_text)
                if progress_callback:
                    progress_callback("✨ Lettre de motivation générée !")
                return letter_content
            except Exception as e:
                logger.error(f"Erreur génération lettre (llama.cpp): {e}")
                self._set_last_generation_error(f"cover_letter_llama_cpp: {e}")
                self._record_failure(f"cover_letter_llama_cpp: {str(e)[:240]}")

                raise RuntimeError(f"Cover letter generation failed (llama.cpp): {e}") from e

        if not TRANSFORMERS_AVAILABLE or self._model is None:
            self._set_last_generation_error("cover_letter: model backend unavailable")
            raise RuntimeError("Cover letter generation failed: model backend unavailable")

        try:
            if progress_callback:
                progress_callback("💌 Génération de la lettre de motivation...")

            # Prompt spécifique pour la lettre
            letter_prompt = self._build_letter_prompt(prompt)
            params = self._resolve_role_params("cover_letter")
            desired_new_tokens = int(params.get("max_new_tokens") or 1200)
            temperature = float(params.get("temperature") or 0.36)
            top_p = float(params.get("top_p") or 0.92)
            top_k = int(params.get("top_k") or 60)
            repetition_penalty = float(params.get("repetition_penalty") or 1.08)
            do_sample = bool(params.get("do_sample", temperature > 0.0))

            # Budget tokens: adapter le prompt et la génération selon la limite recommandée.
            try:
                opt_max_len = int((self._optimization_config or {}).get("max_model_len") or 0)
            except Exception:
                opt_max_len = 0
            role_max_total = int(params.get("max_total_tokens") or 0)
            max_total_len = min(role_max_total or opt_max_len or 4096, 4096)
            max_new_tokens_cap = min(desired_new_tokens, max_total_len // 2)
            role_max_input = int(params.get("max_input_tokens") or 0)
            prompt_max_len = max(256, max_total_len - max_new_tokens_cap - 64)
            prompt_max_len = min(prompt_max_len, 3072)
            if role_max_input:
                prompt_max_len = min(prompt_max_len, max(256, role_max_input))

            inputs = self._tokenizer(letter_prompt, return_tensors="pt", truncation=True, max_length=prompt_max_len).to(
                self._device
            )

            input_len = int(inputs.input_ids.shape[1])
            allowed_new_tokens = max_total_len - input_len - 32
            if allowed_new_tokens > 0:
                max_new_tokens = min(desired_new_tokens, max_new_tokens_cap, allowed_new_tokens)
            else:
                max_new_tokens = max_new_tokens_cap

            slow_device = self._detect_slow_device()
            use_cache = self._resolve_kv_cache(progress_callback)
            if slow_device:
                max_new_tokens = min(max_new_tokens, 900)
            if not use_cache:
                max_new_tokens = min(max_new_tokens, 768)

            if slow_device:
                logger.info(
                    "Cover letter slow mode: cap max_new_tokens=%s",
                    max_new_tokens,
                )
            if not use_cache:
                logger.info(
                    "Cover letter no-cache mode: cap max_new_tokens=%s",
                    max_new_tokens,
                )

            with torch.no_grad():
                outputs = self._model.generate(
                    **inputs,
                    max_new_tokens=max_new_tokens,
                    temperature=temperature,
                    top_p=top_p,
                    top_k=top_k,
                    do_sample=do_sample,
                    repetition_penalty=repetition_penalty,
                    pad_token_id=self._tokenizer.eos_token_id,
                    eos_token_id=self._tokenizer.eos_token_id,
                    use_cache=use_cache,
                )

            generated_text = self._tokenizer.decode(outputs[0][inputs.input_ids.shape[1] :], skip_special_tokens=True)

            letter_content = self._extract_letter_content(generated_text)

            if not str(letter_content or "").strip():
                raise RuntimeError("Cover letter generation returned empty output")

            if progress_callback:
                progress_callback("✨ Lettre de motivation générée !")

            return letter_content

        except Exception as e:
            logger.error(f"Erreur génération lettre: {e}")
            self._set_last_generation_error(f"cover_letter: {e}")
            self._record_failure(f"cover_letter: {str(e)[:240]}")

            if self._is_meta_tensor_error(e):
                if not _meta_recovery_retry:
                    logger.warning(
                        "Cover letter meta tensor error detected; retrying once with safer reload policy."
                    )
                    try:
                        self._activate_meta_recovery_mode(
                            reason="cover_letter",
                            progress_callback=progress_callback,
                        )
                        self.unload_model(reason="cover letter meta tensor")
                        self.load_model(
                            progress_callback,
                            allow_fallback=False,
                        )
                        return self.generate_cover_letter(
                            prompt,
                            progress_callback=progress_callback,
                            _meta_recovery_retry=True,
                            _oom_recovery_retry=_oom_recovery_retry,
                        )
                    except Exception as retry_exc:
                        logger.error("Cover letter retry after meta tensor failed: %s", retry_exc)
                logger.warning(
                    "Cover letter meta tensor error detected; unloading model for safe reload."
                )
                try:
                    self.unload_model(reason="cover letter meta tensor")
                except Exception:
                    pass

            lowered = str(e).lower()
            if "out of memory" in lowered or "cuda out of memory" in lowered:
                if not _oom_recovery_retry:
                    logger.warning(
                        "Cover letter OOM detected; retrying once with CUDA/hybrid reload policy."
                    )
                    try:
                        self.unload_model(reason="cover letter OOM")
                        self.load_model(
                            progress_callback,
                            allow_fallback=False,
                        )
                        return self.generate_cover_letter(
                            prompt,
                            progress_callback=progress_callback,
                            _meta_recovery_retry=_meta_recovery_retry,
                            _oom_recovery_retry=True,
                        )
                    except Exception as retry_exc:
                        logger.error("Cover letter retry after OOM failed: %s", retry_exc)
                logger.warning(
                    "Cover letter OOM detected; unloading model to recover memory."
                )
                try:
                    self.unload_model(reason="cover letter OOM")
                except Exception:
                    pass

            raise RuntimeError(f"Cover letter generation failed: {e}") from e

    @staticmethod
    def _letter_system_prompt() -> str:

        return """Tu es un recruteur senior (HR) et expert en redaction de lettres de motivation.
Ta mission: produire une lettre 100% personnalisee pour l'offre cible, que le candidat pourra relire et corriger.


Contraintes absolues:
- N'invente jamais de faits (experiences, dates, entreprises, diplomes, competences, projets, chiffres, contacts).
- Utilise uniquement les informations presentes dans les DONNEES CANDIDAT fournies.
- Si une information necessaire manque, laisse le champ vide (pas de placeholder, pas d'hypothese).
- Tu peux reformuler et utiliser des synonymes/termes equivalents pour coller a l'offre, tant que le fond reste vrai et verifiable.
- Structure obligatoire: Objet, formule d'appel, 2-3 paragraphes, conclusion + formule de politesse.
- Longueur: maximum 1 page (court, dense, sans blabla).
- Style: professionnel, specifique a l'offre (mots-cles) sans phrases generiques.
- Sortie: texte uniquement (pas de Markdown, pas d'explications)."""
    @staticmethod
    def _letter_user_prompt(base_prompt: str) -> str:

        return f"""{base_prompt}



Genere la lettre finale (texte uniquement), en respectant la structure demandee."""
    def _build_letter_prompt(self, base_prompt: str) -> str:
        """Construit un prompt pour lettre de motivation."""
        system_prompt = self._letter_system_prompt()
        user_prompt = self._letter_user_prompt(base_prompt)
        return f"<|im_start|>system\n{system_prompt}<|im_end|>\n<|im_start|>user\n{user_prompt}<|im_end|>\n<|im_start|>assistant\n"

    @staticmethod
    def _extract_letter_content(generated_text: str) -> str:
        """Delegate to _extract_structured_content (identical implementation)."""
        return QwenManager._extract_structured_content(generated_text)

    @staticmethod
    def _extract_structured_content(generated_text: str) -> str:

        return QwenManager._strip_generation_artifacts(generated_text)

    def cleanup_memory(self):
        """Nettoie la mémoire GPU/CPU."""
        # Si un serveur llama.cpp tourne et qu'on change de modèle, arrêter l'ancien serveur.
        server = getattr(self, "_llama_cpp_server", None)
        if server is not None and getattr(self, "_current_model_path", None) != getattr(self, "model_name", None):
            try:
                server.stop()
            except Exception:
                pass
            self._llama_cpp_server = None
        try:
            import gc

            gc.collect()
        except Exception:
            pass
        if TORCH_AVAILABLE and torch.cuda.is_available():
            try:
                torch.cuda.empty_cache()
                if hasattr(torch.cuda, "ipc_collect"):
                    torch.cuda.ipc_collect()
            except Exception:
                pass
        logger.info("Mémoire nettoyée")

    def unload_model(self, reason: str = "") -> None:
        """Décharge le modèle pour libérer la VRAM entre les étapes."""
        note = f" ({reason})" if reason else ""
        try:
            if self.model_loaded or self._model is not None:
                logger.info("Déchargement du modèle%s", note)
        except Exception:
            pass
        # Forcer l'arrêt d'un serveur llama.cpp si nécessaire.
        self._current_model_path = None
        self._model = None
        self._tokenizer = None
        self._device = None
        self.model_loaded = False

        if self._memory_manager is not None:
            self._memory_manager.reset_run_counter()

        try:
            self.cleanup_memory()
        except Exception:
            pass
