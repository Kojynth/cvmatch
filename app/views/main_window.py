"""Slim main window that composes the refactored panels and coordinators."""

from __future__ import annotations

from typing import Dict, Optional, TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QCursor
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QMainWindow,
    QMenu,
    QMenuBar,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from ..config import DEFAULT_PII_CONFIG
from ..controllers.main_window.history import HistoryCoordinator
from ..controllers.main_window.job_applications import JobApplicationCoordinator
from ..controllers.main_window.ml_workflow import MlWorkflowCoordinator
from ..controllers.main_window.profile_state import ProfileStateCoordinator
from ..controllers.main_window.view_models import ProfileSnapshot
from ..lifecycle.app_shutdown import shutdown_gui
from ..logging.safe_logger import get_safe_logger
from ..models.user_profile import UserProfile
from .panels.history_panel import HistoryPanel
from .panels.job_application_panel import JobApplicationPanel
from .panels.profile import ProfilePanel
from .panels.sidebar_panel import SidebarPanel
from .settings_dialog import SettingsDialog

if TYPE_CHECKING:
    from ..lifecycle.app_initializer import LifecycleServices

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)

__all__ = ["MainWindowWithSidebar"]


class MainWindowWithSidebar(QMainWindow):
    """Main GUI shell that composes the refactored panels."""

    def __init__(
        self,
        profile: UserProfile,
        *,
        lifecycle: "LifecycleServices",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.profile: UserProfile = profile
        self.lifecycle = lifecycle

        # Coordinators / services
        self.profile_state_coordinator: ProfileStateCoordinator = lifecycle.profile_state
        self.job_application_coordinator: JobApplicationCoordinator = lifecycle.job_applications
        self.history_coordinator: HistoryCoordinator = lifecycle.history
        self.ml_workflow_coordinator: MlWorkflowCoordinator = lifecycle.ml_workflow
        self.progress_service = lifecycle.progress_service
        self.dialog_service = lifecycle.dialog_service
        self.telemetry_service = lifecycle.telemetry_service
        self.extraction_coordinator = lifecycle.extraction
        self.navigation_coordinator = lifecycle.navigation
        self.linkedin_coordinator = lifecycle.linkedin
        self.settings_coordinator = lifecycle.settings
        self._ml_current_extractor: object | None = None

        try:
            self.job_application_coordinator.bind_profile(profile)
        except Exception:
            self.job_application_coordinator.profile = profile  # type: ignore[attr-defined]

        try:
            self.progress_service.set_parent(self)
        except Exception:
            pass
        try:
            self.dialog_service.set_parent(self)
        except Exception:
            pass

        self.ml_workflow_coordinator.bind_view(
            parent=self,
            lock_ui=self._set_ui_locked,
            show_warning=self._show_warning,
            show_error=self._show_error,
            show_info=self._show_info,
        )

        # Snapshots / panels
        self.profile_snapshot: ProfileSnapshot = self.profile_state_coordinator.to_snapshot(profile)
        self.sidebar: SidebarPanel | None = None
        self.profile_container: QWidget | None = None
        self.profile_widget: ProfilePanel | None = None
        self.job_application_panel: JobApplicationPanel | None = None
        self.history_widget: HistoryPanel | None = None
        self.settings_widget: QWidget | None = None
        self.stacked_widget: QStackedWidget | None = None
        self.section_indices: Dict[str, int] = {}
        self.status_bar: QStatusBar | None = None

        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setup_ui()
        self.setup_connections()

    # ------------------------------------------------------------------ UI ------------------------------------------------------------------
    def setup_ui(self) -> None:
        self.setWindowTitle(f"CVMatch - {self.profile.name}")
        self.setMinimumSize(1280, 800)
        self.setup_menu_bar()

        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.sidebar = SidebarPanel(self.profile, parent=self)
        main_layout.addWidget(self.sidebar)

        self.stacked_widget = QStackedWidget(self)

        # Build profile container + supporting panels
        self._build_profile_container()

        self.job_application_panel = JobApplicationPanel(
            self.profile,
            parent=self,
            coordinator=self.job_application_coordinator,
        )
        if hasattr(self.job_application_panel, "apply_profile_snapshot"):
            self.job_application_panel.apply_profile_snapshot(self.profile_snapshot)

        self.history_widget = HistoryPanel(
            self.profile,
            coordinator=self.history_coordinator,
            parent=self,
        )
        self.history_widget.render_rows(
            self.history_coordinator.list_application_rows(self.profile.id)
            if getattr(self.profile, "id", None)
            else []
        )

        self.settings_widget = self._build_settings_placeholder()

        # Stacked widget wiring
        self.stacked_widget.addWidget(self.profile_container)
        self.stacked_widget.addWidget(self.job_application_panel)
        self.stacked_widget.addWidget(self.history_widget)
        self.stacked_widget.addWidget(self.settings_widget)

        self.section_indices = {
            "profile": 0,
            "job_application": 1,
            "history": 2,
            "settings": 3,
        }

        main_layout.addWidget(self.stacked_widget)
        if self.stacked_widget.count():
            self.stacked_widget.setCurrentIndex(0)

        self.status_bar = self.statusBar()
        self.status_bar.showMessage(f"Prêt - Modèle {getattr(self.profile.model_version, 'value', 'inconnu')}")

    def setup_menu_bar(self) -> None:
        menubar = QMenuBar(self)
        self.setMenuBar(menubar)

        ml_menu = QMenu("Machine Learning", self)
        menubar.addMenu(ml_menu)

        zero_shot_action = QAction("Activer Zero-shot", self, checkable=True, checked=True)
        ner_action = QAction("Activer NER router", self, checkable=True, checked=True)
        mock_action = QAction("Mode mock", self, checkable=True)
        lite_action = QAction("Mode Lite (CPU)", self, checkable=True)
        status_action = QAction("Statut ML…", self)

        zero_shot_action.triggered.connect(lambda state: self.toggle_zero_shot(state))
        ner_action.triggered.connect(lambda state: self.toggle_ner(state))
        mock_action.triggered.connect(lambda state: self.toggle_mock_mode(state))
        lite_action.triggered.connect(lambda state: self.toggle_lite_mode(state))
        status_action.triggered.connect(self.show_ml_status)

        ml_menu.addActions([zero_shot_action, ner_action, mock_action, lite_action])
        ml_menu.addSeparator()
        ml_menu.addAction(status_action)

        self.zero_shot_action = zero_shot_action
        self.ner_action = ner_action
        self.mock_action = mock_action
        self.lite_action = lite_action

    def setup_connections(self) -> None:
        if self.sidebar is not None:
            self.sidebar.section_changed.connect(self.change_section)

    # --------------------------------------------------------------- Coordinator helpers ----------------------------------------------------
    def _set_ui_locked(self, locked: bool) -> None:
        """Enable or disable interactive panels while background tasks run."""

        for widget in (
            self.profile_widget,
            self.job_application_panel,
            self.history_widget,
            self.sidebar,
        ):
            if widget is not None:
                widget.setDisabled(locked)

    def _show_warning(self, title: str, message: str) -> None:
        self.dialog_service.warning(message, title=title, parent=self)

    def _show_error(self, title: str, message: str) -> None:
        self.dialog_service.error(message, title=title, parent=self)

    def _show_info(self, title: str, message: str) -> None:
        self.dialog_service.info(message, title=title, parent=self)

    def _cancel_ml_worker(self, worker: object | None) -> None:
        if worker is None:
            return

        for method_name in ("requestInterruption", "cancel", "stop"):
            if hasattr(worker, method_name):
                try:
                    getattr(worker, method_name)()  # type: ignore[misc]
                    return
                except Exception:
                    continue

        if hasattr(worker, "ml_cancel_request"):
            try:
                setattr(worker, "ml_cancel_request", True)
            except Exception:
                pass

    def _connect_ml_signals(self, extractor: object | None) -> None:
        """
        Attach the ML workflow coordinator to the given extractor.

        Exposed for panels/tests that need to register long-running workers.
        """

        self._ml_current_extractor = extractor

        if extractor is None:
            self.ml_workflow_coordinator.attach_extractor(None)
            return

        self.ml_workflow_coordinator.attach_extractor(
            extractor,
            cancel_handler=lambda: self._cancel_ml_worker(extractor),
        )

    # ---------------------------------------------------------------- Panels helpers ---------------------------------------------------------
    def _build_profile_container(self) -> None:
        self.profile_container = QWidget(self)
        layout = QVBoxLayout(self.profile_container)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        self.profile_widget = ProfilePanel(self.profile, coordinator=self.profile_state_coordinator)
        self.profile_widget.render_profile(self.profile_snapshot)
        self.profile_widget.profile_updated.connect(self.on_profile_updated)
        layout.addWidget(self.profile_widget)
        layout.addStretch()

    def _build_settings_placeholder(self) -> QWidget:
        widget = QWidget(self)
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        title = QPushButton("Ouvrir les paramètres avancés…", widget)
        title.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        title.clicked.connect(self.open_advanced_settings)
        layout.addWidget(title)

        reset_button = QPushButton("⚠️ Réinitialiser l'application", widget)
        reset_button.setStyleSheet(
            "QPushButton {"
            "background-color: #b91c1c;"
            "color: white;"
            "padding: 8px 12px;"
            "border-radius: 6px;"
            "font-weight: bold;"
            "}"
            "QPushButton:hover { background-color: #dc2626; }"
        )
        reset_button.clicked.connect(self.reset_application)
        layout.addWidget(reset_button)

        layout.addStretch()
        return widget

    # ----------------------------------------------------------------- Actions --------------------------------------------------------------
    def change_section(self, section_id: str) -> None:
        try:
            self.navigation_coordinator.change_section(section_id)
        except Exception:
            logger.debug("Navigation coordinator change failed", exc_info=True)

        if self.sidebar is not None:
            self.sidebar.set_active_section(section_id, emit=False)

        if self.stacked_widget is None or section_id not in self.section_indices:
            return
        self.stacked_widget.setCurrentIndex(self.section_indices[section_id])
        section_names = {
            "profile": "Profil",
            "job_application": "Candidature",
            "history": "Historique",
            "settings": "Paramètres",
        }
        readable = section_names.get(section_id, section_id)
        self.setWindowTitle(f"CVMatch - {self.profile.name} - {readable}")

    def on_profile_updated(self, profile: UserProfile) -> None:
        snapshot = self.profile_state_coordinator.to_snapshot(profile)
        self.profile = profile
        self.profile_snapshot = snapshot
        self.job_application_coordinator.bind_profile(profile)

        if self.job_application_panel is not None:
            self.job_application_panel.profile = profile
            if hasattr(self.job_application_panel, "coordinator"):
                self.job_application_panel.coordinator.bind_profile(profile)
            if hasattr(self.job_application_panel, "apply_profile_snapshot"):
                self.job_application_panel.apply_profile_snapshot(snapshot)
        if self.history_widget is not None:
            self.history_widget.bind_profile(profile)
            rows = self.history_coordinator.list_application_rows(profile.id)
            self.history_widget.render_rows(rows)
        if self.profile_widget is not None:
            self.profile_widget.render_profile(snapshot)

        if self.status_bar is not None:
            self.status_bar.showMessage(
                f"Profil mis à jour - Modèle {getattr(profile.model_version, 'value', 'inconnu')}"
            )
        if self.sidebar is not None:
            self.sidebar.update_user_info(profile)

    def on_cv_generated(self, result: dict) -> None:
        if self.status_bar is not None:
            self.status_bar.showMessage("CV généré avec succès !")
        self.refresh_history()

    def refresh_history(self) -> None:
        if self.history_widget is None or getattr(self.profile, "id", None) is None:
            return
        rows = self.history_coordinator.list_application_rows(self.profile.id)
        self.history_widget.render_rows(rows)

    # --------------------------------------------------------------- ML toggles -------------------------------------------------------------
    def _toggle_zero_shot(self, enabled: bool) -> bool:
        success, message = self.ml_workflow_coordinator.toggle_zero_shot(enabled)
        if not success:
            self.dialog_service.warning(
                message or "Impossible de modifier le mode Zero-shot.",
                parent=self,
            )
        return success

    def _toggle_ner(self, enabled: bool) -> bool:
        success, message = self.ml_workflow_coordinator.toggle_ner(enabled)
        if not success:
            self.dialog_service.warning(
                message or "Impossible de modifier le routeur NER.",
                parent=self,
            )
        return success

    def _toggle_mock(self, enabled: bool) -> bool:
        success, message = self.ml_workflow_coordinator.toggle_mock_mode(enabled)
        if not success:
            self.dialog_service.warning(
                message or "Impossible de modifier le mode mock.",
                parent=self,
            )
        return success

    def _toggle_lite(self, enabled: bool) -> bool:
        success, message = self.ml_workflow_coordinator.toggle_lite_mode(enabled)
        if not success:
            self.dialog_service.warning(
                message or "Impossible de modifier le mode lite.",
                parent=self,
            )
        return success

    def _reset_ml_settings(self) -> None:
        success, message = self.ml_workflow_coordinator.reset_settings()
        if success:
            self.dialog_service.success("Paramètres ML réinitialisés.", parent=self)
        else:
            self.dialog_service.warning(
                message or "Impossible de réinitialiser les paramètres ML.",
                parent=self,
            )

    def reset_ml_settings(self) -> None:
        """Public wrapper used by menus/tests to trigger ML reset."""

        self._reset_ml_settings()

    def reset_application(self) -> None:
        """Expose the full application reset flow without dupe logic."""

        try:
            dialog = SettingsDialog(
                self.profile,
                parent=self,
                ml_coordinator=self.ml_workflow_coordinator,
            )
        except Exception as exc:
            logger.error("Erreur préparation réinitialisation: %s", exc)
            self._show_error(
                "Réinitialisation",
                "Impossible de préparer la réinitialisation complète.",
            )
            return

        dialog.reset_profile()

    def toggle_zero_shot(self, enabled: bool) -> bool:
        result = self._toggle_zero_shot(enabled)
        if hasattr(self, "zero_shot_action"):
            self.zero_shot_action.setChecked(enabled if result else not enabled)
        return result

    def toggle_ner(self, enabled: bool) -> bool:
        result = self._toggle_ner(enabled)
        if hasattr(self, "ner_action"):
            self.ner_action.setChecked(enabled if result else not enabled)
        return result

    def toggle_mock_mode(self, enabled: bool) -> bool:
        result = self._toggle_mock(enabled)
        if hasattr(self, "mock_action"):
            self.mock_action.setChecked(enabled if result else not enabled)
        return result

    def toggle_lite_mode(self, enabled: bool) -> bool:
        result = self._toggle_lite(enabled)
        if hasattr(self, "lite_action"):
            self.lite_action.setChecked(enabled if result else not enabled)
        return result

    def show_ml_status(self) -> None:
        success, message = self.ml_workflow_coordinator.status_summary()
        if success and message:
            self.dialog_service.info(message, title="Status Machine Learning", parent=self)
        else:
            self.dialog_service.warning(
                message or "Impossible d'afficher le status ML.",
                parent=self,
            )

    # ----------------------------------------------------------------- Close -----------------------------------------------------------------
    def closeEvent(self, event) -> None:  # type: ignore[override]
        try:
            if (
                hasattr(self, "profile_widget")
                and self.profile_widget is not None
                and hasattr(self.profile_widget, "has_unsaved_changes")
                and self.profile_widget.has_unsaved_changes()
            ):
                if not self.dialog_service.confirm(
                    "Vous avez des modifications non sauvegardées.\n\nSouhaitez-vous sauvegarder avant de quitter ?",
                    title="Modifications non sauvegardées",
                    parent=self,
                ):
                    # user cancelled save => continue closing without calling save
                    pass
                else:
                    try:
                        self.profile_widget.save_changes()  # type: ignore[attr-defined]
                    except Exception as exc:
                        logger.error("Erreur lors de la sauvegarde finale: %s", exc)

            try:
                self.ml_workflow_coordinator.teardown()
            except Exception as exc:
                logger.error("Erreur nettoyage ML: %s", exc)

            if hasattr(self.job_application_panel, "cleanup"):
                try:
                    self.job_application_panel.cleanup()  # type: ignore[attr-defined]
                except Exception as exc:
                    logger.error("Erreur nettoyage candidatures: %s", exc)

            self._shutdown_app_resources()
            event.accept()
            QApplication.quit()

        except Exception as exc:
            logger.error("Erreur lors de la fermeture: %s", exc)
            event.accept()
            QApplication.quit()

    def _shutdown_app_resources(self) -> None:
        shutdown_gui(
            coordinators=self.lifecycle.iter_coordinators(),
            job_application_coordinator=self.job_application_coordinator,
            progress_service=self.progress_service,
        )

    # ---------------------------------------------------------------- Utilities --------------------------------------------------------------
    def open_advanced_settings(self) -> None:
        try:
            dialog = SettingsDialog(
                self.profile,
                parent=self,
                ml_coordinator=self.ml_workflow_coordinator,
            )
        except Exception as exc:
            logger.error("Erreur ouverture paramètres avancés: %s", exc)
            self._show_error(
                "Paramètres",
                "Impossible d'ouvrir les paramètres avancés pour le moment.",
            )
            return

        result = dialog.exec()
        if result == QDialog.DialogCode.Accepted:
            self.on_profile_updated(self.profile)

    def refresh_progress_bar(self) -> None:
        """Legacy hook retained for compatibility."""
        pass


__all__ = ["MainWindowWithSidebar"]
