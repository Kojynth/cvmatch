"""
Champs génériques et réutilisables
==================================

Module pour créer des champs standardisés et réutilisables dans toute l'application.
Evite la duplication de code et garantit la cohérence de l'interface.
"""

from typing import Dict, List, Any, Optional, Callable, Union
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, 
    QLineEdit, QTextEdit, QComboBox, QPushButton, QFrame,
    QDateEdit, QSpinBox, QCheckBox, QMessageBox
)
from PySide6.QtCore import Qt, Signal, QDate
from PySide6.QtGui import QFont
from loguru import logger

from .phone_widget import PhoneNumberWidget


class GenericFieldWidget(QFrame):
    """Widget générique pour afficher et éditer des données structurées."""
    
    remove_requested = Signal(object)
    data_changed = Signal()
    
    def __init__(self, data: Dict[str, Any] = None, fields_config: List[Dict] = None, 
                 title: str = "Élément", icon: str = "📄"):
        super().__init__()
        # Normaliser les données : s'assurer que c'est un dictionnaire
        if data is None:
            self.original_data = {}
        elif isinstance(data, dict):
            self.original_data = data
        elif isinstance(data, str):
            # Si c'est une chaîne, on tente de l'assigner au premier champ disponible
            self.original_data = {}
            if fields_config and len(fields_config) > 0:
                first_field = fields_config[0]['name']
                self.original_data[first_field] = data
        elif isinstance(data, (list, tuple)):
            # Si c'est une liste, on l'ignore pour l'instant
            self.original_data = {}
        else:
            # Autres types: convertir en string et assigner au premier champ
            self.original_data = {}
            if fields_config and len(fields_config) > 0:
                first_field = fields_config[0]['name']
                self.original_data[first_field] = str(data)
        
        self.fields_config = fields_config or []
        self.title = title
        self.icon = icon
        self.fields = {}
        self.setup_ui()
    
    def setup_ui(self):
        """Configure l'interface du widget."""
        self.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)
        self.setStyleSheet("""
            QFrame {
                background-color: #1e1e1e;
                border: 1px solid #404040;
                border-radius: 4px;
                padding: 10px;
                margin: 2px;
            }
        """)
        
        layout = QVBoxLayout(self)
        
        # En-tête avec titre et bouton supprimer
        header_layout = QHBoxLayout()
        
        title_label = QLabel(f"{self.icon} {self.title}")
        title_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #4db8ff; margin-bottom: 5px;")
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        
        remove_btn = QPushButton("❌")
        remove_btn.setMaximumWidth(30)
        remove_btn.setStyleSheet("""
            QPushButton {
                background: #ef4444;
                color: white;
                border: none;
                padding: 5px;
                border-radius: 3px;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #dc2626;
            }
            QPushButton:pressed {
                background: #b91c1c;
            }
        """)
        remove_btn.clicked.connect(lambda: self.remove_requested.emit(self))
        header_layout.addWidget(remove_btn)
        
        layout.addLayout(header_layout)
        
        # Formulaire des champs
        if self.fields_config:
            form_layout = QFormLayout()
            
            for field_config in self.fields_config:
                field = self.create_field(field_config)
                if field:
                    label = field_config.get('label', field_config['name'])
                    form_layout.addRow(f"{label}:", field)
                    
            layout.addLayout(form_layout)
    
    def create_field(self, config: Dict) -> Optional[QWidget]:
        """Crée un champ selon sa configuration."""
        field_name = config['name']
        field_type = config.get('type', 'text')
        
        # Sécurité: s'assurer que original_data est un dictionnaire
        if not isinstance(self.original_data, dict):
            logger.warning(f"original_data n'est pas un dictionnaire: {type(self.original_data)} = {self.original_data}")
            self.original_data = {}
        
        value = self.original_data.get(field_name, config.get('default', ''))
        placeholder = config.get('placeholder', '')
        
        field = None
        
        if field_type == 'text':
            field = QLineEdit(str(value))
            field.setPlaceholderText(placeholder)
            field.textChanged.connect(self.on_field_changed)
            
        elif field_type == 'email':
            field = QLineEdit(str(value))
            field.setPlaceholderText(placeholder or "exemple@email.com")
            field.textChanged.connect(self.on_field_changed)
            
        elif field_type == 'phone':
            field = PhoneNumberWidget(str(value), placeholder or "Téléphone...", self)
            field.phone_changed.connect(self.on_field_changed)
            
        elif field_type == 'textarea':
            field = QTextEdit(str(value))
            max_height = config.get('max_height', 80)
            field.setMaximumHeight(max_height)
            field.setPlaceholderText(placeholder)
            field.textChanged.connect(self.on_field_changed)
            
        elif field_type == 'select':
            field = QComboBox()
            options = config.get('options', [])
            for option in options:
                if isinstance(option, dict):
                    field.addItem(option['label'], option['value'])
                else:
                    field.addItem(str(option))
            
            # Sélectionner la valeur actuelle
            if value:
                index = field.findText(str(value))
                if index >= 0:
                    field.setCurrentIndex(index)
            
            field.currentTextChanged.connect(self.on_field_changed)
            
        elif field_type == 'date':
            field = QDateEdit()
            field.setCalendarPopup(True)
            if value:
                try:
                    # Essayer plusieurs formats de date
                    date_formats = ['yyyy-MM-dd', 'dd/MM/yyyy', 'MM/yyyy', 'yyyy']
                    for fmt in date_formats:
                        try:
                            date = QDate.fromString(str(value), fmt)
                            if date.isValid():
                                field.setDate(date)
                                break
                        except:
                            continue
                except:
                    pass
            field.dateChanged.connect(self.on_field_changed)
            
        elif field_type == 'number':
            field = QSpinBox()
            field.setMinimum(config.get('min', 0))
            field.setMaximum(config.get('max', 9999))
            field.setValue(int(value) if str(value).isdigit() else 0)
            field.valueChanged.connect(self.on_field_changed)
            
        elif field_type == 'checkbox':
            field = QCheckBox(config.get('label', field_name))
            field.setChecked(bool(value))
            field.stateChanged.connect(self.on_field_changed)
            
        elif field_type == 'url':
            field = QLineEdit(str(value))
            field.setPlaceholderText(placeholder or "https://exemple.com")
            field.textChanged.connect(self.on_field_changed)
        
        if field:
            self.fields[field_name] = field
            
        return field
    
    def on_field_changed(self):
        """Émis quand un champ change."""
        self.data_changed.emit()
    
    def get_data(self) -> Dict[str, Any]:
        """Récupère les données de tous les champs."""
        data = {}
        
        for field_name, field in self.fields.items():
            if isinstance(field, QLineEdit):
                data[field_name] = field.text()
            elif isinstance(field, QTextEdit):
                data[field_name] = field.toPlainText()
            elif isinstance(field, QComboBox):
                data[field_name] = field.currentText()
            elif isinstance(field, QDateEdit):
                data[field_name] = field.date().toString('yyyy-MM-dd')
            elif isinstance(field, QSpinBox):
                data[field_name] = field.value()
            elif isinstance(field, QCheckBox):
                data[field_name] = field.isChecked()
            elif isinstance(field, PhoneNumberWidget):
                data[field_name] = field.get_full_phone_number()
        
        return data
    
    def has_changes(self) -> bool:
        """Vérifie si des modifications ont été apportées."""
        current_data = self.get_data()
        # Sécurité: s'assurer que original_data est un dictionnaire
        if not isinstance(self.original_data, dict):
            self.original_data = {}
        return current_data != self.original_data


