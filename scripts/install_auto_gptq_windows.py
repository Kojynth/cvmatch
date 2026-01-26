#!/usr/bin/env python3
"""
Installation auto-gptq Windows
===============================

Script spécialisé pour installer auto-gptq sur Windows en patchant les problèmes
de variables d'environnement CUDA.
"""

import os
import sys
import tempfile
import subprocess
from pathlib import Path
from loguru import logger

def setup_cuda_environment():
    """Configure l'environnement CUDA pour auto-gptq."""
    
    # Variables CUDA nécessaires pour auto-gptq
    cuda_vars = {
        "CUDA_VERSION": "12.1",  # Version avec point
        "MAX_JOBS": "4",  # Limiter les jobs parallèles sur Windows
        "CUDA_VISIBLE_DEVICES": "0"
    }
    
    logger.info("Configuration de l'environnement CUDA pour auto-gptq...")
    
    for key, value in cuda_vars.items():
        os.environ[key] = value
        logger.info(f"  {key}={value}")
    
    return cuda_vars

def try_precompiled_wheel():
    """Essaie d'installer une roue pré-compilée."""
    logger.info("Tentative d'installation d'une roue pré-compilée...")
    
    # URLs de roues pré-compilées pour Windows
    wheel_urls = [
        # Auto-GPTQ officiel avec support CUDA 12.1
        "https://github.com/PanQiWei/AutoGPTQ/releases/download/v0.7.1/auto_gptq-0.7.1+cu121-cp39-abi3-win_amd64.whl",
        # Fallback version
        "auto-gptq --prefer-binary"
    ]
    
    for wheel_url in wheel_urls:
        try:
            logger.info(f"Essai : {wheel_url}")
            
            if wheel_url.startswith("http"):
                cmd = [sys.executable, "-m", "pip", "install", wheel_url]
            else:
                cmd = [sys.executable, "-m", "pip", "install"] + wheel_url.split()
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode == 0:
                logger.info("✅ Installation réussie avec roue pré-compilée")
                return True
            else:
                logger.warning(f"Échec : {result.stderr}")
                
        except Exception as e:
            logger.warning(f"Erreur avec {wheel_url}: {e}")
    
    return False

def compile_from_source():
    """Compile auto-gptq depuis les sources avec patch."""
    logger.info("Compilation depuis les sources avec patch...")
    
    try:
        # Télécharger les sources
        cmd = [
            sys.executable, "-m", "pip", "download", 
            "--no-deps", "--no-binary=:all:", "auto-gptq==0.7.1"
        ]
        
        with tempfile.TemporaryDirectory() as temp_dir:
            logger.info(f"Téléchargement des sources dans {temp_dir}")
            
            result = subprocess.run(
                cmd,
                cwd=temp_dir,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                logger.error(f"Échec téléchargement : {result.stderr}")
                return False
            
            # Trouver l'archive téléchargée
            archives = list(Path(temp_dir).glob("auto_gptq-*.tar.gz"))
            if not archives:
                logger.error("Archive non trouvée")
                return False
            
            archive_path = archives[0]
            logger.info(f"Archive trouvée : {archive_path}")
            
            # Extraire l'archive
            import tarfile
            with tarfile.open(archive_path, 'r:gz') as tar:
                tar.extractall(temp_dir)
            
            # Trouver le dossier extrait
            extracted_dirs = [d for d in Path(temp_dir).iterdir() 
                            if d.is_dir() and d.name.startswith("auto_gptq-")]
            
            if not extracted_dirs:
                logger.error("Dossier extrait non trouvé")
                return False
            
            source_dir = extracted_dirs[0]
            setup_py_path = source_dir / "setup.py"
            
            if not setup_py_path.exists():
                logger.error("setup.py non trouvé")
                return False
            
            # Patcher setup.py
            logger.info("Application du patch setup.py...")
            
            with open(setup_py_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Remplacer la ligne problématique
            old_line = 'CUDA_VERSION = "".join(os.environ.get("CUDA_VERSION", default_cuda_version).split("."))'
            new_line = '''cuda_version_env = os.environ.get("CUDA_VERSION", default_cuda_version)
if cuda_version_env is None:
    cuda_version_env = default_cuda_version
CUDA_VERSION = "".join(cuda_version_env.split("."))'''
            
            if old_line in content:
                content = content.replace(old_line, new_line)
                logger.info("Patch appliqué avec succès")
                
                with open(setup_py_path, 'w', encoding='utf-8') as f:
                    f.write(content)
            else:
                logger.warning("Ligne à patcher non trouvée, tentative directe")
            
            # Compiler et installer
            logger.info("Compilation et installation...")
            
            cmd = [
                sys.executable, "-m", "pip", "install", 
                str(source_dir), "--no-build-isolation"
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600  # 10 minutes
            )
            
            if result.returncode == 0:
                logger.info("✅ Compilation et installation réussies")
                return True
            else:
                logger.error(f"Échec compilation : {result.stderr}")
                return False
                
    except Exception as e:
        logger.error(f"Erreur lors de la compilation : {e}")
        return False

def test_installation():
    """Teste si auto-gptq est correctement installé."""
    try:
        import auto_gptq
        logger.info(f"✅ auto-gptq {auto_gptq.__version__} installé avec succès")
        return True
    except ImportError:
        logger.error("❌ auto-gptq non installé ou non fonctionnel")
        return False

def main():
    """Fonction principale."""
    logger.info("🚀 Installation spécialisée auto-gptq pour Windows")
    
    # Configurer l'environnement CUDA
    setup_cuda_environment()
    
    # Stratégie 1: Roue pré-compilée
    if try_precompiled_wheel():
        if test_installation():
            logger.info("🎉 Installation réussie avec roue pré-compilée")
            return 0
    
    # Stratégie 2: Compilation depuis sources avec patch
    logger.info("Tentative de compilation depuis les sources...")
    if compile_from_source():
        if test_installation():
            logger.info("🎉 Installation réussie par compilation")
            return 0
    
    # Échec
    logger.error("💥 Toutes les méthodes d'installation ont échoué")
    logger.error("auto-gptq ne sera pas disponible")
    logger.info("L'application fonctionnera sans quantification GPTQ")
    
    return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
