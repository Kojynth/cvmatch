from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QSizePolicy

from ....widgets.phone_widget import create_phone_widget
from ....widgets.linkedin_pdf_widget import LinkedInPdfUploadWidget
from ....utils.emoji_utils import get_display_text
from ....utils import emoji_utils  # backward compat for get_display_text users


class PersonalInfoSection(QGroupBox):
    """Section regroupant les informations personnelles et l'upload LinkedIn PDF."""

    def __init__(self, profile, parent=None):
        super().__init__("Informations personnelles", parent)
        self.profile = profile
        self.name_edit = QLineEdit(profile.name)
        self.email_edit = QLineEdit(profile.email)
        self.phone_widget = create_phone_widget(profile.phone or "", "6 12 34 56 78", self)
        self.linkedin_edit = QLineEdit(profile.linkedin_url or "")
        self.linkedin_pdf_widget = LinkedInPdfUploadWidget(
            profile_id=profile.id,
            initial_path=getattr(profile, "linkedin_pdf_path", None),
            checksum=getattr(profile, "linkedin_pdf_checksum", None),
            uploaded_at=getattr(profile, "linkedin_pdf_uploaded_at", None),
        )
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QFormLayout()
        layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        layout.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        layout.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(8)
        self.setContentsMargins(12, 12, 12, 12)

        self.name_edit.setPlaceholderText("Nom complet")
        self.name_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addRow("Nom:", self.name_edit)

        self.email_edit.setPlaceholderText("Email")
        self.email_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addRow("Email:", self.email_edit)

        if hasattr(self.phone_widget, "setSizePolicy"):
            self.phone_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addRow("Téléphone:", self.phone_widget)

        linkedin_row = QHBoxLayout()
        self.linkedin_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        linkedin_row.addWidget(self.linkedin_edit, 1)

        linkedin_info = QLabel(
            f"{get_display_text('📄')} Utilisez l'URL comme secours. "
            "Importez le PDF exporté ci-dessous pour une synchronisation complète."
        )
        linkedin_info.setStyleSheet("color: #6c757d; font-size: 11px; font-style: italic;")
        linkedin_info.setWordWrap(True)

        linkedin_col = QVBoxLayout()
        linkedin_col.setSpacing(6)
        linkedin_col.addLayout(linkedin_row)
        linkedin_col.addWidget(linkedin_info)
        linkedin_col.addWidget(self.linkedin_pdf_widget)

        container = QGroupBox()
        container.setContentsMargins(6, 6, 6, 6)
        container.setLayout(linkedin_col)
        layout.addRow("LinkedIn:", container)

        self.setLayout(layout)

    def set_linkedin_pdf_metadata(self) -> None:
        if not hasattr(self, "linkedin_pdf_widget"):
            return
        self.linkedin_pdf_widget.set_profile_id(self.profile.id)
        self.linkedin_pdf_widget.set_pdf_metadata(
            path=getattr(self.profile, "linkedin_pdf_path", None),
            checksum=getattr(self.profile, "linkedin_pdf_checksum", None),
            uploaded_at=getattr(self.profile, "linkedin_pdf_uploaded_at", None),
        )
