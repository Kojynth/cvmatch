"""
Section des compétences du profil.
"""

from typing import List, Dict, Any
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QFrame, QLineEdit, QTextEdit, QComboBox
)

from .base_section import BaseSection
from ...models.user_profile import UserProfile
from ...widgets.collapsible_section import create_collapsible_section


class SkillsSection(BaseSection):
    """Section pour les compétences du profil."""
    
    def __init__(self, profile: UserProfile, parent=None):
        super().__init__(profile, parent)
        self.skill_widgets = []
        
    def create_section_widget(self) -> QWidget:
        """Crée la section compétences collapsible."""
        content_widget = QWidget()
        self.content_layout = QVBoxLayout(content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        
        # Bouton ajouter compétence
        add_skill_btn = QPushButton("➕ Ajouter une compétence")
        add_skill_btn.setStyleSheet(self._get_add_button_style())
        add_skill_btn.clicked.connect(self.add_new_skill)
        self.content_layout.addWidget(add_skill_btn)
        
        # Toujours créer le label "aucune compétence"
        self.no_skill_label = QLabel("Aucune compétence extraite. Utilisez le bouton ci-dessus pour en ajouter.")
        self.no_skill_label.setStyleSheet("color: #a0a0a0; font-style: italic; padding: 20px; text-align: center;")
        self.content_layout.addWidget(self.no_skill_label)
        
        # Conversion et affichage des compétences
        self._convert_skills_to_list()
        skills_data = self.get_section_data()
        
        for skill in skills_data:
            skill_widget = self.create_skill_widget(skill, skill)
            self.content_layout.addWidget(skill_widget)
            self.skill_widgets.append(skill_widget)
        
        skill_count = len(skills_data)
        title = f"🛠️ Compétences ({skill_count} compétence{'s' if skill_count != 1 else ''})"
        self.section = create_collapsible_section(title, content_widget, "▼", True)
        
        # Mettre à jour l'affichage initial
        self._update_display()
        
        try:
            from ..text_cleaner import sanitize_widget_tree
            sanitize_widget_tree(content_widget)
        except Exception:
            pass
        return self.section
    
    def _convert_skills_to_list(self):
        """Convertit les compétences du format dict vers list si nécessaire."""
        if hasattr(self.profile, 'extracted_skills') and isinstance(self.profile.extracted_skills, dict):
            skills_list = []
            for category, skills in self.profile.extracted_skills.items():
                if isinstance(skills, list):
                    for skill in skills:
                        if isinstance(skill, str):
                            skills_list.append({
                                'name': skill,
                                'category': category,
                                'level': '',
                                'description': '',
                                'source': 'CV'
                            })
                        elif isinstance(skill, dict):
                            skill['category'] = category
                            skills_list.append(skill)
            self.profile.extracted_skills = skills_list
        elif not hasattr(self.profile, 'extracted_skills'):
            self.profile.extracted_skills = []
    
    def create_skill_widget(self, skill, skill_obj) -> QWidget:
        """Crée un widget pour une compétence."""
        widget = QFrame()
        widget.setStyleSheet(self._get_widget_style())
        
        layout = QVBoxLayout(widget)
        
        if not isinstance(skill, dict):
            skill = {'name': str(skill), 'category': '', 'level': '', 'description': ''}
        
        # Header avec nom et catégorie
        header_layout = QHBoxLayout()
        
        name_edit = QLineEdit(str(skill.get('name', 'Compétence')))
        name_edit.setPlaceholderText("Nom de la compétence...")
        name_edit.setStyleSheet("""
            QLineEdit {
                font-weight: bold; 
                font-size: 14px; 
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
        
        category_edit = QLineEdit(str(skill.get('category', '')))
        category_edit.setPlaceholderText("Catégorie...")
        category_edit.textChanged.connect(lambda text: self._update_skill_field(skill_obj, 'category', text))
        header_layout.addWidget(category_edit)
        
        # Badge source
        source = skill.get('source', 'CV')
        source_colors = {
            'CV': '#4a4a4a',
            'LinkedIn': '#0e76a8',
            'Manuel': '#2d5f3f'
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
        delete_btn.clicked.connect(lambda: self.delete_skill(skill_obj, widget))
        header_layout.addWidget(delete_btn)
        
        layout.addLayout(header_layout)
        
        # Niveau avec menu déroulant
        level_layout = QHBoxLayout()
        level_combo = QComboBox()
        level_combo.addItems([
            "🔴 Notions - Connaissances théoriques de base",
            "🟠 Débutant - Pratique limitée, besoin d'aide", 
            "🟡 Intermédiaire - Autonome sur les tâches standards",
            "🟢 Confirmé - Maîtrise solide, peut résoudre des problèmes complexes",
            "🔵 Expert - Référent, peut former et innover",
            "🟣 Maître - Expertise reconnue, leadership technique"
        ])
        level_combo.setStyleSheet("""
            QComboBox {
                background-color: #3a3a3a;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 8px;
                color: #ffffff;
                min-width: 300px;
            }
            QComboBox:focus {
                border: 2px solid #4db8ff;
                background-color: #404040;
            }
            QComboBox:hover {
                border-color: #777777;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 20px;
                border-left: 1px solid #555555;
            }
            QComboBox::down-arrow {
                image: none;
                border: none;
                width: 0px;
                height: 0px;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #ffffff;
            }
            QComboBox QAbstractItemView {
                background-color: #3a3a3a;
                border: 1px solid #555555;
                selection-background-color: #4db8ff;
                color: #ffffff;
            }
        """)
        
        # Définir la valeur actuelle du niveau
        current_level = str(skill.get('level', ''))
        if current_level:
            # Essayer de trouver l'index correspondant au niveau actuel
            for i, item_text in enumerate([
                "🔴 Notions - Connaissances théoriques de base",
                "🟠 Débutant - Pratique limitée, besoin d'aide", 
                "🟡 Intermédiaire - Autonome sur les tâches standards",
                "🟢 Confirmé - Maîtrise solide, peut résoudre des problèmes complexes",
                "🔵 Expert - Référent, peut former et innover",
                "🟣 Maître - Expertise reconnue, leadership technique"
            ]):
                if current_level.lower() in item_text.lower() or any(word in item_text.lower() for word in current_level.lower().split()):
                    level_combo.setCurrentIndex(i)
                    break
        else:
            level_combo.setCurrentIndex(0)  # Par défaut sur "Notions"
        
        level_combo.currentTextChanged.connect(lambda text: self._update_skill_field(skill_obj, 'level', text))
        level_layout.addWidget(QLabel("📊 Niveau:"))
        level_layout.addWidget(level_combo)
        layout.addLayout(level_layout)
        
        return widget
    
    def _get_add_button_style(self) -> str:
        return """
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
            QPushButton:hover { background-color: #1e4f2f; }
            QPushButton:pressed { background-color: #1a3f2a; }
        """
    
    def _get_widget_style(self) -> str:
        return """
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
        """
    
    def create_delete_button(self) -> QPushButton:
        delete_btn = QPushButton("✖")
        delete_btn.setFixedSize(28, 28)
        delete_btn.setStyleSheet("""
            QPushButton {
                background: #DC143C; border-radius: 14px; color: #FFFFFF; 
                font-weight: bold; font-size: 14px; border: none;
            }
            QPushButton:hover { background: #B22222; }
        """)
        return delete_btn
    
    def get_section_data(self) -> List[Dict[str, Any]]:
        return self.profile.extracted_skills if self.profile.extracted_skills else []
    
    def add_new_skill(self):
        if not hasattr(self.profile, 'extracted_skills') or not self.profile.extracted_skills:
            self.profile.extracted_skills = []
        
        new_skill = {
            'name': 'Nouvelle compétence',
            'category': '',
            'level': '',
            'description': '',
            'source': 'Manuel'
        }
        
        self.profile.extracted_skills.append(new_skill)
        
        # Déclencher la détection de modifications
        self.emit_data_updated(force_reload=True)
        
        self._add_skill_widget_to_layout(new_skill)
    
    def delete_skill(self, skill_obj: Dict, widget: QWidget):
        if hasattr(self.profile, 'extracted_skills') and self.profile.extracted_skills:
            try:
                self.profile.extracted_skills.remove(skill_obj)
                widget.deleteLater()
                if widget in self.skill_widgets:
                    self.skill_widgets.remove(widget)
                
                # Mettre à jour l'affichage dynamiquement
                self._update_display()
                
                # Sauvegarder les données sans rechargement complet
                self.emit_data_updated(force_reload=False)
            except ValueError:
                pass
    
    def _update_display(self):
        """Met à jour l'affichage (message et titre) selon le nombre d'éléments."""
        skills_data = getattr(self.profile, 'extracted_skills', []) or []
        skill_count = len(skills_data)
        
        # Gérer l'affichage du message "aucune compétence"
        if hasattr(self, 'no_skill_label'):
            if skill_count == 0:
                self.no_skill_label.show()
            else:
                self.no_skill_label.hide()
        
        # Mettre à jour le titre avec le nouveau compteur
        if hasattr(self, 'section') and hasattr(self.section, 'title_label'):
            new_title = f"🛠️ Compétences ({skill_count} compétence{'s' if skill_count != 1 else ''})"
            self.section.title_label.setText(new_title)

    def _add_skill_widget_to_layout(self, skill):
        """Ajoute un widget de compétence directement au layout."""
        if hasattr(self, 'content_layout'):
            # Créer et ajouter le nouveau widget
            skill_widget = self.create_skill_widget(skill, skill)
            self.content_layout.addWidget(skill_widget)
            self.skill_widgets.append(skill_widget)
            
            # Mettre à jour l'affichage
            self._update_display()

    def _update_skill_field(self, skill_obj: Dict, field: str, value: str):
        skill_obj[field] = value
        # Émettre signal de modification sans rechargement complet
        self.emit_data_updated(force_reload=False)
