"""Progress dialog management service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

try:
    from app.views.model_loading_dialog import ModelLoadingDialog
except Exception:  # pragma: no cover - dialog optional in headless tests
    ModelLoadingDialog = None  # type: ignore


CancelCallback = Callable[[], None]


@dataclass(slots=True)
class ProgressService:
    """
    Manage the lifecycle of the ML progress dialog.

    The implementation degrades gracefully when the rich dialog is not
    available (e.g., in headless or test environments).
    """

    dialog_factory: Optional[Callable[..., object]] = None
    _dialog_factory: Optional[Callable[..., object]] = None
    _dialog: Optional[object] = None
    _parent: Optional[object] = None
    _cancel_callback: Optional[CancelCallback] = None

    def __post_init__(self) -> None:
        self._dialog_factory = self.dialog_factory or ModelLoadingDialog
        self._dialog = None
        self._parent = None
        self._cancel_callback = None

    def set_parent(self, parent: object | None) -> None:
        """Remember the parent widget for upcoming dialogs."""

        self._parent = parent

    def set_cancel_callback(self, callback: CancelCallback | None) -> None:
        """Register a callback invoked when the user cancels the dialog."""

        self._cancel_callback = callback
        if self._dialog and hasattr(self._dialog, "cancel_clicked"):
            try:
                self._dialog.cancel_clicked.disconnect()  # type: ignore[attr-defined]
            except Exception:
                pass
            if callback is not None:
                self._dialog.cancel_clicked.connect(callback)  # type: ignore[attr-defined]

    def show(self, status: str | None = None) -> None:
        """Display the progress dialog."""

        if self._dialog_factory is None:
            return

        self._dialog = self._dialog_factory(self._parent)  # type: ignore[call-arg]
        if self._cancel_callback and hasattr(self._dialog, "cancel_clicked"):
            self._dialog.cancel_clicked.connect(self._cancel_callback)  # type: ignore[attr-defined]
        if status and hasattr(self._dialog, "set_status"):
            self._dialog.set_status(status)  # type: ignore[attr-defined]
        if hasattr(self._dialog, "show"):
            self._dialog.show()  # type: ignore[attr-defined]

    def set_status(self, text: str) -> None:
        """Update the short status message."""

        if self._dialog and hasattr(self._dialog, "set_status"):
            self._dialog.set_status(text)  # type: ignore[attr-defined]

    def append_log(self, line: str) -> None:
        """Append a log line to the dialog."""

        if self._dialog and hasattr(self._dialog, "append_log"):
            self._dialog.append_log(line)  # type: ignore[attr-defined]

    def set_cancel_enabled(self, enabled: bool) -> None:
        """Enable or disable the cancel action."""

        if self._dialog and hasattr(self._dialog, "set_cancel_enabled"):
            self._dialog.set_cancel_enabled(enabled)  # type: ignore[attr-defined]

    def close(self) -> None:
        """Close and dispose of the dialog."""

        if self._dialog and hasattr(self._dialog, "close"):
            self._dialog.close()  # type: ignore[attr-defined]
        self._dialog = None
