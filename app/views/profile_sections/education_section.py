"""
Section de la formation du profil.

Cette section gère l'affichage, l'édition, l'ajout et la suppression
des formations du profil utilisateur.
"""

from typing import List, Dict, Any
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QFrame, QLineEdit, QTextEdit, QDateEdit, QCheckBox
)
from PySide6.QtCore import QDate

from .base_section import BaseSection
from ...models.user_profile import UserProfile
from ...widgets.collapsible_section import create_collapsible_section


class EducationSection(BaseSection):
    """Section pour la formation du profil."""
    
    def __init__(self, profile: UserProfile, parent=None):
        super().__init__(profile, parent)
        self.education_widgets = []
        
    def create_section_widget(self) -> QWidget:
        """Crée la section formation collapsible."""
        content_widget = QWidget()
        self.content_layout = QVBoxLayout(content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        
        # Bouton ajouter formation
        add_edu_btn = self.create_add_button()
        add_edu_btn.clicked.connect(self.add_new_education)
        self.content_layout.addWidget(add_edu_btn)
        
        # Toujours créer le label "aucune formation"
        self.no_edu_label = QLabel("Aucune formation extraite à forte confidence. Utilisez le bouton ci-dessus pour en ajouter.")
        self.no_edu_label.setStyleSheet("color: #a0a0a0; font-style: italic; padding: 20px; text-align: center;")
        self.content_layout.addWidget(self.no_edu_label)
        
        # Liste des formations existantes
        education_data = getattr(self.profile, 'extracted_education', []) or []
        for edu in education_data:
            edu_widget = self.create_education_widget(edu, edu)
            self.content_layout.addWidget(edu_widget)
            self.education_widgets.append(edu_widget)
        
        # Créer section collapsible avec titre dynamique
        edu_count = len(education_data)
        title = f"🎓 Formation ({edu_count} diplôme{'s' if edu_count != 1 else ''})"
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
        """Crée le bouton d'ajout de formation."""
        add_edu_btn = QPushButton("➕ Ajouter une formation")
        add_edu_btn.setStyleSheet("""
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
        return add_edu_btn
    
    def create_education_widget(self, edu, edu_obj) -> QWidget:
        """Crée un widget pour une formation."""
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
        
        # Si c'est un dict, procéder normalement
        if not isinstance(edu, dict):
            edu = {}
        
        # Header éditable
        header_layout = self.create_education_header(edu, edu_obj, widget)
        layout.addLayout(header_layout)
        
        # Période et lieu éditables
        period_layout = self.create_education_period(edu, edu_obj)
        layout.addLayout(period_layout)
        
        # Description éditable
        desc_edit = self.create_education_description(edu, edu_obj)
        layout.addWidget(desc_edit)
        
        return widget
    
    def create_education_header(self, edu: Dict, edu_obj: Dict, widget: QWidget) -> QHBoxLayout:
        """Crée l'en-tête de la formation avec diplôme, école et actions."""
        header_layout = QHBoxLayout()
        
        degree_edit = QLineEdit(str(edu.get('degree', 'Diplôme')))
        degree_edit.setPlaceholderText("Nom du diplôme...")
        degree_edit.setStyleSheet("""
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
        degree_edit.textChanged.connect(lambda text: self._update_education_field(edu_obj, 'degree', text))
        header_layout.addWidget(degree_edit)
        
        # Label "à" sans encadré
        a_label = QLabel(" à ")
        a_label.setStyleSheet("font-size: 14px; color: #e0e0e0; font-style: italic;")
        header_layout.addWidget(a_label)
        
        school_edit = QLineEdit(str(edu.get('institution', 'École')))
        school_edit.setPlaceholderText("Nom de l'établissement...")
        school_edit.setStyleSheet("""
            QLineEdit {
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
        school_edit.textChanged.connect(lambda text: self._update_education_field(edu_obj, 'institution', text))
        header_layout.addWidget(school_edit)
        
        # Badge source
        source = edu.get('source', 'CV')
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
        delete_btn.clicked.connect(lambda: self.delete_education(edu_obj, widget))
        header_layout.addWidget(delete_btn)
        
        return header_layout
    
    def create_education_period(self, edu: Dict, edu_obj: Dict) -> QHBoxLayout:
        """Crée la section période et lieu de la formation."""
        period_layout = QHBoxLayout()
        
        # Date de début avec calendrier
        start_date_edit = QDateEdit()
        start_date_edit.setCalendarPopup(True)
        start_date_edit.setDisplayFormat("MM/yyyy")
        start_date_edit.setStyleSheet("""
            QDateEdit {
                background-color: #3a3a3a;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 6px;
                color: #ffffff;
                min-width: 80px;
            }
            QDateEdit:focus {
                border: 2px solid #4db8ff;
            }
            QDateEdit::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 20px;
                border-left: 1px solid #555555;
            }
        """)
        
        # Définir la date depuis les données existantes
        start_date_str = edu.get('start_date', '')
        if start_date_str:
            try:
                # Essayer de parser différents formats de date
                if '/' in start_date_str:
                    parts = start_date_str.split('/')
                    if len(parts) >= 2:
                        month, year = int(parts[0]), int(parts[1])
                        start_date_edit.setDate(QDate(year, month, 1))
                elif len(start_date_str) == 4 and start_date_str.isdigit():  # Juste l'année
                    start_date_edit.setDate(QDate(int(start_date_str), 9, 1))  # Septembre par défaut pour les études
            except (ValueError, IndexError):
                start_date_edit.setDate(QDate.currentDate())
        else:
            start_date_edit.setDate(QDate.currentDate())
        
        start_date_edit.dateChanged.connect(lambda date: self._update_education_field(edu_obj, 'start_date', date.toString("MM/yyyy")))
        
        # Date de fin avec calendrier
        end_date_edit = QDateEdit()
        end_date_edit.setCalendarPopup(True)
        end_date_edit.setDisplayFormat("MM/yyyy")
        end_date_edit.setStyleSheet("""
            QDateEdit {
                background-color: #3a3a3a;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 6px;
                color: #ffffff;
                min-width: 80px;
            }
            QDateEdit:focus {
                border: 2px solid #4db8ff;
            }
            QDateEdit::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 20px;
                border-left: 1px solid #555555;
            }
        """)
        
        # Définir la date de fin
        end_date_str = edu.get('end_date', '')
        if end_date_str not in [None, ''] and (not isinstance(end_date_str, str) or end_date_str.lower() not in ['présent', 'en cours', 'current']):
            try:
                if '/' in end_date_str:
                    parts = end_date_str.split('/')
                    if len(parts) >= 2:
                        month, year = int(parts[0]), int(parts[1])
                        end_date_edit.setDate(QDate(year, month, 1))
                elif len(end_date_str) == 4 and end_date_str.isdigit():
                    end_date_edit.setDate(QDate(int(end_date_str), 6, 30))  # Juin par défaut pour fin d'études
            except (ValueError, IndexError):
                end_date_edit.setDate(QDate.currentDate())
        else:
            end_date_edit.setDate(QDate.currentDate())
        
        end_date_edit.dateChanged.connect(lambda date: self._update_education_field(edu_obj, 'end_date', date.toString("MM/yyyy")))

        # Option "En cours" - liée directement à end_date=None
        ongoing_check = QCheckBox("En cours")
        try:
            end_date_value = edu.get('end_date')
            # Unified ongoing logic: None, empty string, or ongoing patterns = ongoing
            if end_date_value is None:
                is_ongoing = True
            elif isinstance(end_date_value, str):
                end_str_lower = end_date_value.lower().strip()
                if end_str_lower == '':
                    is_ongoing = True
                else:
                    ongoing_patterns = ['présent', 'present', 'en cours', 'current', 'currently',
                                        'à ce jour', 'maintenant', 'now', 'today', 'ongoing', 'actuel']
                    is_ongoing = any(pattern in end_str_lower for pattern in ongoing_patterns)
            else:
                is_ongoing = False
        except Exception:
            is_ongoing = False
            
        ongoing_check.setChecked(is_ongoing)
        if is_ongoing:
            end_date_edit.blockSignals(True)
            end_date_edit.setDate(QDate.currentDate())
            end_date_edit.blockSignals(False)
            end_date_edit.setEnabled(False)

        def _on_ongoing_toggled(checked: bool):
            end_date_edit.setEnabled(not checked)
            if checked:
                # Store None in data model and clear the date field visually
                end_date_edit.blockSignals(True)
                end_date_edit.clear()  # Clear the date field instead of showing current date
                end_date_edit.blockSignals(False)
                # Unified model: ongoing = end_date is None
                self._update_education_field(edu_obj, 'end_date', None)
            else:
                # Re-enable and set to current month as reasonable default
                from datetime import datetime
                now = datetime.now()
                end_date_edit.blockSignals(True)
                end_date_edit.setDate(QDate(now.year, now.month, 1))
                end_date_edit.blockSignals(False)
                date_str = f"{now.month:02d}/{now.year}"
                self._update_education_field(edu_obj, 'end_date', date_str)

        ongoing_check.toggled.connect(_on_ongoing_toggled)
        
        # Lieu
        location_edit = QLineEdit(str(edu.get('location', '')))
        location_edit.setPlaceholderText("Lieu...")
        location_edit.setStyleSheet("""
            QLineEdit {
                background-color: #3a3a3a;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 6px;
                color: #ffffff;
            }
            QLineEdit:focus {
                border: 2px solid #4db8ff;
            }
        """)
        location_edit.textChanged.connect(lambda text: self._update_education_field(edu_obj, 'location', text))
        
        period_layout.addWidget(QLabel("📅"))
        period_layout.addWidget(start_date_edit)
        period_layout.addWidget(QLabel(" à "))
        period_layout.addWidget(end_date_edit)
        period_layout.addWidget(ongoing_check)
        period_layout.addWidget(QLabel("📍"))
        period_layout.addWidget(location_edit)
        period_layout.addStretch()
        
        return period_layout
    
    def create_education_description(self, edu: Dict, edu_obj: Dict) -> QTextEdit:
        """Crée le champ de description de la formation."""
        desc_edit = QTextEdit()
        description = edu.get('description', '')
        
        # Convertir en string si c'est une liste
        if isinstance(description, list):
            description = '\n'.join(str(item) for item in description)
        elif not isinstance(description, str):
            description = str(description)
            
        desc_edit.setPlainText(description)
        desc_edit.setPlaceholderText("Description de la formation...")
        desc_edit.setMaximumHeight(100)
        desc_edit.textChanged.connect(lambda: self._update_education_field(edu_obj, 'description', desc_edit.toPlainText()))
        
        return desc_edit
    # delete button helper inherited from BaseSection
    def get_section_data(self) -> List[Dict[str, Any]]:
        """Retourne les données de formation."""
        return self.profile.extracted_education if self.profile.extracted_education else []
    
    def _update_display(self):
        """Met à jour l'affichage (message et titre) selon le nombre d'éléments."""
        education_data = getattr(self.profile, 'extracted_education', []) or []
        edu_count = len(education_data)
        
        # Gérer l'affichage du message "aucune formation"
        if hasattr(self, 'no_edu_label'):
            if edu_count == 0:
                self.no_edu_label.show()
            else:
                self.no_edu_label.hide()
        
        # Mettre à jour le titre avec le nouveau compteur
        if hasattr(self, 'section') and hasattr(self.section, 'title_label'):
            new_title = f"🎓 Formation ({edu_count} diplôme{'s' if edu_count != 1 else ''})"
            self.section.title_label.setText(new_title)
    
    def _add_education_widget_to_layout(self, education):
        """Ajoute un widget de formation directement au layout."""
        if hasattr(self, 'content_layout'):
            # Créer et ajouter le nouveau widget
            edu_widget = self.create_education_widget(education, education)
            self.content_layout.addWidget(edu_widget)
            self.education_widgets.append(edu_widget)
            
            # Mettre à jour l'affichage
            self._update_display()

    def add_new_education(self):
        """Ajoute une nouvelle formation."""
        if not hasattr(self.profile, 'extracted_education') or not self.profile.extracted_education:
            self.profile.extracted_education = []
        
        new_education = {
            'degree': 'Nouveau diplôme',
            'institution': 'Nouvelle école',
            'start_date': '',
            'end_date': None,
            'location': '',
            'description': '',
            'source': 'Manuel'
        }
        
        self.profile.extracted_education.append(new_education)
        
        # Déclencher la détection de modifications
        self.emit_data_updated(force_reload=True)
        
        # Ajouter directement le widget sans recharger toute l'interface
        self._add_education_widget_to_layout(new_education)
    
    def delete_education(self, edu_obj: Dict, widget: QWidget):
        """Supprime une formation."""
        if hasattr(self.profile, 'extracted_education') and self.profile.extracted_education:
            try:
                self.profile.extracted_education.remove(edu_obj)
                widget.deleteLater()
                if widget in self.education_widgets:
                    self.education_widgets.remove(widget)
                
                # Mettre à jour l'affichage dynamiquement
                self._update_display()
                
                # Sauvegarder les données sans rechargement complet
                self.emit_data_updated(force_reload=False)
            except ValueError:
                pass  # La formation n'était pas dans la liste
    
    def _update_education_field(self, edu_obj: Dict, field: str, value: str):
        """Met à jour un champ d'une formation."""
        edu_obj[field] = value
        # Émettre signal de modification sans rechargement complet
        self.emit_data_updated(force_reload=False)
