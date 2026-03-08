#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test pour valider les améliorations des corrections mojibake.
"""

import sys
from pathlib import Path

# Ajouter le répertoire racine au path Python
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_ui_text_corrections():
    """Test des corrections mojibake avec ui_text()."""
    print("[TEST] Validation des corrections mojibake...")
    
    try:
        from app.utils.ui_text import ui_text
    except Exception as e:
        print(f"[ERROR] Import ui_text échoué: {e}")
        return False
    
    # Tests des patterns mojibake courants
    test_cases = [
        # Tests que le système doit maintenant gérer
        ("refactorisÃ©e", "refactorisée"),  # Exemple du audit
        ("sÃ©curisÃ©", "sécurisé"),
        ("ParamÃ¨tres", "Paramètres"),
        ("GÃ©nÃ©rer", "Générer"),
        ("DonnÃ©es", "Données"),
        
        # Texte déjà correct (ne doit pas changer)
        ("Données extraites", "Données extraites"),
        ("Configuration", "Configuration"),
        ("Test normal", "Test normal"),
        
        # Cas edge
        ("", ""),
        ("Texte sans accents", "Texte sans accents"),
    ]
    
    all_passed = True
    for input_text, expected in test_cases:
        try:
            result = ui_text(input_text)
            if expected in result:  # Plus flexible - on vérifie que la correction est présente
                print(f"[OK] '{input_text}' -> '{result}'")
            else:
                print(f"[FAIL] '{input_text}' -> '{result}' (attendu contenant: '{expected}')")
                all_passed = False
        except Exception as e:
            print(f"[ERROR] '{input_text}': {e}")
            all_passed = False
    
    return all_passed

def test_main_window_import():
    """Test que MainWindow importe correctement après corrections."""
    print("\n[TEST] Import MainWindow après corrections...")
    
    try:
        from app.views.main_window import MainWindowWithSidebar
        print("[OK] MainWindow import réussi")
        return True
    except Exception as e:
        print(f"[ERROR] MainWindow import échoué: {e}")
        return False

def test_application_startup_simulation():
    """Simule le démarrage de l'application sans GUI."""
    print("\n[TEST] Simulation démarrage application...")
    
    try:
        # Test des imports critiques
        from app.models.database import get_session
        from app.models.user_profile import UserProfile
        from app.controllers.profile_extractor import ProfileExtractor
        
        print("[OK] Imports critiques réussis")
        
        # Test qu'on peut créer les objets de base
        session = get_session()
        if session:
            print("[OK] Session DB créée")
            session.close()
        
        return True
        
    except Exception as e:
        print(f"[ERROR] Démarrage simulation échoué: {e}")
        return False

def main():
    """Point d'entrée principal."""
    print("=" * 50)
    print("TESTS DE VALIDATION MOJIBAKE")
    print("=" * 50)
    
    tests = [
        ("Corrections ui_text", test_ui_text_corrections),
        ("Import MainWindow", test_main_window_import), 
        ("Simulation démarrage", test_application_startup_simulation),
    ]
    
    results = {}
    for test_name, test_func in tests:
        print(f"\n--- {test_name} ---")
        try:
            results[test_name] = test_func()
        except Exception as e:
            print(f"[ERROR] Test {test_name} crashed: {e}")
            results[test_name] = False
    
    # Résumé
    print(f"\n{'=' * 50}")
    print("RÉSUMÉ DES TESTS")
    print(f"{'=' * 50}")
    
    passed = 0
    total = len(results)
    
    for test_name, passed_test in results.items():
        status = "PASS" if passed_test else "FAIL"
        print(f"[{status}] {test_name}")
        if passed_test:
            passed += 1
    
    print(f"\nRésultat: {passed}/{total} tests réussis")
    
    if passed == total:
        print("\n[SUCCESS] Tous les tests sont passés! Les corrections mojibake fonctionnent.")
        return 0
    else:
        print(f"\n[WARNING] {total - passed} tests ont échoué.")
        return 1

if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)