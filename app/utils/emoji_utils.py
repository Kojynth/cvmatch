"""
Utilitaire pour la gestion des emojis et des polices.
Gère le fallback automatique emoji → texte selon le support système.
Version corrigée avec Unicode escapes propres.
"""

import sys
import os
from pathlib import Path
from typing import Dict, Optional, List
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase, QFont, QFontMetrics
from PySide6.QtCore import Qt


class EmojiManager:
    """Gestionnaire d'emojis avec fallback automatique."""
    
    def __init__(self):
        self.emoji_supported = None
        self.emoji_font = None
        self.force_ascii_mode = False  # Force ASCII fallbacks for problematic systems
        self._emoji_fallbacks = {
            # Navigation principale
            "\U0001F464": "[P]",  # 👤 Profil
            "\u2699\ufe0f": "[S]",  # ⚙️ Settings/Paramètres
            "\U0001F4CB": "[N]",  # 📋 Nouvelle candidature
            "\U0001F4D9": "[H]",  # 📙 Historique
            "\U0001F3E0": "[A]",  # 🏠 Accueil
            
            # Actions communes
            "\U0001F4C1": "[F]",  # 📁 Dossier
            "\U0001F4C2": "[F]",  # 📂 Dossier ouvert
            "\U0001F527": "[T]",  # 🔧 Outils/Technique
            "\U0001F4BC": "[W]",  # 💼 Travail/Business
            "\U0001F393": "[E]",  # 🎓 Education
            "\U0001F4DE": "[T]",  # 📞 Téléphone
            "\U0001F4E7": "[M]",  # 📧 Mail
            "\U0001F517": "[Link]",  # 🔗 Lien - more readable
            "\U0001F4A1": "[I]",  # 💡 Idée
            "\u26A0\ufe0f": "[!]",  # ⚠️ Warning
            "\u2705": "[✓]",  # ✅ Success
            "\u274C": "[✗]",  # ❌ Error
            "\U0001F512": "[S]",  # 🔒 Sécurisé
            "\U0001F6E1\ufe0f": "[P]",  # 🛡️ Protection
            "\U0001F6AB": "[X]",  # 🚫 Interdit
            
            # Analyses et stats
            "\U0001F4CA": "[G]",  # 📊 Graphique
            "\u2696\ufe0f": "[C]",  # ⚖️ Comparaison
            "\U0001F3AF": "[T]",  # 🎯 Target
            "\U0001F4C8": "[+]",  # 📈 Progression
            
            # Emojis supplémentaires utilisés dans l'app
            "\U0001F50D": "[Search]",  # 🔍 Recherche - more readable
            "\U0001F441\ufe0f": "[View]",  # 👁️ Voir - more readable
            "\U0001F4BE": "[Save]",  # 💾 Sauvegarder - more readable
            "\U0001F504": "[Refresh]",  # 🔄 Actualiser - more readable
            "\U0001F680": "[Launch]",  # 🚀 Lancer - more readable
            "\U0001F4DD": "[📝]",  # 📝 Éditer
            "\U0001F4C4": "[📄]",  # 📄 Document
            "\U0001F4C5": "[📅]",  # 📅 Calendrier
            "\u2B50": "[*]",  # ⭐ Star rating - readable asterisk
            "\u270F\ufe0f": "[✏]",  # ✏️ Edit pencil
            "\U0001F5D1\ufe0f": "[🗑]",  # 🗑️ Delete
            "\U0001F48C": "[💌]",  # 💌 Letter
            "\U0001F310": "[🌐]",  # 🌐 Web
            "\U0001F4F1": "[📱]",  # 📱 Mobile
            "\U0001F3AE": "[🎮]",  # 🎮 Gaming/GPU
            "\U0001F4BB": "[💻]",  # 💻 Ordinateur
            "\u2139\ufe0f": "[ℹ]",  # ℹ️ Information
        }
    
    def configure_emoji_font(self) -> bool:
        """Configure la police pour supporter les emojis."""
        try:
            app = QApplication.instance()
            if not app:
                return False
            
            # Essayer différentes polices emoji selon l'OS
            emoji_fonts = []
            
            if sys.platform == "win32":
                emoji_fonts = [
                    "Segoe UI Emoji",
                    "Segoe UI Symbol",
                    "Microsoft YaHei",
                    "Segoe UI Historic",
                    "Malgun Gothic",
                    "Segoe UI",
                    "Calibri"
                ]
            elif sys.platform == "darwin":  # macOS
                emoji_fonts = [
                    "Apple Color Emoji",
                    "SF Pro Display",
                    "Helvetica Neue"
                ]
            else:  # Linux
                emoji_fonts = self._get_linux_emoji_fonts()
            
            font_db = QFontDatabase()
            available_families = font_db.families()
            
            # Trouver la première police disponible avec support emoji
            for font_name in emoji_fonts:
                if font_name in available_families:
                    font = QFont(font_name)
                    font.setPointSize(12)
                    
                    # Tester si la police peut afficher les emojis de base
                    metrics = QFontMetrics(font)
                    if metrics.inFontUcs4(ord('\U0001F464')) or metrics.inFontUcs4(ord('\u2699')):
                        self.emoji_font = font
                        app.setFont(font)
                        print(f"[OK] Police emoji configuree: {font_name}")
                        return True
                        
            print("[WARNING] Aucune police emoji trouvee")
            return False
            
        except Exception as e:
            print(f"[ERROR] Erreur configuration police: {e}")
            return False
    
    def _get_linux_emoji_fonts(self) -> List[str]:
        """Obtient la liste optimisée des polices emoji pour Linux."""
        # Polices emoji principales avec fallbacks robustes
        base_fonts = [
            "Noto Color Emoji",        # Google/Android - le plus courant
            "Twemoji",                 # Twitter emoji (certaines distros)  
            "EmojiOne Color",          # EmojiOne font (si installé)
            "Symbola",                 # Fallback Unicode symbols
            "DejaVu Sans",            # Fallback standard
            "Ubuntu",                  # Ubuntu family
            "Liberation Sans",         # Red Hat/Fedora fallback
            "GNU Unifont",            # Minimal Unicode coverage
        ]
        
        # Détecter des polices supplémentaires selon l'environnement
        detected_fonts = self._detect_additional_linux_fonts()
        
        # Combiner avec priorité aux polices détectées
        return detected_fonts + [f for f in base_fonts if f not in detected_fonts]
    
    def _detect_additional_linux_fonts(self) -> List[str]:
        """Détecte des polices emoji supplémentaires sur Linux."""
        additional_fonts = []
        
        # Chemins communs de polices Linux
        font_paths = [
            "/usr/share/fonts/",
            "/usr/local/share/fonts/", 
            Path.home() / ".fonts/",
            Path.home() / ".local/share/fonts/",
            "/System/Library/Fonts/",  # Si macOS-like
        ]
        
        # Noms de fichiers emoji courants
        emoji_files = [
            "NotoColorEmoji.ttf", "NotoColorEmoji.woff",
            "TwitterColorEmoji-SVGinOT.ttf",
            "EmojiOneColor.otf",
            "Symbola.ttf", "unifont.ttf"
        ]
        
        try:
            for font_path in font_paths:
                if not Path(font_path).exists():
                    continue
                    
                for emoji_file in emoji_files:
                    for font_file in Path(font_path).rglob(emoji_file):
                        if font_file.exists():
                            # Mapper fichier vers nom de police
                            if "Noto" in emoji_file:
                                additional_fonts.append("Noto Color Emoji")
                            elif "Twitter" in emoji_file or "Twemoji" in emoji_file:
                                additional_fonts.append("Twemoji")
                            elif "EmojiOne" in emoji_file:
                                additional_fonts.append("EmojiOne Color")
                            elif "Symbola" in emoji_file:
                                additional_fonts.append("Symbola")
                            break
        except Exception:
            # Silencieusement ignorer les erreurs de détection
            pass
        
        # Détecter l'environnement desktop pour polices spécifiques
        desktop_env = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
        if "gnome" in desktop_env:
            additional_fonts.append("Cantarell")
        elif "kde" in desktop_env or "plasma" in desktop_env:
            additional_fonts.append("Noto Sans")
        
        # Retirer les doublons en préservant l'ordre
        seen = set()
        return [f for f in additional_fonts if not (f in seen or seen.add(f))]
    
    def _is_headless_environment(self) -> bool:
        """Vérifie si on est dans un environnement headless (serveur)."""
        # Pas de display
        if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
            return True
        
        # Session SSH sans forwarding
        if os.environ.get("SSH_CLIENT") and not os.environ.get("DISPLAY"):
            return True
        
        # Variables d'environnement de serveur  
        server_indicators = ["SUDO_USER", "SSH_CONNECTION"]
        if any(os.environ.get(var) for var in server_indicators) and not os.environ.get("DESKTOP_SESSION"):
            return True
        
        return False
    
    def force_ascii_fallbacks(self):
        """Force l'utilisation des fallbacks ASCII - utile pour systèmes problématiques."""
        self.force_ascii_mode = True
        self.emoji_supported = False
        print("[FORCE] Mode ASCII force active - utilisation des fallbacks texte")
    
    def is_emoji_supported(self) -> bool:
        """Vérifie si les emojis sont supportés."""
        # Si mode ASCII forcé, toujours retourner False
        if self.force_ascii_mode:
            return False
            
        if self.emoji_supported is not None:
            return self.emoji_supported
        
        # Environnement headless = toujours utiliser fallbacks
        if sys.platform.startswith('linux') and self._is_headless_environment():
            print("[INFO] Environnement headless detecte - utilisation fallback")
            self.emoji_supported = False
            return False
        
        try:
            app = QApplication.instance()
            if not app:
                self.emoji_supported = False
                return False
            
            # Test avec la police actuelle
            font = app.font()
            metrics = QFontMetrics(font)
            
            # Tester les emojis critiques utilisés dans l'interface
            test_emojis = ['\U0001F464', '\u2699', '\U0001F4CB', '\U0001F4BC', '\U0001F527', '\U0001F4CA', '\u2B50']
            supported_count = 0
            
            for emoji in test_emojis:
                if metrics.inFontUcs4(ord(emoji)):
                    supported_count += 1
            
            # Seuils ajustés pour une détection équilibrée des emojis
            if sys.platform == "win32":
                # Windows: modéré (60% requis) pour permettre les emojis de base
                threshold = 0.6
            elif sys.platform.startswith('linux'):
                # Linux: conservateur (75% requis)
                threshold = 0.75
            else:
                # Autres: standard (50% requis)
                threshold = 0.5
                
            self.emoji_supported = (supported_count >= len(test_emojis) * threshold)
            
            print(f"[DETECT] Support emoji ({sys.platform}): {supported_count}/{len(test_emojis)} emojis supportes (seuil: {int(threshold*100)}%)")
            return self.emoji_supported
            
        except Exception as e:
            print(f"[ERROR] Erreur test emoji: {e}")
            self.emoji_supported = False
            return False
    
    def get_display_text(self, text: str) -> str:
        """
        Retourne le texte d'affichage avec fallback emoji si nécessaire.
        
        Args:
            text: Texte avec emojis potentiels (ex: "👤 Profil")
            
        Returns:
            Texte adapté selon le support système
        """
        if self.is_emoji_supported():
            return text
        
        # Remplacer les emojis par leur fallback
        result = text
        for emoji, fallback in self._emoji_fallbacks.items():
            result = result.replace(emoji, fallback)
        
        return result
    
    def get_safe_emoji(self, emoji: str, fallback: str = "[?]") -> str:
        """
        Retourne l'emoji ou son fallback selon le support.
        
        Args:
            emoji: Emoji Unicode (ex: "👤")
            fallback: Texte de remplacement (ex: "[P]")
            
        Returns:
            Emoji ou fallback selon le support système
        """
        if self.is_emoji_supported():
            return emoji
        
        return self._emoji_fallbacks.get(emoji, fallback)


# Instance globale
emoji_manager = EmojiManager()


def setup_emoji_support() -> bool:
    """Configuration initiale du support emoji."""
    return emoji_manager.configure_emoji_font()


def get_display_text(text: str) -> str:
    """Fonction utilitaire pour obtenir le texte d'affichage adapté."""
    return emoji_manager.get_display_text(text)


def safe_emoji(emoji: str, fallback: str = "[?]") -> str:
    """Fonction utilitaire pour obtenir un emoji sûr."""
    return emoji_manager.get_safe_emoji(emoji, fallback)


def force_ascii_mode() -> None:
    """Force l'utilisation des fallbacks ASCII - utile pour systèmes avec problèmes d'emojis."""
    emoji_manager.force_ascii_fallbacks()

def reset_emoji_detection() -> None:
    """Réinitialise la détection d'emoji - utile après modification des tests."""
    emoji_manager.emoji_supported = None
    emoji_manager.emoji_font = None