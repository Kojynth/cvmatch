"""Dialog service abstraction used by UI panels and coordinators."""

from __future__ import annotations

from typing import Optional, Tuple

from app.widgets.dialog_manager import DialogManager

__all__ = [
    "show_success",
    "show_error",
    "show_warning",
    "show_info",
    "confirm",
    "open_file_dialog",
    "save_file_dialog",
    "show_extraction_success",
]


def show_success(message: str, *, title: str = "Succès", parent=None) -> int:
    """Display a success message."""

    return DialogManager.show_success(title, message, parent=parent)


def show_error(message: str, *, title: str = "Erreur", parent=None) -> int:
    """Display an error message."""

    return DialogManager.show_error(title, message, parent=parent)


def show_warning(message: str, *, title: str = "Attention", parent=None) -> int:
    """Display a warning message."""

    return DialogManager.show_warning(title, message, parent=parent)


def show_info(message: str, *, title: str = "Information", parent=None) -> int:
    """Display an informational dialog."""

    return DialogManager.show_success(title, message, parent=parent)


def confirm(message: str, *, title: str = "Confirmer", parent=None) -> bool:
    """Ask for user confirmation and return True when accepted."""

    return DialogManager.show_question(title, message, parent=parent)


def open_file_dialog(
    title: str,
    filters: str,
    *,
    directory: Optional[str] = None,
    parent=None,
) -> str:
    """Proxy to the dialog manager file picker."""

    return DialogManager.show_file_dialog(title, filters, directory=directory, parent=parent)


def save_file_dialog(
    title: str,
    filters: str,
    *,
    default_name: str = "",
    directory: Optional[str] = None,
    parent=None,
) -> str:
    """Proxy to the dialog manager save picker."""

    return DialogManager.show_save_dialog(
        title,
        filters,
        default_name=default_name,
        directory=directory,
        parent=parent,
    )


def show_extraction_success(
    message: str,
    *,
    title: str = "Extraction terminée",
    action_text: str = "Visualiser les détails",
    parent=None,
) -> Tuple[int, bool]:
    """
    Affiche un dialogue de succès d'extraction avec bouton d'action optionnel.

    Ce dialogue est utilisé après une extraction CV ou LinkedIn pour informer
    l'utilisateur du succès et lui proposer d'ouvrir immédiatement l'éditeur
    de détails pour vérifier l'exactitude des données extraites.

    Args:
        message: Message principal décrivant le résultat de l'extraction
        title: Titre du dialogue
        action_text: Texte du bouton d'action (par défaut: "Visualiser les détails")
        parent: Widget parent

    Returns:
        Tuple (result_code, action_requested)
        action_requested est True si l'utilisateur a cliqué sur le bouton d'action
    """
    return DialogManager.show_extraction_success(
        title, message, action_text=action_text, parent=parent
    )

