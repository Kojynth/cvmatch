"""
Widget d'en-tête de section réutilisable
======================================

Ce module fournit un widget d'en-tête standardisé pour les sections.
"""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont


class SectionHeaderWidget(QFrame):
    """Widget d'en-tête de section avec icône et titre."""
    
    def __init__(self, title: str, icon: str = "📋", subtitle: str = "", parent=None):
        super().__init__(parent)
        self.setup_ui(title, icon, subtitle)
    
    def setup_ui(self, title: str, icon: str, subtitle: str):
        """Configure l'interface du widget."""
        self.setFrameStyle(QFrame.Shape.NoFrame)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 5, 0, 10)
        layout.setSpacing(8)
        
        # Icône
        icon_label = QLabel(icon)
        icon_label.setFont(QFont("Segoe UI Emoji", 14))
        layout.addWidget(icon_label)
        
        # Titre principal
        title_label = QLabel(title)
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setStyleSheet("""
            QLabel {
                color: #4db8ff;
                padding: 0px;
                margin: 0px;
            }
        """)
        layout.addWidget(title_label)
        
        # Sous-titre optionnel
        if subtitle:
            subtitle_label = QLabel(f"({subtitle})")
            subtitle_font = QFont()
            subtitle_font.setPointSize(10)
            subtitle_font.setItalic(True)
            subtitle_label.setFont(subtitle_font)
            subtitle_label.setStyleSheet("""
                QLabel {
                    color: #888888;
                    padding: 0px;
                    margin-left: 5px;
                }
            """)
            layout.addWidget(subtitle_label)
        
        layout.addStretch()
        
        # Ligne de séparation
        self.setStyleSheet("""
            SectionHeaderWidget {
                border-bottom: 1px solid #555555;
                margin-bottom: 5px;
            }
        """)
    
    def update_title(self, new_title: str):
        """Met à jour le titre de la section."""
        layout = self.layout()
        if layout.count() >= 2:
            title_label = layout.itemAt(1).widget()
            if isinstance(title_label, QLabel):
                title_label.setText(new_title)
    
    def update_subtitle(self, new_subtitle: str):
        """Met à jour le sous-titre de la section."""
        layout = self.layout()
        if layout.count() >= 3:
            subtitle_label = layout.itemAt(2).widget()
            if isinstance(subtitle_label, QLabel):
                subtitle_label.setText(f"({new_subtitle})" if new_subtitle else "")


class CompactSectionHeader(QLabel):
    """Version compacte d'un en-tête de section (juste un label stylé)."""
    
    def __init__(self, title: str, icon: str = "", parent=None):
        text = f"{icon} {title}" if icon else title
        super().__init__(text, parent)
        self.setup_style()
    
    def setup_style(self):
        """Configure le style du label."""
        font = QFont()
        font.setPointSize(12)
        font.setBold(True)
        self.setFont(font)
        self.setStyleSheet("""
            QLabel {
                color: #4db8ff;
                padding: 5px 0px;
                border-bottom: 1px solid #555555;
                margin-bottom: 8px;
            }
        """)


class CategoryHeader(QFrame):
    """En-tête de catégorie avec style différencié."""
    
    def __init__(self, title: str, icon: str = "▸", color: str = "#4db8ff", parent=None):
        super().__init__(parent)
        self.setup_ui(title, icon, color)
    
    def setup_ui(self, title: str, icon: str, color: str):
        """Configure l'interface."""
        self.setFrameStyle(QFrame.Shape.NoFrame)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(6)
        
        # Icône d'expansion/collapse
        icon_label = QLabel(icon)
        icon_label.setStyleSheet(f"color: {color}; font-weight: bold;")
        layout.addWidget(icon_label)
        
        # Titre
        title_label = QLabel(title)
        title_font = QFont()
        title_font.setPointSize(11)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setStyleSheet(f"""
            QLabel {{
                color: {color};
                background-color: rgba(77, 184, 255, 0.1);
                padding: 4px 8px;
                border-radius: 3px;
            }}
        """)
        layout.addWidget(title_label)
        
        layout.addStretch()


# Fonctions utilitaires pour créer rapidement des en-têtes
def create_section_header(title: str, icon: str = "📋", subtitle: str = "", parent=None) -> SectionHeaderWidget:
    """
    Crée un en-tête de section standard.
    
    Args:
        title: Titre de la section
        icon: Icône emoji
        subtitle: Sous-titre optionnel
        parent: Widget parent
        
    Returns:
        Widget d'en-tête configuré
    """
    return SectionHeaderWidget(title, icon, subtitle, parent)


def create_compact_header(title: str, icon: str = "", parent=None) -> CompactSectionHeader:
    """
    Crée un en-tête compact.
    
    Args:
        title: Titre
        icon: Icône optionnelle
        parent: Widget parent
        
    Returns:
        Label d'en-tête configuré
    """
    return CompactSectionHeader(title, icon, parent)


def create_category_header(title: str, icon: str = "▸", color: str = "#4db8ff", parent=None) -> CategoryHeader:
    """
    Crée un en-tête de catégorie.
    
    Args:
        title: Titre de la catégorie
        icon: Icône d'expansion
        color: Couleur de l'en-tête
        parent: Widget parent
        
    Returns:
        Widget d'en-tête de catégorie
    """
    return CategoryHeader(title, icon, color, parent)
