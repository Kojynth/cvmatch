"""Helpers to load cvextractor modular pipeline configuration."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict


@lru_cache(maxsize=1)
def _load_all() -> Dict[str, Any]:
    base_path = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "config"
        / "cvextractor"
        / "sections.json"
    )
    if not base_path.exists():
        return {}
    try:
        return json.loads(base_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def load_section_config(section: str) -> Dict[str, Any]:
    """Return the configuration dictionary for a given section."""
    return dict(_load_all().get(section, {}))


def load_all_sections() -> Dict[str, Any]:
    """Return the full cvextractor modular configuration."""
    return dict(_load_all())
