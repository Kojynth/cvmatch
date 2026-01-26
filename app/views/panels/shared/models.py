"""Simple data models shared across panels."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class PanelState:
    """Represents a serialisable snapshot of a panel."""

    identifier: str
    payload: dict[str, object] | None = None
