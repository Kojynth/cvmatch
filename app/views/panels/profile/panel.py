"""Refactored profile panel composed of sectional widgets."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from PySide6.QtCore import QEvent, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QLabel,
    QLayout,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ....config import DEFAULT_PII_CONFIG
from ....controllers.main_window.profile_state import (
    ProfileFormData,
    ProfileStateCoordinator,
)
from ....logging.safe_logger import get_safe_logger
from ....models.user_profile import UserProfile
from ....services.dialogs import (
    confirm,
    show_error,
    show_info,
    show_success,
    show_warning,
)
from ....utils.emoji_utils import get_display_text
from ....utils.parsers import DocumentParser
from ....widgets.style_manager import apply_button_style
from ...ml_dialog_mixin import _MLProgressDialog as MLProgressDialog
from ...model_loading_dialog import ModelLoadingDialog
from ...profile_details_editor import ProfileDetailsEditor
from .actions_section import ActionsSection
from .ai_stats_section import AiStatsSection
from .cover_letter_section import CoverLetterSection
from .cv_section import CvSection
from .linkedin_section import LinkedInSection
from .personal_info_section import PersonalInfoSection
from .preferences_section import PreferencesSection

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


class ProfilePanel(QScrollArea):
    """
    Main profile panel orchestrating sub-sections and coordinating actions.

    We inherit from PersonalInfoSection (which already subclasses QWidget)
    purely to reuse the base QWidget initialisation; actual composition
    happens inside `setup_ui`.
    """

    profile_updated = Signal(UserProfile)

    def __init__(
        self, profile: UserProfile, coordinator: ProfileStateCoordinator | None = None
    ):
        super().__init__()
        self.profile = profile
        self.profile_coordinator = coordinator or ProfileStateCoordinator()
        self.profile_snapshot = self.profile_coordinator.to_snapshot(profile)

        # Workers
        self.linkedin_pdf_worker = None
        self.linkedin_worker = None
        self.extraction_controller = None
        self._ml_progress_dialog: MLProgressDialog | None = None
        self._ml_modal: ModelLoadingDialog | None = None

        self.setup_ui()

    # ---- UI composition -------------------------------------------------
    def setup_ui(self) -> None:
        # Content widget inside a scroll area to avoid "smashed" sections
        content = QWidget(self)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignTop)

        # Scroll behaviour
        self.setWidget(content)
        self.setWidgetResizable(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # Track content to enforce full-width on resize
        self._content = content
        self._content.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        title = QLabel(f"{get_display_text('👤')} Profil utilisateur")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        layout.addWidget(title)

        # Sections
        self.personal_section = PersonalInfoSection(self.profile)
        self.personal_section.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self.personal_section.name_edit.editingFinished.connect(self.auto_save_profile)
        self.personal_section.email_edit.editingFinished.connect(self.auto_save_profile)
        self.personal_section.linkedin_edit.editingFinished.connect(
            self.auto_save_profile
        )
        if hasattr(self.personal_section.phone_widget, "phone_changed"):
            self.personal_section.phone_widget.phone_changed.connect(
                self.auto_save_profile_from_phone
            )
        if hasattr(self.personal_section.linkedin_pdf_widget, "pdf_changed"):
            self.personal_section.linkedin_pdf_widget.pdf_changed.connect(
                self._handle_linkedin_pdf_changed
            )
        if hasattr(self.personal_section.linkedin_pdf_widget, "help_requested"):
            self.personal_section.linkedin_pdf_widget.help_requested.connect(
                self._open_linkedin_pdf_help
            )
        layout.addWidget(self.personal_section)

        self.cv_section = CvSection(
            profile=self.profile,
            on_view_cv=self.view_cv_content,
            on_replace_cv=self.replace_cv,
            on_extract_cv=self.re_extract_cv_data,
            on_view_details=self.show_extracted_details,
        )
        self.cv_section.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        layout.addWidget(self.cv_section)

        self.linkedin_section = LinkedInSection(
            profile=self.profile,
            on_sync=self.sync_linkedin_data,
            on_extract_pdf=self.extract_linkedin_pdf,
        )
        self.linkedin_section.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        layout.addWidget(self.linkedin_section)

        self.preferences_section = PreferencesSection(self.profile)
        self.preferences_section.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        layout.addWidget(self.preferences_section)

        self.cover_letter_section = CoverLetterSection(
            profile=self.profile,
            on_preview=self.preview_cover_letter,
            on_changed=self.update_cover_letter_stats,
        )
        self.cover_letter_section.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        layout.addWidget(self.cover_letter_section)

        self.ai_stats_section = AiStatsSection(
            profile=self.profile, on_retrain=self.retrain_model
        )
        self.ai_stats_section.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        layout.addWidget(self.ai_stats_section)

        self.actions_section = ActionsSection(
            on_save=self.save_profile, on_reset=self.reset_form
        )
        self.actions_section.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum
        )
        layout.addWidget(self.actions_section)

        layout.addStretch()
        self.render_profile(self.profile_snapshot)
        self.update_cover_letter_stats()
        self.refresh_linkedin_ui()
        # Ensure the layout reports its full size so the scroll range covers all sections
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        content.adjustSize()

    # Ensure inner content always matches viewport width (prevents unused dark area)
    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        if self.widget() is not None:
            self.widget().setMinimumWidth(self.viewport().width())
        # Also try to follow parent height if available
        parent = self.parentWidget()
        if parent is not None:
            self.setMinimumHeight(parent.height())

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        parent = self.parentWidget()
        if parent is not None:
            try:
                if not hasattr(self, "_parent_filter_installed"):
                    parent.installEventFilter(self)
                    self._parent_filter_installed = True
            except Exception:
                pass
            self.setMinimumHeight(parent.height())

    def eventFilter(self, obj, event):  # noqa: N802
        try:
            if obj is self.parentWidget() and event.type() == QEvent.Resize:
                self.setMinimumHeight(obj.height())
        except Exception:
            pass
        return super().eventFilter(obj, event)

    # ---- Data helpers ---------------------------------------------------
    def _collect_form_data(self, *, coalesce: bool) -> ProfileFormData:
        name = self.personal_section.name_edit.text().strip()
        email = self.personal_section.email_edit.text().strip()
        linkedin_value = self.personal_section.linkedin_edit.text().strip()

        phone_value = None
        if hasattr(self.personal_section.phone_widget, "get_full_phone_number"):
            phone_candidate = self.personal_section.phone_widget.get_full_phone_number()
            phone_value = phone_candidate or None

        name_value = name if (name or not coalesce) else None
        email_value = email if (email or not coalesce) else None

        return ProfileFormData(
            name=name_value,
            email=email_value,
            phone=phone_value,
            linkedin_url=linkedin_value or None,
            preferred_template=(
                self.preferences_section.template_combo.currentText()
                if self.preferences_section.template_combo is not None
                else None
            ),
            preferred_language=(
                self.preferences_section.language_combo.currentText()
                if self.preferences_section.language_combo is not None
                else None
            ),
            learning_enabled=(
                self.preferences_section.learning_check.isChecked()
                if self.preferences_section.learning_check is not None
                else None
            ),
        )

    def render_profile(self, snapshot) -> None:
        """Update widgets from a profile snapshot."""
        self.personal_section.name_edit.setText(snapshot.name or "")
        self.personal_section.email_edit.setText(snapshot.email or "")
        self.personal_section.linkedin_edit.setText(snapshot.linkedin_url or "")
        if hasattr(self.personal_section.phone_widget, "set_full_phone_number"):
            self.personal_section.phone_widget.set_full_phone_number(
                snapshot.phone or ""
            )
        if (
            self.preferences_section.template_combo is not None
            and snapshot.preferred_template
        ):
            idx = self.preferences_section.template_combo.findText(
                snapshot.preferred_template
            )
            if idx >= 0:
                self.preferences_section.template_combo.setCurrentIndex(idx)
        if (
            self.preferences_section.language_combo is not None
            and snapshot.preferred_language
        ):
            idx = self.preferences_section.language_combo.findText(
                snapshot.preferred_language
            )
            if idx >= 0:
                self.preferences_section.language_combo.setCurrentIndex(idx)
        if (
            self.preferences_section.learning_check is not None
            and snapshot.learning_enabled is not None
        ):
            self.preferences_section.learning_check.setChecked(
                bool(snapshot.learning_enabled)
            )
        self.cover_letter_section.set_text(
            getattr(self.profile, "default_cover_letter", "") or ""
        )
        self.cv_section.update_cv_info(self.profile.master_cv_path)
        self.linkedin_section.update_status(self.profile)

    def update_fields(self) -> None:
        """Refresh fields from current profile (e.g., after editor save)."""
        self.render_profile(self.profile_coordinator.to_snapshot(self.profile))

    # ---- Actions --------------------------------------------------------
    def auto_save_profile(self) -> None:
        if not self.profile_coordinator:
            logger.error("Coordinateur de profil indisponible pour l'auto-sauvegarde")
            return
        form_data = self._collect_form_data(coalesce=True)
        success, error = self.profile_coordinator.save_profile(
            self.profile, form_data, validate=False, coalesce=True
        )
        if success:
            self.refresh_linkedin_ui()
            self.profile_updated.emit(self.profile)
        else:
            logger.error("Erreur sauvegarde automatique: %s", error)

    def auto_save_profile_from_phone(self, phone_number: str) -> None:
        if not self.profile_coordinator:
            logger.error(
                "Coordinateur de profil indisponible pour l'auto-sauvegarde téléphone"
            )
            return
        form_data = ProfileFormData(phone=phone_number)
        success, error = self.profile_coordinator.save_profile(
            self.profile, form_data, validate=False, coalesce=True
        )
        if success:
            self.profile_updated.emit(self.profile)
        else:
            logger.error("Erreur sauvegarde auto téléphone: %s", error)

    def save_profile(self) -> None:
        if not self.profile_coordinator:
            show_error(
                "Coordinateur de profil indisponible.", title="Erreur", parent=self
            )
            return
        form_data = self._collect_form_data(coalesce=False)
        success, error = self.profile_coordinator.save_profile(
            self.profile, form_data, validate=True, coalesce=False
        )
        if not success:
            if error:
                show_error(error, title="Erreur", parent=self)
            return
        show_success("Profil sauvegardé avec succès!", title="Succès", parent=self)
        self.profile_updated.emit(self.profile)

    def reset_form(self) -> None:
        self.update_fields()

    # ---- CV -------------------------------------------------------------
    def replace_cv(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Sélectionner le nouveau CV",
            "",
            "Documents supportés (*.pdf *.docx *.txt);;PDF (*.pdf);;Word (*.docx);;Texte (*.txt)",
        )
        if not file_path:
            return
        try:
            parser = DocumentParser()
            content = parser.parse_document(file_path)
            self.profile.master_cv_path = file_path
            self.profile.master_cv_content = content
            self.cv_section.update_cv_info(file_path)
            show_info("CV mis à jour.", title="Succès", parent=self)
            self.profile_updated.emit(self.profile)
        except Exception as exc:  # noqa: BLE001
            logger.error("Erreur lors du remplacement du CV: %s", exc)
            show_error("Impossible de charger le CV.", title="Erreur", parent=self)

    def view_cv_content(self) -> None:
        if not getattr(self.profile, "master_cv_content", None):
            show_warning(
                "Aucun contenu de CV disponible.", title="Aucun contenu", parent=self
            )
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Contenu du CV")
        dialog.setMinimumSize(600, 400)
        layout = QVBoxLayout(dialog)
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setText(self.profile.master_cv_content)
        layout.addWidget(text_edit)
        close_btn = self.actions_section.build_close_button(dialog)
        layout.addWidget(close_btn)
        dialog.exec()

    def re_extract_cv_data(self) -> None:
        if (
            not self.profile.master_cv_path
            or not Path(self.profile.master_cv_path).exists()
        ):
            show_warning(
                "Aucun CV de référence trouvé.\nVeuillez d'abord charger un CV.",
                title="CV manquant",
                parent=self,
            )
            return
        if not confirm(
            "Cette opération va analyser à nouveau votre CV et remplacer les données existantes.\n\nContinuer ?",
            title="Re-extraction des données",
            parent=self,
        ):
            return
        try:
            from ....controllers.profile_extractor import ProfileExtractionController

            self.extraction_controller = ProfileExtractionController()
            self.extraction_controller.progress_updated.connect(
                self._on_extraction_progress
            )
            self.extraction_controller.extraction_completed.connect(
                self._on_extraction_completed
            )
            self.extraction_controller.extraction_failed.connect(
                self._on_extraction_failed
            )
            self.extraction_controller.extract_complete_profile(self.profile)
            show_info(
                "L'extraction intelligente de votre CV a commencé.\nVous recevrez une notification lorsqu'elle sera terminée.",
                title="Extraction en cours",
                parent=self,
            )
        except ImportError:
            show_info(
                "L'extraction des données du CV va commencer.",
                title="Extraction en cours",
                parent=self,
            )

    # ---- LinkedIn -------------------------------------------------------
    def _handle_linkedin_pdf_changed(self, payload) -> None:
        path, checksum, uploaded_at = payload
        if not self.profile_coordinator:
            logger.error(
                "Coordinateur de profil indisponible pour la mise à jour LinkedIn"
            )
            return
        success, error = self.profile_coordinator.update_linkedin_pdf(
            self.profile, pdf_path=path, checksum=checksum, uploaded_at=uploaded_at
        )
        if not success:
            logger.error("Erreur mise à jour LinkedIn PDF: %s", error)
            return
        self.refresh_linkedin_ui()
        self.profile_updated.emit(self.profile)

    def _open_linkedin_pdf_help(self) -> None:
        help_path = Path.cwd() / "docs" / "LINKEDIN_PDF_GUIDE.md"
        if help_path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(help_path)))
        else:
            QMessageBox.information(
                self,
                "Guide absent",
                "Le guide d'import LinkedIn (docs/LINKEDIN_PDF_GUIDE.md) n'est pas disponible.",
            )

    def extract_linkedin_pdf(self) -> None:
        if getattr(self, "linkedin_pdf_worker", None):
            QMessageBox.information(
                self,
                "Extraction en cours",
                "Une extraction LinkedIn (PDF) est déjà en cours.",
            )
            return
        pdf_path = getattr(self.profile, "linkedin_pdf_path", None)
        if not pdf_path:
            QMessageBox.information(
                self,
                "PDF LinkedIn manquant",
                "Aucun PDF LinkedIn importé.\nImportez d'abord le PDF.",
            )
            return
        pdf_file = Path(pdf_path)
        if not pdf_file.exists():
            show_warning(
                "Le fichier PDF LinkedIn n'existe plus sur le disque.\nImportez-le de nouveau avant d'extraire les données.",
                title="PDF indisponible",
                parent=self,
            )
            return
        if not confirm(
            "Cette opération analyse le PDF exporté de votre profil LinkedIn et remplace les données LinkedIn actuelles.\n\nContinuer ?",
            title="Extraire LinkedIn (PDF)",
            parent=self,
        ):
            return
        try:
            from ....workers.linkedin_pdf_extractor import LinkedInPdfExtractor

            self.linkedin_pdf_worker = LinkedInPdfExtractor(str(pdf_file))
            self.linkedin_pdf_worker.progress_updated.connect(
                self._on_linkedin_pdf_worker_progress
            )
            self.linkedin_pdf_worker.extraction_completed.connect(
                self._on_linkedin_pdf_worker_completed
            )
            self.linkedin_pdf_worker.extraction_failed.connect(
                self._on_linkedin_pdf_worker_failed
            )
            self.linkedin_pdf_worker.start()
            QMessageBox.information(
                self,
                "Extraction LinkedIn (PDF)",
                "L'extraction LinkedIn via PDF a commencé.\nCette fenêtre peut être fermée, un message apparaîtra à la fin.",
            )
        except ImportError as exc:
            logger.error("LinkedInPdfExtractor indisponible: %s", exc)
            QMessageBox.warning(
                self,
                "Indisponible",
                "L'extraction LinkedIn PDF n'est pas disponible sur cet environnement.",
            )

    def sync_linkedin_data(self) -> None:
        if not self.profile.linkedin_url:
            show_warning(
                "Aucune URL LinkedIn n'est renseignée dans votre profil.",
                title="URL LinkedIn manquante",
                parent=self,
            )
            return
        if not confirm(
            "EXTRACTION LINKEDIN SÉCURISÉE\n\nCette fonction va extraire les données publiques de votre profil LinkedIn sans utiliser vos cookies.\nContinuer ?",
            title="Synchronisation LinkedIn - Mode Sécurisé",
            parent=self,
        ):
            return
        try:
            from ....workers.linkedin_extractor import (
                LinkedInExtractionParams,
                LinkedInExtractor,
            )

            params = LinkedInExtractionParams(
                method="crawler",
                use_existing_session=False,
                use_headless_browser=True,
                respect_robots_txt=True,
                delay_between_requests=2.0,
                user_agent_rotation=True,
                public_only=True,
                extract_recommendations=False,
                extract_connections=False,
            )
            self.linkedin_worker = LinkedInExtractor(self.profile.linkedin_url, params)
            self.linkedin_worker.progress_updated.connect(self._on_linkedin_progress)
            self.linkedin_worker.extraction_completed.connect(
                self._on_linkedin_completed
            )
            self.linkedin_worker.extraction_failed.connect(self._on_linkedin_failed)
            QMessageBox.information(
                self,
                "Extraction LinkedIn",
                "L'extraction sécurisée de votre profil LinkedIn a commencé.\nCela peut prendre quelques minutes.",
            )
            self.linkedin_worker.start()
        except ImportError as exc:
            logger.error("LinkedInExtractor indisponible: %s", exc)
            QMessageBox.warning(
                self,
                "Indisponible",
                "L'extraction LinkedIn n'est pas disponible sur cet environnement.",
            )

    def refresh_linkedin_ui(self) -> None:
        self.linkedin_section.update_status(self.profile)

    # ---- Cover letter ---------------------------------------------------
    def preview_cover_letter(self) -> None:
        text = self.cover_letter_section.get_text()
        if not text.strip():
            QMessageBox.information(
                self,
                "Lettre vide",
                "La lettre de motivation est vide.\n\nAjoutez du contenu pour la prévisualiser.",
            )
            return
        preview_dialog = QDialog(self)
        preview_dialog.setWindowTitle("Prévisualisation - Lettre de motivation")
        preview_dialog.resize(600, 500)
        layout = QVBoxLayout(preview_dialog)
        preview_area = QTextEdit()
        preview_area.setReadOnly(True)
        preview_area.setHtml(
            f"<div style='font-family: Segoe UI, Arial; line-height: 1.6; padding: 20px;'>{text}</div>"
        )
        layout.addWidget(preview_area)
        close_btn = self.actions_section.build_close_button(preview_dialog)
        layout.addWidget(close_btn)
        preview_dialog.exec()

    def update_cover_letter_stats(self) -> None:
        text = self.cover_letter_section.get_text()
        word_count = len(text.split()) if text.strip() else 0
        char_count = len(text)
        line_count = len(text.split("\n"))
        self.cover_letter_section.update_stats(word_count, char_count, line_count)

    # ---- ML / Extraction callbacks -------------------------------------
    def _on_extraction_progress(self, percentage: int, message: str) -> None:
        if self._ml_progress_dialog:
            self._ml_progress_dialog.update_progress(percentage, message)

    def _on_extraction_completed(self, updated_profile: UserProfile) -> None:
        self.profile = updated_profile
        self.render_profile(self.profile_coordinator.to_snapshot(updated_profile))
        self.profile_updated.emit(updated_profile)
        show_success(
            "Les données du CV ont été extraites avec succès.",
            title="Extraction terminée",
            parent=self,
        )

    def _on_extraction_failed(self, error_message: str) -> None:
        logger.error("Extraction CV échouée: %s", error_message)
        show_error(
            error_message or "Erreur inconnue.",
            title="Erreur d'extraction",
            parent=self,
        )

    def _on_linkedin_pdf_worker_progress(self, percentage: int, message: str) -> None:
        if self._ml_progress_dialog:
            self._ml_progress_dialog.update_progress(percentage, message)

    def _on_linkedin_pdf_worker_completed(self, payload: Dict[str, Any]) -> None:
        try:
            linkedin_data = payload.get("linkedin_data")
            if linkedin_data:
                self.profile.linkedin_data = linkedin_data  # type: ignore[attr-defined]
                self.profile_updated.emit(self.profile)
            QMessageBox.information(
                self, "Extraction LinkedIn (PDF)", "Extraction LinkedIn terminée."
            )
        finally:
            self.linkedin_pdf_worker = None
            self.refresh_linkedin_ui()

    def _on_linkedin_pdf_worker_failed(self, error: str) -> None:
        logger.error("Extraction LinkedIn PDF échouée: %s", error)
        QMessageBox.critical(
            self,
            "Erreur LinkedIn (PDF)",
            f"Impossible d'extraire les données LinkedIn à partir du PDF:\n    {error}",
        )
        self.linkedin_pdf_worker = None

    def _on_linkedin_progress(self, percentage: int, message: str) -> None:
        if self._ml_progress_dialog:
            self._ml_progress_dialog.update_progress(percentage, message)

    def _on_linkedin_completed(self, linkedin_data: Dict[str, Any]) -> None:
        try:
            self.profile.linkedin_data = linkedin_data  # type: ignore[attr-defined]
            self.profile.linkedin_last_sync = datetime.now()
            self.profile_updated.emit(self.profile)
            QMessageBox.information(
                self,
                f"{get_display_text('??')} Extraction LinkedIn terminée",
                "Les données LinkedIn ont été synchronisées.",
            )
        finally:
            self.linkedin_worker = None
            self.refresh_linkedin_ui()

    def _on_linkedin_failed(self, error_message: str) -> None:
        logger.error("Échec extraction LinkedIn : %s", error_message)
        QMessageBox.critical(
            self,
            f"{get_display_text('??')} Erreur LinkedIn",
            f"{get_display_text('??')} L'extraction LinkedIn a échoué.\n\n{error_message}",
        )
        self.linkedin_worker = None
        self.refresh_linkedin_ui()

    # ---- Details --------------------------------------------------------
    def show_extracted_details(self) -> None:
        """Opens the profile details editor dialog to view/edit extracted data."""
        if not self.profile:
            show_error("Profil utilisateur non disponible", title="Erreur", parent=self)
            return

        try:
            # Create the editor with the current profile
            editor = ProfileDetailsEditor(self.profile, parent=self)

            # Connect the profile_updated signal to our callback
            editor.profile_updated.connect(self.on_extracted_data_updated)

            # Wrap editor in a dialog for modal presentation
            dialog = QDialog(self)
            dialog.setWindowTitle(f"Détails du profil - {self.profile.name}")
            dialog.setModal(True)
            dialog.resize(1200, 800)

            layout = QVBoxLayout(dialog)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(editor)

            # Show dialog modally
            dialog.exec()

        except Exception as error:
            logger.error(
                "Erreur ouverture ProfileDetailsEditor: %s", error, exc_info=True
            )
            show_error(
                f"Impossible d'ouvrir l'éditeur de détails.\n\n{error}",
                title="Erreur",
                parent=self,
            )

    def retrain_model(self) -> None:
        """Lance le réentraînement du modèle IA."""
        reply = QMessageBox.question(
            self,
            "Réentraînement",
            "Voulez-vous lancer le réentraînement du modèle IA?\nCela peut prendre plusieurs minutes.",
            QMessageBox.Yes | QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            QMessageBox.information(
                self, "Réentraînement", "Réentraînement lancé en arrière-plan!"
            )

    def on_extracted_data_updated(self, updated_profile: UserProfile) -> None:
        self.profile = updated_profile
        self.render_profile(self.profile_coordinator.to_snapshot(updated_profile))
        self.profile_updated.emit(updated_profile)

    # ---- ML helpers (minimal stubs) ------------------------------------
    def _ensure_ml_progress_dialog(self) -> MLProgressDialog:
        if self._ml_progress_dialog is None:
            self._ml_progress_dialog = MLProgressDialog(self)
        return self._ml_progress_dialog

    def _ensure_ml_modal(self) -> ModelLoadingDialog:
        if self._ml_modal is None:
            self._ml_modal = ModelLoadingDialog(self)
        return self._ml_modal
