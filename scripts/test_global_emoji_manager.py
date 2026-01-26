#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test de l'instance globale emoji manager
=======================================

Vérifie l'état de l'instance globale utilisée par get_display_text().
"""

import sys
from pathlib import Path

# Ajouter le chemin racine
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_global_emoji_manager():
    """Teste l'instance globale de emoji manager."""
    try:
        from app.utils.emoji_utils import emoji_manager, get_display_text
        
        print("=" * 50)
        print("TEST INSTANCE GLOBALE EMOJI MANAGER")
        print("=" * 50)
        
        print(f"Force ASCII mode global: {emoji_manager.force_ascii_mode}")
        print(f"Emoji supported cached: {emoji_manager.emoji_supported}")
        
        # Tester la détection sur l'instance globale
        is_supported = emoji_manager.is_emoji_supported()
        print(f"Detection sur instance globale: {'SUPPORTÉ' if is_supported else 'FALLBACK'}")
        
        # Tester get_display_text directement
        test_cases = [
            "👤",
            "👤 Profil", 
            "⚙️",
            "⚙️ Paramètres"
        ]
        
        print(f"\nTest get_display_text:")
        print("-" * 30)
        for test in test_cases:
            result = get_display_text(test)
            is_fallback = result != test
            print(f"'{test}' -> '{result}' {'[FALLBACK]' if is_fallback else '[EMOJI]'}")
        
        return True
        
    except Exception as e:
        print(f"ERREUR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_global_emoji_manager()
    sys.exit(0 if success else 1)