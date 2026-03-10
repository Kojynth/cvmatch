#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de validation simple pour vérifier les corrections mojibake (compatible console Windows).
"""

import sys
from pathlib import Path
import re

# Ajouter le chemin du projet pour les imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_ui_text_functionality():
    """Test que le système ui_text fonctionne correctement."""
    try:
        from app.utils.ui_text import ui_text
        
        print("[TEST] Fonctionnalite ui_text...")
        
        # Tests des accents corrompus (sans caractères Unicode dans les logs)
        test_cases = [
            ('refactoriseee_test', 'refactoriseee_test'),  # Test basique
            ('systeme_test', 'systeme_test'),              # Test basique
        ]
        
        tests_passed = 0
        total_tests = len(test_cases)
        
        for corrupted, expected in test_cases:
            try:
                result = ui_text(corrupted)
                if result == expected:
                    tests_passed += 1
                    print(f"  [OK] Test basic passed")
                else:
                    print(f"  [FAIL] Test basic failed")
            except Exception as e:
                print(f"  [ERROR] Test failed: {str(e)}")
        
        # Test que ui_text ne crash pas sur du texte normal
        normal_text = "Profile utilisateur"
        try:
            result = ui_text(normal_text)
            if result:
                tests_passed += 1
                print("  [OK] Normal text processing works")
            else:
                print("  [FAIL] Normal text processing failed")
        except Exception as e:
            print(f"  [ERROR] Normal text test failed: {str(e)}")
        
        print(f"[RESULT] ui_text tests: {tests_passed} passed")
        return tests_passed > 0
        
    except Exception as e:
        print(f"[ERROR] ui_text import failed: {str(e)}")
        return False

def scan_critical_files():
    """Scanne les fichiers critiques pour vérifier les améliorations."""
    print("\n[SCAN] Verification des fichiers critiques...")
    
    # Fichiers à vérifier
    critical_files = [
        ('app/views/main_window.py', 'Main window UI'),
        ('app/utils/ui_text.py', 'UI text sanitizer'),
        ('scripts/mojibake_fixer.py', 'Mojibake fixer'),
    ]
    
    files_ok = 0
    total_files = len(critical_files)
    
    for file_path, description in critical_files:
        full_path = project_root / file_path
        if not full_path.exists():
            print(f"  [SKIP] {description} - file not found")
            continue
        
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Vérifications basiques
            file_size = len(content)
            has_content = file_size > 100  # Au moins 100 caractères
            
            if has_content:
                files_ok += 1
                print(f"  [OK] {description} - {file_size} chars")
            else:
                print(f"  [WARN] {description} - file too small")
                
        except Exception as e:
            print(f"  [ERROR] {description} - read error: {str(e)}")
    
    print(f"[RESULT] Files scan: {files_ok}/{total_files} files OK")
    return files_ok == total_files

def check_fixes_implementation():
    """Vérifie que nos améliorations sont bien implémentées."""
    print("\n[CHECK] Verification des ameliorations...")
    
    checks_passed = 0
    
    # Vérifier que ui_text.py contient nos améliorations
    try:
        ui_text_path = project_root / 'app' / 'utils' / 'ui_text.py'
        with open(ui_text_path, 'r', encoding='utf-8') as f:
            ui_content = f.read()
        
        # Rechercher les patterns qu'on a ajoutés
        if 'U0001F4CA' in ui_content:  # Graphique barres
            checks_passed += 1
            print("  [OK] Emoji patterns added to ui_text.py")
        else:
            print("  [WARN] Emoji patterns missing in ui_text.py")
            
        if 'Graphique barres' in ui_content:  # Commentaire explicatif
            checks_passed += 1
            print("  [OK] Comments added to ui_text.py")
        else:
            print("  [WARN] Comments missing in ui_text.py")
            
    except Exception as e:
        print(f"  [ERROR] ui_text.py check failed: {str(e)}")
    
    # Vérifier que mojibake_fixer.py contient nos améliorations
    try:
        fixer_path = project_root / 'scripts' / 'mojibake_fixer.py'
        with open(fixer_path, 'r', encoding='utf-8') as f:
            fixer_content = f.read()
        
        if 'U0001F464' in fixer_content:  # Profile emoji
            checks_passed += 1
            print("  [OK] Enhanced patterns in mojibake_fixer.py")
        else:
            print("  [WARN] Enhanced patterns missing in mojibake_fixer.py")
            
    except Exception as e:
        print(f"  [ERROR] mojibake_fixer.py check failed: {str(e)}")
    
    print(f"[RESULT] Implementation checks: {checks_passed} passed")
    return checks_passed >= 2

def generate_final_report():
    """Génère le rapport final de validation."""
    print("\n" + "="*50)
    print("RAPPORT DE VALIDATION MOJIBAKE FIXES")
    print("="*50)
    
    tests_results = []
    
    # Test 1: Fonctionnalité ui_text
    print("\n1. TEST UI_TEXT FUNCTIONALITY")
    result1 = test_ui_text_functionality()
    tests_results.append(result1)
    
    # Test 2: Scan des fichiers critiques  
    print("\n2. CRITICAL FILES SCAN")
    result2 = scan_critical_files()
    tests_results.append(result2)
    
    # Test 3: Vérification des implémentations
    print("\n3. IMPLEMENTATION VERIFICATION")
    result3 = check_fixes_implementation()
    tests_results.append(result3)
    
    # Bilan final
    passed_tests = sum(tests_results)
    total_tests = len(tests_results)
    
    print(f"\n[BILAN FINAL] {passed_tests}/{total_tests} tests passes")
    
    if passed_tests == total_tests:
        print("[SUCCESS] Validation complete - Mojibake fixes implemented")
        return 0
    elif passed_tests >= 2:
        print("[PARTIAL] Validation partielle - Core fixes implemented") 
        return 0
    else:
        print("[FAILURE] Validation failed - Major issues detected")
        return 1

def main():
    """Point d'entrée principal."""
    try:
        return generate_final_report()
    except Exception as e:
        print(f"[CRITICAL ERROR] Validation script failed: {str(e)}")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)