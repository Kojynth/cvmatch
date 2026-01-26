from __future__ import annotations

from typing import Callable

from PySide6.QtWidgets import QGroupBox, QHBoxLayout, QPushButton

from ....utils.emoji_utils import get_display_text
from ....widgets.style_manager import apply_button_style


class ActionsSection(QGroupBox):
    """Section pour les actions globales (sauvegarde / réinitialisation)."""

    def __init__(self, *, on_save: Callable[[], None], on_reset: Callable[[], None], parent=None):
        super().__init__("", parent)
        self.on_save = on_save
        self.on_reset = on_reset
        self.save_btn = QPushButton(f"{get_display_text('💾')} Sauvegarder")
        self.reset_btn = QPushButton(f"{get_display_text('↩️')} Annuler")
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout()
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(8)
        self.save_btn.clicked.connect(self.on_save)
        apply_button_style(self.save_btn, "primary")
        layout.addWidget(self.save_btn)

        self.reset_btn.clicked.connect(self.on_reset)
        layout.addWidget(self.reset_btn)

        layout.addStretch()
        self.setLayout(layout)

    @staticmethod
    def build_close_button(dialog):
        btn = QPushButton("Fermer", dialog)
        btn.clicked.connect(dialog.close)
        return btn
