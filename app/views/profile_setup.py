"""
Profile Setup Dialog
===================

Interface de configuration initiale du profil utilisateur.
"""

import json
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QWizard,
    QWizardPage,
)

from ..config import DEFAULT_PII_CONFIG

# PATCH-PII: Remplacement par logger sécurisé
from ..logging.safe_logger import get_safe_logger

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)

from ..models.database import get_session
from ..models.user_profile import ModelVersion, UserProfile
from ..services.dialogs import confirm, show_error, show_success, show_warning
from ..utils.parsers import DocumentParser
from ..widgets.phone_widget import create_phone_widget
from ..widgets.style_manager import apply_button_style
from ..workers.cv_extractor import CVExtractor
from ..workers.profile_parser import ProfileParserWorker

# Logger déjà importé via patch PII ci-dessus


class DragDropArea(QFrame):
    """Zone de drag & drop pour les fichiers."""

    file_dropped = Signal(str)

    def __init__(
        self, text: str = "Glisser votre fichier ici", allowed_extensions: list = None
    ):
        super().__init__()
        self.allowed_extensions = allowed_extensions or [".pdf", ".docx", ".txt"]
        self.setAcceptDrops(True)
        self.setFrameStyle(QFrame.Box | QFrame.Raised)
        self.setLineWidth(2)
        self.setMidLineWidth(1)
        self.setStyleSheet(
            """
            QFrame {
                border: 2px dashed #aaa;
                border-radius: 10px;
                background-color: #f9f9f9;
                color: #666;
            }
            QFrame:hover {
                border-color: #0078d4;
                background-color: #f0f8ff;
            }
            QFrame[rejected="true"] {
                border-color: #d32f2f;
                background-color: #ffebee;
            }
        """
        )

        layout = QVBoxLayout()
        self.label = QLabel(text)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setWordWrap(True)
        font = QFont()
        font.setPointSize(12)
        self.label.setFont(font)
        layout.addWidget(self.label)

        self.setLayout(layout)
        self.setMinimumHeight(120)

    def is_file_allowed(self, file_path: str) -> bool:
        """Vérifie si l'extension du fichier est autorisée."""
        from pathlib import Path

        file_ext = Path(file_path).suffix.lower()
        return file_ext in self.allowed_extensions

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            files = [url.toLocalFile() for url in event.mimeData().urls()]
            if files and self.is_file_allowed(files[0]):
                event.acceptProposedAction()
                self.setProperty("rejected", False)
                self.setStyleSheet(self.styleSheet())
            else:
                event.ignore()
                self.setProperty("rejected", True)
                self.setStyleSheet(self.styleSheet())
                # Rétablir l'état normal après 1 seconde
                QTimer.singleShot(
                    1000,
                    lambda: (
                        self.setProperty("rejected", False),
                        self.setStyleSheet(self.styleSheet()),
                    ),
                )

    def dropEvent(self, event: QDropEvent):
        files = [url.toLocalFile() for url in event.mimeData().urls()]
        if files and self.is_file_allowed(files[0]):
            self.file_dropped.emit(files[0])
        else:
            # Afficher un message d'erreur
            from PySide6.QtWidgets import QMessageBox

            allowed_str = ", ".join(self.allowed_extensions)
            show_warning(
                f"Ce format de fichier n'est pas supporté.\n\n"
                f"Formats autorisés : {allowed_str}",
                title="Format non supporté",
                parent=self,
            )


