"""Modal dialog shown while generating CV/cover letter."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QProgressBar, QVBoxLayout

from app.utils.text_norm import normalize_text_for_ui


class GenerationLoadingDialog(QDialog):
    """Blocking UI dialog with an indeterminate progress bar and a short status line."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Génération en cours")
        self.setWindowModality(Qt.ApplicationModal)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowCloseButtonHint)
        self.setFixedSize(420, 140)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self.status_label = QLabel("Fichier en cours de génération…")
        self.status_label.setWordWrap(True)
        self.status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.status_label.setStyleSheet(
            "font-weight: bold; font-size: 13px; margin-bottom: 4px;"
        )
        layout.addWidget(self.status_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # Indeterminate progress
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)

        self.setStyleSheet(
            """
            QDialog {
                background-color: #f5f5f5;
            }
            QLabel {
                color: #333;
            }
            QProgressBar {
                border: 2px solid grey;
                border-radius: 5px;
            }
            QProgressBar::chunk {
                background-color: #2E86AB;
                border-radius: 3px;
            }
            """
        )

    def set_status(self, text: str) -> None:
        """Update the short status line (kept compact)."""
        normalized = normalize_text_for_ui(text or "", fix_mojibake=True).strip()
        if len(normalized) > 140:
            normalized = f"{normalized[:140]}..."
        self.status_label.setText(normalized or "Fichier en cours de génération…")

    def closeEvent(self, event) -> None:  # pragma: no cover
        """Prevent the user from closing the dialog manually."""
        event.ignore()
