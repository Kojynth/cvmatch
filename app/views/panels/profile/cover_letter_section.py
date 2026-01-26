from __future__ import annotations

from typing import Callable

from PySide6.QtWidgets import QGroupBox, QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout, QSizePolicy

from ....utils.emoji_utils import get_display_text


class CoverLetterSection(QGroupBox):
    """Section pour la lettre de motivation par défaut."""

    def __init__(self, profile, *, on_preview: Callable[[], None], on_changed: Callable[[], None], parent=None):
        super().__init__(f"{get_display_text('📝')} Lettre de motivation par défaut", parent)
        self.profile = profile
        self.on_preview = on_preview
        self.on_changed = on_changed
        self.cover_letter_edit = QTextEdit()
        self.cover_stats_label = QLabel(f"{get_display_text('📊')} 0 mots • 0 caractères • 0 lignes")
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout()
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        info = QLabel("Texte utilisé par défaut pour vos lettres de motivation générées.")
        info.setStyleSheet("color: #6c757d; font-size: 12px; margin-bottom: 10px;")
        layout.addWidget(info)

        self.cover_letter_edit.textChanged.connect(self.on_changed)
        self.cover_letter_edit.setMinimumHeight(200)
        self.cover_letter_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.cover_letter_edit)

        stats_layout = QHBoxLayout()
        stats_layout.addWidget(self.cover_stats_label)
        stats_layout.addStretch()

        preview_btn = QPushButton(f"{get_display_text('👁️')} Prévisualiser")
        preview_btn.clicked.connect(self.on_preview)
        stats_layout.addWidget(preview_btn)
        layout.addLayout(stats_layout)

        self.setLayout(layout)

    def set_text(self, text: str) -> None:
        self.cover_letter_edit.setPlainText(text or "")

    def get_text(self) -> str:
        return self.cover_letter_edit.toPlainText()

    def update_stats(self, words: int, chars: int, lines: int) -> None:
        self.cover_stats_label.setText(f"{get_display_text('📊')} {words} mots • {chars} caractères • {lines} lignes")
