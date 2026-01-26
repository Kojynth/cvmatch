from typing import Optional

from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar, QPushButton
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCursor


class _MLProgressDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Traitement ML en cours...")
        self.setModal(True)
        self.setFixedSize(400, 160)
        self.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        self.phase_label = QLabel("Initialisation...")
        self.phase_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.phase_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)

        self.message_label = QLabel("")
        self.message_label.setAlignment(Qt.AlignCenter)
        self.message_label.setStyleSheet("color: #666; font-size: 9pt;")
        layout.addWidget(self.message_label)

    def update_phase(self, phase_name: str):
        self.phase_label.setText(phase_name)

    def update_progress(self, value: int):
        self.progress_bar.setValue(value)

    def update_message(self, message: str):
        self.message_label.setText(message)

    def reset(self):
        self.phase_label.setText("Initialisation...")
        self.progress_bar.setValue(0)
        self.message_label.setText("")


class MLDialogMixin:
    _ml_modal: Optional[QDialog] = None
    _ml_progress_dialog: Optional[_MLProgressDialog] = None
    _ml_connected_worker = None

    def _ui_lock(self, locked: bool):
        """Try to disable common UI elements while ML runs."""
        # Disable common action buttons if present
        for btn_name in ['replace_cv_btn', 'view_cv_btn', 'extract_button', 'edit_button']:
            if hasattr(self, btn_name):
                try:
                    getattr(self, btn_name).setEnabled(not locked)
                except Exception:
                    pass
        # Disable common edit fields if present
        for field_name in ['name_edit', 'email_edit', 'linkedin_edit']:
            if hasattr(self, field_name):
                try:
                    getattr(self, field_name).setEnabled(not locked)
                except Exception:
                    pass
        # Cursor feedback
        if locked:
            from PySide6.QtWidgets import QApplication
            QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        else:
            from PySide6.QtWidgets import QApplication
            QApplication.restoreOverrideCursor()

    def _ensure_ml_progress_dialog(self):
        if self._ml_progress_dialog is None:
            dlg = _MLProgressDialog(parent=self)
            flags = dlg.windowFlags()
            dlg.setWindowFlags(flags & ~Qt.WindowCloseButtonHint)
            self._ml_progress_dialog = dlg

    def _show_ml_progress_dialog(self, phase_text: str = "Initialisation..."):
        self._ensure_ml_progress_dialog()
        self._ml_progress_dialog.reset()
        self._ml_progress_dialog.update_phase(phase_text)
        self._ml_progress_dialog.update_progress(0)
        self._ml_progress_dialog.show()
        self._ml_progress_dialog.raise_()
        self._ml_progress_dialog.activateWindow()

    def _hide_ml_progress_dialog(self):
        if self._ml_progress_dialog is not None:
            self._ml_progress_dialog.close()

    def _connect_ml_signals(self, worker):
        if self._ml_connected_worker is not None:
            self._disconnect_ml_signals(self._ml_connected_worker)
        # Connect if attributes exist
        for sig, handler in [
            ('ml_started', self._on_ml_started),
            ('ml_finished', self._on_ml_finished),
            ('ml_failed', self._on_ml_failed),
            ('ml_phase', self._on_ml_phase),
            ('ml_progress', self._on_ml_progress),
            ('ml_stage', self._on_ml_stage),
            ('ml_log', self._on_ml_log),
        ]:
            if hasattr(worker, sig):
                try:
                    getattr(worker, sig).connect(handler)
                except Exception:
                    pass
        self._ml_connected_worker = worker

    def _disconnect_ml_signals(self, worker):
        if worker is None:
            return
        for sig, handler in [
            ('ml_started', self._on_ml_started),
            ('ml_finished', self._on_ml_finished),
            ('ml_failed', self._on_ml_failed),
            ('ml_phase', self._on_ml_phase),
            ('ml_progress', self._on_ml_progress),
            ('ml_stage', self._on_ml_stage),
            ('ml_log', self._on_ml_log),
        ]:
            if hasattr(worker, sig):
                try:
                    getattr(worker, sig).disconnect(handler)
                except Exception:
                    pass
        self._ml_connected_worker = None

    # Signal handlers
    def _on_ml_started(self):
        self._ui_lock(True)
        self._show_ml_progress_dialog("Initialisation...")

    def _on_ml_phase(self, phase_name: str):
        if self._ml_progress_dialog is not None:
            self._ml_progress_dialog.update_phase(phase_name)

    def _on_ml_progress(self, value: int):
        if self._ml_progress_dialog is not None:
            self._ml_progress_dialog.update_progress(int(value))

    def _on_ml_stage(self, message: str):
        if self._ml_progress_dialog is not None:
            short_msg = message[:140] + "..." if len(message) > 140 else message
            self._ml_progress_dialog.update_message(short_msg)

    def _on_ml_log(self, line: str):
        # Optional: if progress dialog has logging area in future
        pass

    def _on_ml_finished(self):
        self._ui_lock(False)
        QTimer.singleShot(250, self._hide_ml_progress_dialog)
        if self._ml_connected_worker is not None:
            self._disconnect_ml_signals(self._ml_connected_worker)

    def _on_ml_failed(self, error_message: str):
        self._ui_lock(False)
        self._hide_ml_progress_dialog()
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.critical(self, "Échec initialisation ML", error_message)
        if self._ml_connected_worker is not None:
            self._disconnect_ml_signals(self._ml_connected_worker)

