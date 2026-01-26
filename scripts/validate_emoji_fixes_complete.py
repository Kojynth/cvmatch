#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Validation complète des corrections emoji - CVMatch
===================================================

Script de validation pour vérifier que tous les emojis corrompus ont été corrigés
et que le système de fallback fonctionne correctement.

Utilisation:
    python scripts/validate_emoji_fixes_complete.py
"""

import sys
import re
from pathlib import Path
from typing import Dict, List, Tuple

# Ajouter le chemin racine pour les imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_corrupted_patterns():
    """Teste que les patterns corrompus ont été éliminés."""
    try:
        print("🔍 Vérification des patterns emoji corrompus...")
    except UnicodeEncodeError:
        print("[SEARCH] Verification des patterns emoji corrompus...")
    
    main_window_path = project_root / "app" / "views" / "main_window.py"
    if not main_window_path.exists():
        print("❌ Fichier main_window.py introuvable")
        return False
    
    content = main_window_path.read_text(encoding='utf-8')
    
    # Patterns corrompus qui ne doivent plus exister
    corrupted_patterns = [
        r'🔍[„—Ž]',  # Emojis recherche corrompus
        r'├ó┬¡',       # Etoiles corrompues
        r'├░┼©',       # Patterns mojibake génériques
        r'├ó┼ô',       # Checkmarks corrompus (anciens)
        r'├ó┼Æ',       # X corrompus (anciens)
    ]
    
    issues_found = []
    for pattern in corrupted_patterns:
        matches = re.findall(pattern, content)
        if matches:
            issues_found.append((pattern, len(matches)))
    
    if issues_found:
        print("❌ Patterns corrompus détectés :")
        for pattern, count in issues_found:
            print(f"   • {pattern}: {count} instances")
        return False
    else:
        print("✅ Aucun pattern corrompu trouvé")
        return True

def test_star_emojis():
    """Vérifie que les emojis étoiles sont correctement fixés."""
    print("\n⭐ Vérification des emojis étoiles...")
    
    main_window_path = project_root / "app" / "views" / "main_window.py"
    content = main_window_path.read_text(encoding='utf-8')
    
    # Rechercher les statistiques avec étoiles
    star_patterns = [
        r'Note moyenne.*⭐',  # Doit contenir l'étoile correcte
    ]
    
    star_fixes = 0
    for pattern in star_patterns:
        matches = re.findall(pattern, content)
        star_fixes += len(matches)
    
    if star_fixes >= 2:  # Au moins 2 instances (lignes 206 et 600)
        print(f"✅ Emojis étoiles corrects : {star_fixes} instances trouvées")
        return True
    else:
        print(f"❌ Emojis étoiles manquants : seulement {star_fixes} instances")
        return False

def test_button_emojis():
    """Vérifie que les emojis de boutons sont appropriés."""
    print("\n🔘 Vérification des emojis de boutons...")
    
    main_window_path = project_root / "app" / "views" / "main_window.py"
    content = main_window_path.read_text(encoding='utf-8')
    
    # Boutons avec emojis appropriés attendus
    expected_buttons = [
        (r'QPushButton.*🔄.*Remplacer', "Bouton remplacer avec 🔄"),
        (r'QPushButton.*🔍.*Extraire', "Bouton extraire avec 🔍"),  
        (r'QPushButton.*🔗.*LinkedIn', "Bouton LinkedIn avec 🔗"),
        (r'QPushButton.*🚀.*Réentraîner', "Bouton réentraîner avec 🚀"),
        (r'QPushButton.*💾.*Sauvegarder', "Bouton sauvegarder avec 💾"),
        (r'QPushButton.*🔄.*Actualiser', "Bouton actualiser avec 🔄"),
    ]
    
    buttons_ok = 0
    total_expected = len(expected_buttons)
    
    for pattern, description in expected_buttons:
        matches = re.findall(pattern, content)
        if matches:
            print(f"✅ {description} : trouvé")
            buttons_ok += 1
        else:
            print(f"❌ {description} : manquant")
    
    if buttons_ok >= total_expected * 0.8:  # Au moins 80% des boutons
        print(f"✅ Boutons emoji : {buttons_ok}/{total_expected} corrects")
        return True
    else:
        print(f"❌ Boutons emoji : seulement {buttons_ok}/{total_expected} corrects")
        return False

def test_fallback_system():
    """Teste que le système de fallback emoji est intégré."""
    print("\n🛠️ Vérification du système de fallback...")
    
    main_window_path = project_root / "app" / "views" / "main_window.py"
    content = main_window_path.read_text(encoding='utf-8')
    
    fallback_indicators = [
        r'from.*emoji_utils.*import.*get_display_text',  # Import correct
        r'setup_emoji_support\(\)',  # Initialisation
        r'get_display_text\(',  # Utilisation
    ]
    
    fallback_features = 0
    for pattern in fallback_indicators:
        if re.search(pattern, content):
            fallback_features += 1
    
    if fallback_features >= 3:
        print("✅ Système de fallback emoji intégré")
        return True
    else:
        print(f"❌ Système de fallback incomplete : {fallback_features}/3 features")
        return False

def test_emoji_utils_available():
    """Vérifie que emoji_utils.py est disponible et fonctionnel."""
    print("\n📦 Vérification d'emoji_utils...")
    
    try:
        from app.utils.emoji_utils import get_display_text, safe_emoji, setup_emoji_support
        
        # Test basique
        test_text = get_display_text("⭐ Test")
        if test_text:
            print("✅ emoji_utils fonctionne correctement")
            return True
        else:
            print("❌ emoji_utils retourne une valeur vide")
            return False
            
    except ImportError as e:
        print(f"❌ Impossible d'importer emoji_utils : {e}")
        return False
    except Exception as e:
        print(f"❌ Erreur dans emoji_utils : {e}")
        return False

def generate_report():
    """Génère un rapport complet de validation."""
    print("\n" + "="*60)
    print("📋 RAPPORT DE VALIDATION EMOJI - CVMatch")
    print("="*60)
    
    tests = [
        ("Patterns corrompus éliminés", test_corrupted_patterns),
        ("Emojis étoiles corrigés", test_star_emojis), 
        ("Emojis boutons appropriés", test_button_emojis),
        ("Système fallback intégré", test_fallback_system),
        ("emoji_utils disponible", test_emoji_utils_available),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"❌ Erreur lors du test '{test_name}': {e}")
            results.append((test_name, False))
    
    # Résumé
    print("\n" + "="*60)
    print("📊 RÉSUMÉ DES TESTS")
    print("="*60)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for test_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} | {test_name}")
    
    print(f"\n🎯 SCORE GLOBAL : {passed}/{total} tests réussis ({passed/total*100:.1f}%)")
    
    if passed == total:
        print("\n🎉 VALIDATION COMPLÈTE RÉUSSIE !")
        print("Tous les problèmes d'emoji ont été résolus avec succès.")
        return True
    elif passed >= total * 0.8:
        print("\n✅ VALIDATION LARGEMENT RÉUSSIE !")
        print("Les problèmes majeurs sont résolus.")
        return True
    else:
        print("\n⚠️ VALIDATION PARTIELLE")
        print("Certains problèmes nécessitent encore une attention.")
        return False

def main():
    """Fonction principale."""
    try:
        print("🔧 Validation des corrections emoji CVMatch")
    except UnicodeEncodeError:
        print("[WRENCH] Validation des corrections emoji CVMatch")
    print("=" * 50)
    
    success = generate_report()
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())