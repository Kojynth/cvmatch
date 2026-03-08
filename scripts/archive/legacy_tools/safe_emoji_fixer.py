#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Correcteur sécurisé pour les emojis corrompus - utilise des patterns bytes
"""

import shutil
from pathlib import Path

def fix_emoji_utils_old():
    """Corrige spécifiquement emoji_utils_old.py"""
    file_path = Path(__file__).parent.parent / 'app' / 'utils' / 'emoji_utils_old.py'
    
    if not file_path.exists():
        print(f"[SKIP] {file_path} non trouvé")
        return False
    
    print(f"[FIX] Correction de {file_path.name}...")
    
    # Backup
    backup_path = file_path.with_suffix('.py.emoji_backup')
    shutil.copy2(file_path, backup_path)
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Corrections spécifiques basées sur l'audit
        corrections = [
            # Remplacer les patterns corrompus par des codes Unicode corrects
            ('ðŸ', '\\U0001F4'),  # Début générique des emojis
            ('âš™ï¸', '\\u2699\\uFE0F'),  # ⚙️
            ('âœ…', '\\u2705'),          # ✅  
            ('âŒ', '\\u274C'),           # ❌
            ('âš ï¸', '\\u26A0\\uFE0F'), # ⚠️
            ('âš–ï¸', '\\u2696\\uFE0F'), # ⚖️
        ]
        
        total_corrections = 0
        for old, new in corrections:
            if old in content:
                count = content.count(old)
                content = content.replace(old, new)
                total_corrections += count
                print(f"  {count}x '{old}' -> Unicode")
        
        # Corrections spécifiques pour les mappings d'emojis
        specific_fixes = [
            ('"ðŸ'¤": "[P]"', '"\U0001F464": "[P]"'),  # 👤
            ('"ðŸ"‹": "[N]"', '"\U0001F4CB": "[N]"'),  # 📋  
            ('"ðŸ"§": "[T]"', '"\U0001F527": "[T]"'),  # 🔧
            ('"ðŸ'¼": "[W]"', '"\U0001F4BC": "[W]"'),  # 💼
            ('"ðŸŽ"": "[E]"', '"\U0001F393": "[E]"'),  # 🎓
        ]
        
        for old, new in specific_fixes:
            if old in content:
                content = content.replace(old, new)
                total_corrections += 1
                print(f"  1x emoji mapping corrigé")
        
        with open(file_path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(content)
        
        print(f"[SUCCESS] {total_corrections} corrections appliquées dans {file_path.name}")
        return True
        
    except Exception as e:
        print(f"[ERROR] {file_path.name}: {e}")
        # Restaurer le backup en cas d'erreur
        shutil.copy2(backup_path, file_path)
        return False

def fix_main_window():
    """Corrige spécifiquement main_window.py"""
    file_path = Path(__file__).parent.parent / 'app' / 'views' / 'main_window.py'
    
    if not file_path.exists():
        print(f"[SKIP] {file_path} non trouvé")
        return False
    
    print(f"[FIX] Correction de {file_path.name}...")
    
    # Backup
    backup_path = file_path.with_suffix('.py.emoji_backup')
    shutil.copy2(file_path, backup_path)
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Stratégie: remplacer les patterns les plus courants
        corrections = [
            # Emojis dans les labels et textes UI
            ('👤', '\\U0001F464'),  # Profil - utiliser le bon caractère
            ('📊', '\\U0001F4CA'),  # Stats
            ('🔧', '\\U0001F527'),  # Paramètres  
            ('📋', '\\U0001F4CB'),  # Presse-papier
            ('💼', '\\U0001F4BC'),  # Business
            ('🎓', '\\U0001F393'),  # Education
            ('📞', '\\U0001F4DE'),  # Téléphone
            ('📧', '\\U0001F4E7'),  # Email
            ('🔗', '\\U0001F517'),  # Lien
        ]
        
        total_corrections = 0
        for old, new in corrections:
            if old in content:
                count = content.count(old)
                content = content.replace(old, new)
                total_corrections += count
                print(f"  {count}x emoji UI corrigé")
        
        with open(file_path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(content)
        
        print(f"[SUCCESS] {total_corrections} corrections appliquées dans {file_path.name}")
        return True
        
    except Exception as e:
        print(f"[ERROR] {file_path.name}: {e}")
        shutil.copy2(backup_path, file_path)
        return False

def fix_ui_text():
    """Corrige spécifiquement ui_text.py"""
    file_path = Path(__file__).parent.parent / 'app' / 'utils' / 'ui_text.py'
    
    if not file_path.exists():
        print(f"[SKIP] {file_path} non trouvé")
        return False
    
    print(f"[FIX] Correction de {file_path.name}...")
    
    # Backup
    backup_path = file_path.with_suffix('.py.emoji_backup')
    shutil.copy2(file_path, backup_path)
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Nettoyage des caractères de contrôle corrompus
        corrections = [
            ('âš™ï¸', '\\u2699\\uFE0F'),
            ('âœ…', '\\u2705'),
            ('âŒ', '\\u274C'),
            ('âš ï¸', '\\u26A0\\uFE0F'),
        ]
        
        total_corrections = 0
        for old, new in corrections:
            if old in content:
                count = content.count(old)
                content = content.replace(old, new)  
                total_corrections += count
                print(f"  {count}x caractère contrôle corrigé")
        
        with open(file_path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(content)
        
        print(f"[SUCCESS] {total_corrections} corrections appliquées dans {file_path.name}")
        return True
        
    except Exception as e:
        print(f"[ERROR] {file_path.name}: {e}")
        shutil.copy2(backup_path, file_path)
        return False

def main():
    """Point d'entrée principal."""
    print("[SAFE EMOJI FIX] Debut des corrections...")
    
    results = []
    results.append(fix_emoji_utils_old())
    results.append(fix_main_window()) 
    results.append(fix_ui_text())
    
    success_count = sum(1 for r in results if r)
    total_count = len(results)
    
    print(f"\n[SUMMARY] {success_count}/{total_count} fichiers corriges avec succes")
    
    return 0 if success_count == total_count else 1

if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)