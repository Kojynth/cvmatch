"""
CVMatch Workers Package
======================

Lazy exports for worker classes to avoid importing heavy LLM dependencies
at application startup.
"""

from __future__ import annotations

__all__ = [
    "CVGenerationWorker",
    "QwenManager",
    "ProfileParserWorker",
]


def __getattr__(name: str):
    if name in {"CVGenerationWorker", "QwenManager"}:
        from .llm_worker import CVGenerationWorker, QwenManager

        return {"CVGenerationWorker": CVGenerationWorker, "QwenManager": QwenManager}[name]
    if name == "ProfileParserWorker":
        from .profile_parser import ProfileParserWorker

        return ProfileParserWorker
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
