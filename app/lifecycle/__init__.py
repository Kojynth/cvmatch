"""Lifecycle helpers for the main window refactor."""

from __future__ import annotations

from importlib import import_module
from typing import Any

from .app_shutdown import (
    cleanup_application_resources,
    shutdown_application,
    shutdown_background_workers,
    shutdown_gui,
)
from .bootstrap import BootstrapArtifacts, create_main_window_environment

__all__ = [
    "BootstrapArtifacts",
    "LifecycleServices",
    "bootstrap_main_window",
    "cleanup_application_resources",
    "create_main_window_environment",
    "shutdown_application",
    "shutdown_background_workers",
    "shutdown_gui",
]


def __getattr__(name: str) -> Any:
    if name in {"LifecycleServices", "bootstrap_main_window"}:
        module = import_module("app.lifecycle.app_initializer")
        return getattr(module, name)
    raise AttributeError(f"module 'app.lifecycle' has no attribute {name!r}")
