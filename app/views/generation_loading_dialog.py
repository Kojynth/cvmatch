"""Modal dialog shown while generating CV/cover letter."""

from __future__ import annotations

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import QDialog, QLabel, QProgressBar, QPushButton, QVBoxLayout

from app.utils.text_norm import normalize_text_for_ui


class GenerationLoadingDialog(QDialog):
    """Blocking UI dialog with an indeterminate progress bar and a short status line."""

    cancel_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Generation en cours")
        self.setWindowModality(Qt.ApplicationModal)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowCloseButtonHint)
        self.setFixedSize(420, 200)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self.status_label = QLabel()
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

        self.elapsed_label = QLabel()
        self.elapsed_label.setStyleSheet("font-size: 12px; color: #555;")
        layout.addWidget(self.elapsed_label)

        self.cancel_button = QPushButton("Arreter la generation")
        self.cancel_button.clicked.connect(self._on_cancel_clicked)
        layout.addWidget(self.cancel_button)

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

        self._base_status = "Fichier en cours de generation"
        self._dot_count = 0
        self._elapsed_seconds = 0
        self._animation_timer = QTimer(self)
        self._animation_timer.setInterval(450)
        self._animation_timer.timeout.connect(self._advance_status_animation)
        self._animation_timer.start()
        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(1000)
        self._elapsed_timer.timeout.connect(self._advance_elapsed)
        self._elapsed_timer.start()
        self._apply_animated_status()
        self._apply_elapsed_label()

    def set_status(self, text: str) -> None:
        """Update the short status line (kept compact)."""
        normalized = normalize_text_for_ui(text or "", fix_mojibake=True).strip()
        if len(normalized) > 140:
            normalized = f"{normalized[:140]}..."
        normalized = (normalized or "Fichier en cours de generation").rstrip(". ").rstrip("…")
        self._base_status = normalized or "Fichier en cours de generation"
        self._dot_count = 0
        self._apply_animated_status()

    def _advance_status_animation(self) -> None:
        self._dot_count = (self._dot_count + 1) % 4
        self._apply_animated_status()

    def _advance_elapsed(self) -> None:
        self._elapsed_seconds += 1
        self._apply_elapsed_label()

    def _apply_animated_status(self) -> None:
        suffix = "." * (self._dot_count + 1)
        self.status_label.setText(f"{self._base_status}{suffix}")

    def _apply_elapsed_label(self) -> None:
        minutes, seconds = divmod(self._elapsed_seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            elapsed = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            elapsed = f"{minutes:02d}:{seconds:02d}"
        self.elapsed_label.setText(f"Temps ecoule: {elapsed}")

    def _on_cancel_clicked(self) -> None:
        self.set_cancel_enabled(False, "Annulation en cours...")
        self.cancel_requested.emit()

    def set_cancel_enabled(self, enabled: bool, text: str | None = None) -> None:
        self.cancel_button.setEnabled(enabled)
        if text:
            self.cancel_button.setText(text)
            return
        self.cancel_button.setText("Arreter la generation" if enabled else "Annulation en cours...")

    def closeEvent(self, event) -> None:  # pragma: no cover
        """Prevent the user from closing the dialog manually."""
        event.ignore()

    def showEvent(self, event) -> None:  # pragma: no cover
        try:
            if not self._animation_timer.isActive():
                self._animation_timer.start()
            if not self._elapsed_timer.isActive():
                self._elapsed_timer.start()
        except Exception:
            pass
        super().showEvent(event)

    def hideEvent(self, event) -> None:  # pragma: no cover
        try:
            self._animation_timer.stop()
            self._elapsed_timer.stop()
        except Exception:
            pass
        super().hideEvent(event)
