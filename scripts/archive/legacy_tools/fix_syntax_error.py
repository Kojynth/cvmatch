#!/usr/bin/env python3
"""
Script pour corriger l'erreur de syntaxe dans main_window.py
"""

def fix_syntax_error():
    """Corrige l'erreur de guillemets en trop."""
    file_path = "app/views/main_window.py"
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Corriger le problème de double guillemets
    original = content
    content = content.replace(
        'QGroupBox("get_display_text("📝 Lettre de motivation par défaut")")',
        'QGroupBox(get_display_text("📝 Lettre de motivation par défaut"))'
    )
    
    if content != original:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print("Erreur de syntaxe corrigée!")
        return True
    else:
        print("Aucune correction nécessaire")
        return False

if __name__ == "__main__":
    print("=== CORRECTION ERREUR DE SYNTAXE ===")
    fix_syntax_error()
    print("Terminé!")