"""
GPU Utils Optimized
===================

Version optimisée avec cache pour la détection GPU.
Évite les détections répétées coûteuses au démarrage.
"""

import json
import psutil
import time
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG
logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)

# Lazy import pour éviter le chargement de PyTorch au démarrage
_torch = None

def get_torch():
    """Import lazy de PyTorch."""
    global _torch
    if _torch is None:
        try:
            import torch
            _torch = torch
        except ImportError:
            logger.warning("PyTorch non disponible - GPU utils en mode simulation")
            # Mock torch pour éviter les erreurs
            class MockTorch:
                device = lambda x: type('device', (), {'type': x})()
                cuda = type('cuda', (), {
                    'is_available': lambda: False,
                    'device_count': lambda: 0,
                    'get_device_name': lambda x: 'Mock GPU',
                    'get_device_properties': lambda x: type('props', (), {'total_memory': 8*(1024**3)})(),
                    'memory_allocated': lambda x: 0,
                    'memory_reserved': lambda x: 0,
                    'empty_cache': lambda: None
                })()
                backends = type('backends', (), {
                    'cudnn': type('cudnn', (), {'benchmark': True, 'deterministic': False})()
                })()
                float16 = 'float16'
                float32 = 'float32'
                version = type('version', (), {'cuda': '11.8'})()
            _torch = MockTorch()
    return _torch

# Cache GPU settings
GPU_CACHE_FILE = Path("cache/.cvmatch_gpu_cache")
GPU_CACHE_VALIDITY_HOURS = 48  # Cache GPU valide 48h

# Mock device léger pour éviter l'import PyTorch
class MockDevice:
    """Mock device pour CPU-only sans importer PyTorch."""
    def __init__(self, device_type: str = "cpu"):
        self.type = device_type
    
    def __str__(self):
        return f"device(type='{self.type}')"
    
    def __repr__(self):
        return self.__str__()


