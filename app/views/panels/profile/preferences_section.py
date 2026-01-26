from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QGroupBox, QSizePolicy


class PreferencesSection(QGroupBox):
    """Section des préférences (template, langue, apprentissage)."""

    def __init__(self, profile, parent=None):
        super().__init__("Préférences", parent)
        self.profile = profile
        self.template_combo = QComboBox()
        self.language_combo = QComboBox()
        self.learning_check = QCheckBox("Activer l'apprentissage continu")
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QFormLayout()
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(8)
        self.setContentsMargins(12, 12, 12, 12)

        # Populate with sensible defaults if empty
        if self.profile.preferred_template:
            self.template_combo.addItems([self.profile.preferred_template])
        else:
            self.template_combo.addItems(["modern", "classic", "tech", "creative"])

        if self.profile.preferred_language:
            self.language_combo.addItems([self.profile.preferred_language])
        else:
            self.language_combo.addItems(["fr", "en", "es", "de"])

        self.template_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.language_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.learning_check.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        layout.addRow("Modèle préféré:", self.template_combo)
        layout.addRow("Langue préférée:", self.language_combo)
        layout.addRow("", self.learning_check)
        self.setLayout(layout)
