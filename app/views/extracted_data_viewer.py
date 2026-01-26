"""
Extracted Data Viewer - Interface complète pour visualiser les données extraites
===============================================================================

Interface avancée pour afficher, éditer et valider toutes les données
extraites du CV et de LinkedIn avec une présentation structurée.

VERSION REFACTORISÉE - Utilise maintenant des sections modulaires.
"""

import json
from typing import Dict, List, Any, Optional
from datetime import datetime
from loguru import logger

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget, 
    QScrollArea, QLabel, QTextEdit, QTreeWidget, QTreeWidgetItem,
    QPushButton, QGroupBox, QFormLayout, QLineEdit, QSpinBox,
    QComboBox, QProgressBar, QSplitter, QFrame, QCheckBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QStyle,
    QFileDialog, QListWidget, QListWidgetItem
)
from PySide6.QtCore import Qt, Signal, QTimer, QUrl
from PySide6.QtGui import QFont, QPixmap, QIcon, QCursor
from .text_cleaner import sanitize_widget_tree
from app.utils.emoji_utils import get_display_text
import re
import os

from ..models.user_profile import UserProfile
from ..controllers.profile_extractor import ProfileExtractionController
from ..widgets.phone_widget import PhoneNumberWidget, create_phone_widget
from ..widgets.style_manager import apply_button_style
from ..widgets.collapsible_section import CollapsibleSection, create_collapsible_section
from ..utils.confidence_filter import filter_high_confidence, has_confidence_scores

# Import des sections modulaires
from .profile_sections import (
    PersonalInfoSection, ExperienceSection, EducationSection, 
    SkillsSection, SoftSkillsSection, ProjectsSection, LanguagesSection,
    CertificationsSection, PublicationsSection, VolunteeringSection,
    AwardsSection, ReferencesSection, InterestsSection
)