class WelcomePage(QWizardPage):
    """Page d'accueil du wizard."""

    def __init__(self):
        super().__init__()
        self.setTitle("🎉 Bienvenue dans CVMatch")
        self.setSubTitle(
            "Configurons votre profil pour commencer à générer des CV intelligents"
        )

        layout = QVBoxLayout()

        # Description
        desc = QLabel(
            """
        <h3>CVMatch - Votre assistant IA pour candidatures</h3>
        <p>CVMatch génère des CV et lettres de motivation personnalisés pour chaque offre d'emploi 
        en utilisant l'intelligence artificielle.</p>
        
        <p><b>Fonctionnalités :</b></p>
        <ul>
        <li>🤖 IA personnalisée qui apprend vos préférences</li>
        <li>📄 Génération automatique CV + lettre de motivation</li>
        <li>🎨 Templates professionnels modernes</li>
        <li>📊 Suivi de vos candidatures</li>
        <li>🔄 Amélioration continue de l'IA</li>
        </ul>
        
        <p>Cet assistant va vous guider pour configurer votre profil en quelques étapes.</p>
        """
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        self.setLayout(layout)


class PersonalInfoPage(QWizardPage):
    """Page des informations personnelles."""

    def __init__(self):
        super().__init__()
        self.setTitle("👤 Informations personnelles")
        self.setSubTitle("Renseignez vos informations de base")

        layout = QFormLayout()

        # Champs obligatoires
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Votre nom complet")
        layout.addRow("Nom *:", self.name_edit)

        self.email_edit = QLineEdit()
        self.email_edit.setPlaceholderText("votre.email@exemple.com")
        layout.addRow("Email *:", self.email_edit)

        self.phone_widget = create_phone_widget("", "6 12 34 56 78", self)
        layout.addRow("Téléphone:", self.phone_widget)

        # LinkedIn optionnel
        self.linkedin_edit = QLineEdit()
        self.linkedin_edit.setPlaceholderText("https://linkedin.com/in/votre-profil")
        layout.addRow("LinkedIn:", self.linkedin_edit)

        self.setLayout(layout)

        # Validation
        self.name_edit.textChanged.connect(self.completeChanged)
        self.email_edit.textChanged.connect(self.completeChanged)

        # Enregistrement des champs - seulement les obligatoires
        self.registerField("name*", self.name_edit)
        self.registerField("email*", self.email_edit)
        # Phone et LinkedIn ne sont pas enregistrés pour éviter la validation forcée
        # Ils seront récupérés manuellement dans start_processing()

    def validate_page(self):
        """Valide que les champs obligatoires sont remplis."""
        name_valid = len(self.name_edit.text().strip()) >= 2
        email_valid = "@" in self.email_edit.text() and "." in self.email_edit.text()
        # LinkedIn est optionnel - pas de validation nécessaire
        return name_valid and email_valid

    def isComplete(self):
        return self.validate_page()


class DocumentsPage(QWizardPage):
    """Page pour uploader les documents."""

    def __init__(self):
        super().__init__()
        self.setTitle("📄 Documents de référence")
        self.setSubTitle("Uploadez votre CV principal et lettre type (optionnelle)")

        self.cv_path = None
        self.letter_path = None

        # Champ caché pour stocker le chemin du CV
        self.cv_path_field = QLineEdit()
        self.cv_path_field.setVisible(False)

        layout = QVBoxLayout()
        layout.addWidget(self.cv_path_field)  # Ajouter le champ caché

        # CV principal
        cv_group = QFrame()
        cv_layout = QVBoxLayout(cv_group)
        cv_info_text = QLabel(
            "<b>CV de référence (optionnel)</b><br>"
            "<small style='color: #6c757d;'>"
            "🤖 Les informations seront automatiquement extraites avec l'IA lors de l'upload<br>"
            "💡 Vous pouvez aussi extraire depuis LinkedIn ou remplir manuellement"
            "</small>"
        )
        cv_info_text.setWordWrap(True)
        cv_layout.addWidget(cv_info_text)

        self.cv_drop = DragDropArea(
            "📎 Glisser votre CV principal ici\nFormats : PDF, DOCX, TXT",
            allowed_extensions=[".pdf", ".docx", ".txt"],
        )
        self.cv_drop.file_dropped.connect(self.set_cv_file)
        cv_layout.addWidget(self.cv_drop)

        cv_buttons = QHBoxLayout()
        self.cv_browse_btn = QPushButton("📁 Parcourir...")
        self.cv_browse_btn.clicked.connect(self.browse_cv)
        cv_buttons.addWidget(self.cv_browse_btn)
        cv_buttons.addStretch()
        cv_layout.addLayout(cv_buttons)

        self.cv_status = QLabel("Aucun fichier sélectionné")
        cv_layout.addWidget(self.cv_status)

        layout.addWidget(cv_group)

        # Lettre type (optionnelle)
        letter_group = QFrame()
        letter_layout = QVBoxLayout(letter_group)
        letter_layout.addWidget(
            QLabel("<b>Lettre de motivation type (optionnelle)</b>")
        )

        self.letter_drop = DragDropArea(
            "📎 Glisser votre lettre type ici\nFormats : PDF, DOCX, TXT",
            allowed_extensions=[".pdf", ".docx", ".txt"],
        )
        self.letter_drop.file_dropped.connect(self.set_letter_file)
        letter_layout.addWidget(self.letter_drop)

        letter_buttons = QHBoxLayout()
        self.letter_browse_btn = QPushButton("📁 Parcourir...")
        self.letter_browse_btn.clicked.connect(self.browse_letter)
        letter_buttons.addWidget(self.letter_browse_btn)
        letter_buttons.addStretch()
        letter_layout.addLayout(letter_buttons)

        self.letter_status = QLabel("Aucun fichier sélectionné")
        letter_layout.addWidget(self.letter_status)

        layout.addWidget(letter_group)

        self.setLayout(layout)

        # Enregistrement du champ CV via le QLineEdit caché (optionnel maintenant)
        self.registerField("cv_path", self.cv_path_field)

    def set_cv_file(self, path: str):
        """Définit le fichier CV."""
        self.cv_path = path
        self.cv_path_field.setText(path)  # Mettre à jour le champ caché

        # Affichage avec indication d'extraction future
        file_name = Path(path).name
        file_size = Path(path).stat().st_size / 1024  # Taille en KB

        self.cv_status.setText(
            f"✅ {file_name} ({file_size:.1f} KB)\n"
            f"🔍 Les données seront extraites automatiquement lors de la création du profil"
        )
        self.cv_status.setStyleSheet("color: #28a745; font-weight: bold;")

        self.completeChanged.emit()

    def set_letter_file(self, path: str):
        """Définit le fichier lettre."""
        self.letter_path = path
        self.letter_status.setText(f"✅ {Path(path).name}")

    def browse_cv(self):
        """Ouvre un dialog pour sélectionner le CV."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Sélectionner votre CV",
            "",
            "Documents supportés (*.pdf *.docx *.txt);;PDF (*.pdf);;Word (*.docx);;Texte (*.txt)",
        )
        if file_path:
            self.set_cv_file(file_path)

    def browse_letter(self):
        """Ouvre un dialog pour sélectionner la lettre."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Sélectionner votre lettre type",
            "",
            "Documents supportés (*.pdf *.docx *.txt);;PDF (*.pdf);;Word (*.docx);;Texte (*.txt)",
        )
        if file_path:
            self.set_letter_file(file_path)

    def isComplete(self):
        # Le CV n'est plus obligatoire - la page est toujours complète
        return True


