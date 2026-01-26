#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Audit spécialisé pour les emojis et caractères Unicode corrompus - Phase 2
"""

import os
import re
from pathlib import Path
from typing import Dict, List

class EmojiAuditor:
    """Auditeur spécialisé pour les emojis et caractères Unicode corrompus."""
    
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        
        # Patterns d'emojis corrompus détectés dans le projet
        self.corrupt_emoji_patterns = [
            # Emojis courants corrompus
            r'ð[Ÿ\x9F][^\s]{1,3}',  # Patterns ðŸxxx
            r'â[€\x80-\x99][^\s]{0,2}',  # Patterns â€xxx
            r'Â[°«»®©™]',  # Caractères spéciaux
            # Patterns spécifiques trouvés
            r'ðŸ'¤', r'ðŸ"‹', r'ðŸ"§', r'ðŸ'¼', r'ðŸŽ"',
            r'ðŸ"ž', r'ðŸ"—', r'ðŸ'¡', r'ðŸ"Š', r'ðŸŽ¯',
            r'ðŸ"ˆ', r'ðŸ ', r'ðŸ"', r'ðŸ"‚', r'ðŸ"™',
            r'ðŸ"'', r'ðŸ›¡ï¸', r'ðŸš«', r'ðŸ–¥ï¸', r'ðŸ"',
            # Caractères de contrôle
            r'âš™ï¸', r'âœ…', r'âŒ', r'âš ï¸', r'âš–ï¸',
        ]
        
        self.extensions = {'.py', '.json', '.yaml', '.yml'}
        self.ignore_dirs = {
            '__pycache__', '.git', 'node_modules', '.hf_cache', 'models',
            'datasets', 'cache', 'logs', 'temp_uploads', 'cvmatch_env'
        }
    
    def scan_file(self, file_path: Path) -> Dict:
        """Scanne un fichier pour les emojis corrompus."""
        result = {
            'file': str(file_path.relative_to(self.project_root)),
            'corrupt_emojis': [],
            'total_issues': 0
        }
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
                
            for line_num, line in enumerate(content.splitlines(), 1):
                for pattern in self.corrupt_emoji_patterns:
                    matches = re.finditer(pattern, line)
                    for match in matches:
                        result['corrupt_emojis'].append({
                            'line': line_num,
                            'pattern': match.group(),
                            'context': line.strip()[:100]
                        })
                        result['total_issues'] += 1
                        
        except Exception as e:
            result['error'] = str(e)
        
        return result
    
    def scan_project(self) -> Dict:
        """Scanne tout le projet pour les emojis corrompus."""
        results = {
            'summary': {
                'files_scanned': 0,
                'files_with_issues': 0,
                'total_corrupt_emojis': 0
            },
            'files': []
        }
        
        for file_path in self.project_root.rglob('*'):
            if (file_path.is_file() and 
                file_path.suffix in self.extensions and
                not any(ignore_dir in file_path.parts for ignore_dir in self.ignore_dirs)):
                
                results['summary']['files_scanned'] += 1
                file_result = self.scan_file(file_path)
                
                if file_result['total_issues'] > 0:
                    results['summary']['files_with_issues'] += 1
                    results['summary']['total_corrupt_emojis'] += file_result['total_issues']
                    results['files'].append(file_result)
        
        return results
    
    def print_results(self, results: Dict):
        """Affiche les résultats de manière lisible."""
        print(f"[AUDIT EMOJI] {results['summary']['files_scanned']} fichiers scannes")
        print(f"[AUDIT EMOJI] {results['summary']['files_with_issues']} fichiers avec emojis corrompus")
        print(f"[AUDIT EMOJI] {results['summary']['total_corrupt_emojis']} emojis corrompus detectes")
        
        if results['files']:
            print(f"\n[DETAILS]:")
            for file_info in sorted(results['files'], key=lambda x: x['total_issues'], reverse=True):
                print(f"\n{file_info['file']}: {file_info['total_issues']} issues")
                for issue in file_info['corrupt_emojis'][:5]:  # Limiter à 5 par fichier
                    print(f"  L{issue['line']:3d}: '{issue['pattern']}'")
                    print(f"       {issue['context']}")
                if len(file_info['corrupt_emojis']) > 5:
                    print(f"       ... et {len(file_info['corrupt_emojis']) - 5} autres")

def main():
    """Point d'entrée principal."""
    project_root = Path(__file__).parent.parent
    auditor = EmojiAuditor(str(project_root))
    
    print("[EMOJI AUDIT] Scan des emojis corrompus...")
    results = auditor.scan_project()
    auditor.print_results(results)
    
    return results['summary']['files_with_issues']

if __name__ == "__main__":
    exit_code = main()
    exit(min(exit_code, 1))