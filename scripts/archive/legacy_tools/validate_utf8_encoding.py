#!/usr/bin/env python3
"""
Script de validation des encodages UTF-8 et détection de mojibake.
Utilisé pour prévenir les régressions d'encodage dans le projet CVMatch.
"""

import os
import re
import sys
from pathlib import Path
from typing import List, Dict, Tuple, Set

# Patterns mojibake courants (utilisant Unicode escapes pour éviter les problèmes)
MOJIBAKE_PATTERNS = {
    # UTF-8 → CP1252/Latin-1 - accents minuscules
    "\u00c3\u00a9": "\u00e9",  # Ã© → é
    "\u00c3\u00a8": "\u00e8",  # Ã¨ → è  
    "\u00c3\u00a0": "\u00e0",  # Ã  → à
    "\u00c3\u00a7": "\u00e7",  # Ã§ → ç
    "\u00c3\u00a2": "\u00e2",  # Ã¢ → â
    "\u00c3\u00b4": "\u00f4",  # Ã´ → ô
    "\u00c3\u00ae": "\u00ee",  # Ã® → î
    "\u00c3\u00bb": "\u00fb",  # Ã» → û
    "\u00c3\u00af": "\u00ef",  # Ã¯ → ï
    "\u00c3\u00bc": "\u00fc",  # Ã¼ → ü
    "\u00c3\u00ab": "\u00eb",  # Ã« → ë
    "\u00c3\u00aa": "\u00ea",  # Ãª → ê
    # UTF-8 → CP1252/Latin-1 - accents majuscules
    "\u00c3\u2030": "\u00c9",  # Ã‰ → É
    "\u00c3\u20ac": "\u00c0",  # Ã€ → À  
    "\u00c3\u0160": "\u00ca",  # ÃŠ → Ê
    "\u00c3\u017d": "\u00ce",  # ÃŽ → Î
    "\u00c3\u201d": "\u00d4",  # Ã" → Ô
    "\u00c3\u2122": "\u00d9",  # Ã™ → Ù
    "\u00c3\u0153": "\u00dc",  # Ãœ → Ü
    "\u00c3\u2021": "\u00c7",  # Ã‡ → Ç
    "\u00c3\u2039": "\u00cb",  # Ã‹ → Ë
    # Patterns simples pour détection
    "mojibake_emoji": "emoji_mojibake",
    "mojibake_quote": "quote_mojibake", 
    "mojibake_check": "checkmark_mojibake",
    "mojibake_warn": "warning_mojibake",
    "mojibake_cross": "cross_mojibake",
    "mojibake_nbsp": "nbsp_mojibake",
}

# Emojis valides en Unicode escapes (ne pas signaler comme problématiques)
VALID_UNICODE_EMOJIS = {
    r"\\U0001F[0-9A-F]{3}",  # Emojis Unicode \U0001F...
    r"\\u[0-9A-F]{4}",        # Caractères Unicode \u....
}

class UTF8Validator:
    """Validateur d'encodage UTF-8 et détecteur de mojibake."""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.issues_found = []
        self.files_checked = 0
        
    def validate_project(self) -> Dict[str, any]:
        """Valide tout le projet et retourne un rapport."""
        print("[INFO] Validation encodage UTF-8 du projet CVMatch...")
        
        # Fichiers Python principaux
        py_files = list(self.project_root.rglob("*.py"))
        
        # Filtrer les fichiers à ignorer
        py_files = [f for f in py_files if self._should_check_file(f)]
        
        print(f"[INFO] {len(py_files)} fichiers Python à vérifier")
        
        for py_file in py_files:
            self._check_file(py_file)
        
        return self._generate_report()
    
    def _should_check_file(self, file_path: Path) -> bool:
        """Détermine si un fichier doit être vérifié."""
        # Ignorer certains dossiers
        ignore_dirs = {
            "__pycache__", ".git", ".pytest_cache", ".mypy_cache",
            "node_modules", "venv", "env", ".venv", ".env",
            "models", "cache", "logs", "temp_uploads", ".hf_cache"
        }
        
        # Vérifier si le fichier est dans un dossier à ignorer
        for parent in file_path.parents:
            if parent.name in ignore_dirs:
                return False
        
        # Ignorer certains fichiers spécifiques
        ignore_files = {
            "emoji_utils_old.py",  # Backup
        }
        
        if file_path.name in ignore_files:
            return False
            
        return True
    
    def _check_file(self, file_path: Path):
        """Vérifie un fichier pour les problèmes d'encodage."""
        self.files_checked += 1
        
        try:
            # Lire le fichier
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            
            # Vérifier les patterns mojibake
            issues = self._find_mojibake_issues(content, file_path)
            if issues:
                self.issues_found.extend(issues)
                
        except UnicodeDecodeError as e:
            self.issues_found.append({
                'file': str(file_path),
                'type': 'encoding_error',
                'message': f"Erreur décodage UTF-8: {e}",
                'line': 0
            })
        except Exception as e:
            self.issues_found.append({
                'file': str(file_path),
                'type': 'read_error', 
                'message': f"Erreur lecture: {e}",
                'line': 0
            })
    
    def _find_mojibake_issues(self, content: str, file_path: Path) -> List[Dict]:
        """Trouve les issues mojibake dans le contenu d'un fichier."""
        issues = []
        lines = content.split('\n')
        
        for line_num, line in enumerate(lines, 1):
            # Ignorer les lignes de commentaires avec encodage explicite
            if '# -*- coding:' in line or '# coding:' in line:
                continue
                
            # Vérifier les patterns mojibake
            for mojibake_pattern, description in MOJIBAKE_PATTERNS.items():
                if mojibake_pattern in line:
                    # Vérifier si c'est dans une string ou commentaire
                    context = self._get_line_context(line, mojibake_pattern)
                    
                    issues.append({
                        'file': str(file_path.relative_to(self.project_root)),
                        'type': 'mojibake',
                        'pattern': mojibake_pattern,
                        'expected': description,
                        'line': line_num,
                        'context': context[:100] + '...' if len(context) > 100 else context,
                        'severity': 'high'
                    })
        
        return issues
    
    def _get_line_context(self, line: str, pattern: str) -> str:
        """Obtient le contexte autour d'un pattern trouvé."""
        index = line.find(pattern)
        if index == -1:
            return line.strip()
        
        start = max(0, index - 20)
        end = min(len(line), index + len(pattern) + 20)
        
        return line[start:end].strip()
    
    def _generate_report(self) -> Dict[str, any]:
        """Génère un rapport de validation."""
        report = {
            'files_checked': self.files_checked,
            'issues_count': len(self.issues_found),
            'issues': self.issues_found,
            'status': 'PASS' if len(self.issues_found) == 0 else 'FAIL',
            'severity_breakdown': {}
        }
        
        # Compter par sévérité
        for issue in self.issues_found:
            severity = issue.get('severity', 'medium')
            report['severity_breakdown'][severity] = report['severity_breakdown'].get(severity, 0) + 1
        
        return report


