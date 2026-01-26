"""
WeasyPrint Bootstrap - Configuration DLL pour Windows
=====================================================

Ce module configure automatiquement les chemins DLL pour WeasyPrint sur Windows.
Il doit être importé AVANT tout import de WeasyPrint pour garantir le bon fonctionnement.

Utilisation:
    import scripts.weasyprint_bootstrap  # Avant tout import weasyprint
    import weasyprint  # Maintenant ça marche
"""

import os
import sys
import platform

def configure_weasyprint_dll_paths():
    """
    Configure les chemins DLL pour WeasyPrint sur Windows uniquement.
    
    Cette fonction :
    1. Vérifie si nous sommes sur Windows
    2. Ajoute les répertoires DLL MSYS2 si disponibles
    3. Configure la variable d'environnement WEASYPRINT_DLL_DIRECTORIES
    4. Utilise os.add_dll_directory() pour Python 3.8+
    """
    # Seulement sur Windows
    if platform.system() != "Windows":
        return
    
    # Chemins DLL potentiels pour WeasyPrint
    potential_dll_paths = [
        r"C:\msys64\mingw64\bin",           # MSYS2 MinGW64 (recommandé)
        r"C:\msys64\usr\bin",               # MSYS2 usr/bin (fallback)
        os.environ.get("WEASYPRINT_DLL_DIRECTORIES"),  # Variable d'environnement
    ]
    
    # Filtrer les chemins existants
    valid_dll_paths = []
    for path in potential_dll_paths:
        if path and os.path.isdir(path):
            valid_dll_paths.append(path)
    
    if not valid_dll_paths:
        # Pas de chemins DLL trouvés, WeasyPrint pourrait ne pas fonctionner
        # Mode silencieux pour éviter le spam dans CVMatch.bat
        import sys
        if "--verbose" in sys.argv or os.environ.get("WEASYPRINT_DEBUG"):
            print("[WEASYPRINT_BOOTSTRAP] Aucun chemin DLL trouvé - WeasyPrint pourrait échouer")
            print("[WEASYPRINT_BOOTSTRAP] Installez MSYS2 ou configurez WEASYPRINT_DLL_DIRECTORIES")
        return
    
    # Configurer la variable d'environnement
    dll_paths_str = os.pathsep.join(valid_dll_paths)
    os.environ["WEASYPRINT_DLL_DIRECTORIES"] = dll_paths_str
    
    # Pour Python 3.8+, utiliser os.add_dll_directory()
    import sys
    verbose_mode = "--verbose" in sys.argv or os.environ.get("WEASYPRINT_DEBUG")
    
    if hasattr(os, 'add_dll_directory'):
        for dll_path in valid_dll_paths:
            try:
                os.add_dll_directory(dll_path)
                if verbose_mode:
                    print(f"[WEASYPRINT_BOOTSTRAP] Chemin DLL ajouté: {dll_path}")
            except (OSError, FileNotFoundError) as e:
                if verbose_mode:
                    print(f"[WEASYPRINT_BOOTSTRAP] Échec ajout DLL {dll_path}: {e}")
    else:
        # Python < 3.8, utiliser seulement la variable d'environnement
        if verbose_mode:
            print(f"[WEASYPRINT_BOOTSTRAP] Variable d'environnement configurée: {dll_paths_str}")
            print("[WEASYPRINT_BOOTSTRAP] Python < 3.8 détecté - utilisation variable d'environnement seulement")

def test_weasyprint_import():
    """
    Test l'import de WeasyPrint après configuration.
    
    Returns:
        bool: True si WeasyPrint peut être importé, False sinon
    """
    try:
        import weasyprint
        print(f"[WEASYPRINT_BOOTSTRAP] ✅ WeasyPrint importé avec succès - Version: {weasyprint.__version__}")
        return True
    except ImportError as e:
        print(f"[WEASYPRINT_BOOTSTRAP] ❌ Échec import WeasyPrint: {e}")
        return False
    except Exception as e:
        print(f"[WEASYPRINT_BOOTSTRAP] ❌ Erreur WeasyPrint: {e}")
        return False

# Configuration automatique à l'import du module
if __name__ == "__main__":
    # Mode test direct
    print("[WEASYPRINT_BOOTSTRAP] Test direct du bootstrap WeasyPrint...")
    configure_weasyprint_dll_paths()
    success = test_weasyprint_import()
    sys.exit(0 if success else 1)
else:
    # Import normal - configuration silencieuse
    configure_weasyprint_dll_paths()
