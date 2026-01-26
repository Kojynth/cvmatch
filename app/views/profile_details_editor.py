from .text_cleaner import sanitize_widget_tree
"""
Profile Details Editor
======================

Interface complète d’édition des détails du profil avec sections organisées,
gestion des conflits CV/LinkedIn, et ajout dynamique d’éléments.
"""

import sys
import json
import os
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QScrollArea, QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout,
    QLabel, QLineEdit, QTextEdit, QPushButton, QComboBox, QDateEdit, QSpinBox,
    QGroupBox, QFrame, QMessageBox, QDialog, QCheckBox, QSplitter,
    QApplication, QButtonGroup, QRadioButton
)
from PySide6.QtCore import Qt, Signal, QDate
from PySide6.QtGui import QFont, QIcon, QPalette
from loguru import logger

from ..models.user_profile import UserProfile
from ..models.database import get_session
from ..widgets.style_manager import StyleManager, apply_button_style


from app.utils.emoji_utils import get_display_text
from app.services.dialogs import (
    confirm,
    open_file_dialog,
    save_file_dialog,
    show_error,
    show_info,
)


class DataSourceBadge(QLabel):
    """
    Badge visuel indiquant la source des données (CV, LinkedIn, Manuel, Fusionné).

    Affiche un petit badge coloré pour indiquer d'où proviennent les données
    d'un élément (expérience, formation, compétence, etc.).
    """

    SOURCES = {
        "cv": ("CV", "#2d5f3f", "#ffffff"),              # Vert
        "linkedin": ("LinkedIn", "#0077b5", "#ffffff"),  # Bleu LinkedIn
        "manual": ("Manuel", "#6c757d", "#ffffff"),      # Gris
        "merged": ("CV+LI", "#9333ea", "#ffffff"),       # Violet
    }

    def __init__(self, source: str = "manual", parent=None):
        """
        Initialise le badge avec une source.

        Args:
            source: Type de source ('cv', 'linkedin', 'manual', 'merged')
            parent: Widget parent
        """
        super().__init__(parent)
        self.set_source(source)

    def set_source(self, source: str):
        """Configure le badge pour la source spécifiée."""
        source_lower = (source or "manual").lower()

        # Normaliser les variations de noms de source
        if source_lower in ("cv", "resume"):
            source_lower = "cv"
        elif source_lower in ("linkedin", "li"):
            source_lower = "linkedin"
        elif source_lower in ("merged", "cv+linkedin", "combined"):
            source_lower = "merged"
        else:
            source_lower = "manual"

        label, bg_color, text_color = self.SOURCES.get(source_lower, self.SOURCES["manual"])

        self.setText(label)
        self.setStyleSheet(f"""
            QLabel {{
                background-color: {bg_color};
                color: {text_color};
                padding: 2px 8px;
                border-radius: 10px;
                font-size: 10px;
                font-weight: bold;
            }}
        """)
        self.setFixedHeight(18)
        self.setAlignment(Qt.AlignCenter)
        self.setToolTip(f"Source: {label}")


class DataSourceSelector(QComboBox):
    """Sélecteur de source de données avec indicateurs visuels."""
    
    source_changed = Signal(str)  # Émis quand la source change
    
    def __init__(self, sources: List[Tuple[str, str, bool]] = None):
        """
        Args:
            sources: Liste de (source_name, display_text, has_data)
        """
        super().__init__()
        self.sources_data = {}
        
        if sources:
            self.populate_sources(sources)
        
        self.currentTextChanged.connect(self.source_changed.emit)
    
    def populate_sources(self, sources: List[Tuple[str, str, bool]]):
        """Remplit le sélecteur avec les sources disponibles."""
        self.clear()
        self.sources_data.clear()
        
        for source_name, display_text, has_data in sources:
            if has_data:
                # Source avec données disponibles
                display = f"📊 {display_text}"
                color = "#2d5f3f"  # Vert
            else:
                # Source sans données
                display = f"📝 {display_text} (manuel)"
                color = "#666666"  # Gris
            
            self.addItem(display, source_name)
            self.sources_data[source_name] = {"display": display_text, "has_data": has_data}


class SectionHeader(QFrame):
    """En-tête de section avec ligne de séparation."""
    
    def __init__(self, title: str, icon: str = "📖"):
        super().__init__()
        self.setup_ui(title, icon)
    


class PersonalInfoSection(QGroupBox):
    """Section des informations personnelles."""
    
    data_changed = Signal()
    
    def __init__(self, profile: UserProfile):
        super().__init__()
        self.profile = profile
        self.fields = {}
        self.setup_ui()
        # Sanitize all text-bearing widgets in this section
        sanitize_widget_tree(self)
        self.setTitle(f"{get_display_text('👤')} Informations personnelles")

    def setup_ui(self):
        """Set up the personal information section UI."""
        layout = QFormLayout()
        layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(8)

        # Extract CV data (use 'is not None' to handle empty dicts correctly)
        cv_name = cv_email = cv_phone = cv_linkedin = cv_location = ''
        if self.profile.extracted_personal_info is not None:
            cv_name = self.profile.extracted_personal_info.get('full_name', '') or \
                      self.profile.extracted_personal_info.get('name', '')
            cv_email = self.profile.extracted_personal_info.get('email', '')
            cv_phone = self.profile.extracted_personal_info.get('phone', '') or \
                       self.profile.extracted_personal_info.get('telephone', '')
            cv_linkedin = self.profile.extracted_personal_info.get('linkedin_url', '') or \
                          self.profile.extracted_personal_info.get('linkedin', '')
            cv_location = self.profile.extracted_personal_info.get('location', '') or \
                          self.profile.extracted_personal_info.get('city', '')

        # Extract LinkedIn data
        linkedin_name = linkedin_email = linkedin_phone = linkedin_url = linkedin_location = ''
        if self.profile.linkedin_data:
            linkedin_name = self.profile.linkedin_data.get('name', '') or \
                            self.profile.linkedin_data.get('full_name', '')
            linkedin_email = self.profile.linkedin_data.get('email', '')
            linkedin_phone = self.profile.linkedin_data.get('phone', '')
            linkedin_url = self.profile.linkedin_data.get('url', '') or \
                           self.profile.linkedin_data.get('linkedin_url', '')
            linkedin_location = self.profile.linkedin_data.get('location', '') or \
                                self.profile.linkedin_data.get('city', '')

        # Manual/current values
        manual_name = self.profile.name or ''
        manual_email = self.profile.email or ''
        manual_phone = self.profile.phone or ''
        manual_linkedin = self.profile.linkedin_url or ''
        manual_location = ''
        if self.profile.extracted_personal_info:
            manual_location = self.profile.extracted_personal_info.get('location', '') or ''

        # Create fields with source selectors
        self.create_field_with_source(layout, "Nom complet:", "full_name",
                                      cv_name, linkedin_name, manual_name)
        self.create_field_with_source(layout, "Email:", "email",
                                      cv_email, linkedin_email, manual_email)
        self.create_field_with_source(layout, "Téléphone:", "phone",
                                      cv_phone, linkedin_phone, manual_phone)
        self.create_field_with_source(layout, "LinkedIn:", "linkedin_url",
                                      cv_linkedin, linkedin_url, manual_linkedin)
        self.create_field_with_source(layout, "Localisation:", "location",
                                      cv_location, linkedin_location, manual_location)

        self.setLayout(layout)

    def create_field_with_source(self, layout: QFormLayout, label: str, field_name: str,
                                cv_value: str, linkedin_value: str, manual_value: str):
        """Crée un champ avec sélecteur de source."""
        container = QWidget()
        container_layout = QHBoxLayout()
        container_layout.setContentsMargins(0, 0, 0, 0)
        
        # Champ de saisie
        field = QLineEdit()
        field.setMinimumWidth(200)
        # Use lambda to ignore textChanged str argument (data_changed = Signal() has no params)
        field.textChanged.connect(lambda: self.data_changed.emit())

        # Sélecteur de source
        sources = []
        if cv_value:
            sources.append(("cv", "CV", True))
        if linkedin_value:
            sources.append(("linkedin", "LinkedIn", True))
        sources.append(("manual", "Manuel", True))

        source_selector = DataSourceSelector(sources)
        source_selector.setMaximumWidth(120)

        # Connecter le changement de source
        # SAFE: Store field reference as weak reference to avoid dangling pointers
        from weakref import ref as weakref_ref
        field_ref = weakref_ref(field)

        def on_source_changed(source_name):
            field_obj = field_ref()
            if field_obj is None:
                return  # Field has been deleted, do nothing

            if source_name == "cv" and cv_value:
                field_obj.setText(cv_value)
            elif source_name == "linkedin" and linkedin_value:
                field_obj.setText(linkedin_value)
            elif source_name == "manual":
                field_obj.setText(manual_value)

        source_selector.source_changed.connect(on_source_changed)
        
        # Définir la valeur initiale (priorité: manual -> linkedin -> cv)
        if manual_value:
            field.setText(manual_value)
            source_selector.setCurrentText("📝 Manuel (manuel)")
        elif linkedin_value:
            field.setText(linkedin_value)
            for i in range(source_selector.count()):
                if source_selector.itemData(i) == "linkedin":
                    source_selector.setCurrentIndex(i)
                    break
        elif cv_value:
            field.setText(cv_value)
            for i in range(source_selector.count()):
                if source_selector.itemData(i) == "cv":
                    source_selector.setCurrentIndex(i)
                    break
        
        container_layout.addWidget(field)
        container_layout.addWidget(QLabel("Source:"))
        container_layout.addWidget(source_selector)
        container.setLayout(container_layout)
        
        # Stocker les références
        self.fields[field_name] = {
            'field': field,
            'source_selector': source_selector,
            'cv_value': cv_value,
            'linkedin_value': linkedin_value,
            'manual_value': manual_value
        }
        
        layout.addRow(label, container)
    
    def get_data(self) -> Dict[str, Any]:
        """Retourne les données de la section."""
        data = {}
        for field_name, components in self.fields.items():
            data[field_name] = components['field'].text()
        return data
    
    def has_changes(self) -> bool:
        """Vérifie si des modifications ont été apportées."""
        for field_name, components in self.fields.items():
            current_value = components['field'].text()
            original_value = components['manual_value']
            if current_value != original_value:
                return True
        return False


