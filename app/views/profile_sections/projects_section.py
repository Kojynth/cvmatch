"""Section des projets du profil."""

from typing import List, Dict, Any
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame, QLineEdit, QTextEdit, QComboBox
from .base_section import BaseSection
from ...models.user_profile import UserProfile
from ...widgets.collapsible_section import create_collapsible_section

class ProjectsSection(BaseSection):
    def __init__(self, profile: UserProfile, parent=None):
        super().__init__(profile, parent)
        self.project_widgets = []
        
    def create_section_widget(self) -> QWidget:
        content_widget = QWidget()
        self.content_layout = QVBoxLayout(content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        
        add_btn = QPushButton("➕ Ajouter un projet")
        add_btn.setStyleSheet(self._get_add_button_style())
        add_btn.clicked.connect(self.add_new_project)
        self.content_layout.addWidget(add_btn)
        
        # Toujours créer le label "aucun projet"
        self.no_data_label = QLabel("Aucun projet extrait. Utilisez le bouton ci-dessus pour en ajouter.")
        self.no_data_label.setStyleSheet("color: #a0a0a0; font-style: italic; padding: 20px; text-align: center;")
        self.content_layout.addWidget(self.no_data_label)
        
        projects_data = self.get_section_data()
        for project in projects_data:
            widget = self.create_project_widget(project, project)
            self.content_layout.addWidget(widget)
            self.project_widgets.append(widget)
        
        count = len(projects_data)
        title = f"🚀 Projets ({count} projet{'s' if count != 1 else ''})"
        self.section = create_collapsible_section(title, content_widget, "▼", True)
        
        # Mettre à jour l'affichage initial
        self._update_display()
        
        try:
            from ..text_cleaner import sanitize_widget_tree
            sanitize_widget_tree(content_widget)
        except Exception:
            pass
        return self.section
    
    def create_project_widget(self, project, project_obj) -> QWidget:
        widget = QFrame()
        widget.setStyleSheet(self._get_widget_style())
        layout = QVBoxLayout(widget)
        
        if not isinstance(project, dict):
            project = {}
        
        # Header
        header_layout = QHBoxLayout()
        name_edit = QLineEdit(str(project.get('name', 'Projet')))
        name_edit.setPlaceholderText("Nom du projet...")
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
        name_edit.textChanged.connect(lambda text: self._update_field(project_obj, 'name', text))
        header_layout.addWidget(name_edit)
        
        # Badge source
        source = project.get('source', 'CV')
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
        
        header_layout.addStretch()
        delete_btn = self.create_delete_button()
        delete_btn.clicked.connect(lambda: self.delete_project(project_obj, widget))
        header_layout.addWidget(delete_btn)
        layout.addLayout(header_layout)
        
        # Statut et URL
        status_layout = QHBoxLayout()
        
        # Statut du projet avec menu déroulant
        status_combo = QComboBox()
        status_combo.addItems([
            "🛠️ En cours",
            "✅ Terminé",
            "⏸️ En pause",
            "📅 Planifié",
            "❌ Abandonné"
        ])
        status_combo.setStyleSheet("""
            QComboBox {
                background-color: #3a3a3a;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 6px;
                color: #ffffff;
                min-width: 120px;
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
        
        # Définir le statut actuel
        current_status = str(project.get('status', ''))
        if current_status:
            for i, item_text in enumerate([
                "🛠️ En cours",
                "✅ Terminé", 
                "⏸️ En pause",
                "📅 Planifié",
                "❌ Abandonné"
            ]):
                if current_status.lower() in item_text.lower() or any(word in item_text.lower() for word in current_status.lower().split()):
                    status_combo.setCurrentIndex(i)
                    break
        else:
            status_combo.setCurrentIndex(0)  # Par défaut sur "En cours"
        
        status_combo.currentTextChanged.connect(lambda text: self._update_field(project_obj, 'status', text))
        status_layout.addWidget(QLabel("📊 Statut:"))
        status_layout.addWidget(status_combo)
        
        # URL du projet
        url_edit = QLineEdit(str(project.get('url', '')))
        url_edit.setPlaceholderText("URL du projet...")
        url_edit.setStyleSheet("""
            QLineEdit {
                background-color: #3a3a3a;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 6px;
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
        url_edit.textChanged.connect(lambda text: self._update_field(project_obj, 'url', text))
        status_layout.addWidget(QLabel("🔗"))
        status_layout.addWidget(url_edit)
        
        layout.addLayout(status_layout)
        
        # Description
        desc_edit = QTextEdit()
        desc_edit.setPlainText(str(project.get('description', '')))
        desc_edit.setPlaceholderText("Description du projet...")
        desc_edit.setMaximumHeight(80)
        desc_edit.setStyleSheet("""
            QTextEdit {
                background-color: #3a3a3a;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 8px;
                color: #ffffff;
            }
            QTextEdit:focus {
                border: 2px solid #4db8ff;
                background-color: #404040;
            }
            QTextEdit:hover {
                border-color: #777777;
            }
        """)
        desc_edit.textChanged.connect(lambda: self._update_field(project_obj, 'description', desc_edit.toPlainText()))
        layout.addWidget(desc_edit)
        
        return widget
    
    def _get_add_button_style(self):
        return "QPushButton { background-color: #2d5f3f; color: white; border: none; padding: 12px 20px; border-radius: 8px; font-weight: bold; font-size: 14px; margin: 5px; } QPushButton:hover { background-color: #1e4f2f; }"
    
    def _get_widget_style(self):
        return "QFrame { background-color: #3a3a3a; border: 1px solid #555555; border-radius: 12px; margin: 8px; padding: 15px; } QFrame:hover { border: 1px solid #4db8ff; background-color: #404040; }"
    
    def create_delete_button_legacy(self):
        delete_btn = QPushButton("❌")
        delete_btn.setFixedSize(28, 28)
        delete_btn.setStyleSheet("QPushButton { background: #DC143C; border-radius: 14px; color: #FFFFFF; font-weight: bold; font-size: 14px; border: none; } QPushButton:hover { background: #B22222; }")
        return delete_btn
    
    def get_section_data(self) -> List[Dict[str, Any]]:
        return getattr(self.profile, 'extracted_projects', []) or []
    
    def add_new_project(self):
        if not hasattr(self.profile, 'extracted_projects') or not self.profile.extracted_projects:
            self.profile.extracted_projects = []
        new_project = {'name': 'Nouveau projet', 'description': '', 'url': '', 'status': 'En cours', 'source': 'Manuel'}
        self.profile.extracted_projects.append(new_project)
        
        # Déclencher la détection de modifications
        self.emit_data_updated(force_reload=True)
        self._add_project_widget_to_layout(new_project)
    
    def delete_project(self, project_obj, widget):
        if hasattr(self.profile, 'extracted_projects') and self.profile.extracted_projects:
            try:
                self.profile.extracted_projects.remove(project_obj)
                widget.deleteLater()
                if widget in self.project_widgets:
                    self.project_widgets.remove(widget)
                
                # Mettre à jour l'affichage dynamiquement
                self._update_display()
                
                # Sauvegarder les données sans rechargement complet
                self.emit_data_updated(force_reload=False, )
            except ValueError:
                pass
    
    def _update_display(self):
        """Met à jour l'affichage (message et titre) selon le nombre d'éléments."""
        projects_data = getattr(self.profile, 'extracted_projects', []) or []
        project_count = len(projects_data)
        
        # Gérer l'affichage du message "aucun projet"
        if hasattr(self, 'no_data_label'):
            if project_count == 0:
                self.no_data_label.show()
            else:
                self.no_data_label.hide()
        
        # Mettre à jour le titre avec le nouveau compteur
        if hasattr(self, 'section') and hasattr(self.section, 'title_label'):
            new_title = f"🚀 Projets ({project_count} projet{'s' if project_count != 1 else ''})"
            self.section.title_label.setText(new_title)

    def _add_project_widget_to_layout(self, project):
        """Ajoute un widget de projet directement au layout."""
        if hasattr(self, 'content_layout'):
            widget = self.create_project_widget(project, project)
            self.content_layout.addWidget(widget)
            self.project_widgets.append(widget)
            
            # Mettre à jour l'affichage
            self._update_display()

    def _update_field_legacy(self, obj, field, value):
        obj[field] = value
        # Ne pas déclencher de rechargement complet
