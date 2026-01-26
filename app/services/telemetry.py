"""Telemetry/logging facade placeholder."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class TelemetryService:
    """Wraps safe logging or analytics calls (stub)."""

    logger: object | None = None

    def info(self, message: str) -> None:
        """Log an informational message (stub)."""

        _ = message

