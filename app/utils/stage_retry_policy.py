"""Retry policy helpers for stage subprocess execution."""

from __future__ import annotations


def get_extra_memory_retry_budget(stage: str) -> int:
    stage_key = str(stage or "").strip().lower()
    if stage_key in {"draft", "final", "cover_letter"}:
        return 2
    return 0


def should_extend_memory_retries(
    *,
    transient_memory_error: bool,
    memory_extensions_used: int,
    extra_memory_budget: int,
) -> bool:
    if not transient_memory_error:
        return False
    return int(memory_extensions_used) < int(extra_memory_budget)


def compute_memory_recovery_wait_seconds(memory_extensions_used: int) -> int:
    used = max(0, int(memory_extensions_used))
    return min(45, 10 + (used * 8))


def compute_retry_backoff_seconds(attempt: int) -> float:
    idx = max(1, int(attempt))
    return min(3.0, 0.5 * idx)

