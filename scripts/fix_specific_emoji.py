#!/usr/bin/env python3
"""
Script spécifique pour corriger l'emoji dans main_window.py
"""

def fix_cover_letter_emoji():
    """Corrige spécifiquement l'emoji dans le titre de la lettre de motivation."""
    file_path = "app/views/main_window.py"
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    modified = False
    
    # Recherche et remplacement de la ligne problématique avec plusieurs approches
    import re
    
    # Approche 1: Recherche par le nom de variable et le pattern QGroupBox
    pattern1 = r'(\s+cover_letter_group\s*=\s*QGroupBox\(["\'])([^"\']*📝[^"\']*)(["\']\))'
    if re.search(pattern1, content):
        content = re.sub(pattern1, r'\1get_display_text("\2")\3', content)
        modified = True
        print("Correction appliquée avec le pattern 1")
    
    # Approche 2: Recherche directe de la chaîne "Lettre de motivation par défaut"
    if "cover_letter_group = QGroupBox(" in content and "Lettre de motivation par défaut" in content:
        # Recherche ligne par ligne pour plus de précision
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if "cover_letter_group = QGroupBox(" in line and "Lettre de motivation par défaut" in line:
                if "get_display_text(" not in line:  # Ne pas modifier si déjà corrigé
                    # Remplacer QGroupBox("...") par QGroupBox(get_display_text("..."))
                    lines[i] = re.sub(
                        r'QGroupBox\("([^"]*)"',
                        r'QGroupBox(get_display_text("\1")',
                        line
                    )
                    modified = True
                    print(f"Ligne {i+1} modifiée: {lines[i].strip()}")
        
        if modified:
            content = '\n'.join(lines)
    
    if modified:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print("Fichier modifié avec succès!")
        return True
    else:
        print("Aucune modification nécessaire")
        return False

if __name__ == "__main__":
    print("=== CORRECTION EMOJI LETTRE DE MOTIVATION ===")
    fix_cover_letter_emoji()
    print("Terminé!")