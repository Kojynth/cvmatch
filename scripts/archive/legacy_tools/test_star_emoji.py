#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test spécifique de l'emoji étoile
=================================

Teste que l'emoji étoile s'affiche correctement au lieu de carrés blancs.
"""

import sys
from pathlib import Path

# Ajouter le chemin racine
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_star_emoji():
    """Teste spécifiquement l'emoji étoile."""
    try:
        from app.utils.emoji_utils import get_display_text, emoji_manager
        
        print("=" * 50)
        print("TEST EMOJI ETOILE - CVMatch")
        print("=" * 50)
        
        print(f"Cache emoji_supported: {emoji_manager.emoji_supported}")
        print(f"Force ASCII mode: {emoji_manager.force_ascii_mode}")
        
        # Test de l'étoile spécifiquement
        star_emoji = "⭐"
        star_result = get_display_text(star_emoji)
        
        print(f"\nTest etoile:")
        print(f"  Input:  '{star_emoji}' (U+2B50)")
        print(f"  Output: '{star_result}'")
        
        if star_result == star_emoji:
            print("  Status: EMOJI AFFICHE CORRECTEMENT")
            success = True
        elif star_result == "[*]":
            print("  Status: FALLBACK ASCII (pas de carre blanc)")
            success = True  # C'est OK, pas de carré blanc
        else:
            print(f"  Status: PROBLEME - sortie inattendue: {repr(star_result)}")
            success = False
        
        # Test du texte complet comme dans l'app
        rating = 4.5
        full_text = f"Note moyenne: {rating:.1f}{get_display_text('⭐')}"
        print(f"\nTest texte complet:")
        print(f"  Texte: '{full_text}'")
        
        # Vérifier qu'il n'y a pas de carré blanc (unicode \uFFFD ou ?)
        if "□" in full_text or "�" in full_text or "\uFFFD" in full_text:
            print("  Status: ERREUR - carres blancs detectes!")
            success = False
        else:
            print("  Status: OK - pas de carres blancs")
        
        return success
        
    except Exception as e:
        print(f"ERREUR: {e}")
        return False

if __name__ == "__main__":
    success = test_star_emoji()
    print(f"\nTest {'REUSSI' if success else 'ECHEC'}")
    sys.exit(0 if success else 1)