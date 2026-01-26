"""Placeholder implementation for the extraction coordinator."""

from __future__ import annotations

from .base import Coordinator, SimpleCoordinator


class ExtractionCoordinator(SimpleCoordinator, Coordinator):
    """Coordinates CV extraction workers once the refactor is complete."""

    __slots__ = ()

    def __init__(self) -> None:
        super().__init__()

    def start_extraction(self, *, profile_id: str) -> None:
        """Kick off the extraction workflow (stub)."""

        _ = profile_id  # Placeholder to avoid lint noise.
