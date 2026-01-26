#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Audit sécurisé pour les emojis corrompus - utilise des patterns safe
"""

import os
import re
from pathlib import Path
from typing import Dict, List

def main():
    """Audit simple et sécurisé des emojis corrompus."""
    project_root = Path(__file__).parent.parent
    
    # Patterns sécurisés à chercher (évite les caractères corrompus dans le code)
    patterns_to_find = [
        'ðŸ',  # Début des emojis corrompus
        'âš',  # Début des caractères de contrôle corrompus  
        'âœ',  # Autre pattern de contrôle
        'âŒ',  # Pattern d'erreur corrompu
        'ï¸',  # Fin des caractères de contrôle
    ]
    
    extensions = {'.py', '.json', '.yaml', '.yml'}
    ignore_dirs = {
        '__pycache__', '.git', 'node_modules', '.hf_cache', 'models',
        'datasets', 'cache', 'logs', 'temp_uploads', 'cvmatch_env'
    }
    
    files_with_issues = []
    total_files = 0
    total_issues = 0
    
    print("[SAFE AUDIT] Scan des emojis corrompus...")
    
    for file_path in project_root.rglob('*'):
        if (file_path.is_file() and 
            file_path.suffix in extensions and
            not any(ignore_dir in file_path.parts for ignore_dir in ignore_dirs)):
            
            total_files += 1
            
            try:
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                
                file_issues = 0
                line_issues = []
                
                for line_num, line in enumerate(content.splitlines(), 1):
                    for pattern in patterns_to_find:
                        if pattern in line:
                            file_issues += 1
                            line_issues.append({
                                'line': line_num,
                                'pattern': pattern,
                                'context': line.strip()[:80]
                            })
                
                if file_issues > 0:
                    files_with_issues.append({
                        'file': str(file_path.relative_to(project_root)),
                        'issues': file_issues,
                        'details': line_issues[:3]  # Limiter pour l'affichage
                    })
                    total_issues += file_issues
                    
            except Exception as e:
                print(f"[ERROR] {file_path}: {e}")
    
    # Affichage des résultats
    print(f"\n[RESULTATS]")
    print(f"Fichiers scannes: {total_files}")
    print(f"Fichiers avec emojis corrompus: {len(files_with_issues)}")
    print(f"Total issues detectees: {total_issues}")
    
    if files_with_issues:
        print(f"\n[FICHIERS PROBLEMATIQUES]")
        for file_info in sorted(files_with_issues, key=lambda x: x['issues'], reverse=True):
            print(f"\n{file_info['file']}: {file_info['issues']} issues")
            for detail in file_info['details']:
                print(f"  L{detail['line']:3d}: pattern '{detail['pattern']}'")
                print(f"       {detail['context']}")
    
    return len(files_with_issues)

if __name__ == "__main__":
    exit_code = main()
    exit(min(exit_code, 1))