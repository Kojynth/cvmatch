#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test simple de la détection d'emojis
===================================

Script pour vérifier si les emojis s'affichent correctement ou en fallback.
"""

import sys
from pathlib import Path

# Ajouter le chemin racine
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_emoji_display():
    """Teste l'affichage des emojis principaux."""
    try:
        from app.utils.emoji_utils import get_display_text
        
        print("=" * 50)
        print("TEST DETECTION EMOJI - CVMatch")
        print("=" * 50)
        
        # Test des emojis principaux de l'interface
        emojis_test = [
            ("👤", "Profil"),
            ("⚙️", "Parametres"),
            ("📝", "Nouvelle candidature"),
            ("📜", "Historique"),
            ("📂", "Parcourir"),
            ("📋", "Coller"),
            ("💾", "Sauvegarder"),
            ("🔗", "Lien LinkedIn"),
            ("🔄", "Reinitialiser"),
            ("⭐", "Etoile note"),
        ]
        
        print("\nResultats de detection :")
        print("-" * 30)
        
        for emoji, description in emojis_test:
            result = get_display_text(emoji)
            status = "EMOJI" if result == emoji else "FALLBACK"
            print(f"{description:20} : {result:10} [{status}]")
        
        # Test text complet
        print(f"\nTest texte complet :")
        profile_text = get_display_text("👤 Profil")
        settings_text = get_display_text("⚙️ Paramètres")
        print(f"Profile : '{profile_text}'")
        print(f"Settings: '{settings_text}'")
        
        return True
        
    except Exception as e:
        print(f"ERREUR: {e}")
        return False

if __name__ == "__main__":
    success = test_emoji_display()
    print(f"\nTest {'REUSSI' if success else 'ECHEC'}")
    sys.exit(0 if success else 1)