#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Debug de la détection d'emoji Windows
=====================================

Script pour comprendre pourquoi les emojis ne sont pas détectés comme supportés.
"""

import sys
from pathlib import Path

# Ajouter le chemin racine
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def debug_emoji_detection():
    """Debug de la détection d'emoji."""
    try:
        from app.utils.emoji_utils import emoji_manager
        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QFontMetrics, QFont
        
        print("=" * 60)
        print("DEBUG DETECTION EMOJI WINDOWS")
        print("=" * 60)
        
        # Créer app Qt temporaire
        app = QApplication.instance() or QApplication([])
        
        print(f"\nPlateforme: {sys.platform}")
        print(f"Force ASCII mode: {emoji_manager.force_ascii_mode}")
        
        # Tester la configuration de police emoji
        emoji_configured = emoji_manager.configure_emoji_font()
        print(f"Police emoji configurée: {emoji_configured}")
        if emoji_manager.emoji_font:
            print(f"Police utilisée: {emoji_manager.emoji_font.family()}")
        
        # Test direct des emojis avec la police
        font = app.font()
        if emoji_manager.emoji_font:
            font = emoji_manager.emoji_font
            
        metrics = QFontMetrics(font)
        
        # Test des emojis un par un
        test_emojis = ['\U0001F464', '\u2699', '\U0001F4CB', '\U0001F4BC', '\U0001F527', '\U0001F4CA']
        print(f"\nTest des emojis individuels avec police {font.family()}:")
        print("-" * 40)
        
        supported_count = 0
        for i, emoji in enumerate(test_emojis):
            supported = metrics.inFontUcs4(ord(emoji))
            print(f"Emoji {i+1}: {'SUPPORTÉ' if supported else 'NON SUPPORTÉ'}")
            if supported:
                supported_count += 1
        
        # Calcul du pourcentage et seuil
        threshold = 0.6  # Notre nouveau seuil
        percentage = supported_count / len(test_emojis)
        meets_threshold = percentage >= threshold
        
        print(f"\nRésumé:")
        print(f"Emojis supportés: {supported_count}/{len(test_emojis)} ({percentage:.1%})")
        print(f"Seuil requis: {threshold:.0%}")
        print(f"Seuil atteint: {'OUI' if meets_threshold else 'NON'}")
        
        # Test final de la détection
        emoji_supported = emoji_manager.is_emoji_supported()
        print(f"Détection finale: {'EMOJIS SUPPORTÉS' if emoji_supported else 'FALLBACK ACTIVÉ'}")
        
        return True
        
    except Exception as e:
        print(f"ERREUR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = debug_emoji_detection()
    sys.exit(0 if success else 1)