class GenericListSection(QWidget):
    """Section générique pour gérer une liste d'éléments."""
    
    data_changed = Signal()
    
    def __init__(self, data_list: List[Dict] = None, fields_config: List[Dict] = None,
                 section_title: str = "Section", icon: str = "📄", 
                 item_title: str = "Élément", add_callback: Callable = None):
        super().__init__()
        self.data_list = data_list or []
        self.fields_config = fields_config or []
        self.section_title = section_title
        self.icon = icon
        self.item_title = item_title
        self.add_callback = add_callback
        self.items = []
        self.setup_ui()
    
    def setup_ui(self):
        """Configure l'interface de la section."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Bouton ajouter
        if self.add_callback:
            add_btn = QPushButton(f"➕ Ajouter {self.item_title.lower()}")
            add_btn.setStyleSheet("""
                QPushButton {
                    background-color: #2d5f3f;
                    color: white;
                    border: none;
                    padding: 12px 20px;
                    border-radius: 8px;
                    font-weight: bold;
                    font-size: 14px;
                    margin: 5px;
                }
                QPushButton:hover {
                    background-color: #1e4f2f;
                }
                QPushButton:pressed {
                    background-color: #1a3f2a;
                }
            """)
            add_btn.clicked.connect(self.add_callback)
            layout.addWidget(add_btn)
        
        # Container pour les éléments
        self.items_container = QVBoxLayout()
        
        # Charger les éléments existants
        for item_data in self.data_list:
            self.add_item_widget(item_data)
        
        # Message si vide
        if not self.data_list:
            no_data_label = QLabel(f"Aucun(e) {self.item_title.lower()} trouvé(e)")
            no_data_label.setStyleSheet("color: #a0a0a0; font-style: italic; padding: 20px; text-align: center;")
            self.items_container.addWidget(no_data_label)
        
        layout.addLayout(self.items_container)
    
    def add_item_widget(self, item_data: Dict[str, Any] = None):
        """Ajoute un widget d'élément."""
        item_widget = GenericFieldWidget(
            data=item_data,
            fields_config=self.fields_config,
            title=self.item_title,
            icon=self.icon
        )
        item_widget.remove_requested.connect(self.remove_item_widget)
        item_widget.data_changed.connect(self.data_changed.emit)
        
        self.items.append(item_widget)
        self.items_container.addWidget(item_widget)
    
    def remove_item_widget(self, item_widget):
        """Supprime un widget d'élément."""
        if item_widget in self.items:
            self.items.remove(item_widget)
            self.items_container.removeWidget(item_widget)
            item_widget.deleteLater()
            self.data_changed.emit()
    
    def get_data(self) -> List[Dict[str, Any]]:
        """Récupère les données de tous les éléments."""
        data = []
        for item in self.items:
            item_data = item.get_data()
            # N'inclure que les éléments avec au moins un champ rempli
            if any(str(v).strip() for v in item_data.values()):
                data.append(item_data)
        return data
    
    def has_changes(self) -> bool:
        """Vérifie si des modifications ont été apportées."""
        return any(item.has_changes() for item in self.items)


