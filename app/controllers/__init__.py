"""
CVMatch Controllers Package
===========================

Lightweight package entrypoint with lazy exports.
"""

from __future__ import annotations

__all__ = [
    "CVGenerator",
    "ExportManager",
    "ProfileExtractionController",
]


def __getattr__(name: str):
    """
    Lazy-load heavy controller modules.

    This prevents pulling extraction/generation worker dependencies at startup
    when only lightweight coordinator modules are needed.
    """
    if name == "CVGenerator":
        from .cv_generator import CVGenerator

        return CVGenerator
    if name == "ExportManager":
        from .export_manager import ExportManager

        return ExportManager
    if name == "ProfileExtractionController":
        from .profile_extractor import ProfileExtractionController

        return ProfileExtractionController
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
