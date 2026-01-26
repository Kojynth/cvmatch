"""Validation helpers for panel state."""

from __future__ import annotations

from .models import PanelState


def validate_state(state: PanelState) -> bool:
    """Return True if the panel state looks usable."""

    return bool(state.identifier)
