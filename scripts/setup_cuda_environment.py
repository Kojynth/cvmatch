#!/usr/bin/env python3
"""
Setup CUDA Environment
=======================

Script pour configurer automatiquement les variables d'environnement CUDA
nécessaires pour la compilation de Flash-Attention et auto-gptq.
"""

import os
import sys
import platform
import subprocess
from pathlib import Path
from loguru import logger

def detect_cuda_installation():
    """Détecte l'installation CUDA sur le système."""
    cuda_info = {
        "available": False,
        "version": None,
        "path": None,
        "compute_capabilities": []
    }
    
    # Vérifier nvidia-smi
    try:
        result = subprocess.run(["nvidia-smi"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            cuda_info["available"] = True
            logger.info("GPU NVIDIA détecté via nvidia-smi")
        else:
            logger.warning("nvidia-smi non fonctionnel")
            return cuda_info
    except (subprocess.SubprocessError, FileNotFoundError):
        logger.warning("nvidia-smi non trouvé")
        return cuda_info
    
    # Détecter version CUDA
    try:
        result = subprocess.run(["nvcc", "--version"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            # Parser la version depuis la sortie nvcc
            lines = result.stdout.split('\n')
            for line in lines:
                if "release" in line:
                    # Format: "Cuda compilation tools, release 12.1, V12.1.105"
                    parts = line.split("release ")
                    if len(parts) > 1:
                        version_part = parts[1].split(",")[0].strip()
                        cuda_info["version"] = version_part
                        logger.info(f"Version CUDA détectée : {version_part}")
                        break
        else:
            logger.warning("nvcc non fonctionnel, utilisation version par défaut")
            cuda_info["version"] = "12.1"  # Version par défaut
    except (subprocess.SubprocessError, FileNotFoundError):
        logger.warning("nvcc non trouvé, utilisation version par défaut")
        cuda_info["version"] = "12.1"  # Version par défaut
    
    # Détecter chemin CUDA
    system = platform.system()
    
    if system == "Windows":
        # Chercher dans Program Files
        possible_paths = [
            Path("C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA"),
            Path("C:/Program Files (x86)/NVIDIA GPU Computing Toolkit/CUDA"),
        ]
        
        # Vérifier variable d'environnement
        if "CUDA_PATH" in os.environ:
            cuda_info["path"] = os.environ["CUDA_PATH"]
            logger.info(f"CUDA_PATH trouvé : {cuda_info['path']}")
        else:
            # Chercher dans les dossiers standards
            for base_path in possible_paths:
                if base_path.exists():
                    # Chercher la version spécifique
                    version_path = base_path / f"v{cuda_info['version']}"
                    if version_path.exists():
                        cuda_info["path"] = str(version_path)
                        logger.info(f"Installation CUDA trouvée : {version_path}")
                        break
                    else:
                        # Prendre la première version trouvée
                        version_dirs = [d for d in base_path.iterdir() if d.is_dir() and d.name.startswith("v")]
                        if version_dirs:
                            cuda_info["path"] = str(version_dirs[0])
                            logger.info(f"Installation CUDA trouvée : {version_dirs[0]}")
                            break
    
    elif system == "Linux":
        # Chemins standards Linux
        possible_paths = [
            Path("/usr/local/cuda"),
            Path(f"/usr/local/cuda-{cuda_info['version']}"),
            Path("/opt/cuda"),
        ]
        
        # Vérifier variable d'environnement
        if "CUDA_HOME" in os.environ:
            cuda_info["path"] = os.environ["CUDA_HOME"]
            logger.info(f"CUDA_HOME trouvé : {cuda_info['path']}")
        else:
            # Chercher dans les dossiers standards
            for path in possible_paths:
                if path.exists():
                    cuda_info["path"] = str(path)
                    logger.info(f"Installation CUDA trouvée : {path}")
                    break
    
    # Détecter compute capabilities
    try:
        # Utiliser nvidia-ml-py pour obtenir les infos GPU
        result = subprocess.run([
            "nvidia-smi", 
            "--query-gpu=compute_cap", 
            "--format=csv,noheader,nounits"
        ], capture_output=True, text=True, timeout=5)
        
        if result.returncode == 0:
            capabilities = [cap.strip() for cap in result.stdout.strip().split('\n') if cap.strip()]
            cuda_info["compute_capabilities"] = capabilities
            logger.info(f"Compute capabilities détectées : {capabilities}")
        
    except Exception as e:
        # Fallback avec des capabilities communes
        cuda_info["compute_capabilities"] = ["6.0", "6.1", "7.0", "7.5", "8.0", "8.6", "8.9", "9.0"]
        logger.warning(f"Impossible de détecter compute capabilities, utilisation par défaut : {e}")
    
    return cuda_info

def setup_environment_variables(cuda_info):
    """Configure les variables d'environnement pour la compilation."""
    if not cuda_info["available"]:
        logger.warning("CUDA non disponible, skip configuration")
        return {}
    
    env_vars = {}
    system = platform.system()
    
    # Variables communes
    if cuda_info["version"]:
        # Version nettoyée pour auto-gptq (ex: "12.1" -> "121")
        clean_version = cuda_info["version"].replace(".", "")
        env_vars["CUDA_VERSION"] = clean_version
        
        logger.info(f"CUDA_VERSION configuré : {clean_version}")
    
    if cuda_info["path"]:
        if system == "Windows":
            env_vars["CUDA_HOME"] = cuda_info["path"]
            env_vars["CUDA_PATH"] = cuda_info["path"]
        else:
            env_vars["CUDA_HOME"] = cuda_info["path"]
        
        logger.info(f"Chemin CUDA configuré : {cuda_info['path']}")
    
    # Compute capabilities pour compilation optimisée
    if cuda_info["compute_capabilities"]:
        # Format pour PyTorch/CUDA: "6.0;6.1;7.0;7.5;8.0;8.6;8.9;9.0"
        arch_list = ";".join(cuda_info["compute_capabilities"])
        env_vars["TORCH_CUDA_ARCH_LIST"] = arch_list
        
        logger.info(f"TORCH_CUDA_ARCH_LIST configuré : {arch_list}")
    
    # Variables spécifiques pour auto-gptq
    env_vars["CUDA_VISIBLE_DEVICES"] = "0"  # Utiliser le premier GPU par défaut
    
    # Variables pour Flash-Attention
    env_vars["FLASH_ATTENTION_FORCE_BUILD"] = "TRUE"
    env_vars["MAX_JOBS"] = str(min(8, os.cpu_count() or 4))  # Limiter les jobs parallèles
    
    return env_vars

def apply_environment_variables(env_vars):
    """Applique les variables d'environnement."""
    logger.info("Application des variables d'environnement...")
    
    for key, value in env_vars.items():
        os.environ[key] = value
        logger.info(f"  {key}={value}")
    
    # Créer un script pour les sessions futures
    system = platform.system()
    
    if system == "Windows":
        # Créer un fichier batch
        script_path = Path("setup_cuda_vars.bat")
        with open(script_path, 'w') as f:
            f.write("@echo off\n")
            f.write(":: Variables d'environnement CUDA pour CVMatch\n")
            f.write(":: Généré automatiquement\n\n")
            
            for key, value in env_vars.items():
                f.write(f"set {key}={value}\n")
            
            f.write("\necho Variables CUDA configurées pour CVMatch\n")
        
        logger.info(f"Script Windows créé : {script_path}")
        logger.info("Lancez 'setup_cuda_vars.bat' avant l'installation si nécessaire")
    
    else:
        # Créer un script shell
        script_path = Path("setup_cuda_vars.sh")
        with open(script_path, 'w') as f:
            f.write("#!/bin/bash\n")
            f.write("# Variables d'environnement CUDA pour CVMatch\n")
            f.write("# Généré automatiquement\n\n")
            
            for key, value in env_vars.items():
                f.write(f'export {key}="{value}"\n')
            
            f.write('\necho "Variables CUDA configurées pour CVMatch"\n')
        
        # Rendre exécutable
        script_path.chmod(0o755)
        
        logger.info(f"Script Linux créé : {script_path}")
        logger.info("Lancez 'source setup_cuda_vars.sh' avant l'installation si nécessaire")

def main():
    """Fonction principale."""
    logger.info("🔧 Configuration automatique de l'environnement CUDA")
    
    # Détecter CUDA
    cuda_info = detect_cuda_installation()
    
    if not cuda_info["available"]:
        logger.warning("⚠️ CUDA non détecté - L'application fonctionnera en mode CPU")
        return 0
    
    logger.info("✅ CUDA détecté, configuration de l'environnement...")
    
    # Configurer les variables
    env_vars = setup_environment_variables(cuda_info)
    
    # Appliquer les variables
    apply_environment_variables(env_vars)
    
    logger.info("🎉 Configuration CUDA terminée avec succès !")
    logger.info("L'environnement est prêt pour l'installation des optimisations CUDA")
    
    return 0

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
