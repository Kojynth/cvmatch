"""Section des récompenses du profil."""
from typing import List, Dict, Any
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame, QLineEdit, QTextEdit, QDateEdit, QComboBox
from PySide6.QtCore import QDate
from .base_section import BaseSection
from ...widgets.collapsible_section import create_collapsible_section

class AwardsSection(BaseSection):
    def __init__(self, profile, parent=None):
        super().__init__(profile, parent)
        self.award_widgets = []
        
    def create_section_widget(self) -> QWidget:
        content_widget = QWidget()
        self.content_layout = QVBoxLayout(content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        
        add_btn = QPushButton("➕ Ajouter une récompense")
        add_btn.setStyleSheet("QPushButton { background-color: #2d5f3f; color: white; border: none; padding: 12px 20px; border-radius: 8px; font-weight: bold; font-size: 14px; margin: 5px; } QPushButton:hover { background-color: #1e4f2f; }")
        add_btn.clicked.connect(self.add_new_award)
        self.content_layout.addWidget(add_btn)
        
        # Toujours créer le label "aucune récompense"
        self.no_data_label = QLabel("Aucune récompense extraite. Utilisez le bouton ci-dessus pour en ajouter.")
        self.no_data_label.setStyleSheet("color: #a0a0a0; font-style: italic; padding: 20px; text-align: center;")
        self.content_layout.addWidget(self.no_data_label)
        
        data = self.get_section_data()
        for item in data:
            widget = self.create_award_widget(item, item)
            self.content_layout.addWidget(widget)
            self.award_widgets.append(widget)
        
        count = len(data)
        title = f"🏅 Récompenses ({count} récompense{'s' if count != 1 else ''})"
        self.section = create_collapsible_section(title, content_widget, "▼", True)
        
        # Mettre à jour l'affichage initial
        self._update_display()
        
        try:
            from ..text_cleaner import sanitize_widget_tree
            sanitize_widget_tree(content_widget)
        except Exception:
            pass
        return self.section
    
    def create_award_widget(self, award, award_obj) -> QWidget:
        widget = QFrame()
        widget.setStyleSheet("QFrame { background-color: #3a3a3a; border: 1px solid #555555; border-radius: 12px; margin: 8px; padding: 15px; } QFrame:hover { border: 1px solid #4db8ff; background-color: #404040; }")
        layout = QVBoxLayout(widget)
        
        if not isinstance(award, dict):
            award = {}
        
        # En-tête avec nom et bouton supprimer
        header_layout = QHBoxLayout()
        name_edit = QLineEdit(str(award.get('name', 'Nouvelle récompense')))
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
        name_edit.textChanged.connect(lambda text: self._update_field(award_obj, 'name', text))
        header_layout.addWidget(name_edit)
        
        # Badge source
        source = award.get('source', 'CV')
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
        delete_btn.clicked.connect(lambda: self.delete_award(award_obj, widget))
        header_layout.addWidget(delete_btn)
        layout.addLayout(header_layout)
        
        # Ligne Catégorie et Niveau
        category_level_layout = QHBoxLayout()
        
        # Catégorie de récompense
        category_label = QLabel("🏷️ Catégorie :")
        category_label.setStyleSheet("color: white; font-weight: bold; min-width: 80px;")
        category_combo = QComboBox()
        category_combo.addItems([
            "🏆 Prix professionnel",
            "🎓 Prix académique",
            "📊 Performance",
            "🎖️ Innovation",
            "🤝 Leadership",
            "🎯 Excellence",
            "🔥 Startup/Entrepreneur",
            "🌍 Impact social",
            "📚 Publication",
            "🎨 Créativité",
            "🗺️ Autre"
        ])
        current_category = award.get('category', '🏆 Prix professionnel')
        category_index = category_combo.findText(current_category)
        if category_index >= 0:
            category_combo.setCurrentIndex(category_index)
        category_combo.setStyleSheet("""
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
        category_combo.currentTextChanged.connect(lambda text: self._update_field(award_obj, 'category', text))
        
        # Niveau
        level_label = QLabel("🌍 Niveau :")
        level_label.setStyleSheet("color: white; font-weight: bold; min-width: 70px;")
        level_combo = QComboBox()
        level_combo.addItems([
            "🏢 Interne entreprise",
            "🏙️ Local/Régional",
            "🥇 National",
            "🌍 International",
            "🔥 Mondial"
        ])
        current_level = award.get('level', '🥇 National')
        level_index = level_combo.findText(current_level)
        if level_index >= 0:
            level_combo.setCurrentIndex(level_index)
        level_combo.setStyleSheet("""
            QComboBox {
                background-color: #3a3a3a;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 8px;
                color: white;
                min-width: 140px;
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
        level_combo.currentTextChanged.connect(lambda text: self._update_field(award_obj, 'level', text))
        
        category_level_layout.addWidget(category_label)
        category_level_layout.addWidget(category_combo, 1)
        category_level_layout.addWidget(level_label)
        category_level_layout.addWidget(level_combo, 1)
        
        layout.addLayout(category_level_layout)
        
        # Ligne Organisme et Date
        issuer_date_layout = QHBoxLayout()
        
        # Organisme décerneur
        issuer_label = QLabel("🏢 Organisme :")
        issuer_label.setStyleSheet("color: white; font-weight: bold; min-width: 90px;")
        issuer_edit = QLineEdit(str(award.get('issuer', '')))
        issuer_edit.setPlaceholderText("Organisation, entreprise, institution...")
        issuer_edit.setStyleSheet("""
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
        issuer_edit.textChanged.connect(lambda text: self._update_field(award_obj, 'issuer', text))
        
        # Date
        date_label = QLabel("📅 Date :")
        date_label.setStyleSheet("color: white; font-weight: bold; min-width: 60px;")
        date_edit = QDateEdit()
        date_edit.setDisplayFormat("MM/yyyy")
        date_edit.setCalendarPopup(True)
        
        # Déterminer la date à afficher
        date_str = award.get('date', '')
        if date_str:
            try:
                if '/' in date_str and len(date_str.split('/')) == 2:
                    month, year = date_str.split('/')
                    date_edit.setDate(QDate(int(year), int(month), 1))
                elif len(date_str) == 4:  # Année seulement
                    date_edit.setDate(QDate(int(date_str), 12, 31))
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
        date_edit.dateChanged.connect(lambda date: self._update_field(award_obj, 'date', date.toString("MM/yyyy")))
        
        issuer_date_layout.addWidget(issuer_label)
        issuer_date_layout.addWidget(issuer_edit, 2)
        issuer_date_layout.addWidget(date_label)
        issuer_date_layout.addWidget(date_edit, 1)
        
        layout.addLayout(issuer_date_layout)
        
        # Ligne Classement et URL
        ranking_url_layout = QHBoxLayout()
        
        # Classement/Position
        ranking_label = QLabel("🏅 Classement :")
        ranking_label.setStyleSheet("color: white; font-weight: bold; min-width: 90px;")
        ranking_edit = QLineEdit(str(award.get('ranking', '')))
        ranking_edit.setPlaceholderText("1er, 2ème, Top 10, Finaliste...")
        ranking_edit.setStyleSheet("""
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
        ranking_edit.textChanged.connect(lambda text: self._update_field(award_obj, 'ranking', text))
        
        # URL de vérification
        url_label = QLabel("🔗 URL :")
        url_label.setStyleSheet("color: white; font-weight: bold; min-width: 50px;")
        url_edit = QLineEdit(str(award.get('url', '')))
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
        url_edit.textChanged.connect(lambda text: self._update_field(award_obj, 'url', text))
        
        ranking_url_layout.addWidget(ranking_label)
        ranking_url_layout.addWidget(ranking_edit, 1)
        ranking_url_layout.addWidget(url_label)
        ranking_url_layout.addWidget(url_edit, 2)
        
        layout.addLayout(ranking_url_layout)
        
        # Description/Contexte
        desc_label = QLabel("📝 Description/Contexte :")
        desc_label.setStyleSheet("color: white; font-weight: bold; margin-top: 10px;")
        layout.addWidget(desc_label)
        
        desc_edit = QTextEdit(str(award.get('description', '')))
        desc_edit.setMaximumHeight(80)
        desc_edit.setPlaceholderText("Contexte, critères, nombre de participants, signification...")
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
        desc_edit.textChanged.connect(lambda: self._update_field(award_obj, 'description', desc_edit.toPlainText()))
        layout.addWidget(desc_edit)
        
        return widget
    
    def get_section_data(self) -> List[Dict[str, Any]]:
        return getattr(self.profile, 'extracted_awards', []) or []
    
    def _update_display(self):
        """Met à jour l'affichage (message et titre) selon le nombre d'éléments."""
        awards_data = getattr(self.profile, 'extracted_awards', []) or []
        award_count = len(awards_data)
        
        # Gérer l'affichage du message "aucune récompense"
        if hasattr(self, 'no_data_label'):
            if award_count == 0:
                self.no_data_label.show()
            else:
                self.no_data_label.hide()
        
        # Mettre à jour le titre avec le nouveau compteur
        if hasattr(self, 'section') and hasattr(self.section, 'title_label'):
            new_title = f"🏅 Récompenses ({award_count} récompense{'s' if award_count != 1 else ''})"
            self.section.title_label.setText(new_title)

    def _add_award_widget_to_layout(self, award):
        """Ajoute un widget de récompense directement au layout."""
        if hasattr(self, 'content_layout'):
            widget = self.create_award_widget(award, award)
            self.content_layout.addWidget(widget)
            self.award_widgets.append(widget)
            
            # Mettre à jour l'affichage
            self._update_display()

    def add_new_award(self):
        if not hasattr(self.profile, 'extracted_awards') or not self.profile.extracted_awards:
            self.profile.extracted_awards = []
        new_award = {
            'name': 'Nouvelle récompense',
            'category': '🏆 Prix professionnel',
            'issuer': '',
            'date': '',
            'level': '🥇 National',
            'ranking': '',
            'url': '',
            'description': '',
            'source': 'Manuel'
        }
        self.profile.extracted_awards.append(new_award)
        
        # Déclencher la détection de modifications
        self.emit_data_updated(force_reload=True)
        self._add_award_widget_to_layout(new_award)
    
    def delete_award(self, award_obj, widget):
        if hasattr(self.profile, 'extracted_awards') and self.profile.extracted_awards:
            try:
                self.profile.extracted_awards.remove(award_obj)
                widget.deleteLater()
                if widget in self.award_widgets:
                    self.award_widgets.remove(widget)
                
                # Mettre à jour l'affichage dynamiquement
                self._update_display()
                
                # Sauvegarder les données sans rechargement complet
                self.emit_data_updated(force_reload=False, )
            except ValueError:
                pass
    
    def _update_field_legacy(self, obj, field, value):
        obj[field] = value
        # Ne pas déclencher de rechargement complet
