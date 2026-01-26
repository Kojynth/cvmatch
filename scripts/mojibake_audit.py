#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script d'audit pour détecter tous les problèmes d'encodage mojibake dans le projet CVMatch.
"""

import os
import re
import json
from pathlib import Path
from typing import Dict, List, Tuple, Set

class MojibakeAuditor:
    """Auditeur pour détecter les problèmes d'encodage dans le projet."""
    
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        
        # Patterns mojibake courants (UTF-8 décodé comme Latin-1)
        self.mojibake_patterns = {
            # Accents français
            'Ã©': 'é',  'Ã¨': 'è',  'Ã ': 'à',  'Ãª': 'ê',  'Ã«': 'ë',
            'Ã¢': 'â',  'Ã¹': 'ù',  'Ã¼': 'ü',  'Ã´': 'ô',  'Ã§': 'ç',
            'Ã®': 'î',  'Ã¯': 'ï',  'Ã»': 'û',
            # Majuscules
            'Ã‰': 'É',  'Ã€': 'À',  'ÃŠ': 'Ê',  'ÃŽ': 'Î',  'Ã"': 'Ô',
            'Ã™': 'Ù',  'Ãœ': 'Ü',  'Ã‡': 'Ç',  'Ã‹': 'Ë',  'Ã': 'Ï',
            # Caractères spéciaux
            'â€™': "'", 'â€œ': '"', 'â€': '"', 'â€"': '–', 'â€"': '—',
            'â€¦': '…', 'â€¢': '•', 'Â°': '°', 'Â«': '«', 'Â»': '»',
            'â€': '€', 'â„¢': '™', 'Â®': '®', 'Â©': '©',
            # Emojis corrompus (PHASE 2)
            'ðŸ'¤': '👤', 'ðŸ"‹': '📋', 'ðŸ"§': '🔧', 'ðŸ'¼': '💼', 
            'ðŸŽ"': '🎓', 'ðŸ"ž': '📞', 'ðŸ"§': '📧', 'ðŸ"—': '🔗',
            'ðŸ'¡': '💡', 'ðŸ"Š': '📊', 'ðŸŽ¯': '🎯', 'ðŸ"ˆ': '📈',
            'ðŸ ': '🏠', 'ðŸ"': '📁', 'ðŸ"‚': '📂', 'ðŸ"™': '📙',
            'ðŸ"'': '🔒', 'ðŸ›¡ï¸': '🛡️', 'ðŸš«': '🚫',
            # Caractères de contrôle emoji corrompus
            'âš™ï¸': '⚙️', 'âœ…': '✅', 'âŒ': '❌', 'âš ï¸': '⚠️',
            'ðŸ–¥ï¸': '🖥️', 'ðŸ"': '🔍', 'âš–ï¸': '⚖️',
        }
        
        # Patterns regex pour détecter mojibake
        self.mojibake_regex = re.compile('|'.join(re.escape(k) for k in self.mojibake_patterns.keys()))
        
        # Caractères de contrôle problématiques
        self.control_chars = re.compile(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]')
        
        # Extensions à scanner
        self.extensions = {'.py', '.json', '.yaml', '.yml', '.txt', '.md'}
        
        # Dossiers à ignorer
        self.ignore_dirs = {
            '__pycache__', '.git', 'node_modules', '.hf_cache', 'models',
            'datasets', 'cache', 'logs', 'temp_uploads', 'cvmatch_env'
        }
        
    def scan_file(self, file_path: Path) -> Dict:
        """Scanne un fichier pour détecter les problèmes d'encodage."""
        result = {
            'file': str(file_path.relative_to(self.project_root)),
            'mojibake_issues': [],
            'control_char_issues': [],
            'encoding_issues': [],
            'bom_detected': False
        }
        
        try:
            # Détecter BOM
            with open(file_path, 'rb') as f:
                raw_content = f.read()
                if raw_content.startswith(b'\xef\xbb\xbf'):
                    result['bom_detected'] = True
            
            # Lire le contenu
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except UnicodeDecodeError as e:
                result['encoding_issues'].append(f"UTF-8 decode error: {e}")
                # Essayer d'autres encodages
                for encoding in ['latin-1', 'cp1252', 'iso-8859-1']:
                    try:
                        with open(file_path, 'r', encoding=encoding) as f:
                            content = f.read()
                        result['encoding_issues'].append(f"Successfully read with {encoding}")
                        break
                    except:
                        continue
                else:
                    return result
            
            # Détecter mojibake
            for line_num, line in enumerate(content.splitlines(), 1):
                # Mojibake patterns
                for match in self.mojibake_regex.finditer(line):
                    mojibake_char = match.group()
                    correct_char = self.mojibake_patterns[mojibake_char]
                    result['mojibake_issues'].append({
                        'line': line_num,
                        'column': match.start(),
                        'mojibake': mojibake_char,
                        'correct': correct_char,
                        'context': line.strip()[:100]
                    })
                
                # Caractères de contrôle
                for match in self.control_chars.finditer(line):
                    result['control_char_issues'].append({
                        'line': line_num,
                        'column': match.start(),
                        'char_code': ord(match.group()),
                        'context': line.strip()[:100]
                    })
        
        except Exception as e:
            result['encoding_issues'].append(f"Error reading file: {e}")
        
        return result
    
    def scan_project(self) -> Dict:
        """Scanne tout le projet."""
        results = {
            'summary': {
                'total_files_scanned': 0,
                'files_with_issues': 0,
                'total_mojibake_issues': 0,
                'total_control_char_issues': 0,
                'total_encoding_issues': 0,
                'files_with_bom': 0
            },
            'files': []
        }
        
        # Scanner tous les fichiers
        for file_path in self.project_root.rglob('*'):
            if (file_path.is_file() and 
                file_path.suffix in self.extensions and
                not any(ignore_dir in file_path.parts for ignore_dir in self.ignore_dirs)):
                
                results['summary']['total_files_scanned'] += 1
                file_result = self.scan_file(file_path)
                
                # Compter les issues
                has_issues = False
                if file_result['mojibake_issues']:
                    results['summary']['total_mojibake_issues'] += len(file_result['mojibake_issues'])
                    has_issues = True
                
                if file_result['control_char_issues']:
                    results['summary']['total_control_char_issues'] += len(file_result['control_char_issues'])
                    has_issues = True
                
                if file_result['encoding_issues']:
                    results['summary']['total_encoding_issues'] += len(file_result['encoding_issues'])
                    has_issues = True
                
                if file_result['bom_detected']:
                    results['summary']['files_with_bom'] += 1
                    has_issues = True
                
                if has_issues:
                    results['summary']['files_with_issues'] += 1
                    results['files'].append(file_result)
        
        return results
    
    def generate_report(self, results: Dict) -> str:
        """Génère un rapport lisible."""
        report = []
        report.append("=" * 80)
        report.append("AUDIT MOJIBAKE - PROJET CVMATCH")
        report.append("=" * 80)
        
        summary = results['summary']
        report.append(f"\n[RESUME]:")
        report.append(f"   Fichiers scannes: {summary['total_files_scanned']}")
        report.append(f"   Fichiers avec problemes: {summary['files_with_issues']}")
        report.append(f"   Issues mojibake: {summary['total_mojibake_issues']}")
        report.append(f"   Issues caracteres de controle: {summary['total_control_char_issues']}")
        report.append(f"   Issues d'encodage: {summary['total_encoding_issues']}")
        report.append(f"   Fichiers avec BOM: {summary['files_with_bom']}")
        
        if results['files']:
            report.append(f"\n[DETAILS PAR FICHIER]:")
            
            for file_result in sorted(results['files'], key=lambda x: len(x['mojibake_issues']), reverse=True):
                file_path = file_result['file']
                report.append(f"\n[FILE] {file_path}")
                
                if file_result['bom_detected']:
                    report.append(f"   [WARN] BOM detecte")
                
                if file_result['encoding_issues']:
                    for issue in file_result['encoding_issues']:
                        report.append(f"   [ERROR] Encodage: {issue}")
                
                if file_result['mojibake_issues']:
                    report.append(f"   [MOJIBAKE] {len(file_result['mojibake_issues'])} issues:")
                    for issue in file_result['mojibake_issues'][:5]:  # Limiter à 5 par fichier
                        report.append(f"      L{issue['line']:3d}: '{issue['mojibake']}' -> '{issue['correct']}'")
                        if len(issue['context']) > 50:
                            context = issue['context'][:47] + "..."
                        else:
                            context = issue['context']
                        report.append(f"            {context}")
                    
                    if len(file_result['mojibake_issues']) > 5:
                        report.append(f"      ... et {len(file_result['mojibake_issues']) - 5} autres")
                
                if file_result['control_char_issues']:
                    report.append(f"   [CONTROL] Caracteres de controle ({len(file_result['control_char_issues'])} issues)")
        
        # Recommandations
        report.append(f"\n[RECOMMANDATIONS]:")
        if summary['files_with_bom'] > 0:
            report.append(f"   - Supprimer les BOM de {summary['files_with_bom']} fichiers")
        if summary['total_mojibake_issues'] > 0:
            report.append(f"   - Corriger {summary['total_mojibake_issues']} caracteres mojibake")
        if summary['total_control_char_issues'] > 0:
            report.append(f"   - Nettoyer {summary['total_control_char_issues']} caracteres de controle")
        
        report.append(f"\n[OK] Utilisez les scripts de correction automatisee apres validation.")
        
        return '\n'.join(report)

def main():
    """Point d'entrée principal."""
    project_root = Path(__file__).parent.parent
    auditor = MojibakeAuditor(str(project_root))
    
    print("[SCAN] Analyse des problemes d'encodage en cours...")
    results = auditor.scan_project()
    
    # Générer le rapport
    report = auditor.generate_report(results)
    try:
        print(report)
    except UnicodeEncodeError:
        # Fallback pour Windows console
        print("[INFO] Rapport genere mais probleme d'affichage console Windows")
        print(f"[INFO] {results['summary']['total_files_scanned']} fichiers scannes")
        print(f"[INFO] {results['summary']['files_with_issues']} fichiers avec problemes")
        print(f"[INFO] {results['summary']['total_mojibake_issues']} issues mojibake detectees")
    
    # Sauvegarder les résultats JSON pour traitement automatique
    output_file = project_root / "scripts" / "mojibake_audit_results.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"\n[SAVE] Resultats sauvegardes: {output_file}")
    
    return results['summary']['files_with_issues']

if __name__ == "__main__":
    exit_code = main()
    exit(min(exit_code, 1))  # Exit avec code 1 si des problèmes trouvés