class ExperienceItem(QFrame):
    """Widget pour une expérience professionnelle."""

    remove_requested = Signal(object)  # Émis quand on veut supprimer cet item
    data_changed = Signal()

    def __init__(self, experience_data: Dict[str, Any] = None):
        super().__init__()
        self.experience_data = experience_data or {}
        self.fields = {}
        # Stocker la source des données
        self.data_source = self.experience_data.get("source", "manual")
        self.setup_ui()
        sanitize_widget_tree(self)

    def setup_ui(self):
        """Set up the experience item UI."""
        self.setFrameStyle(QFrame.Box)
        self.setStyleSheet("""
            QFrame {
                background-color: #3a3a3a;
                border: 1px solid #555555;
                border-radius: 8px;
                padding: 12px;
                margin: 4px;
            }
            QFrame:hover {
                border: 1px solid #4db8ff;
            }
        """)

        layout = QVBoxLayout()
        layout.setSpacing(8)

        # Header with source badge, title, company and remove button
        header_layout = QHBoxLayout()

        # Badge de source des données
        self.source_badge = DataSourceBadge(self.data_source)
        header_layout.addWidget(self.source_badge)

        self.fields['title'] = QLineEdit(self.experience_data.get('title', ''))
        self.fields['title'].setPlaceholderText("Intitulé du poste...")
        self.fields['title'].textChanged.connect(lambda: self.data_changed.emit())
        header_layout.addWidget(QLabel("Poste:"))
        header_layout.addWidget(self.fields['title'], 2)

        self.fields['company'] = QLineEdit(self.experience_data.get('company', ''))
        self.fields['company'].setPlaceholderText("Entreprise...")
        self.fields['company'].textChanged.connect(lambda: self.data_changed.emit())
        header_layout.addWidget(QLabel("Entreprise:"))
        header_layout.addWidget(self.fields['company'], 2)

        remove_btn = QPushButton("🗑️")
        remove_btn.setMaximumWidth(30)
        remove_btn.setStyleSheet("""
            QPushButton {
                background: #dc2626;
                color: white;
                border: none;
                padding: 5px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background: #b91c1c;
            }
        """)
        remove_btn.clicked.connect(lambda: self.remove_requested.emit(self))
        header_layout.addWidget(remove_btn)
        layout.addLayout(header_layout)

        # Period and location
        period_layout = QHBoxLayout()
        self.fields['start_date'] = QLineEdit(self.experience_data.get('start_date', ''))
        self.fields['start_date'].setPlaceholderText("MM/YYYY")
        self.fields['start_date'].setMaximumWidth(100)
        self.fields['start_date'].textChanged.connect(lambda: self.data_changed.emit())

        self.fields['end_date'] = QLineEdit(self.experience_data.get('end_date', ''))
        self.fields['end_date'].setPlaceholderText("MM/YYYY ou Présent")
        self.fields['end_date'].setMaximumWidth(120)
        self.fields['end_date'].textChanged.connect(lambda: self.data_changed.emit())

        self.fields['location'] = QLineEdit(self.experience_data.get('location', ''))
        self.fields['location'].setPlaceholderText("Lieu...")
        self.fields['location'].textChanged.connect(lambda: self.data_changed.emit())

        period_layout.addWidget(QLabel("📅"))
        period_layout.addWidget(self.fields['start_date'])
        period_layout.addWidget(QLabel("-"))
        period_layout.addWidget(self.fields['end_date'])
        period_layout.addWidget(QLabel("📍"))
        period_layout.addWidget(self.fields['location'])
        period_layout.addStretch()
        layout.addLayout(period_layout)

        # Description
        self.fields['description'] = QTextEdit(self.experience_data.get('description', ''))
        self.fields['description'].setPlaceholderText("Description des responsabilités et réalisations...")
        self.fields['description'].setMaximumHeight(100)
        self.fields['description'].textChanged.connect(lambda: self.data_changed.emit())
        layout.addWidget(self.fields['description'])

        self.setLayout(layout)

    def get_data(self) -> Dict[str, Any]:
        """Retourne les données de l'expérience."""
        data = {
            'title': self.fields['title'].text(),
            'company': self.fields['company'].text(),
            'start_date': self.fields['start_date'].text(),
            'end_date': self.fields['end_date'].text(),
            'location': self.fields['location'].text(),
            'description': self.fields['description'].toPlainText(),
        }
        # Préserver la source des données
        if self.data_source:
            data['source'] = self.data_source
        return data
    
    def has_changes(self) -> bool:
        """Vérifie si des modifications ont été apportées."""
        current_data = self.get_data()
        return current_data != self.experience_data


class ExperienceSection(QGroupBox):
    """Section des expériences professionnelles."""
    
    data_changed = Signal()
    
    def __init__(self, profile: UserProfile):
        super().__init__()
        self.profile = profile
        self.experience_items = []
        self.setup_ui()
        sanitize_widget_tree(self)
        self.setTitle("💼 Expériences professionnelles")

    def setup_ui(self):
        """Set up the experiences section UI."""
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Add button
        header_layout = QHBoxLayout()
        add_btn = QPushButton("➕ Ajouter une expérience")
        add_btn.setStyleSheet("""
            QPushButton {
                background-color: #2d5f3f;
                color: white;
                border: none;
                padding: 10px 15px;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1e4f2f;
            }
        """)
        add_btn.clicked.connect(self.add_experience_item)
        header_layout.addWidget(add_btn)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Container for experience items
        self.experiences_container = QVBoxLayout()
        self.experiences_container.setSpacing(8)
        layout.addLayout(self.experiences_container)

        # Load existing experiences (use 'is not None' to handle empty lists correctly)
        if self.profile.extracted_experiences is not None:
            for exp in self.profile.extracted_experiences:
                self.add_experience_item(exp)

        layout.addStretch()
        self.setLayout(layout)

    def add_experience_item(self, experience_data: Dict[str, Any] = None):
        """Ajoute un nouvel item d'expérience."""
        experience_item = ExperienceItem(experience_data)
        experience_item.remove_requested.connect(self.remove_experience_item)
        experience_item.data_changed.connect(self.data_changed.emit)
        
        self.experience_items.append(experience_item)
        self.experiences_container.addWidget(experience_item)
    
    def remove_experience_item(self, item: ExperienceItem):
        """Supprime un item d'expérience."""
        if len(self.experience_items) > 1:  # Garder au moins une expérience
            self.experience_items.remove(item)
            self.experiences_container.removeWidget(item)
            item.deleteLater()
            self.data_changed.emit()
        else:
            QMessageBox.information(
                self,
                "Information",
                "Vous devez garder au moins une expérience professionnelle."
            )
    
    def get_data(self) -> List[Dict[str, Any]]:
        """Retourne les données de toutes les expériences."""
        return [item.get_data() for item in self.experience_items]
    
    def has_changes(self) -> bool:
        """Vérifie si des modifications ont été apportées."""
        return any(item.has_changes() for item in self.experience_items)


class EducationItem(QFrame):
    """Widget pour une formation."""

    remove_requested = Signal(object)
    data_changed = Signal()

    def __init__(self, education_data: Dict[str, Any] = None):
        super().__init__()
        self.education_data = education_data or {}
        self.fields = {}
        # Stocker la source des données
        self.data_source = self.education_data.get("source", "manual")
        self.setup_ui()
        sanitize_widget_tree(self)

    def setup_ui(self):
        """Set up the education item UI."""
        self.setFrameStyle(QFrame.Box)
        self.setStyleSheet("""
            QFrame {
                background-color: #3a3a3a;
                border: 1px solid #555555;
                border-radius: 8px;
                padding: 12px;
                margin: 4px;
            }
            QFrame:hover {
                border: 1px solid #4db8ff;
            }
        """)

        layout = QVBoxLayout()
        layout.setSpacing(8)

        # Header with source badge, school, degree and remove button
        header_layout = QHBoxLayout()

        # Badge de source des données
        self.source_badge = DataSourceBadge(self.data_source)
        header_layout.addWidget(self.source_badge)

        self.fields['school'] = QLineEdit(self.education_data.get('school', ''))
        self.fields['school'].setPlaceholderText("École / Université...")
        self.fields['school'].textChanged.connect(lambda: self.data_changed.emit())
        header_layout.addWidget(QLabel("École:"))
        header_layout.addWidget(self.fields['school'], 2)

        self.fields['degree'] = QLineEdit(self.education_data.get('degree', ''))
        self.fields['degree'].setPlaceholderText("Diplôme...")
        self.fields['degree'].textChanged.connect(lambda: self.data_changed.emit())
        header_layout.addWidget(QLabel("Diplôme:"))
        header_layout.addWidget(self.fields['degree'], 2)

        remove_btn = QPushButton("🗑️")
        remove_btn.setMaximumWidth(30)
        remove_btn.setStyleSheet("""
            QPushButton {
                background: #dc2626;
                color: white;
                border: none;
                padding: 5px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background: #b91c1c;
            }
        """)
        remove_btn.clicked.connect(lambda: self.remove_requested.emit(self))
        header_layout.addWidget(remove_btn)
        layout.addLayout(header_layout)

        # Field of study, period and grade
        details_layout = QHBoxLayout()
        self.fields['field_of_study'] = QLineEdit(self.education_data.get('field_of_study', ''))
        self.fields['field_of_study'].setPlaceholderText("Domaine d'études...")
        self.fields['field_of_study'].textChanged.connect(lambda: self.data_changed.emit())
        details_layout.addWidget(QLabel("Domaine:"))
        details_layout.addWidget(self.fields['field_of_study'], 2)

        self.fields['start_date'] = QLineEdit(self.education_data.get('start_date', ''))
        self.fields['start_date'].setPlaceholderText("MM/YYYY")
        self.fields['start_date'].setMaximumWidth(100)
        self.fields['start_date'].textChanged.connect(lambda: self.data_changed.emit())

        self.fields['end_date'] = QLineEdit(self.education_data.get('end_date', ''))
        self.fields['end_date'].setPlaceholderText("MM/YYYY")
        self.fields['end_date'].setMaximumWidth(100)
        self.fields['end_date'].textChanged.connect(lambda: self.data_changed.emit())

        self.fields['grade'] = QLineEdit(self.education_data.get('grade', ''))
        self.fields['grade'].setPlaceholderText("Mention...")
        self.fields['grade'].setMaximumWidth(120)
        self.fields['grade'].textChanged.connect(lambda: self.data_changed.emit())

        details_layout.addWidget(QLabel("📅"))
        details_layout.addWidget(self.fields['start_date'])
        details_layout.addWidget(QLabel("-"))
        details_layout.addWidget(self.fields['end_date'])
        details_layout.addWidget(QLabel("🏆"))
        details_layout.addWidget(self.fields['grade'])
        details_layout.addStretch()
        layout.addLayout(details_layout)

        self.setLayout(layout)

    def get_data(self) -> Dict[str, Any]:
        """Retourne les données de la formation."""
        data = {
            'school': self.fields['school'].text(),
            'degree': self.fields['degree'].text(),
            'field_of_study': self.fields['field_of_study'].text(),
            'start_date': self.fields['start_date'].text(),
            'end_date': self.fields['end_date'].text(),
            'grade': self.fields['grade'].text(),
        }
        # Préserver la source des données
        if self.data_source:
            data['source'] = self.data_source
        return data

    def has_changes(self) -> bool:
        """Vérifie si des modifications ont été apportées."""
        current_data = self.get_data()
        return current_data != self.education_data


class EducationSection(QGroupBox):
    """Section des formations."""

    data_changed = Signal()

    def __init__(self, profile: UserProfile):
        super().__init__()
        self.profile = profile
        self.education_items = []
        self.setup_ui()
        sanitize_widget_tree(self)
        self.setTitle("🎓 Formation")

    def setup_ui(self):
        """Set up the education section UI."""
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Add button
        header_layout = QHBoxLayout()
        add_btn = QPushButton("➕ Ajouter une formation")
        add_btn.setStyleSheet("""
            QPushButton {
                background-color: #2d5f3f;
                color: white;
                border: none;
                padding: 10px 15px;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1e4f2f;
            }
        """)
        add_btn.clicked.connect(self.add_education_item)
        header_layout.addWidget(add_btn)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Container for education items
        self.education_container = QVBoxLayout()
        self.education_container.setSpacing(8)
        layout.addLayout(self.education_container)

        # Load existing education (use 'is not None' to handle empty lists correctly)
        if self.profile.extracted_education is not None:
            for edu in self.profile.extracted_education:
                self.add_education_item(edu)

        layout.addStretch()
        self.setLayout(layout)

    def add_education_item(self, education_data: Dict[str, Any] = None):
        """Ajoute un nouvel item de formation."""
        education_item = EducationItem(education_data)
        education_item.remove_requested.connect(self.remove_education_item)
        education_item.data_changed.connect(self.data_changed.emit)
        
        self.education_items.append(education_item)
        self.education_container.addWidget(education_item)
    
    def remove_education_item(self, item: EducationItem):
        """Supprime un item de formation."""
        if len(self.education_items) > 1:
            self.education_items.remove(item)
            self.education_container.removeWidget(item)
            item.deleteLater()
            self.data_changed.emit()
        else:
            QMessageBox.information(
                self,
                "Information",
                "Vous devez garder au moins une formation."
            )
    
    def get_data(self) -> List[Dict[str, Any]]:
        """Retourne les données de toutes les formations."""
        return [item.get_data() for item in self.education_items]
    
    def has_changes(self) -> bool:
        """Vérifie si des modifications ont été apportées."""
        return any(item.has_changes() for item in self.education_items)


