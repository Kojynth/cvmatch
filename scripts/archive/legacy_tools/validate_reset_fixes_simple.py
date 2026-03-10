#!/usr/bin/env python3
"""Test simple des corrections de réinitialisation"""

import sys
from pathlib import Path

def main():
    print("VALIDATION DES CORRECTIONS DE REINITIALISATION")
    print("=" * 48)
    
    try:
        # Lire le code source
        project_root = Path(__file__).parent.parent
        main_window_file = project_root / "app" / "views" / "main_window.py"
        
        with open(main_window_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        tests_passed = 0
        total_tests = 0
        
        # Test 1: Fichier de log dans le bon dossier
        print("1. Emplacement fichier reset_cleanup.log...")
        total_tests += 1
        if 'logs" / "réinitialisation" / "reset_cleanup.log"' in content:
            print("   [OK] Fichier sera créé dans logs/réinitialisation/")
            tests_passed += 1
        else:
            print("   [ERREUR] Fichier toujours à la racine")
        
        # Test 2: Création automatique du dossier
        print("2. Création automatique du dossier...")
        total_tests += 1
        if 'log_dir.mkdir(parents=True, exist_ok=True)' in content:
            print("   [OK] Dossier sera créé automatiquement")
            tests_passed += 1
        else:
            print("   [ERREUR] Création automatique manquante")
        
        # Test 3: Affichage format court
        print("3. Affichage nom de fichier uniquement...")
        total_tests += 1
        if 'logs/réinitialisation/{log_file_path.name}' in content:
            print("   [OK] Affichage utilisera le format court")
            tests_passed += 1
        else:
            print("   [ERREUR] Affichage du chemin complet toujours présent")
        
        # Test 4: Améliorations du script de redémarrage
        print("4. Améliorations script de redémarrage...")
        total_tests += 1
        improvements = [
            "echo Lancement via CVMatch.bat...",
            "echo CVMatch devrait se relancer dans quelques secondes..."
        ]
        
        found_improvements = sum(1 for imp in improvements if imp in content)
        if found_improvements >= len(improvements):
            print("   [OK] Script de redémarrage amélioré")
            tests_passed += 1
        else:
            print(f"   [ATTENTION] {len(improvements) - found_improvements} amélioration(s) manquante(s)")
        
        print("\n" + "=" * 48)
        print(f"RESULTATS: {tests_passed}/{total_tests} tests réussis")
        
        if tests_passed == total_tests:
            print("🎉 TOUTES LES CORRECTIONS SONT EN PLACE !")
            print("")
            print("AMÉLIORATIONS APPLIQUÉES:")
            print("• Fichier reset_cleanup.log dans logs/réinitialisation/")
            print("• Affichage montre seulement le nom de fichier")
            print("• Script de redémarrage plus informatif")
            print("• Création automatique du dossier de logs")
            return 0
        else:
            print(f"⚠️ {total_tests - tests_passed} problème(s) restant(s)")
            return 1
            
    except Exception as e:
        print(f"[ERREUR] {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())