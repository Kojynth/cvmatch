"""
Generic CV Export Dialog
========================

Dialog that lets the user pick an LLM model and a CV template, then
generates a standalone professional CV from the current profile
(no specific job offer), opens the standard preview, and lets the user
export from there.

Usage::

    dlg = GenericCVExportDialog(profile_json, parent=self)
    dlg.exec()
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Dict, Optional

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

try:
    from app.config import DEFAULT_PII_CONFIG
    from app.logging.safe_logger import get_safe_logger

    logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)
except ImportError:
    import logging

    logger = logging.getLogger(__name__)

from app.services.dialogs import show_error
from app.widgets.style_manager import apply_button_style


def build_generic_cv_preview_data(
    cv_json: Dict[str, Any],
    *,
    language_code: str,
    template: str,
    photo_base64: Optional[str] = None,
) -> Dict[str, Any]:
    """Map generic CVJSON onto the standard preview/export payload."""
    from app.utils.cv_json_renderer import cv_json_to_cv_data, cv_json_to_markdown

    selected_language = str(language_code or "").strip() or "fr"
    selected_template = str(template or "").strip() or "modern"
    payload = dict(cv_json) if isinstance(cv_json, dict) else {}

    preview_data = cv_json_to_cv_data(payload, language=selected_language)
    preview_data["raw_content"] = cv_json_to_markdown(
        payload,
        language=selected_language,
    )
    preview_data["cv_json_final"] = payload
    preview_data["template"] = selected_template
    preview_data["template_used"] = selected_template
    preview_data["language"] = selected_language
    preview_data["generation_mode"] = "generic"
    if str(photo_base64 or "").strip():
        preview_data["photo_base64"] = str(photo_base64).strip()
    return preview_data


def _load_photo_base64(photo_path: Optional[str]) -> str:
    path_text = str(photo_path or "").strip()
    if not path_text:
        return ""

    try:
        photo_path_obj = Path(path_text)
        if not photo_path_obj.is_file():
            return ""
        return base64.b64encode(photo_path_obj.read_bytes()).decode("ascii")
    except Exception as exc:
        logger.debug("GenericCVExportDialog: photo injection skipped: %s", exc)
        return ""


class GenericCVExportDialog(QDialog):
    """Modal dialog for generating a generic CV and opening the preview."""

    _TEMPLATES = ["modern", "tech", "classic", "creative", "minimal"]
    _OPEN_PREVIEW_WINDOWS: list[Any] = []

    def __init__(
        self,
        profile_json: Dict[str, Any],
        parent=None,
        *,
        profile_id: Optional[int] = None,
        model_version: Optional[str] = None,
        profile_photo_path: Optional[str] = None,
    ) -> None:
        super().__init__(parent)
        self._profile_json = profile_json
        self._profile_id = int(profile_id) if profile_id else None
        self._profile_model_version = str(model_version or "").strip()
        self._profile_photo_path = str(profile_photo_path or "").strip()
        self._worker = None
        self._cv_json: Dict[str, Any] = {}
        self._preview_cv_data: Dict[str, Any] = {}
        self._pending_preview_payload: Dict[str, Any] = {}
        self._cancelling = False

        # Build language options from the profile (dynamic) with FR/EN fallback
        try:
            from app.utils.multilang_cv_support import extract_profile_language_options

            self._language_options = extract_profile_language_options(profile_json)
        except Exception:
            self._language_options = [("fr", "Français"), ("en", "English")]

        self.setWindowTitle("Générer un CV générique")
        self.setWindowModality(Qt.ApplicationModal)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setMinimumWidth(480)
        self.setMaximumWidth(600)

        self._build_ui()
        self._apply_style()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        title = QLabel("Générer un CV générique")
        title.setStyleSheet("font-size: 15px; font-weight: bold; color: #e0e0e0;")
        layout.addWidget(title)

        subtitle = QLabel(
            "Le LLM formatera votre profil en CV professionnel sans adaptation à une offre spécifique, puis ouvrira la prévisualisation avant l'export PDF."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("font-size: 12px; color: #999; margin-bottom: 4px;")
        layout.addWidget(subtitle)

        layout.addWidget(self._make_separator())

        layout.addWidget(QLabel("Modèle IA :"))
        from app.widgets.model_selector import CompactModelSelector

        self._model_selector = CompactModelSelector(parent=self)
        layout.addWidget(self._model_selector)

        layout.addWidget(self._make_separator())

        template_row = QHBoxLayout()
        template_row.addWidget(QLabel("Template CV :"))
        self._template_combo = QComboBox()
        for name in self._TEMPLATES:
            self._template_combo.addItem(name.capitalize(), name)
        template_row.addWidget(self._template_combo)
        template_row.addStretch()
        layout.addLayout(template_row)

        lang_row = QHBoxLayout()
        lang_row.addWidget(QLabel("Langue du CV :"))
        self._lang_combo = QComboBox()
        for code, label in self._language_options:
            self._lang_combo.addItem(label, code)
        lang_row.addWidget(self._lang_combo)
        lang_row.addStretch()
        layout.addLayout(lang_row)

        layout.addWidget(self._make_separator())

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setVisible(False)
        layout.addWidget(self._progress_bar)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("font-size: 11px; color: #aaa;")
        self._status_label.setVisible(False)
        layout.addWidget(self._status_label)

        btn_row = QHBoxLayout()
        self._cancel_btn = QPushButton("Annuler")
        apply_button_style(self._cancel_btn, "secondary")
        self._cancel_btn.clicked.connect(self._on_cancel)

        self._generate_btn = QPushButton("Générer et prévisualiser le CV")
        apply_button_style(self._generate_btn, "primary")
        self._generate_btn.clicked.connect(self._on_generate)

        btn_row.addWidget(self._cancel_btn)
        btn_row.addStretch()
        btn_row.addWidget(self._generate_btn)
        layout.addLayout(btn_row)

    def _make_separator(self) -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #3a3a3a;")
        return sep

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QDialog {
                background-color: #1e1e1e;
            }
            QLabel {
                color: #c0c0c0;
                font-size: 13px;
            }
            QComboBox {
                background-color: #2a2a2a;
                color: #e0e0e0;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 4px 8px;
                min-width: 120px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QProgressBar {
                border: 1px solid #444;
                border-radius: 4px;
                text-align: center;
                background-color: #2a2a2a;
                color: #e0e0e0;
            }
            QProgressBar::chunk {
                background-color: #2E86AB;
                border-radius: 3px;
            }
            """
        )

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_generate(self) -> None:
        self._generate_btn.setEnabled(False)
        self._progress_bar.setVisible(True)
        self._status_label.setVisible(True)
        self._progress_bar.setValue(0)

        language_code = self._selected_language_code()
        model_id = self._selected_model_id()

        from app.workers.generic_cv_export_worker import GenericCVExportWorker

        self._worker = GenericCVExportWorker(
            self._profile_json,
            language_code=language_code,
            model_id=model_id,
            parent=self,
        )
        self._worker.progress_updated.connect(self._on_progress)
        self._worker.generation_finished.connect(self._on_generation_finished)
        self._worker.error_occurred.connect(self._on_error)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    def _on_cancel(self) -> None:
        if self._worker and self._worker.isRunning():
            self._cancelling = True
            self._cancel_btn.setEnabled(False)
            self._status_label.setText("Annulation en cours...")
            self._worker.requestInterruption()
            self._worker.quit()
        else:
            self.reject()

    def _on_worker_finished(self) -> None:
        """Called when the worker thread has fully stopped (finished signal)."""
        if self._cancelling:
            self.reject()

    def _on_progress(self, pct: int, msg: str) -> None:
        self._progress_bar.setValue(pct)
        self._status_label.setText(msg)

    def _on_generation_finished(self, cv_json: dict) -> None:
        self._cv_json = dict(cv_json) if isinstance(cv_json, dict) else {}
        template = self._template_combo.currentData() or "modern"

        self._generate_btn.setEnabled(True)
        self._progress_bar.setVisible(False)
        self._status_label.setVisible(False)

        self._preview_cv_data = self._build_preview_payload(self._cv_json, template)
        application_id = self._persist_generated_cv_in_history(
            cv_json=self._cv_json,
            preview_data=self._preview_cv_data,
            template=template,
        )
        if application_id:
            self._preview_cv_data["application_id"] = application_id
            self._preview_cv_data.setdefault("offer_text", "")
        if self._queue_preview_window(self._preview_cv_data):
            self.accept()
            return

        show_error(
            "La fenêtre de prévisualisation n'a pas pu s'ouvrir.\n"
            "Vérifiez que les dépendances (QtWebEngine) sont bien installées.",
            title="Prévisualisation indisponible",
            parent=self,
        )

    def _on_error(self, msg: str) -> None:
        self._generate_btn.setEnabled(True)
        self._progress_bar.setVisible(False)
        self._status_label.setVisible(False)
        show_error(msg, title="Erreur de génération", parent=self)

    # ------------------------------------------------------------------
    # Preview / export
    # ------------------------------------------------------------------

    @classmethod
    def _forget_preview_window(cls, preview_window: Any) -> None:
        logger.info(
            "GenericCVExportDialog: preview window forgotten id=%s",
            id(preview_window),
        )
        cls._OPEN_PREVIEW_WINDOWS = [
            window
            for window in cls._OPEN_PREVIEW_WINDOWS
            if window is not preview_window
        ]

    @classmethod
    def _track_preview_window(cls, preview_window: Any) -> None:
        logger.info(
            "GenericCVExportDialog: preview window tracked id=%s",
            id(preview_window),
        )
        cls._OPEN_PREVIEW_WINDOWS.append(preview_window)
        preview_window.destroyed.connect(
            lambda *_args, window=preview_window, dialog_cls=cls: dialog_cls._forget_preview_window(
                window
            )
        )

    def done(self, result: int) -> None:
        preview_payload = dict(self._pending_preview_payload or {})
        self._pending_preview_payload = {}
        preview_owner = self.parent()
        super().done(result)

        accepted = (
            result == int(QDialog.DialogCode.Accepted)
            or result == QDialog.DialogCode.Accepted
        )
        if accepted and preview_payload:
            self.__class__._schedule_preview_window(preview_payload, preview_owner)

    @classmethod
    def _schedule_preview_window(
        cls,
        preview_data: Dict[str, Any],
        preview_owner: Any = None,
    ) -> None:
        preview_payload = dict(preview_data or {})

        def _open_preview() -> None:
            cls._open_preview_window(preview_payload, preview_owner)

        QTimer.singleShot(0, _open_preview)

    @classmethod
    def _open_preview_window(
        cls,
        preview_data: Dict[str, Any],
        preview_owner: Any = None,
    ) -> None:
        try:
            from app.views.template_preview_window import TemplatePreviewWindow
        except Exception as exc:
            logger.warning(
                "GenericCVExportDialog: preview window unavailable after dialog close: %s",
                exc,
            )
            return

        preview_payload = dict(preview_data or {})
        try:
            preview_window = TemplatePreviewWindow(preview_payload, None)
            preview_window.setWindowFlag(Qt.Window, True)
            cls._attach_preview_navigation_context(preview_window, preview_owner)
            cls._track_preview_window(preview_window)
            logger.info(
                "GenericCVExportDialog: opening preview window id=%s template=%s",
                id(preview_window),
                preview_payload.get("template")
                or preview_payload.get("template_used")
                or "",
            )
            preview_window.showNormal()
            preview_window.raise_()
            preview_window.activateWindow()
        except Exception as exc:
            logger.exception(
                "GenericCVExportDialog: failed to open preview window after dialog close: %s",
                exc,
            )
            show_error(
                f"Impossible d'ouvrir la prévisualisation du CV.\n\n{exc}",
                title="Erreur de prévisualisation",
                parent=None,
            )

    def _selected_language_code(self) -> str:
        return str(self._lang_combo.currentData() or "fr").strip() or "fr"

    @staticmethod
    def _attach_preview_navigation_context(
        preview_window: Any,
        preview_owner: Any,
    ) -> None:
        history_widget = None
        main_window = None
        candidate = preview_owner

        if candidate is not None and hasattr(candidate, "open_editor_for_application"):
            history_widget = candidate
        if candidate is not None and hasattr(candidate, "history_widget"):
            main_window = candidate
        elif candidate is not None and hasattr(candidate, "main_window"):
            main_window = getattr(candidate, "main_window", None)
        elif candidate is not None:
            try:
                owner_window = candidate.window()
            except Exception:
                owner_window = None
            if owner_window is not None and hasattr(owner_window, "history_widget"):
                main_window = owner_window

        if history_widget is None and main_window is not None:
            history_widget = getattr(main_window, "history_widget", None)

        if history_widget is not None:
            setattr(preview_window, "_history_widget_context", history_widget)
        if main_window is not None:
            setattr(preview_window, "_main_window_context", main_window)

    def _selected_model_id(self) -> str:
        try:
            return str(self._model_selector.get_current_model() or "").strip()
        except Exception:
            return ""

    def _history_job_title(self) -> str:
        if self._selected_language_code().startswith("en"):
            return "Generic CV"
        return "CV Générique"

    def _history_company(self) -> str:
        return "N/A"

    def _history_model_label(self) -> str:
        selected_model = self._selected_model_id()
        if selected_model:
            return selected_model[:20]
        if self._profile_model_version:
            return self._profile_model_version[:20]
        return "generic"

    def _refresh_history_views(self) -> None:
        parent = self.parent()
        candidates = [parent]
        if parent is not None:
            try:
                candidates.append(parent.window())
            except Exception:
                pass

        for candidate in candidates:
            if candidate is None:
                continue
            refresh_history = getattr(candidate, "refresh_history", None)
            if callable(refresh_history):
                try:
                    refresh_history()
                except Exception as exc:
                    logger.warning(
                        "GenericCVExportDialog: history refresh failed: %s",
                        exc,
                    )
                return

    def _persist_generated_cv_in_history(
        self,
        *,
        cv_json: Dict[str, Any],
        preview_data: Dict[str, Any],
        template: str,
    ) -> Optional[int]:
        if not self._profile_id:
            logger.info(
                "GenericCVExportDialog: history persistence skipped (missing profile id)"
            )
            return None

        try:
            from app.controllers.main_window.history import HistoryCoordinator

            coordinator = HistoryCoordinator()
            summary = coordinator.create_generic_application(
                profile_id=self._profile_id,
                job_title=self._history_job_title(),
                company=self._history_company(),
                template_used=str(template or "modern").strip() or "modern",
                model_version_used=self._history_model_label(),
                generated_cv_markdown=str(preview_data.get("raw_content") or ""),
                profile_json=(
                    dict(self._profile_json)
                    if isinstance(self._profile_json, dict)
                    else None
                ),
                cv_json_final=dict(cv_json) if isinstance(cv_json, dict) else None,
                offer_analysis={
                    "generation_mode": "generic",
                    "language": self._selected_language_code(),
                },
                notes="Generated without a specific job offer.",
            )
        except Exception as exc:
            logger.warning(
                "GenericCVExportDialog: failed to persist generic CV in history: %s",
                exc,
            )
            return None

        if summary is None:
            return None

        self._refresh_history_views()
        return summary.id

    def _build_preview_payload(
        self,
        cv_json: Dict[str, Any],
        template: str,
    ) -> Dict[str, Any]:
        return build_generic_cv_preview_data(
            cv_json,
            language_code=self._selected_language_code(),
            template=template,
            photo_base64=_load_photo_base64(self._profile_photo_path),
        )

    def _queue_preview_window(self, preview_data: Dict[str, Any]) -> bool:
        try:
            from app.views.template_preview_window import TemplatePreviewWindow
        except Exception as exc:
            logger.warning(
                "GenericCVExportDialog: preview window unavailable, falling back to direct export: %s",
                exc,
            )
            return False

        self._pending_preview_payload = dict(preview_data or {})
        return True
