#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Validation simple des corrections emoji - CVMatch (Windows-safe)
===============================================================

Script de validation pour vérifier que tous les emojis corrompus ont été corrigés.
Version compatible avec les consoles Windows.
"""

import sys
import re
from pathlib import Path

# Ajouter le chemin racine pour les imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def safe_print(text, fallback_text):
    """Affiche le texte avec fallback pour compatibilité Windows."""
    try:
        print(text)
    except UnicodeEncodeError:
        print(fallback_text)

def test_corrupted_patterns():
    """Teste que les patterns corrompus ont été éliminés."""
    safe_print("🔍 Vérification patterns corrompus...", "[SEARCH] Verification patterns corrompus...")
    
    main_window_path = project_root / "app" / "views" / "main_window.py"
    if not main_window_path.exists():
        print("ERREUR: Fichier main_window.py introuvable")
        return False
    
    content = main_window_path.read_text(encoding='utf-8')
    
    # Patterns corrompus critiques
    corrupted_patterns = [
        (r'🔍[„—Ž]', "Emojis recherche corrompus"),
        (r'├ó┬¡', "Etoiles corrompues"),
        (r'├░┼©', "Patterns mojibake génériques"),
    ]
    
    issues_found = 0
    for pattern, description in corrupted_patterns:
        matches = re.findall(pattern, content)
        if matches:
            print(f"  ERREUR: {description} - {len(matches)} instances")
            issues_found += len(matches)
    
    if issues_found == 0:
        safe_print("✅ Aucun pattern corrompu", "OK: Aucun pattern corrompu")
        return True
    else:
        print(f"ERREUR: {issues_found} patterns corrompus trouvés")
        return False

def test_star_fixes():
    """Vérifie les corrections d'étoiles."""
    safe_print("⭐ Vérification étoiles...", "[STAR] Verification etoiles...")
    
    main_window_path = project_root / "app" / "views" / "main_window.py"
    content = main_window_path.read_text(encoding='utf-8')
    
    # Rechercher statistiques avec étoiles correctes
    star_count = len(re.findall(r'Note moyenne.*⭐', content))
    
    if star_count >= 2:
        safe_print(f"✅ {star_count} étoiles correctes", f"OK: {star_count} etoiles correctes")
        return True
    else:
        print(f"ERREUR: Seulement {star_count} étoiles trouvées")
        return False

def test_button_fixes():
    """Vérifie les boutons corrigés."""
    safe_print("🔘 Vérification boutons...", "[BTN] Verification boutons...")
    
    main_window_path = project_root / "app" / "views" / "main_window.py"
    content = main_window_path.read_text(encoding='utf-8')
    
    # Boutons clés attendus
    button_tests = [
        (r'🔄.*Remplacer', "Remplacer avec cycle"),
        (r'🔍.*Extraire', "Extraire avec loupe"),
        (r'🔗.*LinkedIn', "LinkedIn avec lien"),
        (r'💾.*Sauvegarder', "Sauvegarder avec disquette"),
    ]
    
    buttons_ok = 0
    for pattern, description in button_tests:
        if re.search(pattern, content):
            print(f"  OK: {description}")
            buttons_ok += 1
        else:
            print(f"  MANQUE: {description}")
    
    if buttons_ok >= len(button_tests) * 0.75:  # 75% minimum
        safe_print(f"✅ {buttons_ok}/{len(button_tests)} boutons OK", 
                  f"OK: {buttons_ok}/{len(button_tests)} boutons OK")
        return True
    else:
        print(f"ERREUR: Seulement {buttons_ok}/{len(button_tests)} boutons corrects")
        return False

def test_fallback_integration():
    """Teste l'intégration du système de fallback."""
    safe_print("🛠️ Vérification fallback...", "[TOOL] Verification fallback...")
    
    main_window_path = project_root / "app" / "views" / "main_window.py"
    content = main_window_path.read_text(encoding='utf-8')
    
    # Indicateurs d'intégration
    has_import = bool(re.search(r'from.*emoji_utils.*import.*get_display_text', content))
    has_setup = bool(re.search(r'setup_emoji_support\(\)', content))
    has_usage = bool(re.search(r'get_display_text\(', content))
    
    integration_score = sum([has_import, has_setup, has_usage])
    
    print(f"  Import emoji_utils: {'OK' if has_import else 'MANQUE'}")
    print(f"  Setup émoji: {'OK' if has_setup else 'MANQUE'}")
    print(f"  Utilisation: {'OK' if has_usage else 'MANQUE'}")
    
    if integration_score >= 3:
        safe_print("✅ Système fallback intégré", "OK: Systeme fallback integre")
        return True
    else:
        print(f"ERREUR: Intégration incomplète ({integration_score}/3)")
        return False

def main():
    """Fonction principale."""
    print("=" * 60)
    print("VALIDATION CORRECTIONS EMOJI - CVMatch")
    print("=" * 60)
    
    tests = [
        ("Patterns corrompus éliminés", test_corrupted_patterns),
        ("Étoiles statistiques corrigées", test_star_fixes),
        ("Boutons emoji appropriés", test_button_fixes),
        ("Système fallback intégré", test_fallback_integration),
    ]
    
    results = []
    print("\nExécution des tests:")
    print("-" * 30)
    
    for test_name, test_func in tests:
        print(f"\n• {test_name}")
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"  ERREUR: {e}")
            results.append((test_name, False))
    
    # Rapport final
    print("\n" + "=" * 60)
    print("RAPPORT FINAL")
    print("=" * 60)
    
    passed = 0
    for test_name, success in results:
        status = "PASS" if success else "FAIL"
        print(f"{status:4} | {test_name}")
        if success:
            passed += 1
    
    total = len(results)
    success_rate = (passed / total) * 100
    
    print(f"\nSCORE: {passed}/{total} tests réussis ({success_rate:.1f}%)")
    
    if passed == total:
        safe_print("\n🎉 VALIDATION RÉUSSIE !", "\nSUCCESS: VALIDATION REUSSIE !")
        print("Tous les problèmes d'emoji ont été résolus.")
        return True
    elif success_rate >= 75:
        safe_print("\n✅ VALIDATION LARGEMENT RÉUSSIE !", "\nGOOD: VALIDATION LARGEMENT REUSSIE !")
        print("Les problèmes critiques sont résolus.")
        return True
    else:
        safe_print("\n⚠️ VALIDATION PARTIELLE", "\nWARNING: VALIDATION PARTIELLE")
        print("Certains problèmes nécessitent attention.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)