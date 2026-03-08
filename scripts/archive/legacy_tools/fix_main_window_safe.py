#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Correcteur sécurisé pour main_window.py - utilise des patterns bytes
"""

import shutil
from pathlib import Path

def fix_main_window():
    """Corrige les emojis corrompus dans main_window.py using byte patterns"""
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
        # Lire en mode bytes pour éviter les problèmes d'encodage
        with open(file_path, 'rb') as f:
            content_bytes = f.read()
        
        original_bytes = content_bytes
        
        # Remplacements par patterns bytes - codes UTF-8 corrompus vers codes corrects
        byte_replacements = [
            # Profil utilisateur: ðŸ'¤ -> \U0001F464
            (b'\xc3\xb0\xc5\xb8\xe2\x80\x99\xc2\xa4', b'\\U0001F464'),
            # Stats: ðŸ"Š -> \U0001F4CA  
            (b'\xc3\xb0\xc5\xb8\xe2\x80\x9d\xc5\xa0', b'\\U0001F4CA'),
            # Recherche: ðŸ"Ž -> \U0001F50E
            (b'\xc3\xb0\xc5\xb8\xe2\x80\x9d\xc5\xbd', b'\\U0001F50E'),
            # Voir: ðŸ'ï¸ -> \U0001F441\uFE0F
            (b'\xc3\xb0\xc5\xb8\xe2\x80\x99\xc3\xaf\xc2\xb8', b'\\U0001F441\\uFE0F'),
            # Document: ðŸ" -> \U0001F4C4
            (b'\xc3\xb0\xc5\xb8\xe2\x80\x9d', b'\\U0001F517'),
            # Success: âœ… -> \u2705
            (b'\xc3\xa2\xe2\x82\xac\xc5\xa0', b'\\u2705'),
            # Error: âŒ -> \u274C
            (b'\xc3\xa2\xc5\x92', b'\\u274C'),
            # Warning: âš ï¸ -> \u26A0\uFE0F
            (b'\xc3\xa2\xc5\xa1\xc2\xa0\xc3\xaf\xc2\xb8', b'\\u26A0\\uFE0F'),
            # Info: â„¹ï¸ -> \u2139\uFE0F
            (b'\xc3\xa2\xe2\x84\xa2\xc2\xb9\xc3\xaf\xc2\xb8', b'\\u2139\\uFE0F'),
            # Star: â­ -> \u2B50
            (b'\xc3\xa2\xc2\xad', b'\\u2B50'),
            # Bullet: €¢ -> •
            (b'\xe2\x82\xac\xc2\xa2', b'\xe2\x80\xa2'),
            # À corrompu: Ï  -> à 
            (b'\xc3\x8f\xc2\xa0', b'\xc3\xa0\x20'),
        ]
        
        total_corrections = 0
        for old_bytes, new_bytes in byte_replacements:
            if old_bytes in content_bytes:
                count = content_bytes.count(old_bytes)
                content_bytes = content_bytes.replace(old_bytes, new_bytes)
                total_corrections += count
                print(f"  {count}x pattern bytes corrigé")
        
        # Sauvegarde si changements
        if content_bytes != original_bytes:
            with open(file_path, 'wb') as f:
                f.write(content_bytes)
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
    print("[MAIN WINDOW SAFE FIX] Début des corrections...")
    
    success = fix_main_window()
    
    if success:
        print("\\n[SUCCESS] Corrections appliquées avec succès")
        return 0
    else:
        print("\\n[ERROR] Échec des corrections")
        return 1

if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)