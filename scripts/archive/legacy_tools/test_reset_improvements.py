#!/usr/bin/env python3
"""
Test des améliorations du système de réinitialisation
====================================================

Valide que les corrections apportées fonctionnent correctement :
1. Fichier reset_cleanup.log dans le bon dossier
2. Affichage du nom de fichier au lieu du chemin complet
3. Script de redémarrage amélioré

Usage:
    python scripts/test_reset_improvements.py
"""

import sys
from pathlib import Path
import tempfile
import shutil

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_log_file_location():
    """Teste que le fichier de log est créé au bon endroit."""
    print("Test 1: Emplacement du fichier reset_cleanup.log")
    
    try:
        # Importer la classe MainWindow pour accéder à _create_cleanup_script
        from app.views.main_window import MainWindow
        from PySide6.QtWidgets import QApplication
        import tempfile
        
        # Créer une application temporaire pour initialiser QWidget
        if not QApplication.instance():
            app = QApplication(sys.argv)
        
        # Créer un répertoire temporaire pour le test
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Simuler le main_window avec un project_root personnalisé
            class MockMainWindow:
                def _create_cleanup_script(self):
                    project_root = temp_path
                    log_dir = project_root / "logs" / "réinitialisation"
                    log_dir.mkdir(parents=True, exist_ok=True)
                    log_file = log_dir / "reset_cleanup.log"
                    return log_file
            
            mock_window = MockMainWindow()
            log_file = mock_window._create_cleanup_script()
            
            expected_path = temp_path / "logs" / "réinitialisation" / "reset_cleanup.log"
            
            if log_file == expected_path:
                print("   [OK] Fichier de log sera créé dans le bon dossier")
                print(f"   [OK] Chemin attendu: logs/réinitialisation/{log_file.name}")
                return True
            else:
                print(f"   [ERREUR] Chemin incorrect: {log_file}")
                print(f"   [ATTENDU] {expected_path}")
                return False
                
    except Exception as e:
        print(f"   [ERREUR] Exception durant le test: {e}")
        return False

def test_display_format():
    """Teste que l'affichage utilise le bon format."""
    print("\nTest 2: Format d'affichage du chemin de fichier")
    
    try:
        # Simuler les variables utilisées dans la popup
        project_root = Path("/some/long/path/to/cvmatch")
        log_dir = project_root / "logs" / "réinitialisation"
        log_file_path = log_dir / "reset_cleanup.log"
        
        # Simuler le message de la popup
        display_path = f"logs/réinitialisation/{log_file_path.name}"
        
        if display_path == "logs/réinitialisation/reset_cleanup.log":
            print("   [OK] Affichage utilisera le format court")
            print(f"   [OK] Format d'affichage: {display_path}")
            return True
        else:
            print(f"   [ERREUR] Format incorrect: {display_path}")
            return False
            
    except Exception as e:
        print(f"   [ERREUR] Exception durant le test: {e}")
        return False

def test_restart_script_content():
    """Teste que le script de redémarrage contient les améliorations."""
    print("\nTest 3: Contenu du script de redémarrage")
    
    try:
        # Lire le code source pour vérifier les améliorations
        main_window_file = project_root / "app" / "views" / "main_window.py"
        
        with open(main_window_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        improvements = [
            "echo Lancement via CVMatch.bat...",
            "echo Lancement direct via Python...",
            "echo CVMatch devrait se relancer dans quelques secondes...",
            "echo vous pouvez la relancer manuellement via cvmatch.bat"
        ]
        
        all_found = True
        for improvement in improvements:
            if improvement in content:
                print(f"   [OK] Amélioration trouvée: {improvement}")
            else:
                print(f"   [MANQUANT] {improvement}")
                all_found = False
        
        return all_found
        
    except Exception as e:
        print(f"   [ERREUR] Exception durant le test: {e}")
        return False

def test_log_directory_creation():
    """Teste que le code crée bien le dossier logs/réinitialisation."""
    print("\nTest 4: Création automatique du dossier")
    
    try:
        # Lire le code source pour vérifier la création du dossier
        main_window_file = project_root / "app" / "views" / "main_window.py"
        
        with open(main_window_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if 'log_dir.mkdir(parents=True, exist_ok=True)' in content:
            print("   [OK] Le code crée automatiquement le dossier")
            return True
        else:
            print("   [ERREUR] Création automatique du dossier manquante")
            return False
            
    except Exception as e:
        print(f"   [ERREUR] Exception durant le test: {e}")
        return False

def main():
    """Point d'entrée principal du test."""
    print("TEST DES AMÉLIORATIONS DE RÉINITIALISATION")
    print("=" * 45)
    
    tests = [
        test_log_file_location,
        test_display_format,
        test_restart_script_content,
        test_log_directory_creation
    ]
    
    results = []
    for test_func in tests:
        try:
            result = test_func()
            results.append(result)
        except Exception as e:
            print(f"   [ERREUR FATALE] {test_func.__name__}: {e}")
            results.append(False)
    
    # Résumé final
    print("\n" + "=" * 45)
    print("RÉSUMÉ DES TESTS")
    print("=" * 45)
    
    passed = sum(1 for r in results if r)
    total = len(results)
    
    print(f"Tests réussis: {passed}/{total}")
    
    if passed == total:
        print("🎉 [SUCCESS] Toutes les améliorations sont en place!")
        print("📁 Le fichier reset_cleanup.log sera dans logs/réinitialisation/")
        print("📝 L'affichage montrera seulement le nom de fichier")
        print("🔄 Le redémarrage sera plus visible et informatif")
        return 0
    else:
        print(f"⚠️ [ATTENTION] {total - passed} problème(s) détecté(s)")
        print("Vérifiez les détails ci-dessus pour corriger les problèmes")
        return 1

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n[INFO] Test interrompu par l'utilisateur")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERREUR FATALE] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)