"""Placeholder panel for settings UI."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class SettingsPanel:
    """Pure data placeholder until the Qt widget is extracted."""

    name: str = "settings"
