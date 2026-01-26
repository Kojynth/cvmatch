"""
Gestionnaire de dialogues réutilisable pour toute l'application
===========================================================

Ce module centralise tous les dialogues pour garantir la cohérence.
"""

import os
import warnings

from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import QFileDialog, QMessageBox

try:
    # Normalize/sanitize UI texts to prevent mojibake in dialogs
    from app.utils.text_norm import normalize_text_for_ui  # type: ignore
except Exception:  # pragma: no cover
    normalize_text_for_ui = lambda s, fix_mojibake=True: s  # fallback no-op


class DialogManager:
    """Gestionnaire centralisé des dialogues pour l'application."""

    @staticmethod
    def show_success(title: str, message: str, parent=None) -> int:
        """Affiche un dialogue de succès."""
        # Sanitize texts to avoid mojibake/encoding artifacts
        safe_title = normalize_text_for_ui(title, fix_mojibake=True) if title else ""
        safe_message = (
            normalize_text_for_ui(message, fix_mojibake=True) if message else ""
        )
        msg = QMessageBox(parent)
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setWindowTitle(safe_title or "Information")
        msg.setText(safe_message or "")
        msg.setStyleSheet(
            """
            QMessageBox {
                background-color: #2d2d2d;
                color: white;
            }
            QMessageBox QPushButton {
                background-color: #28a745;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                min-width: 80px;
            }
            QMessageBox QPushButton:hover {
                background-color: #218838;
            }
        """
        )
        return msg.exec()

    @staticmethod
    def show_error(title: str, message: str, parent=None) -> int:
        """Affiche un dialogue d'erreur."""
        # Sanitize texts to avoid mojibake/encoding artifacts
        safe_title = normalize_text_for_ui(title, fix_mojibake=True) if title else ""
        safe_message = (
            normalize_text_for_ui(message, fix_mojibake=True) if message else ""
        )
        msg = QMessageBox(parent)
        msg.setIcon(QMessageBox.Icon.Critical)
        msg.setWindowTitle(safe_title or "Erreur")
        msg.setText(safe_message or "")
        msg.setStyleSheet(
            """
            QMessageBox {
                background-color: #2d2d2d;
                color: white;
            }
            QMessageBox QPushButton {
                background-color: #dc2626;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                min-width: 80px;
            }
            QMessageBox QPushButton:hover {
                background-color: #b91c1c;
            }
        """
        )
        return msg.exec()

    @staticmethod
    def show_warning(title: str, message: str, parent=None) -> int:
        """Affiche un dialogue d'avertissement."""
        # Sanitize texts to avoid mojibake/encoding artifacts
        safe_title = normalize_text_for_ui(title, fix_mojibake=True) if title else ""
        safe_message = (
            normalize_text_for_ui(message, fix_mojibake=True) if message else ""
        )
        msg = QMessageBox(parent)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle(safe_title or "Avertissement")
        msg.setText(safe_message or "")
        msg.setStyleSheet(
            """
            QMessageBox {
                background-color: #2d2d2d;
                color: white;
            }
            QMessageBox QPushButton {
                background-color: #ffc107;
                color: #000;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                min-width: 80px;
            }
            QMessageBox QPushButton:hover {
                background-color: #e0a800;
            }
        """
        )
        return msg.exec()

    @staticmethod
    def show_question(title: str, message: str, parent=None) -> bool:
        """Affiche un dialogue de confirmation (Oui/Non)."""
        # Sanitize texts to avoid mojibake/encoding artifacts
        safe_title = normalize_text_for_ui(title, fix_mojibake=True) if title else ""
        safe_message = (
            normalize_text_for_ui(message, fix_mojibake=True) if message else ""
        )
        msg = QMessageBox(parent)
        msg.setIcon(QMessageBox.Icon.Question)
        msg.setWindowTitle(safe_title or "Confirmation")
        msg.setText(safe_message or "")
        msg.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        msg.setDefaultButton(QMessageBox.StandardButton.No)
        msg.setStyleSheet(
            """
            QMessageBox {
                background-color: #2d2d2d;
                color: white;
            }
            QMessageBox QPushButton {
                background-color: #0078d4;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                min-width: 80px;
            }
            QMessageBox QPushButton:hover {
                background-color: #106ebe;
            }
        """
        )
        return msg.exec() == QMessageBox.StandardButton.Yes

    @staticmethod
    def show_extraction_success(
        title: str,
        message: str,
        action_text: str = "Visualiser les détails",
        parent=None,
    ) -> tuple:
        """
        Affiche un dialogue de succès d'extraction avec bouton d'action optionnel.

        Args:
            title: Titre du dialogue
            message: Message principal
            action_text: Texte du bouton d'action secondaire
            parent: Widget parent

        Returns:
            Tuple (result_code, action_requested)
            action_requested est True si l'utilisateur a cliqué sur le bouton d'action
        """
        # Sanitize texts to avoid mojibake/encoding artifacts
        safe_title = normalize_text_for_ui(title, fix_mojibake=True) if title else ""
        safe_message = (
            normalize_text_for_ui(message, fix_mojibake=True) if message else ""
        )
        safe_action = (
            normalize_text_for_ui(action_text, fix_mojibake=True)
            if action_text
            else "Visualiser"
        )

        msg = QMessageBox(parent)
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setWindowTitle(safe_title or "Extraction terminée")
        msg.setText(safe_message or "")

        # Bouton OK standard
        ok_button = msg.addButton(QMessageBox.StandardButton.Ok)

        # Bouton d'action personnalisé (Visualiser les détails)
        action_button = msg.addButton(safe_action, QMessageBox.ButtonRole.AcceptRole)

        msg.setStyleSheet(
            """
            QMessageBox {
                background-color: #2d2d2d;
                color: white;
            }
            QMessageBox QLabel {
                color: white;
                font-size: 13px;
                padding: 8px;
            }
            QMessageBox QPushButton {
                background-color: #6c757d;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                min-width: 80px;
                font-weight: normal;
            }
            QMessageBox QPushButton:hover {
                background-color: #5a6268;
            }
        """
        )

        # Style spécial pour le bouton d'action (vert, plus visible)
        action_button.setStyleSheet(
            """
            QPushButton {
                background-color: #2d5f3f;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
                min-width: 120px;
            }
            QPushButton:hover {
                background-color: #1e4f2f;
            }
        """
        )

        result = msg.exec()
        action_requested = msg.clickedButton() == action_button

        return (result, action_requested)

    @staticmethod
    def show_file_dialog(
        title: str, file_filters: str, directory: str = None, parent=None
    ) -> str:
        """
        Affiche un dialogue de sélection de fichier.

        Args:
            title: Titre du dialogue
            file_filters: Filtres de fichiers (ex: "Images (*.png *.jpg)")
            directory: Répertoire de départ
            parent: Widget parent

        Returns:
            Chemin du fichier sélectionné ou chaîne vide si annulé
        """
        if directory is None:
            directory = QStandardPaths.writableLocation(
                QStandardPaths.StandardLocation.DocumentsLocation
            )

        file_path, _ = QFileDialog.getOpenFileName(
            parent, title, directory, file_filters
        )

        return file_path if file_path else ""

    @staticmethod
    def show_save_dialog(
        title: str,
        file_filters: str,
        default_name: str = "",
        directory: str = None,
        parent=None,
    ) -> str:
        """
        Affiche un dialogue de sauvegarde de fichier.

        Args:
            title: Titre du dialogue
            file_filters: Filtres de fichiers
            default_name: Nom de fichier par défaut
            directory: Répertoire de départ
            parent: Widget parent

        Returns:
            Chemin de sauvegarde ou chaîne vide si annulé
        """
        if directory is None:
            directory = QStandardPaths.writableLocation(
                QStandardPaths.StandardLocation.DocumentsLocation
            )

        if default_name:
            full_path = os.path.join(directory, default_name)
        else:
            full_path = directory

        file_path, _ = QFileDialog.getSaveFileName(
            parent, title, full_path, file_filters
        )

        return file_path if file_path else ""

    @staticmethod
    def show_directory_dialog(title: str, directory: str = None, parent=None) -> str:
        """
        Affiche un dialogue de sélection de dossier.

        Args:
            title: Titre du dialogue
            directory: Répertoire de départ
            parent: Widget parent

        Returns:
            Chemin du dossier ou chaîne vide si annulé
        """
        if directory is None:
            directory = QStandardPaths.writableLocation(
                QStandardPaths.StandardLocation.DocumentsLocation
            )

        dir_path = QFileDialog.getExistingDirectory(parent, title, directory)

        return dir_path if dir_path else ""