class GPUManager:
    """Gestionnaire GPU avec détection automatique et optimisation + cache."""
    
    def __init__(self, use_cache: bool = True):
        self.device = None
        self.gpu_info = None
        self.use_cache = use_cache
        self._torch_available = False
        self._detect_hardware()
    
    def _load_gpu_cache(self) -> Optional[Dict[str, Any]]:
        """Charger le cache de détection GPU."""
        if not self.use_cache or not GPU_CACHE_FILE.exists():
            return None
        
        try:
            with open(GPU_CACHE_FILE, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            # Vérifier la validité du cache
            cache_time = cache_data.get('timestamp', 0)
            if time.time() - cache_time > GPU_CACHE_VALIDITY_HOURS * 3600:
                return None  # Cache expiré
            
            logger.info("🎮 Using cached GPU detection ⚡")
            return cache_data.get('gpu_info')
        except (json.JSONDecodeError, KeyError, FileNotFoundError):
            return None
    
    def _save_gpu_cache(self, gpu_info: Dict[str, Any]):
        """Sauvegarder le cache de détection GPU."""
        if not self.use_cache:
            return
        
        try:
            cache_data = {
                'timestamp': time.time(),
                'gpu_info': gpu_info
            }
            
            with open(GPU_CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2)
        except Exception as e:
            logger.warning(f"Cannot save GPU cache: {e}")
    
    def _detect_hardware(self):
        """Détecte le matériel disponible avec cache optionnel."""
        # Essayer le cache d'abord
        cached_info = self._load_gpu_cache()
        if cached_info:
            self.gpu_info = cached_info
            self._torch_available = cached_info.get('torch_available', False)
            
            # Optimisation: éviter l'import PyTorch si pas de CUDA
            if cached_info.get('cuda_available') and self._torch_available:
                # Seulement si CUDA détecté, importer PyTorch pour validation
                torch = get_torch()
                if hasattr(torch, 'device') and torch.cuda.is_available():
                    self.device = torch.device("cuda")
                else:
                    self.device = torch.device("cpu")
            else:
                # CPU-only ou pas de PyTorch: utiliser mock device léger
                if self._torch_available:
                    self.device = MockDevice("cpu")
                else:
                    self.device = None
                logger.info("⚡ Using cached GPU detection (CPU-only, no PyTorch import)")
            return
        
        logger.info("🔍 Detecting GPU hardware (no cache)...")
        
        # Détection fraîche
        torch = get_torch()
        self._torch_available = hasattr(torch, 'cuda')
        
        gpu_info = {'torch_available': self._torch_available}
        
        if self._torch_available and torch.cuda.is_available():
            self.device = torch.device("cuda")
            gpu_count = torch.cuda.device_count()
            
            # Info GPU principal
            gpu_name = torch.cuda.get_device_name(0)
            gpu_memory = torch.cuda.get_device_properties(0).total_memory / (1024**3)  # GB
            
            gpu_info.update({
                "available": True,
                "cuda_available": True,
                "count": gpu_count,
                "name": gpu_name,
                "total_memory_gb": gpu_memory,
                "cuda_version": torch.version.cuda if hasattr(torch.version, 'cuda') else 'Unknown'
            })
            
            logger.info(f"GPU détecté: {gpu_name} ({gpu_memory:.1f}GB VRAM)")
        else:
            self.device = torch.device("cpu") if self._torch_available else None
            gpu_info.update({
                "available": False,
                "cuda_available": False,
                "reason": "PyTorch non installé" if not self._torch_available else "Aucun GPU CUDA disponible"
            })
            reason = "PyTorch non installé" if not self._torch_available else "Aucun GPU CUDA disponible"
            logger.info(f"{reason} - Utilisation CPU")
        
        self.gpu_info = gpu_info
        
        # Sauvegarder en cache
        self._save_gpu_cache(gpu_info)
    
    def get_available_vram(self) -> float:
        """Retourne la VRAM disponible en GB."""
        if not self._torch_available or not self.gpu_info.get("available", False):
            return 0.0
        
        # Import PyTorch seulement si vraiment nécessaire (CUDA disponible)
        if not self.gpu_info.get("cuda_available", False):
            return 0.0
            
        torch = get_torch()
        torch.cuda.empty_cache()
        free_memory = torch.cuda.get_device_properties(0).total_memory - torch.cuda.memory_allocated(0)
        return free_memory / (1024**3)
    
    def recommend_quantization(self, model_size_gb: float = 32.0) -> Dict[str, Any]:
        """Recommande la quantisation optimale selon le matériel disponible."""
        if not self.gpu_info.get("available", False):
            # Éviter l'import PyTorch pour CPU-only
            return {
                "device": "cpu",
                "dtype": "float32",
                "load_in_8bit": False,
                "load_in_4bit": False,
                "reason": "GPU non disponible - CPU uniquement"
            }
        
        available_vram = self.get_available_vram()
        total_vram = float(self.gpu_info.get("total_memory_gb", 0) or 0)
        
        # Estimations optimisées pour RTX 4050 (6GB VRAM)
        memory_requirements = {
            "fp16": model_size_gb * 2,      # ~64GB (impossible RTX 4050)
            "int8": model_size_gb * 1,      # ~32GB (impossible RTX 4050)  
            "int4": model_size_gb * 0.5,    # ~16GB (impossible RTX 4050)
            "gptq": model_size_gb * 0.25,   # ~8GB (limite RTX 4050)
            "awq": model_size_gb * 0.22,    # ~7GB (optimal RTX 4050)
            "ggml": model_size_gb * 0.20,   # ~6.4GB (très optimal RTX 4050)
        }
        
        # Détection spécifique RTX 4050 / faible VRAM
        gpu_name = self.gpu_info.get("name", "").lower()
        is_rtx_4050 = "rtx 4050" in gpu_name
        is_low_vram = 0 < total_vram <= 6.5
        label = "RTX 4050" if is_rtx_4050 else "GPU faible VRAM"
        
        # Import PyTorch seulement si GPU CUDA disponible
        if self.gpu_info.get("cuda_available", False):
            torch = get_torch()
        else:
            # Retourner config CPU par défaut sans PyTorch
            return {
                "device": "cpu",
                "dtype": "float32",
                "load_in_8bit": False,
                "load_in_4bit": False,
                "reason": "CPU-only mode (no PyTorch import required)"
            }
        
        if is_rtx_4050 or is_low_vram:
            if is_rtx_4050:
                logger.info("🎮 RTX 4050 détectée - Configuration ultra-optimisée")
            else:
                logger.info("🎮 GPU faible VRAM détecté - Configuration optimisée")
            
            if available_vram >= memory_requirements["ggml"]:
                return {
                    "device": "cuda",
                    "dtype": "float16",
                    "load_in_4bit": True,
                    "bnb_4bit_compute_dtype": "float16",
                    "bnb_4bit_use_double_quant": True,
                    "reason": f"{label} optimisée: 4-bit + FP16 ({available_vram:.1f}GB disponible)"
                }
            else:
                return {
                    "device": "cpu",
                    "dtype": "float32",
                    "load_in_8bit": False,
                    "load_in_4bit": False,
                    "reason": f"VRAM insuffisante ({label}): {available_vram:.1f}GB < {memory_requirements['ggml']:.1f}GB requis"
                }
        
        # Configuration générale pour autres GPU
        if available_vram >= memory_requirements["fp16"]:
            return {
                "device": "cuda",
                "dtype": torch.float16,
                "load_in_8bit": False,
                "load_in_4bit": False,
                "reason": f"GPU haute-mémoire: FP16 ({available_vram:.1f}GB disponible)"
            }
        elif available_vram >= memory_requirements["int8"]:
            return {
                "device": "cuda",
                "dtype": torch.float16,
                "load_in_8bit": True,
                "load_in_4bit": False,
                "reason": f"GPU moyenne-mémoire: 8-bit ({available_vram:.1f}GB disponible)"
            }
        elif available_vram >= memory_requirements["int4"]:
            return {
                "device": "cuda",
                "dtype": torch.float16,
                "load_in_8bit": False,
                "load_in_4bit": True,
                "reason": f"GPU faible-mémoire: 4-bit ({available_vram:.1f}GB disponible)"
            }
        else:
            return {
                "device": "cpu",
                "dtype": torch.float32,
                "load_in_8bit": False,
                "load_in_4bit": False,
                "reason": f"VRAM insuffisante: {available_vram:.1f}GB < {memory_requirements['int4']:.1f}GB requis"
            }


# Instance globale avec cache
_gpu_manager = None

def get_gpu_manager(use_cache: bool = True) -> GPUManager:
    """Obtenir l'instance globale du gestionnaire GPU."""
    global _gpu_manager
    if _gpu_manager is None:
        _gpu_manager = GPUManager(use_cache=use_cache)
    return _gpu_manager

# Compatibility avec l'ancienne API
class GPUUtils:
    """Classe de compatibilité pour l'ancienne API."""
    
    def __init__(self):
        self.manager = get_gpu_manager()
    
    def _detect_hardware(self):
        return self.manager._detect_hardware()
    
    @property
    def device(self):
        return self.manager.device
    
    @property
    def gpu_info(self):
        return self.manager.gpu_info
    
    def get_available_vram(self):
        return self.manager.get_available_vram()
    
    def recommend_quantization(self, model_size_gb: float = 32.0):
        return self.manager.recommend_quantization(model_size_gb)