# Configurations prédéfinies pour différents types de données

LANGUAGE_FIELDS = [
    {'name': 'language', 'type': 'text', 'label': 'Langue', 'placeholder': 'Ex: Anglais, Espagnol...'},
    {'name': 'proficiency', 'type': 'select', 'label': 'Niveau', 'options': [
        'A1 - Débutant', 'A2 - Élémentaire', 'B1 - Intermédiaire', 
        'B2 - Intermédiaire+', 'C1 - Avancé', 'C2 - Maîtrise', 'Natif'
    ]}
]

CERTIFICATION_FIELDS = [
    {'name': 'name', 'type': 'text', 'label': 'Nom', 'placeholder': 'Ex: AWS Solutions Architect'},
    {'name': 'organization', 'type': 'text', 'label': 'Organisme', 'placeholder': 'Ex: Amazon Web Services'},
    {'name': 'date', 'type': 'text', 'label': 'Date d\'obtention', 'placeholder': 'MM/YYYY'},
    {'name': 'expiry_date', 'type': 'text', 'label': 'Date d\'expiration', 'placeholder': 'MM/YYYY (optionnel)'},
    {'name': 'credential_id', 'type': 'text', 'label': 'ID de certification', 'placeholder': 'Ex: ABC123'},
    {'name': 'url', 'type': 'url', 'label': 'URL', 'placeholder': 'Lien vers la certification'}
]