# Fonctions utilitaires pour usage rapide
def show_success(title: str, message: str, parent=None):
    """⚠️ DEPRECATED: Old calling convention with title-first positional arguments.

    Use app.services.dialogs.show_success() instead with the new convention:
        show_success(message, *, title="...", parent=...)

    OLD (deprecated):
        show_success("Title", "Message", parent_widget)
    NEW (recommended):
        show_success("Message", title="Title", parent=parent_widget)
    """
    warnings.warn(
        "show_success(title, message, parent) is deprecated. "
        "Use show_success(message, *, title='Succès', parent=None) from app.services.dialogs instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return DialogManager.show_success(title, message, parent)


def show_error(title: str, message: str, parent=None):
    """⚠️ DEPRECATED: Old calling convention with title-first positional arguments.

    Use app.services.dialogs.show_error() instead with the new convention:
        show_error(message, *, title="...", parent=...)
    """
    warnings.warn(
        "show_error(title, message, parent) is deprecated. "
        "Use show_error(message, *, title='Erreur', parent=None) from app.services.dialogs instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return DialogManager.show_error(title, message, parent)


def show_warning(title: str, message: str, parent=None):
    """⚠️ DEPRECATED: Old calling convention with title-first positional arguments.

    Use app.services.dialogs.show_warning() instead with the new convention:
        show_warning(message, *, title="...", parent=...)
    """
    warnings.warn(
        "show_warning(title, message, parent) is deprecated. "
        "Use show_warning(message, *, title='Attention', parent=None) from app.services.dialogs instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return DialogManager.show_warning(title, message, parent)


def ask_confirmation(title: str, message: str, parent=None) -> bool:
    """⚠️ DEPRECATED: Old calling convention with title-first positional arguments.

    Use app.services.dialogs.confirm() instead with the new convention:
        confirm(message, *, title="...", parent=...)
    """
    warnings.warn(
        "ask_confirmation(title, message, parent) is deprecated. "
        "Use confirm(message, *, title='Confirmer', parent=None) from app.services.dialogs instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return DialogManager.show_question(title, message, parent)


def select_file(title: str, file_filters: str, parent=None) -> str:
    """Raccourci pour sélectionner un fichier."""
    return DialogManager.show_file_dialog(title, file_filters, parent=parent)


def save_file(
    title: str, file_filters: str, default_name: str = "", parent=None
) -> str:
    """Raccourci pour sauvegarder un fichier."""
    return DialogManager.show_save_dialog(
        title, file_filters, default_name, parent=parent
    )


def select_directory(title: str, parent=None) -> str:
    """Raccourci pour sélectionner un dossier."""
    return DialogManager.show_directory_dialog(title, parent=parent)


def get_text_input(title: str, label: str, default_text: str = "", parent=None) -> str:
    """Demande une saisie de texte à l'utilisateur."""
    from PySide6.QtWidgets import QInputDialog

    text, ok = QInputDialog.getText(parent, title, label, text=default_text)
    return text if ok else ""


def get_link_input(parent=None) -> tuple:
    """Dialogue personnalisé pour ajouter un lien (nom + URL en une seule fenêtre)."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QDialog,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPushButton,
        QVBoxLayout,
    )

    dialog = QDialog(parent)
    dialog.setWindowTitle("Ajouter un lien")
    dialog.setModal(True)
    dialog.resize(400, 150)
    dialog.setStyleSheet(
        """
        QDialog {
            background-color: #2d2d2d;
            color: white;
        }
        QLineEdit {
            background: #3a3a3a;
            border: 1px solid #555;
            border-radius: 3px;
            padding: 5px;
            font-size: 12px;
        }
        QPushButton {
            background: #2d5f3f;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            font-weight: bold;
            min-width: 80px;
        }
        QPushButton:hover {
            background: #1e4f2f;
        }
        QPushButton#cancel {
            background: #6c757d;
        }
        QPushButton#cancel:hover {
            background: #5a6268;
        }
    """
    )

    layout = QVBoxLayout(dialog)

    # Champ nom
    layout.addWidget(QLabel("Nom du lien:"))
    name_edit = QLineEdit()
    name_edit.setPlaceholderText("Ex: Mon portfolio")
    layout.addWidget(name_edit)

    # Champ URL
    layout.addWidget(QLabel("URL:"))
    url_edit = QLineEdit()
    url_edit.setPlaceholderText("Ex: https://monsite.com")
    url_edit.setText("https://")
    layout.addWidget(url_edit)

    # Boutons
    buttons_layout = QHBoxLayout()
    buttons_layout.addStretch()

    cancel_btn = QPushButton("Annuler")
    cancel_btn.setObjectName("cancel")
    cancel_btn.clicked.connect(dialog.reject)
    buttons_layout.addWidget(cancel_btn)

    ok_btn = QPushButton("Ajouter")
    ok_btn.clicked.connect(dialog.accept)
    ok_btn.setDefault(True)
    buttons_layout.addWidget(ok_btn)

    layout.addLayout(buttons_layout)

    # Focus sur le champ nom
    name_edit.setFocus()

    if dialog.exec() == QDialog.DialogCode.Accepted:
        name = name_edit.text().strip()
        url = url_edit.text().strip()
        if name and url and url != "https://":
            return (name, url)

    return (None, None)
