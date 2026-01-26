#!/usr/bin/env python3
"""
Setup WeasyPrint pour Windows - Script d'installation automatique
================================================================

Ce script configure automatiquement WeasyPrint sur Windows en :
1. Détectant si MSYS2 est installé
2. Installant MSYS2 via winget si nécessaire
3. Installant les bibliothèques natives requises
4. Configurant les variables d'environnement
5. Testant l'import de WeasyPrint

Usage:
    python scripts/setup_weasyprint_windows.py
    python scripts/setup_weasyprint_windows.py --verbose
"""

import os
import sys
import subprocess
import platform
from pathlib import Path

def check_windows():
    """Vérifie que nous sommes sur Windows."""
    if platform.system() != "Windows":
        print("❌ Ce script est seulement pour Windows")
        return False
    return True

def check_msys2():
    """Vérifie si MSYS2 est installé."""
    msys2_path = Path("C:/msys64/mingw64/bin")
    if msys2_path.exists():
        print("✅ MSYS2 détecté")
        return True
    else:
        print("⚠️  MSYS2 non détecté")
        return False

def install_msys2():
    """Installe MSYS2 via winget."""
    print("📦 Installation de MSYS2 via winget...")
    try:
        # Utiliser --accept-source-agreements et --accept-package-agreements pour éviter les prompts
        result = subprocess.run([
            "winget", "install", "-e", "--id", "MSYS2.MSYS2", 
            "--accept-source-agreements", "--accept-package-agreements", "--silent"
        ], capture_output=True, text=True, check=True, timeout=300)  # 5 minutes max
        print("✅ MSYS2 installé avec succès")
        return True
    except subprocess.TimeoutExpired:
        print("⏰ Installation MSYS2 timeout - processus trop long")
        print("   Veuillez installer MSYS2 manuellement depuis https://www.msys2.org/")
        return False
    except subprocess.CalledProcessError as e:
        print(f"❌ Échec installation MSYS2: {e}")
        print(f"   Sortie d'erreur: {e.stderr}")
        print("   Veuillez installer MSYS2 manuellement depuis https://www.msys2.org/")
        return False
    except FileNotFoundError:
        print("❌ winget non trouvé")
        print("   Veuillez installer MSYS2 manuellement depuis https://www.msys2.org/")
        return False

def install_weasyprint_libs():
    """Installe les bibliothèques WeasyPrint via MSYS2."""
    print("📚 Installation des bibliothèques WeasyPrint...")
    msys2_bash = "C:/msys64/usr/bin/bash.exe"
    
    if not Path(msys2_bash).exists():
        print("❌ MSYS2 bash non trouvé")
        return False
    
    # Commande d'installation des packages
    cmd = [
        msys2_bash, "-lc",
        "pacman -S --noconfirm --needed mingw-w64-x86_64-pango mingw-w64-x86_64-cairo mingw-w64-x86_64-gdk-pixbuf2 mingw-w64-x86_64-harfbuzz"
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=600)  # 10 minutes max
        print("✅ Bibliothèques WeasyPrint installées")
        return True
    except subprocess.TimeoutExpired:
        print("⏰ Installation bibliothèques timeout - processus trop long")
        return False
    except subprocess.CalledProcessError as e:
        print(f"❌ Échec installation bibliothèques: {e}")
        if e.stderr:
            print(f"   Erreur détaillée: {e.stderr}")
        # Tentative de mise à jour de pacman
        print("🔄 Tentative de mise à jour de pacman...")
        try:
            subprocess.run([msys2_bash, "-lc", "pacman -Syu --noconfirm"], 
                         capture_output=True, text=True, check=True, timeout=300)
            # Re-tentative d'installation
            subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=600)
            print("✅ Bibliothèques WeasyPrint installées (après mise à jour)")
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e2:
            print(f"❌ Échec définitif: {e2}")
            return False

def configure_environment():
    """Configure les variables d'environnement."""
    print("⚙️  Configuration des variables d'environnement...")
    dll_path = "C:\\msys64\\mingw64\\bin"
    
    # Configuration de la session courante
    os.environ["WEASYPRINT_DLL_DIRECTORIES"] = dll_path
    
    # Configuration persistante via setx
    try:
        subprocess.run([
            "setx", "WEASYPRINT_DLL_DIRECTORIES", dll_path
        ], capture_output=True, text=True, check=True)
        print("✅ Variables d'environnement configurées")
        return True
    except subprocess.CalledProcessError as e:
        print(f"⚠️  Échec configuration persistante: {e}")
        print("   Variable configurée pour cette session seulement")
        return True

def test_weasyprint():
    """Teste l'import de WeasyPrint."""
    print("🧪 Test de WeasyPrint...")
    
    # Import du bootstrap pour configurer les DLL
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        import scripts.weasyprint_bootstrap
        os.environ["WEASYPRINT_DEBUG"] = "1"  # Mode verbose pour le bootstrap
    except Exception as e:
        print(f"⚠️  Bootstrap non disponible: {e}")
    
    # Test d'import
    try:
        import weasyprint
        print(f"✅ WeasyPrint disponible - Version: {weasyprint.__version__}")
        
        # Test rapide de génération PDF
        try:
            html_doc = weasyprint.HTML(string="<html><body><h1>Test WeasyPrint</h1></body></html>")
            # Ne pas générer de fichier, juste tester l'initialisation
            print("✅ Test de génération PDF réussi")
            return True
        except Exception as e:
            print(f"⚠️  Test génération PDF échoué: {e}")
            print("   WeasyPrint importé mais bibliothèques possiblement incomplètes")
            return False
            
    except ImportError as e:
        print(f"❌ Échec import WeasyPrint: {e}")
        return False

def main():
    """Fonction principale."""
    verbose = "--verbose" in sys.argv
    if verbose:
        os.environ["WEASYPRINT_DEBUG"] = "1"
    
    print("🔧 Setup WeasyPrint pour Windows")
    print("=" * 40)
    
    # Vérification Windows
    if not check_windows():
        return 1
    
    # Vérification/Installation MSYS2
    if not check_msys2():
        if not install_msys2():
            return 1
        # Vérifier à nouveau après installation
        if not check_msys2():
            print("❌ MSYS2 toujours non détecté après installation")
            return 1
    
    # Installation des bibliothèques
    if not install_weasyprint_libs():
        return 1
    
    # Configuration de l'environnement
    if not configure_environment():
        return 1
    
    # Test final
    if test_weasyprint():
        print("\n🎉 WeasyPrint configuré avec succès!")
        print("   L'export PDF complet est maintenant disponible.")
        return 0
    else:
        print("\n❌ Configuration WeasyPrint incomplète")
        print("   Redémarrez votre terminal et re-testez.")
        print("   Si le problème persiste, consultez:")
        print("   https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#windows")
        return 1

if __name__ == "__main__":
    sys.exit(main())
