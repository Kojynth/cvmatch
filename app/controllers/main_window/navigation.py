"""Placeholder coordinator for sidebar navigation."""

from __future__ import annotations

from .base import Coordinator, SimpleCoordinator


class NavigationCoordinator(SimpleCoordinator, Coordinator):
    """Switches between panels based on user interaction."""

    __slots__ = ()

    def __init__(self) -> None:
        super().__init__()

    def change_section(self, section: str) -> None:
        """Change the active section (stub)."""

        _ = section
