"""
Section des expériences professionnelles du profil.

Cette section gère l'affichage, l'édition, l'ajout et la suppression
des expériences professionnelles du profil utilisateur.
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


class ExperienceSection(BaseSection):
    """Section pour les expériences professionnelles du profil."""
    
    def __init__(self, profile: UserProfile, parent=None):
        super().__init__(profile, parent)
        self.experience_widgets = []
        
    def create_section_widget(self) -> QWidget:
        """Crée la section expériences professionnelles collapsible."""
        # Contenu de la section
        content_widget = QWidget()
        self.content_layout = QVBoxLayout(content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        
        # Bouton ajouter expérience
        add_exp_btn = self.create_add_button()
        add_exp_btn.clicked.connect(self.add_new_experience)
        self.content_layout.addWidget(add_exp_btn)
        
        # Toujours créer le label "aucune expérience" (masqué si nécessaire)
        self.no_exp_label = QLabel("Aucune expérience extraite à forte confidence. Utilisez le bouton ci-dessus pour en ajouter.")
        self.no_exp_label.setStyleSheet("color: #a0a0a0; font-style: italic; padding: 20px; text-align: center;")
        self.content_layout.addWidget(self.no_exp_label)
        
        # Liste des expériences existantes (filtrées)
        all_experiences = self.profile.extracted_experiences if self.profile.extracted_experiences else []
        
        # Filtrer les expériences par confidence et règles de validation  
        filtered_experiences = [
            exp for exp in all_experiences
            if self._get_confidence_score(exp.get('confidence', 'medium')) >= 0.5 
            and 'R-EXP' not in ' '.join(exp.get('explain_rules', []))
            and not (exp.get('title') == 'Poste à définir' and exp.get('company') == 'Entreprise à définir')
        ]
        
        from loguru import logger
        logger.info(f"🛠️ Création de {len(filtered_experiences)} widgets d'expérience validées sur {len(all_experiences)} total")
        
        for i, exp in enumerate(filtered_experiences):
            logger.info(f"🛠️ Création widget expérience {i+1}: {exp.get('title', 'Sans titre')}")
            exp_widget = self.create_experience_widget(exp, exp)
            self.content_layout.addWidget(exp_widget)
            self.experience_widgets.append(exp_widget)
            logger.info(f"✅ Widget expérience {i+1} ajouté au layout")
        
        # Créer section collapsible avec titre initial
        exp_count = len(filtered_experiences)
        title = f"💼 Expériences professionnelles ({exp_count} entrée{'s' if exp_count != 1 else ''})"
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
        """Crée le bouton d'ajout d'expérience."""
        add_exp_btn = QPushButton("➕ Ajouter une expérience")
        add_exp_btn.setStyleSheet("""
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
        return add_exp_btn
    
    def create_experience_widget(self, exp, exp_obj) -> QWidget:
        """Crée un widget pour une expérience."""
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
        
        # Gérer le cas où exp est une string
        if isinstance(exp, str):
            exp_label = QLabel(exp)
            exp_label.setWordWrap(True)
            exp_label.setStyleSheet("padding: 10px; background: transparent;")
            layout.addWidget(exp_label)
            return widget
        
        # Si c'est un dict, procéder normalement
        if not isinstance(exp, dict):
            exp = {}
        
        # Header éditable
        header_layout = self.create_experience_header(exp, exp_obj, widget)
        layout.addLayout(header_layout)
        
        # Période et lieu éditables
        period_layout = self.create_experience_period(exp, exp_obj)
        layout.addLayout(period_layout)
        
        # Description éditable
        desc_edit = self.create_experience_description(exp, exp_obj)
        layout.addWidget(desc_edit)
        
        return widget
    
    def create_experience_header(self, exp: Dict, exp_obj: Dict, widget: QWidget) -> QHBoxLayout:
        """Crée l'en-tête de l'expérience avec titre, entreprise et actions."""
        header_layout = QHBoxLayout()
        
        title_edit = QLineEdit(str(exp.get('title', 'Poste')))
        title_edit.setPlaceholderText("Intitulé du poste...")
        title_edit.setStyleSheet("""
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
        title_edit.textChanged.connect(lambda text: self._update_experience_field(exp_obj, 'title', text))
        header_layout.addWidget(title_edit)
        
        # Label "chez" sans encadré
        chez_label = QLabel(" chez ")
        chez_label.setStyleSheet("font-size: 14px; color: #e0e0e0; font-style: italic;")
        header_layout.addWidget(chez_label)
        
        company_edit = QLineEdit(str(exp.get('company', 'Entreprise')))
        company_edit.setPlaceholderText("Nom de l'entreprise...")
        company_edit.setStyleSheet("""
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
        company_edit.textChanged.connect(lambda text: self._update_experience_field(exp_obj, 'company', text))
        header_layout.addWidget(company_edit)
        
        # Badge source
        source = exp.get('source', 'CV')
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
        delete_btn.clicked.connect(lambda: self.delete_experience(exp_obj, widget))
        header_layout.addWidget(delete_btn)
        
        return header_layout
    
    def create_experience_period(self, exp: Dict, exp_obj: Dict) -> QHBoxLayout:
        """Crée la section période et lieu de l'expérience."""
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
        start_date_str = exp.get('start_date', '')
        if start_date_str:
            try:
                # Essayer de parser différents formats de date
                if '/' in start_date_str:
                    parts = start_date_str.split('/')
                    if len(parts) >= 2:
                        month, year = int(parts[0]), int(parts[1])
                        start_date_edit.setDate(QDate(year, month, 1))
                elif len(start_date_str) == 4 and start_date_str.isdigit():  # Juste l'année
                    start_date_edit.setDate(QDate(int(start_date_str), 1, 1))
            except (ValueError, IndexError):
                start_date_edit.setDate(QDate.currentDate())
        else:
            start_date_edit.setDate(QDate.currentDate())
        
        start_date_edit.dateChanged.connect(lambda date: self._update_experience_field(exp_obj, 'start_date', date.toString("MM/yyyy")))
        
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

        # Pas de date sentinelle: l'état "En cours" est représenté dans le modèle par une chaîne vide et le flag current

        # Définir la date de fin (provisoire)
        end_date_str = exp.get('end_date', '')
        if end_date_str not in [None, ''] and (not isinstance(end_date_str, str) or end_date_str.lower() not in ['présent', 'en cours', 'current']):
            try:
                if '/' in end_date_str:
                    parts = end_date_str.split('/')
                    if len(parts) >= 2:
                        month, year = int(parts[0]), int(parts[1])
                        end_date_edit.setDate(QDate(year, month, 1))
                elif len(end_date_str) == 4 and end_date_str.isdigit():
                    end_date_edit.setDate(QDate(int(end_date_str), 12, 31))
            except (ValueError, IndexError):
                end_date_edit.setDate(QDate.currentDate())
        else:
            end_date_edit.setDate(QDate.currentDate())
        
        def _on_end_date_changed(date: QDate):
            self._update_experience_field(exp_obj, 'end_date', date.toString("MM/yyyy"))
            self._update_experience_field(exp_obj, 'current', False)

        end_date_edit.dateChanged.connect(_on_end_date_changed)

        # Option "En cours" - synchronisée avec end_date vide et le flag current
        ongoing_check = QCheckBox("En cours")
        try:
            end_date_value = exp.get('end_date')
            # Unified ongoing logic: None, empty or ongoing patterns = ongoing
            if end_date_value is None:
                is_ongoing = True
            elif isinstance(end_date_value, str):
                end_str_lower = end_date_value.lower().strip()
                if end_str_lower == '':
                    is_ongoing = True
                else:
                    ongoing_patterns = ['présent', 'present', 'en cours', 'current', 'currently',
                                        'à ce jour', 'à ce jour', 'a ce jour', 'maintenant', 'now', 'today', 'ongoing', 'actuel']
                    is_ongoing = any(pattern in end_str_lower for pattern in ongoing_patterns)
            else:
                is_ongoing = False
        except Exception:
            is_ongoing = False

        exp_obj['current'] = bool(is_ongoing)
        ongoing_check.setChecked(is_ongoing)
        if is_ongoing:
            # Désactiver le sélecteur et afficher une date neutre (aujourd'hui) tout en stockant une fin vide
            exp_obj['current'] = True
            end_date_edit.blockSignals(True)
            end_date_edit.setDate(QDate.currentDate())
            end_date_edit.blockSignals(False)
            end_date_edit.setEnabled(False)

        def _on_ongoing_toggled(checked: bool):
            end_date_edit.setEnabled(not checked)
            self._update_experience_field(exp_obj, 'current', checked)
            if checked:
                end_date_edit.blockSignals(True)
                end_date_edit.clear()
                end_date_edit.blockSignals(False)
                self._update_experience_field(exp_obj, 'end_date', '')
            else:
                from datetime import datetime
                now = datetime.now()
                end_date_edit.blockSignals(True)
                end_date_edit.setDate(QDate(now.year, now.month, 1))
                end_date_edit.blockSignals(False)
                date_str = f"{now.month:02d}/{now.year}"
                self._update_experience_field(exp_obj, 'end_date', date_str)

        ongoing_check.toggled.connect(_on_ongoing_toggled)
        
        # Lieu
        location_edit = QLineEdit(str(exp.get('location', '')))
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
        location_edit.textChanged.connect(lambda text: self._update_experience_field(exp_obj, 'location', text))
        
        period_layout.addWidget(QLabel("📅"))
        period_layout.addWidget(start_date_edit)
        period_layout.addWidget(QLabel(" à "))
        period_layout.addWidget(end_date_edit)
        period_layout.addWidget(ongoing_check)
        period_layout.addWidget(QLabel("📍"))
        period_layout.addWidget(location_edit)
        period_layout.addStretch()
        
        return period_layout
    
    def create_experience_description(self, exp: Dict, exp_obj: Dict) -> QTextEdit:
        """Crée le champ de description de l'expérience."""
        desc_edit = QTextEdit()
        description = exp.get('description', '')
        
        # Convertir en string si c'est une liste
        if isinstance(description, list):
            description = '\n'.join(str(item) for item in description)
        elif not isinstance(description, str):
            description = str(description)
            
        desc_edit.setPlainText(description)
        desc_edit.setPlaceholderText("Description du poste...")
        desc_edit.setMaximumHeight(100)
        desc_edit.textChanged.connect(lambda: self._update_experience_field(exp_obj, 'description', desc_edit.toPlainText()))
        
        return desc_edit
    # delete button helper inherited from BaseSection
    def get_section_data(self) -> List[Dict[str, Any]]:
        """Retourne les données des expériences."""
        return self.profile.extracted_experiences if self.profile.extracted_experiences else []
    
    def add_new_experience(self):
        """Ajoute une nouvelle expérience."""
        if not hasattr(self.profile, 'extracted_experiences') or not self.profile.extracted_experiences:
            self.profile.extracted_experiences = []
        
        new_experience = {
            'title': 'Nouveau poste',
            'company': 'Nouvelle entreprise',
            'start_date': '',
            'end_date': '',
            'location': '',
            'description': '',
            'source': 'Manuel'
        }
        
        self.profile.extracted_experiences.append(new_experience)
        
        # Déclencher la détection de modifications
        self.emit_data_updated(force_reload=True)
        
        # Ajouter directement le widget sans recharger toute l'interface
        self._add_experience_widget_to_layout(new_experience)
    
    def delete_experience(self, exp_obj: Dict, widget: QWidget):
        """Supprime une expérience."""
        if hasattr(self.profile, 'extracted_experiences') and self.profile.extracted_experiences:
            try:
                self.profile.extracted_experiences.remove(exp_obj)
                widget.deleteLater()
                if widget in self.experience_widgets:
                    self.experience_widgets.remove(widget)
                
                # Notifier le parent qu'il y a eu des modifications
                if hasattr(self.parent(), 'on_data_modified'):
                    self.parent().on_data_modified()
                
                # Mettre à jour l'affichage dynamiquement
                self._update_display()
                
                # Sauvegarder les données sans rechargement complet
                self.emit_data_updated(force_reload=False)
            except ValueError:
                pass  # L'expérience n'était pas dans la liste
    
    def _update_display(self):
        """Met à jour l'affichage (message et titre) selon le nombre d'éléments."""
        experiences_data = getattr(self.profile, 'extracted_experiences', []) or []
        
        # Filtrer les expériences par confidence et règles de validation
        filtered_experiences = [
            exp for exp in experiences_data
            if self._get_confidence_score(exp.get('confidence', 'medium')) >= 0.5 
            and 'R-EXP' not in ' '.join(exp.get('explain_rules', []))
            and not (exp.get('title') == 'Poste à définir' and exp.get('company') == 'Entreprise à définir')
        ]
        
        exp_count = len(filtered_experiences)
        
        from loguru import logger
        logger.info(f"🎯 ExperienceSection._update_display() - {exp_count} expériences validées sur {len(experiences_data)} total")
        
        # Gérer l'affichage du message "aucune expérience"
        if hasattr(self, 'no_exp_label'):
            if exp_count == 0:
                self.no_exp_label.show()
                logger.info("🙁 Affichage du message 'aucune expérience'")
            else:
                self.no_exp_label.hide()
                logger.info("🙂 Masquage du message 'aucune expérience'")
        
        # Mettre à jour le titre avec le nouveau compteur
        if hasattr(self, 'section') and hasattr(self.section, 'title_label'):
            new_title = f"💼 Expériences professionnelles ({exp_count} entrée{'s' if exp_count != 1 else ''})"
            self.section.title_label.setText(new_title)
            logger.info(f"🏷️ Titre mis à jour: {new_title}")

    def _add_experience_widget_to_layout(self, experience):
        """Ajoute un widget d'expérience directement au layout."""
        if hasattr(self, 'content_layout'):
            # Créer et ajouter le nouveau widget
            exp_widget = self.create_experience_widget(experience, experience)
            self.content_layout.addWidget(exp_widget)
            self.experience_widgets.append(exp_widget)
            
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

    def _update_experience_field(self, exp_obj: Dict, field: str, value: str):
        """Met à jour un champ d'une expérience."""
        exp_obj[field] = value
        # Émettre signal de modification sans rechargement complet
        self.emit_data_updated(force_reload=False)
