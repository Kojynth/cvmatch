"""Sidebar navigation panel extracted from the main window."""

from __future__ import annotations

from typing import Dict

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget, QFrame

from ...config import DEFAULT_PII_CONFIG
from ...logging.safe_logger import get_safe_logger
from ...models.user_profile import UserProfile
from ...utils.emoji_utils import get_display_text

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)

__all__ = ["SidebarPanel", "SidebarButton"]


class SidebarButton(QPushButton):
    """Custom button widget for sidebar entries."""

    def __init__(self, icon: str, text: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setText(f"{icon} {text}")
        self.setCheckable(True)
        self.setMinimumHeight(50)
        self.setStyleSheet(
            """
            QPushButton {
                text-align: left;
                padding: 10px 20px;
                border: none;
                background-color: transparent;
                color: #e0e0e0;
                font-size: 14px;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
                color: #ffffff;
            }
            QPushButton:checked {
                background-color: #0078d4;
                color: white;
                font-weight: bold;
            }
            """
        )


class SidebarPanel(QWidget):
    """Navigation sidebar that broadcasts section changes."""

    section_changed = Signal(str)

    def __init__(self, profile: UserProfile, parent: QWidget | None = None):
        super().__init__(parent)
        self.profile = profile
        self.buttons: Dict[str, SidebarButton] = {}
        self.stats_text: QLabel | None = None
        self.user_info: QLabel | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout()
        layout.setSpacing(5)
        layout.setContentsMargins(10, 20, 10, 20)

        title = QLabel("CVMatch")
        title.setFont(QFont("Arial", 18, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #4db8ff; padding: 10px 0;")
        layout.addWidget(title)

        self.user_info = QLabel(self._user_label_text())
        self.user_info.setFont(QFont("Arial", 12))
        self.user_info.setAlignment(Qt.AlignCenter)
        self.user_info.setStyleSheet("color: #cccccc; padding-bottom: 20px;")
        layout.addWidget(self.user_info)

        sections = [
            (get_display_text("👤"), "Profil", "profile"),
            (get_display_text("📋"), "Nouvelle candidature", "job_application"),
            (get_display_text("🕘"), "Historique", "history"),
            (get_display_text("⚙️"), "Paramètres", "settings"),
        ]

        for icon, text, section_id in sections:
            button = SidebarButton(icon, text, self)
            button.clicked.connect(lambda checked=False, s=section_id: self.on_section_clicked(s))
            self.buttons[section_id] = button
            layout.addWidget(button)

        if "profile" in self.buttons:
            self.buttons["profile"].setChecked(True)
            QTimer.singleShot(100, lambda: self.section_changed.emit("profile"))

        layout.addStretch()

        stats_frame = QFrame()
        stats_frame.setFrameStyle(QFrame.Box)
        stats_frame.setStyleSheet(
            "background-color: #2a2a2a; border: 1px solid #404040; border-radius: 8px;"
        )
        stats_layout = QVBoxLayout(stats_frame)

        stats_title = QLabel(f"{get_display_text('📊')} Statistiques")
        stats_title.setFont(QFont("Arial", 10, QFont.Bold))
        stats_title.setStyleSheet("color: #e0e0e0;")
        stats_layout.addWidget(stats_title)

        self.stats_text = QLabel()
        self.stats_text.setFont(QFont("Arial", 9))
        self.stats_text.setStyleSheet("color: #cccccc;")
        stats_layout.addWidget(self.stats_text)
        self._refresh_stats()

        layout.addWidget(stats_frame)

        self.setLayout(layout)
        self.setFixedWidth(250)
        self.setStyleSheet("background-color: #1e1e1e; border-right: 1px solid #404040;")

    def _user_label_text(self) -> str:
        return f"{get_display_text('👤')} {self.profile.name}" if self.profile.name else f"{get_display_text('👤')} Profil"

    def _refresh_stats(self) -> None:
        if not self.stats_text:
            return

        total_generated = getattr(self.profile, "total_cvs_generated", 0) or 0
        average_rating = getattr(self.profile, "average_rating", 0.0) or 0.0
        model_version = getattr(self.profile, "model_version", None)
        model_label = getattr(model_version, "value", model_version) or "inconnu"

        stats = (
            f"CV générés: {total_generated}\n"
            f"Note moyenne: {average_rating:.1f} {get_display_text('⭐')}\n"
            f"Modèle: {model_label}"
        )
        self.stats_text.setText(stats)

    def on_section_clicked(self, section_id: str) -> None:
        self.set_active_section(section_id, emit=True)

    def set_active_section(self, section_id: str, *, emit: bool = False) -> None:
        for button_id, button in self.buttons.items():
            button.setChecked(button_id == section_id)
        if emit:
            self.section_changed.emit(section_id)

    def update_user_info(self, profile: UserProfile | None = None) -> None:
        if profile is not None:
            self.profile = profile

        if self.user_info is not None:
            self.user_info.setText(self._user_label_text())
        self._refresh_stats()

        logger.info("Sidebar updated for profile_id=%s", getattr(self.profile, "id", "unknown"))
