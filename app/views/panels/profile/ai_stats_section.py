from __future__ import annotations

from typing import Callable

from PySide6.QtWidgets import QGroupBox, QLabel, QPushButton, QVBoxLayout

from ....utils.emoji_utils import get_display_text


class AiStatsSection(QGroupBox):
    """Section affichant les statistiques IA et le retrain."""

    def __init__(self, profile, *, on_retrain: Callable[[], None], parent=None):
        super().__init__("Intelligence Artificielle", parent)
        self.profile = profile
        self.on_retrain = on_retrain
        self.info_label = QLabel()
        self.retrain_btn = QPushButton(f"{get_display_text('🔄')} Réentraîner le modèle")
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout()
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        self._refresh_info()
        self.info_label.setStyleSheet("color: #666;")
        layout.addWidget(self.info_label)

        self.retrain_btn.clicked.connect(self.on_retrain)
        layout.addWidget(self.retrain_btn)
        self.setLayout(layout)

    def _refresh_info(self) -> None:
        profile = self.profile
        self.info_label.setText(
            f"<b>Modèle actuel:</b> {getattr(profile, 'model_version', '') if hasattr(profile, 'model_version') else 'N/A'}<br>"
            f"<b>CV générés:</b> {getattr(profile, 'total_cvs_generated', 0)}<br>"
            f"<b>CV validés:</b> {getattr(profile, 'total_cvs_validated', 0)}<br>"
            f"<b>Note moyenne:</b> {getattr(profile, 'average_rating', 0):.1f}/5<br>"
            f"<b>Dernier fine-tuning:</b> {profile.last_fine_tuning.strftime('%d/%m/%Y') if getattr(profile, 'last_fine_tuning', None) else 'Jamais'}"
        )
