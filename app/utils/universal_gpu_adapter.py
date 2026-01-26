"""
Universal GPU Adapter
=====================

Système adaptatif universel qui optimise automatiquement selon le GPU disponible.
De la GTX 1080 à la RTX 5070, avec garantie de génération sous 10 minutes.
"""

import re
import psutil
from typing import Dict, Any, Optional, Tuple
from loguru import logger
from .model_registry import model_registry


try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

try:
    import pynvml
    pynvml.nvmlInit()
    NVML_AVAILABLE = True
except ImportError:
    NVML_AVAILABLE = False


class UniversalGPUAdapter:
    """Adaptateur universel pour tous types de GPU."""
    
    # Base de données GPU avec scores de performance relatifs
    GPU_DATABASE = {
        # RTX 50 Series (2025+) - Performance score: 95-100
        "rtx 5090": {"score": 100, "tier": "flagship", "vram": 24, "gen": "ada_lovelace_next"},
        "rtx 5080": {"score": 85, "tier": "high_end", "vram": 16, "gen": "ada_lovelace_next"},
        "rtx 5070": {"score": 75, "tier": "high_mid", "vram": 12, "gen": "ada_lovelace_next"},
        
        # RTX 40 Series - Performance score: 60-90
        "rtx 4090": {"score": 90, "tier": "flagship", "vram": 24, "gen": "ada_lovelace"},
        "rtx 4080": {"score": 80, "tier": "high_end", "vram": 16, "gen": "ada_lovelace"},
        "rtx 4070": {"score": 70, "tier": "high_mid", "vram": 12, "gen": "ada_lovelace"},
        "rtx 4060": {"score": 65, "tier": "mid_range", "vram": 8, "gen": "ada_lovelace"},
        "rtx 4050": {"score": 60, "tier": "entry", "vram": 6, "gen": "ada_lovelace"},
        
        # RTX 30 Series - Performance score: 45-75
        "rtx 3090": {"score": 75, "tier": "flagship", "vram": 24, "gen": "ampere"},
        "rtx 3080": {"score": 70, "tier": "high_end", "vram": 10, "gen": "ampere"},
        "rtx 3070": {"score": 65, "tier": "high_mid", "vram": 8, "gen": "ampere"},
        "rtx 3060": {"score": 55, "tier": "mid_range", "vram": 8, "gen": "ampere"},
        "rtx 3050": {"score": 45, "tier": "entry", "vram": 4, "gen": "ampere"},
        
        # RTX 20 Series - Performance score: 35-60
        "rtx 2080 ti": {"score": 60, "tier": "high_end", "vram": 11, "gen": "turing"},
        "rtx 2080": {"score": 55, "tier": "high_mid", "vram": 8, "gen": "turing"},
        "rtx 2070": {"score": 50, "tier": "mid_range", "vram": 8, "gen": "turing"},
        "rtx 2060": {"score": 40, "tier": "entry", "vram": 6, "gen": "turing"},
        
        # GTX 16 Series - Performance score: 25-40
        "gtx 1660 ti": {"score": 35, "tier": "budget", "vram": 6, "gen": "turing"},
        "gtx 1660": {"score": 30, "tier": "budget", "vram": 6, "gen": "turing"},
        "gtx 1650": {"score": 25, "tier": "budget", "vram": 4, "gen": "turing"},
        
        # GTX 10 Series - Performance score: 20-45
        "gtx 1080 ti": {"score": 45, "tier": "legacy_high", "vram": 11, "gen": "pascal"},
        "gtx 1080": {"score": 40, "tier": "legacy_high", "vram": 8, "gen": "pascal"},
        "gtx 1070": {"score": 35, "tier": "legacy_mid", "vram": 8, "gen": "pascal"},
        "gtx 1060": {"score": 25, "tier": "legacy_budget", "vram": 6, "gen": "pascal"},
        "gtx 1050": {"score": 20, "tier": "legacy_budget", "vram": 4, "gen": "pascal"},
        
        # AMD GPUs (estimation basique)
        "rx 7900": {"score": 80, "tier": "high_end", "vram": 20, "gen": "rdna3"},
        "rx 6800": {"score": 65, "tier": "high_mid", "vram": 16, "gen": "rdna2"},
        "rx 6600": {"score": 45, "tier": "mid_range", "vram": 8, "gen": "rdna2"},
    }
    
    def __init__(self):
        self.gpu_info = self._detect_gpu()
        self.system_info = self._get_system_info()
        self.performance_profile = self._create_performance_profile()
        self._registry_choice = None
    
    def _detect_gpu(self) -> Dict[str, Any]:
        """Détecte le GPU et ses caractéristiques."""
        gpu_info = {
            "available": False,
            "name": "CPU seulement",
            "vram_gb": 0,
            "score": 0,
            "tier": "cpu_only",
            "generation": "none"
        }
        
        if not TORCH_AVAILABLE:
            logger.warning("PyTorch non disponible - Détection GPU limitée")
            # Tentative de détection système
            return self._detect_gpu_system_fallback()
        
        if torch.cuda.is_available():
            try:
                gpu_name = torch.cuda.get_device_name(0).lower()
                vram_bytes = torch.cuda.get_device_properties(0).total_memory
                vram_gb = vram_bytes / (1024**3)
                
                # Recherche dans la base de données
                gpu_data = self._match_gpu_in_database(gpu_name)
                
                gpu_info.update({
                    "available": True,
                    "name": gpu_name,
                    "vram_gb": vram_gb,
                    "score": gpu_data["score"],
                    "tier": gpu_data["tier"], 
                    "generation": gpu_data["gen"]
                })
                
                logger.info(f"🎮 GPU détecté: {gpu_name} ({vram_gb:.1f}GB) - Score: {gpu_data['score']}/100")
                
            except Exception as e:
                logger.error(f"Erreur détection GPU PyTorch: {e}")
                # Fallback vers détection système
                return self._detect_gpu_system_fallback()
        else:
            logger.info("CUDA non disponible dans PyTorch - Tentative détection système")
            # Fallback vers détection système
            return self._detect_gpu_system_fallback()
        
        return gpu_info
    
    def _detect_gpu_system_fallback(self) -> Dict[str, Any]:
        """Détection GPU fallback via commandes système."""
        gpu_info = {
            "available": False,
            "name": "CPU seulement",
            "vram_gb": 0,
            "score": 5,  # Score minimal pour CPU
            "tier": "cpu_only",
            "generation": "none"
        }
        
        try:
            import subprocess
            import platform
            
            if platform.system() == "Windows":
                # Utiliser nvidia-smi si disponible
                try:
                    result = subprocess.run(
                        ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                        capture_output=True, text=True, timeout=5
                    )
                    
                    if result.returncode == 0:
                        lines = result.stdout.strip().split('\n')
                        if lines and lines[0]:
                            parts = lines[0].split(', ')
                            if len(parts) >= 2:
                                gpu_name = parts[0].lower().strip()
                                vram_mb = int(parts[1])
                                vram_gb = vram_mb / 1024
                                
                                # Recherche dans la base de données
                                gpu_data = self._match_gpu_in_database(gpu_name)
                                
                                gpu_info.update({
                                    "available": True,
                                    "name": gpu_name,
                                    "vram_gb": vram_gb,
                                    "score": gpu_data["score"],
                                    "tier": gpu_data["tier"],
                                    "generation": gpu_data["gen"]
                                })
                                
                                logger.info(f"🎮 GPU détecté (nvidia-smi): {gpu_name} ({vram_gb:.1f}GB)")
                                return gpu_info
                                
                except (subprocess.SubprocessError, FileNotFoundError, ValueError):
                    pass
        
        except Exception as e:
            logger.warning(f"Erreur détection système: {e}")
        
        logger.info("💻 Aucun GPU détecté - Mode CPU activé")
        return gpu_info
    
    def _match_gpu_in_database(self, gpu_name: str) -> Dict[str, Any]:
        """Trouve le GPU dans la base de données."""
        gpu_name_clean = re.sub(r'[^a-z0-9\s]', '', gpu_name.lower())
        
        # Recherche exacte d'abord
        for db_name, data in self.GPU_DATABASE.items():
            if db_name in gpu_name_clean:
                return data
        
        # Recherche approximative
        for db_name, data in self.GPU_DATABASE.items():
            db_parts = db_name.split()
            if all(part in gpu_name_clean for part in db_parts):
                return data
        
        # Estimation par VRAM si GPU inconnu
        vram_gb = self.gpu_info.get("vram_gb", 0) if hasattr(self, 'gpu_info') else 0
        
        if vram_gb >= 20:
            return {"score": 85, "tier": "high_end", "gen": "modern"}
        elif vram_gb >= 12:
            return {"score": 70, "tier": "high_mid", "gen": "modern"}
        elif vram_gb >= 8:
            return {"score": 55, "tier": "mid_range", "gen": "modern"}
        elif vram_gb >= 6:
            return {"score": 40, "tier": "entry", "gen": "modern"}
        else:
            return {"score": 25, "tier": "budget", "gen": "legacy"}
    
    def _get_system_info(self) -> Dict[str, Any]:
        """Récupère les infos système."""
        memory = psutil.virtual_memory()
        
        return {
            "ram_total_gb": memory.total / (1024**3),
            "ram_available_gb": memory.available / (1024**3),
            "cpu_count": psutil.cpu_count(),
            "platform": psutil.os.name
        }
    
    def _create_performance_profile(self) -> Dict[str, Any]:
        """Crée un profil de performance adaptatif."""
        gpu_score = self.gpu_info["score"]
        vram_gb = self.gpu_info["vram_gb"]
        ram_gb = self.system_info["ram_available_gb"]
        
        # Détecter la plateforme pour ajuster les optimisations
        import platform
        is_windows = platform.system() == "Windows"
        
        # Profils adaptatifs selon performance
        if gpu_score >= 80:  # RTX 4080+, RTX 5070+
            profile = {
                "tier": "ultra_performance",
                "model_size": "32B",
                "quantization": "fp16",
                "max_tokens": 4096,
                "batch_size": 4,
                "use_vllm": not is_windows,  # vLLM désactivé sur Windows
                "use_flash_attn": not is_windows,  # Flash-Attention désactivé sur Windows
                "estimated_time_minutes": 2 if is_windows else 1,
                "max_time_limit_minutes": 7 if is_windows else 5
            }
        elif gpu_score >= 60:  # RTX 4050+, RTX 3070+
            profile = {
                "tier": "high_performance", 
                "model_size": "7B",  # Changé de 32B à 7B pour RTX 4050
                "quantization": "gptq" if is_windows else ("awq" if vram_gb >= 6 else "gptq"),
                "max_tokens": 3072,
                "batch_size": 2,
                "use_vllm": not is_windows,  # vLLM désactivé sur Windows
                "use_flash_attn": not is_windows and vram_gb >= 6,
                "estimated_time_minutes": 4 if is_windows else 2,
                "max_time_limit_minutes": 8 if is_windows else 7
            }
        elif gpu_score >= 40:  # GTX 1080, RTX 2060+
            profile = {
                "tier": "medium_performance",
                "model_size": "7B" if is_windows else ("13B" if vram_gb < 8 else "32B"),
                "quantization": "gptq",
                "max_tokens": 2048,
                "batch_size": 1,
                "use_vllm": not is_windows and vram_gb >= 6,
                "use_flash_attn": False,  # Toujours désactivé pour ce tier
                "estimated_time_minutes": 5 if is_windows else 4,
                "max_time_limit_minutes": 9 if is_windows else 8
            }
        elif gpu_score >= 25:  # GTX 1060, Budget GPUs
            profile = {
                "tier": "basic_performance",
                "model_size": "7B",
                "quantization": "ggml_q4",
                "max_tokens": 1536,
                "batch_size": 1,
                "use_vllm": False,
                "use_flash_attn": False,
                "estimated_time_minutes": 7 if is_windows else 6,
                "max_time_limit_minutes": 10 if is_windows else 9
            }
        else:  # GPU très faibles ou CPU
            profile = {
                "tier": "cpu_fallback",
                "model_size": "3B",
                "quantization": "ggml_q8",
                "max_tokens": 1024,
                "batch_size": 1,
                "use_vllm": False,
                "use_flash_attn": False,
                "estimated_time_minutes": 8,
                "max_time_limit_minutes": 10,
                "use_cpu": True
            }
        
        # Ajustements selon RAM disponible
        if ram_gb < 16 and profile["model_size"] == "32B":
            profile["model_size"] = "13B"
            profile["estimated_time_minutes"] += 1
        
        logger.info(f"📊 Profil adaptatif: {profile['tier']} - Temps estimé: {profile['estimated_time_minutes']}min")
        
        return profile
    
    def get_optimal_model_config(self) -> Dict[str, Any]:
        """Retourne la configuration optimale pour ce système."""
        config = {
            "model_name": self._get_optimal_model_name(),
            "device": "cuda" if self.gpu_info["available"] and not self.performance_profile.get("use_cpu") else "cpu",
            "quantization": self.performance_profile["quantization"],
            "max_new_tokens": self.performance_profile["max_tokens"],
            "batch_size": self.performance_profile["batch_size"],
            "gpu_memory_utilization": self._get_optimal_memory_utilization(),
            "use_vllm": self.performance_profile["use_vllm"],
            "use_flash_attention": self.performance_profile["use_flash_attn"],
            "timeout_minutes": self.performance_profile["max_time_limit_minutes"]
        }
        if self._registry_choice:
            config["registry_key"] = self._registry_choice.key

        return config
    def _get_optimal_model_name(self) -> str:
        """Selectionne le modèle optimal selon les performances et le registre."""
        hardware = {
            "available": self.gpu_info.get("available", False),
            "vram_gb": self.gpu_info.get("vram_gb", 0),
            "ram_gb": self.system_info.get("ram_available_gb") or self.system_info.get("ram_total_gb"),
        }
        profile = model_registry.select_profile(hardware)
        if profile:
            self._registry_choice = profile
            logger.info("Selection registre: %s -> %s", profile.key, profile.model_id)
            return profile.model_id
        # Fallback vers l'ancienne logique si aucun profil n'est disponible.
        model_size = self.performance_profile.get("model_size", "7B")
        model_map = {
            "32B": "Qwen/Qwen2.5-32B-Instruct",
            "13B": "Qwen/Qwen2.5-14B-Instruct",
            "14B": "Qwen/Qwen2.5-14B-Instruct",
            "7B": "Qwen/Qwen2.5-7B-Instruct",
            "3B": "Qwen/Qwen2.5-3B-Instruct",
        }
        fallback = model_map.get(model_size, "Qwen/Qwen2.5-7B-Instruct")
        logger.warning("Registre n'a renvoie aucun profil, fallback vers %s", fallback)
        return fallback

    def _get_optimal_memory_utilization(self) -> float:
        """Calcule l'utilisation mémoire optimale."""
        vram_gb = self.gpu_info["vram_gb"]
        
        if vram_gb >= 20:
            return 0.90  # GPU haut de gamme
        elif vram_gb >= 12:
            return 0.85  # GPU milieu de gamme
        elif vram_gb >= 8:
            return 0.80  # GPU entrée de gamme
        elif vram_gb >= 6:
            return 0.75  # GPU budget
        else:
            return 0.70  # GPU très limités
    
    def get_performance_recommendations(self) -> Dict[str, Any]:
        """Génère des recommandations de performance."""
        recommendations = {
            "current_config": self.performance_profile,
            "estimated_performance": {},
            "upgrade_suggestions": [],
            "optimization_tips": []
        }
        
        # Performance estimée
        recommendations["estimated_performance"] = {
            "generation_time_minutes": self.performance_profile["estimated_time_minutes"],
            "max_timeout_minutes": self.performance_profile["max_time_limit_minutes"],
            "quality_level": self._estimate_quality_level(),
            "memory_usage_percent": int(self._get_optimal_memory_utilization() * 100)
        }
        
        # Suggestions d'upgrade
        gpu_score = self.gpu_info["score"]
        if gpu_score < 40:
            recommendations["upgrade_suggestions"].append("🔄 GPU trop ancien - Considérer RTX 4060+ pour de meilleures performances")
        if self.gpu_info["vram_gb"] < 8:
            recommendations["upgrade_suggestions"].append("💾 VRAM limitée - 8GB+ recommandé pour modèles 32B")
        if self.system_info["ram_available_gb"] < 16:
            recommendations["upgrade_suggestions"].append("🧠 RAM insuffisante - 16GB+ recommandé")
        
        # Tips d'optimisation
        recommendations["optimization_tips"] = [
            f"🎯 Utiliser le modèle {self.performance_profile['model_size']} pour votre configuration",
            f"⚡ Quantification {self.performance_profile['quantization']} optimale",
            f"🕐 Temps de génération attendu: ~{self.performance_profile['estimated_time_minutes']} minutes",
            "🧹 Fermer les autres applications gourmandes",
            "🔥 Surveiller la température GPU durant la génération"
        ]
        
        return recommendations
    
    def get_optimal_model_config(self) -> Dict[str, Any]:
        """Retourne la configuration optimale pour ce système."""
        config = {
            "model_name": self._get_optimal_model_name(),
            "device": "cuda" if self.gpu_info["available"] and not self.performance_profile.get("use_cpu") else "cpu",
            "quantization": self.performance_profile["quantization"],
            "max_new_tokens": self.performance_profile["max_tokens"],
            "batch_size": self.performance_profile["batch_size"],
            "gpu_memory_utilization": self._get_optimal_memory_utilization(),
            "use_vllm": self.performance_profile["use_vllm"],
            "use_flash_attention": self.performance_profile["use_flash_attn"],
            "timeout_minutes": self.performance_profile["max_time_limit_minutes"]
        }
        if self._registry_choice:
            config["registry_key"] = self._registry_choice.key

        return config
    def _estimate_quality_level(self) -> str:
        """Estime le niveau de qualité selon la config."""
        model_size = self.performance_profile["model_size"]
        quantization = self.performance_profile["quantization"]
        
        if model_size == "32B" and quantization in ["fp16", "awq"]:
            return "Excellente"
        elif model_size == "32B" and quantization == "gptq":
            return "Très bonne"
        elif model_size in ["13B", "14B"]:
            return "Bonne"
        elif model_size == "7B":
            return "Correcte"
        else:
            return "Basique"
    
    def check_10_minute_guarantee(self) -> Dict[str, Any]:
        """Vérifie si la garantie 10 minutes peut être respectée."""
        estimated_time = self.performance_profile["estimated_time_minutes"]
        max_time = self.performance_profile["max_time_limit_minutes"]
        
        result = {
            "guarantee_met": max_time <= 10,
            "estimated_time": estimated_time,
            "max_time": max_time,
            "safety_margin": 10 - max_time,
            "recommendations": []
        }
        
        if not result["guarantee_met"]:
            result["recommendations"] = [
                "⚠️ Configuration ne respecte pas la limite 10min",
                f"🔧 Réduire à modèle {self._get_faster_model_size()}",
                "💾 Augmenter la quantification",
                "🚀 Activer vLLM si possible"
            ]
        
        return result
    
    def _get_faster_model_size(self) -> str:
        """Suggère un modèle plus rapide."""
        current_size = self.performance_profile["model_size"]
        
        size_hierarchy = ["32B", "13B", "7B", "3B"]
        current_index = size_hierarchy.index(current_size) if current_size in size_hierarchy else 0
        
        if current_index < len(size_hierarchy) - 1:
            return size_hierarchy[current_index + 1]
        else:
            return "3B"  # Plus petit modèle
    
    def _get_optimal_model_name(self) -> str:
        """Selectionne le modèle optimal selon les performances."""
        model_size = self.performance_profile["model_size"]
        
        model_map = {
            "32B": "Qwen/Qwen2.5-32B-Instruct",
            "13B": "Qwen/Qwen2.5-14B-Instruct", 
            "7B": "Qwen/Qwen2.5-7B-Instruct",
            "3B": "Qwen/Qwen2.5-3B-Instruct"
        }
        
        return model_map.get(model_size, "Qwen/Qwen2.5-7B-Instruct")
    
    def _get_optimal_memory_utilization(self) -> float:
        """Calcule l'utilisation mémoire optimale."""
        vram_gb = self.gpu_info["vram_gb"]
        
        if vram_gb >= 20:
            return 0.90  # GPU haut de gamme
        elif vram_gb >= 12:
            return 0.85  # GPU milieu de gamme
        elif vram_gb >= 8:
            return 0.80  # GPU entrée de gamme
        elif vram_gb >= 6:
            return 0.75  # GPU budget (RTX 4050)
        else:
            return 0.70  # GPU très limités


# Instance globale
universal_gpu_adapter = UniversalGPUAdapter()
