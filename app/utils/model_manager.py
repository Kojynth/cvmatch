"""
Model Manager
=============

Gestionnaire des modèles IA avec détection automatique et recommandations.
"""

import os
import shutil
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
from loguru import logger
from .model_registry import model_registry


try:
    from .universal_gpu_adapter import universal_gpu_adapter
    GPU_ADAPTER_AVAILABLE = True
except ImportError:
    GPU_ADAPTER_AVAILABLE = False
    logger.warning("GPU Adapter non disponible")


@dataclass
class ModelInfo:
    """Informations sur un modèle IA."""
    name: str
    display_name: str
    vram_required: float  # GB (VRAM GPU)
    ram_required: float  # GB (RAM CPU)
    quality_stars: int  # 1-5
    speed_rating: int  # 1-3 (3 = plus rapide)
    description: str
    model_path: str
    quantization: str = "auto"
    use_flash_attention: bool = False
    use_vllm: bool = False
    loader: str = "transformers"
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class ModelTier(str, Enum):
    """Niveaux de modèles."""
    LIGHT = "light"
    MEDIUM = "medium" 
    HEAVY = "heavy"
    CPU_FALLBACK = "cpu_fallback"


class ModelManager:
    """Gestionnaire principal des modèles IA."""
    
    # Configuration globale
    OFFLINE_MODE = True  # MODE OFFLINE - Évite téléchargements automatiques
    MAX_DOWNLOAD_TIME_MINUTES = 2  # Timeout rapide pour téléchargements
    DROPDOWN_TAG = "default"
    
    def __init__(self):
        self.registry = model_registry
        self._models_map = self._load_registry_profiles()
        self.gpu_info = self._get_gpu_info()
        self.system_ram_gb = self._get_system_ram_gb()
        self.recommended_model = self._get_recommended_model()
        self.available_models = self._get_available_models()
    
    def _load_registry_profiles(self) -> Dict[str, ModelInfo]:
        profiles: Dict[str, ModelInfo] = {}
        for profile in self.registry.list_profiles():
            extra = dict(profile.extra) if profile.extra else {}
            profiles[profile.key] = ModelInfo(
                name=profile.key,
                display_name=profile.display_name,
                vram_required=profile.min_vram_gb,
                ram_required=profile.min_ram_gb,  # RAM CPU requise
                quality_stars=profile.quality_stars,
                speed_rating=profile.speed_rating,
                description=profile.description,
                model_path=profile.model_id,
                quantization=profile.quantization,
                use_flash_attention=bool(extra.pop('use_flash_attention', False)),
                use_vllm=bool(extra.pop('use_vllm', False)),
                loader=profile.loader,
                tags=list(profile.tags),
                metadata=extra,
            )
        return profiles

    def _get_system_ram_gb(self) -> float:
        try:
            import psutil

            return float(psutil.virtual_memory().total) / (1024 ** 3)
        except Exception:
            return 0.0

    def _get_gpu_info(self) -> Dict[str, Any]:
        """Récupère les informations GPU."""
        if GPU_ADAPTER_AVAILABLE:
            return universal_gpu_adapter.gpu_info
        return {
            "available": False,
            "name": "CPU seulement",
            "vram_gb": 0,
            "score": 0,
            "tier": "cpu_only"
        }
    
    def _get_recommended_model(self) -> str:
        """Determine le modele recommande a partir du registre dynamique."""
        # Utiliser RAM TOTALE (Windows libère le cache automatiquement quand nécessaire)
        try:
            import psutil
            ram_total_gb = psutil.virtual_memory().total / (1024**3)
        except ImportError:
            ram_total_gb = self.system_ram_gb

        hardware = {
            "available": self.gpu_info.get("available", False),
            "vram_gb": self.gpu_info.get("vram_gb", 0),
            "ram_gb": ram_total_gb,  # RAM totale
        }
        selected = self.registry.select_profile(hardware)
        if selected and selected.key in self._models_map:
            logger.info(
                "Modele recommande depuis registre: %s (RAM dispo: %.1fGB)",
                selected.key,
                ram_total_gb,
            )
            return selected.key
        if self._models_map:
            fallback_key = next(iter(self._models_map))
            logger.warning("Aucun profil recommande trouve, fallback sur %s", fallback_key)
            return fallback_key
        logger.error("Registre de modeles vide, utilisation de 'tinyllama' par defaut")
        return "tinyllama"

    def _get_available_models(self) -> List[str]:
        """Retourne la liste des modèles compatibles avec le hardware."""
        vram_gb = float(self.gpu_info.get("vram_gb", 0) or 0)
        vram_tolerance = 0.25
        available: List[str] = []

        # Utiliser RAM TOTALE (Windows libère le cache automatiquement)
        try:
            import psutil
            ram_total_gb = psutil.virtual_memory().total / (1024**3)
        except ImportError:
            ram_total_gb = self.system_ram_gb

        cuda_actually_available = False
        try:
            import torch
            cuda_actually_available = torch.cuda.is_available() and torch.cuda.device_count() > 0
        except ImportError:
            pass

        for model_id, model_info in self._models_map.items():
            ram_required = model_info.ram_required

            if not cuda_actually_available:
                # Mode CPU: vérifier vram_required == 0 ET RAM suffisante
                if model_info.vram_required == 0:
                    # Marge de 20% pour la RAM
                    if ram_total_gb >= ram_required * 0.8:
                        available.append(model_id)
            else:
                # Mode GPU: vérifier VRAM
                if model_info.vram_required == 0 or model_info.vram_required <= vram_gb + vram_tolerance:
                    available.append(model_id)

        available.sort(key=lambda key: self._models_map[key].quality_stars, reverse=True)
        return available

    def get_dropdown_model_ids(self) -> List[str]:
        """Retourne les modeles autorises dans le menu deroulant."""
        tagged = [
            model_id
            for model_id, model_info in self._models_map.items()
            if self.DROPDOWN_TAG in (model_info.tags or [])
        ]
        return tagged or list(self._models_map.keys())

    def get_model_info(self, model_id: str) -> Optional[ModelInfo]:
        """Récupère les informations d'un modèle."""
        return self._models_map.get(model_id)

    def prune_model_cache_except(self, model_id: str) -> List[str]:
        """Supprime les caches HF des modeles non selectionnes."""
        model_info = self.get_model_info(model_id)
        if not model_info:
            return []

        model_path = model_info.model_path
        if model_path and os.path.exists(model_path):
            # Modele local: ne pas toucher aux caches HF.
            return []

        keep_key = None
        if isinstance(model_path, str) and "/" in model_path:
            keep_key = f"models--{model_path.replace('/', '--')}"
        else:
            keep_key = f"models--{model_id.replace('/', '--')}"

        hf_home = os.getenv("HF_HOME")
        hub_cache = os.getenv("HUGGINGFACE_HUB_CACHE")
        if hub_cache:
            cache_root = Path(hub_cache)
        elif hf_home:
            cache_root = Path(hf_home) / "hub"
        else:
            cache_root = Path.home() / ".cache" / "huggingface" / "hub"

        if not cache_root.exists():
            return []

        deleted: List[str] = []
        for entry in cache_root.glob("models--*"):
            if keep_key and entry.name == keep_key:
                continue
            if not entry.is_dir():
                continue
            try:
                shutil.rmtree(entry)
                deleted.append(entry.name)
            except Exception as exc:
                logger.warning("Cache delete failed for %s: %s", entry, exc)

        return deleted

    def get_model_display_info(self, model_id: str) -> Dict[str, Any]:
        """Retourne les infos d'affichage adaptées au hardware utilisateur."""
        model_info = self.get_model_info(model_id)
        if not model_info:
            return {}
        
        # Détection hardware dynamique
        cuda_available = False
        try:
            import torch
            cuda_available = torch.cuda.is_available() and torch.cuda.device_count() > 0
        except ImportError:
            pass
        
        # Calcul du temps estimé selon la configuration réelle
        estimated_time = self._calculate_estimated_time(model_id, cuda_available)
        
        # Détermination du statut du modèle sur cette machine
        model_status = self._get_model_status(model_id, cuda_available)
        
        # Calcul de la note de performance pour cette machine
        performance_score = self._calculate_performance_score(model_id, cuda_available)
        
        return {
            "display_name": model_info.display_name,
            "vram_required": model_info.vram_required,
            "ram_required": model_info.ram_required,  # RAM CPU requise
            "quality_stars": model_info.quality_stars,  # Nombre d'étoiles
            "speed_rating": model_info.speed_rating,    # Nombre d'éclairs
            "description": model_info.description,
            "estimated_time": estimated_time,
            "is_recommended": model_id == self.recommended_model,
            "is_available": model_id in self.available_models,
            "model_status": model_status,
            "performance_score": performance_score,
            "hardware_optimized": cuda_available and model_info.vram_required > 0,
            "cpu_optimized": model_info.vram_required == 0,
            "loader": getattr(model_info, 'loader', 'transformers'),
            "quantization": model_info.quantization,
            "tags": getattr(model_info, 'tags', []),
            "metadata": getattr(model_info, 'metadata', {})
        }
    
    def _calculate_estimated_time(self, model_id: str, cuda_available: bool) -> int:
        """Calcule le temps estimé selon le hardware réel."""
        model_info = self.get_model_info(model_id)
        if not model_info:
            return 10
        
        if cuda_available and model_info.vram_required > 0:
            # Mode GPU - selon le score GPU
            gpu_score = self.gpu_info.get("score", 0)
            if gpu_score >= 80:    # RTX 4070+ 
                base_time = 2
            elif gpu_score >= 60:  # RTX 4060+
                base_time = 3
            elif gpu_score >= 40:  # RTX 4050+
                base_time = 4
            elif gpu_score >= 20:  # GTX 1660+
                base_time = 6
            else:                  # GPU anciens
                base_time = 8
        else:
            # Mode CPU - selon les specs CPU
            try:
                import psutil
                ram_gb = psutil.virtual_memory().total / (1024**3)
                cpu_count = psutil.cpu_count()
                
                if ram_gb >= 32 and cpu_count >= 16:    # Workstation
                    base_time = 3
                elif ram_gb >= 16 and cpu_count >= 8:   # PC puissant
                    base_time = 5
                elif ram_gb >= 8 and cpu_count >= 4:    # PC correct
                    base_time = 8
                else:                                    # PC léger
                    base_time = 12
            except ImportError:
                base_time = 10
        
        # Ajustement selon la taille du modèle
        size_multipliers = {
            "qwen2-0.5b": 0.2,   # Ultra-léger Qwen3-0.6B
            "tinyllama": 0.3,
            "phi-3-mini": 0.6,
            "qwen2-1.5b": 0.5,   # Qwen3-1.7B
            "qwen2-3b": 0.7,     # Qwen3-4B
            "mistral-7b": 1.0,
            "qwen-7b": 1.2,
            "qwen-14b": 2.0,
            "qwen-32b": 4.0
        }
        
        multiplier = size_multipliers.get(model_id, 1.0)
        return max(1, int(base_time * multiplier))
    
    def _get_model_status(self, model_id: str, cuda_available: bool) -> str:
        """Détermine le statut du modèle sur cette machine.

        Règles strictes pour les statuts:
        - "recommended": modèle recommandé pour cette config
        - "available": modèle compatible et utilisable
        - "gpu_required": modèle GPU mais pas de CUDA
        - "vram_insufficient": modèle GPU mais VRAM insuffisante
        - "ram_insufficient": modèle CPU mais RAM insuffisante
        - "incompatible": autre raison d'incompatibilité
        """
        model_info = self.get_model_info(model_id)
        if not model_info:
            return "unknown"

        # Utiliser RAM TOTALE (Windows libère le cache automatiquement)
        try:
            import psutil
            ram_total = psutil.virtual_memory().total / (1024**3)
        except ImportError:
            ram_total = 999  # Si pas de psutil, on suppose assez de RAM

        vram_available = float(self.gpu_info.get("vram_gb", 0) or 0)
        vram_tolerance = 0.25

        # 1. Modèle recommandé = toujours "recommended"
        if model_id == self.recommended_model:
            return "recommended"

        # 2. Modèle GPU sans CUDA = "gpu_required"
        if model_info.vram_required > 0 and not cuda_available:
            return "gpu_required"

        # 3. Modèle GPU avec CUDA mais VRAM insuffisante = "vram_insufficient"
        if model_info.vram_required > 0 and cuda_available:
            if model_info.vram_required > vram_available + vram_tolerance:
                return "vram_insufficient"
            return "available"  # VRAM OK → disponible

        # 4. Modèle CPU (vram_required == 0)
        if model_info.vram_required == 0:
            # SEUL CAS où on affiche "ram_insufficient"
            if ram_total < model_info.ram_required * 0.8:
                return "ram_insufficient"
            return "available"  # RAM OK → disponible !

        # 5. Fallback
        return "available" if model_id in self.available_models else "incompatible"
    
    def _calculate_performance_score(self, model_id: str, cuda_available: bool) -> float:
        """Calcule un score de performance 0-10 pour cette machine."""
        model_info = self.get_model_info(model_id)
        if not model_info:
            return 0.0
        
        # Score de base selon la qualité du modèle
        base_score = model_info.quality_stars * 2  # 0-10
        
        # Ajustements selon le hardware
        if cuda_available and model_info.vram_required > 0:
            # GPU disponible et modèle GPU
            gpu_score = self.gpu_info.get("score", 0)
            if gpu_score >= 80:
                hardware_bonus = 1.0
            elif gpu_score >= 60:
                hardware_bonus = 0.8
            elif gpu_score >= 40:
                hardware_bonus = 0.6
            else:
                hardware_bonus = 0.4
        elif not cuda_available and model_info.vram_required == 0:
            # CPU seulement et modèle CPU
            try:
                import psutil
                ram_gb = psutil.virtual_memory().total / (1024**3)
                cpu_count = psutil.cpu_count()
                
                if ram_gb >= 16 and cpu_count >= 8:
                    hardware_bonus = 0.8
                elif ram_gb >= 8 and cpu_count >= 4:
                    hardware_bonus = 0.6
                else:
                    hardware_bonus = 0.4
            except ImportError:
                hardware_bonus = 0.5
        else:
            # Mismatch hardware/modèle
            hardware_bonus = 0.2
        
        final_score = min(10.0, base_score * hardware_bonus)
        return round(final_score, 1)
    
    def get_models_for_dropdown(self) -> List[Dict[str, Any]]:
        """Retourne les modèles formatés pour un dropdown avec infos adaptatives."""
        models = []
        
        # Inclure les modeles autorises par tag
        all_model_ids = self.get_dropdown_model_ids()
        
        for model_id in all_model_ids:
            model_info = self.get_model_display_info(model_id)
            
            # Créer le texte descriptif adaptatif
            status_text = self._get_status_text(model_info["model_status"])
            quality_stars = "*" * model_info["quality_stars"]
            speed_rating = "!" * model_info["speed_rating"]
            
            # Format adaptatif selon le statut
            if model_info["model_status"] == "recommended":
                display_text = f"[RECOMMANDE] {model_info['display_name']} ({model_info['estimated_time']}min) {quality_stars}"
            elif model_info["model_status"] == "gpu_required":
                display_text = f"[GPU REQUIS] {model_info['display_name']} - Nécessite CUDA/GPU"
            elif model_info["model_status"] == "vram_insufficient":
                # Afficher la VRAM requise pour aider l'utilisateur
                vram_req = model_info.get("vram_required", 0)
                display_text = f"[VRAM INSUFFISANTE] {model_info['display_name']} - {vram_req:.0f}GB VRAM requis"
            elif model_info["model_status"] == "ram_insufficient":
                # Afficher la RAM requise pour aider l'utilisateur
                ram_req = model_info.get("ram_required", 0)
                display_text = f"[RAM INSUFFISANTE] {model_info['display_name']} - {ram_req:.0f}GB requis"
            elif model_info["model_status"] == "available":
                display_text = f"[DISPONIBLE] {model_info['display_name']} ({model_info['estimated_time']}min) {quality_stars}"
            else:
                display_text = f"[INCOMPATIBLE] {model_info['display_name']}"
            
            models.append({
                "id": model_id,
                "text": display_text,
                "is_recommended": model_info["is_recommended"],
                "is_available": model_info["is_available"],
                "model_status": model_info["model_status"],
                "performance_score": model_info["performance_score"],
                "estimated_time": model_info["estimated_time"],
                "quality_stars": model_info["quality_stars"],
                "description": model_info["description"],
                "detailed_info": self._get_detailed_info(model_id, model_info)
            })
        
        # Trier par ordre de recommandation intelligent
        models.sort(key=lambda x: (
            -int(x["is_recommended"]),          # Recommandé en premier
            -x["performance_score"],            # Puis par score de performance
            x["estimated_time"],                # Puis par temps (plus rapide = mieux)
            -x["quality_stars"]                 # Puis par qualité
        ))
        
        return models
    
    def _get_status_text(self, status: str) -> str:
        """Convertit le statut en texte lisible."""
        status_map = {
            "recommended": "Recommandé",
            "available": "Disponible",
            "gpu_required": "GPU requis",
            "vram_insufficient": "VRAM insuffisante",
            "ram_insufficient": "RAM insuffisante",
            "incompatible": "Incompatible"
        }
        return status_map.get(status, "Inconnu")
    
    def _get_detailed_info(self, model_id: str, model_info: Dict[str, Any]) -> str:
        """Génère une description détaillée pour l'infobulle."""
        lines = [
            f"Modèle: {model_info['display_name']}",
            f"Qualité: {model_info['quality_stars']}/5 étoiles",
            f"Vitesse: {model_info['speed_rating']}/3",
            f"Temps estimé: ~{model_info['estimated_time']} minutes",
            f"Score performance: {model_info['performance_score']}/10",
            f"Statut: {self._get_status_text(model_info['model_status'])}",
            "",
            f"Description: {model_info['description']}"
        ]
        
        if model_info["hardware_optimized"]:
            lines.append("🎮 Optimisé GPU - Utilise votre carte graphique")
        elif model_info["cpu_optimized"]:
            lines.append("💻 Optimisé CPU - Fonctionne sans GPU")
            
        return "\n".join(lines)
    
    def validate_model_selection(self, model_id: str) -> Dict[str, Any]:
        """Valide qu'un modèle peut être utilisé selon le hardware disponible."""
        model_info = self.get_model_info(model_id)
        if not model_info:
            return {
                "valid": False,
                "error": "Modèle inconnu"
            }

        # Détection GPU
        cuda_available = False
        try:
            import torch
            cuda_available = torch.cuda.is_available() and torch.cuda.device_count() > 0
        except ImportError:
            pass

        vram_available = self.gpu_info.get("vram_gb", 0)
        vram_tolerance = 0.25

        # Vérification pour modèles GPU
        if model_info.vram_required > 0:
            if not cuda_available:
                return {
                    "valid": False,
                    "error": f"Ce modèle nécessite un GPU ({model_info.vram_required}GB VRAM). Aucun GPU CUDA détecté."
                }
            if model_info.vram_required > vram_available + vram_tolerance:
                return {
                    "valid": False,
                    "error": f"VRAM insuffisante: {model_info.vram_required}GB requis, {vram_available:.2f}GB disponible"
                }
            if model_info.vram_required > vram_available:
                logger.warning(
                    "VRAM borderline for {}: required={}GB, available={:.2f}GB",
                    model_id,
                    model_info.vram_required,
                    vram_available,
                )

        # Vérification RAM pour modèles CPU (utilise RAM totale)
        if not cuda_available:
            try:
                import psutil
                ram_total = psutil.virtual_memory().total / (1024**3)
                # Utiliser ram_required depuis le profil (plus précis)
                ram_required = model_info.ram_required

                if ram_total < ram_required * 0.8:  # Marge de 20%
                    return {
                        "valid": False,
                        "error": f"RAM insuffisante: ~{ram_required:.0f}GB requis, {ram_total:.1f}GB total"
                    }
            except ImportError:
                pass

        return {
            "valid": True,
            "model_info": model_info
        }

    def _estimate_ram_requirement(self, model_id: str) -> float:
        """Estime la RAM requise pour un modèle en mode CPU (float32)."""
        # Estimation basée sur la taille du modèle
        # En float32, chaque paramètre = 4 bytes
        # 1B params ≈ 4GB RAM, avec overhead système ~1.5x
        ram_estimates = {
            "qwen2-0.5b": 1.5,    # 0.6B params (Qwen3-0.6B)
            "tinyllama": 2.5,     # 1.1B params
            "phi-3-mini": 8.0,    # 3.8B params
            "qwen2-1.5b": 4.0,    # 1.7B params (Qwen3-1.7B)
            "qwen2-3b": 8.0,      # 4B params (Qwen3-4B)
            "mistral-7b": 16.0,   # 7B params - ATTENTION: gros modèle!
            "qwen-7b": 16.0,      # 8B params (Qwen3-8B)
            "qwen-14b": 32.0,     # 14B params
            "qwen-32b": 64.0,     # 32B params
        }
        return ram_estimates.get(model_id, 8.0)  # Default: 8GB


# Instance globale
model_manager = ModelManager()
