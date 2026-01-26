from __future__ import annotations

from typing import Callable

from PySide6.QtWidgets import QGroupBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QSizePolicy

from ....utils.emoji_utils import get_display_text
from ....widgets.style_manager import apply_button_style


class LinkedInSection(QGroupBox):
    """Section LinkedIn : statut et actions de synchronisation."""

    def __init__(self, profile, *, on_sync: Callable[[], None], on_extract_pdf: Callable[[], None], parent=None):
        super().__init__("LinkedIn", parent)
        self.profile = profile
        self.on_sync = on_sync
        self.on_extract_pdf = on_extract_pdf
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.sync_btn = QPushButton(f"{get_display_text('🔗')} Synchro LinkedIn")
        self.pdf_btn = QPushButton(f"{get_display_text('📄')} Extraire LinkedIn (PDF)")
        self._build_ui()
        self.update_status(profile)

    def _build_ui(self) -> None:
        layout = QVBoxLayout()
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(8)

        self.sync_btn.setObjectName("linkedin_sync_btn")
        self.sync_btn.clicked.connect(self.on_sync)
        actions_layout.addWidget(self.sync_btn)

        self.pdf_btn.setObjectName("linkedin_pdf_btn")
        apply_button_style(self.pdf_btn, "success")
        self.pdf_btn.clicked.connect(self.on_extract_pdf)
        actions_layout.addWidget(self.pdf_btn)
        actions_layout.addStretch()

        layout.addLayout(actions_layout)
        layout.addWidget(self.status_label)
        self.setLayout(layout)

    def update_status(self, profile) -> None:
        self.profile = profile
        if profile.linkedin_url:
            if getattr(profile, "linkedin_sync_status", None) == "success":
                apply_button_style(self.sync_btn, "success")
                status = "LinkedIn synchronisé"
            elif getattr(profile, "linkedin_sync_status", None) == "error":
                apply_button_style(self.sync_btn, "warning")
                status = "Erreur de synchronisation LinkedIn"
            else:
                apply_button_style(self.sync_btn, "info")
                status = "Prêt pour la synchronisation LinkedIn"
        else:
            apply_button_style(self.sync_btn, "secondary")
            status = "Aucune URL LinkedIn renseignée"
        self.status_label.setText(status)
