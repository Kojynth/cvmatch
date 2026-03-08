#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de correction des emojis corrompus - Phase 2
"""

import shutil
from pathlib import Path
from typing import Dict

class EmojiCorruptionFixer:
    """Correcteur pour les emojis corrompus."""
    
    def __init__(self):
        # Mapping des corrections d'emojis : pattern corrompu -> code Unicode correct
        self.emoji_fixes = {
            # Pattern détectés dans l'audit - on utilise des approximations safe
            # Navigation
            'ðŸ'¤': r'\U0001F464',  # 👤 Profil
            'ðŸ"‹': r'\U0001F4CB',  # 📋 Presse-papier
            'ðŸ"§': r'\U0001F527',  # 🔧 Outils  
            'ðŸ'¼': r'\U0001F4BC',  # 💼 Business
            'ðŸŽ"': r'\U0001F393',  # 🎓 Education
            
            # Communication
            'ðŸ"ž': r'\U0001F4DE',  # 📞 Téléphone
            'ðŸ"§': r'\U0001F4E7',  # 📧 Email
            'ðŸ"—': r'\U0001F517',  # 🔗 Lien
            
            # Analyse
            'ðŸ'¡': r'\U0001F4A1',  # 💡 Idée
            'ðŸ"Š': r'\U0001F4CA',  # 📊 Graphique
            'ðŸŽ¯': r'\U0001F3AF',  # 🎯 Cible
            'ðŸ"ˆ': r'\U0001F4C8',  # 📈 Tendance
            
            # Fichiers
            'ðŸ ': r'\U0001F3E0',   # 🏠 Maison
            'ðŸ"': r'\U0001F4C1',   # 📁 Dossier
            'ðŸ"‚': r'\U0001F4C2',   # 📂 Dossier ouvert
            'ðŸ"™': r'\U0001F4D9',   # 📙 Livre
            
            # Sécurité
            'ðŸ"'': r'\U0001F512',   # 🔒 Cadenas
            'ðŸš«': r'\U0001F6AB',   # 🚫 Interdit
            
            # États et contrôles (patterns complexes)
            'âœ…': r'\u2705',        # ✅ Check
            'âŒ': r'\u274C',         # ❌ Croix
            'âš ': r'\u26A0',         # ⚠ Warning (sans ️)
            'âš™': r'\u2699',         # ⚙ Paramètres (sans ️)
            'âš–': r'\u2696',         # ⚖ Balance (sans ️)
            'ðŸ–¥': r'\U0001F5A5',   # 🖥 Desktop (sans ️)
            'ðŸ"': r'\U0001F50D',    # 🔍 Loupe
        }
        
        # Patterns avec suffixes ï¸ à nettoyer
        self.control_suffix_fixes = {
            'âš™ï¸': r'\u2699\uFE0F',  # ⚙️ Paramètres complet
            'âš ï¸': r'\u26A0\uFE0F',  # ⚠️ Warning complet
            'âš–ï¸': r'\u2696\uFE0F',  # ⚖️ Balance complète
            'ðŸ›¡ï¸': r'\U0001F6E1\uFE0F',  # 🛡️ Bouclier
            'ðŸ–¥ï¸': r'\U0001F5A5\uFE0F',  # 🖥️ Desktop
        }
    
    def fix_file(self, file_path: Path, backup: bool = True) -> Dict:
        """Corrige un fichier et retourne les stats."""
        result = {
            'file': str(file_path),
            'corrections': 0,
            'error': None
        }
        
        try:
            if backup:
                backup_path = file_path.with_suffix(file_path.suffix + '.emoji_bak')
                shutil.copy2(file_path, backup_path)
            
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            original_content = content
            
            # Appliquer les corrections d'emojis
            for corrupt, correct in self.emoji_fixes.items():
                if corrupt in content:
                    count = content.count(corrupt)
                    content = content.replace(corrupt, correct)
                    result['corrections'] += count
                    print(f"[FIX] {file_path.name}: {count}x '{corrupt}' -> Unicode")
            
            # Appliquer les corrections de suffixes de contrôle
            for corrupt, correct in self.control_suffix_fixes.items():
                if corrupt in content:
                    count = content.count(corrupt)
                    content = content.replace(corrupt, correct)
                    result['corrections'] += count
                    print(f"[FIX] {file_path.name}: {count}x '{corrupt}' -> Unicode+Suffix")
            
            # Sauvegarder si changements
            if content != original_content:
                with open(file_path, 'w', encoding='utf-8', newline='\n') as f:
                    f.write(content)
                print(f"[SAVE] {file_path.name}: {result['corrections']} corrections appliquees")
            
        except Exception as e:
            result['error'] = str(e)
            print(f"[ERROR] {file_path}: {e}")
        
        return result
    
    def fix_priority_files(self) -> Dict:
        """Corrige les fichiers prioritaires."""
        project_root = Path(__file__).parent.parent
        
        priority_files = [
            project_root / 'app' / 'utils' / 'emoji_utils_old.py',
            project_root / 'app' / 'utils' / 'ui_text.py',
            project_root / 'app' / 'views' / 'main_window.py',
        ]
        
        results = []
        total_corrections = 0
        
        print("[EMOJI FIX] Debut correction des emojis corrompus...")
        
        for file_path in priority_files:
            if file_path.exists():
                result = self.fix_file(file_path)
                results.append(result)
                total_corrections += result['corrections']
            else:
                print(f"[SKIP] {file_path.name}: fichier non trouve")
        
        print(f"\n[SUMMARY] {total_corrections} corrections appliquees")
        return {
            'files': results,
            'total_corrections': total_corrections
        }

def main():
    """Point d'entrée principal."""
    fixer = EmojiCorruptionFixer()
    results = fixer.fix_priority_files()
    
    if results['total_corrections'] > 0:
        print(f"\n[SUCCESS] {results['total_corrections']} emojis corriges")
        return 0
    else:
        print(f"\n[INFO] Aucune correction necessaire")
        return 0

if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)