PUBLICATION_FIELDS = [
    {'name': 'title', 'type': 'text', 'label': 'Titre', 'placeholder': 'Titre de la publication'},
    {'name': 'authors', 'type': 'text', 'label': 'Auteurs', 'placeholder': 'Vous + co-auteurs'},
    {'name': 'journal', 'type': 'text', 'label': 'Revue/Conférence', 'placeholder': 'Nom de la publication'},
    {'name': 'date', 'type': 'text', 'label': 'Date', 'placeholder': 'MM/YYYY'},
    {'name': 'url', 'type': 'url', 'label': 'URL', 'placeholder': 'Lien vers la publication'},
    {'name': 'abstract', 'type': 'textarea', 'label': 'Résumé', 'placeholder': 'Résumé de la publication', 'max_height': 100}
]

VOLUNTEERING_FIELDS = [
    {'name': 'organization', 'type': 'text', 'label': 'Organisation', 'placeholder': 'Nom de l\'association'},
    {'name': 'role', 'type': 'text', 'label': 'Rôle', 'placeholder': 'Votre fonction'},
    {'name': 'start_date', 'type': 'text', 'label': 'Date début', 'placeholder': 'MM/YYYY'},
    {'name': 'end_date', 'type': 'text', 'label': 'Date fin', 'placeholder': 'MM/YYYY ou Actuellement'},
    {'name': 'description', 'type': 'textarea', 'label': 'Description', 'placeholder': 'Description de vos actions'},
    {'name': 'location', 'type': 'text', 'label': 'Lieu', 'placeholder': 'Ville, Pays'}
]

AWARD_FIELDS = [
    {'name': 'name', 'type': 'text', 'label': 'Nom', 'placeholder': 'Ex: Prix d\'excellence'},
    {'name': 'organization', 'type': 'text', 'label': 'Organisme', 'placeholder': 'Qui a décerné le prix'},
    {'name': 'date', 'type': 'text', 'label': 'Date', 'placeholder': 'MM/YYYY'},
    {'name': 'description', 'type': 'textarea', 'label': 'Description', 'placeholder': 'Contexte et importance'},
    {'name': 'level', 'type': 'select', 'label': 'Niveau', 'options': ['Local', 'Régional', 'National', 'International']}
]

REFERENCE_FIELDS = [
    {'name': 'name', 'type': 'text', 'label': 'Nom complet', 'placeholder': 'Nom et prénom'},
    {'name': 'title', 'type': 'text', 'label': 'Titre/Poste', 'placeholder': 'Fonction'},
    {'name': 'company', 'type': 'text', 'label': 'Entreprise', 'placeholder': 'Nom de l\'entreprise'},
    {'name': 'email', 'type': 'email', 'label': 'Email', 'placeholder': 'email@exemple.com'},
    {'name': 'phone', 'type': 'phone', 'label': 'Téléphone'},
    {'name': 'relationship', 'type': 'select', 'label': 'Relation', 'options': [
        'Supérieur hiérarchique', 'Collègue', 'Client', 'Partenaire', 'Professeur', 'Autre'
    ]}
]

PROJECT_FIELDS = [
    {'name': 'name', 'type': 'text', 'label': 'Nom du projet', 'placeholder': 'Nom du projet'},
    {'name': 'description', 'type': 'textarea', 'label': 'Description', 'placeholder': 'Description du projet'},
    {'name': 'technologies', 'type': 'text', 'label': 'Technologies', 'placeholder': 'Ex: Python, React, Docker'},
    {'name': 'url', 'type': 'url', 'label': 'URL', 'placeholder': 'https://github.com/user/project'},
    {'name': 'start_date', 'type': 'text', 'label': 'Date début', 'placeholder': 'MM/YYYY'},
    {'name': 'end_date', 'type': 'text', 'label': 'Date fin', 'placeholder': 'MM/YYYY ou En cours'},
    {'name': 'status', 'type': 'select', 'label': 'Statut', 'options': ['En cours', 'Terminé', 'En pause', 'Abandonné']}
]

