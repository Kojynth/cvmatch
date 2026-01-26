"""
Section des soft skills du profil.

Cette section gère l'affichage, l'édition, l'ajout et la suppression
des soft skills (compétences comportementales) du profil utilisateur.
"""

from typing import List, Dict, Any
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QFrame, QLineEdit, QTextEdit, QComboBox, QSlider
)
from PySide6.QtCore import Qt

from .base_section import BaseSection
from ...models.user_profile import UserProfile
from ...widgets.collapsible_section import create_collapsible_section


class SoftSkillsSection(BaseSection):
    """Section pour les soft skills du profil."""
    
    def __init__(self, profile: UserProfile, parent=None):
        super().__init__(profile, parent)
        self.skill_widgets = []
        
    def create_section_widget(self) -> QWidget:
        """Crée la section soft skills collapsible."""
        # Contenu de la section
        content_widget = QWidget()
        self.content_layout = QVBoxLayout(content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        
        # Bouton ajouter soft skill
        add_skill_btn = self.create_add_button()
        add_skill_btn.clicked.connect(self.add_new_soft_skill)
        self.content_layout.addWidget(add_skill_btn)
        
        # Toujours créer le label "aucune soft skill" (masqué si nécessaire)
        self.no_skill_label = QLabel("Aucune soft skill extraite à forte confidence. Utilisez le bouton ci-dessus pour en ajouter.")
        self.no_skill_label.setStyleSheet("color: #a0a0a0; font-style: italic; padding: 20px; text-align: center;")
        self.content_layout.addWidget(self.no_skill_label)
        
        # Liste des soft skills existantes (filtrées)
        all_soft_skills = self.profile.extracted_soft_skills if self.profile.extracted_soft_skills else []
        
        # Filtrer les soft skills par confidence et règles de validation
        filtered_soft_skills = [
            skill for skill in all_soft_skills
            if self._get_confidence_score(skill.get('confidence', 'medium')) >= 0.5 
            and skill.get('name', '').strip() != ''
            and skill.get('name') not in ['Compétence à définir', 'Soft skill générique']
        ]
        
        from loguru import logger
        logger.info(f"🧠 Création de {len(filtered_soft_skills)} widgets de soft skills validées sur {len(all_soft_skills)} total")
        
        for i, skill in enumerate(filtered_soft_skills):
            logger.info(f"🧠 Création widget soft skill {i+1}: {skill.get('name', 'Sans nom')}")
            skill_widget = self.create_soft_skill_widget(skill, skill)
            self.content_layout.addWidget(skill_widget)
            self.skill_widgets.append(skill_widget)
            logger.info(f"✅ Widget soft skill {i+1} ajouté au layout")
        
        # Créer section collapsible avec titre initial
        skill_count = len(filtered_soft_skills)
        title = f"🧠 Soft Skills ({skill_count} compétence{'s' if skill_count != 1 else ''})"
        self.section = create_collapsible_section(title, content_widget, "▼", True)
        
        # Mettre à jour l'affichage initial
        self._update_display()
        
        try:
            from ..text_cleaner import sanitize_widget_tree
            sanitize_widget_tree(content_widget)
        except Exception:
            pass
        return self.section
    
    def create_add_button(self) -> QPushButton:
        """Crée le bouton d'ajout de soft skill."""
        add_skill_btn = QPushButton("➕ Ajouter une soft skill")
        add_skill_btn.setStyleSheet("""
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
        return add_skill_btn
    
    def create_soft_skill_widget(self, skill, skill_obj) -> QWidget:
        """Crée un widget pour une soft skill."""
        widget = QFrame()
        widget.setStyleSheet("""
            QFrame {
                background-color: #3a3a3a;
                border: 1px solid #555555;
                border-radius: 12px;
                margin: 8px;
                padding: 15px;
            }
            QFrame:hover {
                border: 1px solid #4db8ff;
                background-color: #404040;
            }
        """)
        
        layout = QVBoxLayout(widget)
        
        # Gérer le cas où skill est une string
        if isinstance(skill, str):
            skill_label = QLabel(skill)
            skill_label.setWordWrap(True)
            skill_label.setStyleSheet("padding: 10px; background: transparent;")
            layout.addWidget(skill_label)
            return widget
        
        # Si c'est un dict, procéder normalement
        if not isinstance(skill, dict):
            skill = {}
        
        # Header éditable
        header_layout = self.create_skill_header(skill, skill_obj, widget)
        layout.addLayout(header_layout)
        
        # Niveau et catégorie éditables
        details_layout = self.create_skill_details(skill, skill_obj)
        layout.addLayout(details_layout)
        
        # Description éditable
        desc_edit = self.create_skill_description(skill, skill_obj)
        layout.addWidget(desc_edit)
        
        return widget
    
    def create_skill_header(self, skill: Dict, skill_obj: Dict, widget: QWidget) -> QHBoxLayout:
        """Crée l'en-tête de la soft skill avec nom et actions."""
        header_layout = QHBoxLayout()
        
        name_edit = QLineEdit(str(skill.get('name', 'Nouvelle compétence')))
        name_edit.setPlaceholderText("Nom de la compétence...")
        name_edit.setStyleSheet("""
            QLineEdit {
                font-weight: bold; 
                font-size: 16px; 
                background-color: #3a3a3a;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 8px;
                color: #ffffff;
            }
            QLineEdit:focus {
                border: 2px solid #4db8ff;
                background-color: #404040;
            }
            QLineEdit:hover {
                border-color: #777777;
            }
        """)
        name_edit.textChanged.connect(lambda text: self._update_skill_field(skill_obj, 'name', text))
        header_layout.addWidget(name_edit)
        
        # Badge source
        source = skill.get('source', 'CV')
        source_colors = {
            'CV': '#4a4a4a',
            'LinkedIn': '#0e76a8',
            'Manuel': '#2d5f3f',
            'IA': '#7b68ee'
        }
        source_label = QLabel(source)
        source_label.setStyleSheet(f"""
            QLabel {{
                background-color: {source_colors.get(source, '#4a4a4a')};
                color: white;
                padding: 2px 6px;
                border-radius: 3px;
                font-size: 10px;
                font-weight: bold;
                margin-left: 10px;
            }}
        """)
        header_layout.addWidget(source_label)
        
        # Bouton suppression
        header_layout.addStretch()
        delete_btn = self.create_delete_button()
        delete_btn.clicked.connect(lambda: self.delete_soft_skill(skill_obj, widget))
        header_layout.addWidget(delete_btn)
        
        return header_layout
    
    def create_skill_details(self, skill: Dict, skill_obj: Dict) -> QHBoxLayout:
        """Crée la section niveau de la soft skill."""
        details_layout = QHBoxLayout()
        
        # Niveau avec slider amélioré
        level = skill.get('level', skill.get('confidence', 5))
        if isinstance(level, float) and level <= 1.0:
            level = int(level * 10)  # Convertir 0.0-1.0 vers 0-10
        level = max(1, min(10, int(level)))  # Assurer que c'est entre 1-10
        
        # Label niveau
        niveau_label = QLabel("Niveau:")
        niveau_label.setStyleSheet("color: #e0e0e0; font-size: 14px; margin-right: 10px;")
        
        # Slider avec un meilleur design
        level_slider = QSlider(Qt.Horizontal)
        level_slider.setRange(1, 10)
        level_slider.setValue(level)
        level_slider.setMinimumWidth(150)
        level_slider.setStyleSheet("""
            QSlider {
                height: 20px;
            }
            QSlider::groove:horizontal {
                border: none;
                height: 8px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #ff4444, stop:0.3 #ffaa00, stop:0.7 #44ff44, stop:1 #00ff44);
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #ffffff;
                border: 2px solid #4db8ff;
                width: 20px;
                height: 20px;
                margin: -8px 0;
                border-radius: 10px;
            }
            QSlider::handle:horizontal:hover {
                background: #f0f0f0;
                border: 2px solid #66c2ff;
            }
            QSlider::handle:horizontal:pressed {
                background: #e0e0e0;
                border: 2px solid #3399cc;
            }
        """)
        
        # Labels de niveau avec couleurs
        level_display = QLabel()
        level_display.setStyleSheet("color: #ffffff; font-weight: bold; font-size: 16px; min-width: 60px; text-align: center;")
        level_display.setAlignment(Qt.AlignCenter)
        
        def update_level_display(value):
            colors = {
                1: "#ff4444", 2: "#ff6644", 3: "#ff8844", 4: "#ffaa44",
                5: "#ffcc44", 6: "#ccff44", 7: "#88ff44", 8: "#44ff44",
                9: "#44ff88", 10: "#00ff44"
            }
            level_display.setText(f"<span style='color: {colors.get(value, '#ffffff')}'>{value}/10</span>")
            self._update_skill_field(skill_obj, 'level', value)
        
        # Initialiser l'affichage
        update_level_display(level)
        level_slider.valueChanged.connect(update_level_display)
        
        details_layout.addWidget(niveau_label)
        details_layout.addWidget(level_slider)
        details_layout.addWidget(level_display)
        details_layout.addStretch()
        
        return details_layout
    
    def create_skill_description(self, skill: Dict, skill_obj: Dict) -> QTextEdit:
        """Crée le champ de description de la soft skill."""
        desc_edit = QTextEdit()
        description = skill.get('description', skill.get('context', ''))
        
        # Convertir en string si c'est une liste
        if isinstance(description, list):
            description = '\n'.join(str(item) for item in description)
        elif not isinstance(description, str):
            description = str(description)
            
        desc_edit.setPlainText(description)
        desc_edit.setPlaceholderText("Description ou exemple d'utilisation de cette soft skill...")
        desc_edit.setMaximumHeight(80)
        desc_edit.setStyleSheet("""
            QTextEdit {
                background-color: #3a3a3a;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 8px;
                color: #ffffff;
                font-size: 13px;
            }
            QTextEdit:focus {
                border: 2px solid #4db8ff;
                background-color: #404040;
            }
        """)
        desc_edit.textChanged.connect(lambda: self._update_skill_field(skill_obj, 'description', desc_edit.toPlainText()))
        
        return desc_edit
    # delete button helper inherited from BaseSection
    def get_section_data(self) -> List[Dict[str, Any]]:
        """Retourne les données des soft skills."""
        return self.profile.extracted_soft_skills if self.profile.extracted_soft_skills else []
    
    def add_new_soft_skill(self):
        """Ajoute une nouvelle soft skill."""
        if not hasattr(self.profile, 'extracted_soft_skills') or not self.profile.extracted_soft_skills:
            self.profile.extracted_soft_skills = []
        
        new_skill = {
            'name': 'Nouvelle compétence',
            'level': 7,
            'description': '',
            'confidence': 1.0,
            'source': 'Manuel'
        }
        
        self.profile.extracted_soft_skills.append(new_skill)
        
        # Déclencher la détection de modifications
        self.emit_data_updated(force_reload=True)
        
        # Ajouter directement le widget sans recharger toute l'interface
        self._add_skill_widget_to_layout(new_skill)
    
    def delete_soft_skill(self, skill_obj: Dict, widget: QWidget):
        """Supprime une soft skill."""
        if hasattr(self.profile, 'extracted_soft_skills') and self.profile.extracted_soft_skills:
            try:
                self.profile.extracted_soft_skills.remove(skill_obj)
                widget.deleteLater()
                if widget in self.skill_widgets:
                    self.skill_widgets.remove(widget)
                
                # Notifier le parent qu'il y a eu des modifications
                if hasattr(self.parent(), 'on_data_modified'):
                    self.parent().on_data_modified()
                
                # Mettre à jour l'affichage dynamiquement
                self._update_display()
                
                # Sauvegarder les données sans rechargement complet
                self.emit_data_updated(force_reload=False)
            except ValueError:
                pass  # La soft skill n'était pas dans la liste
    
    def _update_display(self):
        """Met à jour l'affichage (message et titre) selon le nombre d'éléments."""
        soft_skills_data = getattr(self.profile, 'extracted_soft_skills', []) or []
        
        # Filtrer les soft skills par confidence et règles de validation
        filtered_skills = [
            skill for skill in soft_skills_data
            if self._get_confidence_score(skill.get('confidence', 'medium')) >= 0.5 
            and skill.get('name', '').strip() != ''
            and skill.get('name') not in ['Compétence à définir', 'Soft skill générique']
        ]
        
        skill_count = len(filtered_skills)
        
        from loguru import logger
        logger.info(f"🎯 SoftSkillsSection._update_display() - {skill_count} soft skills validées sur {len(soft_skills_data)} total")
        
        # Gérer l'affichage du message "aucune soft skill"
        if hasattr(self, 'no_skill_label'):
            if skill_count == 0:
                self.no_skill_label.show()
                logger.info("🙁 Affichage du message 'aucune soft skill'")
            else:
                self.no_skill_label.hide()
                logger.info("🙂 Masquage du message 'aucune soft skill'")
        
        # Mettre à jour le titre avec le nouveau compteur
        if hasattr(self, 'section') and hasattr(self.section, 'title_label'):
            new_title = f"🧠 Soft Skills ({skill_count} compétence{'s' if skill_count != 1 else ''})"
            self.section.title_label.setText(new_title)
            logger.info(f"🏷️ Titre mis à jour: {new_title}")

    def _add_skill_widget_to_layout(self, skill):
        """Ajoute un widget de soft skill directement au layout."""
        if hasattr(self, 'content_layout'):
            # Créer et ajouter le nouveau widget
            skill_widget = self.create_soft_skill_widget(skill, skill)
            self.content_layout.addWidget(skill_widget)
            self.skill_widgets.append(skill_widget)
            
            # Mettre à jour l'affichage
            self._update_display()

    def _get_confidence_score(self, confidence) -> float:
        """Convertit confidence string vers float."""
        if isinstance(confidence, (int, float)):
            return float(confidence)
        elif isinstance(confidence, str):
            confidence_map = {'low': 0.3, 'medium': 0.7, 'high': 0.9}
            return confidence_map.get(confidence.lower(), 0.7)
        else:
            return 0.7

    def _update_skill_field(self, skill_obj: Dict, field: str, value):
        """Met à jour un champ d'une soft skill."""
        skill_obj[field] = value
        # Émettre signal de modification sans rechargement complet
        self.emit_data_updated(force_reload=False)
