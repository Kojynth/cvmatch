"""
Lazy Import Manager
===================

Gestionnaire d'imports paresseux pour les modules coûteux (IA/ML).
Évite de charger les gros modules au démarrage et les charge seulement à la demande.
"""

import sys
import importlib
import time
from typing import Optional, Dict, Any, Callable
from functools import wraps
from pathlib import Path

# Logger sécurisé
try:
    from ..logging.safe_logger import get_safe_logger
    from ..config import DEFAULT_PII_CONFIG
    logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


class LazyModule:
    """Proxy pour un module qui sera chargé à la demande."""
    
    def __init__(self, module_name: str, import_func: Optional[Callable] = None):
        self._module_name = module_name
        self._module = None
        self._import_func = import_func or (lambda: importlib.import_module(module_name))
        self._load_time = None
    
    def _ensure_loaded(self):
        """S'assurer que le module est chargé."""
        if self._module is None:
            start_time = time.time()
            logger.info(f"[LOADING] Lazy loading: {self._module_name}")
            try:
                self._module = self._import_func()
                self._load_time = time.time() - start_time
                logger.info(f"[SUCCESS] Loaded {self._module_name} in {self._load_time:.2f}s")
            except Exception as e:
                logger.error(f"[ERROR] Failed to lazy load {self._module_name}: {e}")
                raise
        return self._module
    
    def __getattr__(self, name):
        module = self._ensure_loaded()
        return getattr(module, name)
    
    def __call__(self, *args, **kwargs):
        module = self._ensure_loaded()
        return module(*args, **kwargs)
    
    @property
    def is_loaded(self) -> bool:
        """Vérifier si le module est déjà chargé."""
        return self._module is not None
    
    @property
    def load_time(self) -> Optional[float]:
        """Temps de chargement en secondes."""
        return self._load_time


class LazyImportManager:
    """Gestionnaire central des imports paresseux."""
    
    def __init__(self):
        self._lazy_modules: Dict[str, LazyModule] = {}
        self._cache_file = Path(".cvmatch_lazy_cache")
    
    def register_lazy(self, name: str, module_name: str, import_func: Optional[Callable] = None) -> LazyModule:
        """Enregistrer un module pour import paresseux."""
        lazy_module = LazyModule(module_name, import_func)
        self._lazy_modules[name] = lazy_module
        return lazy_module
    
    def get_lazy(self, name: str) -> LazyModule:
        """Récupérer un module lazy enregistré."""
        if name not in self._lazy_modules:
            raise ValueError(f"Lazy module '{name}' not registered")
        return self._lazy_modules[name]
    
    def preload_critical(self, modules: list = None):
        """Pré-charger les modules critiques en arrière-plan."""
        if modules is None:
            modules = ['torch', 'transformers']  # Modules les plus critiques
        
        for module_name in modules:
            if module_name in self._lazy_modules:
                try:
                    # Charger en arrière-plan sans bloquer
                    self._lazy_modules[module_name]._ensure_loaded()
                except Exception as e:
                    logger.warning(f"Preload failed for {module_name}: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Statistiques de chargement des modules."""
        stats = {}
        for name, lazy_mod in self._lazy_modules.items():
            stats[name] = {
                'loaded': lazy_mod.is_loaded,
                'load_time': lazy_mod.load_time,
                'module_name': lazy_mod._module_name
            }
        return stats


# Instance globale
_lazy_manager = LazyImportManager()


def register_ml_modules():
    """Enregistrer tous les modules ML/IA pour lazy loading."""
    
    # PyTorch
    _lazy_manager.register_lazy('torch', 'torch')
    
    # Transformers
    _lazy_manager.register_lazy('transformers', 'transformers')
    
    # Sentence Transformers
    _lazy_manager.register_lazy('sentence_transformers', 'sentence_transformers')
    
    # FAISS
    _lazy_manager.register_lazy('faiss', 'faiss')
    
    # WeasyPrint avec fonction custom
    def load_weasyprint():
        try:
            import weasyprint
            return weasyprint
        except ImportError as e:
            logger.warning(f"WeasyPrint not available: {e}")
            return None
    
    _lazy_manager.register_lazy('weasyprint', 'weasyprint', load_weasyprint)
    
    # Modules internes GPU
    def load_gpu_utils():
        from ..utils.gpu_utils import GPUManager
        return GPUManager
    
    _lazy_manager.register_lazy('gpu_utils', 'app.utils.gpu_utils', load_gpu_utils)
    
    def load_universal_gpu():
        from ..utils.universal_gpu_adapter import UniversalGPUAdapter
        return UniversalGPUAdapter
    
    _lazy_manager.register_lazy('universal_gpu', 'app.utils.universal_gpu_adapter', load_universal_gpu)
    
    def load_model_manager():
        from ..utils.model_manager import ModelManager
        return ModelManager
    
    _lazy_manager.register_lazy('model_manager', 'app.utils.model_manager', load_model_manager)
    
    logger.info(f"[PACKAGE] Registered {len(_lazy_manager._lazy_modules)} lazy modules")


# Fonctions d'accès simplifiées
def get_torch():
    """Accès paresseux à PyTorch."""
    return _lazy_manager.get_lazy('torch')

def get_transformers():
    """Accès paresseux à Transformers."""
    return _lazy_manager.get_lazy('transformers')

def get_sentence_transformers():
    """Accès paresseux à Sentence Transformers."""
    return _lazy_manager.get_lazy('sentence_transformers')

def get_faiss():
    """Accès paresseux à FAISS."""
    return _lazy_manager.get_lazy('faiss')

def get_weasyprint():
    """Accès paresseux à WeasyPrint."""
    return _lazy_manager.get_lazy('weasyprint')

def get_gpu_utils():
    """Accès paresseux aux GPU utils."""
    return _lazy_manager.get_lazy('gpu_utils')

def get_universal_gpu():
    """Accès paresseux à l'adaptateur GPU universel."""
    return _lazy_manager.get_lazy('universal_gpu')

def get_model_manager():
    """Accès paresseux au gestionnaire de modèles."""
    return _lazy_manager.get_lazy('model_manager')


# Décorateur pour functions nécessitant ML
def requires_ml(*modules):
    """Décorateur qui charge les modules ML nécessaires avant l'exécution."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Charger les modules requis
            for module_name in modules:
                if module_name in _lazy_manager._lazy_modules:
                    _lazy_manager.get_lazy(module_name)._ensure_loaded()
            
            return func(*args, **kwargs)
        return wrapper
    return decorator


def preload_background():
    """Lancer le pré-chargement en arrière-plan."""
    _lazy_manager.preload_critical()


def get_lazy_stats():
    """Récupérer les statistiques de lazy loading."""
    return _lazy_manager.get_stats()


# Auto-registration au import
register_ml_modules()