class SkillItem(QFrame):
    """Widget pour une compétence."""

    remove_requested = Signal(object)
    data_changed = Signal()

    def __init__(self, skill_data: Dict[str, Any] = None):
        super().__init__()
        self.skill_data = skill_data or {}
        self.fields = {}
        self.setup_ui()
        sanitize_widget_tree(self)

    def setup_ui(self):
        """Set up the skill item UI."""
        self.setFrameStyle(QFrame.Box)
        self.setStyleSheet("""
            QFrame {
                background-color: #3a3a3a;
                border: 1px solid #555555;
                border-radius: 8px;
                padding: 12px;
                margin: 4px;
            }
            QFrame:hover {
                border: 1px solid #4db8ff;
            }
        """)

        layout = QHBoxLayout()
        layout.setSpacing(8)

        self.fields['name'] = QLineEdit(self.skill_data.get('name', ''))
        self.fields['name'].setPlaceholderText("Nom de la compétence...")
        self.fields['name'].textChanged.connect(lambda: self.data_changed.emit())
        layout.addWidget(QLabel("Compétence:"))
        layout.addWidget(self.fields['name'], 3)

        self.fields['level'] = QComboBox()
        self.fields['level'].addItems(["Débutant", "Intermédiaire", "Avancé", "Expert"])
        current_level = self.skill_data.get('level', '')
        if current_level in ["Débutant", "Intermédiaire", "Avancé", "Expert"]:
            self.fields['level'].setCurrentText(current_level)
        self.fields['level'].currentTextChanged.connect(lambda: self.data_changed.emit())
        layout.addWidget(QLabel("Niveau:"))
        layout.addWidget(self.fields['level'], 1)

        remove_btn = QPushButton("🗑️")
        remove_btn.setMaximumWidth(30)
        remove_btn.setStyleSheet("""
            QPushButton {
                background: #dc2626;
                color: white;
                border: none;
                padding: 5px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background: #b91c1c;
            }
        """)
        remove_btn.clicked.connect(lambda: self.remove_requested.emit(self))
        layout.addWidget(remove_btn)

        self.setLayout(layout)

    def get_data(self) -> Dict[str, Any]:
        """Retourne les données de la compétence."""
        return {
            'name': self.fields['name'].text(),
            'level': self.fields['level'].currentText()
        }
    
    def has_changes(self) -> bool:
        """Vérifie si des modifications ont été apportées."""
        current_data = self.get_data()
        return current_data != self.skill_data


class SkillsSection(QGroupBox):
    """Section des compétences."""
    
    data_changed = Signal()
    
    def __init__(self, profile: UserProfile):
        super().__init__()
        self.profile = profile
        self.skill_items = []
        self.setup_ui()
        sanitize_widget_tree(self)
        self.setTitle(f"{get_display_text('🛠️')} Compétences")

    def setup_ui(self):
        """Set up the skills section UI."""
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Add button
        header_layout = QHBoxLayout()
        add_btn = QPushButton("➕ Ajouter une compétence")
        add_btn.setStyleSheet("""
            QPushButton {
                background-color: #2d5f3f;
                color: white;
                border: none;
                padding: 10px 15px;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1e4f2f;
            }
        """)
        add_btn.clicked.connect(self.add_skill_item)
        header_layout.addWidget(add_btn)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Container for skill items
        self.skills_container = QVBoxLayout()
        self.skills_container.setSpacing(8)
        layout.addLayout(self.skills_container)

        # Load existing skills (use 'is not None' to handle empty dicts/lists correctly)
        if self.profile.extracted_skills is not None:
            for skill in self.profile.extracted_skills:
                self.add_skill_item(skill)

        layout.addStretch()
        self.setLayout(layout)

    def add_skill_item(self, skill_data: Dict[str, Any] = None):
        """Ajoute un nouvel item de compétence."""
        skill_item = SkillItem(skill_data)
        skill_item.remove_requested.connect(self.remove_skill_item)
        skill_item.data_changed.connect(self.data_changed.emit)
        
        self.skill_items.append(skill_item)
        self.skills_container.addWidget(skill_item)
    
    def remove_skill_item(self, item: SkillItem):
        """Supprime un item de compétence."""
        self.skill_items.remove(item)
        self.skills_container.removeWidget(item)
        item.deleteLater()
        self.data_changed.emit()
    
    def get_data(self) -> List[Dict[str, Any]]:
        """Retourne les données de toutes les compétences."""
        return [item.get_data() for item in self.skill_items if item.get_data().get('name', '').strip()]
    
    def has_changes(self) -> bool:
        """Vérifie si des modifications ont été apportées."""
        return any(item.has_changes() for item in self.skill_items)


class SoftSkillItem(QFrame):
    """Widget pour une soft skill."""

    remove_requested = Signal(object)
    data_changed = Signal()

    def __init__(self, skill_data: Dict[str, Any] = None):
        super().__init__()
        self.skill_data = skill_data or {}
        self.fields = {}
        self.setup_ui()
        sanitize_widget_tree(self)

    def setup_ui(self):
        """Set up the soft skill item UI."""
        self.setFrameStyle(QFrame.Box)
        self.setStyleSheet("""
            QFrame {
                background-color: #3a3a3a;
                border: 1px solid #555555;
                border-radius: 8px;
                padding: 12px;
                margin: 4px;
            }
            QFrame:hover {
                border: 1px solid #4db8ff;
            }
        """)

        layout = QHBoxLayout()
        layout.setSpacing(8)

        self.fields['name'] = QLineEdit(self.skill_data.get('name', ''))
        self.fields['name'].setPlaceholderText("Soft skill...")
        self.fields['name'].textChanged.connect(lambda: self.data_changed.emit())
        layout.addWidget(QLabel("Soft skill:"))
        layout.addWidget(self.fields['name'], 3)

        self.fields['level'] = QComboBox()
        self.fields['level'].addItems(["Débutant", "Intermédiaire", "Avancé", "Expert"])
        current_level = self.skill_data.get('level', '')
        if current_level in ["Débutant", "Intermédiaire", "Avancé", "Expert"]:
            self.fields['level'].setCurrentText(current_level)
        self.fields['level'].currentTextChanged.connect(lambda: self.data_changed.emit())
        layout.addWidget(QLabel("Niveau:"))
        layout.addWidget(self.fields['level'], 1)

        remove_btn = QPushButton("🗑️")
        remove_btn.setMaximumWidth(30)
        remove_btn.setStyleSheet("""
            QPushButton {
                background: #dc2626;
                color: white;
                border: none;
                padding: 5px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background: #b91c1c;
            }
        """)
        remove_btn.clicked.connect(lambda: self.remove_requested.emit(self))
        layout.addWidget(remove_btn)

        self.setLayout(layout)

    def get_data(self) -> Dict[str, Any]:
        """Retourne les données de la soft skill."""
        return {
            'name': self.fields['name'].text(),
            'level': self.fields['level'].currentText()
        }

    def has_changes(self) -> bool:
        """Vérifie si des modifications ont été apportées."""
        current_data = self.get_data()
        return current_data != self.skill_data


class SoftSkillsSection(QGroupBox):
    """Section des soft skills."""

    data_changed = Signal()

    def __init__(self, profile: UserProfile):
        super().__init__()
        self.profile = profile
        self.skill_items = []
        self.setup_ui()
        sanitize_widget_tree(self)
        self.setTitle(f"{get_display_text('🧠')} Soft skills")

    def setup_ui(self):
        """Set up the soft skills section UI."""
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        header_layout = QHBoxLayout()
        add_btn = QPushButton("➕ Ajouter une soft skill")
        add_btn.setStyleSheet("""
            QPushButton {
                background-color: #2d5f3f;
                color: white;
                border: none;
                padding: 10px 15px;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1e4f2f;
            }
        """)
        add_btn.clicked.connect(self.add_skill_item)
        header_layout.addWidget(add_btn)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        self.skills_container = QVBoxLayout()
        self.skills_container.setSpacing(8)
        layout.addLayout(self.skills_container)

        if self.profile.extracted_soft_skills is not None:
            for skill in self.profile.extracted_soft_skills:
                self.add_skill_item(skill)

        layout.addStretch()
        self.setLayout(layout)

    def add_skill_item(self, skill_data: Dict[str, Any] = None):
        """Ajoute un nouvel item de soft skill."""
        skill_item = SoftSkillItem(skill_data)
        skill_item.remove_requested.connect(self.remove_skill_item)
        skill_item.data_changed.connect(self.data_changed.emit)

        self.skill_items.append(skill_item)
        self.skills_container.addWidget(skill_item)

    def remove_skill_item(self, item: SoftSkillItem):
        """Supprime un item de soft skill."""
        self.skill_items.remove(item)
        self.skills_container.removeWidget(item)
        item.deleteLater()
        self.data_changed.emit()

    def get_data(self) -> List[Dict[str, Any]]:
        """Retourne les données de toutes les soft skills."""
        return [item.get_data() for item in self.skill_items if item.get_data().get('name', '').strip()]

    def has_changes(self) -> bool:
        """Vérifie si des modifications ont été apportées."""
        return any(item.has_changes() for item in self.skill_items)


class LanguageItem(QFrame):
    """Widget pour une langue."""

    remove_requested = Signal(object)
    data_changed = Signal()

    def __init__(self, language_data: Dict[str, Any] = None):
        super().__init__()
        self.language_data = language_data or {}
        self.fields = {}
        self.setup_ui()
        sanitize_widget_tree(self)

    def setup_ui(self):
        """Set up the language item UI."""
        self.setFrameStyle(QFrame.Box)
        self.setStyleSheet("""
            QFrame {
                background-color: #3a3a3a;
                border: 1px solid #555555;
                border-radius: 8px;
                padding: 12px;
                margin: 4px;
            }
            QFrame:hover {
                border: 1px solid #4db8ff;
            }
        """)

        layout = QHBoxLayout()
        layout.setSpacing(8)

        self.fields['language'] = QLineEdit(self.language_data.get('language', ''))
        self.fields['language'].setPlaceholderText("Langue...")
        self.fields['language'].textChanged.connect(lambda: self.data_changed.emit())
        layout.addWidget(QLabel("Langue:"))
        layout.addWidget(self.fields['language'], 3)

        self.fields['proficiency'] = QComboBox()
        self.fields['proficiency'].addItems(["A1", "A2", "B1", "B2", "C1", "C2", "Natif"])
        current_proficiency = self.language_data.get('proficiency', '')
        if current_proficiency in ["A1", "A2", "B1", "B2", "C1", "C2", "Natif"]:
            self.fields['proficiency'].setCurrentText(current_proficiency)
        self.fields['proficiency'].currentTextChanged.connect(lambda: self.data_changed.emit())
        layout.addWidget(QLabel("Niveau:"))
        layout.addWidget(self.fields['proficiency'], 1)

        remove_btn = QPushButton("🗑️")
        remove_btn.setMaximumWidth(30)
        remove_btn.setStyleSheet("""
            QPushButton {
                background: #dc2626;
                color: white;
                border: none;
                padding: 5px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background: #b91c1c;
            }
        """)
        remove_btn.clicked.connect(lambda: self.remove_requested.emit(self))
        layout.addWidget(remove_btn)

        self.setLayout(layout)

    def get_data(self) -> Dict[str, Any]:
        """Retourne les données de la langue."""
        return {
            'language': self.fields['language'].text(),
            'proficiency': self.fields['proficiency'].currentText()
        }
    
    def has_changes(self) -> bool:
        """Vérifie si des modifications ont été apportées."""
        current_data = self.get_data()
        return current_data != self.language_data


