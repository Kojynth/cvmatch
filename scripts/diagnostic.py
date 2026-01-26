#!/usr/bin/env python3
"""
CVMatch Diagnostic Script
========================

Simple diagnostic script to test critical imports and system health.
This script replaces the complex inline diagnostics in the batch file.
"""

import sys
import os
from pathlib import Path

def test_python_info():
    """Test basic Python information."""
    print(f"Python executable: {sys.executable}")
    print(f"Python version: {sys.version}")
    print(f"Python path: {sys.path[0]}")
    return True

def test_pyside6():
    """Test PySide6 availability."""
    try:
        import PySide6
        print(f"PySide6: OK - Version {PySide6.__version__}")
        return True
    except ImportError as e:
        print(f"ERREUR PySide6: {str(e)}")
        return False
    except Exception as e:
        print(f"ERREUR PySide6: {str(e)}")
        return False

def test_qtwidgets():
    """Test QtWidgets availability."""
    try:
        from PySide6.QtWidgets import QApplication
        print("QtWidgets: OK")
        return True
    except ImportError as e:
        print(f"ERREUR QtWidgets: {str(e)}")
        return False
    except Exception as e:
        print(f"ERREUR QtWidgets: {str(e)}")
        return False

def test_critical_imports():
    """Test all critical imports for CVMatch."""
    critical_packages = [
        ('torch', 'PyTorch'),
        ('transformers', 'Transformers'),
        ('loguru', 'Loguru'),
        ('pypdf', 'PyPDF'),
        ('sqlmodel', 'SQLModel'),
        ('pandas', 'Pandas'),
        ('numpy', 'NumPy')
    ]
    
    success_count = 0
    total_count = len(critical_packages)
    
    print("\nTest des dépendances critiques:")
    print("-" * 40)
    
    for package, display_name in critical_packages:
        try:
            __import__(package)
            print(f"[OK] {display_name}: OK")
            success_count += 1
        except ImportError:
            print(f"[MANQUANT] {display_name}: MANQUANT")
        except Exception as e:
            print(f"[ERREUR] {display_name}: ERREUR - {str(e)}")
    
    print("-" * 40)
    print(f"Résultat: {success_count}/{total_count} packages disponibles")
    
    return success_count == total_count

def test_file_structure():
    """Test critical file structure."""
    required_files = [
        'main.py',
        'app/config.py',
        'app/views/main_window.py'
    ]
    
    print("\nTest de la structure des fichiers:")
    print("-" * 40)
    
    all_present = True
    for file_path in required_files:
        if os.path.exists(file_path):
            print(f"[OK] {file_path}: OK")
        else:
            print(f"[MANQUANT] {file_path}: MANQUANT")
            all_present = False
    
    return all_present

def main():
    """Run all diagnostic tests."""
    print("=" * 50)
    print("CVMatch - Diagnostic Système")
    print("=" * 50)
    
    tests = [
        ("Informations Python", test_python_info),
        ("PySide6", test_pyside6),
        ("QtWidgets", test_qtwidgets),
        ("Dépendances Critiques", test_critical_imports),
        ("Structure des Fichiers", test_file_structure)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n[TEST] {test_name}")
        try:
            result = test_func()
            results.append((test_name, result))
            if result:
                print(f"[RÉSULTAT] {test_name}: SUCCÈS")
            else:
                print(f"[RÉSULTAT] {test_name}: ÉCHEC")
        except Exception as e:
            print(f"[RÉSULTAT] {test_name}: ERREUR - {str(e)}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 50)
    print("RÉSUMÉ DES TESTS")
    print("=" * 50)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "[SUCCES]" if result else "[ECHEC] "
        print(f"{status:<10} {test_name}")
    
    print("-" * 50)
    print(f"Total: {passed}/{total} tests réussis")
    
    if passed == total:
        print("\n[SUCCESS] Tous les tests sont passes! CVMatch devrait fonctionner correctement.")
        return 0
    else:
        print(f"\n[WARNING] {total - passed} test(s) ont echoue. Consultez les details ci-dessus.")
        return 1

if __name__ == "__main__":
    sys.exit(main())