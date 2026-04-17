"""
Generic CV Export Dialog
========================

Dialog that lets the user pick an LLM model and a CV template, then
generates a standalone professional CV PDF from the current profile
(no specific job offer).

Usage::

    dlg = GenericCVExportDialog(profile_json, parent=self)
    dlg.exec()
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Dict

from PySide6.QtCore import Qt
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

from app.services.dialogs import save_file_dialog, show_error, show_info
from app.widgets.style_manager import apply_button_style


class GenericCVExportDialog(QDialog):
    """Modal dialog for generating a generic CV PDF via LLM."""

    _TEMPLATES = ["modern", "tech", "classic", "creative", "minimal"]

    def __init__(
        self,
        profile_json: Dict[str, Any],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._profile_json = profile_json
        self._worker = None
        self._cv_json: Dict[str, Any] = {}
        self._cancelling = False

        # Build language options from the profile (dynamic) with FR/EN fallback
        try:
            from app.utils.multilang_cv_support import extract_profile_language_options
            self._language_options = extract_profile_language_options(profile_json)
        except Exception:
            self._language_options = [("fr", "Français"), ("en", "English")]

        self.setWindowTitle("Générer un CV PDF générique")
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

        # --- Title ---
        title = QLabel("Générer un CV PDF générique")
        title.setStyleSheet("font-size: 15px; font-weight: bold; color: #e0e0e0;")
        layout.addWidget(title)

        subtitle = QLabel(
            "Le LLM formatera votre profil en CV professionnel sans adaptation à une offre spécifique."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("font-size: 12px; color: #999; margin-bottom: 4px;")
        layout.addWidget(subtitle)

        layout.addWidget(self._make_separator())

        # --- LLM model selector ---
        layout.addWidget(QLabel("Modèle IA :"))
        from app.widgets.model_selector import CompactModelSelector

        self._model_selector = CompactModelSelector(parent=self)
        layout.addWidget(self._model_selector)

        layout.addWidget(self._make_separator())

        # --- Template selector ---
        template_row = QHBoxLayout()
        template_row.addWidget(QLabel("Template CV :"))
        self._template_combo = QComboBox()
        for name in self._TEMPLATES:
            self._template_combo.addItem(name.capitalize(), name)
        template_row.addWidget(self._template_combo)
        template_row.addStretch()
        layout.addLayout(template_row)

        # --- Language selector (dynamic from profile, fallback FR/EN) ---
        lang_row = QHBoxLayout()
        lang_row.addWidget(QLabel("Langue du CV :"))
        self._lang_combo = QComboBox()
        for code, label in self._language_options:
            self._lang_combo.addItem(label, code)
        lang_row.addWidget(self._lang_combo)
        lang_row.addStretch()
        layout.addLayout(lang_row)

        layout.addWidget(self._make_separator())

        # --- Progress area (hidden until generation starts) ---
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setVisible(False)
        layout.addWidget(self._progress_bar)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("font-size: 11px; color: #aaa;")
        self._status_label.setVisible(False)
        layout.addWidget(self._status_label)

        # --- Buttons ---
        btn_row = QHBoxLayout()
        self._cancel_btn = QPushButton("Annuler")
        apply_button_style(self._cancel_btn, "secondary")
        self._cancel_btn.clicked.connect(self._on_cancel)

        self._generate_btn = QPushButton("Générer et exporter le PDF")
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

        language_code = self._lang_combo.currentData() or "fr"
        model_id = ""
        try:
            model_id = str(self._model_selector.get_current_model() or "").strip()
        except Exception:
            model_id = ""

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
        # Safe shutdown: only close the dialog once the thread has actually stopped.
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    def _on_cancel(self) -> None:
        if self._worker and self._worker.isRunning():
            self._cancelling = True
            self._cancel_btn.setEnabled(False)
            self._status_label.setText("Annulation en cours...")
            self._worker.requestInterruption()
            self._worker.quit()
            # _on_worker_finished will call reject() once the thread stops.
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
        self._cv_json = cv_json
        template = self._template_combo.currentData() or "modern"
        self._export_pdf(cv_json, template)
        self._generate_btn.setEnabled(True)
        self._progress_bar.setVisible(False)
        self._status_label.setVisible(False)

    def _on_error(self, msg: str) -> None:
        self._generate_btn.setEnabled(True)
        self._progress_bar.setVisible(False)
        self._status_label.setVisible(False)
        show_error(msg, title="Erreur de génération", parent=self)

    # ------------------------------------------------------------------
    # PDF export
    # ------------------------------------------------------------------

    def _export_pdf(self, cv_json: dict, template: str) -> None:
        from app.controllers.export_manager import ExportManager

        today = date.today().strftime("%Y%m%d")
        default_name = f"CV_generique_{today}.pdf"
        export_dir = Path.cwd() / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)

        path = save_file_dialog(
            "Enregistrer le CV PDF",
            "PDF (*.pdf)",
            default_name=default_name,
            directory=str(export_dir),
            parent=self,
        )
        if not path:
            return

        try:
            manager = ExportManager()
            manager.export_cv(cv_json, template=template, output_format="pdf", output_path=path)
            show_info(
                f"CV exporté avec succès :\n{path}",
                title="Export réussi",
                parent=self,
            )
            self.accept()
        except Exception as exc:
            logger.exception("GenericCVExportDialog: PDF export error: %s", exc)
            show_error(
                f"Impossible d'exporter le PDF.\n\n{exc}",
                title="Erreur d'export",
                parent=self,
            )
