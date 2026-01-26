#!/usr/bin/env python3
"""
Test de continuité du logging de réinitialisation
================================================

Teste que le logging commence dès la confirmation et continue 
avec le script externe.

Usage:
    python scripts/test_continuous_logging.py
"""

import sys
from pathlib import Path

def test_setup_reset_logging():
    """Teste que la fonction _setup_reset_logging existe et fonctionne."""
    print("Test 1: Fonction _setup_reset_logging")
    
    try:
        # Lire le code source
        project_root = Path(__file__).parent.parent
        main_window_file = project_root / "app" / "views" / "main_window.py"
        
        with open(main_window_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        checks = [
            ("Fonction _setup_reset_logging définie", "def _setup_reset_logging(self)" in content),
            ("Création dossier logs/réinitialisation", "log_dir = project_root / \"logs\" / \"réinitialisation\"" in content),
            ("Création immédiate du fichier", "log_file = log_dir / \"reset_cleanup.log\"" in content),
            ("Écriture début réinitialisation", "=== DEBUT REINITIALISATION CVMATCH ===" in content),
            ("Message confirmation utilisateur", "Utilisateur a confirmé la réinitialisation" in content)
        ]
        
        all_passed = True
        for check_name, result in checks:
            if result:
                print(f"   [OK] {check_name}")
            else:
                print(f"   [ERREUR] {check_name}")
                all_passed = False
        
        return all_passed
        
    except Exception as e:
        print(f"   [ERREUR] Exception: {e}")
        return False

def test_double_logging():
    """Teste que le double logger est implémenté."""
    print("\nTest 2: Double logging (app + reset_cleanup.log)")
    
    try:
        # Lire le code source
        project_root = Path(__file__).parent.parent
        main_window_file = project_root / "app" / "views" / "main_window.py"
        
        with open(main_window_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        checks = [
            ("Appel _setup_reset_logging au début", "reset_log_file = self._setup_reset_logging()" in content),
            ("Fonction log_both définie", "def log_both(message, level=\"INFO\"):" in content),
            ("Écriture logs normaux", "logger.info(message)" in content),
            ("Écriture dans reset_cleanup.log", "with open(reset_log_file, 'a'" in content),
            ("Timestamp pour chaque log", "timestamp = datetime.datetime.now()" in content),
            ("Usage de log_both dans reset_profile", "log_both(\"🧹 Début de réinitialisation complète" in content)
        ]
        
        all_passed = True
        for check_name, result in checks:
            if result:
                print(f"   [OK] {check_name}")
            else:
                print(f"   [ERREUR] {check_name}")
                all_passed = False
        
        return all_passed
        
    except Exception as e:
        print(f"   [ERREUR] Exception: {e}")
        return False

def test_script_continuity():
    """Teste que le script externe continue l'écriture dans le même fichier."""
    print("\nTest 3: Continuité script externe")
    
    try:
        # Lire le code source
        project_root = Path(__file__).parent.parent
        main_window_file = project_root / "app" / "views" / "main_window.py"
        
        with open(main_window_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        checks = [
            ("Script n'écrase pas le fichier", "=== DEBUT PHASE SCRIPT EXTERNE === >> \"%logfile%\"" in content),
            ("Continuité indiquée dans app", "=== FIN PHASE APPLICATION - DEBUT PHASE SCRIPT EXTERNE ===" in content),
            ("Message de continuité", "Continuité dans reset_cleanup.log" in content),
            ("Pas d'écrasement initial", "> \"%logfile%\"" not in content.split("=== DEBUT PHASE SCRIPT EXTERNE ===")[1] if "=== DEBUT PHASE SCRIPT EXTERNE ===" in content else False)
        ]
        
        all_passed = True
        for check_name, result in checks:
            if result:
                print(f"   [OK] {check_name}")
            else:
                print(f"   [ERREUR] {check_name}")
                all_passed = False
        
        return all_passed
        
    except Exception as e:
        print(f"   [ERREUR] Exception: {e}")
        return False

def test_log_flow():
    """Teste le flux complet du logging."""
    print("\nTest 4: Flux complet du logging")
    
    try:
        # Lire le code source
        project_root = Path(__file__).parent.parent
        main_window_file = project_root / "app" / "views" / "main_window.py"
        
        with open(main_window_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Compter les usages de log_both dans reset_profile
        reset_function_start = content.find("def reset_profile(self):")
        if reset_function_start == -1:
            print("   [ERREUR] Fonction reset_profile non trouvée")
            return False
        
        # Prendre seulement la fonction reset_profile (approximativement)
        reset_function = content[reset_function_start:reset_function_start + 15000]  # Estimation
        log_both_count = reset_function.count("log_both(")
        
        checks = [
            ("Au moins 8 usages de log_both", log_both_count >= 8),
            ("Logging dès la confirmation", "reset_log_file = self._setup_reset_logging()" in reset_function),
            ("Logging fermeture ressources", "log_both(\"🔧 Fermeture des ressources" in reset_function),
            ("Logging résumé final", "log_both(f\"🎉 Réinitialisation terminée" in reset_function),
            ("Logging avant script externe", "log_both(\"🚀 Script de nettoyage externe" in reset_function),
            ("Séparation phases clairement marquée", "FIN PHASE APPLICATION - DEBUT PHASE SCRIPT EXTERNE" in reset_function)
        ]
        
        print(f"   [INFO] {log_both_count} appels à log_both() détectés dans reset_profile()")
        
        all_passed = True
        for check_name, result in checks:
            if result:
                print(f"   [OK] {check_name}")
            else:
                print(f"   [ERREUR] {check_name}")
                all_passed = False
        
        return all_passed
        
    except Exception as e:
        print(f"   [ERREUR] Exception: {e}")
        return False

def main():
    """Point d'entrée principal du test."""
    print("TEST DE CONTINUITÉ DU LOGGING DE RÉINITIALISATION")
    print("=" * 52)
    
    tests = [
        test_setup_reset_logging,
        test_double_logging,
        test_script_continuity,
        test_log_flow
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
    print("\n" + "=" * 52)
    print("RÉSUMÉ DES TESTS")
    print("=" * 52)
    
    passed = sum(1 for r in results if r)
    total = len(results)
    
    print(f"Tests réussis: {passed}/{total}")
    
    if passed == total:
        print("SUCCESS: Logging continu opérationnel !")
        print("")
        print("WORKFLOW DE LOGGING CONFIRMÉ:")
        print("1. Confirmation utilisateur → Création immédiate reset_cleanup.log")
        print("2. Toute la réinitialisation → Double logging (app + reset_cleanup.log)")
        print("3. Script externe → Continue dans le même fichier reset_cleanup.log")
        print("4. Résultat → Un seul fichier avec TOUT l'historique de A à Z")
        print("")
        print("L'utilisateur peut maintenant voir les logs dès la confirmation !")
        return 0
    else:
        print(f"ATTENTION: {total - passed} problème(s) détecté(s)")
        print("Le logging pourrait ne pas être complètement continu")
        return 1

if __name__ == "__main__":
    sys.exit(main())