"""Dialog service abstraction used by UI panels and coordinators."""

from __future__ import annotations

from typing import Optional

from app.widgets.dialog_manager import DialogManager

__all__ = [
    "show_success",
    "show_error",
    "show_warning",
    "show_info",
    "confirm",
    "open_file_dialog",
    "save_file_dialog",
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

