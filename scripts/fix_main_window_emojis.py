#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Correcteur spécialisé pour main_window.py - émojis corrompus
"""

import shutil
from pathlib import Path

def fix_main_window():
    """Corrige les emojis corrompus dans main_window.py"""
    file_path = Path(__file__).parent.parent / 'app' / 'views' / 'main_window.py'
    
    if not file_path.exists():
        print(f"[SKIP] {file_path} non trouvé")
        return False
    
    print(f"[FIX] Correction des emojis dans {file_path.name}...")
    
    # Backup
    backup_path = file_path.with_suffix('.py.emoji_fix_backup')
    shutil.copy2(file_path, backup_path)
    print(f"[BACKUP] Sauvegarde créée: {backup_path.name}")
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        # Corrections spécifiques pour les emojis détectés
        emoji_corrections = [
            # Profil utilisateur
            ('ðŸ'¤', '\\U0001F464'),  # 👤 Profil
            
            # Stats et analyses
            ('ðŸ"Š', '\\U0001F4CA'),  # 📊 Statistiques
            
            # Actions
            ('ðŸ"Ž', '\\U0001F50E'),  # 🔎 Recherche/Remplacer
            ('ðŸ'ï¸', '\\U0001F441\\uFE0F'),  # 👁️ Voir
            ('ðŸ"', '\\U0001F4C4'),   # 📄 Document
            ('ðŸ"', '\\U0001F517'),   # 🔗 LinkedIn
            
            # États et validations
            ('âœ…', '\\u2705'),      # ✅ Success
            ('âŒ', '\\u274C'),       # ❌ Error
            ('âš ï¸', '\\u26A0\\uFE0F'), # ⚠️ Warning
            ('â„¹ï¸', '\\u2139\\uFE0F'), # ℹ️ Info
            
            # Autres caractères
            ('â­', '\\u2B50'),       # ⭐ Star
            (' €¢ ', ' • '),         # Bullet point corrompu
            ('Ï ', 'à '),            # À corrompu
        ]
        
        total_corrections = 0
        for old, new in emoji_corrections:
            if old in content:
                count = content.count(old)
                content = content.replace(old, new)
                total_corrections += count
                print(f"  {count}x '{old}' -> '{new}'")
        
        # Sauvegarde si changements
        if content != original_content:
            with open(file_path, 'w', encoding='utf-8', newline='\n') as f:
                f.write(content)
            print(f"[SUCCESS] {total_corrections} corrections appliquées dans {file_path.name}")
            return True
        else:
            print(f"[INFO] Aucune correction nécessaire dans {file_path.name}")
            return True
            
    except Exception as e:
        print(f"[ERROR] {file_path.name}: {e}")
        # Restaurer le backup en cas d'erreur
        shutil.copy2(backup_path, file_path)
        return False

def main():
    """Point d'entrée principal."""
    print("[MAIN WINDOW EMOJI FIX] Début des corrections...")
    
    success = fix_main_window()
    
    if success:
        print("\n[SUCCESS] Corrections appliquées avec succès")
        return 0
    else:
        print("\n[ERROR] Échec des corrections")
        return 1

if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)