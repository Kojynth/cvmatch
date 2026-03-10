#!/usr/bin/env python3
# Script de correction finale des emojis
import os
import re

def fix_main_window():
    """Corrige main_window.py avec toutes les corrections manquées."""
    file_path = "app/views/main_window.py"
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    
    # Corrections de navigation (ligne 177)
    content = content.replace('("⚙️", "Paramètres", "settings")', '(safe_emoji("⚙️", "[S]"), "Paramètres", "settings")')
    
    # Corrections statistiques (ligne 200)  
    content = content.replace('QLabel("📊 Statistiques")', 'QLabel(get_display_text("📊 Statistiques"))')
    
    # Corrections boutons (lignes 2681, 3415)
    content = content.replace('QPushButton("⚙️")', 'QPushButton(safe_emoji("⚙️", "[S]"))')
    content = content.replace('QLabel("⚙️ Paramètres")', 'QLabel(get_display_text("⚙️ Paramètres"))')
    
    if content != original_content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False

def fix_extracted_data_viewer():
    """Corrige extracted_data_viewer.py."""
    file_path = "app/views/extracted_data_viewer.py"
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    
    # Ajouter import si manquant
    if 'from ..utils.emoji_utils import' not in content:
        import_line = 'from loguru import logger'
        content = content.replace(import_line, import_line + '\nfrom ..utils.emoji_utils import get_display_text, safe_emoji')
    
    # Corrections spécifiques
    corrections = [
        ('setText("👤")', 'setText(safe_emoji("👤", "[P]"))'),
        ('"📋 Vue structurée"', 'get_display_text("📋 Vue structurée")'),
        ('"📊 Analyse qualité"', 'get_display_text("📊 Analyse qualité")'),
        ('"📊 Vue structurée"', 'get_display_text("📊 Vue structurée")'),
        ('"📊 Qualité"', 'get_display_text("📊 Qualité")'),
    ]
    
    for old, new in corrections:
        content = content.replace(old, new)
    
    if content != original_content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False

def fix_section_header():
    """Corrige section_header.py."""
    file_path = "app/widgets/section_header.py"
    
    if not os.path.exists(file_path):
        return False
        
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    
    # Ajouter import si manquant
    if 'from ..utils.emoji_utils import' not in content:
        # Trouver une ligne d'import appropriée
        if 'from PySide6' in content:
            pattern = r'(from PySide6[^\n]+\n)'
            content = re.sub(pattern, r'\1from ..utils.emoji_utils import safe_emoji\n', content, count=1)
    
    # Corriger le paramètre par défaut
    content = content.replace('icon: str = "📋"', 'icon: str = safe_emoji("📋", "[N]")')
    
    if content != original_content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False

if __name__ == "__main__":
    print("=== CORRECTION FINALE DES EMOJIS ===")
    
    results = []
    
    print("1. Correction main_window.py...")
    results.append(("main_window.py", fix_main_window()))
    
    print("2. Correction extracted_data_viewer.py...")
    results.append(("extracted_data_viewer.py", fix_extracted_data_viewer()))
    
    print("3. Correction section_header.py...")
    results.append(("section_header.py", fix_section_header()))
    
    print("\n=== RÉSULTATS ===")
    for filename, changed in results:
        status = "MODIFIÉ" if changed else "INCHANGÉ"
        print(f"{filename}: {status}")
    
    print("\nCorrections terminées!")