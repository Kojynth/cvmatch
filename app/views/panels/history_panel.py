"""History panel extracted from the main window refactor."""

from __future__ import annotations

from typing import Iterable, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ...config import DEFAULT_PII_CONFIG
from ...logging.safe_logger import get_safe_logger
from ...models.job_application import ApplicationStatus
from ...models.user_profile import UserProfile
from ...controllers.main_window.history import HistoryCoordinator
from ...controllers.main_window.view_models import HistoryRowViewModel, JobApplicationSummary
from ...services.dialogs import show_error, show_info, show_success, show_warning, confirm

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)

try:  # pragma: no cover
    from ..template_preview_window import TemplatePreviewWindow
except ImportError:  # pragma: no cover
    TemplatePreviewWindow = None  # type: ignore

__all__ = ["HistoryPanel"]


class HistoryPanel(QWidget):
    """Table-based widget displaying generated applications."""

    profile_updated = Signal(UserProfile)

    def __init__(
        self,
        profile: UserProfile,
        coordinator: Optional[HistoryCoordinator] = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.profile = profile
        self.coordinator = coordinator or HistoryCoordinator()

        self._all_rows: List[HistoryRowViewModel] = []
        self._filtered_rows: List[HistoryRowViewModel] = []

        self._setup_ui()

        if getattr(self.profile, "id", None):
            self.refresh_history()

    def bind_profile(self, profile: UserProfile) -> None:
        """Attach a new profile and refresh the table."""

        self.profile = profile
        self.refresh_history()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        header_layout = QHBoxLayout()
        title = QLabel("🔙 Historique des candidatures")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        header_layout.addWidget(title)
        header_layout.addStretch()

        refresh_btn = QPushButton("🔄 Actualiser")
        refresh_btn.clicked.connect(self.refresh_history)
        header_layout.addWidget(refresh_btn)
        layout.addLayout(header_layout)

        filters_layout = QHBoxLayout()
        filters_layout.addWidget(QLabel("Filtrer par statut:"))

        self.status_filter = QComboBox()
        self.status_filter.addItems(["Tous", "Draft", "Envoyé", "Entretien", "Accepté", "Rejeté"])
        self.status_filter.currentTextChanged.connect(self.filter_applications)
        filters_layout.addWidget(self.status_filter)
        filters_layout.addStretch()
        layout.addLayout(filters_layout)

        self.table = QTableWidget()
        headers = ["Date", "Poste", "Entreprise", "Statut", "Note", "Template", "Actions"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setDefaultSectionSize(120)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.cellDoubleClicked.connect(self.view_application)
        layout.addWidget(self.table)

    # ------------------------------------------------------------------
    # Data binding
    # ------------------------------------------------------------------
    def bind_profile(self, profile: UserProfile) -> None:
        """Swap the active profile and refresh the table."""

        self.profile = profile
        self.refresh_history()
        self.profile_updated.emit(profile)

    def refresh_history(self) -> None:
        """Fetch summaries from the coordinator."""

        rows: List[HistoryRowViewModel] = []
        if getattr(self.profile, "id", None) is not None:
            try:
                rows = self.coordinator.list_application_rows(self.profile.id)
            except Exception as exc:  # pragma: no cover - defensive guard
                logger.error("Impossible de charger l'historique: %s", exc)
        self._all_rows = rows
        self.filter_applications(self.status_filter.currentText())

    def filter_applications(self, status_filter: str) -> None:
        """Filter summaries by status."""

        if status_filter == "Tous":
            self._filtered_rows = list(self._all_rows)
        else:
            normalized = status_filter.lower()
            self._filtered_rows = [
                row
                for row in self._all_rows
                if row.summary.status.value == normalized
            ]

        self._populate_table()

    def render_rows(self, rows: Iterable[HistoryRowViewModel]) -> None:
        """Render history rows provided by the coordinator."""

        self._all_rows = list(rows)
        self.filter_applications(self.status_filter.currentText())

    def _populate_table(self) -> None:
        self.table.setRowCount(len(self._filtered_rows))

        for row, row_model in enumerate(self._filtered_rows):
            summary = row_model.summary
            self.table.setItem(row, 0, QTableWidgetItem(row_model.display_created_at))
            self.table.setItem(row, 1, QTableWidgetItem(summary.job_title))
            self.table.setItem(row, 2, QTableWidgetItem(summary.company))

            status_item = QTableWidgetItem(row_model.display_status)
            if summary.status == ApplicationStatus.ACCEPTED:
                status_item.setBackground(Qt.GlobalColor.green)
            elif summary.status == ApplicationStatus.REJECTED:
                status_item.setBackground(Qt.GlobalColor.red)
            elif summary.status == ApplicationStatus.INTERVIEW:
                status_item.setBackground(Qt.GlobalColor.yellow)
            self.table.setItem(row, 3, status_item)

            rating = str(summary.user_rating) if summary.user_rating else "-"
            self.table.setItem(row, 4, QTableWidgetItem(rating))
            self.table.setItem(row, 5, QTableWidgetItem(row_model.display_template))

            actions_btn = QPushButton("⚙️")
            actions_btn.setMaximumWidth(36)
            actions_btn.clicked.connect(lambda _, r=row: self._show_actions_menu(r))
            self.table.setCellWidget(row, 6, actions_btn)

    # ------------------------------------------------------------------
    # Menu helpers
    # ------------------------------------------------------------------
    def _show_context_menu(self, position) -> None:
        if self.table.itemAt(position) is None:
            return
        row = self.table.currentRow()
        if row < 0:
            return
        self._show_actions_menu(row)

    def _show_actions_menu(self, row: int) -> None:
        summary = self._get_summary(row)
        if summary is None:
            return

        menu = QMenu(self)
        view_action = menu.addAction("👁️ Visualiser")
        edit_action = menu.addAction("✏️ Modifier le statut")
        export_action = menu.addAction("📤 Exporter")
        duplicate_action = menu.addAction("🗂️ Dupliquer")
        menu.addSeparator()
        delete_action = menu.addAction("🗑️ Supprimer")

        choice = menu.exec(self.table.viewport().mapToGlobal(self.table.visualItemRect(self.table.item(row, 0)).bottomLeft()))
        if choice == view_action:
            self.view_application(row, 0)
        elif choice == edit_action:
            self.edit_status(row)
        elif choice == export_action:
            self.export_application_to_preview(row)
        elif choice == duplicate_action:
            self.duplicate_application(row)
        elif choice == delete_action:
            self.delete_application(row)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _get_summary_by_id(self, application_id: int) -> Optional[JobApplicationSummary]:
        if not application_id:
            return None
        try:
            refreshed = self.coordinator.get_application_summary(application_id)
            if refreshed is not None:
                return refreshed
        except Exception as exc:
            logger.warning(f"Impossible de charger la candidature {application_id}: {exc}")
        for row in self._all_rows:
            if row.summary.id == application_id:
                return row.summary
        return None

    def _open_application_editor(self, summary: JobApplicationSummary) -> None:
        refreshed = self._get_summary_by_id(summary.id)
        if refreshed is not None:
            summary = refreshed
        dialog = QDialog(self)
        dialog.setWindowTitle(f"CV - {summary.job_title} chez {summary.company}")
        dialog.setMinimumSize(800, 600)

        layout = QVBoxLayout(dialog)
        tabs = QTabWidget()

        cv_markdown = summary.final_cv_markdown or summary.generated_cv_markdown or ""
        cv_html = summary.final_cv_html or summary.generated_cv_html
        if not cv_html and summary.cv_json_final:
            try:
                from ...utils.cv_json_renderer import cv_json_to_html

                cv_html = cv_json_to_html(
                    summary.cv_json_final, template=summary.template_used
                )
            except Exception as exc:
                logger.warning(f"CVHTML render failed for history view: {exc}")

        cv_text = QTextEdit()
        cv_text.setPlainText(cv_html or cv_markdown)
        cv_text.setAcceptRichText(False)
        tabs.addTab(cv_text, "CV")

        letter_text = QTextEdit()
        letter_text.setPlainText(
            summary.final_cover_letter or summary.generated_cover_letter or ""
        )
        letter_text.setAcceptRichText(False)
        tabs.addTab(letter_text, "Lettre")

        layout.addWidget(tabs)

        buttons_layout = QHBoxLayout()
        save_btn = QPushButton("Sauvegarder")
        buttons_layout.addWidget(save_btn)
        export_btn = QPushButton("Exporter en PDF")
        buttons_layout.addWidget(export_btn)

        close_btn = QPushButton("Fermer")
        close_btn.clicked.connect(dialog.close)
        buttons_layout.addStretch()
        buttons_layout.addWidget(close_btn)

        layout.addLayout(buttons_layout)

        def _collect_user_edits() -> tuple[Optional[str], Optional[str], str]:
            html_or_md = cv_text.toPlainText()
            cover_letter = letter_text.toPlainText()
            final_cv_html = None
            final_cv_markdown = None
            if html_or_md.lstrip().startswith("<"):
                final_cv_html = html_or_md
            else:
                final_cv_markdown = html_or_md
            return final_cv_html, final_cv_markdown, cover_letter

        def on_save() -> None:
            final_cv_html, final_cv_markdown, cover_letter = _collect_user_edits()
            updated = self.coordinator.save_user_edits(
                summary.id,
                final_cv_html=final_cv_html,
                final_cv_markdown=final_cv_markdown,
                final_cover_letter=cover_letter,
            )
            if updated is None:
                show_error(
                    "Impossible de sauvegarder les modifications.",
                    title="Erreur",
                    parent=dialog,
                )
                return
            show_success(
                "Modifications sauvegardees.",
                title="Sauvegarde",
                parent=dialog,
            )
            self.refresh_history()

        def on_export() -> None:
            final_cv_html, final_cv_markdown, cover_letter = _collect_user_edits()
            updated = self.coordinator.save_user_edits(
                summary.id,
                final_cv_html=final_cv_html,
                final_cv_markdown=final_cv_markdown,
                final_cover_letter=cover_letter,
            )
            if updated is None:
                show_error(
                    "Impossible de sauvegarder les modifications.",
                    title="Erreur",
                    parent=dialog,
                )
                return
            self.refresh_history()

            if not TemplatePreviewWindow:
                show_error(
                    "Fenetre de previsualisation indisponible.",
                    title="Erreur",
                    parent=dialog,
                )
                return

            try:
                cv_data = self._convert_summary_to_cv_data(updated)
                preview = TemplatePreviewWindow(cv_data, self)
                preview.show()
                dialog.close()
            except Exception as exc:
                logger.error("Export impossible: %s", exc)
                show_error(
                    f"Impossible d'exporter la candidature:\n{exc}",
                    title="Erreur",
                    parent=dialog,
                )

        save_btn.clicked.connect(on_save)
        export_btn.clicked.connect(on_export)
        dialog.exec()

    def open_editor_for_application(self, application_id: int) -> bool:
        summary = self._get_summary_by_id(application_id)
        if summary is None:
            return False
        self._open_application_editor(summary)
        return True

    def get_cv_data_for_application(self, application_id: int) -> Optional[dict]:
        summary = None
        try:
            summary = self.coordinator.get_application_summary(application_id)
        except Exception as exc:
            logger.warning(f"Impossible de rafraichir la candidature {application_id}: {exc}")
        if summary is None:
            summary = self._get_summary_by_id(application_id)
        if summary is None:
            return None
        return self._convert_summary_to_cv_data(summary)

    def view_application(self, row: int, _column: int) -> None:
        summary = self._get_summary(row)
        if summary is None:
            return
        self._open_application_editor(summary)

    def export_application_to_preview(self, row: int) -> None:
        summary = self._get_summary(row)
        if summary is None:
            return
        self.export_application_to_preview_by_id(summary.id)

    def export_application_to_preview_by_id(self, application_id: int) -> None:
        summary = self._get_summary_by_id(application_id)
        if summary is None:
            show_error(
                "Impossible d'exporter la candidature.",
                title="Erreur",
                parent=self,
            )
            return

        try:
            cv_data = self._convert_summary_to_cv_data(summary)
            if not TemplatePreviewWindow:
                raise RuntimeError("Fenetre de previsualisation indisponible")
            preview = TemplatePreviewWindow(cv_data, self)
            preview.show()
        except Exception as exc:
            logger.error("Export impossible: %s", exc)
            show_error(
                f"Impossible d'exporter la candidature:\n{exc}",
                title="Erreur",
                parent=self,
            )

    def edit_status(self, row: int) -> None:
        summary = self._get_summary(row)
        if summary is None:
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Modifier le statut")

        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(f"Candidature: {summary.job_title} chez {summary.company}"))

        status_combo = QComboBox()
        statuses = [
            ApplicationStatus.DRAFT,
            ApplicationStatus.SENT,
            ApplicationStatus.INTERVIEW,
            ApplicationStatus.ACCEPTED,
            ApplicationStatus.REJECTED,
        ]
        status_combo.addItems([status.value.title() for status in statuses])
        status_combo.setCurrentText(summary.status.value.title())
        layout.addWidget(status_combo)

        buttons = QHBoxLayout()
        save_btn = QPushButton("💾 Sauvegarder")
        cancel_btn = QPushButton("Annuler")
        buttons.addWidget(save_btn)
        buttons.addWidget(cancel_btn)
        layout.addLayout(buttons)

        def on_save() -> None:
            target = next(s for s in statuses if s.value.title() == status_combo.currentText())
            updated = self.coordinator.update_status(summary.id, target)
            if updated is None:
                show_error("Impossible de mettre à jour la candidature.", title="Erreur", parent=dialog)
                return
            self.refresh_history()
            dialog.accept()

        save_btn.clicked.connect(on_save)
        cancel_btn.clicked.connect(dialog.reject)
        dialog.exec()

    def duplicate_application(self, row: int) -> None:
        summary = self._get_summary(row)
        if summary is None:
            return

        duplicated = self.coordinator.duplicate_application(summary.id)
        if duplicated is None:
            show_error("Impossible de dupliquer la candidature.", title="Erreur", parent=self)
            return
        self.refresh_history()
        show_success("La candidature a été dupliquée avec succès.", title="Duplication", parent=self)

    def delete_application(self, row: int) -> None:
        summary = self._get_summary(row)
        if summary is None:
            return

        if not confirm(
            f"Supprimer la candidature pour {summary.job_title} chez {summary.company} ?",
            title="Confirmer la suppression",
            parent=self,
        ):
            return
            return

        if not self.coordinator.delete_application(summary.id):
            show_error("Impossible de supprimer la candidature.", title="Erreur", parent=self)
            return

        self.refresh_history()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_summary(self, row: int) -> Optional[JobApplicationSummary]:
        if row < 0 or row >= len(self._filtered_rows):
            return None
        return self._filtered_rows[row].summary

    def _convert_summary_to_cv_data(self, summary: JobApplicationSummary) -> dict:
        cv_markdown = summary.final_cv_markdown or summary.generated_cv_markdown or ""
        cv_html = summary.final_cv_html or summary.generated_cv_html

        data = {
            "name": getattr(self.profile, "name", "") or "Candidat",
            "email": getattr(self.profile, "email", "") or "",
            "phone": getattr(self.profile, "phone", "") or "",
            "linkedin_url": getattr(self.profile, "linkedin_url", "") or "",
            "job_title": summary.job_title,
            "company": summary.company,
            "template": summary.template_used,
            "application_id": summary.id,
            "raw_content": cv_markdown,
            "cover_letter": summary.final_cover_letter or summary.generated_cover_letter or "",
        }

        if summary.cv_json_final:
            try:
                from ...utils.cv_json_renderer import cv_json_to_cv_data

                structured = cv_json_to_cv_data(summary.cv_json_final)
                structured["raw_content"] = cv_markdown
                data.update(structured)
            except Exception as exc:
                logger.warning(f"CVJSON mapping failed for history preview: {exc}")

        if summary.final_cv_html:
            data["raw_html"] = summary.final_cv_html
        elif cv_html and not summary.cv_json_final:
            data["raw_html"] = cv_html

        return data
