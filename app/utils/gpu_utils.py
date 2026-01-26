"""
GPU Utils
=========

Utilitaires pour la détection GPU et optimisation automatique.
"""

import psutil
from loguru import logger
from typing import Dict, Any, Optional, Tuple

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    logger.warning("PyTorch non disponible - GPU utils en mode simulation")
    TORCH_AVAILABLE = False
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
    torch = MockTorch()


class GPUManager:
    """Gestionnaire GPU avec détection automatique et optimisation."""
    
    def __init__(self):
        self.device = None
        self.gpu_info = None
        self._detect_hardware()
    
    def _detect_hardware(self):
        """Détecte le matériel disponible."""
        if TORCH_AVAILABLE and torch.cuda.is_available():
            self.device = torch.device("cuda")
            gpu_count = torch.cuda.device_count()
            
            # Info GPU principal
            gpu_name = torch.cuda.get_device_name(0)
            gpu_memory = torch.cuda.get_device_properties(0).total_memory / (1024**3)  # GB
            
            self.gpu_info = {
                "available": True,
                "count": gpu_count,
                "name": gpu_name,
                "total_memory_gb": gpu_memory,
                "cuda_version": torch.version.cuda if hasattr(torch.version, 'cuda') else 'Unknown'
            }
            
            logger.info(f"GPU détecté: {gpu_name} ({gpu_memory:.1f}GB VRAM)")
        else:
            self.device = torch.device("cpu") if TORCH_AVAILABLE else None
            self.gpu_info = {"available": False}
            reason = "PyTorch non installé" if not TORCH_AVAILABLE else "Aucun GPU CUDA disponible"
            logger.info(f"{reason} - Utilisation CPU")
    
    def get_available_vram(self) -> float:
        """Retourne la VRAM disponible en GB."""
        if not TORCH_AVAILABLE or not self.gpu_info["available"]:
            return 0.0

        try:
            if hasattr(torch.cuda, "mem_get_info"):
                free_bytes, _ = torch.cuda.mem_get_info()
                return free_bytes / (1024**3)
        except Exception:
            pass

        torch.cuda.empty_cache()
        free_memory = torch.cuda.get_device_properties(0).total_memory - torch.cuda.memory_allocated(0)
        return free_memory / (1024**3)
    
    def get_system_ram(self) -> float:
        """Retourne la RAM système TOTALE en GB (Windows libère le cache automatiquement)."""
        return psutil.virtual_memory().total / (1024**3)
    
    def recommend_quantization(self, model_size_gb: float = 32.0) -> Dict[str, Any]:
        """Recommande la quantisation optimale selon le matériel disponible."""
        if not self.gpu_info["available"]:
            return {
                "device": "cpu",
                "dtype": torch.float32,
                "load_in_8bit": False,
                "load_in_4bit": False,
                "reason": "GPU non disponible - CPU uniquement"
            }
        
        available_vram = self.get_available_vram()
        
        # Estimations optimisées pour RTX 4050 (6GB VRAM)
        memory_requirements = {
            "fp16": model_size_gb * 2,      # ~64GB (impossible RTX 4050)
            "int8": model_size_gb * 1,      # ~32GB (impossible RTX 4050)  
            "int4": model_size_gb * 0.5,    # ~16GB (impossible RTX 4050)
            "gptq": model_size_gb * 0.25,   # ~8GB (limite RTX 4050)
            "awq": model_size_gb * 0.22,    # ~7GB (optimal RTX 4050)
            "ggml": model_size_gb * 0.20,   # ~6.4GB (très optimal RTX 4050)
        }
        
        # Détection spécifique RTX 4050
        gpu_name = self.gpu_info.get("name", "").lower()
        is_rtx_4050 = "rtx 4050" in gpu_name or available_vram <= 6.5
        
        if is_rtx_4050:
            logger.info("🎮 RTX 4050 détectée - Configuration ultra-optimisée")
            
            if available_vram >= memory_requirements["ggml"]:
                return {
                    "device": "cuda",
                    "dtype": torch.float16,
                    "quantization": "ggml_q4",
                    "load_in_4bit": True,
                    "use_vllm": True,
                    "gpu_memory_utilization": 0.85,
                    "max_model_len": 4096,
                    "reason": f"RTX 4050 optimisé - GGML Q4 ({available_vram:.1f}GB VRAM)"
                }
            elif available_vram >= memory_requirements["awq"]:
                return {
                    "device": "cuda",
                    "dtype": torch.float16,
                    "quantization": "awq",
                    "load_in_4bit": True,
                    "use_vllm": True,
                    "gpu_memory_utilization": 0.80,
                    "max_model_len": 3072,
                    "reason": f"RTX 4050 - AWQ quantization ({available_vram:.1f}GB VRAM)"
                }
            elif available_vram >= memory_requirements["gptq"]:
                return {
                    "device": "cuda",
                    "dtype": torch.float16,
                    "quantization": "gptq",
                    "load_in_4bit": True,
                    "max_model_len": 2048,
                    "reason": f"RTX 4050 - GPTQ 4-bit ({available_vram:.1f}GB VRAM)"
                }
            else:
                # RTX 4050 avec très peu de VRAM libre
                return {
                    "device": "cuda",
                    "dtype": torch.float16,
                    "quantization": "exllama",
                    "load_in_4bit": True,
                    "gpu_memory_utilization": 0.95,
                    "max_model_len": 1024,
                    "reason": f"RTX 4050 mode extrême - ExLlama ({available_vram:.1f}GB VRAM)"
                }
        
        # Configuration standard pour autres GPU
        if available_vram >= memory_requirements["fp16"]:
            return {
                "device": "cuda",
                "dtype": torch.float16,
                "load_in_8bit": False,
                "load_in_4bit": False,
                "reason": f"VRAM suffisante ({available_vram:.1f}GB) pour FP16"
            }
        elif available_vram >= memory_requirements["int4"]:
            return {
                "device": "cuda",
                "dtype": torch.float16, 
                "load_in_8bit": False,
                "load_in_4bit": True,
                "reason": f"VRAM faible ({available_vram:.1f}GB) - Quantisation 4-bit"
            }
        else:
            # VRAM insuffisante, utiliser CPU + RAM
            available_ram = self.get_system_ram()
            if available_ram >= model_size_gb * 2:
                return {
                    "device": "cpu",
                    "dtype": torch.float32,
                    "load_in_8bit": False,
                    "load_in_4bit": False,
                    "reason": f"VRAM insuffisante ({available_vram:.1f}GB) - CPU avec {available_ram:.1f}GB RAM"
                }
            else:
                return {
                    "device": "cpu",
                    "dtype": torch.float32,
                    "load_in_8bit": True,
                    "load_in_4bit": False,
                    "reason": f"Mémoire limitée - CPU + quantisation 8-bit"
                }
    
    def get_rtx_4050_optimizations(self) -> Dict[str, Any]:
        """Retourne les optimisations spécifiques RTX 4050."""
        if not self.gpu_info["available"]:
            return {"rtx_4050_detected": False}
        
        gpu_name = self.gpu_info.get("name", "").lower()
        available_vram = self.get_available_vram()
        is_rtx_4050 = "rtx 4050" in gpu_name or available_vram <= 6.5
        
        optimizations = {
            "rtx_4050_detected": is_rtx_4050,
            "gpu_name": self.gpu_info.get("name", "Unknown"),
            "vram_gb": available_vram,
            "recommended_engines": [],
            "quantization_options": [],
            "performance_tips": []
        }
        
        if is_rtx_4050:
            optimizations["recommended_engines"] = [
                "vLLM (optimal)",
                "ExLlamaV2 (ultra-rapide)",
                "ctranslate2 (efficace)",
                "ONNX Runtime (compatible)"
            ]
            
            optimizations["quantization_options"] = [
                "GGML Q4 (recommandé pour 32B)",
                "AWQ (équilibre vitesse/qualité)",
                "GPTQ (économie mémoire)",
                "ExLlama (vitesse maximale)"
            ]
            
            optimizations["performance_tips"] = [
                "🚀 Utiliser vLLM avec AWQ quantization",
                "⚡ Activer FlashAttention-2 si disponible",
                "💾 GPU memory utilization à 0.85 max",
                "🔧 Réduire max_model_len si nécessaire",
                "🧹 Vider le cache CUDA régulièrement",
                "📊 Surveiller la température GPU"
            ]
        
        return optimizations
    
    def optimize_for_inference(self):
        """Optimise les paramètres pour l'inférence."""
        if TORCH_AVAILABLE and self.gpu_info["available"]:
            # Activer optimisations CUDA
            torch.backends.cudnn.benchmark = True
            torch.backends.cudnn.deterministic = False
            
            # Vider le cache CUDA
            torch.cuda.empty_cache()
            
            logger.info("Optimisations GPU activées pour l'inférence")
        else:
            logger.info("Optimisations GPU ignorées (GPU non disponible)")
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques mémoire actuelles."""
        stats = {
            "system_ram_gb": psutil.virtual_memory().total / (1024**3),
            "available_ram_gb": self.get_system_ram(),
            "gpu_available": self.gpu_info["available"]
        }
        
        if TORCH_AVAILABLE and self.gpu_info["available"]:
            stats.update({
                "total_vram_gb": self.gpu_info["total_memory_gb"],
                "available_vram_gb": self.get_available_vram(),
                "allocated_vram_gb": torch.cuda.memory_allocated(0) / (1024**3),
                "reserved_vram_gb": torch.cuda.memory_reserved(0) / (1024**3)
            })
        
        return stats


# Instance globale
gpu_manager = GPUManager()
