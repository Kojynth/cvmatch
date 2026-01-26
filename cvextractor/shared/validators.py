"""Common validators shared by cvextractor modules."""

from __future__ import annotations

from typing import Any, Mapping, Sequence


def is_confident(
    candidate: Mapping[str, Any] | None, *, threshold: float = 0.5
) -> bool:
    """Return True when a candidate dictionary exposes sufficient confidence."""
    if not candidate:
        return False
    confidence = candidate.get("confidence")
    if confidence is None:
        return True  # Assume valid when the producer does not expose confidence yet.
    try:
        return float(confidence) >= threshold
    except (TypeError, ValueError):
        return False


def has_required_keys(candidate: Mapping[str, Any] | None, *keys: str) -> bool:
    """Return True when all required keys are present and truthy."""
    if not candidate:
        return False
    return all(candidate.get(key) for key in keys)


def non_empty_sequence(value: Sequence[Any] | None) -> bool:
    """Guard helper for list-like results."""
    return bool(value and len(value) > 0)
