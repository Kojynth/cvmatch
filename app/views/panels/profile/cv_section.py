from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtWidgets import QGroupBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QSizePolicy

from ....utils.emoji_utils import get_display_text
from ....widgets.style_manager import apply_button_style


class CvSection(QGroupBox):
    """Section CV de référence avec actions principales."""

    def __init__(
        self,
        profile,
        *,
        on_view_cv: Callable[[], None],
        on_replace_cv: Callable[[], None],
        on_extract_cv: Callable[[], None],
        on_view_details: Callable[[], None],
        parent=None,
    ):
        super().__init__("CV de référence", parent)
        self.profile = profile
        self.on_view_cv = on_view_cv
        self.on_replace_cv = on_replace_cv
        self.on_extract_cv = on_extract_cv
        self.on_view_details = on_view_details
        self.cv_info = QLabel()
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout()
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.update_cv_info(self.profile.master_cv_path)
        self.cv_info.setWordWrap(True)
        self.cv_info.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(self.cv_info)

        cv_buttons = QHBoxLayout()
        cv_buttons.setSpacing(8)
        replace_cv_btn = QPushButton(f"{get_display_text('📄')} Remplacer le CV")
        replace_cv_btn.clicked.connect(self.on_replace_cv)
        cv_buttons.addWidget(replace_cv_btn)

        view_cv_btn = QPushButton(f"{get_display_text('👁️')} Voir le contenu")
        view_cv_btn.clicked.connect(self.on_view_cv)
        cv_buttons.addWidget(view_cv_btn)
        cv_buttons.addStretch()
        layout.addLayout(cv_buttons)

        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(8)
        view_details_btn = QPushButton(f"{get_display_text('🔍')} Visualiser les détails")
        apply_button_style(view_details_btn, "info")
        view_details_btn.clicked.connect(self.on_view_details)
        actions_layout.addWidget(view_details_btn)

        extract_btn = QPushButton(f"{get_display_text('🔄')} Extraire le CV")
        apply_button_style(extract_btn, "info")
        extract_btn.clicked.connect(self.on_extract_cv)
        actions_layout.addWidget(extract_btn)
        actions_layout.addStretch()
        layout.addLayout(actions_layout)

        self.setLayout(layout)

    def update_cv_info(self, path: str | None) -> None:
        filename = Path(path).name if path else "Aucun"
        self.cv_info.setText(f"Fichier actuel: {filename}")
