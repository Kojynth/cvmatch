"""Section des centres d'intérêt du profil."""
from typing import List, Dict, Any
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame, QLineEdit, QTextEdit, QComboBox
from .base_section import BaseSection
from ...widgets.collapsible_section import create_collapsible_section

class InterestsSection(BaseSection):
    def __init__(self, profile, parent=None):
        super().__init__(profile, parent)
        self.interest_widgets = []
        
    def create_section_widget(self) -> QWidget:
        content_widget = QWidget()
        self.content_layout = QVBoxLayout(content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        
        add_btn = QPushButton("➕ Ajouter un centre d'intérêt")
        add_btn.setStyleSheet("QPushButton { background-color: #2d5f3f; color: white; border: none; padding: 12px 20px; border-radius: 8px; font-weight: bold; font-size: 14px; margin: 5px; } QPushButton:hover { background-color: #1e4f2f; }")
        add_btn.clicked.connect(self.add_new_interest)
        self.content_layout.addWidget(add_btn)
        
        data = self.get_section_data()
        if data:
            for item in data:
                widget = self.create_interest_widget(item, item)
                self.content_layout.addWidget(widget)
                self.interest_widgets.append(widget)
        else:
            self.no_data_label = QLabel("Aucun centre d'intérêt extrait. Utilisez le bouton ci-dessus pour en ajouter.")
            self.no_data_label.setStyleSheet("color: #a0a0a0; font-style: italic; padding: 20px; text-align: center;")
            self.content_layout.addWidget(self.no_data_label)
        
        count = len(data)
        title = f"🎯 Centres d'intérêt ({count} intérêt{'s' if count != 1 else ''})"
        self.section = create_collapsible_section(title, content_widget, "▼", True)
        
        # Mettre à jour l'affichage initial
        self._update_display()
        
        try:
            from ..text_cleaner import sanitize_widget_tree
            sanitize_widget_tree(content_widget)
        except Exception:
            pass
        return self.section
    
    def create_interest_widget(self, interest, interest_obj) -> QWidget:
        widget = QFrame()
        widget.setStyleSheet("QFrame { background-color: #3a3a3a; border: 1px solid #555555; border-radius: 12px; margin: 8px; padding: 15px; } QFrame:hover { border: 1px solid #4db8ff; background-color: #404040; }")
        layout = QVBoxLayout(widget)
        
        if not isinstance(interest, dict):
            interest = {}
        
        # En-tête avec nom et bouton supprimer
        header_layout = QHBoxLayout()
        name_edit = QLineEdit(str(interest.get('name', 'Nouveau centre d\'intérêt')))
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
        name_edit.textChanged.connect(lambda text: self._update_field(interest_obj, 'name', text))
        header_layout.addWidget(name_edit)
        
        # Badge source
        source = interest.get('source', 'CV')
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
        delete_btn.clicked.connect(lambda: self.delete_interest(interest_obj, widget))
        header_layout.addWidget(delete_btn)
        layout.addLayout(header_layout)
        
        # Ligne Catégorie et Niveau d'engagement
        category_engagement_layout = QHBoxLayout()
        
        # Catégorie
        category_label = QLabel("🏷️ Catégorie :")
        category_label.setStyleSheet("color: white; font-weight: bold; min-width: 80px;")
        category_combo = QComboBox()
        category_combo.addItems([
            "🎯 Loisirs",
            "⚽ Sport",
            "🎨 Art & Culture",
            "📚 Lecture & Écriture",
            "🎵 Musique",
            "💻 Technologie",
            "🌍 Voyage",
            "🌱 Nature & Environnement",
            "🍳 Gastronomie",
            "🤝 Social & Bénévolat",
            "🎮 Gaming",
            "💰 Finance & Investissement",
            "📝 Autre"
        ])
        current_category = interest.get('category', '🎯 Loisirs')
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
        category_combo.currentTextChanged.connect(lambda text: self._update_field(interest_obj, 'category', text))
        
        # Niveau d'engagement
        engagement_label = QLabel("💪 Engagement :")
        engagement_label.setStyleSheet("color: white; font-weight: bold; min-width: 90px;")
        engagement_combo = QComboBox()
        engagement_combo.addItems([
            "🔥 Passionné",
            "❤️‍🩹 Amateur éclairé",
            "👍 Intéressé",
            "🔍 Curieux",
            "🌱 Débutant"
        ])
        current_engagement = interest.get('engagement', '🔥 Passionné')
        engagement_index = engagement_combo.findText(current_engagement)
        if engagement_index >= 0:
            engagement_combo.setCurrentIndex(engagement_index)
        engagement_combo.setStyleSheet("""
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
        engagement_combo.currentTextChanged.connect(lambda text: self._update_field(interest_obj, 'engagement', text))
        
        category_engagement_layout.addWidget(category_label)
        category_engagement_layout.addWidget(category_combo, 1)
        category_engagement_layout.addWidget(engagement_label)
        category_engagement_layout.addWidget(engagement_combo, 1)
        
        layout.addLayout(category_engagement_layout)
        
        # Ligne Fréquence
        frequency_layout = QHBoxLayout()
        frequency_label = QLabel("📅 Fréquence :")
        frequency_label.setStyleSheet("color: white; font-weight: bold; min-width: 90px;")
        frequency_combo = QComboBox()
        frequency_combo.addItems([
            "🗓️ Régulier",
            "🔥 Quotidien",
            "📅 Hebdomadaire",
            "🏖️ Weekend",
            "🌙 Soirées",
            "🍀 Occasionnel",
            "🎪 Événementiel",
            "🏝️ Vacances"
        ])
        current_frequency = interest.get('frequency', '🗓️ Régulier')
        frequency_index = frequency_combo.findText(current_frequency)
        if frequency_index >= 0:
            frequency_combo.setCurrentIndex(frequency_index)
        frequency_combo.setStyleSheet("""
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
        frequency_combo.currentTextChanged.connect(lambda text: self._update_field(interest_obj, 'frequency', text))
        
        frequency_layout.addWidget(frequency_label)
        frequency_layout.addWidget(frequency_combo)
        frequency_layout.addStretch()
        
        layout.addLayout(frequency_layout)
        
        # Description/Détails
        desc_label = QLabel("📝 Description/Détails :")
        desc_label.setStyleSheet("color: white; font-weight: bold; margin-top: 10px;")
        layout.addWidget(desc_label)
        
        desc_edit = QTextEdit(str(interest.get('description', '')))
        desc_edit.setMaximumHeight(70)
        desc_edit.setPlaceholderText("Ex: Pratique du tennis en club, randonnées en montagne, lecture de science-fiction...")
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
        desc_edit.textChanged.connect(lambda: self._update_field(interest_obj, 'description', desc_edit.toPlainText()))
        layout.addWidget(desc_edit)
        
        return widget
    
    def get_section_data(self) -> List[Dict[str, Any]]:
        return getattr(self.profile, 'extracted_interests', []) or []
    
    def add_new_interest(self):
        if not hasattr(self.profile, 'extracted_interests') or not self.profile.extracted_interests:
            self.profile.extracted_interests = []
        new_interest = {
            'name': 'Nouveau centre d\'intérêt',
            'category': '🎯 Loisirs',
            'engagement': '🔥 Passionné',
            'frequency': '🗓️ Régulier',
            'description': '',
            'source': 'Manuel'
        }
        self.profile.extracted_interests.append(new_interest)
        
        # Déclencher la détection de modifications
        self.emit_data_updated(force_reload=True)
        self._add_interest_widget_to_layout(new_interest)
    
    def delete_interest(self, interest_obj, widget):
        if hasattr(self.profile, 'extracted_interests') and self.profile.extracted_interests:
            try:
                self.profile.extracted_interests.remove(interest_obj)
                widget.deleteLater()
                if widget in self.interest_widgets:
                    self.interest_widgets.remove(widget)
                # Mettre à jour l'affichage dynamiquement
                self._update_display()
                
                # Sauvegarder les données sans rechargement complet
                self.emit_data_updated(force_reload=False, )
            except ValueError:
                pass
    
    def _update_display(self):
        """Met à jour l'affichage (message et titre) selon le nombre d'éléments."""
        interests_data = getattr(self.profile, 'extracted_interests', []) or []
        interest_count = len(interests_data)
        
        # Gérer l'affichage du message "aucun intérêt"
        if hasattr(self, 'no_data_label'):
            if interest_count == 0:
                self.no_data_label.show()
            else:
                self.no_data_label.hide()
        
        # Mettre à jour le titre avec le nouveau compteur
        if hasattr(self, 'section') and hasattr(self.section, 'title_label'):
            new_title = f"🎯 Centres d'intérêt ({interest_count} intérêt{'s' if interest_count != 1 else ''})"
            self.section.title_label.setText(new_title)

    def _add_interest_widget_to_layout(self, interest):
        """Ajoute un widget d'intérêt directement au layout."""
        if hasattr(self, 'content_layout'):
            widget = self.create_interest_widget(interest, interest)
            self.content_layout.addWidget(widget)
            self.interest_widgets.append(widget)
            
            # Mettre à jour l'affichage
            self._update_display()

    def _update_field_legacy(self, obj, field, value):
        obj[field] = value
        # Ne pas déclencher de rechargement complet
