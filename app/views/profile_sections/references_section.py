"""Section des références du profil."""
from typing import List, Dict, Any
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame, QLineEdit, QTextEdit, QComboBox
from .base_section import BaseSection
from ...widgets.collapsible_section import create_collapsible_section

class ReferencesSection(BaseSection):
    def __init__(self, profile, parent=None):
        super().__init__(profile, parent)
        self.ref_widgets = []
        
    def create_section_widget(self) -> QWidget:
        content_widget = QWidget()
        self.content_layout = QVBoxLayout(content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        
        add_btn = QPushButton("➕ Ajouter une référence")
        add_btn.setStyleSheet("QPushButton { background-color: #2d5f3f; color: white; border: none; padding: 12px 20px; border-radius: 8px; font-weight: bold; font-size: 14px; margin: 5px; } QPushButton:hover { background-color: #1e4f2f; }")
        add_btn.clicked.connect(self.add_new_reference)
        self.content_layout.addWidget(add_btn)
        
        # Toujours créer le label "aucune référence"
        self.no_data_label = QLabel("Aucune référence extraite. Utilisez le bouton ci-dessus pour en ajouter.")
        self.no_data_label.setStyleSheet("color: #a0a0a0; font-style: italic; padding: 20px; text-align: center;")
        self.content_layout.addWidget(self.no_data_label)
        
        data = self.get_section_data()
        for item in data:
            widget = self.create_reference_widget(item, item)
            self.content_layout.addWidget(widget)
            self.ref_widgets.append(widget)
        
        count = len(data)
        title = f"👤 Références ({count} référence{'s' if count != 1 else ''})"
        self.section = create_collapsible_section(title, content_widget, "▼", True)
        
        # Mettre à jour l'affichage initial
        self._update_display()
        
        try:
            from ..text_cleaner import sanitize_widget_tree
            sanitize_widget_tree(content_widget)
        except Exception:
            pass
        return self.section
    
    def create_reference_widget(self, ref, ref_obj) -> QWidget:
        widget = QFrame()
        widget.setStyleSheet("QFrame { background-color: #3a3a3a; border: 1px solid #555555; border-radius: 12px; margin: 8px; padding: 15px; } QFrame:hover { border: 1px solid #4db8ff; background-color: #404040; }")
        layout = QVBoxLayout(widget)
        
        if not isinstance(ref, dict):
            ref = {}
        
        # En-tête avec nom et bouton supprimer
        header_layout = QHBoxLayout()
        name_edit = QLineEdit(str(ref.get('name', 'Nouvelle référence')))
        name_edit.setStyleSheet("""
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
        name_edit.textChanged.connect(lambda text: self._update_field(ref_obj, 'name', text))
        header_layout.addWidget(name_edit)
        
        # Badge source
        source = ref.get('source', 'CV')
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
        delete_btn.clicked.connect(lambda: self.delete_reference(ref_obj, widget))
        header_layout.addWidget(delete_btn)
        layout.addLayout(header_layout)
        
        # Ligne Poste et Entreprise
        position_company_layout = QHBoxLayout()
        
        # Poste
        position_label = QLabel("💼 Poste :")
        position_label.setStyleSheet("color: white; font-weight: bold; min-width: 70px;")
        position_edit = QLineEdit(str(ref.get('position', '')))
        position_edit.setPlaceholderText("Directeur, Manager, Collègue...")
        position_edit.setStyleSheet("""
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
        position_edit.textChanged.connect(lambda text: self._update_field(ref_obj, 'position', text))
        
        # Texte "chez"
        chez_label = QLabel("chez")
        chez_label.setStyleSheet("color: #a0a0a0; font-style: italic; margin: 0 8px;")
        
        # Entreprise
        company_edit = QLineEdit(str(ref.get('company', '')))
        company_edit.setPlaceholderText("Nom de l'entreprise")
        company_edit.setStyleSheet("""
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
        company_edit.textChanged.connect(lambda text: self._update_field(ref_obj, 'company', text))
        
        position_company_layout.addWidget(position_label)
        position_company_layout.addWidget(position_edit, 2)
        position_company_layout.addWidget(chez_label)
        position_company_layout.addWidget(company_edit, 2)
        
        layout.addLayout(position_company_layout)
        
        # Ligne Relation et Disponibilité
        relation_availability_layout = QHBoxLayout()
        
        # Type de relation
        relation_label = QLabel("🤝 Relation :")
        relation_label.setStyleSheet("color: white; font-weight: bold; min-width: 80px;")
        relation_combo = QComboBox()
        relation_combo.addItems([
            "💼 Ancien manager",
            "👤 Ancien collègue",
            "🎯 Client",
            "🤝 Partenaire",
            "🎓 Professeur",
            "🏢 Mentor",
            "📈 Subordonné",
            "🔗 Contact réseau",
            "📝 Autre"
        ])
        current_relation = ref.get('relation', '💼 Ancien manager')
        relation_index = relation_combo.findText(current_relation)
        if relation_index >= 0:
            relation_combo.setCurrentIndex(relation_index)
        relation_combo.setStyleSheet("""
            QComboBox {
                background-color: #3a3a3a;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 8px;
                color: white;
                min-width: 150px;
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
        relation_combo.currentTextChanged.connect(lambda text: self._update_field(ref_obj, 'relation', text))
        
        # Disponibilité
        availability_label = QLabel("🕒 Disponibilité :")
        availability_label.setStyleSheet("color: white; font-weight: bold; min-width: 90px;")
        availability_combo = QComboBox()
        availability_combo.addItems([
            "✅ Disponible",
            "🛠️ À contacter d'abord",
            "⏳ Disponible après préavis",
            "📞 Uniquement par téléphone",
            "📧 Uniquement par email",
            "⚠️ Limitée",
            "❌ Indisponible"
        ])
        current_availability = ref.get('availability', '✅ Disponible')
        availability_index = availability_combo.findText(current_availability)
        if availability_index >= 0:
            availability_combo.setCurrentIndex(availability_index)
        availability_combo.setStyleSheet("""
            QComboBox {
                background-color: #3a3a3a;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 8px;
                color: white;
                min-width: 180px;
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
        availability_combo.currentTextChanged.connect(lambda text: self._update_field(ref_obj, 'availability', text))
        
        relation_availability_layout.addWidget(relation_label)
        relation_availability_layout.addWidget(relation_combo, 1)
        relation_availability_layout.addWidget(availability_label)
        relation_availability_layout.addWidget(availability_combo, 1)
        
        layout.addLayout(relation_availability_layout)
        
        # Ligne Email et Téléphone
        contact_layout = QHBoxLayout()
        
        # Email
        email_label = QLabel("📧 Email :")
        email_label.setStyleSheet("color: white; font-weight: bold; min-width: 60px;")
        email_edit = QLineEdit(str(ref.get('email', '')))
        email_edit.setPlaceholderText("nom@entreprise.com")
        email_edit.setStyleSheet("""
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
        email_edit.textChanged.connect(lambda text: self._update_field(ref_obj, 'email', text))
        
        # Téléphone
        phone_label = QLabel("📞 Tél. :")
        phone_label.setStyleSheet("color: white; font-weight: bold; min-width: 50px;")
        phone_edit = QLineEdit(str(ref.get('phone', '')))
        phone_edit.setPlaceholderText("+33 6 12 34 56 78")
        phone_edit.setStyleSheet("""
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
        phone_edit.textChanged.connect(lambda text: self._update_field(ref_obj, 'phone', text))
        
        contact_layout.addWidget(email_label)
        contact_layout.addWidget(email_edit, 2)
        contact_layout.addWidget(phone_label)
        contact_layout.addWidget(phone_edit, 1)
        
        layout.addLayout(contact_layout)
        
        # Ligne LinkedIn et Années de connaissance
        linkedin_years_layout = QHBoxLayout()
        
        # LinkedIn
        linkedin_label = QLabel("🔗 LinkedIn :")
        linkedin_label.setStyleSheet("color: white; font-weight: bold; min-width: 80px;")
        linkedin_edit = QLineEdit(str(ref.get('linkedin', '')))
        linkedin_edit.setPlaceholderText("https://linkedin.com/in/...")
        linkedin_edit.setStyleSheet("""
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
        linkedin_edit.textChanged.connect(lambda text: self._update_field(ref_obj, 'linkedin', text))
        
        # Années de connaissance
        years_label = QLabel("📅 Connu depuis :")
        years_label.setStyleSheet("color: white; font-weight: bold; min-width: 100px;")
        years_edit = QLineEdit(str(ref.get('years_known', '')))
        years_edit.setPlaceholderText("2020-2023, 3 ans...")
        years_edit.setStyleSheet("""
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
        years_edit.textChanged.connect(lambda text: self._update_field(ref_obj, 'years_known', text))
        
        linkedin_years_layout.addWidget(linkedin_label)
        linkedin_years_layout.addWidget(linkedin_edit, 2)
        linkedin_years_layout.addWidget(years_label)
        linkedin_years_layout.addWidget(years_edit, 1)
        
        layout.addLayout(linkedin_years_layout)
        
        # Contexte de la relation
        context_label = QLabel("🎯 Contexte de collaboration :")
        context_label.setStyleSheet("color: white; font-weight: bold; margin-top: 10px;")
        layout.addWidget(context_label)
        
        context_edit = QTextEdit(str(ref.get('context', '')))
        context_edit.setMaximumHeight(60)
        context_edit.setPlaceholderText("Ex: Collaboration sur le projet X pendant 2 ans, management d'équipe...")
        context_edit.setStyleSheet("""
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
        context_edit.textChanged.connect(lambda: self._update_field(ref_obj, 'context', context_edit.toPlainText()))
        layout.addWidget(context_edit)
        
        # Notes personnelles
        notes_label = QLabel("📝 Notes personnelles :")
        notes_label.setStyleSheet("color: white; font-weight: bold; margin-top: 10px;")
        layout.addWidget(notes_label)
        
        notes_edit = QTextEdit(str(ref.get('notes', '')))
        notes_edit.setMaximumHeight(60)
        notes_edit.setPlaceholderText("Notes privées sur cette référence (pas dans le CV)...")
        notes_edit.setStyleSheet("""
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
        notes_edit.textChanged.connect(lambda: self._update_field(ref_obj, 'notes', notes_edit.toPlainText()))
        layout.addWidget(notes_edit)
        
        return widget
    
    def get_section_data(self) -> List[Dict[str, Any]]:
        return getattr(self.profile, 'extracted_references', []) or []
    
    def _update_display(self):
        """Met à jour l'affichage (message et titre) selon le nombre d'éléments."""
        references_data = getattr(self.profile, 'extracted_references', []) or []
        ref_count = len(references_data)
        
        # Gérer l'affichage du message "aucune référence"
        if hasattr(self, 'no_data_label'):
            if ref_count == 0:
                self.no_data_label.show()
            else:
                self.no_data_label.hide()
        
        # Mettre à jour le titre avec le nouveau compteur
        if hasattr(self, 'section') and hasattr(self.section, 'title_label'):
            new_title = f"👤 Références ({ref_count} référence{'s' if ref_count != 1 else ''})"
            self.section.title_label.setText(new_title)

    def _add_reference_widget_to_layout(self, reference):
        """Ajoute un widget de référence directement au layout."""
        if hasattr(self, 'content_layout'):
            widget = self.create_reference_widget(reference, reference)
            self.content_layout.addWidget(widget)
            self.ref_widgets.append(widget)
            
            # Mettre à jour l'affichage
            self._update_display()
    
    def add_new_reference(self):
        if not hasattr(self.profile, 'extracted_references') or not self.profile.extracted_references:
            self.profile.extracted_references = []
        new_ref = {
            'name': 'Nouvelle référence',
            'position': '',
            'company': '',
            'relation': '💼 Ancien manager',
            'email': '',
            'phone': '',
            'linkedin': '',
            'availability': '✅ Disponible',
            'years_known': '',
            'context': '',
            'notes': '',
            'source': 'Manuel'
        }
        self.profile.extracted_references.append(new_ref)
        
        # Déclencher la détection de modifications
        self.emit_data_updated(force_reload=True)
        self._add_reference_widget_to_layout(new_ref)
    
    def delete_reference(self, ref_obj, widget):
        if hasattr(self.profile, 'extracted_references') and self.profile.extracted_references:
            try:
                self.profile.extracted_references.remove(ref_obj)
                widget.deleteLater()
                if widget in self.ref_widgets:
                    self.ref_widgets.remove(widget)
                
                # Mettre à jour l'affichage dynamiquement
                self._update_display()
                
                # Sauvegarder les données sans rechargement complet
                self.emit_data_updated(force_reload=False, )
            except ValueError:
                pass
    
    def _update_field_legacy(self, obj, field, value):
        obj[field] = value
        # Ne pas déclencher de rechargement complet
