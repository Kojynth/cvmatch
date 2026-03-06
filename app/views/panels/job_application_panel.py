"""Job application panel extracted from main window."""

from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...config import DEFAULT_PII_CONFIG
from ...controllers.main_window.job_applications import JobApplicationCoordinator
from ...controllers.main_window.view_models import ProfileSnapshot
from ...logging.safe_logger import get_safe_logger
from ...models.job_application import ApplicationStatus
from ...models.user_profile import UserProfile
from ...services.dialogs import show_error, show_info, show_success, show_warning
from ...utils.emoji_utils import get_display_text
from ...utils.parsers import DocumentParser
from ...widgets.text_only_edit import TextOnlyEdit
from ..profile_setup import DragDropArea
from ..generation_loading_dialog import GenerationLoadingDialog

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)

TemplatePreviewWindow = None  # type: ignore[assignment]
_TEMPLATE_PREVIEW_IMPORT_ERROR: Exception | None = None


def _load_template_preview_window_class():
    """Lazy-load preview window to avoid QtWebEngine startup overhead."""
    global TemplatePreviewWindow, _TEMPLATE_PREVIEW_IMPORT_ERROR
    if TemplatePreviewWindow is not None:
        return TemplatePreviewWindow
    if _TEMPLATE_PREVIEW_IMPORT_ERROR is not None:
        return None
    try:  # pragma: no cover - optional dependency in some environments
        from ..template_preview_window import TemplatePreviewWindow as _TemplatePreviewWindow

        TemplatePreviewWindow = _TemplatePreviewWindow
        return TemplatePreviewWindow
    except Exception as exc:  # pragma: no cover
        _TEMPLATE_PREVIEW_IMPORT_ERROR = exc
        logger.warning(f"Template Preview Window non disponible: {exc}")
        return None

__all__ = ["JobApplicationPanel"]


