"""
Classe de base pour toutes les sections du profile viewer.

Cette classe abstraite définit l'interface commune et les styles partagés
pour toutes les sections de données du profil.
"""

from abc import ABCMeta, abstractmethod
from typing import Dict, List, Any, Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout, 
    QLineEdit, QTextEdit, QPushButton, QLabel, QFrame
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from ...models.user_profile import UserProfile
from ...widgets.style_manager import apply_button_style
from ...widgets.collapsible_section import CollapsibleSection, create_collapsible_section
from ...utils.confidence_filter import filter_high_confidence, has_confidence_scores


# Métaclasse combinée pour résoudre le conflit entre Qt et ABC
class QABCMeta(type(QWidget), ABCMeta):
    pass


class BaseSection(QWidget, metaclass=QABCMeta):
    """Classe de base abstraite pour toutes les sections de profil."""
    
    data_updated = Signal(UserProfile)
    structural_change = Signal(UserProfile)  # Signal pour les changements structurels
    
    def __init__(self, profile: UserProfile, parent=None):
        super().__init__(parent)
        self.profile = profile
        self.parent_viewer = parent
        self.dynamic_widgets = []  # Liste pour stocker les widgets dynamiques
        
        # Style sombre cohérent
        self.setStyleSheet(self._get_section_stylesheet())
        
    def _get_section_stylesheet(self) -> str:
        """Retourne le stylesheet commun à toutes les sections."""
        return """
            QWidget {
                background-color: #1e1e1e;
                color: #e0e0e0;
            }
            QGroupBox {
                background-color: #2a2a2a;
                border: 1px solid #404040;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
                font-weight: bold;
                color: #ffffff;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 10px 0 10px;
                color: #4db8ff;
                font-size: 14px;
            }
            QLineEdit {
                background-color: #3a3a3a;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 12px;
                color: #ffffff;
                font-size: 14px;
                min-height: 20px;
            }
            QLineEdit:focus {
                border: 2px solid #4db8ff;
                background-color: #404040;
            }
            QTextEdit {
                background-color: #3a3a3a;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 12px;
                color: #ffffff;
                font-size: 14px;
                min-height: 80px;
            }
            QTextEdit:focus {
                border: 2px solid #4db8ff;
                background-color: #404040;
            }
            QPushButton {
                background-color: #4db8ff;
                border: none;
                color: white;
                padding: 12px 24px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 14px;
                min-height: 20px;
            }
            QPushButton:hover {
                background-color: #66c2ff;
            }
            QPushButton:pressed {
                background-color: #3399cc;
            }
            QPushButton.danger {
                background-color: #e74c3c;
            }
            QPushButton.danger:hover {
                background-color: #c0392b;
            }
            QLabel {
                color: #e0e0e0;
                font-size: 14px;
            }
        """
    
    @abstractmethod
    def create_section_widget(self) -> QWidget:
        """Crée et retourne le widget principal de la section."""
        pass
    
    @abstractmethod
    def get_section_data(self) -> Any:
        """Retourne les données de cette section du profil."""
        pass
    
    def get_filtered_data(self, data, section_name: str = ""):
        """Filtre les données selon leur niveau de confiance."""
        if isinstance(data, dict) and has_confidence_scores(data):
            return filter_high_confidence(data, section_name)
        elif isinstance(data, list):
            return [filter_high_confidence(item, section_name) if has_confidence_scores(item) else item 
                   for item in data]
        return data
    
    def create_form_field(self, label: str, value: str = "", is_multiline: bool = False) -> tuple:
        """Crée un champ de formulaire standard avec label et widget."""
        if is_multiline:
            widget = QTextEdit()
            widget.setPlainText(str(value))
            widget.setMaximumHeight(100)
        else:
            widget = QLineEdit()
            widget.setText(str(value))
        
        return QLabel(label), widget
    
    def create_action_button(self, text: str, style: str = "primary", icon: str = "") -> QPushButton:
        """Crée un bouton d'action standardisé."""
        if icon:
            button = QPushButton(f"{icon} {text}")
        else:
            button = QPushButton(text)
            
        if style == "danger":
            button.setProperty("class", "danger")
        
        apply_button_style(button, style)
        return button
    
    def create_section_header(self, title: str, count: int = 0) -> QWidget:
        """Crée un en-tête de section avec titre et compteur optionnel."""
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        if count > 0:
            title_label = QLabel(f"{title} ({count})")
        else:
            title_label = QLabel(title)
            
        title_label.setFont(QFont("Arial", 14, QFont.Bold))
        title_label.setStyleSheet("color: #4db8ff;")
        
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        
        return header
    
    def clear_dynamic_widgets(self):
        """Supprime tous les widgets dynamiques stockés."""
        for widget in self.dynamic_widgets:
            if widget and not widget.isHidden():
                widget.deleteLater()
        self.dynamic_widgets.clear()
    
    def add_dynamic_widget(self, widget: QWidget):
        """Ajoute un widget à la liste des widgets dynamiques."""
        if widget:
            self.dynamic_widgets.append(widget)
    
    def emit_data_updated(self, force_reload=False, auto_save=True):
        """Émet le signal de mise à jour des données."""
        if force_reload:
            # Changements structurels qui nécessitent un rechargement complet
            self.structural_change.emit(self.profile)
        else:
            # Modifications de données qui ne nécessitent pas de rechargement
            self.data_updated.emit(self.profile)
        
        # Sauvegarder uniquement si explicitement demandé
        if auto_save and self.parent_viewer and hasattr(self.parent_viewer, 'data_updated'):
            self.parent_viewer.data_updated.emit(self.profile)
    
    def create_separator(self) -> QFrame:
        """Crée une ligne de séparation."""
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setStyleSheet("QFrame { color: #404040; }")
        return separator

    # Shared helpers extracted from duplicated section methods
    def _update_field(self, obj: dict, field: str, value):
        """Minimal field updater used across sections."""
        if isinstance(obj, dict):
            obj[field] = value
            # Émettre signal de modification sans rechargement complet
            self.emit_data_updated(force_reload=False)

    def _get_add_button_style(self) -> str:
        """Standard style for small green add buttons (languages/projects)."""
        return (
            "QPushButton { background-color: #2d5f3f; color: white; border: none; "
            "padding: 12px 20px; border-radius: 8px; font-weight: bold; font-size: 14px; margin: 5px; } "
            "QPushButton:hover { background-color: #1e4f2f; }"
        )

    def _get_widget_style(self) -> str:
        """Standard frame style for item containers (languages/projects)."""
        return (
            "QFrame { background-color: #3a3a3a; border: 1px solid #555555; border-radius: 12px; "
            "margin: 8px; padding: 15px; } QFrame:hover { border: 1px solid #4db8ff; background-color: #404040; }"
        )

    def create_delete_button(self) -> QPushButton:
        """Small red circular delete button used across sections."""
        btn = QPushButton("🗑️")
        btn.setFixedSize(28, 28)
        btn.setStyleSheet(
            "QPushButton { background: #DC143C; border-radius: 14px; color: #FFFFFF; "
            "font-weight: bold; font-size: 14px; border: none; } "
            "QPushButton:hover { background: #B22222; }"
        )
        return btn
