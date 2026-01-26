"""Dialog orchestration service facade."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from . import dialogs as dialog_api


@dataclass(slots=True)
class DialogService:
    """Lightweight wrapper around the dialog manager helpers."""

    default_parent: object | None = None

    def set_parent(self, parent: object | None) -> None:
        """Remember the default parent widget for dialogs."""

        self.default_parent = parent

    def info(self, message: str, *, title: str = "Information", parent: object | None = None) -> int:
        """Display an informational message."""

        return dialog_api.show_info(
            message,
            title=title,
            parent=self._resolve_parent(parent),
        )

    def success(self, message: str, *, title: str = "Succès", parent: object | None = None) -> int:
        """Display a success message."""

        return dialog_api.show_success(
            message,
            title=title,
            parent=self._resolve_parent(parent),
        )

    def warning(self, message: str, *, title: str = "Attention", parent: object | None = None) -> int:
        """Display a warning dialog."""

        return dialog_api.show_warning(
            message,
            title=title,
            parent=self._resolve_parent(parent),
        )

    def error(self, message: str, *, title: str = "Erreur", parent: object | None = None) -> int:
        """Display an error dialog."""

        return dialog_api.show_error(
            message,
            title=title,
            parent=self._resolve_parent(parent),
        )

    def confirm(self, message: str, *, title: str = "Confirmer", parent: object | None = None) -> bool:
        """Ask the user to confirm an action."""

        return dialog_api.confirm(
            message,
            title=title,
            parent=self._resolve_parent(parent),
        )

    def open_file_dialog(
        self,
        title: str,
        filters: str,
        *,
        directory: Optional[str] = None,
        parent: object | None = None,
    ) -> str:
        """Open a file picker dialog."""

        return dialog_api.open_file_dialog(
            title,
            filters,
            directory=directory,
            parent=self._resolve_parent(parent),
        )

    def save_file_dialog(
        self,
        title: str,
        filters: str,
        *,
        default_name: str = "",
        directory: Optional[str] = None,
        parent: object | None = None,
    ) -> str:
        """Open a save file picker dialog."""

        return dialog_api.save_file_dialog(
            title,
            filters,
            default_name=default_name,
            directory=directory,
            parent=self._resolve_parent(parent),
        )

    def _resolve_parent(self, parent: object | None) -> object | None:
        """Return the explicit parent or the stored default."""

        return parent if parent is not None else self.default_parent
