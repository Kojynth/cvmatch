"""Section du bénévolat du profil."""
from typing import List, Dict, Any
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame, QLineEdit, QTextEdit, QDateEdit, QComboBox, QSpinBox, QCheckBox
from PySide6.QtCore import QDate
from .base_section import BaseSection
from ...widgets.collapsible_section import create_collapsible_section

class VolunteeringSection(BaseSection):
    def __init__(self, profile, parent=None):
        super().__init__(profile, parent)
        self.vol_widgets = []
        
    def create_section_widget(self) -> QWidget:
        content_widget = QWidget()
        self.content_layout = QVBoxLayout(content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        
        add_btn = QPushButton("➕ Ajouter un bénévolat")
        add_btn.setStyleSheet("QPushButton { background-color: #2d5f3f; color: white; border: none; padding: 12px 20px; border-radius: 8px; font-weight: bold; font-size: 14px; margin: 5px; } QPushButton:hover { background-color: #1e4f2f; }")
        add_btn.clicked.connect(self.add_new_volunteering)
        self.content_layout.addWidget(add_btn)
        
        # Toujours créer le label "aucun bénévolat"
        self.no_data_label = QLabel("Aucun bénévolat extrait. Utilisez le bouton ci-dessus pour en ajouter.")
        self.no_data_label.setStyleSheet("color: #a0a0a0; font-style: italic; padding: 20px; text-align: center;")
        self.content_layout.addWidget(self.no_data_label)
        
        data = self.get_section_data()
        for item in data:
            widget = self.create_volunteering_widget(item, item)
            self.content_layout.addWidget(widget)
            self.vol_widgets.append(widget)
        
        count = len(data)
        title = f"🤝 Bénévolat ({count} activité{'s' if count != 1 else ''})"
        self.section = create_collapsible_section(title, content_widget, "▼", True)
        
        # Mettre à jour l'affichage initial
        self._update_display()
        
        try:
            from ..text_cleaner import sanitize_widget_tree
            sanitize_widget_tree(content_widget)
        except Exception:
            pass
        return self.section
    
    def create_volunteering_widget(self, vol, vol_obj) -> QWidget:
        widget = QFrame()
        widget.setStyleSheet("QFrame { background-color: #3a3a3a; border: 1px solid #555555; border-radius: 12px; margin: 8px; padding: 15px; } QFrame:hover { border: 1px solid #4db8ff; background-color: #404040; }")
        layout = QVBoxLayout(widget)
        
        if not isinstance(vol, dict):
            vol = {}
        
        # En-tête avec rôle et bouton supprimer
        header_layout = QHBoxLayout()
        role_edit = QLineEdit(str(vol.get('role', 'Nouveau bénévolat')))
        role_edit.setStyleSheet("""
            QLineEdit {
                background-color: #3a3a3a;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 8px;
                font-weight: bold;
                font-size: 14px;
                color: white;
            }
            QLineEdit:focus {
                border: 2px solid #4db8ff;
                background-color: #404040;
            }
            QLineEdit:hover {
                border-color: #777777;
            }
        """)
        role_edit.textChanged.connect(lambda text: self._update_field(vol_obj, 'role', text))
        header_layout.addWidget(role_edit)
        
        # Badge source
        source = vol.get('source', 'CV')
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
        delete_btn = QPushButton("✖")
        delete_btn.setFixedSize(28, 28)
        delete_btn.setStyleSheet("QPushButton { background: #DC143C; border-radius: 14px; color: #FFFFFF; font-weight: bold; font-size: 14px; border: none; } QPushButton:hover { background: #B22222; }")
        delete_btn.clicked.connect(lambda: self.delete_volunteering(vol_obj, widget))
        header_layout.addWidget(delete_btn)
        layout.addLayout(header_layout)
        
        # Ligne Organisation et Statut
        org_status_layout = QHBoxLayout()
        
        # Organisation
        org_label = QLabel("🏢 Organisation :")
        org_label.setStyleSheet("color: white; font-weight: bold; min-width: 100px;")
        org_edit = QLineEdit(str(vol.get('organization', '')))
        org_edit.setStyleSheet("""
            QLineEdit {
                background-color: #3a3a3a;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 8px;
                color: white;
            }
            QLineEdit:focus {
                border: 2px solid #4db8ff;
                background-color: #404040;
            }
            QLineEdit:hover {
                border-color: #777777;
            }
        """)
        org_edit.textChanged.connect(lambda text: self._update_field(vol_obj, 'organization', text))
        
        # Statut
        status_label = QLabel("📊 Statut :")
        status_label.setStyleSheet("color: white; font-weight: bold; min-width: 70px;")
        status_combo = QComboBox()
        status_combo.addItems([
            "🛠️ En cours",
            "✅ Terminé",
            "⏸️ En pause",
            "📅 Régulier",
            "🎖️ Ponctuel",
            "🗓️ Saisonnier"
        ])
        current_status = vol.get('status', '🛠️ En cours')
        status_index = status_combo.findText(current_status)
        if status_index >= 0:
            status_combo.setCurrentIndex(status_index)
        status_combo.setStyleSheet("""
            QComboBox {
                background-color: #3a3a3a;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 8px;
                color: white;
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
                background-color: #4a4a4a;
            }
            QComboBox::drop-down:hover {
                background-color: #5a5a5a;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid white;
                width: 0px;
                height: 0px;
            }
            QComboBox QAbstractItemView {
                background-color: #2a2a2a;
                border: 1px solid #555555;
                selection-background-color: #4db8ff;
                color: white;
            }
        """)
        status_combo.currentTextChanged.connect(lambda text: self._update_field(vol_obj, 'status', text))
        
        org_status_layout.addWidget(org_label)
        org_status_layout.addWidget(org_edit, 2)
        org_status_layout.addWidget(status_label)
        org_status_layout.addWidget(status_combo, 1)
        
        layout.addLayout(org_status_layout)
        
        # Ligne Dates de début et fin
        dates_layout = QHBoxLayout()
        
        # Date de début
        start_label = QLabel("📅 Début :")
        start_label.setStyleSheet("color: white; font-weight: bold; min-width: 70px;")
        start_edit = QDateEdit()
        start_edit.setDisplayFormat("MM/yyyy")
        start_edit.setCalendarPopup(True)
        
        # Déterminer la date de début
        start_date_str = vol.get('start_date', '')
        if start_date_str:
            try:
                if '/' in start_date_str and len(start_date_str.split('/')) == 2:
                    month, year = start_date_str.split('/')
                    start_edit.setDate(QDate(int(year), int(month), 1))
                elif len(start_date_str) == 4:
                    start_edit.setDate(QDate(int(start_date_str), 1, 1))
                else:
                    start_edit.setDate(QDate.currentDate())
            except (ValueError, IndexError):
                start_edit.setDate(QDate.currentDate())
        else:
            start_edit.setDate(QDate.currentDate())
        
        start_edit.setStyleSheet("""
            QDateEdit {
                background-color: #3a3a3a;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 8px;
                color: white;
                min-width: 100px;
            }
            QDateEdit:focus {
                border: 2px solid #4db8ff;
                background-color: #404040;
            }
            QDateEdit:hover {
                border-color: #777777;
            }
            QDateEdit::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 20px;
                border-left: 1px solid #555555;
                background-color: #4a4a4a;
            }
            QDateEdit::drop-down:hover {
                background-color: #5a5a5a;
            }
            QDateEdit::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid white;
                width: 0px;
                height: 0px;
            }
        """)
        start_edit.dateChanged.connect(lambda date: self._update_field(vol_obj, 'start_date', date.toString("MM/yyyy")))
        
        # Date de fin
        end_label = QLabel("🏁 Fin :")
        end_label.setStyleSheet("color: white; font-weight: bold; min-width: 50px;")
        end_edit = QDateEdit()
        end_edit.setDisplayFormat("MM/yyyy")
        end_edit.setCalendarPopup(True)
        # Pas de sentinelle: l'état "En cours" se reflète dans le modèle (None)
        _end_str = (vol.get('end_date', '') or '').strip()
        _ongoing = False
        try:
            _ongoing = (_end_str == '') or (_end_str.lower() in ['présent','present','en cours','current']) or (vol.get('end_date') is None)
        except Exception:
            _ongoing = False
        
        # Déterminer la date de fin
        end_date_str = vol.get('end_date', '')
        if end_date_str and not _ongoing:
            try:
                if '/' in end_date_str and len(end_date_str.split('/')) == 2:
                    month, year = end_date_str.split('/')
                    end_edit.setDate(QDate(int(year), int(month), 1))
                elif len(end_date_str) == 4:
                    end_edit.setDate(QDate(int(end_date_str), 12, 31))
                else:
                    end_edit.setDate(QDate.currentDate())
            except (ValueError, IndexError):
                end_edit.setDate(QDate.currentDate())
        else:
            end_edit.setDate(QDate.currentDate())
            if _ongoing:
                end_edit.blockSignals(True)
                end_edit.setDate(QDate.currentDate())
                end_edit.blockSignals(False)
                end_edit.setEnabled(False)
        
        end_edit.setStyleSheet("""
            QDateEdit {
                background-color: #3a3a3a;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 8px;
                color: white;
                min-width: 100px;
            }
            QDateEdit:focus {
                border: 2px solid #4db8ff;
                background-color: #404040;
            }
            QDateEdit:hover {
                border-color: #777777;
            }
            QDateEdit::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 20px;
                border-left: 1px solid #555555;
                background-color: #4a4a4a;
            }
            QDateEdit::drop-down:hover {
                background-color: #5a5a5a;
            }
            QDateEdit::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid white;
                width: 0px;
                height: 0px;
            }
        """)
        end_edit.dateChanged.connect(lambda date: self._update_field(vol_obj, 'end_date', date.toString("MM/yyyy")))

        # Case à cocher "En cours" (désactive la date de fin)
        ongoing_check = QCheckBox("En cours")
        ongoing_check.setChecked(_ongoing)
        def _on_ongoing_toggled(checked: bool):
            end_edit.setEnabled(not checked)
            if checked:
                # Store None in data model and clear the date field visually
                end_edit.blockSignals(True)
                end_edit.clear()  # Clear the date field instead of showing current date
                end_edit.blockSignals(False)
                # Store null to represent ongoing
                self._update_field(vol_obj, 'end_date', None)
            else:
                # Re-enable and set to current month as reasonable default
                from datetime import datetime
                now = datetime.now()
                end_edit.blockSignals(True)
                end_edit.setDate(QDate(now.year, now.month, 1))
                end_edit.blockSignals(False)
                date_str = f"{now.month:02d}/{now.year}"
                self._update_field(vol_obj, 'end_date', date_str)
        ongoing_check.toggled.connect(_on_ongoing_toggled)
        
        dates_layout.addWidget(start_label)
        dates_layout.addWidget(start_edit, 1)
        dates_layout.addWidget(end_label)
        dates_layout.addWidget(end_edit, 1)
        dates_layout.addWidget(ongoing_check)
        
        layout.addLayout(dates_layout)
        
        # Ligne Heures par semaine et Lieu
        hours_location_layout = QHBoxLayout()
        
        # Heures par semaine
        hours_label = QLabel("⏱️ Heures/sem. :")
        hours_label.setStyleSheet("color: white; font-weight: bold; min-width: 90px;")
        hours_spin = QSpinBox()
        hours_spin.setMinimum(0)
        hours_spin.setMaximum(168)  # Max heures dans une semaine
        hours_spin.setSuffix(" h")
        hours_spin.setValue(vol.get('hours_per_week', 0))
        hours_spin.setStyleSheet("""
            QSpinBox {
                background-color: #3a3a3a;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 8px;
                color: white;
                min-width: 80px;
            }
            QSpinBox:focus {
                border: 2px solid #4db8ff;
                background-color: #404040;
            }
            QSpinBox:hover {
                border-color: #777777;
            }
            QSpinBox::up-button {
                subcontrol-origin: border;
                subcontrol-position: top right;
                width: 20px;
                background-color: #4a4a4a;
                border-left: 1px solid #555555;
            }
            QSpinBox::down-button {
                subcontrol-origin: border;
                subcontrol-position: bottom right;
                width: 20px;
                background-color: #4a4a4a;
                border-left: 1px solid #555555;
            }
            QSpinBox::up-arrow {
                border-left: 3px solid transparent;
                border-right: 3px solid transparent;
                border-bottom: 4px solid white;
                width: 0px;
                height: 0px;
            }
            QSpinBox::down-arrow {
                border-left: 3px solid transparent;
                border-right: 3px solid transparent;
                border-top: 4px solid white;
                width: 0px;
                height: 0px;
            }
        """)
        hours_spin.valueChanged.connect(lambda value: self._update_field(vol_obj, 'hours_per_week', value))
        
        # Lieu
        location_label = QLabel("📍 Lieu :")
        location_label.setStyleSheet("color: white; font-weight: bold; min-width: 60px;")
        location_edit = QLineEdit(str(vol.get('location', '')))
        location_edit.setPlaceholderText("Ville, pays")
        location_edit.setStyleSheet("""
            QLineEdit {
                background-color: #3a3a3a;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 8px;
                color: white;
            }
            QLineEdit:focus {
                border: 2px solid #4db8ff;
                background-color: #404040;
            }
            QLineEdit:hover {
                border-color: #777777;
            }
        """)
        location_edit.textChanged.connect(lambda text: self._update_field(vol_obj, 'location', text))
        
        hours_location_layout.addWidget(hours_label)
        hours_location_layout.addWidget(hours_spin, 1)
        hours_location_layout.addWidget(location_label)
        hours_location_layout.addWidget(location_edit, 2)
        
        layout.addLayout(hours_location_layout)
        
        # Ligne Compétences acquises
        skills_layout = QHBoxLayout()
        skills_label = QLabel("🎯 Compétences acquises :")
        skills_label.setStyleSheet("color: white; font-weight: bold; min-width: 140px;")
        skills_edit = QLineEdit(str(vol.get('skills_gained', '')))
        skills_edit.setPlaceholderText("Communication, leadership, gestion...")
        skills_edit.setStyleSheet("""
            QLineEdit {
                background-color: #3a3a3a;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 8px;
                color: white;
            }
            QLineEdit:focus {
                border: 2px solid #4db8ff;
                background-color: #404040;
            }
            QLineEdit:hover {
                border-color: #777777;
            }
        """)
        skills_edit.textChanged.connect(lambda text: self._update_field(vol_obj, 'skills_gained', text))
        
        skills_layout.addWidget(skills_label)
        skills_layout.addWidget(skills_edit)
        
        layout.addLayout(skills_layout)
        
        # Impact/Résultats
        impact_label = QLabel("🏆 Impact/Résultats :")
        impact_label.setStyleSheet("color: white; font-weight: bold; margin-top: 10px;")
        layout.addWidget(impact_label)
        
        impact_edit = QTextEdit(str(vol.get('impact', '')))
        impact_edit.setMaximumHeight(60)
        impact_edit.setPlaceholderText("Ex: Aide à 100 familles, organisation de 5 événements...")
        impact_edit.setStyleSheet("""
            QTextEdit {
                background-color: #3a3a3a;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 8px;
                color: white;
            }
            QTextEdit:focus {
                border: 2px solid #4db8ff;
                background-color: #404040;
            }
            QTextEdit:hover {
                border-color: #777777;
            }
        """)
        impact_edit.textChanged.connect(lambda: self._update_field(vol_obj, 'impact', impact_edit.toPlainText()))
        layout.addWidget(impact_edit)
        
        return widget
    
    def get_section_data(self) -> List[Dict[str, Any]]:
        return getattr(self.profile, 'extracted_volunteering', []) or []
    
    def _update_display(self):
        """Met à jour l'affichage (message et titre) selon le nombre d'éléments."""
        volunteering_data = getattr(self.profile, 'extracted_volunteering', []) or []
        vol_count = len(volunteering_data)
        
        # Gérer l'affichage du message "aucun bénévolat"
        if hasattr(self, 'no_data_label'):
            if vol_count == 0:
                self.no_data_label.show()
            else:
                self.no_data_label.hide()
        
        # Mettre à jour le titre avec le nouveau compteur
        if hasattr(self, 'section') and hasattr(self.section, 'title_label'):
            new_title = f"🤝 Bénévolat ({vol_count} activité{'s' if vol_count != 1 else ''})"
            self.section.title_label.setText(new_title)

    def _add_volunteering_widget_to_layout(self, volunteering):
        """Ajoute un widget de bénévolat directement au layout."""
        if hasattr(self, 'content_layout'):
            widget = self.create_volunteering_widget(volunteering, volunteering)
            self.content_layout.addWidget(widget)
            self.vol_widgets.append(widget)
            
            # Mettre à jour l'affichage
            self._update_display()

    def add_new_volunteering(self):
        if not hasattr(self.profile, 'extracted_volunteering') or not self.profile.extracted_volunteering:
            self.profile.extracted_volunteering = []
        new_vol = {
            'role': 'Nouveau bénévolat',
            'organization': '',
            'start_date': '',
            'end_date': None,
            'status': '🛠️ En cours',
            'hours_per_week': 0,
            'location': '',
            'skills_gained': '',
            'impact': '',
            'source': 'Manuel'
        }
        self.profile.extracted_volunteering.append(new_vol)
        
        # Déclencher la détection de modifications
        self.emit_data_updated(force_reload=True)
        self._add_volunteering_widget_to_layout(new_vol)
    
    def delete_volunteering(self, vol_obj, widget):
        if hasattr(self.profile, 'extracted_volunteering') and self.profile.extracted_volunteering:
            try:
                self.profile.extracted_volunteering.remove(vol_obj)
                widget.deleteLater()
                if widget in self.vol_widgets:
                    self.vol_widgets.remove(widget)
                
                # Mettre à jour l'affichage dynamiquement
                self._update_display()
                
                # Sauvegarder les données sans rechargement complet
                self.emit_data_updated(force_reload=False, )
            except ValueError:
                pass
    
    def _update_field_legacy(self, obj, field, value):
        obj[field] = value
        # Ne pas déclencher de rechargement complet
