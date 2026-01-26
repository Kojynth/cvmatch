"""Placeholder coordinator for LinkedIn ingestion logic."""

from __future__ import annotations

from .base import Coordinator, SimpleCoordinator


class LinkedInCoordinator(SimpleCoordinator, Coordinator):
    """Manages LinkedIn import flows and deduplication."""

    __slots__ = ()

    def __init__(self) -> None:
        super().__init__()

    def ingest_profile(self, url: str) -> None:
        """Trigger LinkedIn ingestion (stub)."""

        _ = url