class LanguagesSection(QGroupBox):
    """Section des langues."""
    
    data_changed = Signal()
    
    def __init__(self, profile: UserProfile):
        super().__init__()
        self.profile = profile
        self.language_items = []
        self.setup_ui()
        sanitize_widget_tree(self)
        self.setTitle(f"{get_display_text('🌐')} Langues")

    def setup_ui(self):
        """Set up the languages section UI."""
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Add button
        header_layout = QHBoxLayout()
        add_btn = QPushButton("➕ Ajouter une langue")
        add_btn.setStyleSheet("""
            QPushButton {
                background-color: #2d5f3f;
                color: white;
                border: none;
                padding: 10px 15px;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1e4f2f;
            }
        """)
        add_btn.clicked.connect(self.add_language_item)
        header_layout.addWidget(add_btn)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Container for language items
        self.languages_container = QVBoxLayout()
        self.languages_container.setSpacing(8)
        layout.addLayout(self.languages_container)

        # Load existing languages (use 'is not None' to handle empty lists correctly)
        if self.profile.extracted_languages is not None:
            for lang in self.profile.extracted_languages:
                self.add_language_item(lang)

        layout.addStretch()
        self.setLayout(layout)

    def add_language_item(self, language_data: Dict[str, Any] = None):
        """Ajoute un nouvel item de langue."""
        language_item = LanguageItem(language_data)
        language_item.remove_requested.connect(self.remove_language_item)
        language_item.data_changed.connect(self.data_changed.emit)
        
        self.language_items.append(language_item)
        self.languages_container.addWidget(language_item)
    
    def remove_language_item(self, item: LanguageItem):
        """Supprime un item de langue."""
        self.language_items.remove(item)
        self.languages_container.removeWidget(item)
        item.deleteLater()
        self.data_changed.emit()
    
    def get_data(self) -> List[Dict[str, Any]]:
        """Retourne les données de toutes les langues."""
        return [item.get_data() for item in self.language_items if item.get_data().get('language', '').strip()]
    
    def has_changes(self) -> bool:
        """Vérifie si des modifications ont été apportées."""
        return any(item.has_changes() for item in self.language_items)


class ProjectItem(QFrame):
    """Widget pour un projet."""

    remove_requested = Signal(object)
    data_changed = Signal()

    def __init__(self, project_data: Dict[str, Any] = None):
        super().__init__()
        self.project_data = project_data or {}
        self.fields = {}
        self.setup_ui()
        sanitize_widget_tree(self)

    def setup_ui(self):
        """Set up the project item UI."""
        self.setFrameStyle(QFrame.Box)
        self.setStyleSheet("""
            QFrame {
                background-color: #3a3a3a;
                border: 1px solid #555555;
                border-radius: 8px;
                padding: 12px;
                margin: 4px;
            }
            QFrame:hover {
                border: 1px solid #4db8ff;
            }
        """)

        layout = QVBoxLayout()
        layout.setSpacing(8)

        # Header with name and remove button
        header_layout = QHBoxLayout()
        self.fields['name'] = QLineEdit(self.project_data.get('name', ''))
        self.fields['name'].setPlaceholderText("Nom du projet...")
        self.fields['name'].textChanged.connect(lambda: self.data_changed.emit())
        header_layout.addWidget(QLabel("Projet:"))
        header_layout.addWidget(self.fields['name'], 3)

        remove_btn = QPushButton("🗑️")
        remove_btn.setMaximumWidth(30)
        remove_btn.setStyleSheet("""
            QPushButton {
                background: #dc2626;
                color: white;
                border: none;
                padding: 5px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background: #b91c1c;
            }
        """)
        remove_btn.clicked.connect(lambda: self.remove_requested.emit(self))
        header_layout.addWidget(remove_btn)
        layout.addLayout(header_layout)

        # URL and technologies
        details_layout = QHBoxLayout()
        self.fields['url'] = QLineEdit(self.project_data.get('url', ''))
        self.fields['url'].setPlaceholderText("URL du projet...")
        self.fields['url'].textChanged.connect(lambda: self.data_changed.emit())
        details_layout.addWidget(QLabel("URL:"))
        details_layout.addWidget(self.fields['url'], 2)

        self.fields['technologies'] = QLineEdit(self.project_data.get('technologies', ''))
        self.fields['technologies'].setPlaceholderText("Technologies utilisées...")
        self.fields['technologies'].textChanged.connect(lambda: self.data_changed.emit())
        details_layout.addWidget(QLabel("Technologies:"))
        details_layout.addWidget(self.fields['technologies'], 2)
        layout.addLayout(details_layout)

        # Description
        self.fields['description'] = QTextEdit(self.project_data.get('description', ''))
        self.fields['description'].setPlaceholderText("Description du projet...")
        self.fields['description'].setMaximumHeight(80)
        self.fields['description'].textChanged.connect(lambda: self.data_changed.emit())
        layout.addWidget(self.fields['description'])

        self.setLayout(layout)

    def get_data(self) -> Dict[str, Any]:
        """Retourne les données du projet."""
        return {
            'name': self.fields['name'].text(),
            'url': self.fields['url'].text(),
            'technologies': self.fields['technologies'].text(),
            'description': self.fields['description'].toPlainText()
        }
    
    def has_changes(self) -> bool:
        """Vérifie si des modifications ont été apportées."""
        current_data = self.get_data()
        return current_data != self.project_data


class ProjectsSection(QGroupBox):
    """Section des projets."""

    data_changed = Signal()

    def __init__(self, profile: UserProfile):
        super().__init__()
        self.profile = profile
        self.project_items = []
        self.setup_ui()
        sanitize_widget_tree(self)
        self.setTitle("🚀 Projets")

    def setup_ui(self):
        """Set up the projects section UI."""
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Add button
        header_layout = QHBoxLayout()
        add_btn = QPushButton("➕ Ajouter un projet")
        add_btn.setStyleSheet("""
            QPushButton {
                background-color: #2d5f3f;
                color: white;
                border: none;
                padding: 10px 15px;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1e4f2f;
            }
        """)
        add_btn.clicked.connect(self.add_project_item)
        header_layout.addWidget(add_btn)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Container for project items
        self.projects_container = QVBoxLayout()
        self.projects_container.setSpacing(8)
        layout.addLayout(self.projects_container)

        # Load existing projects (use 'is not None' to handle empty lists correctly)
        if self.profile.extracted_projects is not None:
            for project in self.profile.extracted_projects:
                self.add_project_item(project)

        layout.addStretch()
        self.setLayout(layout)

    def add_project_item(self, project_data: Dict[str, Any] = None):
        """Ajoute un nouvel item de projet."""
        project_item = ProjectItem(project_data)
        project_item.remove_requested.connect(self.remove_project_item)
        project_item.data_changed.connect(self.data_changed.emit)
        
        self.project_items.append(project_item)
        self.projects_container.addWidget(project_item)
    
    def remove_project_item(self, item: ProjectItem):
        """Supprime un item de projet."""
        self.project_items.remove(item)
        self.projects_container.removeWidget(item)
        item.deleteLater()
        self.data_changed.emit()
    
    def get_data(self) -> List[Dict[str, Any]]:
        """Retourne les données de tous les projets."""
        return [item.get_data() for item in self.project_items if item.get_data().get('name', '').strip()]
    
    def has_changes(self) -> bool:
        """Vérifie si des modifications ont été apportées."""
        return any(item.has_changes() for item in self.project_items)


class SimpleListSection(QGroupBox):
    """Section pour les listes simples (certifications, publications, etc.)."""
    
    data_changed = Signal()
    
    def __init__(self, profile: UserProfile, section_name: str, title: str, icon: str, 
                 fields_config: List[Tuple[str, str, str]] = None):
        """
        Args:
            profile: Profil utilisateur
            section_name: Nom du champ dans le profil (ex: 'extracted_certifications')
            title: Titre affiché
            icon: Icône de la section
            fields_config: Liste de (field_name, label, placeholder)
        """
        super().__init__()
        self.profile = profile
        self.section_name = section_name
        self.fields_config = fields_config or [("name", "Nom:", "")]
        self.items = []
        self.setup_ui(title, icon)
        self.setTitle(f"{icon} {title}")

    def setup_ui(self, title: str, icon: str):
        """Set up the simple list section UI."""
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Add button
        header_layout = QHBoxLayout()
        add_btn = QPushButton(f"➕ Ajouter {title.lower()}")
        add_btn.setStyleSheet("""
            QPushButton {
                background-color: #2d5f3f;
                color: white;
                border: none;
                padding: 10px 15px;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1e4f2f;
            }
        """)
        add_btn.clicked.connect(self.add_item)
        header_layout.addWidget(add_btn)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Container for items
        self.items_container = QVBoxLayout()
        self.items_container.setSpacing(8)
        layout.addLayout(self.items_container)

        # Load existing data from profile
        existing_data = getattr(self.profile, self.section_name, None) or []
        if existing_data:
            for item in existing_data:
                self.add_item(item)

        layout.addStretch()
        self.setLayout(layout)

    def add_item(self, item_data: Dict[str, Any] = None):
        """Ajoute un nouvel item."""
        item_data = item_data or {}
        
        item_frame = QFrame()
        item_frame.setFrameStyle(QFrame.Box)
        # Style géré par le style global
        
        layout = QVBoxLayout()
        
        # En-tête avec bouton supprimer
        header_layout = QHBoxLayout()
        header_layout.addStretch()
        
        remove_btn = QPushButton("🗑️")
        remove_btn.setMaximumWidth(30)
        remove_btn.setStyleSheet("QPushButton { background: #dc2626; color: white; border: none; padding: 5px; border-radius: 3px; } QPushButton:hover { background: #b91c1c; }")
        remove_btn.clicked.connect(lambda: self.remove_item(item_frame))
        header_layout.addWidget(remove_btn)
        layout.addLayout(header_layout)
        
        # Champs
        form_layout = QFormLayout()
        fields = {}
        
        for field_name, label, placeholder in self.fields_config:
            if field_name == "description":
                field = QTextEdit(item_data.get(field_name, ''))
                field.setMaximumHeight(80)
            else:
                field = QLineEdit(item_data.get(field_name, ''))
                if placeholder:
                    field.setPlaceholderText(placeholder)

            # Use lambda to ignore textChanged str argument (data_changed = Signal() has no params)
            field.textChanged.connect(lambda: self.data_changed.emit())
            fields[field_name] = field
            form_layout.addRow(label, field)
        
        layout.addLayout(form_layout)
        item_frame.setLayout(layout)
        
        # Stocker les références
        item_frame.fields = fields
        item_frame.original_data = item_data
        
        self.items.append(item_frame)
        self.items_container.addWidget(item_frame)
    
    def remove_item(self, item_frame):
        """Supprime un item."""
        self.items.remove(item_frame)
        self.items_container.removeWidget(item_frame)
        item_frame.deleteLater()
        self.data_changed.emit()
    
    def get_data(self) -> List[Dict[str, Any]]:
        """Retourne les données de tous les items."""
        data = []
        for item_frame in self.items:
            item_data = {}
            for field_name, field in item_frame.fields.items():
                if isinstance(field, QTextEdit):
                    value = field.toPlainText()
                else:
                    value = field.text()
                if value.strip():
                    item_data[field_name] = value
            
            # N'ajouter que si au moins un champ est rempli
            if any(v.strip() for v in item_data.values()):
                data.append(item_data)
        
        return data
    
    def has_changes(self) -> bool:
        """Vérifie si des modifications ont été apportées."""
        current_data = self.get_data()
        original_data = getattr(self.profile, self.section_name, None) or []
        return current_data != original_data