class ExtractedDataViewer(QDialog):
    """Visualisateur complet des données extraites - Version modulaire."""
    
    data_updated = Signal(UserProfile)
    
    def __init__(self, profile: UserProfile, parent=None):
        super().__init__(parent)
        self.profile = profile
        self.setWindowTitle(f"Profil détaillé - {profile.name}")
        self.setModal(True)
        self.resize(1200, 800)
        
        # Dictionnaire pour stocker les références aux sections
        self.sections = {}
        self.dynamic_sections = {}
        
        # Contrôleur d'extraction
        self.extraction_controller = None
        
        # Système de cache pour les modifications non sauvegardées
        self.original_data_cache = self._create_profile_cache()
        self.has_unsaved_changes = False
        self._is_restoring = False  # Flag pour éviter les signaux pendant la restauration

        # Système de debouncing pour les rechargemens
        from PySide6.QtCore import QTimer
        self._reload_timer = QTimer()
        self._reload_timer.setSingleShot(True)
        self._reload_timer.timeout.connect(self._delayed_reload)
        self._pending_reload = False
        self._last_reload_time = 0

        # Monitoring des performances
        self._reload_count = 0
        self._reload_durations = []
        
        self.setup_ui()
        self.load_profile_data()
    
    def setup_ui(self):
        """Configure l'interface utilisateur."""
        self.setStyleSheet(self._get_main_stylesheet())
        
        # Layout principal
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        # Header compact
        header = self.create_compact_header()
        main_layout.addWidget(header)
        
        # Contenu principal avec onglets
        content_area = self.create_main_content()
        main_layout.addWidget(content_area)
        
        # Footer avec boutons d'action
        footer = self.create_compact_footer()
        main_layout.addWidget(footer)
        # Sanitize label/button texts to avoid mojibake artifacts on Windows consoles
        sanitize_widget_tree(self)

    def _safe_delete_widget(self, widget):
        """Safely delete a widget with pending signals.

        SAFE: Prevents "Internal C++ object already deleted" errors by:
        1. Blocking signals before deletion
        2. Scheduling deletion with deleteLater()
        3. Processing pending events to complete deletion
        """
        if widget:
            try:
                widget.blockSignals(True)  # Block all signals
                widget.setParent(None)
                widget.deleteLater()
                # Process events to complete deletion immediately
                from PySide6.QtWidgets import QApplication
                QApplication.processEvents()
            except:
                pass  # Widget already deleted or invalid

    def _get_main_stylesheet(self) -> str:
        """Retourne le stylesheet principal de l'application."""
        return """
            QDialog {
                background-color: #1e1e1e;
                color: #e0e0e0;
            }
            QWidget {
                background-color: #1e1e1e;
                color: #e0e0e0;
            }
            QGroupBox {
                background-color: #2a2a2a;
                border: 1px solid #404040;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
                font-weight: bold;
                color: #ffffff;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 10px 0 10px;
                color: #4db8ff;
                font-size: 14px;
            }
            QLineEdit {
                background-color: #3a3a3a;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 12px;
                color: #ffffff;
                font-size: 14px;
                min-height: 20px;
            }
            QLineEdit:focus {
                border: 2px solid #4db8ff;
                background-color: #404040;
            }
            QTextEdit {
                background-color: #3a3a3a;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 12px;
                color: #ffffff;
                font-size: 14px;
                min-height: 80px;
            }
            QTextEdit:focus {
                border: 2px solid #4db8ff;
                background-color: #404040;
            }
            QTabWidget::pane {
                border: 1px solid #404040;
                background-color: #2a2a2a;
            }
            QTabBar::tab {
                background-color: #3a3a3a;
                color: #e0e0e0;
                padding: 8px 16px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background-color: #4db8ff;
                color: #ffffff;
            }
            QTabBar::tab:hover {
                background-color: #505050;
            }
        """
    
    def create_compact_header(self) -> QWidget:
        """Crée l'en-tête compact avec photo, info et statut."""
        header = QFrame()
        header.setMinimumHeight(120)  # Plus de hauteur pour éviter l'écrasement
        header.setMaximumHeight(140)
        header.setStyleSheet("background-color: #2a2a2a; border-radius: 8px; margin: 5px;")
        
        layout = QHBoxLayout(header)
        layout.setContentsMargins(20, 15, 20, 15)  # Plus de marges
        layout.setSpacing(30)  # Plus d'espacement
        
        # Photo de profil cliquable
        self.photo_label = QLabel()
        self.photo_label.setFixedSize(70, 70)  # Légèrement plus grande
        self.photo_label.setStyleSheet("""
            QLabel {
                border: 2px solid #555555;
                border-radius: 35px;
                background-color: #3a3a3a;
                color: #e0e0e0;
            }
        """)
        self.photo_label.setText("👤")
        self.photo_label.setAlignment(Qt.AlignCenter)
        try:
            self.photo_label.setText(get_display_text("👤"))
        except Exception:
            pass
        self.photo_label.setFont(QFont("Arial", 22))
        self.photo_label.mousePressEvent = self.select_profile_photo
        self.photo_label.setCursor(QCursor(Qt.PointingHandCursor))
        layout.addWidget(self.photo_label)
        
        # Section informations principales - Plus d'espace vertical
        info_section = QVBoxLayout()
        info_section.setSpacing(10)
        
        # Nom (ligne dédiée, bien visible)
        self.name_edit = QLineEdit(str(self.profile.name or ""))
        self.name_edit.setPlaceholderText("Nom complet...")
        self.name_edit.setStyleSheet("""
            QLineEdit {
                font-size: 16px; 
                font-weight: bold; 
                background-color: #3a3a3a;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 8px 12px;
                color: #ffffff;
                min-width: 280px;
            }
            QLineEdit:focus {
                border: 2px solid #4db8ff;
                background-color: #404040;
            }
            QLineEdit:hover {
                border-color: #777777;
            }
        """)
        self.name_edit.editingFinished.connect(self.save_name_change)
        info_section.addWidget(self.name_edit)
        
        # Contact - Email et Téléphone avec plus d'espace
        contact_layout = QHBoxLayout()
        contact_layout.setSpacing(15)
        
        # Email 
        self.email_edit = QLineEdit(str(self.profile.email or ""))
        self.email_edit.setPlaceholderText("📧 Email...")
        self.email_edit.setStyleSheet("""
            QLineEdit {
                background-color: #3a3a3a;
                border: 1px solid #555555;
                border-radius: 3px;
                padding: 6px 10px;
                color: #ffffff;
                font-size: 12px;
                min-width: 180px;
            }
            QLineEdit:focus {
                border: 2px solid #4db8ff;
                background-color: #404040;
            }
            QLineEdit:hover {
                border-color: #777777;
            }
        """)
        self.email_edit.editingFinished.connect(self.save_email_change)
        contact_layout.addWidget(self.email_edit)
        
        # Téléphone avec plus d'espace
        self.phone_widget = PhoneNumberWidget(str(self.profile.phone or ""), "📞 Téléphone...", self)
        self.phone_widget.setMinimumWidth(180)
        self.phone_widget.setMaximumWidth(220)
        self.phone_widget.phone_changed.connect(self.save_phone_change_from_widget)
        contact_layout.addWidget(self.phone_widget)
        
        info_section.addLayout(contact_layout)
        layout.addLayout(info_section, 3)
        
        # Section LinkedIn + liens avec plus d'espace
        social_section = QVBoxLayout()
        social_section.setSpacing(10)
        
        # LinkedIn avec plus d'espace
        self.linkedin_edit = QLineEdit(str(self.profile.linkedin_url or ""))
        self.linkedin_edit.setPlaceholderText("🔗 LinkedIn...")
        self.linkedin_edit.setStyleSheet("""
            QLineEdit {
                background-color: #3a3a3a;
                border: 1px solid #555555;
                border-radius: 3px;
                padding: 6px 10px;
                color: #ffffff;
                font-size: 12px;
                min-width: 250px;
            }
            QLineEdit:focus {
                border: 2px solid #4db8ff;
                background-color: #404040;
            }
            QLineEdit:hover {
                border-color: #777777;
            }
        """)
        self.linkedin_edit.editingFinished.connect(self.save_linkedin_change)
        try:
            self.linkedin_edit.setPlaceholderText(f"{get_display_text('🔗')} LinkedIn...")
        except Exception:
            pass
        self.linkedin_edit.setMaximumWidth(360)
        social_section.addWidget(self.linkedin_edit)
        
        # Liens additionnels avec plus d'espace
        self.links_container = QHBoxLayout()
        self.links_container.setSpacing(8)
        
        # Initialiser l'affichage des liens
        try:
            self.refresh_links_display()
        except Exception as e:
            logger.error(f"Erreur lors de l'initialisation des liens: {e}")
            links_placeholder = QLabel("🌐 Aucun lien additionnel")
            links_placeholder.setStyleSheet("color: #888888; font-size: 11px;")
            self.links_container.addWidget(links_placeholder)
        
        social_section.addLayout(self.links_container)
        layout.addLayout(social_section, 2)
        
        # Spacer pour pousser le statut à droite
        layout.addStretch(1)
        
        # Section statut (avec plus d'espace et meilleure lisibilité)
        status_section = QVBoxLayout()
        status_section.setAlignment(Qt.AlignTop | Qt.AlignRight)
        status_section.setSpacing(8)
        
        # Statut principal plus visible
        status_label = QLabel("✅ Profil CV")
        status_label.setFont(QFont("Arial", 13, QFont.Weight.Bold))
        try:
            status_label.setText(f"{get_display_text('📄')} Profil CV")
        except Exception:
            pass
        status_label.setStyleSheet("color: #4db8ff; text-align: right;")
        status_label.setAlignment(Qt.AlignRight)
        status_label.setMinimumWidth(160)
        status_section.addWidget(status_label)
        
        # Sous-statut
        substatus_label = QLabel("Prêt à l'emploi")
        substatus_label.setStyleSheet("color: #e0e0e0; font-size: 11px; text-align: right;")
        substatus_label.setAlignment(Qt.AlignRight)
        substatus_label.setMinimumWidth(160)
        status_section.addWidget(substatus_label)
        
        # Date avec plus de lisibilité
        date_label = QLabel(f"🕒 {datetime.now().strftime('%d/%m/%Y à %H:%M')}")
        date_label.setStyleSheet("color: #a0a0a0; font-size: 10px; text-align: right;")
        date_label.setAlignment(Qt.AlignRight)
        try:
            date_label.setText(f"{get_display_text('📅')} {datetime.now().strftime('%d/%m/%Y à %H:%M')}")
        except Exception:
            pass
        date_label.setMinimumWidth(160)
        status_section.addWidget(date_label)
        
        layout.addLayout(status_section, 1)
        
        return header
    
    def create_main_content(self) -> QWidget:
        """Crée le panneau principal avec les onglets."""
        # Onglets pour différentes vues
        self.tab_widget = QTabWidget()
        
        # Onglet Vue structurée
        structured_tab = self.create_structured_view()
        self.tab_widget.addTab(structured_tab, "📋 Vue structurée")
        
        # Onglet Vue JSON
        json_tab = self.create_json_view()
        self.tab_widget.addTab(json_tab, "🔧 Vue technique")
        
        # Onglet Comparaison CV/LinkedIn
        comparison_tab = self.create_comparison_view()
        self.tab_widget.addTab(comparison_tab, "⚖️ Comparaison")
        
        # Onglet Analyse qualité
        quality_tab = self.create_quality_analysis()
        self.tab_widget.addTab(quality_tab, "📊 Analyse qualité")
        try:
            self.tab_widget.setTabText(0, f"{get_display_text('🗂️')} Vue structurée")
            self.tab_widget.setTabText(1, f"{get_display_text('🧪')} Vue technique")
            self.tab_widget.setTabText(2, f"{get_display_text('🔀')} Comparaison")
            self.tab_widget.setTabText(3, f"{get_display_text('📊')} Analyse qualité")
        except Exception:
            pass

        return self.tab_widget
    
    def create_structured_view(self) -> QWidget:
        """Crée la vue structurée des données."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Zone de défilement
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        
        # Utiliser le widget principal avec toutes les sections
        content_widget = self.create_main_sections_widget()
        
        scroll.setWidget(content_widget)
        layout.addWidget(scroll)
        
        return widget
    
    def create_main_sections_widget(self) -> QWidget:
        """Crée le widget principal avec toutes les sections."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(25)
        layout.setContentsMargins(25, 25, 25, 25)
        
        # Créer toutes les sections modulaires
        self.create_all_sections(layout)
        
        return widget
    
    def _sanitize_profile_for_display(self):
        """Nettoie les expériences suspectes avant affichage."""
        def looks_like_interest_local(s: str) -> bool:
            kws = [
                "natation","fitness","course","marathon","trail","randonnée","vélo","cyclisme",
                "football","basket","tennis","escalade","musculation","yoga","danse",
                "musique","piano","guitare","batterie","chant","cinéma","lecture",
                "voyage","cuisine","jeux vidéo","échecs","bénévolat"
            ]
            import re
            s = (s or "").lower()
            return any(re.search(rf"\b{kw}\b", s, re.I) for kw in kws)

        exps = list(getattr(self.profile, "extracted_experiences", []) or [])
        keep, demoted = [], []
        for e in exps:
            # Handle description which can be a list or string
            description = e.get("description", "")
            if isinstance(description, list):
                description = " ".join(description)
            elif description is None:
                description = ""
            
            blob = " ".join([e.get("title",""), e.get("company",""), description])
            if e.get("_excluded"):
                continue
            if ((e.get("title") in (None,"","Poste à définir") and 
                 e.get("company") in (None,"","Entreprise à définir")) or 
                looks_like_interest_local(blob)):
                demoted.append(e)
            else:
                keep.append(e)

        if demoted:
            interests = list(getattr(self.profile, "extracted_interests", []) or [])
            for d in demoted:
                label = d.get("title") or d.get("company") or (d.get("description","").split(".")[0] if d.get("description") else "")
                if label:
                    interests.append({"label": label, "note": "reclassé depuis expériences (UI)"})
            self.profile.extracted_interests = interests
            logger.info(f"🧹 Reclassé {len(demoted)} expériences suspectes vers intérêts")

        self.profile.extracted_experiences = keep

    def create_all_sections(self, layout: QVBoxLayout):
        """Crée toutes les sections modulaires et les ajoute au layout.

        Note: Nettoie les anciennes sections avant recréation pour éviter les doublons.
        """
        # Nettoyage défensif: supprimer les anciennes sections si existantes
        if self.sections:
            for section in self.sections.values():
                if hasattr(section, 'clear_dynamic_widgets'):
                    section.clear_dynamic_widgets()
            self.sections.clear()

        self._sanitize_profile_for_display()

        # Informations personnelles
        personal_section = PersonalInfoSection(self.profile, self)
        personal_section.data_updated.connect(self.on_section_data_updated)
        personal_section.structural_change.connect(self.on_structural_change)
        layout.addWidget(personal_section.create_section_widget())
        self.sections['personal'] = personal_section
        
        # Expériences professionnelles
        logger.info(f"🔧 Création ExperienceSection avec {len(self.profile.extracted_experiences or [])} expériences")
        experience_section = ExperienceSection(self.profile, self)
        experience_section.data_updated.connect(self.on_section_data_updated)
        experience_section.structural_change.connect(self.on_structural_change)
        layout.addWidget(experience_section.create_section_widget())
        self.sections['experience'] = experience_section
        
        # Formation/Éducation
        education_section = EducationSection(self.profile, self)
        education_section.data_updated.connect(self.on_section_data_updated)
        education_section.structural_change.connect(self.on_structural_change)
        layout.addWidget(education_section.create_section_widget())
        self.sections['education'] = education_section
        
        # Compétences
        skills_section = SkillsSection(self.profile, self)
        skills_section.data_updated.connect(self.on_section_data_updated)
        skills_section.structural_change.connect(self.on_structural_change)
        layout.addWidget(skills_section.create_section_widget())
        self.sections['skills'] = skills_section
        
        # Soft Skills
        soft_skills_section = SoftSkillsSection(self.profile, self)
        soft_skills_section.data_updated.connect(self.on_section_data_updated)
        soft_skills_section.structural_change.connect(self.on_structural_change)
        layout.addWidget(soft_skills_section.create_section_widget())
        self.sections['soft_skills'] = soft_skills_section
        
        # Projets
        projects_section = ProjectsSection(self.profile, self)
        projects_section.data_updated.connect(self.on_section_data_updated)
        projects_section.structural_change.connect(self.on_structural_change)
        layout.addWidget(projects_section.create_section_widget())
        self.sections['projects'] = projects_section
        
        # Langues
        languages_section = LanguagesSection(self.profile, self)
        languages_section.data_updated.connect(self.on_section_data_updated)
        languages_section.structural_change.connect(self.on_structural_change)
        layout.addWidget(languages_section.create_section_widget())
        self.sections['languages'] = languages_section
        
        # Certifications
        certifications_section = CertificationsSection(self.profile, self)
        certifications_section.data_updated.connect(self.on_section_data_updated)
        certifications_section.structural_change.connect(self.on_structural_change)
        layout.addWidget(certifications_section.create_section_widget())
        self.sections['certifications'] = certifications_section
        
        # Publications
        publications_section = PublicationsSection(self.profile, self)
        publications_section.data_updated.connect(self.on_section_data_updated)
        publications_section.structural_change.connect(self.on_structural_change)
        layout.addWidget(publications_section.create_section_widget())
        self.sections['publications'] = publications_section
        
        # Bénévolat
        volunteering_section = VolunteeringSection(self.profile, self)
        volunteering_section.data_updated.connect(self.on_section_data_updated)
        volunteering_section.structural_change.connect(self.on_structural_change)
        layout.addWidget(volunteering_section.create_section_widget())
        self.sections['volunteering'] = volunteering_section
        
        # Récompenses
        awards_section = AwardsSection(self.profile, self)
        awards_section.data_updated.connect(self.on_section_data_updated)
        awards_section.structural_change.connect(self.on_structural_change)
        layout.addWidget(awards_section.create_section_widget())
        self.sections['awards'] = awards_section
        
        # Références
        references_section = ReferencesSection(self.profile, self)
        references_section.data_updated.connect(self.on_section_data_updated)
        references_section.structural_change.connect(self.on_structural_change)
        layout.addWidget(references_section.create_section_widget())
        self.sections['references'] = references_section
        
        # Centres d'intérêt
        interests_section = InterestsSection(self.profile, self)
        interests_section.data_updated.connect(self.on_section_data_updated)
        interests_section.structural_change.connect(self.on_structural_change)
        layout.addWidget(interests_section.create_section_widget())
        self.sections['interests'] = interests_section
    
    def create_json_view(self) -> QWidget:
        """Crée la vue JSON pour debug."""
        json_text = QTextEdit()
        json_text.setReadOnly(True)
        json_text.setFont(QFont("Consolas", 10))
        
        try:
            profile_dict = self.profile.to_dict() if hasattr(self.profile, 'to_dict') else vars(self.profile)
            json_content = json.dumps(profile_dict, indent=2, ensure_ascii=False, default=str)
            json_text.setPlainText(json_content)
        except Exception as e:
            json_text.setPlainText(f"Erreur lors de la sérialisation JSON: {str(e)}")
        
        return json_text
    
    def create_comparison_view(self) -> QWidget:
        """Crée la vue de comparaison CV/LinkedIn."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        
        # Colonne CV
        cv_group = QGroupBox("Données CV")
        cv_layout = QVBoxLayout()
        self.cv_comparison_text = QTextEdit()
        self.cv_comparison_text.setReadOnly(True)
        cv_layout.addWidget(self.cv_comparison_text)
        cv_group.setLayout(cv_layout)
        
        # Colonne LinkedIn
        linkedin_group = QGroupBox("Données LinkedIn")
        linkedin_layout = QVBoxLayout()
        self.linkedin_comparison_text = QTextEdit()
        self.linkedin_comparison_text.setReadOnly(True)
        linkedin_layout.addWidget(self.linkedin_comparison_text)
        linkedin_group.setLayout(linkedin_layout)
        
        layout.addWidget(cv_group)
        layout.addWidget(linkedin_group)
        
        return widget
    
    def create_quality_analysis(self) -> QWidget:
        """Crée l'onglet d'analyse qualité."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Tableau des métriques
        self.quality_table = QTableWidget()
        self.quality_table.setColumnCount(3)
        self.quality_table.setHorizontalHeaderLabels(["Section", "Statut", "Score"])
        
        header = self.quality_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        
        layout.addWidget(self.quality_table)
        
        # Charger l'analyse qualité
        self.update_quality_analysis()
        
        return widget
    
    def create_compact_footer(self) -> QWidget:
        """Crée le footer compact avec CTA et boutons de sauvegarde."""
        footer = QFrame()
        footer.setMinimumHeight(80)
        footer.setMaximumHeight(100)
        footer.setStyleSheet("background-color: #2a2a2a; border-radius: 8px; margin: 5px;")
        
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(15, 8, 15, 8)
        
        # Indicateur d'état des modifications
        self.status_indicator = QLabel("✅ Aucune modification")
        self.status_indicator.setStyleSheet("color: #4CAF50; font-weight: bold; font-size: 11px;")
        layout.addWidget(self.status_indicator)
        
        # Date de dernière mise à jour (petit texte)
        last_update = QLabel(f"Dernière mise à jour: {datetime.now().strftime('%d/%m/%Y à %H:%M')}")
        last_update.setStyleSheet("color: #a0a0a0; font-size: 10px;")
        layout.addWidget(last_update)
        
        # Spacer
        layout.addStretch()
        
        # Bouton Restaurer supprimé - remplacé par dialogue de fermeture
        
        # Boutons CTA compacts
        btn_style = """
            QPushButton {
                background-color: #3a3a3a;
                color: #e0e0e0;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 5px 10px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
            }
        """
        
        # CTA de visualisation
        struct_btn = QPushButton("📊 Vue structurée")
        struct_btn.setStyleSheet(btn_style)
        struct_btn.clicked.connect(lambda: self.switch_to_tab(0))
        layout.addWidget(struct_btn)
        
        tech_btn = QPushButton("🔧 Vue technique") 
        tech_btn.setStyleSheet(btn_style)
        tech_btn.clicked.connect(lambda: self.switch_to_tab(1))
        layout.addWidget(tech_btn)
        
        comparison_btn = QPushButton("⚖️ Comparaison")
        comparison_btn.setStyleSheet(btn_style)
        comparison_btn.clicked.connect(lambda: self.switch_to_tab(2))
        layout.addWidget(comparison_btn)
        
        quality_btn = QPushButton("📊 Qualité")
        quality_btn.setStyleSheet(btn_style)
        quality_btn.clicked.connect(lambda: self.switch_to_tab(3))
        layout.addWidget(quality_btn)
        
        # Bouton Extraire CV
        extract_cv_btn = QPushButton("📄 Extraire CV")
        extract_cv_btn.setStyleSheet("""
            QPushButton {
                background-color: #0e76a8;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0a5a7a;
            }
        """)
        extract_cv_btn.clicked.connect(self.extract_cv_data)
        layout.addWidget(extract_cv_btn)
        
        # Bouton Resynchro LinkedIn
        linkedin_btn = QPushButton("🔗 Resynchro LinkedIn")
        linkedin_btn.setStyleSheet("""
            QPushButton {
                background-color: #0e76a8;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0a5a7a;
            }
        """)
        linkedin_btn.clicked.connect(self.sync_linkedin_data)
        layout.addWidget(linkedin_btn)
        
        # Bouton Sauvegarder (juste avant le bouton Fermer)
        self.save_btn = QPushButton("💾 Sauvegarder")
        self.save_btn.setEnabled(False)
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #007bff;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 5px 10px;
                font-size: 11px;
                font-weight: bold;
                margin-left: 5px;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
            QPushButton:disabled {
                background-color: #3a3a3a;
                color: #666666;
            }
        """)
        self.save_btn.clicked.connect(self.save_changes)
        layout.addWidget(self.save_btn)
        
        # Bouton Fermer
        close_btn = QPushButton("❌ Fermer")
        close_btn.setStyleSheet(btn_style)
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)
        
        return footer
    
    def save_name_change(self):
        """Sauvegarde le changement de nom."""
        # Ignorer les signaux pendant la restauration
        if getattr(self, '_is_restoring', False):
            return
            
        sender = self.sender()
        if sender and hasattr(sender, 'text'):
            self.profile.name = sender.text()
            self.on_data_modified()
            self.data_updated.emit(self.profile)
    
    def save_email_change(self):
        """Sauvegarde le changement d'email."""
        # Ignorer les signaux pendant la restauration
        if getattr(self, '_is_restoring', False):
            return
            
        sender = self.sender()
        if sender and hasattr(sender, 'text'):
            self.profile.email = sender.text()
            self.on_data_modified()
            self.data_updated.emit(self.profile)
    
    def save_phone_change_from_widget(self, full_phone_number: str):
        """Sauvegarde le changement de téléphone depuis le widget."""
        # Ignorer les signaux pendant la restauration
        if getattr(self, '_is_restoring', False):
            return
            
        self.profile.phone = full_phone_number
        self.on_data_modified()
        self.data_updated.emit(self.profile)
    
    def save_linkedin_change(self):
        """Sauvegarde le changement d'URL LinkedIn."""
        # Ignorer les signaux pendant la restauration
        if getattr(self, '_is_restoring', False):
            return
            
        sender = self.sender()
        if sender and hasattr(sender, 'text'):
            self.profile.linkedin_url = sender.text()
            self.on_data_modified()
            self.data_updated.emit(self.profile)
    
    def on_section_data_updated(self, profile: UserProfile):
        """Callback pour les modifications de données simples (pas de rechargement)."""
        # Ignorer les signaux pendant la restauration
        if getattr(self, '_is_restoring', False):
            return
            
        # Mettre à jour le profil local
        self.profile = profile
        
        # Déclencher la détection de modifications
        self.on_data_modified()
        
        # Propager le signal vers le parent pour sauvegarde
        self.data_updated.emit(profile)
    
    def on_structural_change(self, profile: UserProfile):
        """Callback pour les changements structurels (nécessite rechargement)."""
        # Ignorer les signaux pendant la restauration
        if getattr(self, '_is_restoring', False):
            return

        # Mettre à jour le profil local
        self.profile = profile

        # Déclencher la détection de modifications
        self.on_data_modified()

        # Recharger l'interface avec debouncing pour les changements structurels
        self.request_reload(force_immediate=False)
        # Propager le signal vers le parent
        self.data_updated.emit(profile)
    
    def extract_cv_data(self):
        """Lance l'extraction des données du CV."""
        try:
            if hasattr(self.parent(), 're_extract_cv_data'):
                self.parent().re_extract_cv_data()
            else:
                QMessageBox.information(self, "Extraction CV", "Fonctionnalité d'extraction CV non disponible.")
        except Exception as e:
            logger.error(f"Erreur lors de l'extraction CV: {e}")
            QMessageBox.warning(self, "Erreur", f"Erreur lors de l'extraction CV: {str(e)}")
    
    def sync_linkedin_data(self):
        """Lance la synchronisation des données LinkedIn."""
        try:
            if hasattr(self.parent(), 'sync_linkedin_data'):
                self.parent().sync_linkedin_data()
            else:
                QMessageBox.information(self, "Sync LinkedIn", "Fonctionnalité de synchronisation LinkedIn non disponible.")
        except Exception as e:
            logger.error(f"Erreur lors de la sync LinkedIn: {e}")
            QMessageBox.warning(self, "Erreur", f"Erreur lors de la sync LinkedIn: {str(e)}")
    
    def save_all_changes(self):
        """Sauvegarde toutes les modifications."""
        try:
            # Émettre le signal de mise à jour
            self.data_updated.emit(self.profile)
            QMessageBox.information(self, "Sauvegarde", "Toutes les modifications ont été sauvegardées.")
            logger.info("Profile sauvegardé avec succès")
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde: {e}")
            QMessageBox.warning(self, "Erreur", f"Erreur lors de la sauvegarde: {str(e)}")

    def _delayed_reload(self):
        """Exécute le rechargement après le délai de debouncing."""
        if self._pending_reload:
            self._pending_reload = False
            self.load_profile_data()

    def request_reload(self, force_immediate=False):
        """Demande un rechargement avec debouncing pour éviter les recharges multiples."""
        import time
        current_time = time.time()

        if force_immediate or (current_time - self._last_reload_time) > 2.0:
            # Si plus de 2 secondes depuis le dernier reload, exécuter immédiatement
            self._reload_timer.stop()
            self._pending_reload = False
            self.load_profile_data()
            self._last_reload_time = current_time
        else:
            # Sinon, utiliser le système de debouncing (500ms)
            if not self._pending_reload:
                self._pending_reload = True
                self._reload_timer.start(500)

    def load_profile_data(self):
        """Charge les données du profil et recrée l'interface."""
        import time
        start_time = time.time()
        import traceback
        caller_info = traceback.extract_stack()[-2]
        logger.info(f"📊 Rechargement des données du profil - Appelé depuis {caller_info.filename}:{caller_info.lineno}")
        
        # Sauvegarder la position de scroll actuelle
        current_scroll_position = 0
        if hasattr(self, 'tab_widget'):
            current_tab = self.tab_widget.currentIndex()
            # Si on est sur l'onglet structuré, sauvegarder le scroll
            if current_tab == 0:
                structured_widget = self.tab_widget.widget(0)
                if hasattr(structured_widget, 'findChild'):
                    scroll_area = structured_widget.findChild(QScrollArea)
                    if scroll_area:
                        current_scroll_position = scroll_area.verticalScrollBar().value()
        
        # Recréer l'interface principale complètement
        if hasattr(self, 'tab_widget'):
            # Sauvegarder l'onglet actuel
            current_tab_index = self.tab_widget.currentIndex()

            # Recréer le contenu principal
            new_main_widget = self.create_main_content()

            # Remplacer l'ancien widget dans le layout principal
            main_layout = self.layout()
            for i in range(main_layout.count()):
                item = main_layout.itemAt(i)
                if item and item.widget() == self.tab_widget:
                    main_layout.removeWidget(self.tab_widget)
                    # SAFE: Use safe deletion to prevent "already deleted" errors
                    self._safe_delete_widget(self.tab_widget)
                    main_layout.insertWidget(i, new_main_widget)
                    self.tab_widget = new_main_widget
                    break

            # Restaurer l'onglet actuel
            if current_tab_index < self.tab_widget.count():
                self.tab_widget.setCurrentIndex(current_tab_index)
                
                # Restaurer la position de scroll si c'était l'onglet structuré
                if current_tab_index == 0 and current_scroll_position > 0:
                    QTimer.singleShot(100, lambda: self._restore_scroll_position(current_scroll_position))
        
        # Rafraîchir les liens dans le header
        if hasattr(self, 'links_container'):
            try:
                self.refresh_links_display()
            except Exception as e:
                logger.warning(f"Erreur lors de la mise à jour des liens: {e}")
                
        end_time = time.time()
        duration = end_time - start_time
        self._reload_count += 1
        self._reload_durations.append(duration)

        # Calculer les statistiques de performance
        avg_duration = sum(self._reload_durations) / len(self._reload_durations) if self._reload_durations else 0
        logger.info(f"Interface rechargée avec succès en {duration:.2f}s (#{self._reload_count}, moyenne: {avg_duration:.2f}s)")
    
    def _restore_scroll_position(self, position: int):
        """Restaure la position de scroll."""
        if hasattr(self, 'tab_widget') and self.tab_widget.count() > 0:
            structured_widget = self.tab_widget.widget(0)
            if hasattr(structured_widget, 'findChild'):
                scroll_area = structured_widget.findChild(QScrollArea)
                if scroll_area:
                    scroll_area.verticalScrollBar().setValue(position)
                    logger.debug(f"Position de scroll restaurée : {position}")

    def get_performance_stats(self):
        """Retourne les statistiques de performance des recharges."""
        if not self._reload_durations:
            return "Aucun rechargement effectué"

        avg_duration = sum(self._reload_durations) / len(self._reload_durations)
        max_duration = max(self._reload_durations)
        min_duration = min(self._reload_durations)

        return (f"Statistiques de rechargement:\n"
                f"- Nombre total: {self._reload_count}\n"
                f"- Durée moyenne: {avg_duration:.2f}s\n"
                f"- Durée max: {max_duration:.2f}s\n"
                f"- Durée min: {min_duration:.2f}s")

    # Méthodes de compatibilité pour ne pas casser le code existant
    def get_filtered_data(self, data, section_name: str = ""):
        """Filtre les données selon leur niveau de confiance - Méthode de compatibilité."""
        if isinstance(data, dict) and has_confidence_scores(data):
            return filter_high_confidence(data, section_name)
        elif isinstance(data, list):
            return [filter_high_confidence(item, section_name) if has_confidence_scores(item) else item 
                   for item in data]
        return data
    
    def select_profile_photo(self, event):
        """Sélectionne une nouvelle photo de profil."""
        file_dialog = QFileDialog()
        file_path, _ = file_dialog.getOpenFileName(
            self, 
            "Sélectionner une photo de profil",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif)"
        )
        
        if file_path:
            try:
                # Charger et redimensionner l'image
                pixmap = QPixmap(file_path)
                if not pixmap.isNull():
                    scaled_pixmap = pixmap.scaled(60, 60, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    self.photo_label.setPixmap(scaled_pixmap)
                    self.photo_label.setText("")  # Enlever le texte emoji
                    
                    # Sauvegarder le chemin dans le profil (optionnel)
                    if hasattr(self.profile, 'photo_path'):
                        self.profile.photo_path = file_path
                        self.data_updated.emit(self.profile)
            except Exception as e:
                logger.error(f"Erreur lors du chargement de la photo: {e}")
                QMessageBox.warning(self, "Erreur", f"Impossible de charger la photo: {str(e)}")
    
    def refresh_links_display(self):
        """Rafraîchit l'affichage des liens dans le header."""
        # Nettoyer les widgets existants
        while self.links_container.count():
            child = self.links_container.takeAt(0)
            if child.widget():
                # SAFE: Use safe deletion to prevent "already deleted" errors
                self._safe_delete_widget(child.widget())
        
        # Récupérer les liens du profil depuis extracted_personal_info
        links = []
        personal_info = self.profile.extracted_personal_info or {}
        if 'links' in personal_info and personal_info['links']:
            links.extend(personal_info['links'])
        
        # Ajouter LinkedIn URL si présent
        if hasattr(self.profile, 'linkedin_url') and self.profile.linkedin_url:
            links.append({"platform": "LinkedIn", "url": self.profile.linkedin_url})
        
        # Plus d'affichage des liens dans le header (centralisé dans PersonalInfoSection)
        
        # Spacer pour pousser vers la gauche
        self.links_container.addStretch()
    
    
    def open_link(self, url: str):
        """Ouvre un lien dans le navigateur."""
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception as e:
            logger.error(f"Erreur lors de l'ouverture du lien: {e}")
    
    def update_quality_analysis(self):
        """Met à jour l'analyse qualité."""
        if not hasattr(self, 'quality_table'):
            return
            
        # Définir les sections à analyser
        sections_to_analyze = [
            ("Informations personnelles", self.profile.name and self.profile.email),
            ("Expériences", bool(getattr(self.profile, 'extracted_experiences', None))),
            ("Formation", bool(getattr(self.profile, 'extracted_education', None))),
            ("Compétences", bool(getattr(self.profile, 'extracted_skills', None))),
            ("Langues", bool(getattr(self.profile, 'extracted_languages', None))),
        ]
        
        self.quality_table.setRowCount(len(sections_to_analyze))
        
        for i, (section_name, has_data) in enumerate(sections_to_analyze):
            # Nom de la section
            self.quality_table.setItem(i, 0, QTableWidgetItem(section_name))
            
            # Statut
            status = "✅ Complète" if has_data else "⚠️ Incomplète"
            self.quality_table.setItem(i, 1, QTableWidgetItem(status))
            
            # Score
            score = "100%" if has_data else "0%"
            self.quality_table.setItem(i, 2, QTableWidgetItem(score))
    
    def switch_to_tab(self, index: int):
        """Change vers l'onglet spécifié."""
        if hasattr(self, 'tab_widget'):
            self.tab_widget.setCurrentIndex(index)
    
    def _create_profile_cache(self) -> Dict[str, Any]:
        """Crée un cache des données actuelles du profil."""
        return {
            'extracted_personal_info': self.profile.extracted_personal_info.copy() if self.profile.extracted_personal_info else {},
            'extracted_experiences': [exp.copy() for exp in (self.profile.extracted_experiences or [])],
            'extracted_education': [edu.copy() for edu in (self.profile.extracted_education or [])],
            'extracted_skills': [skill.copy() for skill in (self.profile.extracted_skills or [])] if isinstance(self.profile.extracted_skills, list) else (self.profile.extracted_skills.copy() if self.profile.extracted_skills else {}),
            'extracted_languages': [lang.copy() for lang in (self.profile.extracted_languages or [])],
            'extracted_projects': [proj.copy() for proj in (self.profile.extracted_projects or [])],
            'extracted_certifications': [cert.copy() for cert in (self.profile.extracted_certifications or [])],
            'extracted_publications': [pub.copy() for pub in (self.profile.extracted_publications or [])],
            'extracted_volunteering': [vol.copy() for vol in (self.profile.extracted_volunteering or [])],
            'extracted_awards': [award.copy() for award in (self.profile.extracted_awards or [])],
            'extracted_references': [ref.copy() for ref in (self.profile.extracted_references or [])],
            'extracted_interests': (self.profile.extracted_interests or []).copy()
        }
    
    def _restore_from_cache(self):
        """Restaure les données du profil depuis le cache."""
        cache = self.original_data_cache
        
        # Log pour debug
        logger.info(f"📊 Cache experiences: {len(cache.get('extracted_experiences', []))} éléments")
        logger.info(f"📊 Profil experiences avant: {len(self.profile.extracted_experiences or [])} éléments")
        
        # Restaurer toutes les données extraites
        self.profile.extracted_personal_info = cache['extracted_personal_info'].copy()
        self.profile.extracted_experiences = [exp.copy() for exp in cache['extracted_experiences']]
        self.profile.extracted_education = [edu.copy() for edu in cache['extracted_education']]
        self.profile.extracted_skills = cache['extracted_skills'].copy() if isinstance(cache['extracted_skills'], dict) else [skill.copy() for skill in cache['extracted_skills']]
        self.profile.extracted_languages = [lang.copy() for lang in cache['extracted_languages']]
        self.profile.extracted_projects = [proj.copy() for proj in cache['extracted_projects']]
        self.profile.extracted_certifications = [cert.copy() for cert in cache['extracted_certifications']]
        self.profile.extracted_publications = [pub.copy() for pub in cache['extracted_publications']]
        self.profile.extracted_volunteering = [vol.copy() for vol in cache['extracted_volunteering']]
        self.profile.extracted_awards = [award.copy() for award in cache['extracted_awards']]
        self.profile.extracted_references = [ref.copy() for ref in cache['extracted_references']]
        self.profile.extracted_interests = cache['extracted_interests'].copy()
        
        # Log pour debug
        logger.info(f"📊 Profil experiences après: {len(self.profile.extracted_experiences or [])} éléments")
        logger.info("🔄 Données restaurées depuis le cache")
    
    def closeEvent(self, event):
        """Gère la fermeture de la fenêtre avec dialogue de confirmation si modifications non sauvegardées."""
        if self.has_unsaved_changes:
            # Afficher le dialogue de confirmation avec 3 options
            choice = self.show_close_confirmation_dialog()
            
            if choice == "save_and_close":
                # Sauvegarder puis fermer
                try:
                    self.save_changes()
                    logger.info("✅ Modifications sauvegardées avant fermeture")
                    event.accept()
                except Exception as e:
                    logger.error(f"Erreur lors de la sauvegarde: {e}")
                    event.ignore()  # Empêcher la fermeture si sauvegarde échoue
            
            elif choice == "close_without_save":
                # Fermer et perdre les modifications (restaurer depuis le cache)
                logger.info("🔄 Fermeture avec restauration automatique depuis le cache")
                self._restore_from_cache()
                event.accept()
            
            else:  # choice == "cancel" ou dialog fermé
                # Rester sur la page
                logger.info("❌ Fermeture annulée - l'utilisateur continue les modifications")
                event.ignore()
        else:
            logger.info("✅ Fermeture de la page détaillée - aucune modification à annuler")
            event.accept()
    
    def show_close_confirmation_dialog(self) -> str:
        """Affiche le dialogue de confirmation de fermeture avec 3 options."""
        from PySide6.QtWidgets import QMessageBox
        
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Question)
        msg.setWindowTitle("Modifications non sauvegardées")
        msg.setText("Vous avez des modifications non sauvegardées.")
        msg.setInformativeText("Que souhaitez-vous faire ?")
        
        # Définir les 3 boutons avec des textes clairs
        save_btn = msg.addButton("Sauvegarder et fermer", QMessageBox.AcceptRole)
        stay_btn = msg.addButton("Continuer à modifier", QMessageBox.RejectRole)  
        discard_btn = msg.addButton("Fermer sans sauvegarder", QMessageBox.DestructiveRole)
        
        # Définir le bouton par défaut (le plus sûr)
        msg.setDefaultButton(stay_btn)
        
        # Agrandir la fenêtre et ajuster les boutons
        msg.resize(500, 200)
        
        # Personnaliser le style pour s'adapter au thème sombre
        msg.setStyleSheet("""
            QMessageBox {
                background-color: #2a2a2a;
                color: #e0e0e0;
                min-width: 480px;
                font-size: 13px;
            }
            QMessageBox QPushButton {
                background-color: #4db8ff;
                color: white;
                border: none;
                padding: 10px 14px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 12px;
                min-width: 140px;
                max-width: 180px;
            }
            QMessageBox QPushButton:hover {
                background-color: #66c2ff;
            }
            QMessageBox QPushButton[role="destructive"] {
                background-color: #e74c3c;
            }
            QMessageBox QPushButton[role="destructive"]:hover {
                background-color: #c0392b;
            }
        """)
        
        # Exécuter le dialogue et retourner le choix
        msg.exec()
        clicked_button = msg.clickedButton()
        
        if clicked_button == save_btn:
            return "save_and_close"
        elif clicked_button == discard_btn:
            return "close_without_save" 
        else:  # stay_btn ou fermeture du dialog
            return "cancel"
    
    def on_data_modified(self):
        """Appelé quand des données sont modifiées dans les sections."""
        self.has_unsaved_changes = True
        
        # Activer le bouton de sauvegarde
        if hasattr(self, 'save_btn'):
            self.save_btn.setEnabled(True)
        
        # Mettre à jour l'indicateur d'état
        if hasattr(self, 'status_indicator'):
            self.status_indicator.setText("⚠️ Modifications non sauvegardées")
            self.status_indicator.setStyleSheet("color: #FF9800; font-weight: bold; font-size: 11px;")
        
        logger.info("📝 Modifications détectées dans la page détaillée")
    
    def save_changes(self):
        """Sauvegarde les modifications dans la base de données."""
        logger.info("🔘 DEBUT save_changes() - Méthode appelée")
        try:
            logger.info("💾 Début de la sauvegarde...")
            from ..models.database import get_session
            
            # Log des données avant sauvegarde
            logger.info(f"📊 Sauvegarde - Expériences: {len(self.profile.extracted_experiences or [])}")
            logger.info(f"📊 Sauvegarde - Email: {self.profile.email}")
            
            # Log des informations personnelles (adresse, ville, etc.)
            personal_info = self.profile.extracted_personal_info or {}
            logger.info(f"📊 Sauvegarde - Adresse: {personal_info.get('address', 'Vide')}")
            logger.info(f"📊 Sauvegarde - Ville: {personal_info.get('city', 'Vide')}")
            logger.info(f"📊 Sauvegarde - Code postal: {personal_info.get('postal_code', 'Vide')}")
            
            # Sauvegarder le profil en base de données
            with get_session() as session:
                # Utiliser merge() pour les mises à jour (plus robuste que add())
                updated_profile = session.merge(self.profile)
                session.commit()
                session.refresh(updated_profile)
                
                # Mettre à jour la référence locale
                self.profile = updated_profile
                
            logger.info("💾 Sauvegarde en base réussie")
            
            # Mettre à jour le cache avec les nouvelles données sauvegardées
            self.original_data_cache = self._create_profile_cache()
            self.has_unsaved_changes = False
            
            # Désactiver le bouton de sauvegarde
            if hasattr(self, 'save_btn'):
                self.save_btn.setEnabled(False)
            
            # Mettre à jour l'indicateur d'état
            if hasattr(self, 'status_indicator'):
                self.status_indicator.setText("✅ Modifications sauvegardées")
                self.status_indicator.setStyleSheet("color: #4CAF50; font-weight: bold; font-size: 11px;")
            
            # Émettre le signal de mise à jour
            self.data_updated.emit(self.profile)
            
            logger.info("✅ Modifications sauvegardées avec succès en base de données")
            
        except Exception as e:
            logger.error(f"❌ Erreur lors de la sauvegarde: {e}")
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(
                self,
                "Erreur de sauvegarde",
                f"Une erreur est survenue lors de la sauvegarde :\n{str(e)}"
            )
    
    def cancel_changes(self):
        """Restaure les modifications depuis le cache (même logique que la fermeture)."""
        try:
            logger.info("🔄 Restauration des données depuis le cache")
            
            # Marquer qu'on est en cours de restauration pour éviter les signaux indésirables
            self._is_restoring = True
            
            # Restaurer depuis le cache AVANT de recharger l'interface
            self._restore_from_cache()
            
            # Réinitialiser l'état avant le rechargement
            self.has_unsaved_changes = False
            
            # Utiliser la même méthode robuste que lors de la fermeture
            self.load_profile_data()
            
            # Forcer le rafraîchissement de l'affichage Qt
            self.update()
            self.repaint()
            if hasattr(self, 'tab_widget'):
                self.tab_widget.update()
                self.tab_widget.repaint()
            
            # Forcer un rafraîchissement différé pour être sûr
            from PySide6.QtCore import QTimer
            QTimer.singleShot(100, self._force_display_refresh)
            
            # Désactiver le bouton de sauvegarde
            if hasattr(self, 'save_btn'):
                self.save_btn.setEnabled(False)
            
            # Mettre à jour l'indicateur d'état
            if hasattr(self, 'status_indicator'):
                self.status_indicator.setText("✅ Données restaurées")
                self.status_indicator.setStyleSheet("color: #4CAF50; font-weight: bold; font-size: 11px;")
            
            # Fin de la restauration
            self._is_restoring = False
            
            logger.info("✅ Données restaurées avec succès depuis le cache")
            
        except Exception as e:
            self._is_restoring = False  # S'assurer de remettre le flag même en cas d'erreur
            logger.error(f"Erreur lors de la restauration: {e}")
            # Mettre à jour l'indicateur d'erreur
            if hasattr(self, 'status_indicator'):
                self.status_indicator.setText("❌ Erreur lors de la restauration")
                self.status_indicator.setStyleSheet("color: #e74c3c; font-weight: bold; font-size: 11px;")
    
    def _force_full_reload(self):
        """Force un rechargement complet de l'interface pour afficher les données restaurées."""
        try:
            # Utiliser la même logique que load_profile_data pour recréer complètement l'interface
            new_main_widget = self.create_main_content()

            # Remplacer l'ancien widget dans le layout principal
            main_layout = self.layout()
            for i in range(main_layout.count()):
                item = main_layout.itemAt(i)
                if item and item.widget() == self.tab_widget:
                    main_layout.removeWidget(self.tab_widget)
                    # SAFE: Use safe deletion to prevent "already deleted" errors
                    self._safe_delete_widget(self.tab_widget)
                    main_layout.insertWidget(i, new_main_widget)
                    self.tab_widget = new_main_widget
                    break

            logger.info("🔄 Interface complètement rechargée avec les données restaurées")
            
        except Exception as e:
            logger.error(f"Erreur lors du rechargement complet: {e}")
            # Fallback: rechargement simple
            self.load_profile_data()
    
    def _force_display_refresh(self):
        """Force un rafraîchissement complet de l'affichage."""
        try:
            # Rafraîchir tous les widgets visibles
            self.update()
            if hasattr(self, 'tab_widget'):
                current_tab = self.tab_widget.currentWidget()
                if current_tab:
                    current_tab.update()
                    current_tab.repaint()
                    
                    # Forcer la mise à jour de tous les enfants (avec vérification du type)
                    for child in current_tab.findChildren(QWidget):
                        try:
                            child.update()
                        except TypeError:
                            # Certains widgets Qt ont des signatures différentes pour update()
                            pass
            
            logger.info("🔄 Rafraîchissement d'affichage forcé")
            
        except Exception as e:
            logger.error(f"Erreur lors du rafraîchissement forcé: {e}")
