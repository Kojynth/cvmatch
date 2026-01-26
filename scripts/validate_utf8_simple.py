#!/usr/bin/env python3
"""
Script simple de validation UTF-8 pour CVMatch.
Version simplifiée sans emojis pour éviter les problèmes d'encodage.
"""

import sys
from pathlib import Path

def check_file_for_mojibake(file_path: Path) -> int:
    """Vérifie un fichier pour les problèmes de mojibake."""
    issues = 0
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Patterns mojibake simples à détecter
        mojibake_indicators = [
            'Ã©', 'Ã¨', 'Ã ', 'Ã§', 'Ã¢', 'Ã´', 'Ã®', 'Ã»',  # Accents
            'ðŸ', 'â€', 'âœ', 'âš', 'âŒ',  # Emojis mojibakés
        ]
        
        lines = content.split('\n')
        for line_num, line in enumerate(lines, 1):
            for pattern in mojibake_indicators:
                if pattern in line and 'utf-8' not in line.lower():
                    print(f"ISSUE: {file_path.name}:{line_num} - Pattern '{pattern}' detected")
                    issues += 1
                    break  # Une issue par ligne suffit
                    
    except Exception as e:
        print(f"ERROR: Cannot read {file_path}: {e}")
        issues += 1
        
    return issues

def main():
    """Point d'entrée principal."""
    project_root = Path(__file__).parent.parent
    print(f"Validating UTF-8 encoding in {project_root}")
    
    # Fichiers Python principaux
    py_files = list(project_root.rglob("*.py"))
    
    # Filtrer les dossiers à ignorer
    ignore_dirs = {'__pycache__', '.git', 'models', 'cache', 'logs', 'temp_uploads', '.hf_cache'}
    py_files = [f for f in py_files if not any(p.name in ignore_dirs for p in f.parents)]
    
    print(f"Checking {len(py_files)} Python files...")
    
    total_issues = 0
    files_with_issues = 0
    
    for py_file in py_files:
        file_issues = check_file_for_mojibake(py_file)
        if file_issues > 0:
            files_with_issues += 1
        total_issues += file_issues
    
    print(f"\nRESULTS:")
    print(f"Files checked: {len(py_files)}")
    print(f"Files with issues: {files_with_issues}")
    print(f"Total issues: {total_issues}")
    print(f"Status: {'PASS' if total_issues == 0 else 'FAIL'}")
    
    return 0 if total_issues == 0 else 1

if __name__ == "__main__":
    sys.exit(main())