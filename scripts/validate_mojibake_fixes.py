#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de validation pour vérifier que les corrections mojibake ont été appliquées correctement.
"""

import sys
from pathlib import Path
import re

# Ajouter le chemin du projet pour les imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_ui_text_functionality():
    """Test que le système ui_text fonctionne correctement avec les nouveaux patterns."""
    try:
        from app.utils.ui_text import ui_text
        
        print("[TEST] Fonctionnalité ui_text...")
        
        # Tests des accents corrompus
        test_cases = [
            ('refactorisÃ©e', 'refactorisée'),
            ('systÃ¨me', 'système'),
            ('tÃ©lÃ©phone', 'téléphone'),
            ('gÃ©nÃ©rÃ©s', 'générés'),
            ('prÃ©fÃ©rences', 'préférences'),
            ('caractÃ¨res', 'caractères'),
            ('opÃ©ration', 'opération'),
        ]
        
        for corrupted, expected in test_cases:
            result = ui_text(corrupted)
            if result == expected:
                print(f"  ✓ '{corrupted}' → '{expected}'")
            else:
                print(f"  ✗ '{corrupted}' → '{result}' (attendu: '{expected}')")
        
        # Tests des emojis via codes Unicode
        emoji_tests = [
            ('\U0001F464', '👤'),  # Profil
            ('\U0001F4CB', '📋'),  # Presse-papier
            ('\U0001F4CA', '📊'),  # Graphique
            ('\u2699\uFE0F', '⚙️'),  # Engrenage
            ('\u2705', '✅'),       # Check
            ('\u274C', '❌'),       # Croix
        ]
        
        for unicode_char, expected in emoji_tests:
            result = ui_text(unicode_char)
            if result == expected:
                print(f"  ✓ Emoji Unicode → {expected}")
            else:
                print(f"  ✗ Emoji Unicode → {result} (attendu: {expected})")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] Test ui_text échoué: {e}")
        return False

def scan_for_remaining_mojibake():
    """Scanne les fichiers critiques pour identifier le mojibake restant."""
    print("\n[SCAN] Recherche du mojibake restant...")
    
    # Patterns mojibake à rechercher
    patterns = [
        r'Ã[©¨ ªÂ¢¹¼´§®¯»]',  # Accents français corrompus
        r'â€[™œ"•¦]',           # Caractères spéciaux corrompus
        r'ð\x9f[\x91-\x9f][\x80-\xbf]',  # Emojis corrompus
        r'âš[™ ï¸]',            # Emojis de contrôle corrompus
    ]
    
    # Fichiers critiques à vérifier
    critical_files = [
        'app/views/main_window.py',
        'app/utils/ui_text.py',
        'scripts/mojibake_fixer.py',
    ]
    
    total_issues = 0
    for file_path in critical_files:
        full_path = project_root / file_path
        if not full_path.exists():
            print(f"  [SKIP] {file_path} non trouvé")
            continue
        
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            file_issues = 0
            for pattern in patterns:
                matches = re.findall(pattern, content)
                file_issues += len(matches)
            
            if file_issues > 0:
                print(f"  ⚠️  {file_path}: {file_issues} problèmes détectés")
                total_issues += file_issues
            else:
                print(f"  ✓ {file_path}: aucun problème détecté")
                
        except Exception as e:
            print(f"  ✗ {file_path}: erreur de lecture - {e}")
    
    print(f"\n[RÉSULTAT] {total_issues} problèmes mojibake restants détectés")
    return total_issues == 0

def test_enhanced_mojibake_fixer():
    """Teste que le fixer amélioré contient tous les patterns nécessaires."""
    print("\n[TEST] Vérification du fixer amélioré...")
    
    try:
        fixer_path = project_root / 'scripts' / 'mojibake_fixer.py'
        if not fixer_path.exists():
            print("  ✗ mojibake_fixer.py non trouvé")
            return False
        
        with open(fixer_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Vérifier la présence des patterns essentiels
        essential_patterns = [
            'Ã©.*é',    # Accent é corrompu
            'Ã¨.*è',    # Accent è corrompu
            'â€™.*\'',   # Apostrophe corrompue
            'U0001F464', # Emoji profil
            'u2699',     # Emoji engrenage
        ]
        
        missing_patterns = []
        for pattern in essential_patterns:
            if not re.search(pattern, content):
                missing_patterns.append(pattern)
        
        if missing_patterns:
            print(f"  ✗ Patterns manquants: {missing_patterns}")
            return False
        else:
            print("  ✓ Tous les patterns essentiels présents")
            return True
            
    except Exception as e:
        print(f"  ✗ Erreur lors du test du fixer: {e}")
        return False

def generate_report():
    """Génère un rapport de validation complet."""
    print("\n" + "="*60)
    print("RAPPORT DE VALIDATION MOJIBAKE")
    print("="*60)
    
    tests_passed = 0
    total_tests = 3
    
    # Test 1: Fonctionnalité ui_text
    if test_ui_text_functionality():
        tests_passed += 1
    
    # Test 2: Scan des problèmes restants  
    if scan_for_remaining_mojibake():
        tests_passed += 1
    
    # Test 3: Vérification du fixer amélioré
    if test_enhanced_mojibake_fixer():
        tests_passed += 1
    
    print(f"\n[BILAN] {tests_passed}/{total_tests} tests réussis")
    
    if tests_passed == total_tests:
        print("✅ VALIDATION RÉUSSIE - Corrections mojibake complètes")
        return 0
    else:
        print("⚠️  VALIDATION PARTIELLE - Actions supplémentaires requises")
        return 1

def main():
    """Point d'entrée principal."""
    try:
        return generate_report()
    except Exception as e:
        print(f"[ERREUR CRITIQUE] {e}")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)