class InterestsSection(QGroupBox):
    """Section des centres d'intérêt (liste simple de mots-clés)."""

    data_changed = Signal()

    def __init__(self, profile: UserProfile):
        super().__init__()
        self.profile = profile
        self.setup_ui()
        sanitize_widget_tree(self)
        self.setTitle("🎯 Centres d'intérêt")

    def setup_ui(self):
        """Set up the interests section UI."""
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        instructions = QLabel("Listez vos centres d'intérêt séparés par des virgules.\nExemple: Lecture, Sport, Voyages, Musique")
        instructions.setStyleSheet("color: #a0a0a0; font-style: italic;")
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        self.interests_text = QTextEdit()
        self.interests_text.setMaximumHeight(100)
        self.interests_text.setPlaceholderText("Vos centres d'intérêt...")
        # Use lambda to ignore textChanged str argument (data_changed = Signal() has no params)
        self.interests_text.textChanged.connect(lambda: self.data_changed.emit())

        # Load existing interests
        existing = self.profile.extracted_interests or []
        if existing:
            if isinstance(existing, list):
                if existing and isinstance(existing[0], dict):
                    names = [item.get('name', str(item)) for item in existing]
                    text = ', '.join(names)
                else:
                    text = ', '.join(str(i) for i in existing)
            else:
                text = str(existing)
            self.interests_text.setPlainText(text)

        layout.addWidget(self.interests_text)
        layout.addStretch()
        self.setLayout(layout)

    def get_data(self) -> List[str]:
        """Retourne les données des centres d'intérêt."""
        text = self.interests_text.toPlainText()
        if not text.strip():
            return []
        
        # Séparer par virgules et nettoyer
        interests = [interest.strip() for interest in text.split(',')]
        return [interest for interest in interests if interest]
    
    def has_changes(self) -> bool:
        """Vérifie si des modifications ont été apportées."""
        current_data = self.get_data()
        original_data = self.profile.extracted_interests or []
        return current_data != original_data


