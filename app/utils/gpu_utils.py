"""
GPU Utils
=========

Utilitaires pour la détection GPU et optimisation automatique.
"""

import psutil
import re
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

    def _get_rtx_model_number(self) -> Optional[int]:
        """Extract RTX model number from GPU name."""
        gpu_name = str(self.gpu_info.get("name", "")).lower() if self.gpu_info else ""
        match = re.search(r"rtx\s*(\d{4})", gpu_name)
        if not match:
            return None
        try:
            return int(match.group(1))
        except ValueError:
            return None
    
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
        total_vram = float(self.gpu_info.get("total_memory_gb", 0) or 0)
        
        # Estimations optimisées pour GPU faible VRAM (~6GB)
        memory_requirements = {
            "fp16": model_size_gb * 2,      # ~64GB (impossible RTX 4050)
            "int8": model_size_gb * 1,      # ~32GB (impossible RTX 4050)  
            "int4": model_size_gb * 0.5,    # ~16GB (impossible RTX 4050)
            "gptq": model_size_gb * 0.25,   # ~8GB (limite RTX 4050)
            "awq": model_size_gb * 0.22,    # ~7GB (optimal RTX 4050)
            "ggml": model_size_gb * 0.20,   # ~6.4GB (très optimal RTX 4050)
        }
        # Detection RTX et VRAM faible
        rtx_model_number = self._get_rtx_model_number()
        is_rtx_4050_or_more = rtx_model_number is not None and rtx_model_number >= 4050
        is_low_vram = 0 < total_vram <= 6.5
        label = f"RTX {rtx_model_number}" if is_rtx_4050_or_more else "GPU faible VRAM"

        if is_low_vram:
            if is_rtx_4050_or_more:
                logger.info(f"[GPU] {label} detectee - Configuration ultra-optimisee")
            else:
                logger.info("[GPU] GPU faible VRAM detectee - Configuration optimisee")
            if available_vram >= memory_requirements["ggml"]:
                return {
                    "device": "cuda",
                    "dtype": torch.float16,
                    "quantization": "ggml_q4",
                    "load_in_4bit": True,
                    "use_vllm": True,
                    "gpu_memory_utilization": 0.85,
                    "max_model_len": 4096,
                    "reason": f"{label} optimisé - GGML Q4 ({available_vram:.1f}GB VRAM)"
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
                    "reason": f"{label} - AWQ quantization ({available_vram:.1f}GB VRAM)"
                }
            elif available_vram >= memory_requirements["gptq"]:
                return {
                    "device": "cuda",
                    "dtype": torch.float16,
                    "quantization": "gptq",
                    "load_in_4bit": True,
                    "max_model_len": 2048,
                    "reason": f"{label} - GPTQ 4-bit ({available_vram:.1f}GB VRAM)"
                }
            else:
                # GPU faible VRAM avec très peu de VRAM libre
                return {
                    "device": "cuda",
                    "dtype": torch.float16,
                    "quantization": "exllama",
                    "load_in_4bit": True,
                    "gpu_memory_utilization": 0.95,
                    "max_model_len": 1024,
                    "reason": f"{label} mode extrême - ExLlama ({available_vram:.1f}GB VRAM)"
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
    
    def get_rtx_optimizations(self) -> Dict[str, Any]:
        """Return optimizations for RTX-class GPUs."""
        if not self.gpu_info["available"]:
            return {
                "rtx_4050_detected": False,
                "rtx_4050_or_more": False,
                "rtx_model_number": None,
            }

        rtx_model_number = self._get_rtx_model_number()
        is_rtx_4050 = rtx_model_number == 4050
        is_rtx_4050_or_more = rtx_model_number is not None and rtx_model_number >= 4050
        available_vram = self.get_available_vram()

        optimizations = {
            "rtx_4050_detected": is_rtx_4050,
            "rtx_4050_or_more": is_rtx_4050_or_more,
            "rtx_model_number": rtx_model_number,
            "gpu_name": self.gpu_info.get("name", "Unknown"),
            "vram_gb": available_vram,
            "recommended_engines": [],
            "quantization_options": [],
            "performance_tips": []
        }

        if is_rtx_4050_or_more:
            optimizations["recommended_engines"] = [
                "vLLM (optimal)",
                "ExLlamaV2 (ultra-rapide)",
                "ctranslate2 (efficace)",
                "ONNX Runtime (compatible)"
            ]

            optimizations["quantization_options"] = [
                "GGML Q4 (recommande pour 32B)",
                "AWQ (equilibre vitesse/qualite)",
                "GPTQ (economie memoire)",
                "ExLlama (vitesse maximale)"
            ]

            optimizations["performance_tips"] = [
                "Utiliser vLLM avec AWQ quantization",
                "Activer FlashAttention-2 si disponible",
                "GPU memory utilization a 0.85 max",
                "Reduire max_model_len si necessaire",
                "Vider le cache CUDA regulierement",
                "Surveiller la temperature GPU"
            ]

        return optimizations

    def get_rtx_4050_optimizations(self) -> Dict[str, Any]:
        """Backward-compatible alias for get_rtx_optimizations."""
        return self.get_rtx_optimizations()

    def optimize_for_inference(self):
        """Optimise les paramètres pour l'inférence."""
        if TORCH_AVAILABLE and self.gpu_info["available"]:
            # Activer optimisations CUDA
            torch.backends.cudnn.benchmark = True
            torch.backends.cudnn.deterministic = False
            try:
                if hasattr(torch.backends, "cuda"):
                    # Prefer memory-efficient SDPA path when available.
                    if hasattr(torch.backends.cuda, "enable_mem_efficient_sdp"):
                        torch.backends.cuda.enable_mem_efficient_sdp(True)
                    if hasattr(torch.backends.cuda, "enable_math_sdp"):
                        torch.backends.cuda.enable_math_sdp(True)
                    if hasattr(torch.backends.cuda, "enable_flash_sdp"):
                        torch.backends.cuda.enable_flash_sdp(True)
                    if hasattr(torch.backends.cuda, "matmul") and hasattr(torch.backends.cuda.matmul, "allow_tf32"):
                        torch.backends.cuda.matmul.allow_tf32 = True
            except Exception as exc:
                logger.debug(f"CUDA SDPA optimization setup skipped: {exc}")
            
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
