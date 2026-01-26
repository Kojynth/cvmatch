"""
Model Configuration Manager
============================

Gestionnaire centralisé pour synchroniser la configuration des modèles IA
entre le sélecteur compact et les paramètres avancés.
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import json
from loguru import logger

from .model_manager import model_manager, ModelInfo


class QuantizationType(str, Enum):
    """Types de quantification supportés."""
    GPTQ = "gptq"
    AWQ = "awq"
    Q4 = "q4"
    Q8 = "q8"
    FP16 = "fp16"
    AUTO = "auto"


class OptimizationType(str, Enum):
    """Types d'optimisations disponibles."""
    FLASH_ATTENTION = "flash_attention"
    XFORMERS = "xformers"
    VLLM = "vllm"
    AUTO_GPTQ = "auto_gptq"


class GenerationStyle(str, Enum):
    """Style de génération du CV."""
    UNSET = "unset"
    CONSERVATIVE = "conservative"
    CREATIVE = "creative"


@dataclass
class ModelConfiguration:
    """Configuration complète d'un modèle."""
    model_id: str
    model_name: str
    quantization: QuantizationType
    optimizations: List[OptimizationType]
    use_flash_attention: bool = False
    use_vllm: bool = False
    use_xformers: bool = True
    use_auto_gptq: bool = True
    custom_parameters: Dict[str, Any] = None
    use_registry_auto: bool = False
    generation_style: GenerationStyle = GenerationStyle.UNSET
    
    def __post_init__(self):
        if self.custom_parameters is None:
            self.custom_parameters = {}