def print_report(report: Dict[str, any]):
    """Affiche le rapport de validation."""
    print("\n" + "="*60)
    print("RAPPORT DE VALIDATION UTF-8")
    print("="*60)
    
    print(f"Fichiers verifies: {report['files_checked']}")
    status_icon = "FAIL" if report['issues_count'] > 0 else "PASS"
    print(f"Issues trouvees: {report['issues_count']} ({status_icon})")
    print(f"Statut: {report['status']}")
    
    if report['severity_breakdown']:
        print("\nRepartition par severite:")
        for severity, count in report['severity_breakdown'].items():
            print(f"  {severity.capitalize()}: {count}")
    
    if report['issues_count'] > 0:
        print("\nDETAILS DES ISSUES:")
        print("-" * 50)
        
        for i, issue in enumerate(report['issues'], 1):
            print(f"\n{i}. {issue['type'].upper()}")
            print(f"   Fichier: {issue['file']}")
            print(f"   Ligne: {issue['line']}")
            
            if issue['type'] == 'mojibake':
                print(f"   Pattern: '{issue['pattern']}'")
                print(f"   Attendu: '{issue['expected']}'")
                print(f"   Contexte: {issue['context']}")
            else:
                print(f"   Message: {issue['message']}")
    
    print("\n" + "="*60)


def fix_mojibake_automatically(report: Dict[str, any], project_root: Path, dry_run: bool = True):
    """Corrige automatiquement les problèmes de mojibake détectés."""
    if report['issues_count'] == 0:
        print("[OK] Aucune correction necessaire")
        return
    
    print(f"\n[INFO] {'SIMULATION' if dry_run else 'CORRECTION'} automatique...")
    
    # Grouper par fichier
    files_to_fix = {}
    for issue in report['issues']:
        if issue['type'] == 'mojibake':
            file_path = issue['file']
            if file_path not in files_to_fix:
                files_to_fix[file_path] = []
            files_to_fix[file_path].append(issue)
    
    for file_path, issues in files_to_fix.items():
        full_path = project_root / file_path
        print(f"\n📝 {'Simulerait' if dry_run else 'Correction'}: {file_path}")
        
        if not dry_run:
            try:
                # Lire le fichier
                with open(full_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Appliquer les corrections
                original_content = content
                for issue in issues:
                    if issue['pattern'] in MOJIBAKE_PATTERNS:
                        correct_char = MOJIBAKE_PATTERNS[issue['pattern']]
                        if correct_char != "emoji_mojibake":  # Éviter les corrections automatiques d'emojis
                            content = content.replace(issue['pattern'], correct_char)
                
                # Sauvegarder si changements
                if content != original_content:
                    with open(full_path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    print(f"  ✅ {len(issues)} corrections appliquées")
                else:
                    print(f"  ℹ️ Aucune correction automatique possible")
                    
            except Exception as e:
                print(f"  ❌ Erreur: {e}")
        
        # Montrer les issues
        for issue in issues[:3]:  # Limiter l'affichage
            print(f"  • Ligne {issue['line']}: '{issue['pattern']}' → '{issue['expected']}'")
        
        if len(issues) > 3:
            print(f"  • ... et {len(issues) - 3} autres")


def main():
    """Point d'entrée principal."""
    project_root = Path(__file__).parent.parent
    
    # Arguments
    dry_run = "--dry-run" in sys.argv or "-n" in sys.argv
    auto_fix = "--fix" in sys.argv
    
    validator = UTF8Validator(project_root)
    report = validator.validate_project()
    
    print_report(report)
    
    # Correction automatique si demandée
    if auto_fix:
        fix_mojibake_automatically(report, project_root, dry_run=dry_run)
    
    # Code de sortie
    sys.exit(0 if report['status'] == 'PASS' else 1)


if __name__ == "__main__":
    main()