class ProfileDetailsEditor(QScrollArea):
    """Éditeur complet des détails du profil."""
    
    profile_updated = Signal(UserProfile)
    
    def __init__(self, profile: UserProfile, parent=None):
        super().__init__(parent)
        self.profile = profile
        self.sections = {}
        self.has_unsaved_changes = False
        self._refreshing = False  # Flag pour ignorer les signaux pendant refresh

        # Chemin du fichier cache
        self.cache_file_path = self._get_cache_file_path()
        
        # Vérifier et restaurer depuis le cache persistant si nécessaire
        self._check_and_restore_from_persistent_cache()
        
        # Charger ou créer le cache des données sauvegardées
        self.original_data_cache = self._load_or_create_cache()
        
        # Sauvegarder un checkpoint des données propres
        self._save_persistent_cache()
        
        self.setup_ui()
        sanitize_widget_tree(self)
    
    def setup_ui(self):
        self.setWindowTitle("Détails du profil")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        # Appliquer le style sombre cohérent
        self.setStyleSheet(f"""
            QScrollArea {{
                background-color: {StyleManager.COLORS['dark']};
                border: none;
            }}
            QWidget {{
                background-color: {StyleManager.COLORS['dark']};
                color: {StyleManager.COLORS['text_dark']};
            }}
            QGroupBox {{
                background-color: {StyleManager.COLORS['background_dark']};
                border: 1px solid {StyleManager.COLORS['border']};
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
                font-weight: bold;
                color: {StyleManager.COLORS['text_dark']};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 10px 0 10px;
                color: {StyleManager.COLORS['focus']};
                font-size: 14px;
            }}
            QLineEdit {{
                background-color: {StyleManager.COLORS['background_dark']};
                border: 1px solid {StyleManager.COLORS['border']};
                border-radius: 4px;
                padding: 8px;
                color: {StyleManager.COLORS['text_dark']};
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border: 2px solid {StyleManager.COLORS['focus']};
                background-color: {StyleManager.COLORS['background_dark']};
            }}
            QTextEdit {{
                background-color: {StyleManager.COLORS['background_dark']};
                border: 1px solid {StyleManager.COLORS['border']};
                border-radius: 4px;
                padding: 8px;
                color: {StyleManager.COLORS['text_dark']};
                font-size: 13px;
            }}
            QTextEdit:focus {{
                border: 2px solid {StyleManager.COLORS['focus']};
                background-color: {StyleManager.COLORS['background_dark']};
            }}
            QComboBox {{
                background-color: {StyleManager.COLORS['background_dark']};
                border: 1px solid {StyleManager.COLORS['border']};
                border-radius: 4px;
                padding: 8px;
                color: {StyleManager.COLORS['text_dark']};
                font-size: 13px;
                min-width: 100px;
            }}
            QComboBox:hover {{
                border: 1px solid {StyleManager.COLORS['focus']};
            }}
            QComboBox::drop-down {{
                background-color: {StyleManager.COLORS['background_dark']};
                border-left: 1px solid {StyleManager.COLORS['border']};
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid {StyleManager.COLORS['text_dark']};
            }}
            QComboBox QAbstractItemView {{
                background-color: {StyleManager.COLORS['background_dark']};
                border: 1px solid {StyleManager.COLORS['border']};
                selection-background-color: {StyleManager.COLORS['focus']};
                color: {StyleManager.COLORS['text_dark']};
            }}
            QLabel {{
                color: {StyleManager.COLORS['text_dark']};
                font-size: 13px;
            }}
            QFrame {{
                background-color: {StyleManager.COLORS['background_dark']};
                border: 1px solid {StyleManager.COLORS['border']};
                border-radius: 5px;
            }}
            QFrame[frameShape="4"] {{
                color: {StyleManager.COLORS['border']};
                background-color: {StyleManager.COLORS['border']};
            }}
        """)
        
        # Widget principal
        main_widget = QWidget()
        main_layout = QVBoxLayout()
        
        # En-tête avec boutons sauvegarde et annulation
        header_layout = QHBoxLayout()
        title_label = QLabel("Édition des détails du profil")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #4db8ff; padding: 10px 0px;")
        
        # Boutons d'action
        buttons_layout = QHBoxLayout()
        # Boutons import/export JSON
        self.import_json_button = QPushButton("Importer JSON")
        apply_button_style(self.import_json_button, "info")
        self.import_json_button.clicked.connect(self.import_profile_json)

        self.export_json_button = QPushButton("Exporter JSON")
        apply_button_style(self.export_json_button, "info")
        self.export_json_button.clicked.connect(self.export_profile_json)

        
        # Bouton annuler (revenir au cache)
        self.cancel_button = QPushButton("↩️ Annuler les modifications")
        self.cancel_button.setEnabled(False)  # Désactivé par défaut
        apply_button_style(self.cancel_button, "secondary")
        self.cancel_button.clicked.connect(self.cancel_changes)
        
        # Bouton sauvegarder
        self.save_button = QPushButton("💾 Sauvegarder")
        self.save_button.setEnabled(False)  # Désactivé par défaut
        apply_button_style(self.save_button, "primary")
        self.save_button.clicked.connect(self.save_changes)
        
        buttons_layout.addWidget(self.import_json_button)
        buttons_layout.addWidget(self.export_json_button)
        buttons_layout.addWidget(self.cancel_button)
        buttons_layout.addWidget(self.save_button)
        
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        header_layout.addLayout(buttons_layout)
        main_layout.addLayout(header_layout)
        
        # Sections
        self.create_sections(main_layout)
        
        # Footer avec boutons d'action fixes
        self.create_footer(main_layout)
        
        main_widget.setLayout(main_layout)
        self.setWidget(main_widget)
        # Final text sanitization for the full editor tree
        sanitize_widget_tree(self)
    
    def create_sections(self, main_layout: QVBoxLayout):
        """Crée toutes les sections de l'éditeur."""
        
        # Section informations personnelles
        self.sections['personal'] = PersonalInfoSection(self.profile)
        self.sections['personal'].data_changed.connect(self.on_data_changed)
        main_layout.addWidget(self.sections['personal'])
        
        # Section expériences
        self.sections['experiences'] = ExperienceSection(self.profile)
        self.sections['experiences'].data_changed.connect(self.on_data_changed)
        main_layout.addWidget(self.sections['experiences'])
        
        # Section formation
        self.sections['education'] = EducationSection(self.profile)
        self.sections['education'].data_changed.connect(self.on_data_changed)
        main_layout.addWidget(self.sections['education'])
        
        # Section compétences
        self.sections['skills'] = SkillsSection(self.profile)
        self.sections['skills'].data_changed.connect(self.on_data_changed)
        main_layout.addWidget(self.sections['skills'])

        # Section soft skills
        self.sections['soft_skills'] = SoftSkillsSection(self.profile)
        self.sections['soft_skills'].data_changed.connect(self.on_data_changed)
        main_layout.addWidget(self.sections['soft_skills'])
        
        # Section langues
        self.sections['languages'] = LanguagesSection(self.profile)
        self.sections['languages'].data_changed.connect(self.on_data_changed)
        main_layout.addWidget(self.sections['languages'])
        
        # Section projets
        self.sections['projects'] = ProjectsSection(self.profile)
        self.sections['projects'].data_changed.connect(self.on_data_changed)
        main_layout.addWidget(self.sections['projects'])
        
        # Section certifications
        certifications_fields = [
            ("name", "Nom de la certification:", "Ex: AWS Certified Solutions Architect"),
            ("organization", "Organisme:", "Ex: Amazon Web Services"),
            ("date", "Date d'obtention:", "MM/YYYY"),
            ("url", "URL:", "Lien vers la certification")
        ]
        # Normalisation des libellés (correction mojibake)
        publications_fields = [
            ("title", "Titre:", "Titre de la publication"),
            ("authors", "Auteurs:", "Vous + co-auteurs"),
            ("journal", "Revue/Conférence:", "Nom de la publication"),
            ("date", "Date:", "MM/YYYY"),
            ("url", "URL:", "Lien vers la publication")
        ]
        self.sections['certifications'] = SimpleListSection(
            self.profile, 'extracted_certifications', 'Certifications', '📜', certifications_fields
        )
        self.sections['certifications'].data_changed.connect(self.on_data_changed)
        main_layout.addWidget(self.sections['certifications'])
        self.sections['certifications'].setTitle(f"{get_display_text('📜')} Certifications")
        
        # Section publications
        publications_fields = [
            ("title", "Titre:", "Titre de la publication"),
            ("authors", "Auteurs:", "Vous + co-auteurs"),
            ("journal", "Revue/Conférence:", "Nom de la publication"),
            ("date", "Date:", "MM/YYYY"),
            ("url", "URL:", "Lien vers la publication")
        ]
        # Normalisation des libellés (correction mojibake)
        volunteering_fields = [
            ("organization", "Organisation:", "Nom de l'association"),
            ("role", "Rôle:", "Votre fonction"),
            ("period", "Période:", "MM/YYYY - MM/YYYY"),
            ("description", "Description:", "Description de vos actions")
        ]
        self.sections['publications'] = SimpleListSection(
            self.profile, 'extracted_publications', 'Publications', '📚', publications_fields
        )
        self.sections['publications'].data_changed.connect(self.on_data_changed)
        main_layout.addWidget(self.sections['publications'])
        self.sections['publications'].setTitle(f"{get_display_text('📚')} Publications")
        
        # Section bénévolat
        volunteering_fields = [
            ("organization", "Organisation:", "Nom de l'association"),
            ("role", "Rôle:", "Votre fonction"),
            ("period", "Période:", "MM/YYYY - MM/YYYY"),
            ("description", "Description:", "Description de vos actions")
        ]
        # Normalisation des libellés (correction mojibake)
        awards_fields = [
            ("name", "Nom de la récompense:", "Ex: Prix d'excellence"),
            ("organization", "Organisme:", "Qui a décerné le prix"),
            ("date", "Date:", "MM/YYYY"),
            ("description", "Description:", "Contexte et importance")
        ]
        self.sections['volunteering'] = SimpleListSection(
            self.profile, 'extracted_volunteering', 'Bénévolat', '🤝', volunteering_fields
        )
        self.sections['volunteering'].data_changed.connect(self.on_data_changed)
        main_layout.addWidget(self.sections['volunteering'])
        self.sections['volunteering'].setTitle(f"{get_display_text('🤝')} Bénévolat")
        
        # Section récompenses
        awards_fields = [
            ("name", "Nom de la récompense:", "Ex: Prix d'excellence"),
            ("organization", "Organisme:", "Qui a décerné le prix"),
            ("date", "Date:", "MM/YYYY"),
            ("description", "Description:", "Contexte et importance")
        ]
        # Normalisation des libellés (correction mojibake)
        references_fields = [
            ("name", "Nom:", "Nom complet"),
            ("title", "Titre:", "Poste/fonction"),
            ("company", "Entreprise:", "Nom de l'entreprise"),
            ("email", "Email:", "email@example.com"),
            ("phone", "Téléphone:", "+33 X XX XX XX XX")
        ]
        self.sections['awards'] = SimpleListSection(
            self.profile, 'extracted_awards', 'Récompenses', '🏆', awards_fields
        )
        self.sections['awards'].data_changed.connect(self.on_data_changed)
        main_layout.addWidget(self.sections['awards'])
        self.sections['awards'].setTitle(f"{get_display_text('🏆')} Récompenses")
        
        # Section références
        references_fields = [
            ("name", "Nom:", "Nom complet"),
            ("title", "Titre:", "Poste/fonction"),
            ("company", "Entreprise:", "Nom de l'entreprise"),
            ("email", "Email:", "email@example.com"),
            ("phone", "Téléphone:", "+33 X XX XX XX XX")
        ]
        self.sections['references'] = SimpleListSection(
            self.profile, 'extracted_references', 'Références', '📇', references_fields
        )
        self.sections['references'].data_changed.connect(self.on_data_changed)
        main_layout.addWidget(self.sections['references'])
        self.sections['references'].setTitle(f"{get_display_text('📇')} Références")
        
        # Section centres d'intérêt
        self.sections['interests'] = InterestsSection(self.profile)
        self.sections['interests'].data_changed.connect(self.on_data_changed)
        main_layout.addWidget(self.sections['interests'])
    
    def create_footer(self, main_layout: QVBoxLayout):
        """Crée le footer avec les boutons d'action."""
        # Widget de footer fixe
        footer_widget = QWidget()
        footer_widget.setFixedHeight(80)
        footer_widget.setStyleSheet(f"""
            QWidget {{
                background-color: {StyleManager.COLORS['background_dark']};
                border-top: 2px solid {StyleManager.COLORS['border']};
                margin: 0px;
                padding: 10px;
            }}
        """)
        
        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(20, 15, 20, 15)
        
        # Texte d'état
        self.status_label = QLabel("✅ Aucune modification")
        self.status_label.setStyleSheet(f"color: {StyleManager.COLORS['success']}; font-weight: bold; font-size: 11px;")
        
        # Boutons du footer (copies des boutons du header)
        self.footer_cancel_button = QPushButton("↩️ Annuler les modifications")
        self.footer_cancel_button.setEnabled(False)
        apply_button_style(self.footer_cancel_button, "secondary")
        self.footer_cancel_button.clicked.connect(self.cancel_changes)

        self.footer_save_button = QPushButton("💾 Sauvegarder")
        self.footer_save_button.setEnabled(False)
        apply_button_style(self.footer_save_button, "primary")
        self.footer_save_button.clicked.connect(self.save_changes)
        
        footer_layout.addWidget(self.status_label)
        footer_layout.addStretch()
        footer_layout.addWidget(self.footer_cancel_button)
        footer_layout.addWidget(self.footer_save_button)
        
        footer_widget.setLayout(footer_layout)
        main_layout.addWidget(footer_widget)
    
    def on_data_changed(self, *args):
        """Appelé quand des données sont modifiées.

        Args:
            *args: Arguments optionnels ignorés (pour compatibilité avec différents types de signaux Qt).
                   Certains signaux émettent avec UserProfile, d'autres sans arguments.
        """
        # Ignorer si on est en train de rafraîchir l'interface
        if self._refreshing:
            logger.debug("Ignoring data_changed signal during refresh")
            return

        self.has_unsaved_changes = True

        # Activer les boutons du header
        self.save_button.setEnabled(True)
        self.cancel_button.setEnabled(True)

        # Activer les boutons du footer (avec vérification de sécurité)
        if hasattr(self, 'footer_save_button') and self.footer_save_button is not None:
            self.footer_save_button.setEnabled(True)
        if hasattr(self, 'footer_cancel_button') and self.footer_cancel_button is not None:
            self.footer_cancel_button.setEnabled(True)

        # Mettre à jour le texte d'état (avec vérification de sécurité)
        if hasattr(self, 'status_label') and self.status_label is not None:
            self.status_label.setText(f"{get_display_text('⚠️')} Modifications non sauvegardées • Fermer = Annulation automatique")
            self.status_label.setStyleSheet(f"color: {StyleManager.COLORS['warning']}; font-weight: bold; font-size: 11px;")
    
    def save_changes(self):
        """Sauvegarde les modifications."""
        # Activer le flag pour ignorer les signaux pendant la sauvegarde
        self._refreshing = True

        try:
            # Récupérer les données de toutes les sections
            personal_data = self.sections['personal'].get_data()
            experiences_data = self.sections['experiences'].get_data()
            education_data = self.sections['education'].get_data()
            skills_data = self.sections['skills'].get_data()
            soft_skills_data = self.sections['soft_skills'].get_data()
            languages_data = self.sections['languages'].get_data()
            projects_data = self.sections['projects'].get_data()
            certifications_data = self.sections['certifications'].get_data()
            publications_data = self.sections['publications'].get_data()
            volunteering_data = self.sections['volunteering'].get_data()
            awards_data = self.sections['awards'].get_data()
            references_data = self.sections['references'].get_data()
            interests_data = self.sections['interests'].get_data()
            
            # Mettre à jour les champs principaux du profil
            self.profile.name = personal_data.get('full_name', self.profile.name)
            self.profile.email = personal_data.get('email', self.profile.email)
            self.profile.phone = personal_data.get('phone', self.profile.phone)
            self.profile.linkedin_url = personal_data.get('linkedin_url', self.profile.linkedin_url)
            
            # Mettre à jour toutes les données extraites structurées
            current_personal = dict(self.profile.extracted_personal_info or {})
            current_personal.update(personal_data)
            self.profile.extracted_personal_info = current_personal
            
            self.profile.extracted_experiences = experiences_data
            self.profile.extracted_education = education_data
            self.profile.extracted_skills = skills_data
            self.profile.extracted_soft_skills = soft_skills_data
            self.profile.extracted_languages = languages_data
            self.profile.extracted_projects = projects_data
            self.profile.extracted_certifications = certifications_data
            self.profile.extracted_publications = publications_data
            self.profile.extracted_volunteering = volunteering_data
            self.profile.extracted_awards = awards_data
            self.profile.extracted_references = references_data
            self.profile.extracted_interests = interests_data
            
            # Sauvegarder en base de données
            with get_session() as session:
                session.add(self.profile)
                session.commit()
                session.refresh(self.profile)

            try:
                from ..utils.profile_json import (
                    build_profile_json_from_extracted_profile,
                    has_profile_json_content,
                    save_profile_json_cache,
                )

                profile_json = build_profile_json_from_extracted_profile(self.profile)
                if has_profile_json_content(profile_json) and self.profile.id:
                    save_profile_json_cache(self.profile.id, profile_json)
            except Exception as exc:
                logger.warning("Unable to save profile JSON cache: %s", exc)
            
            # Réinitialiser l'état des modifications et mettre à jour le cache
            self.has_unsaved_changes = False
            self.save_button.setEnabled(False)
            self.cancel_button.setEnabled(False)
            self.footer_save_button.setEnabled(False)
            self.footer_cancel_button.setEnabled(False)
            
            # Mettre à jour le texte d'état
            self.status_label.setText("✅ Modifications sauvegardées • Fermer = OK")
            self.status_label.setStyleSheet(f"color: {StyleManager.COLORS['success']}; font-weight: bold; font-size: 11px;")
            
            # Mettre à jour le cache avec les nouvelles données sauvegardées
            self.original_data_cache = self._create_profile_cache()
            
            # Nettoyer le cache persistant puisqu'on a sauvegardé
            self._cleanup_persistent_cache()
            
            # Sauvegarder un nouveau checkpoint des données propres
            self._save_persistent_cache()
            
            # Notifier la mise à jour
            self.profile_updated.emit(self.profile)
            
            # Calculer le nombre de sections remplies
            sections_filled = sum([
                1 for data in [experiences_data, education_data, skills_data, soft_skills_data, languages_data,
                              projects_data, certifications_data, publications_data,
                              volunteering_data, awards_data, references_data, interests_data]
                if data
            ])
            
            show_info(
                f"Les modifications ont été sauvegardées avec succès !\n\n"
                f"📊 Profil mis à jour :\n"
                f"• {len(experiences_data)} expérience(s)\n"
                f"• {len(education_data)} formation(s)\n"
                f"• {len(skills_data)} compétence(s)\n"
                f"• {len(soft_skills_data)} soft skill(s)\n"
                f"• {len(languages_data)} langue(s)\n"
                f"• {sections_filled} section(s) remplie(s) au total",
                title="✅ Sauvegarde réussie",
                parent=self,
            )
            
            logger.info("Profil profile_id={profile_id} mis à jour avec succès - {sections_filled} sections",
                        profile_id=self.profile.id, sections_filled=sections_filled)
            
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde : {e}")
            show_error(f"Une erreur est survenue lors de la sauvegarde :\n{e}", title="❌ Erreur de sauvegarde", parent=self)
        finally:
            # Désactiver le flag même en cas d'erreur
            self._refreshing = False

    def export_profile_json(self) -> None:
        from ..utils.profile_json import build_profile_json_from_extracted_profile

        profile_json = build_profile_json_from_extracted_profile(self.profile)
        default_name = (
            f"profile_{self.profile.id}_json.json" if self.profile.id else "profile_json.json"
        )
        export_dir = Path.cwd() / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        path = save_file_dialog(
            "Exporter le profil (JSON)",
            "JSON (*.json)",
            default_name=default_name,
            directory=str(export_dir),
            parent=self,
        )
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8') as handle:
                json.dump(profile_json, handle, indent=2, ensure_ascii=False)
        except Exception as exc:
            logger.error('Erreur export JSON: %s', exc)
            show_error(
                f"Impossible d'exporter le JSON.\n\n{exc}",
                title="Erreur",
                parent=self,
            )
            return

        show_info("Export JSON termine.", title="Export", parent=self)

    def import_profile_json(self) -> None:
        if self.has_unsaved_changes:
            proceed = confirm(
                "Des modifications non sauvegardees seront perdues. Continuer ?",
                title="Importer JSON",
                parent=self,
            )
            if not proceed:
                return

        path = open_file_dialog(
            "Importer un JSON",
            "JSON (*.json)",
            parent=self,
        )
        if not path:
            return

        try:
            with open(path, 'r', encoding='utf-8') as handle:
                payload = json.load(handle)
        except Exception as exc:
            logger.error('Erreur lecture JSON: %s', exc)
            show_error(
                f"Impossible de lire le JSON.\n\n{exc}",
                title="Erreur",
                parent=self,
            )
            return

        if not isinstance(payload, dict):
            show_error(
                "Le JSON doit etre un objet.",
                title="Erreur",
                parent=self,
            )
            return

        try:
            from ..utils.profile_json import (
                apply_profile_json_to_profile,
                has_profile_json_content,
                map_payload_to_profile_json,
                normalize_profile_json,
                save_profile_json_cache,
            )

            schema_version = str(payload.get('schema_version') or '')
            if schema_version.startswith('cv.') or (
                'contact' in payload and 'experience' in payload
            ):
                converted = self._convert_cv_json_to_profile_payload(payload)
                profile_json = normalize_profile_json(
                    map_payload_to_profile_json(converted, source='import')
                )
            else:
                profile_json = normalize_profile_json(payload)

            if not has_profile_json_content(profile_json):
                show_error(
                    "Le JSON importe est vide ou incompatible.",
                    title="Erreur",
                    parent=self,
                )
                return

            self._refreshing = True
            apply_profile_json_to_profile(self.profile, profile_json)
            personal = profile_json.get('personal_info') or {}
            if personal.get('full_name'):
                self.profile.name = personal['full_name']
            if personal.get('email'):
                self.profile.email = personal['email']
            if personal.get('phone'):
                self.profile.phone = personal['phone']
            if personal.get('linkedin_url'):
                self.profile.linkedin_url = personal['linkedin_url']

            with get_session() as session:
                session.add(self.profile)
                session.commit()
                session.refresh(self.profile)

            if self.profile.id:
                save_profile_json_cache(self.profile.id, profile_json)
        except Exception as exc:
            self._refreshing = False
            logger.error('Erreur import JSON: %s', exc)
            show_error(
                f"Impossible d'importer le JSON.\n\n{exc}",
                title="Erreur",
                parent=self,
            )
            return
        finally:
            self._refreshing = False

        self.original_data_cache = self._create_profile_cache()
        self._cleanup_persistent_cache()
        self._save_persistent_cache()
        self.has_unsaved_changes = False
        self._refresh_all_sections()
        self.save_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        if hasattr(self, 'footer_save_button') and self.footer_save_button is not None:
            self.footer_save_button.setEnabled(False)
        if hasattr(self, 'footer_cancel_button') and self.footer_cancel_button is not None:
            self.footer_cancel_button.setEnabled(False)
        if hasattr(self, 'status_label') and self.status_label is not None:
            self.status_label.setText('? Import JSON termine - Fermer = OK')
            self.status_label.setStyleSheet(
                f"color: {StyleManager.COLORS['success']}; font-weight: bold; font-size: 11px;"
            )

        self.profile_updated.emit(self.profile)
        show_info("Import JSON termine.", title="Import", parent=self)

    def _convert_cv_json_to_profile_payload(self, cv_json: Dict[str, Any]) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            'personal_info': cv_json.get('contact') if isinstance(cv_json.get('contact'), dict) else {},
            'education': cv_json.get('education') or [],
            'skills': cv_json.get('skills') or [],
            'languages': cv_json.get('languages') or [],
            'projects': cv_json.get('projects') or [],
            'certifications': cv_json.get('certifications') or [],
            'interests': cv_json.get('interests') or [],
        }

        experiences = []
        for item in cv_json.get('experience') or []:
            if not isinstance(item, dict):
                continue
            exp = dict(item)
            summary = exp.pop('summary', None)
            highlights = exp.pop('highlights', None)
            desc_parts = []
            if isinstance(summary, str) and summary.strip():
                desc_parts.append(summary.strip())
            if isinstance(highlights, list):
                desc_parts.extend(
                    str(entry).strip()
                    for entry in highlights
                    if str(entry).strip()
                )
            if desc_parts:
                exp['description'] = '\n'.join(desc_parts)
            experiences.append(exp)
        payload['experiences'] = experiences
        return payload

    def _create_profile_cache(self) -> Dict[str, Any]:
        """Crée un cache des données actuelles du profil."""
        return {
            'name': self.profile.name,
            'email': self.profile.email,
            'phone': self.profile.phone,
            'linkedin_url': self.profile.linkedin_url,
            'extracted_personal_info': self.profile.extracted_personal_info.copy() if self.profile.extracted_personal_info else {},
            'extracted_experiences': [exp.copy() for exp in (self.profile.extracted_experiences or [])],
            'extracted_education': [edu.copy() for edu in (self.profile.extracted_education or [])],
            'extracted_skills': [skill.copy() for skill in (self.profile.extracted_skills or [])],
            'extracted_soft_skills': [skill.copy() for skill in (self.profile.extracted_soft_skills or [])],
            'extracted_languages': [lang.copy() for lang in (self.profile.extracted_languages or [])],
            'extracted_projects': [proj.copy() for proj in (self.profile.extracted_projects or [])],
            'extracted_certifications': [cert.copy() for cert in (self.profile.extracted_certifications or [])],
            'extracted_publications': [pub.copy() for pub in (self.profile.extracted_publications or [])],
            'extracted_volunteering': [vol.copy() for vol in (self.profile.extracted_volunteering or [])],
            'extracted_awards': [award.copy() for award in (self.profile.extracted_awards or [])],
            'extracted_references': [ref.copy() for ref in (self.profile.extracted_references or [])],
            'extracted_interests': (self.profile.extracted_interests or []).copy()
        }
    
    def _load_or_create_cache(self) -> Dict[str, Any]:
        """Charge le cache existant ou en crée un nouveau basé sur les données de la DB."""
        # Pour un système de cache persistant, on pourrait stocker en DB ou fichier
        # Pour l'instant, on utilise un cache basé sur les données "propres" de la DB
        
        # Recharger le profil depuis la DB pour avoir les données sauvegardées
        try:
            with get_session() as session:
                # Récupérer la version fraîche depuis la DB
                fresh_profile = session.get(UserProfile, self.profile.id)
                if fresh_profile:
                    # Créer le cache basé sur les données fraîches de la DB
                    return {
                        'name': fresh_profile.name,
                        'email': fresh_profile.email,
                        'phone': fresh_profile.phone,
                        'linkedin_url': fresh_profile.linkedin_url,
                        'extracted_personal_info': fresh_profile.extracted_personal_info.copy() if fresh_profile.extracted_personal_info else {},
                        'extracted_experiences': [exp.copy() for exp in (fresh_profile.extracted_experiences or [])],
                        'extracted_education': [edu.copy() for edu in (fresh_profile.extracted_education or [])],
                        'extracted_skills': [skill.copy() for skill in (fresh_profile.extracted_skills or [])],
                        'extracted_soft_skills': [skill.copy() for skill in (fresh_profile.extracted_soft_skills or [])],
                        'extracted_languages': [lang.copy() for lang in (fresh_profile.extracted_languages or [])],
                        'extracted_projects': [proj.copy() for proj in (fresh_profile.extracted_projects or [])],
                        'extracted_certifications': [cert.copy() for cert in (fresh_profile.extracted_certifications or [])],
                        'extracted_publications': [pub.copy() for pub in (fresh_profile.extracted_publications or [])],
                        'extracted_volunteering': [vol.copy() for vol in (fresh_profile.extracted_volunteering or [])],
                        'extracted_awards': [award.copy() for award in (fresh_profile.extracted_awards or [])],
                        'extracted_references': [ref.copy() for ref in (fresh_profile.extracted_references or [])],
                        'extracted_interests': (fresh_profile.extracted_interests or []).copy()
                    }
        except Exception as e:
            logger.error(f"Erreur lors du chargement du cache depuis la DB: {e}")
        
        # Fallback: créer le cache avec les données actuelles
        return self._create_profile_cache()
    
    def _check_and_restore_from_cache_if_needed(self):
        """Vérifie si les données actuelles diffèrent du cache et restaure si nécessaire."""
        current_data = self._create_profile_cache()
        
        # Log pour debug - comparer les longueurs des expériences
        current_exp_count = len(current_data.get('extracted_experiences', []))
        cache_exp_count = len(self.original_data_cache.get('extracted_experiences', []))
        
        logger.info(f"🔍 Comparaison données:")
        logger.info(f"  - Expériences actuelles: {current_exp_count}")
        logger.info(f"  - Expériences dans cache: {cache_exp_count}")
        
        # Comparer les données actuelles avec le cache (données sauvegardées)
        if current_data != self.original_data_cache:
            logger.info("🛠️ Données modifiées détectées - restauration depuis le cache")
            
            # Restaurer les données depuis le cache
            self._restore_from_cache()
            
            # Log pour debug
            logger.info("✅ Profil restauré depuis le cache des données sauvegardées")
        else:
            logger.info("✅ Aucune modification détectée - pas de restauration nécessaire")
    
    def _reload_profile_from_db(self):
        """Recharge complètement le profil depuis la base de données."""
        try:
            with get_session() as session:
                # Récupérer la version fraîche depuis la DB
                fresh_profile = session.get(UserProfile, self.profile.id)
                if fresh_profile:
                    # Mettre à jour tous les attributs du profil actuel
                    self.profile.name = fresh_profile.name
                    self.profile.email = fresh_profile.email
                    self.profile.phone = fresh_profile.phone
                    self.profile.linkedin_url = fresh_profile.linkedin_url
                    self.profile.extracted_personal_info = fresh_profile.extracted_personal_info
                    self.profile.extracted_experiences = fresh_profile.extracted_experiences
                    self.profile.extracted_education = fresh_profile.extracted_education
                    self.profile.extracted_skills = fresh_profile.extracted_skills
                    self.profile.extracted_soft_skills = fresh_profile.extracted_soft_skills
                    self.profile.extracted_languages = fresh_profile.extracted_languages
                    self.profile.extracted_projects = fresh_profile.extracted_projects
                    self.profile.extracted_certifications = fresh_profile.extracted_certifications
                    self.profile.extracted_publications = fresh_profile.extracted_publications
                    self.profile.extracted_volunteering = fresh_profile.extracted_volunteering
                    self.profile.extracted_awards = fresh_profile.extracted_awards
                    self.profile.extracted_references = fresh_profile.extracted_references
                    self.profile.extracted_interests = fresh_profile.extracted_interests
                    
                    logger.info("🛠️ Profil rechargé depuis la base de données")
                else:
                    logger.warning("⚠️ Profil non trouvé en DB - utilisation des données actuelles")
        except Exception as e:
            logger.error(f"Erreur lors du rechargement du profil depuis la DB: {e}")
    
    def _get_cache_file_path(self) -> str:
        """Retourne le chemin du fichier cache pour ce profil."""
        # Créer un dossier cache dans le répertoire de l'application
        cache_dir = Path.cwd() / "cache" / "profile_editor"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return str(cache_dir / f"profile_{self.profile.id}_checkpoint.json")
    
    def _save_persistent_cache(self):
        """Sauvegarde le cache des données propres sur disque."""
        try:
            cache_data = {
                'profile_id': self.profile.id,
                'timestamp': datetime.now().isoformat(),
                'data': self.original_data_cache
            }
            
            with open(self.cache_file_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"💾 Cache persistant sauvegardé: {self.cache_file_path}")
            
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde du cache persistant: {e}")
    
    def _load_persistent_cache(self) -> Optional[Dict[str, Any]]:
        """Charge le cache persistant depuis le disque."""
        try:
            if not Path(self.cache_file_path).exists():
                return None
            
            with open(self.cache_file_path, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            # Vérifier que c'est bien le bon profil
            if cache_data.get('profile_id') != self.profile.id:
                logger.warning("Cache persistant pour un autre profil - ignoré")
                return None
            
            logger.info(f"📂 Cache persistant chargé: {self.cache_file_path}")
            return cache_data.get('data')
            
        except Exception as e:
            logger.error(f"Erreur lors du chargement du cache persistant: {e}")
            return None
    
    def _check_and_restore_from_persistent_cache(self):
        """Vérifie s'il faut restaurer depuis le cache persistant.

        Note: Ne restaure PAS si le profil a déjà des données extraites fraîches,
        pour éviter d'écraser les résultats d'une extraction récente.
        """
        # Vérifier si le profil a déjà des données extraites fraîches
        # Si oui, ne pas restaurer depuis le cache pour ne pas écraser
        has_fresh_extracted_data = any([
            self.profile.extracted_experiences,
            self.profile.extracted_education,
            self.profile.extracted_skills,
            self.profile.extracted_soft_skills,
            self.profile.extracted_personal_info,
        ])
        if has_fresh_extracted_data:
            logger.info("✅ Profil avec données extraites fraîches - skip cache restoration")
            # Mettre à jour le cache persistant avec les données actuelles
            self.original_data_cache = self._create_profile_cache()
            self._save_persistent_cache()
            return

        # Recharger d'abord depuis la DB
        self._reload_profile_from_db()

        # Charger le cache persistant
        persistent_cache = self._load_persistent_cache()
        if not persistent_cache:
            logger.info("Aucun cache persistant trouvé")
            return

        # Comparer les données actuelles avec le cache persistant
        current_data = self._create_profile_cache()

        if current_data != persistent_cache:
            logger.info("🛠️ Différences détectées avec le cache persistant - restauration nécessaire")

            # Restaurer depuis le cache persistant
            self._restore_from_persistent_cache(persistent_cache)

            # Sauvegarder la restauration en DB
            try:
                with get_session() as session:
                    session.add(self.profile)
                    session.commit()
                    session.refresh(self.profile)
                logger.info("✅ Profil restauré depuis le cache persistant et sauvegardé en DB")
            except Exception as e:
                logger.error(f"Erreur lors de la sauvegarde de la restauration: {e}")
        else:
            logger.info("✅ Données cohérentes avec le cache persistant")
    
    def _restore_from_persistent_cache(self, cache_data: Dict[str, Any]):
        """Restaure les données depuis le cache persistant."""
        try:
            # Restaurer les champs principaux
            self.profile.name = cache_data.get('name', self.profile.name)
            self.profile.email = cache_data.get('email', self.profile.email)
            self.profile.phone = cache_data.get('phone', self.profile.phone)
            self.profile.linkedin_url = cache_data.get('linkedin_url', self.profile.linkedin_url)
            
            # Restaurer toutes les données extraites
            self.profile.extracted_personal_info = cache_data.get('extracted_personal_info', {})
            self.profile.extracted_experiences = cache_data.get('extracted_experiences', [])
            self.profile.extracted_education = cache_data.get('extracted_education', [])
            self.profile.extracted_skills = cache_data.get('extracted_skills', [])
            self.profile.extracted_soft_skills = cache_data.get('extracted_soft_skills', [])
            self.profile.extracted_languages = cache_data.get('extracted_languages', [])
            self.profile.extracted_projects = cache_data.get('extracted_projects', [])
            self.profile.extracted_certifications = cache_data.get('extracted_certifications', [])
            self.profile.extracted_publications = cache_data.get('extracted_publications', [])
            self.profile.extracted_volunteering = cache_data.get('extracted_volunteering', [])
            self.profile.extracted_awards = cache_data.get('extracted_awards', [])
            self.profile.extracted_references = cache_data.get('extracted_references', [])
            self.profile.extracted_interests = cache_data.get('extracted_interests', [])
            
            logger.info("🛠️ Données restaurées depuis le cache persistant")
            
        except Exception as e:
            logger.error(f"Erreur lors de la restauration depuis le cache persistant: {e}")
    
    def _cleanup_persistent_cache(self):
        """Nettoie le cache persistant (appelé après sauvegarde réussie)."""
        try:
            if Path(self.cache_file_path).exists():
                os.remove(self.cache_file_path)
                logger.info("🧹 Cache persistant nettoyé après sauvegarde")
        except Exception as e:
            logger.error(f"Erreur lors du nettoyage du cache persistant: {e}")
    
    def _restore_from_cache(self):
        """Restaure les données du profil depuis le cache."""
        cache = self.original_data_cache
        
        # Restaurer les champs principaux
        self.profile.name = cache['name']
        self.profile.email = cache['email']
        self.profile.phone = cache['phone']
        self.profile.linkedin_url = cache['linkedin_url']
        
        # Restaurer toutes les données extraites
        self.profile.extracted_personal_info = cache['extracted_personal_info'].copy()
        self.profile.extracted_experiences = [exp.copy() for exp in cache['extracted_experiences']]
        self.profile.extracted_education = [edu.copy() for edu in cache['extracted_education']]
        self.profile.extracted_skills = [skill.copy() for skill in cache['extracted_skills']]
        self.profile.extracted_soft_skills = [skill.copy() for skill in cache.get('extracted_soft_skills', [])]
        self.profile.extracted_languages = [lang.copy() for lang in cache['extracted_languages']]
        self.profile.extracted_projects = [proj.copy() for proj in cache['extracted_projects']]
        self.profile.extracted_certifications = [cert.copy() for cert in cache['extracted_certifications']]
        self.profile.extracted_publications = [pub.copy() for pub in cache['extracted_publications']]
        self.profile.extracted_volunteering = [vol.copy() for vol in cache['extracted_volunteering']]
        self.profile.extracted_awards = [award.copy() for award in cache['extracted_awards']]
        self.profile.extracted_references = [ref.copy() for ref in cache['extracted_references']]
        self.profile.extracted_interests = cache['extracted_interests'].copy()
    
    def cancel_changes(self):
        """Annule les modifications et revient aux données du cache."""
        if self.has_unsaved_changes:
            reply = QMessageBox.question(
                self,
                "↩️ Annuler les modifications",
                "Êtes-vous sûr de vouloir annuler toutes les modifications ?\n\n"
                "Toutes les données non sauvegardées seront perdues et l'interface "
                "reviendra à l'état lors de la dernière sauvegarde.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                # Restaurer les données depuis le cache
                self._restore_from_cache()
                
                # Recréer l'interface avec les données restaurées
                self._refresh_all_sections()
                
                # Réinitialiser l'état des modifications
                self.has_unsaved_changes = False
                self.save_button.setEnabled(False)
                self.cancel_button.setEnabled(False)

                # Vérifier que les boutons existent avant de les modifier
                if hasattr(self, 'footer_save_button') and self.footer_save_button is not None:
                    self.footer_save_button.setEnabled(False)
                if hasattr(self, 'footer_cancel_button') and self.footer_cancel_button is not None:
                    self.footer_cancel_button.setEnabled(False)

                # Mettre à jour le texte d'état
                if hasattr(self, 'status_label') and self.status_label is not None:
                    self.status_label.setText("✅ Modifications annulées • Fermer = OK")
                    self.status_label.setStyleSheet(f"color: {StyleManager.COLORS['success']}; font-weight: bold; font-size: 11px;")
                
                # Nettoyer le cache persistant puisqu'on a restauré
                self._cleanup_persistent_cache()
                
                # Sauvegarder un nouveau checkpoint des données propres
                self._save_persistent_cache()
                
                # Message de confirmation
                QMessageBox.information(
                    self,
                    "✅ Modifications annulées",
                    "Les modifications ont été annulées avec succès.\n\n"
                    "L'interface a été restaurée à l'état de la dernière sauvegarde."
                )
                
                logger.info("Modifications annulées - retour au cache")
    
    def _refresh_all_sections(self):
        """Rafraîchit toutes les sections avec les données actuelles du profil."""
        # Activer le flag de refresh
        self._refreshing = True

        try:
            # SAFE: Disable updates and block signals during refresh
            self.setUpdatesEnabled(False)

            # Step 1: Disconnect and block signals from ALL sections
            for section_name, section in list(self.sections.items()):
                try:
                    section.blockSignals(True)  # Block signals during cleanup
                    if hasattr(section, 'data_changed'):
                        try:
                            section.data_changed.disconnect()  # Remove all signal connections
                        except:
                            pass
                except:
                    pass

            # Step 2: Remove all sections from layout and schedule deletion
            for section_name, section in list(self.sections.items()):
                section.setParent(None)
                section.deleteLater()

            self.sections.clear()

            # Step 3: Process pending events to complete deletion before recreating
            from PySide6.QtWidgets import QApplication
            QApplication.processEvents()

            # Step 4: Recréer le widget principal avec les sections mises à jour
            main_widget = self.widget()
            main_layout = main_widget.layout()

            # Supprimer le layout des sections (garder l'en-tête)
            while main_layout.count() > 1:  # Garder l'en-tête (index 0)
                item = main_layout.takeAt(1)
                if item.widget():
                    item.widget().deleteLater()

            # S'assurer que les widgets sont bien supprimés
            QApplication.processEvents()

            # Recréer les sections
            self.create_sections(main_layout)

            # Recréer le footer
            self.create_footer(main_layout)

            # Re-enable updates
            self.setUpdatesEnabled(True)

        finally:
            # Désactiver le flag de refresh (même en cas d'erreur)
            self._refreshing = False
    
    def closeEvent(self, event):
        """Gère la fermeture de la fenêtre."""
        if self.has_unsaved_changes:
            # Comportement par défaut : annuler automatiquement les modifications non sauvegardées
            logger.info("🛠️ Fermeture de la fenêtre - annulation automatique des modifications non sauvegardées")
            
            # Restaurer depuis le cache avant de fermer (mode silencieux)
            self._restore_from_cache()
            
            # Sauvegarder la restauration en DB pour que la prochaine ouverture soit propre
            try:
                with get_session() as session:
                    session.add(self.profile)
                    session.commit()
                    session.refresh(self.profile)
                # Nettoyer et recréer le cache persistant
                self._cleanup_persistent_cache()
                self.original_data_cache = self._create_profile_cache()
                self._save_persistent_cache()
                
                logger.info("✅ Fenêtre fermée - modifications annulées et données restaurées")
            except Exception as e:
                logger.error(f"Erreur lors de la sauvegarde de la restauration: {e}")
            
            event.accept()
        else:
            logger.info("✅ Fermeture de la fenêtre - aucune modification à annuler")
            event.accept()


# Test de l'interface (à supprimer en production)
if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Créer un profil de test
    from ..models.user_profile import UserProfile
    test_profile = UserProfile(
        name="John Doe",
        email="john@example.com",
        phone="+33 6 12 34 56 78",
        linkedin_url="https://linkedin.com/in/johndoe",
        extracted_personal_info={
            "full_name": "John Doe",
            "email": "john.doe@company.com",
            "phone": "+33 6 98 76 54 32"
        },
        extracted_experiences=[
            {
                "title": "Développeur Senior",
                "company": "Tech Corp",
                "start_date": "01/2020",
                "end_date": "Actuellement",
                "location": "Paris, France",
                "description": "Développement d'applications web avec React et Python."
            }
        ]
    )
    
    editor = ProfileDetailsEditor(test_profile)
    editor.show()
    
    sys.exit(app.exec())
