#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test du système de fallback emoji
=================================

Script rapide pour tester si le système de fallback emoji fonctionne correctement.
"""

import sys
from pathlib import Path

# Ajouter le chemin racine
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_emoji_fallbacks():
    """Teste les fallbacks emoji."""
    try:
        from app.utils.emoji_utils import get_display_text, safe_emoji, force_ascii_mode
        
        print("=" * 50)
        print("TEST DU SYSTEME DE FALLBACK EMOJI")
        print("=" * 50)
        
        # Test des emojis critiques AVANT force ASCII
        print("\n1. AVANT force ASCII mode:")
        print("   Star:", repr(get_display_text("⭐")))
        print("   Search:", repr(get_display_text("🔍")))
        print("   Save:", repr(get_display_text("💾")))
        print("   Link:", repr(get_display_text("🔗")))
        
        # Activer le mode force ASCII
        print("\n2. Activation du mode force ASCII...")
        force_ascii_mode()
        
        # Test des emojis critiques APRES force ASCII
        print("\n3. APRES force ASCII mode:")
        print("   Star:", repr(get_display_text("⭐")))
        print("   Search:", repr(get_display_text("🔍")))  
        print("   Save:", repr(get_display_text("💾")))
        print("   Link:", repr(get_display_text("🔗")))
        
        # Test du texte complet comme dans l'application
        print("\n4. TEST SIMULATION INTERFACE:")
        rating = 4.2
        stats_text = f"Note moyenne: {rating:.1f}" + get_display_text("⭐")
        print("   Stats display:", repr(stats_text))
        
        button_text = get_display_text("🔍 Extraire le CV")
        print("   Button text:", repr(button_text))
        
        linkedin_button = get_display_text("🔗 Synchro LinkedIn")
        print("   LinkedIn button:", repr(linkedin_button))
        
        print("\n" + "=" * 50)
        print("RESULTAT: Si vous voyez [*], [Search], [Save], [Link]")
        print("alors le système de fallback fonctionne correctement!")
        print("=" * 50)
        
        return True
        
    except Exception as e:
        print(f"ERREUR: {e}")
        return False

def main():
    """Fonction principale."""
    print("Test du système de fallback emoji CVMatch")
    
    success = test_emoji_fallbacks()
    
    if success:
        print("\n✓ Test terminé avec succès")
        return 0
    else:
        print("\n✗ Test échoué")
        return 1

if __name__ == "__main__":
    sys.exit(main())