INTEREST_FIELDS = [
    {'name': 'name', 'type': 'text', 'label': 'Centre d\'intérêt', 'placeholder': 'Ex: Photographie, Cuisine, Sport...'},
    {'name': 'description', 'type': 'textarea', 'label': 'Description', 'placeholder': 'Décrivez brièvement votre passion', 'max_height': 60},
    {'name': 'level', 'type': 'select', 'label': 'Niveau', 'options': ['Débutant', 'Amateur', 'Passionné', 'Expert']},
    {'name': 'frequency', 'type': 'select', 'label': 'Fréquence', 'options': ['Occasionnel', 'Régulier', 'Quotidien', 'Professionnel']}
]


def create_generic_section(section_title: str, icon: str, data_list: List[Dict], 
                          fields_config: List[Dict], item_title: str,
                          add_callback: Callable = None) -> GenericListSection:
    """
    Fonction utilitaire pour créer rapidement une section générique.
    
    Args:
        section_title: Titre de la section (ex: "Langues")
        icon: Icône de la section (ex: "🌍")
        data_list: Liste des données existantes
        fields_config: Configuration des champs
        item_title: Titre d'un élément (ex: "Langue")
        add_callback: Fonction à appeler pour ajouter un élément
    
    Returns:
        Section générique configurée
    """
    return GenericListSection(
        data_list=data_list,
        fields_config=fields_config,
        section_title=section_title,
        icon=icon,
        item_title=item_title,
        add_callback=add_callback
    )


# Fonctions de création spécialisées pour chaque type

def create_languages_section(data_list: List[Dict], add_callback: Callable = None) -> GenericListSection:
    """Crée une section Langues."""
    return create_generic_section("Langues", "🌍", data_list, LANGUAGE_FIELDS, "Langue", add_callback)

def create_certifications_section(data_list: List[Dict], add_callback: Callable = None) -> GenericListSection:
    """Crée une section Certifications."""
    return create_generic_section("Certifications", "📜", data_list, CERTIFICATION_FIELDS, "Certification", add_callback)

def create_publications_section(data_list: List[Dict], add_callback: Callable = None) -> GenericListSection:
    """Crée une section Publications."""
    return create_generic_section("Publications", "📝", data_list, PUBLICATION_FIELDS, "Publication", add_callback)

def create_volunteering_section(data_list: List[Dict], add_callback: Callable = None) -> GenericListSection:
    """Crée une section Bénévolat."""
    return create_generic_section("Activités bénévoles", "🤝", data_list, VOLUNTEERING_FIELDS, "Activité bénévole", add_callback)

def create_awards_section(data_list: List[Dict], add_callback: Callable = None) -> GenericListSection:
    """Crée une section Récompenses."""
    return create_generic_section("Récompenses", "🏆", data_list, AWARD_FIELDS, "Récompense", add_callback)

def create_references_section(data_list: List[Dict], add_callback: Callable = None) -> GenericListSection:
    """Crée une section Références."""
    return create_generic_section("Références", "👥", data_list, REFERENCE_FIELDS, "Référence", add_callback)

def create_projects_section(data_list: List[Dict], add_callback: Callable = None) -> GenericListSection:
    """Crée une section Projets."""
    return create_generic_section("Projets", "🚀", data_list, PROJECT_FIELDS, "Projet", add_callback)

def create_interests_section(data_list: List[Dict], add_callback: Callable = None) -> GenericListSection:
    """Crée une section Centres d'intérêt."""
    return create_generic_section("Centres d'intérêt", "🎯", data_list, INTEREST_FIELDS, "Centre d'intérêt", add_callback)
