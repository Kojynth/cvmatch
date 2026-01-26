# -*- coding: utf-8 -*-
"""
Small UI text helpers:
- ui_text(text): fix common accent mojibake (Ã© → é, etc.) then apply emoji fallbacks
- sanitize_widget_texts(widget): traverse common Qt widgets and sanitize their texts

No source encoding change; fixes are applied at runtime only.
"""

from typing import Any
from PySide6.QtWidgets import QLabel, QPushButton, QCheckBox, QRadioButton, QGroupBox, QTabWidget, QWidget
from PySide6.QtGui import QAction

from .emoji_utils import emoji_manager


def ui_text(text: str) -> str:
    """Return a display-safe string by fixing common accent mojibake and applying emoji fallbacks."""
    try:
        if isinstance(text, str) and text:
            # Cache pour éviter les corrections multiples
            if hasattr(ui_text, '_cache') and text in ui_text._cache:
                return ui_text._cache[text]
            
            original_text = text
            fixes = {
                # Accents français (UTF-8 → Latin-1 mojibake)
                'Ã©': 'é', 'Ã¨': 'è', 'Ã ': 'à', 'Ãª': 'ê', 'Ã«': 'ë',
                'Ã¢': 'â', 'Ã¹': 'ù', 'Ã¼': 'ü', 'Ã´': 'ô', 'Ã§': 'ç',
                'Ã®': 'î', 'Ã¯': 'ï', 'Ã»': 'û',
                # Majuscules avec accents
                'Ã‰': 'É', 'Ã€': 'À', 'ÃŠ': 'Ê', 'ÃŽ': 'Î', 'Ã"': 'Ô',
                'Ã™': 'Ù', 'Ãœ': 'Ü', 'Ã‡': 'Ç', 'Ã‹': 'Ë', 'Ã\u008f': 'Ï',
                # Caractères spéciaux courants
                '\u2019': "'", '\u201C': '"', '\u201D': '"', '\u2013': '–', '\u2014': '—',
                '\u2026': '…', '\u2022': '•', '\u00B0': '°', '\u00AB': '«', '\u00BB': '»',
                # Séquences mojibake d'emojis fréquents (patterns réalistes)
                '\U0001F464': '👤',  # Profil
                '\U0001F4CB': '📋',  # Presse-papier  
                '\U0001F4BC': '💼',  # Mallette
                '\U0001F393': '🎓',  # Chapeau diplômé
                # Emojis corrompus supplémentaires trouvés dans l'audit final
                '\U0001F4CA': '📊',  # Graphique barres
                '\U0001F50D': '🔍',  # Loupe
                '\U0001F50E': '🔎',  # Loupe droite
                '\U0001F441\uFE0F': '👁️',  # Oeil
                '\U0001F504': '🔄',  # Flèches circulaires
                '\U0001F4BE': '💾',  # Disquette
                '\U0001F4C4': '📄',  # Page
                '\U0001F4DE': '📞',  # Téléphone
                '\U0001F517': '🔗',  # Lien
                '\U0001F4D9': '📙',  # Livre orange
                '\u2139\uFE0F': 'ℹ️',  # Information
                '\U0001F4C1': '📁',  # Dossier
                '\U0001F4C2': '📂',  # Dossier ouvert
                '\U0001F512': '🔒',  # Verrouillage
                '\U0001F6E1\uFE0F': '🛡️',  # Bouclier
                '\U0001F527': '🔧',  # Outils
                '\U0001F389': '🎉',  # Confettis
                '\U0001F4CC': '📌',  # Épingle
                '\U0001F4C3': '📃',  # Page repliée
                '\U0001F5C2\uFE0F': '🗂️',  # Index fichiers
                '\U0001F5C3\uFE0F': '🗃️',  # Boîte fichiers
                # Patterns corrompus découverts - utilisation sûre via codes hex
                # Note: Les patterns emoji corrompus sont gérés par le fixer externe
                '€¢': '•',     # Bullet point corrompu (safe pattern)
                # Caractères de contrôle problématiques
                '\u2699\uFE0F': '⚙️', '\u2705': '✅', '\u274C': '❌', '\u26A0\uFE0F': '⚠️',
                '\u20AC': '€', '\u2122': '™', '\u00AE': '®', '\u00A9': '©',
            }
            
            # Application des corrections
            for bad, good in fixes.items():
                if bad in text:
                    text = text.replace(bad, good)
            
            # Cache pour optimiser les performances
            if not hasattr(ui_text, '_cache'):
                ui_text._cache = {}
            if len(ui_text._cache) < 1000:  # Limiter la taille du cache
                ui_text._cache[original_text] = emoji_manager.get_display_text(text)
            
            return emoji_manager.get_display_text(text)
    except Exception:
        pass
    return emoji_manager.get_display_text(text)


