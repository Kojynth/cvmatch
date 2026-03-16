"""
Section des informations personnelles du profil.

Cette section gère l'affichage et l'édition des informations personnelles
de base du profil utilisateur.
"""

from typing import Dict, Any
from PySide6.QtWidgets import (
    QWidget, QGroupBox, QFormLayout, QLineEdit, QVBoxLayout, 
    QHBoxLayout, QPushButton, QLabel, QDialog, QDialogButtonBox
)

from .base_section import BaseSection
from ...models.user_profile import UserProfile


class PersonalInfoSection(BaseSection):
    """Section pour les informations personnelles du profil."""
    
    def __init__(self, profile: UserProfile, parent=None):
        super().__init__(profile, parent)
        self.address_edit = None
        self.city_edit = None
        self.postal_edit = None
        
    def create_section_widget(self) -> QWidget:
        """Crée la section informations personnelles."""
        section = QGroupBox("👤 Informations personnelles complémentaires")
        section.setStyleSheet("""
            QGroupBox {
                font-size: 16px;
                font-weight: bold;
                color: #4db8ff;
                border: 2px solid #404040;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 20px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 10px;
            }
        """)
        
        layout = QVBoxLayout(section)
        layout.setSpacing(10)
        
        # Formulaire pour les champs de base
        form_layout = QFormLayout()
        form_layout.setSpacing(10)
        
        # Récupérer les données depuis extracted_personal_info
        personal_info = self.profile.extracted_personal_info or {}
        
        # Adresse éditable
        self.address_edit = QLineEdit(personal_info.get('address', ''))
        self.address_edit.setPlaceholderText("Adresse complète...")
        self.address_edit.textChanged.connect(self._on_address_changed)
        form_layout.addRow("📍 Adresse:", self.address_edit)
        
        # Ville éditable
        self.city_edit = QLineEdit(personal_info.get('city', ''))
        self.city_edit.setPlaceholderText("Ville...")
        self.city_edit.textChanged.connect(self._on_city_changed)
        form_layout.addRow("🏙️ Ville:", self.city_edit)
        
        # Code postal éditable
        self.postal_edit = QLineEdit(personal_info.get('postal_code', ''))
        self.postal_edit.setPlaceholderText("Code postal...")
        self.postal_edit.textChanged.connect(self._on_postal_changed)
        form_layout.addRow("📮 Code postal:", self.postal_edit)
        
        layout.addLayout(form_layout)
        
        # Section liens
        links_section = self._create_links_section()
        layout.addWidget(links_section)
        
        return section
    
    def get_section_data(self) -> Dict[str, Any]:
        """Retourne les données de la section informations personnelles."""
        personal_info = self.profile.extracted_personal_info or {}
        return {
            'address': personal_info.get('address', ''),
            'city': personal_info.get('city', ''),
            'postal_code': personal_info.get('postal_code', '')
        }
    
    def _on_address_changed(self, text: str):
        """Callback pour changement d'adresse."""
        from loguru import logger
        logger.info(f"📍 Changement adresse: '{text}'")
        
        if not self.profile.extracted_personal_info:
            self.profile.extracted_personal_info = {}
        self.profile.extracted_personal_info['address'] = text
        self.emit_data_updated()
        logger.info(f"📍 Adresse sauvegardée dans extracted_personal_info")
    
    def _on_city_changed(self, text: str):
        """Callback pour changement de ville."""
        from loguru import logger
        logger.info(f"🏙️ Changement ville: '{text}'")
        
        if not self.profile.extracted_personal_info:
            self.profile.extracted_personal_info = {}
        self.profile.extracted_personal_info['city'] = text
        self.emit_data_updated()
        logger.info(f"🏙️ Ville sauvegardée dans extracted_personal_info")
    
    def _on_postal_changed(self, text: str):
        """Callback pour changement de code postal."""
        from loguru import logger
        logger.info(f"📮 Changement code postal: '{text}'")
        
        if not self.profile.extracted_personal_info:
            self.profile.extracted_personal_info = {}
        self.profile.extracted_personal_info['postal_code'] = text
        self.emit_data_updated()
        logger.info(f"📮 Code postal sauvegardé dans extracted_personal_info")
    
    def update_data(self):
        """Met à jour les champs avec les dernières données du profil."""
        personal_info = self.profile.extracted_personal_info or {}
        
        if self.address_edit:
            self.address_edit.setText(personal_info.get('address', ''))
        if self.city_edit:
            self.city_edit.setText(personal_info.get('city', ''))
        if self.postal_edit:
            self.postal_edit.setText(personal_info.get('postal_code', ''))
    
    def _create_links_section(self) -> QWidget:
        """Crée la section de gestion des liens."""
        links_widget = QWidget()
        links_layout = QVBoxLayout(links_widget)
        links_layout.setContentsMargins(0, 10, 0, 0)
        
        # Titre de la sous-section
        links_title = QLabel("Liens :")
        links_title.setStyleSheet("font-weight: bold; font-size: 14px; color: #e0e0e0; margin-bottom: 5px;")
        links_layout.addWidget(links_title)
        
        # Container pour les liens existants
        self.links_container = QVBoxLayout()
        self._refresh_links_display()
        links_layout.addLayout(self.links_container)
        
        # Bouton ajouter lien
        add_link_btn = QPushButton("➕ Ajouter un lien")
        add_link_btn.setStyleSheet("""
            QPushButton {
                background-color: #2d5f3f;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 12px;
                margin-top: 5px;
            }
            QPushButton:hover {
                background-color: #1e4f2f;
            }
        """)
        add_link_btn.clicked.connect(self._add_new_link)
        links_layout.addWidget(add_link_btn)
        
        return links_widget
    
    def _refresh_links_display(self):
        """Rafraîchit l'affichage des liens."""
        from loguru import logger
        logger.info(f"🔄 Début rafraîchissement affichage liens")
        
        # Nettoyer les widgets existants
        widget_count = self.links_container.count()
        logger.info(f"🔄 Suppression de {widget_count} widgets existants")
        while self.links_container.count():
            child = self.links_container.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        # Récupérer les liens du profil depuis extracted_personal_info
        personal_info = self.profile.extracted_personal_info or {}
        links = personal_info.get('links', []) or []
        logger.info(f"🔄 Liens trouvés dans le profil: {len(links)}")
        for i, link in enumerate(links):
            logger.info(f"🔄 Lien {i}: {link}")
        
        # Afficher chaque lien avec possibilité de suppression
        widgets_created = 0
        for i, link in enumerate(links):
            if isinstance(link, dict) and link.get('url'):
                logger.info(f"🔄 Création widget pour lien {i}: {link.get('platform')} -> {link.get('url')}")
                link_widget = self._create_link_widget(link, i)
                self.links_container.addWidget(link_widget)
                widgets_created += 1
            else:
                logger.warning(f"🔄 Lien {i} ignoré (format invalide): {link}")
        
        logger.info(f"🔄 {widgets_created} widgets de liens créés")
    
    def _create_link_widget(self, link: Dict, index: int) -> QWidget:
        """Crée un widget pour afficher un lien avec bouton de suppression."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(5, 2, 5, 2)
        
        # Lien cliquable pour édition (plus d'ouverture externe)
        link_btn = QPushButton(f'{link.get("label") or link.get("platform") or "Lien"}')
        link_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #4db8ff;
                border: none;
                text-align: left;
                padding: 0;
                font-size: 12px;
                text-decoration: underline;
            }
            QPushButton:hover {
                color: #66c2ff;
                background-color: rgba(77, 184, 255, 0.1);
            }
        """)
        link_btn.clicked.connect(lambda: self._edit_link(index, link))
        layout.addWidget(link_btn)
        
        layout.addStretch()
        
        # Bouton supprimer
        delete_btn = QPushButton("🗑️")
        delete_btn.setFixedSize(24, 24)
        delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                border-radius: 3px;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        delete_btn.clicked.connect(lambda: self._delete_link(index))
        layout.addWidget(delete_btn)
        
        return widget
    
    def _add_new_link(self):
        """Ajoute un nouveau lien via un dialogue unique."""
        dialog = LinkDialog(self)
        if dialog.exec() == QDialog.Accepted:
            platform, url = dialog.get_link_data()
            
            # Debug - vérifier les données récupérées
            from loguru import logger
            logger.info(f"🔗 Ajout lien - Platform: '{platform}', URL: '{url}'")
            
            # Valider que les champs ne sont pas vides
            if not platform.strip() or not url.strip():
                logger.warning("🔗 Lien ignoré - champs vides")
                return
            
            # Ajouter le lien au profil dans extracted_personal_info
            if not self.profile.extracted_personal_info:
                self.profile.extracted_personal_info = {}
                
            if 'links' not in self.profile.extracted_personal_info:
                self.profile.extracted_personal_info['links'] = []
                logger.info("🔗 Création de la liste extracted_personal_info['links']")
            
            cleaned_label = platform.strip()
            new_link = {
                "label": cleaned_label,
                "url": url.strip()
            }
            self.profile.extracted_personal_info['links'].append(new_link)
            
            logger.info(f"🔗 Lien ajouté: {new_link}")
            logger.info(f"🔗 Total liens: {len(self.profile.extracted_personal_info['links'])}")
            
            # Rafraîchir l'affichage
            self._refresh_links_display()
            self.emit_data_updated()
            
            logger.info("🔗 Affichage rafraîchi et signal émis")
    
    def _edit_link(self, index: int, link: Dict):
        """Édite un lien existant."""
        from loguru import logger
        logger.info(f"✏️ Édition lien {index}: {link}")
        
        # Ouvrir le dialogue avec les données pré-remplies
        dialog = LinkDialog(self, link.get('label') or link.get('platform', ''), link.get('url', ''))
        if dialog.exec() == QDialog.Accepted:
            platform, url = dialog.get_link_data()
            
            # Valider les données
            if not platform.strip() or not url.strip():
                logger.warning("✏️ Édition annulée - champs vides")
                return
            
            # Mettre à jour le lien dans le profil
            personal_info = self.profile.extracted_personal_info or {}
            links = personal_info.get('links', [])
            
            if 0 <= index < len(links):
                old_link = links[index].copy()
                cleaned_label = platform.strip()
                links[index] = {
                    "label": cleaned_label,
                    "url": url.strip()
                }
                logger.info(f"✏️ Lien modifié: {old_link} -> {links[index]}")
                
                # Rafraîchir l'affichage
                self._refresh_links_display()
                self.emit_data_updated()
    
    def _delete_link(self, index: int):
        """Supprime un lien."""
        personal_info = self.profile.extracted_personal_info or {}
        links = personal_info.get('links', [])
        
        if 0 <= index < len(links):
            removed_link = links.pop(index)
            from loguru import logger
            logger.info(f"🗑️ Lien supprimé: {removed_link}")
            self._refresh_links_display()
            self.emit_data_updated()


