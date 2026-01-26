"""Section des publications du profil."""
from typing import List, Dict, Any
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame, QLineEdit, QTextEdit, QDateEdit, QComboBox
from PySide6.QtCore import QDate
from .base_section import BaseSection
from ...widgets.collapsible_section import create_collapsible_section

class PublicationsSection(BaseSection):
    def __init__(self, profile, parent=None):
        super().__init__(profile, parent)
        self.pub_widgets = []
        
    def create_section_widget(self) -> QWidget:
        content_widget = QWidget()
        self.content_layout = QVBoxLayout(content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        
        add_btn = QPushButton("➕ Ajouter une publication")
        add_btn.setStyleSheet("QPushButton { background-color: #2d5f3f; color: white; border: none; padding: 12px 20px; border-radius: 8px; font-weight: bold; font-size: 14px; margin: 5px; } QPushButton:hover { background-color: #1e4f2f; }")
        add_btn.clicked.connect(self.add_new_publication)
        self.content_layout.addWidget(add_btn)
        
        # Toujours créer le label "aucune publication"
        self.no_data_label = QLabel("Aucune publication extraite. Utilisez le bouton ci-dessus pour en ajouter.")
        self.no_data_label.setStyleSheet("color: #a0a0a0; font-style: italic; padding: 20px; text-align: center;")
        self.content_layout.addWidget(self.no_data_label)
        
        data = self.get_section_data()
        for item in data:
            widget = self.create_publication_widget(item, item)
            self.content_layout.addWidget(widget)
            self.pub_widgets.append(widget)
        
        count = len(data)
        title = f"📚 Publications ({count} publication{'s' if count != 1 else ''})"
        self.section = create_collapsible_section(title, content_widget, "▼", True)
        
        # Mettre à jour l'affichage initial
        self._update_display()
        
        try:
            from ..text_cleaner import sanitize_widget_tree
            sanitize_widget_tree(content_widget)
        except Exception:
            pass
        return self.section
    
    def create_publication_widget(self, pub, pub_obj) -> QWidget:
        widget = QFrame()
        widget.setStyleSheet("QFrame { background-color: #3a3a3a; border: 1px solid #555555; border-radius: 12px; margin: 8px; padding: 15px; } QFrame:hover { border: 1px solid #4db8ff; background-color: #404040; }")
        layout = QVBoxLayout(widget)
        
        if not isinstance(pub, dict):
            pub = {}
        
        # En-tête avec titre et bouton supprimer
        header_layout = QHBoxLayout()
        title_edit = QLineEdit(str(pub.get('title', 'Nouvelle publication')))
        title_edit.setStyleSheet("""
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
        title_edit.textChanged.connect(lambda text: self._update_field(pub_obj, 'title', text))
        header_layout.addWidget(title_edit)
        
        # Badge source
        source = pub.get('source', 'CV')
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
        delete_btn.clicked.connect(lambda: self.delete_publication(pub_obj, widget))
        header_layout.addWidget(delete_btn)
        layout.addLayout(header_layout)
        
        # Ligne Type et Statut
        type_status_layout = QHBoxLayout()
        
        # Type de publication
        type_label = QLabel("📰 Type :")
        type_label.setStyleSheet("color: white; font-weight: bold; min-width: 80px;")
        type_combo = QComboBox()
        type_combo.addItems([
            "📰 Article",
            "📚 Livre",
            "📖 Chapitre",
            "🎓 Thèse",
            "📊 Rapport",
            "📝 Blog",
            "📰 Journal",
            "🎤 Conférence",
            "📄 Autre"
        ])
        current_type = pub.get('type', '📰 Article')
        type_index = type_combo.findText(current_type)
        if type_index >= 0:
            type_combo.setCurrentIndex(type_index)
        type_combo.setStyleSheet("""
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
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid white;
                margin: 0px;
            }
            QComboBox QAbstractItemView {
                background-color: #2a2a2a;
                border: 1px solid #555555;
                selection-background-color: #4db8ff;
                color: white;
            }
        """)
        type_combo.currentTextChanged.connect(lambda text: self._update_field(pub_obj, 'type', text))
        
        type_status_layout.addWidget(type_label)
        type_status_layout.addWidget(type_combo)
        type_status_layout.addStretch()
        
        # Statut
        status_label = QLabel("📊 Statut :")
        status_label.setStyleSheet("color: white; font-weight: bold; min-width: 80px;")
        status_combo = QComboBox()
        status_combo.addItems([
            "✅ Publié",
            "📝 En rédaction",
            "👀 En révision",
            "⏳ Soumis",
            "🛠️ En cours",
            "📅 Planifié",
            "❌ Rejeté"
        ])
        current_status = pub.get('status', '✅ Publié')
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
                min-width: 130px;
            }
            QComboBox:focus {
                border: 2px solid #4db8ff;
                background-color: #404040;
            }
            QComboBox:hover {
                border-color: #777777;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid white;
                margin: 0px;
            }
            QComboBox QAbstractItemView {
                background-color: #2a2a2a;
                border: 1px solid #555555;
                selection-background-color: #4db8ff;
                color: white;
            }
        """)
        status_combo.currentTextChanged.connect(lambda text: self._update_field(pub_obj, 'status', text))
        
        type_status_layout.addWidget(status_label)
        type_status_layout.addWidget(status_combo)
        
        layout.addLayout(type_status_layout)
        
        # Ligne Journal/Éditeur et Date
        journal_date_layout = QHBoxLayout()
        
        # Journal/Éditeur
        journal_label = QLabel("🏢 Journal/Éditeur :")
        journal_label.setStyleSheet("color: white; font-weight: bold; min-width: 120px;")
        journal_edit = QLineEdit(str(pub.get('journal', '')))
        journal_edit.setStyleSheet("""
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
        journal_edit.textChanged.connect(lambda text: self._update_field(pub_obj, 'journal', text))
        
        # Date
        date_label = QLabel("📅 Date :")
        date_label.setStyleSheet("color: white; font-weight: bold; min-width: 60px;")
        date_edit = QDateEdit()
        date_edit.setDisplayFormat("MM/yyyy")
        date_edit.setCalendarPopup(True)
        
        # Déterminer la date à afficher
        date_str = pub.get('date', '')
        if date_str:
            try:
                if '/' in date_str and len(date_str.split('/')) == 2:
                    month, year = date_str.split('/')
                    date_edit.setDate(QDate(int(year), int(month), 1))
                elif len(date_str) == 4:  # Année seulement
                    date_edit.setDate(QDate(int(date_str), 1, 1))
                else:
                    date_edit.setDate(QDate.currentDate())
            except (ValueError, IndexError):
                date_edit.setDate(QDate.currentDate())
        else:
            date_edit.setDate(QDate.currentDate())
        
        date_edit.setStyleSheet("""
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
        date_edit.dateChanged.connect(lambda date: self._update_field(pub_obj, 'date', date.toString("MM/yyyy")))
        
        journal_date_layout.addWidget(journal_label)
        journal_date_layout.addWidget(journal_edit, 2)
        journal_date_layout.addWidget(date_label)
        journal_date_layout.addWidget(date_edit, 1)
        
        layout.addLayout(journal_date_layout)
        
        # Ligne Co-auteurs
        authors_layout = QHBoxLayout()
        authors_label = QLabel("👤 Co-auteurs :")
        authors_label.setStyleSheet("color: white; font-weight: bold; min-width: 100px;")
        authors_edit = QLineEdit(str(pub.get('authors', '')))
        authors_edit.setPlaceholderText("Séparés par des virgules")
        authors_edit.setStyleSheet("""
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
        authors_edit.textChanged.connect(lambda text: self._update_field(pub_obj, 'authors', text))
        
        authors_layout.addWidget(authors_label)
        authors_layout.addWidget(authors_edit)
        
        layout.addLayout(authors_layout)
        
        # Ligne URL
        url_layout = QHBoxLayout()
        url_label = QLabel("🔗 URL :")
        url_label.setStyleSheet("color: white; font-weight: bold; min-width: 60px;")
        url_edit = QLineEdit(str(pub.get('url', '')))
        url_edit.setPlaceholderText("https://...")
        url_edit.setStyleSheet("""
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
        url_edit.textChanged.connect(lambda text: self._update_field(pub_obj, 'url', text))
        
        url_layout.addWidget(url_label)
        url_layout.addWidget(url_edit)
        
        layout.addLayout(url_layout)
        
        # Description/Résumé
        desc_label = QLabel("📝 Description/Résumé :")
        desc_label.setStyleSheet("color: white; font-weight: bold; margin-top: 10px;")
        layout.addWidget(desc_label)
        
        desc_edit = QTextEdit(str(pub.get('description', '')))
        desc_edit.setMaximumHeight(80)
        desc_edit.setStyleSheet("""
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
        desc_edit.textChanged.connect(lambda: self._update_field(pub_obj, 'description', desc_edit.toPlainText()))
        layout.addWidget(desc_edit)
        
        return widget
    
    def get_section_data(self) -> List[Dict[str, Any]]:
        return getattr(self.profile, 'extracted_publications', []) or []
    
    def _update_display(self):
        """Met à jour l'affichage (message et titre) selon le nombre d'éléments."""
        publications_data = getattr(self.profile, 'extracted_publications', []) or []
        pub_count = len(publications_data)
        
        # Gérer l'affichage du message "aucune publication"
        if hasattr(self, 'no_data_label'):
            if pub_count == 0:
                self.no_data_label.show()
            else:
                self.no_data_label.hide()
        
        # Mettre à jour le titre avec le nouveau compteur
        if hasattr(self, 'section') and hasattr(self.section, 'title_label'):
            new_title = f"📚 Publications ({pub_count} publication{'s' if pub_count != 1 else ''})"
            self.section.title_label.setText(new_title)

    def _add_publication_widget_to_layout(self, publication):
        """Ajoute un widget de publication directement au layout."""
        if hasattr(self, 'content_layout'):
            widget = self.create_publication_widget(publication, publication)
            self.content_layout.addWidget(widget)
            self.pub_widgets.append(widget)
            
            # Mettre à jour l'affichage
            self._update_display()

    def add_new_publication(self):
        if not hasattr(self.profile, 'extracted_publications') or not self.profile.extracted_publications:
            self.profile.extracted_publications = []
        new_pub = {
            'title': 'Nouvelle publication',
            'type': '📰 Article',
            'journal': '',
            'date': '',
            'authors': '',
            'url': '',
            'status': '✅ Publié',
            'description': '',
            'source': 'Manuel'
        }
        self.profile.extracted_publications.append(new_pub)
        
        # Déclencher la détection de modifications
        self.emit_data_updated(force_reload=True)
        self._add_publication_widget_to_layout(new_pub)
    
    def delete_publication(self, pub_obj, widget):
        if hasattr(self.profile, 'extracted_publications') and self.profile.extracted_publications:
            try:
                self.profile.extracted_publications.remove(pub_obj)
                widget.deleteLater()
                if widget in self.pub_widgets:
                    self.pub_widgets.remove(widget)
                
                # Mettre à jour l'affichage dynamiquement
                self._update_display()
                
                # Sauvegarder les données sans rechargement complet
                self.emit_data_updated(force_reload=False)
            except ValueError:
                pass
    
    def _update_field_legacy(self, obj, field, value):
        obj[field] = value
        # Ne pas déclencher de rechargement complet