class ModelConfigManager:
    """Gestionnaire centralisé de configuration des modèles."""
    
    def __init__(self):
        self.config_file = Path.home() / ".cvmatch" / "model_config.json"
        self.config_file.parent.mkdir(exist_ok=True)
        self._current_config = self._load_config()
        self._observers = []  # Pattern Observer pour synchronisation
    
    def _load_config(self) -> ModelConfiguration:
        """Charge la configuration depuis le fichier avec revalidation hardware."""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                    loaded_model_id = data.get('model_id', model_manager.recommended_model)

                    # Revalidation: vérifier que le modèle est compatible avec le hardware actuel
                    allowed_ids = model_manager.get_dropdown_model_ids()
                    if loaded_model_id not in model_manager.available_models or loaded_model_id not in allowed_ids:
                        recommended = model_manager.recommended_model
                        if recommended not in allowed_ids and allowed_ids:
                            recommended = allowed_ids[0]
                        logger.warning(
                            f"Modèle persisté '{loaded_model_id}' incompatible avec hardware actuel, "
                            f"basculement vers '{recommended}'"
                        )
                        loaded_model_id = recommended
                        # Mettre à jour le fichier pour éviter le problème au prochain démarrage
                        data['model_id'] = recommended
                        model_info = model_manager.get_model_info(recommended)
                        if model_info:
                            data['model_name'] = model_info.display_name

                        try:
                            with open(self.config_file, 'w', encoding='utf-8') as fw:
                                json.dump(data, fw, indent=2, ensure_ascii=False)
                            logger.info("Configuration corrigée et sauvegardée")
                        except Exception as save_err:
                            logger.warning(f"Impossible de sauvegarder la config corrigée: {save_err}")

                    return ModelConfiguration(
                        model_id=loaded_model_id,
                        model_name=data.get('model_name', 'Auto'),
                        quantization=QuantizationType(data.get('quantization', 'auto')),
                        optimizations=[OptimizationType(opt) for opt in data.get('optimizations', [])],
                        use_flash_attention=data.get('use_flash_attention', False),
                        use_vllm=data.get('use_vllm', False),
                        use_xformers=data.get('use_xformers', True),
                        use_auto_gptq=data.get('use_auto_gptq', True),
                        custom_parameters=data.get('custom_parameters', {}),
                        generation_style=GenerationStyle(data.get('generation_style', 'unset')),
                        use_registry_auto=data.get('use_registry_auto', False),
                    )
            except Exception as e:
                logger.warning(f"Erreur chargement config: {e}")

        # Configuration par défaut
        return self._create_default_config()
    
    def _create_default_config(self) -> ModelConfiguration:
        """Crée une configuration par défaut basée sur le hardware."""
        gpu_info = model_manager.gpu_info
        recommended_model = model_manager.recommended_model
        
        # Optimisations par défaut selon le hardware
        default_optimizations = []
        use_flash_attention = False
        use_vllm = False
        use_xformers = True
        use_auto_gptq = True
        
        # Configuration selon le GPU
        if gpu_info.get("available", False):
            gpu_score = gpu_info.get("score", 0)
            if gpu_score >= 80:  # GPU haut de gamme
                default_optimizations = [OptimizationType.FLASH_ATTENTION, OptimizationType.VLLM, OptimizationType.XFORMERS]
                use_flash_attention = True
                use_vllm = True
            elif gpu_score >= 60:  # GPU moyen/haut
                default_optimizations = [OptimizationType.XFORMERS, OptimizationType.AUTO_GPTQ]
                use_xformers = True
                use_auto_gptq = True
            else:  # GPU entrée de gamme
                default_optimizations = [OptimizationType.AUTO_GPTQ]
                use_auto_gptq = True
        
        # Quantification par défaut
        vram_gb = gpu_info.get("vram_gb", 0)
        if vram_gb >= 16:
            quantization = QuantizationType.AWQ
        elif vram_gb >= 8:
            quantization = QuantizationType.GPTQ
        else:
            quantization = QuantizationType.Q4
        
        return ModelConfiguration(
            model_id=recommended_model,
            model_name=model_manager.get_model_info(recommended_model).display_name,
            quantization=quantization,
            optimizations=default_optimizations,
            use_flash_attention=use_flash_attention,
            use_vllm=use_vllm,
            use_xformers=use_xformers,
            use_auto_gptq=use_auto_gptq,
            generation_style=GenerationStyle.UNSET,
            use_registry_auto=True
        )
    
    def _save_config(self):
        """Sauvegarde la configuration."""
        try:
            data = {
                'model_id': self._current_config.model_id,
                'model_name': self._current_config.model_name,
                'quantization': self._current_config.quantization.value,
                'optimizations': [opt.value for opt in self._current_config.optimizations],
                'use_flash_attention': self._current_config.use_flash_attention,
                'use_vllm': self._current_config.use_vllm,
                'use_xformers': self._current_config.use_xformers,
                'use_auto_gptq': self._current_config.use_auto_gptq,
                'custom_parameters': self._current_config.custom_parameters,
                'generation_style': self._current_config.generation_style.value,
                'use_registry_auto': self._current_config.use_registry_auto
            }
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Configuration sauvegardée: {self._current_config.model_id}")
            
        except Exception as e:
            logger.error(f"Erreur sauvegarde config: {e}")
    
    def update_generation_style(self, style: 'GenerationStyle') -> bool:
        """Met à jour le style de génération (conservateur/créatif)."""
        try:
            old_style = self._current_config.generation_style
            self._current_config.generation_style = style
            # Mirroir pour rétrocompatibilité
            self._current_config.custom_parameters["generation_style"] = style.value
            self._save_config()
            self._notify_observers('generation_style_changed', old_style, style)
            logger.info(f"Style de génération mis à jour: {old_style.value} → {style.value}")
            return True
        except Exception as e:
            logger.error(f"Erreur mise à jour style génération: {e}")
            return False
    
    def get_current_config(self) -> ModelConfiguration:
        """Retourne la configuration actuelle."""
        return self._current_config
    
    def update_model(self, model_id: str) -> bool:
        """Met à jour le modèle sélectionné."""
        allowed_ids = model_manager.get_dropdown_model_ids()
        if model_id not in allowed_ids and allowed_ids:
            logger.warning(f"Modele non autorise: {model_id} -> {allowed_ids[0]}")
            model_id = allowed_ids[0]
        model_info = model_manager.get_model_info(model_id)
        if not model_info:
            logger.error(f"Modèle inconnu: {model_id}")
            return False
        
        # Validation (warning only)
        validation = model_manager.validate_model_selection(model_id)
        if not validation.get("valid"):
            logger.warning(f"Modele invalide: {validation.get('error')} - tentative de chargement forcee")

        
        # Mise à jour
        old_model = self._current_config.model_id
        self._current_config.model_id = model_id
        self._current_config.model_name = model_info.display_name
        self._current_config.use_registry_auto = False
        
        # Ajuster la quantification selon le nouveau modèle
        self._adjust_quantization_for_model(model_info)
        
        self._save_config()
        self._notify_observers('model_changed', old_model, model_id)
        
        logger.info(f"Modèle mis à jour: {old_model} → {model_id}")
        return True
    
    def set_auto_mode(self, enabled: bool) -> bool:
        """Active ou desactive le suivi automatique du registre."""
        if enabled:
            recommended_id = model_manager.recommended_model
            info = model_manager.get_model_info(recommended_id)
            if not info:
                logger.error("Impossible de resoudre le modele recommande pour le mode auto")
                return False
            old_model = self._current_config.model_id
            self._current_config.model_id = recommended_id
            self._current_config.model_name = info.display_name
            self._current_config.use_registry_auto = True
            self._adjust_quantization_for_model(info)
            self._save_config()
            self._notify_observers('model_changed', old_model, recommended_id)
            logger.info(f"Mode auto actif -> {recommended_id}")
            return True
        if self._current_config.use_registry_auto:
            self._current_config.use_registry_auto = False
            self._save_config()
            self._notify_observers('auto_mode_disabled', True, False)
            logger.info("Mode auto desactive")
        return True

    def update_quantization(self, quantization: QuantizationType) -> bool:
        """Met à jour la quantification."""
        old_quant = self._current_config.quantization
        self._current_config.quantization = quantization
        
        self._save_config()
        self._notify_observers('quantization_changed', old_quant, quantization)
        
        logger.info(f"Quantification mise à jour: {old_quant} → {quantization}")
        return True
    
    def update_optimizations(self, optimizations: List[OptimizationType]) -> bool:
        """Met à jour les optimisations."""
        old_opts = self._current_config.optimizations.copy()
        self._current_config.optimizations = optimizations
        
        # Mettre à jour les flags individuels
        self._current_config.use_flash_attention = OptimizationType.FLASH_ATTENTION in optimizations
        self._current_config.use_vllm = OptimizationType.VLLM in optimizations
        self._current_config.use_xformers = OptimizationType.XFORMERS in optimizations
        self._current_config.use_auto_gptq = OptimizationType.AUTO_GPTQ in optimizations
        
        self._save_config()
        self._notify_observers('optimizations_changed', old_opts, optimizations)
        
        logger.info(f"Optimisations mises à jour: {len(optimizations)} actives")
        return True
    
    def _adjust_quantization_for_model(self, model_info: ModelInfo):
        """Ajuste automatiquement la quantification selon le modèle."""
        # Utiliser la quantification recommandée par le modèle
        if hasattr(model_info, 'quantization') and model_info.quantization != "auto":
            if model_info.quantization == "gptq":
                self._current_config.quantization = QuantizationType.GPTQ
            elif model_info.quantization == "awq":
                self._current_config.quantization = QuantizationType.AWQ
    
    def get_model_cache_info(self) -> Dict[str, Any]:
        """Retourne les informations sur le cache des modèles."""
        cache_dir = Path.home() / ".cache" / "cvmatch"
        
        if not cache_dir.exists():
            return {
                "exists": False,
                "path": str(cache_dir),
                "size_mb": 0,
                "model_count": 0
            }
        
        # Calculer la taille
        total_size = 0
        model_count = 0
        
        for path in cache_dir.rglob("*"):
            if path.is_file():
                total_size += path.stat().st_size
                if path.suffix in ['.bin', '.safetensors', '.pt']:
                    model_count += 1
        
        return {
            "exists": True,
            "path": str(cache_dir),
            "size_mb": total_size / (1024 * 1024),
            "model_count": model_count
        }
    
    def clear_model_cache(self) -> bool:
        """Nettoie le cache des modèles."""
        cache_dir = Path.home() / ".cache" / "cvmatch"
        
        if not cache_dir.exists():
            return True
        
        try:
            import shutil
            shutil.rmtree(cache_dir)
            cache_dir.mkdir(parents=True, exist_ok=True)
            
            logger.info("Cache des modèles nettoyé")
            self._notify_observers('cache_cleared')
            return True
            
        except Exception as e:
            logger.error(f"Erreur nettoyage cache: {e}")
            return False
    
    def add_observer(self, callback):
        """Ajoute un observer pour les changements de configuration."""
        self._observers.append(callback)
    
    def remove_observer(self, callback):
        """Supprime un observer."""
        if callback in self._observers:
            self._observers.remove(callback)
    
    def _notify_observers(self, event_type: str, *args):
        """Notifie tous les observers d'un changement."""
        for callback in self._observers:
            try:
                callback(event_type, *args)
            except Exception as e:
                logger.error(f"Erreur notification observer: {e}")


# Instance globale
model_config_manager = ModelConfigManager()