class LinkDialog(QDialog):
    """Dialogue pour ajouter/éditer un lien."""
    
    def __init__(self, parent=None, initial_platform="", initial_url=""):
        super().__init__(parent)
        
        # Titre selon le mode (ajout ou édition)
        if initial_platform or initial_url:
            self.setWindowTitle("Modifier le lien")
        else:
            self.setWindowTitle("Ajouter un lien")
            
        self.setModal(True)
        self.resize(400, 150)
        
        # Stocker les valeurs initiales
        self.initial_platform = initial_platform
        self.initial_url = initial_url
        
        # Style sombre
        self.setStyleSheet("""
            QDialog {
                background-color: #2a2a2a;
                color: #e0e0e0;
            }
            QLineEdit {
                background-color: #3a3a3a;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 8px;
                color: #ffffff;
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 2px solid #4db8ff;
            }
            QLabel {
                color: #e0e0e0;
                font-size: 14px;
            }
        """)
        
        layout = QVBoxLayout(self)
        
        # Champ nom/plateforme
        layout.addWidget(QLabel("Nom du lien (ex: LinkedIn, GitHub, Portfolio):"))
        self.platform_edit = QLineEdit()
        self.platform_edit.setPlaceholderText("LinkedIn")
        self.platform_edit.setText(self.initial_platform)  # Pré-remplir
        layout.addWidget(self.platform_edit)
        
        # Champ URL
        layout.addWidget(QLabel("URL complète:"))
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://www.linkedin.com/in/votre-profil")
        self.url_edit.setText(self.initial_url)  # Pré-remplir
        layout.addWidget(self.url_edit)
        
        # Boutons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        # Focus sur le premier champ
        self.platform_edit.setFocus()
        # Si c'est une édition, sélectionner tout le texte
        if self.initial_platform:
            self.platform_edit.selectAll()
    
    def get_link_data(self) -> tuple:
        """Retourne les données du lien (platform, url)."""
        return self.platform_edit.text(), self.url_edit.text()
