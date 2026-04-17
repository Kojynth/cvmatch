"""
CVMatch Utils Package
====================

Keep package import side effects minimal.

Tests and lightweight callers import submodules from ``app.utils`` directly.
Importing parser dependencies from the package root makes those imports fail in
reduced environments such as the contract-test CI job. ``DocumentParser``
therefore stays available through a lazy attribute import instead of being
loaded eagerly at package import time.
"""

from __future__ import annotations

from typing import Any

__all__ = ["DocumentParser"]


def __getattr__(name: str) -> Any:
    if name == "DocumentParser":
        from .parsers import DocumentParser

        return DocumentParser
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
