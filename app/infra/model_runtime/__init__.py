"""Model-runtime facade with lazy exports."""

from __future__ import annotations

from typing import Any

__all__ = ["QwenManager"]


def __getattr__(name: str) -> Any:
    if name == "QwenManager":
        from .qwen_manager import QwenManager

        return QwenManager
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