def sanitize_widget_texts(root: QWidget) -> None:
    """Traverse child widgets and sanitize their visible texts with ui_text()."""
    try:
        if root is None:
            return
            
        # Compteur pour le debug
        fixed_count = 0
        
        # Sanitize window title
        try:
            title = root.windowTitle()
            if title:
                fixed = ui_text(title)
                if fixed != title:
                    root.setWindowTitle(fixed)
                    fixed_count += 1
        except Exception:
            pass
            
        # Sanitize statusbar si présent
        try:
            if hasattr(root, 'statusBar') and root.statusBar():
                msg = root.statusBar().currentMessage()
                if msg:
                    fixed = ui_text(msg)
                    if fixed != msg:
                        root.statusBar().showMessage(fixed)
                        fixed_count += 1
        except Exception:
            pass
        
        # Sanitize common text-bearing widgets de manière récursive
        for w in root.findChildren(QWidget):
            try:
                # Labels
                if isinstance(w, QLabel):
                    txt = w.text()
                    if txt:
                        fixed = ui_text(txt)
                        if fixed != txt:
                            w.setText(fixed)
                            fixed_count += 1
                    
                    # Tooltips aussi
                    tooltip = w.toolTip()
                    if tooltip:
                        fixed_tooltip = ui_text(tooltip)
                        if fixed_tooltip != tooltip:
                            w.setToolTip(fixed_tooltip)
                            fixed_count += 1
                
                # Boutons et contrôles
                elif isinstance(w, (QPushButton, QCheckBox, QRadioButton)):
                    txt = w.text()
                    if txt:
                        fixed = ui_text(txt)
                        if fixed != txt:
                            w.setText(fixed)
                            fixed_count += 1
                    
                    tooltip = w.toolTip()
                    if tooltip:
                        fixed_tooltip = ui_text(tooltip)
                        if fixed_tooltip != tooltip:
                            w.setToolTip(fixed_tooltip)
                            fixed_count += 1
                
                # GroupBox
                elif isinstance(w, QGroupBox):
                    t = w.title()
                    if t:
                        fixed = ui_text(t)
                        if fixed != t:
                            w.setTitle(fixed)
                            fixed_count += 1
                
                # TabWidget
                elif isinstance(w, QTabWidget):
                    for i in range(w.count()):
                        t = w.tabText(i)
                        if t:
                            fixed = ui_text(t)
                            if fixed != t:
                                w.setTabText(i, fixed)
                                fixed_count += 1
                        
                        # Tab tooltips
                        tooltip = w.tabToolTip(i)
                        if tooltip:
                            fixed_tooltip = ui_text(tooltip)
                            if fixed_tooltip != tooltip:
                                w.setTabToolTip(i, fixed_tooltip)
                                fixed_count += 1
                
                # Autres widgets avec propriété text générique
                elif hasattr(w, 'text') and callable(getattr(w, 'text')):
                    try:
                        txt = w.text()
                        if txt and hasattr(w, 'setText'):
                            fixed = ui_text(txt)
                            if fixed != txt:
                                w.setText(fixed)
                                fixed_count += 1
                    except Exception:
                        pass
                        
            except Exception:
                continue
        
        # Sanitize actions (menus/toolbars)
        for a in root.findChildren(QAction):
            try:
                t = a.text()
                if t:
                    fixed = ui_text(t)
                    if fixed != t:
                        a.setText(fixed)
                        fixed_count += 1
                
                # Action tooltips et status tips
                tooltip = a.toolTip()
                if tooltip:
                    fixed_tooltip = ui_text(tooltip)
                    if fixed_tooltip != tooltip:
                        a.setToolTip(fixed_tooltip)
                        fixed_count += 1
                        
                status_tip = a.statusTip()
                if status_tip:
                    fixed_status = ui_text(status_tip)
                    if fixed_status != status_tip:
                        a.setStatusTip(fixed_status)
                        fixed_count += 1
                        
            except Exception:
                continue
        
        # Log du résultat si des corrections ont été appliquées
        if fixed_count > 0:
            print(f"🔧 UI Sanitizer: {fixed_count} corrections appliquées")
            
    except Exception as e:
        print(f"⚠️ Erreur dans sanitize_widget_texts: {e}")
        pass


def auto_setup_ui_sanitizer(main_window) -> None:
    """Configure le sanitizer automatique pour une fenêtre principale."""
    try:
        # Sanitization initiale
        sanitize_widget_texts(main_window)
        
        # Optionnel: Hook sur les événements show pour futures corrections
        original_show = main_window.show
        def sanitized_show():
            result = original_show()
            sanitize_widget_texts(main_window)
            return result
        main_window.show = sanitized_show
        
        print("✅ UI Sanitizer automatique configuré")
        
    except Exception as e:
        print(f"⚠️ Erreur configuration UI Sanitizer: {e}")
        pass
