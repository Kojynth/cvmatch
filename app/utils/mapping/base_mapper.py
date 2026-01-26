"""Shared utilities for modular extraction mapping."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config" / "mapping_rules"


@lru_cache(maxsize=None)
def load_mapping_rules(filename: str) -> Dict[str, Any]:
    """Load a JSON mapping rule file with caching."""
    path = CONFIG_DIR / filename
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def format_label(entry: Dict[str, Any] | None, fallback: str = "") -> str:
    """Combine emoji and label fields into a display string."""
    if not isinstance(entry, dict):
        return fallback

    emoji = (entry.get("emoji") or "").strip()
    label = (entry.get("label") or "").strip()

    if emoji and label:
        return f"{emoji} {label}"
    if emoji:
        return emoji
    if label:
        return label
    return fallback


__all__ = ["load_mapping_rules", "format_label"]