class JobApplicationPanel(QWidget):
    """Panel pour gérer la création de candidature."""

    def __init__(
        self,
        profile: UserProfile,
        parent: QWidget | None = None,
        coordinator: JobApplicationCoordinator | None = None,
    ):
        super().__init__(parent)
        self.profile = profile
        self.profile_snapshot: ProfileSnapshot | None = None
        self.main_window = parent
        self.coordinator = coordinator or JobApplicationCoordinator(profile)
        self.coordinator.bind_profile(profile)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()

        # Titre
        title = QLabel(f"{get_display_text('📄')} Nouvelle candidature")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        layout.addWidget(title)

        # Recréer les widgets ici pour éviter l'import circulaire
        # Widget d'offre d'emploi
        self.offer_widget = self.create_offer_widget()
        layout.addWidget(self.offer_widget)

        # Widget de génération
        self.generation_widget = self.create_generation_widget()
        layout.addWidget(self.generation_widget)

        # Les connexions sont gérées dans les méthodes de création

        layout.addStretch()
        self.setLayout(layout)
        # Utilise les couleurs par défaut du système (pas de setStyleSheet)

    def apply_profile_snapshot(self, snapshot: ProfileSnapshot) -> None:
        """Update derived stats from a profile snapshot."""
        self.profile_snapshot = snapshot
        total_generated = (
            snapshot.metadata.get("total_cvs_generated") if snapshot.metadata else None
        )
        total_generated = (
            total_generated
            if total_generated is not None
            else getattr(self.profile, "total_cvs_generated", 0)
        )
        widget = getattr(self, "generation_widget", None)
        if widget is not None and hasattr(widget, "stats_label"):
            widget.stats_label.setText(f"CV générés : {total_generated}")

    def create_offer_widget(self):
        """Crée le widget d'offre d'emploi."""
        widget = QFrame()
        widget.setFrameStyle(QFrame.Box | QFrame.Raised)
        layout = QVBoxLayout(widget)

        # Zone de drop
        drop_area = DragDropArea(
            f"{get_display_text('📄')} Glisser l'offre d'emploi ici\nFormats : PDF, DOCX, TXT, Copier-coller",
            allowed_extensions=[".pdf", ".docx", ".txt"],
        )
        layout.addWidget(drop_area)

        # Boutons
        buttons_layout = QHBoxLayout()

        browse_btn = QPushButton(f"{get_display_text('📁')} Parcourir...")
        browse_btn.clicked.connect(lambda: self.browse_offer(widget))
        buttons_layout.addWidget(browse_btn)

        paste_btn = QPushButton(f"{get_display_text('📋')} Coller texte")
        paste_btn.clicked.connect(lambda: self.paste_offer(widget))
        buttons_layout.addWidget(paste_btn)

        buttons_layout.addStretch()
        layout.addLayout(buttons_layout)

        # Zone de texte pour édition
        text_edit = TextOnlyEdit()
        text_edit.setPlaceholderText("Le texte de l'offre apparaîtra ici...")
        text_edit.setMaximumHeight(150)
        layout.addWidget(text_edit)

        # Informations de l'offre
        info_layout = QGridLayout()

        info_layout.addWidget(QLabel("Titre du poste:"), 0, 0)
        job_title_edit = QLineEdit()
        info_layout.addWidget(job_title_edit, 0, 1)

        info_layout.addWidget(QLabel("Entreprise:"), 1, 0)
        company_edit = QLineEdit()
        info_layout.addWidget(company_edit, 1, 1)

        layout.addLayout(info_layout)

        # Stocker les références
        widget.drop_area = drop_area
        widget.text_edit = text_edit
        widget.job_title_edit = job_title_edit
        widget.company_edit = company_edit
        widget.offer_data = None

        # Pas besoin de signal ici, on utilise des méthodes directes

        # Connexions
        drop_area.file_dropped.connect(lambda path: self.load_offer_file(widget, path))
        text_edit.textChanged.connect(lambda: self.analyze_offer(widget))
        job_title_edit.editingFinished.connect(lambda: self.analyze_offer(widget))
        company_edit.editingFinished.connect(lambda: self.analyze_offer(widget))

        return widget

    def create_generation_widget(self):
        """Create the CV generation widget wired to the worker pipeline."""
        widget = QFrame()
        layout = QVBoxLayout(widget)

        header_layout = QHBoxLayout()
        title = QLabel(self.profile.name or "Profil")
        title.setFont(QFont("Arial", 12, QFont.Bold))
        header_layout.addWidget(title)

        stats_label = QLabel(f"CV générés : {self.profile.total_cvs_generated}")
        header_layout.addWidget(stats_label)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        style_layout = QHBoxLayout()
        style_layout.addWidget(QLabel("Style :"))

        template_combo = QComboBox()
        template_combo.addItems(["modern", "classic", "tech", "creative"])
        template_combo.setCurrentText(self.profile.preferred_template)
        style_layout.addWidget(template_combo)
        style_layout.addStretch()
        layout.addLayout(style_layout)

        try:
            from ...utils.universal_gpu_adapter import universal_gpu_adapter

            gpu_info = universal_gpu_adapter.gpu_info
            performance_profile = universal_gpu_adapter.performance_profile

            gpu_layout = QHBoxLayout()
            gpu_label = QLabel(
                f"GPU : {gpu_info['name']} ({gpu_info['vram_gb']:.1f} GB)"
            )
            gpu_label.setStyleSheet("font-weight: bold; color: #0078d4;")
            gpu_layout.addWidget(gpu_label)

            tier = performance_profile.get("tier", "unknown").replace("_", " ").title()
            perf_label = QLabel(f"Profil : {tier}")
            perf_label.setStyleSheet("color: #555; font-size: 11px;")
            gpu_layout.addWidget(perf_label)

            eta = performance_profile.get("estimated_time_minutes")
            if eta:
                time_label = QLabel(f"Temps estimé ~{eta} min")
                time_label.setStyleSheet("color: #777; font-size: 11px;")
                gpu_layout.addWidget(time_label)

            gpu_layout.addStretch()
            layout.addLayout(gpu_layout)
        except Exception:
            pass

        ai_suggestion = QLabel(
            "Chargez une offre pour obtenir une suggestion de template."
        )
        ai_suggestion.setStyleSheet("color: #0078d4; font-style: italic;")
        layout.addWidget(ai_suggestion)

        try:
            from ...widgets.model_selector import CompactModelSelector

            model_selector = CompactModelSelector()
            model_selector.model_changed.connect(self.on_model_changed)
            layout.addWidget(model_selector)
        except Exception as exc:
            logger.warning(f"Model selector unavailable: {exc}")
            model_selector = None

        generate_btn = QPushButton("Générer le CV adapté")

        generate_btn.setEnabled(False)

        generate_btn.setStyleSheet("padding: 12px 24px; font-weight: bold;")

        generate_letter_btn = QPushButton("Générer la lettre de motivation")

        generate_letter_btn.setEnabled(False)

        generate_letter_btn.setStyleSheet("padding: 12px 24px; font-weight: bold;")

        buttons_row = QHBoxLayout()

        buttons_row.addWidget(generate_btn)

        buttons_row.addWidget(generate_letter_btn)

        buttons_row.addStretch()

        layout.addLayout(buttons_row)

        progress_label = QLabel("")
        progress_label.setStyleSheet(
            "color: #0078d4; font-weight: bold; margin: 10px 0;"
        )
        progress_label.hide()
        layout.addWidget(progress_label)

        widget.template_combo = template_combo

        widget.ai_suggestion = ai_suggestion

        widget.generate_btn = generate_btn

        widget.generate_letter_btn = generate_letter_btn

        widget.progress_label = progress_label

        widget.stats_label = stats_label

        widget.model_selector = model_selector

        widget.offer_data = None

        widget.generated_cv_data = None

        widget.generated_cover_letter = None

        widget.generated_result = None

        widget.generated_application_id = None

        widget.current_worker = None

        widget.current_letter_worker = None

        widget.generation_dialog = None

        widget.current_template = template_combo.currentText()

        template_combo.currentTextChanged.connect(
            lambda value: setattr(widget, "current_template", value)
        )

        generate_btn.clicked.connect(lambda: self.start_generation(widget))

        generate_letter_btn.clicked.connect(
            lambda: self.start_cover_letter_generation(widget)
        )

        return widget

    def _show_generation_dialog(self, widget, initial_status: str) -> None:
        dialog = getattr(widget, "generation_dialog", None)
        if dialog is None:
            dialog = GenerationLoadingDialog(parent=self)
            widget.generation_dialog = dialog
        try:
            dialog.cancel_requested.disconnect()
        except Exception:
            pass
        dialog.cancel_requested.connect(lambda: self._cancel_active_generation(widget))
        dialog.set_cancel_enabled(True)
        dialog.set_status(initial_status)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _update_generation_dialog(self, widget, status: str) -> None:
        dialog = getattr(widget, "generation_dialog", None)
        if dialog is None:
            return
        dialog.set_status(status)

    def _hide_generation_dialog(self, widget) -> None:
        dialog = getattr(widget, "generation_dialog", None)
        if dialog is None:
            return
        try:
            dialog.hide()
            dialog.deleteLater()
        except Exception:
            pass
        widget.generation_dialog = None

    def _cancel_active_generation(self, widget) -> None:
        """Allow users to stop a running generation manually."""
        worker = getattr(widget, "current_worker", None)
        worker_kind = "cv"
        if worker is None:
            worker = getattr(widget, "current_letter_worker", None)
            worker_kind = "letter"
        if worker is None:
            self._hide_generation_dialog(widget)
            return

        dialog = getattr(widget, "generation_dialog", None)
        if dialog is not None:
            dialog.set_status("Annulation demandee")
            dialog.set_cancel_enabled(False, "Annulation en cours...")

        for method_name in ("requestInterruption", "cancel", "stop"):
            if hasattr(worker, method_name):
                try:
                    getattr(worker, method_name)()
                except Exception:
                    continue

        try:
            if hasattr(worker, "isRunning") and worker.isRunning():
                worker.terminate()
                worker.wait(2000)
        except Exception as exc:
            logger.warning(f"Annulation worker impossible ({worker_kind}): {exc}")

        try:
            if hasattr(worker, "qwen_manager") and hasattr(worker.qwen_manager, "cleanup_memory"):
                worker.qwen_manager.cleanup_memory()
        except Exception:
            pass

        try:
            self.coordinator.release_worker(worker)
        except Exception:
            pass

        if worker_kind == "cv":
            widget.current_worker = None
            widget.generate_btn.setEnabled(True)
            widget.generate_btn.setText("GÃ©nÃ©rer le CV adaptÃ©")
            if hasattr(widget, "generate_letter_btn") and getattr(widget, "current_letter_worker", None) is None:
                widget.generate_letter_btn.setEnabled(True)
                widget.generate_letter_btn.setText("GÃ©nÃ©rer la lettre de motivation")
        else:
            widget.current_letter_worker = None
            widget.generate_letter_btn.setEnabled(True)
            widget.generate_letter_btn.setText("GÃ©nÃ©rer la lettre de motivation")
            if getattr(widget, "current_worker", None) is None:
                widget.generate_btn.setEnabled(True)

        widget.progress_label.hide()
        widget._preview_regen_in_progress = False
        self._hide_generation_dialog(widget)
        show_info(
            "GÃ©nÃ©ration arrÃªtÃ©e Ã  la demande de l'utilisateur.",
            title="GÃ©nÃ©ration annulÃ©e",
            parent=self,
        )

    def browse_offer(self, widget):
        """Ouvre un dialog pour sélectionner l'offre."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Sélectionner l'offre d'emploi",
            "",
            "Documents supportés (*.pdf *.docx *.txt);;PDF (*.pdf);;Word (*.docx);;Texte (*.txt)",
        )
        if file_path:
            self.load_offer_file(widget, file_path)

    def paste_offer(self, widget):
        """Colle le texte du presse-papier."""
        from PySide6.QtWidgets import QApplication

        clipboard = QApplication.clipboard()
        text = clipboard.text()
        if text:
            widget.text_edit.setText(text)

    def load_offer_file(self, widget, file_path: str):
        """Charge une offre depuis un fichier."""
        try:
            parser = DocumentParser()
            content = parser.parse_document(file_path)
            widget.text_edit.setText(content)

            # Extraire titre basique
            lines = content.split("\n")
            if lines:
                for line in lines[:5]:
                    if line.strip():
                        widget.job_title_edit.setText(line.strip())
                        break

        except Exception as e:
            show_warning(
                f"Impossible de lire le fichier:\n{e}", title="Erreur", parent=self
            )

    def analyze_offer(self, widget):
        """Analyse the job offer text and prepare metadata for generation."""
        text = widget.text_edit.toPlainText()
        if not text or len(text.strip()) < 50:

            widget.offer_data = None

            self.set_offer_data_to_generation(None)

            return

        job_title = widget.job_title_edit.text().strip()
        company = widget.company_edit.text().strip()
        lower_text = text.lower()

        analysis = {
            "language": (
                "fr"
                if any(
                    token in lower_text for token in [" le ", " la ", " de ", " du "]
                )
                else "en"
            ),
            "tech_keywords": [
                kw
                for kw in [
                    "python",
                    "javascript",
                    "react",
                    "api",
                    "sql",
                    "docker",
                    "aws",
                ]
                if kw in lower_text
            ],
            "sector": (
                "tech"
                if any(
                    term in lower_text
                    for term in ["developpeur", "developer", "programmeur", "engineer"]
                )
                else "general"
            ),
        }

        widget.offer_data = {
            "text": text,
            "job_title": job_title or "Poste non specifie",
            "company": company or "Entreprise non specifiee",
            "analysis": analysis,
        }

        self.set_offer_data_to_generation(widget.offer_data)

    def set_offer_data_to_generation(self, offer_data):
        """Store offer information on the generation widget and update hints."""
        if not hasattr(self, "generation_widget"):
            return
        widget = self.generation_widget
        widget.offer_data = offer_data

        if not offer_data:
            widget.generate_btn.setEnabled(False)

            if hasattr(widget, "generate_letter_btn"):
                widget.generate_letter_btn.setEnabled(False)
                widget.generate_letter_btn.setText("Generer la lettre de motivation")

            widget.ai_suggestion.setText(
                "Chargez une offre pour obtenir une suggestion de template."
            )
            return

        widget.generate_btn.setEnabled(True)

        if hasattr(widget, "generate_letter_btn"):

            widget.generate_letter_btn.setEnabled(True)

            widget.generate_letter_btn.setText("Générer la lettre de motivation")

        analysis = offer_data.get("analysis", {}) if offer_data else {}
        if analysis.get("sector") == "tech":
            widget.template_combo.setCurrentText("tech")
            widget.ai_suggestion.setText(
                "Template recommandé : tech (offre détectée comme technique)."
            )
        else:
            widget.ai_suggestion.setText(
                "Template recommandé : modern (offre générale)."
            )
        widget.current_template = widget.template_combo.currentText()

    def start_generation(
        self,
        widget,
        *,
        user_instruction: str = "",
        cv_only_regen: bool = False,
        from_preview: bool = False,
        keep_application_id: bool = False,
        previous_generation_audit: Optional[Dict[str, Any]] = None,
    ):
        """Launch CV generation through the background worker."""
        if hasattr(self, "offer_widget"):
            self.analyze_offer(self.offer_widget)
        if not widget.offer_data:
            show_warning(
                "Veuillez d'abord charger une offre d'emploi.",
                title="Erreur",
                parent=self,
            )
            return
        if widget.current_worker is not None:
            show_info(
                "Une génération est déjà en cours.",
                title="Génération en cours",
                parent=self,
            )
            return

        widget._preview_regen_in_progress = bool(from_preview)

        if not cv_only_regen:
            # Reset cached outputs to avoid reopening stale previews on failure.
            widget.generated_cv_data = None
            widget.generated_cover_letter = None
            widget.generated_result = None
            widget.generated_application_id = None
            if not from_preview:
                preview = getattr(self, "template_preview_window", None)
                if preview is not None:
                    try:
                        preview.close()
                    except Exception:
                        pass
                    self.template_preview_window = None

        template = widget.template_combo.currentText()
        widget.current_template = template

        offer_payload = dict(widget.offer_data)
        target_application_id = (
            getattr(widget, "generated_application_id", None)
            if (keep_application_id or cv_only_regen)
            else None
        )

        worker = self.coordinator.create_cv_worker(
            offer_data=offer_payload,
            template=template,
            application_id=target_application_id,
            user_instruction=user_instruction,
            cv_only_regen=cv_only_regen,
            previous_generation_audit=previous_generation_audit,
        )
        widget.current_worker = worker

        worker.progress_updated.connect(
            lambda message: self.on_generation_progress(widget, message)
        )
        worker.generation_finished.connect(
            lambda result: self.on_generation_finished(widget, result)
        )
        worker.error_occurred.connect(
            lambda message: self.on_generation_error(widget, message)
        )

        widget.generate_btn.setEnabled(False)

        widget.generate_btn.setText("Génération en cours...")

        if hasattr(widget, "generate_letter_btn"):

            widget.generate_letter_btn.setEnabled(False)
        widget.progress_label.setText("Initialisation de la génération...")
        widget.progress_label.show()

        self._show_generation_dialog(widget, "Fichier en cours de génération...")
        worker.start()

    def start_cover_letter_generation(
        self,
        widget,
        *,
        user_instruction: str = "",
        from_preview: bool = False,
        previous_generation_audit: Optional[Dict[str, Any]] = None,
    ):
        """Launch cover-letter generation through the background worker."""
        if hasattr(self, "offer_widget"):
            self.analyze_offer(self.offer_widget)
        if not getattr(widget, "offer_data", None):
            show_warning(
                "Veuillez d'abord charger une offre d'emploi.",
                title="Erreur",
                parent=self,
            )
            return
        if getattr(widget, "current_worker", None) is not None:
            show_info(
                "Une génération de CV est déjà en cours.",
                title="Génération en cours",
                parent=self,
            )
            return
        if getattr(widget, "current_letter_worker", None) is not None:
            show_info(
                "Une génération de lettre de motivation est déjà en cours.",
                title="Génération en cours",
                parent=self,
            )
            return

        widget._preview_regen_in_progress = bool(from_preview)
        offer_payload = dict(widget.offer_data)
        template = (
            widget.template_combo.currentText()
            if hasattr(widget, "template_combo")
            else "modern"
        )

        application_id = getattr(widget, "generated_application_id", None)
        worker = self.coordinator.create_cover_letter_worker(
            offer_data=offer_payload,
            template=template,
            application_id=application_id,
            user_instruction=user_instruction,
            previous_generation_audit=previous_generation_audit,
        )
        widget.current_letter_worker = worker

        worker.progress_updated.connect(
            lambda message: self.on_cover_letter_progress(widget, message)
        )
        worker.generation_finished.connect(
            lambda result: self.on_cover_letter_finished(widget, result)
        )
        worker.error_occurred.connect(
            lambda message: self.on_cover_letter_error(widget, message)
        )

        widget.generate_letter_btn.setEnabled(False)
        widget.generate_letter_btn.setText("Génération lettre de motivation en cours...")
        widget.generate_btn.setEnabled(False)
        widget.progress_label.setText("Initialisation de la lettre...")
        widget.progress_label.show()

        self._show_generation_dialog(widget, "Fichier en cours de génération...")
        worker.start()

    def on_cover_letter_progress(self, widget, message):
        """Update UI during cover-letter generation."""
        widget.progress_label.setText(message or "Génération de la lettre de motivation...")
        widget.progress_label.show()
        if message:
            self._update_generation_dialog(widget, message)

    def on_cover_letter_finished(self, widget, result):
        """Handle successful cover-letter generation."""
        from_preview = bool(getattr(widget, "_preview_regen_in_progress", False))
        self._hide_generation_dialog(widget)
        worker = getattr(widget, "current_letter_worker", None)
        if worker is not None:
            try:
                worker.deleteLater()
            except Exception:
                pass
            widget.current_letter_worker = None
            self.coordinator.release_worker(worker)
            self.coordinator.release_worker(worker)

        widget.generate_letter_btn.setEnabled(True)
        widget.generate_letter_btn.setText("Générer la lettre de motivation")
        if getattr(widget, "current_worker", None) is None:
            widget.generate_btn.setEnabled(True)

        widget.progress_label.hide()

        letter_text = (result or {}).get("cover_letter") or ""
        widget.generated_cover_letter = letter_text
        if widget.generated_cv_data is not None:
            widget.generated_cv_data["cover_letter"] = letter_text
            if isinstance((result or {}).get("generation_audit"), dict):
                widget.generated_cv_data["generation_audit"] = result.get("generation_audit")
            if isinstance((result or {}).get("cover_letter_review"), dict):
                widget.generated_cv_data["cover_letter_review"] = result.get("cover_letter_review")
            if isinstance((result or {}).get("alignment_audit"), dict):
                widget.generated_cv_data["alignment_audit"] = result.get("alignment_audit")
        if isinstance((result or {}).get("generation_audit"), dict):
            if not isinstance(getattr(widget, "generated_result", None), dict):
                widget.generated_result = {}
            widget.generated_result["generation_audit"] = result.get("generation_audit")
        if isinstance((result or {}).get("cover_letter_review"), dict):
            if not isinstance(getattr(widget, "generated_result", None), dict):
                widget.generated_result = {}
            widget.generated_result["cover_letter_review"] = result.get("cover_letter_review")
        if isinstance((result or {}).get("alignment_audit"), dict):
            if not isinstance(getattr(widget, "generated_result", None), dict):
                widget.generated_result = {}
            widget.generated_result["alignment_audit"] = result.get("alignment_audit")
        if (result or {}).get("application_id"):
            widget.generated_application_id = result.get("application_id")

        if hasattr(self, "cover_letter_edit"):
            self.cover_letter_edit.setPlainText(letter_text)
            try:
                self.update_cover_letter_stats()
            except Exception:
                pass

        show_success(
            "La lettre de motivation personnalisée a été générée.",
            title="Lettre de motivation générée",
            parent=self,
        )
        self.refresh_applications()
        if from_preview:
            preview = getattr(self, "template_preview_window", None)
            if preview is not None and getattr(widget, "generated_cv_data", None):
                try:
                    if hasattr(preview, "set_cv_data"):
                        preview.set_cv_data(dict(widget.generated_cv_data))
                    else:
                        preview.cv_data = dict(widget.generated_cv_data)
                    preview.load_letter_preview()
                    if hasattr(preview, "_update_audit_panel"):
                        preview._update_audit_panel()
                    preview.status_label.setText("Regeneration lettre terminee.")
                    if hasattr(preview, "regenerate_button"):
                        preview.regenerate_button.setEnabled(True)
                except Exception as exc:
                    logger.warning(f"Preview letter refresh failed: {exc}")
        elif letter_text.strip():
            try:
                self.preview_cover_letter()
            except Exception as exc:
                logger.warning(f"Preview cover letter failed: {exc}")
        widget._preview_regen_in_progress = False

    def on_cover_letter_error(self, widget, message):
        """Handle cover-letter generation failure."""
        self._hide_generation_dialog(widget)
        worker = getattr(widget, "current_letter_worker", None)
        if worker is not None:
            try:
                worker.deleteLater()
            except Exception:
                pass
            widget.current_letter_worker = None

        widget.generate_letter_btn.setEnabled(True)
        widget.generate_letter_btn.setText("Générer la lettre de motivation")
        if getattr(widget, "current_worker", None) is None:
            widget.generate_btn.setEnabled(True)
        widget.progress_label.hide()
        show_error(
            message or "Une erreur est survenue.",
            title="La Génération de la lettre de motivation a échouée",
            parent=self,
        )
        preview = getattr(self, "template_preview_window", None)
        if preview is not None and hasattr(preview, "regenerate_button"):
            preview.regenerate_button.setEnabled(True)
        widget._preview_regen_in_progress = False

    def on_generation_progress(self, widget, message):
        """Update progress information during generation."""
        widget.progress_label.setText(message or "Generation en cours...")
        widget.progress_label.show()
        if message:
            self._update_generation_dialog(widget, message)

    def on_generation_finished(self, widget, result):
        """Handle successful generation from the worker."""
        from_preview = bool(getattr(widget, "_preview_regen_in_progress", False))
        self._hide_generation_dialog(widget)
        worker = widget.current_worker
        if worker is not None:
            try:
                worker.deleteLater()
            except Exception:
                pass
            widget.current_worker = None
            self.coordinator.release_worker(worker)

        widget.generate_btn.setEnabled(True)

        widget.generate_btn.setText("Générer le CV adapté")

        if (
            hasattr(widget, "generate_letter_btn")
            and getattr(widget, "current_letter_worker", None) is None
        ):

            widget.generate_letter_btn.setEnabled(True)

            widget.generate_letter_btn.setText("Générer la lettre de motivation")

        widget.progress_label.hide()

        cv_markdown = result.get("cv_markdown") or ""
        cv_json_final = result.get("cv_json_final")
        structured_data = None

        if isinstance(cv_json_final, dict):
            try:
                from ...utils.cv_json_renderer import cv_json_to_cv_data

                language = None
                if widget.offer_data:
                    analysis = widget.offer_data.get("analysis") or {}
                    language = analysis.get("language") if isinstance(analysis, dict) else None
                structured_data = cv_json_to_cv_data(cv_json_final, language=language)
                structured_data["raw_content"] = cv_markdown
            except Exception as exc:
                logger.warning(f"CVJSON mapping failed: {exc}")
                structured_data = None

        if structured_data is None:
            structured_data = self.parse_markdown_to_data(cv_markdown)
            try:
                from ...controllers.cv_generator import CVGenerator

                cv_controller = CVGenerator()
                parsed = cv_controller.parse_cv_from_markdown(cv_markdown)
                parsed = cv_controller.enhance_cv_data(parsed, self.profile)
                parsed["raw_content"] = cv_markdown
                structured_data.update(parsed)
            except Exception as exc:
                logger.warning(f"Parsing generated CV failed: {exc}")
                structured_data["raw_content"] = cv_markdown

        if widget.offer_data:
            structured_data["job_title"] = widget.offer_data.get("job_title")
            structured_data["company"] = widget.offer_data.get("company")
        structured_data["template"] = result.get("template") or widget.current_template
        structured_data["application_id"] = result.get("application_id")
        structured_data["cover_letter"] = result.get("cover_letter") or widget.generated_cover_letter
        if isinstance(result.get("generation_audit"), dict):
            structured_data["generation_audit"] = result.get("generation_audit")
        if isinstance(result.get("alignment_audit"), dict):
            structured_data["alignment_audit"] = result.get("alignment_audit")
        if isinstance(result.get("cover_letter_review"), dict):
            structured_data["cover_letter_review"] = result.get("cover_letter_review")

        # Inject profile photo as base64 for CV template rendering
        try:
            _photo_path = getattr(self.profile, "profile_photo_path", None)
            if _photo_path:
                from pathlib import Path as _Path
                import base64 as _b64
                _pf = _Path(_photo_path)
                if _pf.is_file():
                    structured_data["photo_base64"] = _b64.b64encode(_pf.read_bytes()).decode("ascii")
        except Exception as _exc:
            logger.debug(f"Photo injection skipped: {_exc}")

        widget.generated_cv_data = structured_data
        widget.generated_cover_letter = result.get("cover_letter")
        widget.generated_result = result
        widget.generated_application_id = result.get("application_id")

        refreshed_profile = self.coordinator.refresh_profile()
        if refreshed_profile is not None:
            self.profile = refreshed_profile

        if hasattr(widget, "stats_label"):
            widget.stats_label.setText(
                f"CV générés : {getattr(self.profile, 'total_cvs_generated', 0)}"
            )

        self.refresh_applications()
        show_success(
            "Le CV et la lettre de motivation on été générés et enregistrés.",
            title="Generation terminee",
            parent=self,
        )
        if from_preview:
            preview = getattr(self, "template_preview_window", None)
            if preview is not None:
                try:
                    if hasattr(preview, "set_cv_data"):
                        preview.set_cv_data(dict(widget.generated_cv_data or {}))
                    else:
                        preview.cv_data = dict(widget.generated_cv_data or {})
                    preview.load_template_preview()
                    if hasattr(preview, "_update_audit_panel"):
                        preview._update_audit_panel()
                    preview.status_label.setText("Regeneration terminee.")
                    if hasattr(preview, "regenerate_button"):
                        preview.regenerate_button.setEnabled(True)
                except Exception as exc:
                    logger.warning(f"Preview refresh failed after regeneration: {exc}")
            else:
                self.open_template_preview(widget)
        else:
            self.open_template_preview(widget)
        widget._preview_regen_in_progress = False

    def on_generation_error(self, widget, message):
        """Handle generation failure."""
        self._hide_generation_dialog(widget)
        worker = widget.current_worker
        if worker is not None:
            try:
                worker.deleteLater()
            except Exception:
                pass
            widget.current_worker = None
            self.coordinator.release_worker(worker)

        widget.generate_btn.setEnabled(True)

        widget.generate_btn.setText("Générer le CV adapté")

        if (
            hasattr(widget, "generate_letter_btn")
            and getattr(widget, "current_letter_worker", None) is None
        ):

            widget.generate_letter_btn.setEnabled(True)

            widget.generate_letter_btn.setText("Générer la lettre de motivation")

        widget.progress_label.hide()

        show_error(
            message or "Une erreur est survenue.",
            title="Échec de la génération",
            parent=self,
        )
        preview = getattr(self, "template_preview_window", None)
        if preview is not None and hasattr(preview, "regenerate_button"):
            preview.regenerate_button.setEnabled(True)
        widget._preview_regen_in_progress = False

    def _on_preview_window_destroyed(self, *_args) -> None:
        """Clear stale reference after preview window destruction."""
        self.template_preview_window = None

    def open_template_preview(self, widget):
        """Ouvre la fenêtre de prévisualisation des templates."""
        if not widget.generated_cv_data:
            show_warning("Veuillez d'abord générer un CV.", title="Erreur", parent=self)
            return

        preview_window_cls = _load_template_preview_window_class()
        if not preview_window_cls:
            show_error(
                "La fenêtre de prévisualisation n'est pas disponible.",
                title="Erreur",
                parent=self,
            )
            return

        try:
            preview = getattr(self, "template_preview_window", None)

            # Reuse an existing preview to avoid spawning multiple WebEngine windows.
            if preview is not None:
                try:
                    if hasattr(preview, "set_cv_data"):
                        preview.set_cv_data(dict(widget.generated_cv_data or {}))
                    preview.load_template_preview()
                    preview.showNormal()
                    preview.raise_()
                    preview.activateWindow()
                    return
                except Exception:
                    try:
                        preview.close()
                    except Exception:
                        pass
                    self.template_preview_window = None

            # Ouvrir la fenêtre de prévisualisation
            self.template_preview_window = preview_window_cls(
                dict(widget.generated_cv_data or {}), self
            )
            if hasattr(self.template_preview_window, "regenerate_requested"):
                self.template_preview_window.regenerate_requested.connect(
                    lambda payload: self.on_preview_regenerate_requested(widget, payload)
                )
            self.template_preview_window.destroyed.connect(self._on_preview_window_destroyed)
            self.template_preview_window.show()

        except Exception as e:
            logger.error(f"Erreur ouverture prévisualisation: {e}")
            show_error(
                f"Impossible d'ouvrir la prévisualisation:\n{e}",
                title="Erreur",
                parent=self,
            )

    def on_preview_regenerate_requested(self, widget, payload):
        """Handle tab-aware regeneration requests coming from preview window."""
        data = payload if isinstance(payload, dict) else {}
        target = str(data.get("target") or "cv").strip().lower()
        instruction = str(data.get("instruction") or "").strip()
        application_id = data.get("application_id")

        if application_id:
            widget.generated_application_id = application_id

        previous_generation_audit = None
        cv_data = data.get("cv_data")
        if isinstance(cv_data, dict) and isinstance(cv_data.get("generation_audit"), dict):
            previous_generation_audit = cv_data.get("generation_audit")
        elif isinstance(getattr(widget, "generated_cv_data", None), dict):
            prev = widget.generated_cv_data.get("generation_audit")
            if isinstance(prev, dict):
                previous_generation_audit = prev

        if target == "letter":
            self.start_cover_letter_generation(
                widget,
                user_instruction=instruction,
                from_preview=True,
                previous_generation_audit=previous_generation_audit,
            )
            return

        self.start_generation(
            widget,
            user_instruction=instruction,
            cv_only_regen=True,
            from_preview=True,
            keep_application_id=True,
            previous_generation_audit=previous_generation_audit,
        )

    def parse_markdown_to_data(self, markdown_text):
        """Fallback parser that turns markdown into a minimal structured payload."""
        data = {
            "name": self.profile.name or "Candidat",
            "email": self.profile.email or "",
            "phone": self.profile.phone or "",
            "linkedin_url": self.profile.linkedin_url or "",
            "job_title": "Professionnel",
            "profile_summary": "",
            "experience": [],
            "education": [],
            "skills": [],
            "languages": [],
            "projects": [],
            "certifications": [],
            "interests": [],
            "raw_content": markdown_text,
        }

        if not markdown_text:
            return data

        lines = markdown_text.splitlines()
        current_section = None

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("# "):
                title_text = stripped[2:].strip()
                if title_text and (not data["name"] or data["name"] == "Candidat"):
                    data["name"] = title_text
            elif stripped.startswith("## "):
                current_section = stripped[3:].lower().strip()
            elif stripped and current_section:
                if "profil" in current_section or "about" in current_section:
                    if data["profile_summary"]:
                        data["profile_summary"] += " "
                    data["profile_summary"] += stripped

        data["profile_summary"] = data["profile_summary"].strip()
        return data

    def refresh_applications(self):
        """Rafraîchit la liste des candidatures."""
        try:
            # émettre un signal pour rafraîchir l'interface principale
            main_window = self.main_window or self.window()
            if main_window and hasattr(main_window, "refresh_history"):
                main_window.refresh_history()
        except Exception as e:
            logger.error(f"Erreur rafraîchissement: {e}")

    def on_model_changed(self, model_id: str):
        """Gère le changement de modèle IA."""
        logger.info(f"Modèle sélectionné: {model_id}")

        # Mettre à  jour le profil utilisateur si nÃƒ©cessaire
        try:
            from ...utils.model_manager import model_manager

            model_info = model_manager.get_model_info(model_id)
            if model_info:
                # Optionnel: sauvegarder le choix dans le profil
                # self.profile.preferred_model = model_id
                logger.info(f"Modèle configuré: {model_info.display_name}")
        except Exception as e:
            logger.error(f"Erreur changement modèle: {e}")
