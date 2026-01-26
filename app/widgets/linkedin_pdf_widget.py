"""Widget pour la gestion de l''upload LinkedIn PDF."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFileDialog,
    QMessageBox,
    QFrame,
)

from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG
from ..utils.linkedin_pdf_manager import (
    store_linkedin_pdf,
    copy_for_download,
    remove_stored_pdf,
)

LOGGER = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


class LinkedInPdfUploadWidget(QWidget):
    """Widget dédié à l'import et la gestion du PDF LinkedIn."""

    pdf_changed = Signal(object)  # Emitted with (path, checksum, uploaded_at)
    help_requested = Signal()

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        profile_id: Optional[int] = None,
        initial_path: Optional[str] = None,
        checksum: Optional[str] = None,
        uploaded_at: Optional[datetime] = None,
        show_help: bool = True,
    ) -> None:
        super().__init__(parent)
        self._profile_id = profile_id
        self._current_path: Optional[str] = initial_path
        self._current_checksum: Optional[str] = checksum
        self._uploaded_at = uploaded_at

        self._build_ui(show_help)
        self._refresh_status()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self, show_help: bool) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Boutons d'action
        buttons_layout = QHBoxLayout()
        self._upload_button = QPushButton("📁 Parcourir…")
        self._upload_button.clicked.connect(self._select_pdf)
        buttons_layout.addWidget(self._upload_button)

        self._remove_button = QPushButton("🗑️ Supprimer")
        self._remove_button.clicked.connect(self._remove_pdf)
        buttons_layout.addWidget(self._remove_button)

        buttons_layout.addStretch()
        layout.addLayout(buttons_layout)

        # Statut du fichier
        self._status_label = QLabel("Aucun PDF LinkedIn importé")
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        # Boutons secondaires (actions sur le fichier)
        secondary_layout = QHBoxLayout()

        self._preview_button = QPushButton("👁️ Ouvrir")
        self._preview_button.clicked.connect(self._open_pdf)
        secondary_layout.addWidget(self._preview_button)

        self._download_button = QPushButton("💾 Télécharger")
        self._download_button.clicked.connect(self._download_pdf)
        secondary_layout.addWidget(self._download_button)

        secondary_layout.addStretch()
        layout.addLayout(secondary_layout)

        # Footer avec aide
        footer_layout = QHBoxLayout()
        footer_layout.addStretch()

        if show_help:
            self._help_button = QPushButton("❓ Comment récupérer le PDF ?")
            self._help_button.setFlat(True)
            self._help_button.clicked.connect(self.show_help_dialog)
            footer_layout.addWidget(self._help_button)
        else:
            self._help_button = None

        layout.addLayout(footer_layout)
        self._update_buttons_state()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set_profile_id(self, profile_id: Optional[int]) -> None:
        self._profile_id = profile_id

    def current_path(self) -> Optional[str]:
        return self._current_path

    def current_checksum(self) -> Optional[str]:
        return self._current_checksum

    def uploaded_at(self) -> Optional[datetime]:
        return self._uploaded_at

    def set_pdf_metadata(
        self,
        *,
        path: Optional[str],
        checksum: Optional[str] = None,
        uploaded_at: Optional[datetime] = None,
    ) -> None:
        self._current_path = path
        self._current_checksum = checksum
        self._uploaded_at = uploaded_at
        self._refresh_status()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _import_pdf(self, file_path: str) -> None:
        """Importe un PDF LinkedIn (utilisé par drag & drop et sélection manuelle)."""
        try:
            stored_path, checksum, uploaded_at = store_linkedin_pdf(file_path, self._profile_id)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Erreur import LinkedIn",
                f"Le fichier n'a pas pu être importé.\n\nDétail: {exc}"
            )
            LOGGER.error("Import PDF LinkedIn échoué | err=%s", exc)
            return
        self._current_path = stored_path
        self._current_checksum = checksum
        self._uploaded_at = uploaded_at
        self._refresh_status()
        self.pdf_changed.emit((stored_path, checksum, uploaded_at))

    def _select_pdf(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Sélectionner le PDF LinkedIn",
            "",
            "PDF (*.pdf)"
        )
        if not selected:
            return
        self._import_pdf(selected)

    def _open_pdf(self) -> None:
        if not self._current_path:
            QMessageBox.information(self, "Aucun fichier", "Aucun PDF LinkedIn n'est disponible.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(self._current_path))

    def _download_pdf(self) -> None:
        if not self._current_path:
            QMessageBox.information(self, "Aucun fichier", "Aucun PDF LinkedIn n'est disponible.")
            return
        dest, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Enregistrer le PDF LinkedIn",
            str(Path.home() / "linkedin_profile.pdf"),
            "PDF (*.pdf)"
        )
        if not dest:
            return
        try:
            copy_for_download(self._current_path, dest)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Téléchargement impossible",
                f"Le fichier n'a pas pu être copié.\n\nDétail: {exc}"
            )
            LOGGER.error("Téléchargement PDF LinkedIn échoué | err=%s", exc)

    def _remove_pdf(self) -> None:
        if not self._current_path:
            return
        response = QMessageBox.question(
            self,
            "Supprimer le PDF LinkedIn",
            "Voulez-vous supprimer le PDF LinkedIn stocké ?",
        )
        if response != QMessageBox.Yes:
            return
        remove_stored_pdf(self._current_path)
        self._current_path = None
        self._current_checksum = None
        self._uploaded_at = None
        self._refresh_status()
        self.pdf_changed.emit((None, None, None))

    def _refresh_status(self) -> None:
        if self._current_path:
            name = Path(self._current_path).name
            uploaded_str = (
                self._uploaded_at.strftime("%d/%m/%Y %H:%M")
                if isinstance(self._uploaded_at, datetime)
                else ""
            )
            checksum = self._current_checksum[:12] if self._current_checksum else ""
            text = f"<b>{name}</b>"
            if uploaded_str:
                text += f"<br><small>Importé le {uploaded_str}</small>"
            if checksum:
                text += f"<br><small>Hash: {checksum}</small>"
            self._status_label.setText(text)
        else:
            self._status_label.setText("Aucun PDF LinkedIn importé")
        self._update_buttons_state()

    def _update_buttons_state(self) -> None:
        has_pdf = bool(self._current_path)
        self._preview_button.setEnabled(has_pdf)
        self._download_button.setEnabled(has_pdf)
        self._remove_button.setEnabled(has_pdf)

    def show_help_dialog(self) -> None:
        """Affiche le tutoriel pour récupérer le PDF LinkedIn."""
        help_text = """
<h3>📖 Comment récupérer votre profil LinkedIn en PDF</h3>

<p>Pour importer votre profil LinkedIn dans CVMatch, vous devez d'abord
l'exporter depuis LinkedIn :</p>

<p><b>1️⃣ Connectez-vous à LinkedIn</b><br/>
→ Allez sur <a href="https://www.linkedin.com">www.linkedin.com</a></p>

<p><b>2️⃣ Accédez à votre profil</b><br/>
→ Cliquez sur votre photo en haut à droite<br/>
→ Sélectionnez "Voir le profil"</p>

<p><b>3️⃣ Exportez le PDF</b><br/>
→ Cliquez sur "Plus" (bouton avec 3 points ⋮)<br/>
→ Sélectionnez "Enregistrer au format PDF"<br/>
→ Le téléchargement démarre automatiquement</p>

<p><b>4️⃣ Importez dans CVMatch</b><br/>
→ Revenez ici<br/>
→ Cliquez sur "📁 Parcourir…"<br/>
→ Sélectionnez le fichier PDF téléchargé</p>
"""

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Aide - Export PDF LinkedIn")
        msg_box.setTextFormat(Qt.RichText)
        msg_box.setText(help_text)
        msg_box.setIcon(QMessageBox.Information)
        msg_box.setStandardButtons(QMessageBox.Ok)

        # Rendre les liens cliquables
        msg_box.setTextInteractionFlags(
            Qt.TextBrowserInteraction | Qt.LinksAccessibleByMouse
        )

        msg_box.exec()


__all__ = ["LinkedInPdfUploadWidget"]