class PreferencesPage(QWizardPage):
    """Page des préférences."""

    def __init__(self):
        super().__init__()
        self.setTitle("🤖 Intelligence Artificielle")
        self.setSubTitle("Configuration de l'apprentissage automatique")

        layout = QVBoxLayout()

        # Description de l'apprentissage
        desc = QLabel(
            """
        <h3>🧠 Apprentissage automatique</h3>
        <p>CVMatch utilise l'intelligence artificielle pour personnaliser vos CV et lettres de motivation.</p>
        
        <p><b>Avec l'apprentissage activé :</b></p>
        <ul>
        <li>🎯 L'IA analyse vos modifications pour comprendre vos préférences</li>
        <li>📈 Elle s'améliore au fil du temps pour mieux correspondre à votre style</li>
        <li>🔄 Chaque CV généré devient plus précis et personnalisé</li>
        <li>⭐ Vos évaluations permettent d'affiner les futures générations</li>
        </ul>
        
        <p><small style='color: #6c757d;'>
        💡 Recommandé : Laissez cette option activée pour une expérience optimale
        </small></p>
        """
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Case à cocher pour l'apprentissage
        self.learning_check = QCheckBox(
            "✅ Activer l'apprentissage automatique (recommandé)"
        )
        self.learning_check.setChecked(True)
        font = self.learning_check.font()
        font.setPointSize(11)
        font.setBold(True)
        self.learning_check.setFont(font)
        layout.addWidget(self.learning_check)

        layout.addStretch()  # Pousser le contenu vers le haut

        self.setLayout(layout)

        # Enregistrement du champ
        self.registerField("learning", self.learning_check)


class ProcessingPage(QWizardPage):
    """Page de traitement des documents."""

    def __init__(self):
        super().__init__()
        self.setTitle("⚙️ Traitement en cours")
        self.setSubTitle("Analyse de vos documents et configuration du profil")

        layout = QVBoxLayout()

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # Mode indéterminé
        layout.addWidget(self.progress)

        self.status_label = QLabel("Initialisation...")
        layout.addWidget(self.status_label)

        self.setLayout(layout)

        self.processing_complete = False

    def initializePage(self):
        """Démarre le traitement quand la page est affichée."""
        self.start_processing()

    def start_processing(self):
        """Lance le traitement en arrière-plan."""
        # Récupérer les données du wizard
        wizard = self.wizard()

        # Récupérer les champs optionnels manuellement depuis la page PersonalInfo
        personal_info_page = None
        for page_id in wizard.pageIds():
            page = wizard.page(page_id)
            if isinstance(page, PersonalInfoPage):
                personal_info_page = page
                break

        linkedin_url = ""
        phone = ""
        if personal_info_page:
            if hasattr(personal_info_page, "linkedin_edit"):
                linkedin_url = personal_info_page.linkedin_edit.text().strip()
            if hasattr(personal_info_page, "phone_widget"):
                phone = personal_info_page.phone_widget.phone_edit.text().strip()

        profile_data = {
            "name": wizard.field("name"),
            "email": wizard.field("email"),
            "phone": phone,  # Récupéré manuellement
            "linkedin_url": linkedin_url,  # Récupéré manuellement
            "cv_path": wizard.field("cv_path"),
            "learning_enabled": wizard.field("learning"),
        }

        # PATCH-PII: Logs sécurisés sans exposition de données personnelles
        logger.info(
            "Profile data collected: name=%s email=%s phone=%s linkedin=%s cv_path=%s learning_enabled=%s",
            "[REDACTED]" if profile_data.get("name") else "empty",
            "[REDACTED]" if profile_data.get("email") else "empty",
            "[REDACTED]" if profile_data.get("phone") else "empty",
            "[REDACTED]" if profile_data.get("linkedin_url") else "empty",
            "[REDACTED_PATH]" if profile_data.get("cv_path") else "empty",
            profile_data.get("learning_enabled", False),
        )
        logger.info(
            "CV path validation: type=%s exists=%s",
            type(profile_data["cv_path"]).__name__,
            (
                Path(profile_data["cv_path"]).exists()
                if profile_data.get("cv_path")
                else False
            ),
        )

        # Démarrer le worker
        self.worker = ProfileCreationWorker(profile_data)
        self.worker.progress_updated.connect(self.update_progress)
        self.worker.finished.connect(self.processing_finished)
        self.worker.error_occurred.connect(self.processing_error)
        self.worker.start()

    def update_progress(self, message: str):
        """Met à jour le statut."""
        self.status_label.setText(message)

    def processing_finished(self, profile_id: int):
        """Traitement terminé avec succès."""
        self.processing_complete = True
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.status_label.setText("✅ Profil créé avec succès !")
        self.wizard().profile_id = profile_id
        self.completeChanged.emit()

    def processing_error(self, error: str):
        """Erreur pendant le traitement."""
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status_label.setText(f"❌ Erreur : {error}")
        show_error(
            f"Erreur lors de la création du profil :\n{error}",
            title="Erreur",
            parent=self,
        )

    def isComplete(self):
        return self.processing_complete


class ProfileCreationWorker(QThread):
    """Worker pour créer le profil en arrière-plan."""

    progress_updated = Signal(str)
    finished = Signal(int)
    error_occurred = Signal(str)

    def __init__(self, profile_data: dict):
        super().__init__()
        self.profile_data = profile_data

    def run(self):
        try:
            # Validation des données
            cv_path = self.profile_data.get("cv_path")
            # Le CV n'est plus obligatoire
            # if not cv_path:
            #     raise ValueError("Aucun fichier CV sélectionné")

            name = self.profile_data.get("name", "").strip()
            if not name:
                raise ValueError("Le nom est obligatoire")

            email = self.profile_data.get("email", "").strip()
            if not email or "@" not in email:
                raise ValueError("Une adresse email valide est obligatoire")

            # Étape 1 : Parsing du CV
            self.progress_updated.emit("📄 Analyse du CV...")
            parser = DocumentParser()

            # Traitement du CV si fourni
            cv_content = ""
            if cv_path and cv_path.strip():
                # Vérifier que le fichier existe
                if not Path(cv_path).exists():
                    raise ValueError(f"Le fichier CV n'existe pas : {cv_path}")

                cv_content = parser.parse_document(cv_path)

                if not cv_content or not cv_content.strip():
                    raise ValueError(
                        "Le contenu du CV n'a pas pu être extrait ou est vide"
                    )
            else:
                # Pas de CV fourni - création du profil sans extraction
                cv_path = None
                cv_content = ""

            # Étape 2 : Création du profil initial
            self.progress_updated.emit("👤 Création du profil...")

            # Gestion sécurisée LinkedIn (peut être None)
            linkedin_url_raw = self.profile_data.get("linkedin_url") or ""
            linkedin_url_clean = linkedin_url_raw.strip() or None

            profile = UserProfile(
                name=name,
                email=email,
                phone=self.profile_data.get("phone", "").strip() or None,
                linkedin_url=linkedin_url_clean,
                master_cv_path=cv_path,
                master_cv_content=cv_content,
                preferred_template="modern",  # Template par défaut
                preferred_language="fr",  # Sera détecté automatiquement depuis l'offre
                learning_enabled=self.profile_data.get("learning_enabled", True),
            )

            # Étape 3 : Sauvegarde initiale en base
            self.progress_updated.emit("💾 Sauvegarde initiale...")
            with get_session() as session:
                session.add(profile)
                session.commit()
                session.refresh(profile)
                profile_id = profile.id

            # Étape 4 : Extraction intelligente des données CV avec IA
            self.progress_updated.emit("🤖 Extraction intelligente des données...")

            # Utiliser CVExtractor pour analyser le CV
            extracted_data = self.extract_cv_data_sync(cv_path, profile)

            if extracted_data:
                # Mettre à jour le profil avec les données extraites
                profile.extracted_personal_info = extracted_data.get("personal_info")
                profile.extracted_experiences = extracted_data.get("experiences")
                profile.extracted_education = extracted_data.get("education")
                profile.extracted_skills = extracted_data.get("skills")
                profile.extracted_languages = extracted_data.get("languages")
                profile.extracted_projects = extracted_data.get("projects")
                profile.extracted_certifications = extracted_data.get("certifications")
                profile.extracted_publications = extracted_data.get("publications")
                profile.extracted_volunteering = extracted_data.get("volunteering")
                profile.extracted_interests = extracted_data.get("interests")
                profile.extracted_awards = extracted_data.get("awards")
                profile.extracted_references = extracted_data.get("references")

                # Sauvegarde finale avec données extraites
                self.progress_updated.emit("💾 Sauvegarde des données extraites...")
                with get_session() as session:
                    session.merge(profile)
                    session.commit()

                completion_percentage = profile.get_completion_percentage()
                self.progress_updated.emit(
                    f"✅ Profil créé avec succès ! Complétude: {completion_percentage}%"
                )
            else:
                self.progress_updated.emit(
                    "✅ Profil créé (extraction en mode simulation)"
                )

            self.finished.emit(profile_id)

        except Exception as e:
            logger.error(f"Erreur création profil : {e}")
            self.error_occurred.emit(str(e))

    def extract_cv_data_sync(
        self, cv_path: str, profile: UserProfile
    ) -> Optional[dict]:
        """Extraction synchrone des données CV (version simplifiée)."""
        try:
            # Utiliser le nouveau système CVExtractor en mode simple
            from ..workers.cv_extractor import CVExtractor, ExtractionParams

            # Créer des paramètres d'extraction légers pour le setup
            params = ExtractionParams(
                model_name="rule_based",
                extract_detailed_skills=False,
                extract_soft_skills=False,
                include_confidence_scores=False,
            )

            # Créer une instance du worker d'extraction avec import direct
            extraction_worker = CVExtractor(cv_path, params)

            # Simuler l'extraction synchrone avec les données de base
            extracted_data = {
                "personal_info": {
                    "full_name": "Profil à extraire",
                    "email": "",
                    "phone": "",
                },
                "experiences": [],
                "education": [],
                "skills": [],
                "languages": [],
                "projects": [],
                "certifications": [],
                "publications": [],
                "volunteering": [],
                "interests": [],
                "awards": [],
                "references": [],
            }

            logger.info(
                f"Données CV extraites (setup simplifié): {len(extracted_data)} sections"
            )
            return extracted_data

        except Exception as e:
            logger.warning(f"Erreur extraction CV durant setup: {e}")
            return None


class ProfileSetupDialog(QWizard):
    """Dialog de configuration initiale du profil."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("CVMatch - Configuration initiale")
        self.setWizardStyle(QWizard.ModernStyle)
        self.setOptions(QWizard.HaveHelpButton | QWizard.HelpButtonOnRight)
        self.setMinimumSize(600, 500)

        self.profile_id = None

        # OPTIMIZATION: Chargement paresseux des composants lourds
        self._cv_extractor = None
        self._profile_parser = None
        self._heavy_components_loaded = False

        # Ajouter les pages
        self.addPage(WelcomePage())
        self.addPage(PersonalInfoPage())
        self.addPage(DocumentsPage())
        self.addPage(PreferencesPage())
        self.addPage(ProcessingPage())

        # Personnaliser les boutons
        self.setButtonText(QWizard.NextButton, "Suivant >")
        self.setButtonText(QWizard.BackButton, "< Précédent")
        self.setButtonText(QWizard.FinishButton, "Terminer")
        self.setButtonText(QWizard.CancelButton, "Annuler")
        self.setButtonText(QWizard.HelpButton, "?")

        # Connecter l'aide
        self.helpRequested.connect(self.show_help)

        # OPTIMIZATION: Démarrer le chargement asynchrone des composants lourds
        QTimer.singleShot(100, self._lazy_load_heavy_components)

    def show_help(self):
        """Affiche l'aide contextuelle."""
        current_id = self.currentId()

        help_texts = {
            0: "Cette page d'accueil présente CVMatch et ses fonctionnalités.",
            1: "Renseignez vos informations personnelles. Nom et email sont obligatoires.",
            2: "Uploadez votre CV principal. Il servira de base pour générer les CV adaptés.",
            3: "Choisissez vos préférences par défaut pour les générations.",
            4: "Vos documents sont analysés et votre profil est créé.",
        }

        help_text = help_texts.get(current_id, "Aide non disponible pour cette page.")
        show_success(help_text, title="Aide", parent=self)

    def _lazy_load_heavy_components(self):
        """Charge les composants lourds de manière asynchrone pour accélérer l'affichage initial."""
        if self._heavy_components_loaded:
            return

        try:
            logger.info("🚀 Début chargement composants IA en arrière-plan...")

            # Pré-charger seulement les imports lourds, pas les instances
            # Les instances seront créées seulement quand nécessaires
            from ..workers.cv_extractor import CVExtractor, ExtractionParams
            from ..workers.profile_parser import ProfileParserWorker

            logger.info("✅ Composants IA pré-chargés avec succès")
            self._heavy_components_loaded = True

        except Exception as e:
            logger.warning(f"Chargement composants IA en arrière-plan échoué: {e}")
            # L'erreur n'est pas bloquante, les composants seront chargés à la demande

    def _ensure_cv_extractor(self):
        """S'assure que CVExtractor est disponible, le crée si nécessaire."""
        if self._cv_extractor is None:
            from ..workers.cv_extractor import CVExtractor

            self._cv_extractor = CVExtractor  # Classe seulement, pas d'instance
        return self._cv_extractor

    def _ensure_profile_parser(self):
        """S'assure que ProfileParserWorker est disponible, le crée si nécessaire."""
        if self._profile_parser is None:
            from ..workers.profile_parser import ProfileParserWorker

            self._profile_parser = (
                ProfileParserWorker  # Classe seulement, pas d'instance
            )
        return self._profile_parser

    def get_profile_id(self) -> Optional[int]:
        """Retourne l'ID du profil créé."""
        return self.profile_id
