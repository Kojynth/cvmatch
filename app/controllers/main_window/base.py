"""
Core interfaces and lightweight data structures for main window coordinators.

These stubs allow the refactor to evolve behind a stable contract. They are
pure-Python so they can be exercised in unit tests without importing PySide6.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(slots=True)
class CoordinatorContext:
    """Common dependencies shared by coordinators."""

    telemetry: object | None = None
    dialog_service: object | None = None
    progress_service: object | None = None


@runtime_checkable
class Coordinator(Protocol):
    """Minimal lifecycle surface expected from every coordinator."""

    def bind(self, context: CoordinatorContext) -> None:
        """Supply the shared coordinator context."""

    def teardown(self) -> None:
        """Release resources allocated during the session."""


class SimpleCoordinator:
    """Utility mixin implementing the Coordinator protocol."""

    def __init__(self) -> None:
        self._context: CoordinatorContext | None = None

    def bind(self, context: CoordinatorContext) -> None:
        self._context = context

    def teardown(self) -> None:
        self._context = None

    @property
    def context(self) -> CoordinatorContext | None:
        """Expose the currently bound context for subclasses."""

        return self._context
