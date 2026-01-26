#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script simple pour corriger les problèmes mojibake dans main_window.py
Utilise uniquement des chaînes de caractères sûres.
"""

import shutil
from pathlib import Path

def fix_main_window_simple():
    """Corrige les problèmes mojibake dans main_window.py de manière sécurisée."""
    project_root = Path(__file__).parent.parent
    main_window_path = project_root / "app" / "views" / "main_window.py"
    
    if not main_window_path.exists():
        print("[ERROR] Fichier main_window.py non trouve")
        return False
    
    # Backup du fichier original
    backup_path = main_window_path.with_suffix('.py.simple_backup')
    shutil.copy2(main_window_path, backup_path)
    print(f"[BACKUP] Sauvegarde creee: {backup_path.name}")
    
    try:
        # Lire le fichier
        with open(main_window_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        corrections_made = 0
        
        # Liste des corrections à appliquer (patterns sûrs uniquement)
        replacements = [
            # Accents français corrompus les plus fréquents
            ('Ã©', 'é'),
            ('Ã¨', 'è'), 
            ('Ã ', 'à'),
            ('Ãª', 'ê'),
            ('Ã¢', 'â'),
            ('Ã´', 'ô'),
            ('Ã®', 'î'),
            ('Ã¯', 'ï'),
            ('Ã§', 'ç'),
            ('Ã¹', 'ù'),
            ('Ã»', 'û'),
            ('Ã‰', 'É'),
            ('Ã€', 'À'),
            ('ÃŠ', 'Ê'),
            ('ÃŽ', 'Î'),
            
            # Mots corrompus spécifiques trouvés dans le fichier
            ('refactorisÃ©e', 'refactorisée'),
            ('sÃ©curisÃ©', 'sécurisé'),
            ('systÃ¨me', 'système'),
            ('zÃ©ro', 'zéro'),
            ('personnalisÃ©', 'personnalisé'),
            ('premiÃ¨re', 'première'),
            ('gÃ©nÃ©rÃ©s', 'générés'),
            ('modÃ¨le', 'modèle'),
            ('sÃ©lectionner', 'sélectionner'),
            ('tÃ©lÃ©phone', 'téléphone'),
            ('donnÃ©es', 'données'),
            ('rÃ©fÃ©rence', 'référence'),
            ('dÃ©tails', 'détails'),
            ('prÃ©fÃ©rences', 'préférences'),
            ('caractÃ¨res', 'caractères'),
            ('succÃ¨s', 'succès'),
            ('crÃ©ation', 'création'),
            ('opÃ©ration', 'opération'),
            ('mÃ©thode', 'méthode'),
            ('arriÃ¨re-plan', 'arrière-plan'),
            
            # Caractères spéciaux simples
            ('â€™', "'"),  # Apostrophe courbe
            ('â€œ', '"'),  # Guillemet ouvrant
            ('â€', '"'),   # Guillemet fermant
            ('â€¢', '•'),  # Puce
            
            # Emojis - remplacer par codes Unicode échappés
            ('👤', '\\U0001F464'),  # User profile
            ('📋', '\\U0001F4CB'),  # Clipboard
            ('📙', '\\U0001F4D9'),  # Orange book
            ('⚙️', '\\u2699\\uFE0F'),  # Gear
            ('📊', '\\U0001F4CA'),  # Bar chart
            ('🔍', '\\U0001F50D'),  # Magnifying glass
            ('🔎', '\\U0001F50E'),  # Magnifying glass tilted right
            ('👁️', '\\U0001F441\\uFE0F'),  # Eye
            ('📄', '\\U0001F4C4'),  # Page facing up
            ('🔗', '\\U0001F517'),  # Link
            ('⚠️', '\\u26A0\\uFE0F'),  # Warning
            ('✅', '\\u2705'),        # Check mark
            ('🔄', '\\U0001F504'),    # Anticlockwise arrows
            ('💾', '\\U0001F4BE'),    # Floppy disk
            ('📞', '\\U0001F4DE'),    # Telephone receiver
            ('💼', '\\U0001F4BC'),    # Briefcase
            ('🎓', '\\U0001F393'),    # Graduation cap
            ('ℹ️', '\\u2139\\uFE0F'),  # Information
        ]
        
        # Appliquer toutes les corrections
        for old, new in replacements:
            if old in content:
                count = content.count(old)
                content = content.replace(old, new)
                corrections_made += count
                print(f"[FIX] {count}x '{old}' → '{new}'")
        
        # Sauvegarder si des changements ont été faits
        if content != original_content:
            with open(main_window_path, 'w', encoding='utf-8', newline='\n') as f:
                f.write(content)
            print(f"[SUCCESS] {corrections_made} corrections appliquees dans main_window.py")
        else:
            print("[INFO] Aucune correction necessaire dans main_window.py")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] Erreur lors de la correction: {str(e)}")
        # Restaurer depuis le backup en cas d'erreur
        if backup_path.exists():
            shutil.copy2(backup_path, main_window_path)
            print("[RESTORE] Fichier original restaure depuis la sauvegarde")
        return False

if __name__ == "__main__":
    print("[SIMPLE MOJIBAKE FIX] Correction de main_window.py...")
    success = fix_main_window_simple()
    exit(0 if success else 1)