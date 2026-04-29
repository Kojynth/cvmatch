"""Job application panel extracted from main window."""

from __future__ import annotations

import threading
from typing import Any, Dict, Optional

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
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
from ...services.dialogs import confirm, show_error, show_info, show_success, show_warning
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
        self._cache_prune_lock = threading.Lock()
        self._cache_prune_in_flight = False
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

    def _get_profile_cv_language_options(self):
        """Return CV language choices declared in the profile."""
        try:
            from ...utils.multilang_cv_support import extract_profile_language_options

            profile_languages = (
                getattr(self.profile, "extracted_languages", None)
                or getattr(self.profile, "languages", None)
                or []
            )
            options = extract_profile_language_options(
                {"languages": profile_languages},
                fallback=False,
            )
        except Exception:
            options = []
        return options

    def _get_profile_cv_language_codes(self) -> set[str]:
        return {code for code, _label in self._get_profile_cv_language_options()}

    @staticmethod
    def _language_display_label(language_code: str) -> str:
        code = str(language_code or "").strip().lower()
        if not code:
            return ""
        try:
            from ...utils.multilang_cv_support import ISO_TO_DISPLAY_LABEL

            return str(ISO_TO_DISPLAY_LABEL.get(code) or code.upper())
        except Exception:
            return code.upper()

    @staticmethod
    def _detect_offer_language(offer_payload: Dict[str, Any] | None) -> str:
        data = offer_payload if isinstance(offer_payload, dict) else {}
        analysis = data.get("analysis")
        analysis = analysis if isinstance(analysis, dict) else {}
        try:
            from ...utils.language_policy import (
                detect_language_from_text_default,
                normalize_language_code,
            )

            for source in (data, analysis):
                for key in (
                    "cv_language",
                    "target_language",
                    "language_code",
                    "language",
                ):
                    value = str(source.get(key) or "").strip()
                    if value:
                        return normalize_language_code(value)
            text = str(data.get("text") or "").strip()
            if text:
                return detect_language_from_text_default(text)
        except Exception:
            pass
        return ""

    def _remove_non_profile_language_options(self, combo: QComboBox) -> None:
        profile_codes = self._get_profile_cv_language_codes()
        for index in range(combo.count() - 1, -1, -1):
            code = str(combo.itemData(index) or "").strip().lower()
            if code and code not in profile_codes:
                combo.removeItem(index)

    def _sync_cv_language_combo_with_offer(self, offer_language: str) -> None:
        """Select the offer language when the profile declares it.

        If the offer language is absent from the profile, add a temporary
        explicit offer-language option so the visible target matches the
        generation override that will be confirmed before launch.
        """
        widget = getattr(self, "generation_widget", None)
        combo = getattr(widget, "cv_language_combo", None)
        if combo is None:
            return

        if bool(getattr(widget, "cv_language_user_selected", False)):
            combo.setEnabled(combo.count() > 1)
            return

        self._remove_non_profile_language_options(combo)
        profile_options = self._get_profile_cv_language_options()
        profile_codes = {code for code, _label in profile_options}
        if not profile_options:
            combo.setEnabled(False)
            return

        language = str(offer_language or "").strip().lower()
        if language and language in profile_codes:
            self._set_combo_to_data(combo, language)
        elif language:
            label = self._language_display_label(language)
            combo.addItem(f"{label} (langue de l'offre)", language)
            combo.setCurrentIndex(combo.count() - 1)

        widget.cv_language_user_selected = False
        widget.cv_language_selection_source = "analysis"
        widget.current_cv_language = self._selected_cv_language(widget)
        combo.setEnabled(combo.count() > 1)

    @staticmethod
    def _set_combo_to_data(combo, value: str) -> bool:
        for index in range(combo.count()):
            if combo.itemData(index) == value:
                combo.setCurrentIndex(index)
                return True
        return False

    def _reset_cv_language_choice_source(self) -> None:
        widget = getattr(self, "generation_widget", None)
        if widget is None:
            return
        widget.cv_language_user_selected = False
        widget.cv_language_selection_source = "analysis"

    def _mark_cv_language_manually_selected(self, widget) -> None:
        widget.cv_language_user_selected = True
        widget.cv_language_selection_source = "manual"
        widget.current_cv_language = self._selected_cv_language(widget)

    def _select_cv_language_in_combo(
        self,
        widget,
        language: str,
        *,
        source: str,
    ) -> None:
        language = str(language or "").strip().lower()
        if not language:
            return
        combo = getattr(widget, "cv_language_combo", None)
        if combo is not None and not self._set_combo_to_data(combo, language):
            label = self._language_display_label(language)
            combo.addItem(f"{label} (langue de l'offre)", language)
            combo.setCurrentIndex(combo.count() - 1)
            combo.setEnabled(combo.count() > 1)
        widget.current_cv_language = language
        widget.cv_language_user_selected = source == "manual"
        widget.cv_language_selection_source = source

    @staticmethod
    def _selected_cv_language(widget) -> str:
        combo = getattr(widget, "cv_language_combo", None)
        if combo is None:
            return ""
        try:
            return str(combo.currentData() or "").strip().lower()
        except Exception:
            return ""

    def _apply_selected_cv_language_to_offer_payload(
        self,
        widget,
        offer_payload,
        cv_language: str = "",
    ):
        cv_language = (
            (cv_language or self._selected_cv_language(widget)).strip().lower()
        )
        widget.current_cv_language = cv_language
        if not cv_language:
            return offer_payload

        payload = dict(offer_payload or {})
        payload["cv_language"] = cv_language
        payload["target_language"] = cv_language
        analysis = payload.get("analysis")
        analysis_payload = dict(analysis) if isinstance(analysis, dict) else {}
        analysis_payload["language"] = cv_language
        analysis_payload["cv_language"] = cv_language
        analysis_payload["target_language"] = cv_language
        payload["analysis"] = analysis_payload
        return payload

    def _confirm_unprofiled_offer_language(
        self,
        *,
        offer_language: str,
        document_label: str,
    ) -> bool:
        profile_options = self._get_profile_cv_language_options()
        if not profile_options:
            return True
        profile_labels = ", ".join(label for _code, label in profile_options)
        offer_label = self._language_display_label(offer_language)
        return confirm(
            (
                f"L'offre semble redigee en {offer_label}, une langue absente "
                f"des langues maitrisees/renseignees dans le profil "
                f"({profile_labels}).\n\n"
                f"Voulez-vous generer {document_label} en {offer_label} ?"
            ),
            title="Langue de generation a confirmer",
            parent=self,
        )

    def _language_conflict_options(
        self,
        *,
        selected_language: str,
        offer_language: str,
    ) -> list[tuple[str, str]]:
        options: list[tuple[str, str]] = []
        seen: set[str] = set()

        def add(code: str, label: str) -> None:
            normalized = str(code or "").strip().lower()
            if not normalized or normalized in seen:
                return
            seen.add(normalized)
            options.append((normalized, label))

        selected_language = str(selected_language or "").strip().lower()
        offer_language = str(offer_language or "").strip().lower()
        if selected_language:
            add(
                selected_language,
                f"{self._language_display_label(selected_language)} "
                "(selection actuelle)",
            )
        if offer_language:
            add(
                offer_language,
                f"{self._language_display_label(offer_language)} "
                "(recommandee par l'analyse de l'offre)",
            )
        for code, label in self._get_profile_cv_language_options():
            add(code, label)
        return options

    def _choose_generation_language_for_conflict(
        self,
        *,
        selected_language: str,
        offer_language: str,
        document_label: str,
    ) -> str | None:
        selected_language = str(selected_language or "").strip().lower()
        offer_language = str(offer_language or "").strip().lower()
        options = self._language_conflict_options(
            selected_language=selected_language,
            offer_language=offer_language,
        )
        if not options:
            return selected_language or offer_language or None

        dialog = QDialog(self)
        dialog.setWindowTitle("Langue de generation")
        layout = QVBoxLayout(dialog)

        selected_label = self._language_display_label(selected_language)
        offer_label = self._language_display_label(offer_language)
        message = QLabel(
            (
                f"La langue selectionnee pour {document_label} est "
                f"{selected_label}, mais l'offre semble redigee en "
                f"{offer_label}.\n\n"
                "Choisissez la langue a utiliser avant de lancer la generation."
            )
        )
        message.setWordWrap(True)
        layout.addWidget(message)

        combo = QComboBox(dialog)
        for code, label in options:
            combo.addItem(label, code)
        self._set_combo_to_data(combo, selected_language)
        layout.addWidget(combo)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        chosen = str(combo.currentData() or "").strip().lower()
        return chosen or selected_language or offer_language or None

    def _resolve_generation_language_for_offer(
        self,
        widget,
        offer_payload: Dict[str, Any],
        *,
        document_label: str,
    ) -> str | None:
        offer_language = self._detect_offer_language(offer_payload)
        selected_language = self._selected_cv_language(widget)
        user_selected_language = bool(
            getattr(widget, "cv_language_user_selected", False)
        )

        if (
            user_selected_language
            and selected_language
            and offer_language
            and selected_language != offer_language
        ):
            chosen_language = self._choose_generation_language_for_conflict(
                selected_language=selected_language,
                offer_language=offer_language,
                document_label=document_label,
            )
            if not chosen_language:
                return None
            self._select_cv_language_in_combo(
                widget,
                chosen_language,
                source=(
                    "analysis_confirmed"
                    if chosen_language == offer_language
                    else "manual"
                ),
            )
            return chosen_language

        if (
            not user_selected_language
            and offer_language
            and selected_language != offer_language
        ):
            self._select_cv_language_in_combo(
                widget,
                offer_language,
                source="analysis",
            )
            selected_language = offer_language

        profile_codes = self._get_profile_cv_language_codes()
        if profile_codes and offer_language and offer_language not in profile_codes:
            if not self._confirm_unprofiled_offer_language(
                offer_language=offer_language,
                document_label=document_label,
            ):
                return None
            self._select_cv_language_in_combo(
                widget,
                offer_language,
                source="analysis_confirmed",
            )
            return offer_language
        return selected_language or offer_language

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

        style_layout.addWidget(QLabel("Langue CV :"))
        cv_language_combo = QComboBox()
        language_options = self._get_profile_cv_language_options()
        if language_options:
            for code, label in language_options:
                cv_language_combo.addItem(label, code)
            preferred_language = str(
                getattr(self.profile, "preferred_language", "") or ""
            ).strip().lower()
            if preferred_language:
                self._set_combo_to_data(cv_language_combo, preferred_language)
            cv_language_combo.setEnabled(len(language_options) > 1)
        else:
            cv_language_combo.addItem("Non renseignee", "")
            cv_language_combo.setEnabled(False)
        style_layout.addWidget(cv_language_combo)
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

        widget.cv_language_combo = cv_language_combo

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

        widget.current_cv_language = self._selected_cv_language(widget)

        widget.cv_language_user_selected = False

        widget.cv_language_selection_source = "profile"

        template_combo.currentTextChanged.connect(
            lambda value: setattr(widget, "current_template", value)
        )
        cv_language_combo.currentIndexChanged.connect(
            lambda _index: setattr(
                widget, "current_cv_language", self._selected_cv_language(widget)
            )
        )
        cv_language_combo.activated.connect(
            lambda _index: self._mark_cv_language_manually_selected(widget)
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
            widget.generate_btn.setText("Générer le CV adapté")
            if hasattr(widget, "generate_letter_btn") and getattr(widget, "current_letter_worker", None) is None:
                widget.generate_letter_btn.setEnabled(True)
                widget.generate_letter_btn.setText("Générer la lettre de motivation")
        else:
            widget.current_letter_worker = None
            widget.generate_letter_btn.setEnabled(True)
            widget.generate_letter_btn.setText("Générer la lettre de motivation")
            if getattr(widget, "current_worker", None) is None:
                widget.generate_btn.setEnabled(True)

        widget.progress_label.hide()
        widget._preview_regen_in_progress = False
        self._hide_generation_dialog(widget)
        show_info(
            "Génération arrêtée à la demande de l'utilisateur.",
            title="Génération annulée",
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
            self._reset_cv_language_choice_source()
            widget.text_edit.setText(text)

    def load_offer_file(self, widget, file_path: str):
        """Charge une offre depuis un fichier."""
        try:
            parser = DocumentParser()
            content = parser.parse_document(file_path)
            self._reset_cv_language_choice_source()
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

    def analyze_offer(self, widget, *, sync_language: bool = True):
        """Analyse the job offer text and prepare metadata for generation."""
        text = widget.text_edit.toPlainText()
        if not text or len(text.strip()) < 50:

            widget.offer_data = None

            self.set_offer_data_to_generation(None)
            if sync_language:
                self._sync_cv_language_combo_with_offer("")

            return

        job_title = widget.job_title_edit.text().strip()
        company = widget.company_edit.text().strip()
        lower_text = text.lower()
        detected_language = self._detect_offer_language({"text": text})

        analysis = {
            "language": detected_language or "fr",
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
        if sync_language:
            self._sync_cv_language_combo_with_offer(detected_language)

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
        offer_data_override: Optional[Dict[str, Any]] = None,
        application_id_override: Optional[int] = None,
    ):
        """Launch CV generation through the background worker."""
        if isinstance(offer_data_override, dict):
            widget.offer_data = dict(offer_data_override)
        elif hasattr(self, "offer_widget"):
            self.analyze_offer(self.offer_widget, sync_language=False)
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

        raw_offer_payload = dict(widget.offer_data)
        target_language = self._resolve_generation_language_for_offer(
            widget,
            raw_offer_payload,
            document_label="le CV",
        )
        if target_language is None:
            return

        self._prune_model_cache_before_generation(widget)

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

        offer_payload = self._apply_selected_cv_language_to_offer_payload(
            widget,
            raw_offer_payload,
            target_language,
        )
        if isinstance(application_id_override, int):
            target_application_id = application_id_override
        else:
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

    def _resolve_selected_model_id(self, widget) -> str:
        model_id = ""
        try:
            from ...utils.model_config_manager import model_config_manager

            model_id = str(
                getattr(model_config_manager.get_current_config(), "model_id", "") or ""
            ).strip()
        except Exception:
            model_id = ""

        if not model_id:
            selector = getattr(widget, "model_selector", None)
            if selector is not None:
                try:
                    model_id = str(selector.get_current_model() or "").strip()
                except Exception:
                    model_id = ""

        return model_id

    def _prune_model_cache_before_generation(self, widget) -> None:
        selected_model_id = self._resolve_selected_model_id(widget)
        if not selected_model_id:
            logger.warning("Cache prune skipped: selected model id is empty.")
            return

        with self._cache_prune_lock:
            if self._cache_prune_in_flight:
                logger.info(
                    "Model cache prune already running, skipping duplicate request (selected=%s).",
                    selected_model_id,
                )
                return
            self._cache_prune_in_flight = True

        def _run_prune() -> None:
            try:
                from ...utils.model_manager import model_manager

                pruned = model_manager.prune_model_cache_except(selected_model_id)
                if pruned:
                    logger.info(
                        "Model cache pruned asynchronously: selected=%s removed=%s",
                        selected_model_id,
                        len(pruned),
                    )
                else:
                    logger.info(
                        "Model cache already clean: selected=%s",
                        selected_model_id,
                    )
            except Exception as exc:
                logger.warning("Model cache prune ignored: %s", exc)
            finally:
                with self._cache_prune_lock:
                    self._cache_prune_in_flight = False

        threading.Thread(
            target=_run_prune,
            name="model-cache-prune",
            daemon=True,
        ).start()

    def start_cover_letter_generation(
        self,
        widget,
        *,
        user_instruction: str = "",
        from_preview: bool = False,
        previous_generation_audit: Optional[Dict[str, Any]] = None,
        offer_data_override: Optional[Dict[str, Any]] = None,
        application_id_override: Optional[int] = None,
    ):
        """Launch cover-letter generation through the background worker."""
        if isinstance(offer_data_override, dict):
            widget.offer_data = dict(offer_data_override)
        elif hasattr(self, "offer_widget"):
            self.analyze_offer(self.offer_widget, sync_language=False)
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

        raw_offer_payload = dict(widget.offer_data)
        target_language = self._resolve_generation_language_for_offer(
            widget,
            raw_offer_payload,
            document_label="la lettre de motivation",
        )
        if target_language is None:
            return

        self._prune_model_cache_before_generation(widget)

        widget._preview_regen_in_progress = bool(from_preview)
        offer_payload = self._apply_selected_cv_language_to_offer_payload(
            widget,
            raw_offer_payload,
            target_language,
        )
        template = (
            widget.template_combo.currentText()
            if hasattr(widget, "template_combo")
            else "modern"
        )

        if isinstance(application_id_override, int):
            application_id = application_id_override
        else:
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

                language = (
                    result.get("language")
                    or cv_json_final.get("language")
                    or self._selected_cv_language(widget)
                    or None
                )
                if widget.offer_data:
                    analysis = widget.offer_data.get("analysis") or {}
                    language = (
                        language
                        or widget.offer_data.get("cv_language")
                        or widget.offer_data.get("target_language")
                        or (
                            analysis.get("language")
                            if isinstance(analysis, dict)
                            else None
                        )
                    )
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

        selected_language = (
            result.get("language")
            or (
                cv_json_final.get("language")
                if isinstance(cv_json_final, dict)
                else ""
            )
            or self._selected_cv_language(widget)
        )
        if selected_language:
            structured_data["language"] = str(selected_language).strip().lower()

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

    @staticmethod
    def _coerce_application_id(value: Any) -> Optional[int]:
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.isdigit():
                try:
                    return int(stripped)
                except Exception:
                    return None
        return None

    def _load_offer_payload_from_application(
        self,
        application_id: Optional[int],
    ) -> Optional[Dict[str, Any]]:
        app_id = self._coerce_application_id(application_id)
        if not isinstance(app_id, int):
            return None
        try:
            from ...models.database import get_session
            from ...models.job_application import JobApplication

            with get_session() as session:
                app = session.get(JobApplication, app_id)
                if app is None:
                    return None
                analysis = (
                    dict(app.offer_analysis)
                    if isinstance(app.offer_analysis, dict)
                    else {}
                )
                return {
                    "text": str(app.offer_text or ""),
                    "job_title": str(app.job_title or ""),
                    "company": str(app.company or ""),
                    "analysis": analysis,
                }
        except Exception as exc:
            logger.warning(
                "Impossible de charger le contexte offre pour application_id=%s: %s",
                application_id,
                exc,
            )
            return None

    def on_preview_regenerate_requested(self, widget, payload):
        """Handle tab-aware regeneration requests coming from preview window."""
        data = payload if isinstance(payload, dict) else {}
        target = str(data.get("target") or "cv").strip().lower()
        instruction = str(data.get("instruction") or "").strip()
        application_id = self._coerce_application_id(data.get("application_id"))

        requested_template = str(data.get("template") or "").strip()
        if requested_template and hasattr(widget, "template_combo"):
            combo = getattr(widget, "template_combo", None)
            if combo is not None:
                idx = combo.findText(requested_template)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                    widget.current_template = combo.currentText()

        requested_language = str(data.get("language") or "").strip().lower()
        if not requested_language and isinstance(data.get("cv_data"), dict):
            requested_language = str(
                data.get("cv_data", {}).get("language") or ""
            ).strip().lower()
        if requested_language and hasattr(widget, "cv_language_combo"):
            combo = getattr(widget, "cv_language_combo", None)
            if combo is not None and self._set_combo_to_data(combo, requested_language):
                widget.current_cv_language = self._selected_cv_language(widget)

        cv_data = data.get("cv_data")
        offer_payload_override = (
            dict(data.get("offer_data"))
            if isinstance(data.get("offer_data"), dict)
            else None
        )
        if not isinstance(offer_payload_override, dict):
            offer_payload_override = self._load_offer_payload_from_application(application_id)
        if not isinstance(offer_payload_override, dict) and isinstance(cv_data, dict):
            offer_text = str(cv_data.get("offer_text") or "").strip()
            job_title = str(cv_data.get("job_title") or "").strip()
            company = str(cv_data.get("company") or "").strip()
            analysis = cv_data.get("offer_analysis")
            if offer_text and job_title and company:
                offer_payload_override = {
                    "text": offer_text,
                    "job_title": job_title,
                    "company": company,
                    "analysis": dict(analysis) if isinstance(analysis, dict) else {},
                }

        if isinstance(application_id, int):
            widget.generated_application_id = application_id
        if isinstance(offer_payload_override, dict):
            widget.offer_data = dict(offer_payload_override)

        previous_generation_audit = None
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
                offer_data_override=offer_payload_override,
                application_id_override=application_id,
            )
            return

        self.start_generation(
            widget,
            user_instruction=instruction,
            cv_only_regen=True,
            from_preview=True,
            keep_application_id=True,
            previous_generation_audit=previous_generation_audit,
            offer_data_override=offer_payload_override,
            application_id_override=application_id,
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

        # Mettre à jour le profil utilisateur si nécessaire
        try:
            from ...utils.model_manager import model_manager

            model_info = model_manager.get_model_info(model_id)
            if model_info:
                # Optionnel: sauvegarder le choix dans le profil
                # self.profile.preferred_model = model_id
                logger.info(f"Modèle configuré: {model_info.display_name}")
        except Exception as e:
            logger.error(f"Erreur changement modèle: {e}")
