"""
Runtime state pour les modes CPU/Offline
========================================

Gestion centralisée des modes d'exécution ML avec cache et fallbacks.
"""

from dataclasses import dataclass
from typing import Literal, Optional, Dict
import os
from pathlib import Path

Mode = Literal["rules_only", "mock", "hf_online", "hf_offline", "lite"]
Device = Literal["auto", "cpu", "cuda"]

@dataclass
class MLRuntimeState:
    """État runtime pour configuration ML dynamique."""
    
    mode: Mode = "mock"
    device: Device = "auto"
    cache_dir: str = ".hf_cache"
    enable_multilingual_fallback: bool = True

    def __post_init__(self) -> None:
        self.cache_dir = self._normalize_cache_dir(self.cache_dir)

    @staticmethod
    def _normalize_cache_dir(cache_dir: str) -> str:
        path = Path(cache_dir or ".hf_cache")
        return path.as_posix()

    def update_cache_dir(self, cache_dir: str) -> None:
        self.cache_dir = self._normalize_cache_dir(cache_dir)

    def local_files_only(self) -> bool:
        """Retourne True si on doit utiliser uniquement les fichiers locaux."""
        return self.mode == "hf_offline"

    def use_mock(self) -> bool:
        """Retourne True si on doit utiliser les backends mock."""
        return self.mode in ("rules_only", "mock")

    def is_zero_shot_enabled(self) -> bool:
        """Retourne True si la classification zero-shot est disponible."""
        return self.mode in ("mock", "hf_offline", "hf_online", "lite") and not self.mode == "rules_only"

    def is_ner_enabled(self) -> bool:
        """Retourne True si la reconnaissance d'entités nommées est disponible.""" 
        return self.mode in ("mock", "hf_offline", "hf_online", "lite") and not self.mode == "rules_only"

    def get_status_summary(self) -> str:
        """Utilisé par _dump_ml_snapshot() pour résumer l'état runtime."""
        return f"mode={self.mode} device={self.device} local_only={self.local_files_only()}"

    def get_effective_config(self, base: dict) -> dict:
        """Génère la configuration effective en appliquant les overrides runtime."""
        cfg = dict(base or {})
        
        # Configuration zero-shot
        zs = cfg.setdefault("zero_shot", {})
        if self.mode == "lite":
            zs["model"] = "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli"
        zs["device"] = self.device
        
        # Configuration NER
        ner = cfg.setdefault("ner", {})
        ner["device"] = self.device
        
        # Configuration générale
        cfg["hf_cache_dir"] = self.cache_dir
        cfg["enable_multilingual_fallback"] = self.enable_multilingual_fallback
        cfg["local_files_only"] = self.local_files_only()
        cfg["use_mock"] = self.use_mock()
        cfg["enabled"] = self.mode != "rules_only"
        
        return cfg

    def apply_env(self):
        """Applique les variables d'environnement selon le mode."""
        if self.local_files_only():
            os.environ["HF_HUB_OFFLINE"] = "1"
            os.environ["TRANSFORMERS_OFFLINE"] = "1"
        else:
            os.environ.pop("HF_HUB_OFFLINE", None)
            os.environ.pop("TRANSFORMERS_OFFLINE", None)


# Singleton global pour l'état runtime
_rt_singleton: Optional[MLRuntimeState] = None

def get_ml_runtime_state() -> MLRuntimeState:
    """Retourne l'instance singleton de l'état runtime ML."""
    global _rt_singleton
    if _rt_singleton is None:
        _rt_singleton = MLRuntimeState()  # TODO: hydrate from QSettings if present
    return _rt_singleton

def set_ml_runtime_mode(mode: Mode, device: Device = "auto"):
    """Configure le mode et device ML runtime."""
    global _rt_singleton
    state = get_ml_runtime_state()
    state.mode = mode
    state.device = device
    state.apply_env()
