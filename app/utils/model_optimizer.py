"""
Model Optimizer
===============

Utilitaire pour optimiser les téléchargements et la gestion des modèles IA
avec hf_xet et huggingface_hub.
"""

import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List
from loguru import logger

try:
    from huggingface_hub import snapshot_download, HfApi
    from huggingface_hub.utils import HfHubHTTPError
    HF_HUB_AVAILABLE = True
except ImportError:
    HF_HUB_AVAILABLE = False
    logger.warning("huggingface_hub non disponible")

try:
    import hf_xet
    HF_XET_AVAILABLE = True
    # Ne pas logger automatiquement au démarrage - seulement lors de l'utilisation
except ImportError:
    HF_XET_AVAILABLE = False


class ModelOptimizer:
    """Gestionnaire optimisé pour les modèles Hugging Face."""
    
    ALLOWED_LLM_REPO_PREFIXES = (
        "qwen/",
        "mistralai/",
    )
    LLM_REPO_HINTS = (
        "instruct",
        "chat",
        "llama",
        "qwen",
        "mistral",
        "mixtral",
        "phi",
        "gemma",
        "falcon",
        "deepseek",
        "gpt",
        "mpt",
        "internlm",
    )

    def __init__(self, cache_dir: Optional[str] = None):
        self.cache_dir = cache_dir or self._resolve_cache_dir_from_env()
        self.api = HfApi() if HF_HUB_AVAILABLE else None

    def _cache_candidates(self) -> List[str]:
        candidates = [self.cache_dir]
        default_cache = os.path.expanduser("~/.cache/huggingface/hub")
        if os.path.normcase(os.path.abspath(default_cache)) != os.path.normcase(
            os.path.abspath(self.cache_dir)
        ):
            candidates.append(default_cache)
        return candidates

    @staticmethod
    def _is_local_model_ref(model_name: str) -> bool:
        model_ref = str(model_name or "").strip()
        lowered = model_ref.lower()

        if not model_ref:
            return True
        if lowered.startswith((".", "..")):
            return True
        if os.path.isabs(model_ref):
            return True
        if "\\" in model_ref:
            return True
        if ":" in model_ref:
            return True
        if lowered.endswith(".gguf"):
            return True
        return False

    def _is_llm_repo(self, model_name: str) -> bool:
        model_ref = str(model_name or "").strip()
        if not model_ref or self._is_local_model_ref(model_ref):
            return False
        if "/" not in model_ref:
            return False
        lowered = model_ref.lower()
        return any(hint in lowered for hint in self.LLM_REPO_HINTS)

    def _is_allowed_llm_repo(self, model_name: str) -> bool:
        lowered = str(model_name or "").strip().lower()
        return any(lowered.startswith(prefix) for prefix in self.ALLOWED_LLM_REPO_PREFIXES)

    def _resolve_cached_model_snapshot(self, model_name: str) -> Optional[str]:
        model_ref = str(model_name or "").strip()
        if not model_ref or "/" not in model_ref:
            return None

        model_dir_name = f"models--{model_ref.replace('/', '--')}"
        for cache_candidate in self._cache_candidates():
            snapshots_dir = Path(cache_candidate) / model_dir_name / "snapshots"
            if not snapshots_dir.exists():
                continue
            try:
                snapshots = sorted(
                    [p for p in snapshots_dir.iterdir() if p.is_dir()],
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )
            except Exception:
                snapshots = [p for p in snapshots_dir.iterdir() if p.is_dir()]

            for snapshot in snapshots:
                if (snapshot / "config.json").exists():
                    return str(snapshot)

        return None

    @staticmethod
    def _model_ref_to_cache_slug(model_name: str) -> str:
        return str(model_name or "").strip().replace("/", "--").replace("\\", "--").replace(":", "_")

    def _build_plain_local_dir(self, model_name: str) -> Path:
        return Path(self.cache_dir) / "plain_snapshots" / self._model_ref_to_cache_slug(model_name)

    def _resolve_plain_local_snapshot(self, model_name: str) -> Optional[str]:
        local_dir = self._build_plain_local_dir(model_name)
        if (local_dir / "config.json").exists():
            return str(local_dir)
        return None

    @staticmethod
    def _is_windows_privilege_error(error: Exception) -> bool:
        message = str(error or "").lower()
        return (
            "winerror 1314" in message
            or "privilège nécessaire" in message
            or "privilege" in message
        )

    def _apply_llm_download_policy(self, model_name: str) -> Optional[str]:
        if not self._is_llm_repo(model_name):
            return None
        if self._is_allowed_llm_repo(model_name):
            return None

        cached_snapshot = self._resolve_cached_model_snapshot(model_name)
        if cached_snapshot:
            logger.warning(
                "Model download blocked by policy for %s; using cached snapshot %s",
                model_name,
                cached_snapshot,
            )
            return cached_snapshot

        allowed = ", ".join(self.ALLOWED_LLM_REPO_PREFIXES)
        raise RuntimeError(
            f"Model download blocked by policy: {model_name}. "
            f"Allowed LLM families: {allowed}"
        )

    @staticmethod
    def _resolve_cache_dir_from_env() -> str:
        """Resolve HF cache directory from runtime env with project-friendly fallbacks."""
        hub_cache = str(os.getenv("HUGGINGFACE_HUB_CACHE") or "").strip()
        if hub_cache:
            return hub_cache

        hf_home = str(os.getenv("HF_HOME") or "").strip()
        if hf_home:
            hf_home_path = Path(hf_home)
            if hf_home_path.name.lower() == "hub":
                return str(hf_home_path)
            return str(hf_home_path / "hub")

        transformers_cache = str(os.getenv("TRANSFORMERS_CACHE") or "").strip()
        if transformers_cache:
            return transformers_cache

        project_cache = Path.cwd() / ".hf_cache"
        if project_cache.exists():
            return str(project_cache)

        return os.path.expanduser("~/.cache/huggingface/hub")
        
    def check_hf_xet_status(self) -> Dict[str, Any]:
        """Vérifie le statut des optimisations hf_xet."""
        status = {
            "hf_hub_available": HF_HUB_AVAILABLE,
            "hf_xet_available": HF_XET_AVAILABLE,
            "optimizations_active": HF_HUB_AVAILABLE and HF_XET_AVAILABLE,
            "cache_dir": self.cache_dir,
        }
        
        if HF_XET_AVAILABLE:
            try:
                # Vérifier la version hf_xet
                import hf_xet
                status["hf_xet_version"] = getattr(hf_xet, "__version__", "unknown")
            except Exception as e:
                logger.warning(f"Erreur version hf_xet: {e}")
        
        return status
    
    def optimize_model_download(
        self,
        model_name: str,
        progress_callback=None,
        force_download=False
    ) -> str:
        """
        Télécharge un modèle avec optimisations hf_xet si disponible.

        Returns:
            str: Chemin vers le modèle téléchargé
        """
        if not HF_HUB_AVAILABLE:
            raise RuntimeError("huggingface_hub non disponible")

        try:
            # ════════════════════════════════════════════════════════════════
            # VÉRIFICATION DU CACHE AVANT TÉLÉCHARGEMENT
            # ════════════════════════════════════════════════════════════════
            # Évite les re-téléchargements inutiles si le modèle est déjà en cache
            if not force_download:
                try:
                    plain_snapshot = self._resolve_plain_local_snapshot(model_name)
                    if plain_snapshot:
                        logger.info(f"Model {model_name} found in local plain cache: {plain_snapshot}")
                        if progress_callback:
                            progress_callback("Model in local plain cache (no download)")
                        return plain_snapshot

                    from huggingface_hub import try_to_load_from_cache
                    for cache_candidate in self._cache_candidates():
                        cached_path = try_to_load_from_cache(
                            model_name,
                            "config.json",
                            cache_dir=cache_candidate,
                        )
                        if cached_path is not None and str(cached_path) != "_CACHED_NO_EXIST":
                            model_dir = Path(cached_path).parent
                            logger.info(f"Model {model_name} found in cache: {model_dir}")
                            if progress_callback:
                                progress_callback("Model in cache (no download)")
                            return str(model_dir)
                except Exception as e:
                    logger.debug(f"Cache check failed (download planned): {e}")

            cached_policy_path = self._apply_llm_download_policy(model_name)
            if cached_policy_path:
                if progress_callback:
                    progress_callback("Model in cache (download policy)")
                return cached_policy_path

            if progress_callback:
                if HF_XET_AVAILABLE:
                    progress_callback("🚀 Téléchargement optimisé avec hf_xet...")
                    logger.info("✅ hf_xet utilisé pour téléchargement optimisé")
                else:
                    progress_callback("📥 Téléchargement standard...")
                    logger.info("📥 Téléchargement standard (hf_xet non disponible)")

            # Configuration du téléchargement
            download_kwargs = {
                "repo_id": model_name,
                "cache_dir": self.cache_dir,
                "resume_download": not force_download,
                "local_files_only": False,
            }

            # Windows: forcer la copie au lieu des symlinks (évite WinError 1314)
            if sys.platform == "win32":
                download_kwargs["local_dir_use_symlinks"] = False

            # Si hf_xet est disponible, il sera utilisé automatiquement
            try:
                model_path = snapshot_download(**download_kwargs)
            except Exception as download_exc:
                if sys.platform == "win32" and self._is_windows_privilege_error(download_exc):
                    local_dir = self._build_plain_local_dir(model_name)
                    local_dir.mkdir(parents=True, exist_ok=True)
                    retry_kwargs = dict(download_kwargs)
                    retry_kwargs["local_dir"] = str(local_dir)
                    retry_kwargs["local_dir_use_symlinks"] = False
                    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
                    os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "0")
                    if progress_callback:
                        progress_callback("Windows sans privilèges symlink détecté: retry en mode copie locale...")
                    logger.warning(
                        "Windows privilege issue while downloading %s; retrying with local_dir=%s and symlinks disabled.",
                        model_name,
                        local_dir,
                    )
                    snapshot_download(**retry_kwargs)
                    model_path = str(local_dir)
                else:
                    raise
            
            if progress_callback:
                cache_size = self.get_cache_size()
                progress_callback(f"✅ Modèle téléchargé - Cache: {cache_size}")
            
            logger.info(f"Modèle {model_name} téléchargé vers {model_path}")
            return model_path
            
        except HfHubHTTPError as e:
            logger.error(f"Erreur téléchargement modèle {model_name}: {e}")
            raise
        except Exception as e:
            logger.error(f"Erreur inattendue: {e}")
            raise
    
    def get_cache_size(self) -> str:
        """Retourne la taille du cache des modèles."""
        try:
            cache_path = Path(self.cache_dir)
            if not cache_path.exists():
                return "0 MB"
            
            total_size = 0
            for path in cache_path.rglob("*"):
                if path.is_file():
                    total_size += path.stat().st_size
            
            # Convertir en unités lisibles
            if total_size < 1024**2:
                return f"{total_size / 1024:.1f} KB"
            elif total_size < 1024**3:
                return f"{total_size / (1024**2):.1f} MB"
            else:
                return f"{total_size / (1024**3):.1f} GB"
                
        except Exception as e:
            logger.warning(f"Erreur calcul taille cache: {e}")
            return "Unknown"
    
    def cleanup_cache(self, older_than_days: int = 30) -> Dict[str, Any]:
        """
        Nettoie le cache des modèles.
        
        Args:
            older_than_days: Supprimer les fichiers plus anciens que X jours
        """
        try:
            import time
            from datetime import datetime, timedelta
            
            cache_path = Path(self.cache_dir)
            if not cache_path.exists():
                return {"status": "no_cache", "freed_space": 0}
            
            cutoff_time = time.time() - (older_than_days * 24 * 60 * 60)
            freed_space = 0
            files_deleted = 0
            
            for path in cache_path.rglob("*"):
                if path.is_file() and path.stat().st_mtime < cutoff_time:
                    try:
                        file_size = path.stat().st_size
                        path.unlink()
                        freed_space += file_size
                        files_deleted += 1
                    except Exception as e:
                        logger.warning(f"Impossible de supprimer {path}: {e}")
            
            # Supprimer les dossiers vides
            for path in cache_path.rglob("*"):
                if path.is_dir() and not any(path.iterdir()):
                    try:
                        path.rmdir()
                    except Exception:
                        pass
            
            return {
                "status": "success",
                "files_deleted": files_deleted,
                "freed_space": freed_space,
                "freed_space_mb": freed_space / (1024**2)
            }
            
        except Exception as e:
            logger.error(f"Erreur nettoyage cache: {e}")
            return {"status": "error", "error": str(e)}
    
    def get_model_info(self, model_name: str) -> Dict[str, Any]:
        """Récupère les informations sur un modèle."""
        if not self.api:
            return {"error": "API non disponible"}
        
        try:
            model_info = self.api.model_info(model_name)
            
            return {
                "model_name": model_name,
                "downloads": getattr(model_info, 'downloads', 0),
                "likes": getattr(model_info, 'likes', 0),
                "tags": getattr(model_info, 'tags', []),
                "library_name": getattr(model_info, 'library_name', 'unknown'),
                "pipeline_tag": getattr(model_info, 'pipeline_tag', 'unknown'),
                "model_size": self.estimate_model_size(model_info),
            }
            
        except Exception as e:
            logger.error(f"Erreur info modèle {model_name}: {e}")
            return {"error": str(e)}
    
    def estimate_model_size(self, model_info) -> str:
        """Estime la taille d'un modèle."""
        try:
            # Essayer de récupérer les informations de taille depuis les fichiers
            if hasattr(model_info, 'siblings') and model_info.siblings:
                total_size = 0
                for sibling in model_info.siblings:
                    if hasattr(sibling, 'size') and sibling.size:
                        total_size += sibling.size
                
                if total_size > 0:
                    if total_size < 1024**3:
                        return f"{total_size / (1024**2):.1f} MB"
                    else:
                        return f"{total_size / (1024**3):.1f} GB"
            
            # Estimation basée sur le nom du modèle
            model_name = str(model_info.modelId).lower()
            if "32b" in model_name:
                return "~60 GB"
            elif "13b" in model_name:
                return "~25 GB"
            elif "7b" in model_name:
                return "~14 GB"
            elif "3b" in model_name:
                return "~6 GB"
            elif "1b" in model_name:
                return "~2 GB"
            else:
                return "Unknown"
                
        except Exception:
            return "Unknown"
    
    def pre_download_check(self, model_name: str) -> Dict[str, Any]:
        """Vérifie l'espace disque avant téléchargement."""
        try:
            import shutil
            
            # Espace disque disponible
            total, used, free = shutil.disk_usage(self.cache_dir)
            
            # Informations sur le modèle
            model_info = self.get_model_info(model_name)
            
            return {
                "disk_free_gb": free / (1024**3),
                "disk_total_gb": total / (1024**3),
                "cache_size": self.get_cache_size(),
                "model_estimated_size": model_info.get("model_size", "Unknown"),
                "hf_xet_active": HF_XET_AVAILABLE,
                "recommendations": self.get_download_recommendations(free, model_name)
            }
            
        except Exception as e:
            logger.error(f"Erreur vérification pré-téléchargement: {e}")
            return {"error": str(e)}
    
    def get_download_recommendations(self, free_space: int, model_name: str) -> list:
        """Génère des recommandations pour le téléchargement."""
        recommendations = []
        
        # Vérification espace disque
        free_gb = free_space / (1024**3)
        if free_gb < 10:
            recommendations.append("⚠️ Espace disque faible (<10GB)")
        
        # Recommandations modèle
        if "32b" in model_name.lower():
            recommendations.append("📊 Modèle 32B nécessite ~60GB + RAM 64GB+")
            if not HF_XET_AVAILABLE:
                recommendations.append("🚀 Installez hf_xet pour un téléchargement plus rapide")
        
        if not recommendations:
            recommendations.append("✅ Prêt pour le téléchargement")
        
        return recommendations


# Instance globale pour l'application
model_optimizer = ModelOptimizer()
