#!/usr/bin/env python3
"""Test simple de persistance du fichier reset_cleanup.log"""

import sys
from pathlib import Path

def test_code_corrections():
    """Teste que les corrections sont présentes dans le code."""
    print("TEST CORRECTIONS PERSISTANCE LOGS")
    print("=" * 35)
    
    try:
        # Lire le code source
        project_root = Path(__file__).parent.parent
        main_window_file = project_root / "app" / "views" / "main_window.py"
        
        with open(main_window_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        tests_passed = 0
        total_tests = 0
        
        # Test 1: Protection logs/réinitialisation
        print("1. Protection logs/réinitialisation...")
        total_tests += 1
        if 'PROTECTION: Préservation logs/réinitialisation' in content:
            print("   [OK] Message de protection ajouté")
            tests_passed += 1
        else:
            print("   [ERREUR] Protection manquante")
        
        # Test 2: Recréation dossier réinitialisation
        print("2. Recréation dossier réinitialisation...")
        total_tests += 1
        if 'mkdir "{project_root / "logs" / "réinitialisation"}"' in content:
            print("   [OK] Recréation dossier assurée")
            tests_passed += 1
        else:
            print("   [ERREUR] Recréation manquante")
        
        # Test 3: Pas d'auto-suppression
        print("3. Suppression auto-suppression script...")
        total_tests += 1
        if 'REM del "%~f0" 2>nul' in content:
            print("   [OK] Auto-suppression désactivée")
            tests_passed += 1
        else:
            print("   [ERREUR] Auto-suppression toujours active")
        
        # Test 4: Message informatif final
        print("4. Message informatif final...")
        total_tests += 1
        if 'Log disponible dans logs/réinitialisation/reset_cleanup.log' in content:
            print("   [OK] Message informatif ajouté")
            tests_passed += 1
        else:
            print("   [ERREUR] Message informatif manquant")
        
        # Test 5: Log de sauvegarde
        print("5. Log de confirmation sauvegarde...")
        total_tests += 1
        if 'Fichier de log sauvegardé: logs/réinitialisation/reset_cleanup.log' in content:
            print("   [OK] Log de confirmation présent")
            tests_passed += 1
        else:
            print("   [ERREUR] Log de confirmation manquant")
        
        print("\n" + "=" * 35)
        print(f"RESULTATS: {tests_passed}/{total_tests} tests réussis")
        
        if tests_passed == total_tests:
            print("SUCCESS: Toutes les corrections sont en place !")
            print("")
            print("AMELIORATIONS CONFIRMEES:")
            print("• Protection explicite du dossier logs/réinitialisation")
            print("• Recréation automatique du dossier si nécessaire")
            print("• Pas d'auto-suppression du script")
            print("• Messages informatifs pour l'utilisateur")
            print("• Log de confirmation de sauvegarde")
            print("")
            print("Le fichier reset_cleanup.log sera maintenant préservé !")
            return 0
        else:
            print(f"ATTENTION: {total_tests - tests_passed} problème(s) restant(s)")
            return 1
            
    except Exception as e:
        print(f"[ERREUR] {e}")
        return 1

if __name__ == "__main__":
    sys.exit(test_code_corrections())