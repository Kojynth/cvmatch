"""
Section collapsible réutilisable
===============================

Widget de section qui peut être étendue ou repliée.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QRect, QEasingCurve
from PySide6.QtGui import QFont, QCursor
from loguru import logger


class CollapsibleSection(QFrame):
    """Section collapsible avec en-tête cliquable."""
    
    toggled = Signal(bool)  # Émis quand la section est étendue/repliée
    
    def __init__(self, title: str, icon: str = "▼", parent=None):
        super().__init__(parent)
        self.is_expanded = True
        self.content_widget = None
        self.setup_ui(title, icon)
    
    def setup_ui(self, title: str, icon: str):
        """Configure l'interface de la section."""
        self.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)
        self.setStyleSheet("""
            CollapsibleSection {
                background-color: #2a2a2a;
                border: 1px solid #555555;
                border-radius: 8px;
                margin: 2px;
            }
        """)
        
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # En-tête cliquable
        self.header = QFrame()
        self.header.setFixedHeight(40)
        self.header.setStyleSheet("""
            QFrame {
                background-color: #3a3a3a;
                border: none;
                border-radius: 8px 8px 0 0;
                padding: 5px;
            }
            QFrame:hover {
                background-color: #404040;
            }
        """)
        
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(10, 0, 10, 0)
        
        # Icône d'expansion
        self.toggle_icon = QLabel(icon)
        self.toggle_icon.setFont(QFont("Arial", 10))
        self.toggle_icon.setStyleSheet("color: #4db8ff; font-weight: bold;")
        header_layout.addWidget(self.toggle_icon)
        
        # Titre
        self.title_label = QLabel(title)
        self.title_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        self.title_label.setStyleSheet("color: #4db8ff; margin-left: 5px;")
        header_layout.addWidget(self.title_label)
        
        header_layout.addStretch()
        
        # Bouton collapse/expand plus visible
        self.toggle_button = QPushButton()
        self.toggle_button.setFixedSize(30, 30)
        self.toggle_button.setStyleSheet("""
            QPushButton {
                background-color: #4db8ff;
                border: 2px solid #FFFFFF;
                border-radius: 15px;
                color: #FFFFFF;
                font-weight: bold;
                font-size: 18px;
                text-align: center;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: #3da8e8;
                color: #FFFFFF;
                border: 2px solid #FFFF00;
            }
        """)
        self.update_toggle_button()
        self.toggle_button.clicked.connect(self.toggle)
        header_layout.addWidget(self.toggle_button)
        
        # Rendre l'en-tête cliquable
        self.header.mousePressEvent = lambda event: self.toggle()
        self.header.setCursor(QCursor(Qt.PointingHandCursor))
        
        self.main_layout.addWidget(self.header)
        
        # Container pour le contenu
        self.content_container = QFrame()
        self.content_container.setStyleSheet("""
            QFrame {
                background-color: #2a2a2a;
                border: none;
                border-radius: 0 0 8px 8px;
            }
        """)
        
        self.content_layout = QVBoxLayout(self.content_container)
        self.content_layout.setContentsMargins(10, 10, 10, 10)
        
        self.main_layout.addWidget(self.content_container)
    
    def set_content(self, widget: QWidget):
        """Définit le contenu de la section."""
        if self.content_widget:
            self.content_layout.removeWidget(self.content_widget)
            self.content_widget.setParent(None)
        
        self.content_widget = widget
        self.content_layout.addWidget(widget)
    
    def toggle(self):
        """Bascule l'état étendu/replié de la section."""
        self.is_expanded = not self.is_expanded
        self.content_container.setVisible(self.is_expanded)
        self.update_toggle_button()
        self.update_toggle_icon()
        self.toggled.emit(self.is_expanded)
        
        logger.debug(f"Section '{self.title_label.text()}' {'étendue' if self.is_expanded else 'repliée'}")
    
    def update_toggle_button(self):
        """Met à jour l'icône du bouton toggle."""
        if self.is_expanded:
            self.toggle_button.setText("▲")  # Flèche vers le haut
        else:
            self.toggle_button.setText("▼")  # Flèche vers le bas
    
    def update_toggle_icon(self):
        """Met à jour l'icône directionnelle."""
        if self.is_expanded:
            self.toggle_icon.setText("▼")  # Flèche vers le bas
        else:
            self.toggle_icon.setText("▶")  # Flèche vers la droite
    
    def expand(self):
        """Force l'expansion de la section."""
        if not self.is_expanded:
            self.toggle()
    
    def collapse(self):
        """Force la contraction de la section."""
        if self.is_expanded:
            self.toggle()
    
    def set_title(self, title: str):
        """Met à jour le titre de la section."""
        self.title_label.setText(title)
    
    def get_title(self) -> str:
        """Récupère le titre de la section."""
        return self.title_label.text()


class QuickCollapsibleGroup(QFrame):
    """Groupe de sections avec boutons rapides expand/collapse all."""
    
    def __init__(self, title: str = "Sections", parent=None):
        super().__init__(parent)
        self.sections = []
        self.setup_ui(title)
    
    def setup_ui(self, title: str):
        """Configure l'interface du groupe."""
        layout = QVBoxLayout(self)
        
        # En-tête avec contrôles globaux
        header_layout = QHBoxLayout()
        
        title_label = QLabel(title)
        title_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #e0e0e0; margin-bottom: 5px;")
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        
        # Boutons expand/collapse all
        expand_all_btn = QPushButton("Tout développer")
        expand_all_btn.setStyleSheet("background: #2d5f3f; color: white; padding: 4px 8px; border-radius: 3px; font-size: 10px;")
        expand_all_btn.clicked.connect(self.expand_all)
        header_layout.addWidget(expand_all_btn)
        
        collapse_all_btn = QPushButton("Tout replier")
        collapse_all_btn.setStyleSheet("background: #5f2d2d; color: white; padding: 4px 8px; border-radius: 3px; font-size: 10px;")
        collapse_all_btn.clicked.connect(self.collapse_all)
        header_layout.addWidget(collapse_all_btn)
        
        layout.addLayout(header_layout)
        
        # Container pour les sections
        self.sections_layout = QVBoxLayout()
        layout.addLayout(self.sections_layout)
    
    def add_section(self, section: CollapsibleSection):
        """Ajoute une section au groupe."""
        self.sections.append(section)
        self.sections_layout.addWidget(section)
    
    def expand_all(self):
        """Étend toutes les sections."""
        for section in self.sections:
            section.expand()
    
    def collapse_all(self):
        """Replie toutes les sections."""
        for section in self.sections:
            section.collapse()


# Fonctions utilitaires
def create_collapsible_section(title: str, content_widget: QWidget, icon: str = "▼", expanded: bool = True) -> CollapsibleSection:
    """
    Crée rapidement une section collapsible.
    
    Args:
        title: Titre de la section
        content_widget: Widget contenu
        icon: Icône initiale
        expanded: État initial (étendu ou non)
        
    Returns:
        Section collapsible configurée
    """
    section = CollapsibleSection(title, icon)
    section.set_content(content_widget)
    
    if not expanded:
        section.collapse()
    
    return section
