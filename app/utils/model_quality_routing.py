"""Quality-oriented model override helpers for writer stages."""

from __future__ import annotations

from typing import Iterable, Optional


WRITER_STAGES = {"draft", "final", "cover_letter", "cover_letter_critic"}

LOW_QUALITY_WRITER_MODELS = {
    "qwen2-0.5b",
    "qwen2-1.5b",
    "qwen2-3b",
    "llama3.2-3b",
}

PREFERRED_WRITER_ORDER = (
    "qwen2-7b",
    "mistral-7b",
    "ministral-8b",
    "qwen2-3b",
)


def resolve_writer_quality_override(
    *,
    stage: str,
    current_model_id: str,
    available_model_ids: Iterable[str],
) -> Optional[str]:
    """Pick a better writer model when current one is known as low-quality."""
    stage_key = str(stage or "").strip().lower()
    current_key = str(current_model_id or "").strip().lower()
    available = {str(mid or "").strip().lower() for mid in (available_model_ids or []) if str(mid or "").strip()}

    if stage_key not in WRITER_STAGES:
        return None
    if not current_key:
        return None
    if current_key not in LOW_QUALITY_WRITER_MODELS:
        return None

    for candidate in PREFERRED_WRITER_ORDER:
        candidate_key = candidate.lower()
        if candidate_key in available and candidate_key != current_key:
            return candidate

    return None

