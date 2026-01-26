"""Section des certifications du profil."""
from typing import List, Dict, Any
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame, QLineEdit, QTextEdit, QDateEdit, QComboBox
from PySide6.QtCore import QDate
from .base_section import BaseSection
from ...models.user_profile import UserProfile
from ...widgets.collapsible_section import create_collapsible_section

class CertificationsSection(BaseSection):
    def __init__(self, profile: UserProfile, parent=None):
        super().__init__(profile, parent)
        self.cert_widgets = []
        
    def create_section_widget(self) -> QWidget:
        content_widget = QWidget()
        self.content_layout = QVBoxLayout(content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        
        add_btn = QPushButton("➕ Ajouter une certification")
        add_btn.setStyleSheet("QPushButton { background-color: #2d5f3f; color: white; border: none; padding: 12px 20px; border-radius: 8px; font-weight: bold; font-size: 14px; margin: 5px; } QPushButton:hover { background-color: #1e4f2f; }")
        add_btn.clicked.connect(self.add_new_certification)
        self.content_layout.addWidget(add_btn)
        
        data = self.get_section_data()
        # Toujours créer le label "aucune certification"
        self.no_data_label = QLabel("Aucune certification extraite. Utilisez le bouton ci-dessus pour en ajouter.")
        self.no_data_label.setStyleSheet("color: #a0a0a0; font-style: italic; padding: 20px; text-align: center;")
        self.content_layout.addWidget(self.no_data_label)
        
        for item in data:
            widget = self.create_certification_widget(item, item)
            self.content_layout.addWidget(widget)
            self.cert_widgets.append(widget)
        
        count = len(data)
        title = f"🏆 Certifications ({count} certification{'s' if count != 1 else ''})"
        self.section = create_collapsible_section(title, content_widget, "▼", True)
        
        # Mettre à jour l'affichage initial
        self._update_display()
        
        try:
            from ..text_cleaner import sanitize_widget_tree
            sanitize_widget_tree(content_widget)
        except Exception:
            pass
        return self.section
    
    def create_certification_widget(self, cert, cert_obj) -> QWidget:
        widget = QFrame()
        widget.setStyleSheet("QFrame { background-color: #3a3a3a; border: 1px solid #555555; border-radius: 12px; margin: 8px; padding: 15px; } QFrame:hover { border: 1px solid #4db8ff; background-color: #404040; }")
        layout = QVBoxLayout(widget)
        
        if not isinstance(cert, dict):
            cert = {}
        
        # Header avec nom et organisme
        header_layout = QHBoxLayout()
        name_edit = QLineEdit(str(cert.get('name', 'Certification')))
        name_edit.setPlaceholderText("Nom de la certification...")
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
        name_edit.textChanged.connect(lambda text: self._update_field(cert_obj, 'name', text))
        header_layout.addWidget(name_edit)
        
        # Label "par" sans encadré
        par_label = QLabel(" par ")
        par_label.setStyleSheet("font-size: 14px; color: #e0e0e0; font-style: italic;")
        header_layout.addWidget(par_label)
        
        # Organisme certificateur
        issuer_edit = QLineEdit(str(cert.get('issuer', 'Organisme')))
        issuer_edit.setPlaceholderText("Organisme certificateur...")
        issuer_edit.setStyleSheet("""
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
        issuer_edit.textChanged.connect(lambda text: self._update_field(cert_obj, 'issuer', text))
        header_layout.addWidget(issuer_edit)
        
        # Badge source
        source = cert.get('source', 'CV')
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
        delete_btn.clicked.connect(lambda: self.delete_certification(cert_obj, widget))
        header_layout.addWidget(delete_btn)
        layout.addLayout(header_layout)
        
        # Détails de la certification
        details_layout = QHBoxLayout()
        
        # Date d'obtention
        date_edit = QDateEdit()
        date_edit.setCalendarPopup(True)
        date_edit.setDisplayFormat("MM/yyyy")
        date_edit.setStyleSheet("""
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
        date_str = cert.get('date', '')
        if date_str:
            try:
                if '/' in date_str:
                    parts = date_str.split('/')
                    if len(parts) >= 2:
                        month, year = int(parts[0]), int(parts[1])
                        date_edit.setDate(QDate(year, month, 1))
                elif len(date_str) == 4 and date_str.isdigit():
                    date_edit.setDate(QDate(int(date_str), 1, 1))
            except (ValueError, IndexError):
                date_edit.setDate(QDate.currentDate())
        else:
            date_edit.setDate(QDate.currentDate())
        
        date_edit.dateChanged.connect(lambda date: self._update_field(cert_obj, 'date', date.toString("MM/yyyy")))
        
        # Statut de validité
        validity_combo = QComboBox()
        validity_combo.addItems([
            "✅ Valide",
            "⏳ Expire bientôt",
            "❌ Expirée",
            "🛠️ À renouveler",
            "♾️ Permanente"
        ])
        validity_combo.setStyleSheet("""
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
        
        # Définir le statut de validité actuel
        current_validity = str(cert.get('validity', ''))
        if current_validity:
            for i, item_text in enumerate([
                "✅ Valide",
                "⏳ Expire bientôt",
                "❌ Expirée",
                "🛠️ À renouveler",
                "♾️ Permanente"
            ]):
                if current_validity.lower() in item_text.lower() or any(word in item_text.lower() for word in current_validity.lower().split()):
                    validity_combo.setCurrentIndex(i)
                    break
        else:
            validity_combo.setCurrentIndex(0)  # Par défaut sur "Valide"
        
        validity_combo.currentTextChanged.connect(lambda text: self._update_field(cert_obj, 'validity', text))
        
        details_layout.addWidget(QLabel("📅"))
        details_layout.addWidget(date_edit)
        details_layout.addWidget(QLabel("📊"))
        details_layout.addWidget(validity_combo)
        
        # Numéro de certification
        cert_number_edit = QLineEdit(str(cert.get('cert_number', '')))
        cert_number_edit.setPlaceholderText("N° certification...")
        cert_number_edit.setStyleSheet("""
            QLineEdit {
                background-color: #3a3a3a;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 6px;
                color: #ffffff;
                min-width: 120px;
            }
            QLineEdit:focus {
                border: 2px solid #4db8ff;
                background-color: #404040;
            }
            QLineEdit:hover {
                border-color: #777777;
            }
        """)
        cert_number_edit.textChanged.connect(lambda text: self._update_field(cert_obj, 'cert_number', text))
        details_layout.addWidget(QLabel("🔢"))
        details_layout.addWidget(cert_number_edit)
        
        details_layout.addStretch()
        layout.addLayout(details_layout)
        
        # URL de vérification
        url_layout = QHBoxLayout()
        url_edit = QLineEdit(str(cert.get('verification_url', '')))
        url_edit.setPlaceholderText("URL de vérification de la certification...")
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
        url_edit.textChanged.connect(lambda text: self._update_field(cert_obj, 'verification_url', text))
        url_layout.addWidget(QLabel("🔗"))
        url_layout.addWidget(url_edit)
        layout.addLayout(url_layout)
        
        # Notes/Description
        desc_edit = QTextEdit()
        desc_edit.setPlainText(str(cert.get('description', '')))
        desc_edit.setPlaceholderText("Notes, compétences acquises, validité...")
        desc_edit.setMaximumHeight(60)
        desc_edit.setStyleSheet("""
            QTextEdit {
                background-color: #3a3a3a;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 6px;
                color: #ffffff;
                font-size: 12px;
            }
            QTextEdit:focus {
                border: 2px solid #4db8ff;
                background-color: #404040;
            }
            QTextEdit:hover {
                border-color: #777777;
            }
        """)
        desc_edit.textChanged.connect(lambda: self._update_field(cert_obj, 'description', desc_edit.toPlainText()))
        layout.addWidget(desc_edit)
        
        return widget
    
    def get_section_data(self) -> List[Dict[str, Any]]:
        return getattr(self.profile, 'extracted_certifications', []) or []
    
    def add_new_certification(self):
        if not hasattr(self.profile, 'extracted_certifications') or not self.profile.extracted_certifications:
            self.profile.extracted_certifications = []
        new_cert = {
            'name': 'Nouvelle certification', 
            'issuer': 'Organisme', 
            'date': '', 
            'validity': 'Valide',
            'cert_number': '',
            'verification_url': '',
            'description': '',
            'source': 'Manuel'
        }
        self.profile.extracted_certifications.append(new_cert)
        
        # Déclencher la détection de modifications
        self.emit_data_updated(force_reload=True)
        self._add_cert_widget_to_layout(new_cert)
    
    def delete_certification(self, cert_obj, widget):
        if hasattr(self.profile, 'extracted_certifications') and self.profile.extracted_certifications:
            try:
                self.profile.extracted_certifications.remove(cert_obj)
                widget.deleteLater()
                if widget in self.cert_widgets:
                    self.cert_widgets.remove(widget)
                # Mettre à jour l'affichage dynamiquement
                self._update_display()
                
                # Sauvegarder les données sans rechargement complet
                self.emit_data_updated(force_reload=False, )
            except ValueError:
                pass
    
    def _update_display(self):
        """Met à jour l'affichage (message et titre) selon le nombre d'éléments."""
        certifications_data = getattr(self.profile, 'extracted_certifications', []) or []
        cert_count = len(certifications_data)
        
        # Gérer l'affichage du message "aucune certification"
        if hasattr(self, 'no_data_label'):
            if cert_count == 0:
                self.no_data_label.show()
            else:
                self.no_data_label.hide()
        
        # Mettre à jour le titre avec le nouveau compteur
        if hasattr(self, 'section') and hasattr(self.section, 'title_label'):
            new_title = f"🏆 Certifications ({cert_count} certification{'s' if cert_count != 1 else ''})"
            self.section.title_label.setText(new_title)

    def _add_cert_widget_to_layout(self, cert):
        """Ajoute un widget de certification directement au layout."""
        if hasattr(self, 'content_layout'):
            widget = self.create_certification_widget(cert, cert)
            self.content_layout.addWidget(widget)
            self.cert_widgets.append(widget)
            
            # Mettre à jour l'affichage
            self._update_display()

    def _update_field_legacy(self, obj, field, value):
        obj[field] = value
        # Ne pas déclencher de rechargement complet
