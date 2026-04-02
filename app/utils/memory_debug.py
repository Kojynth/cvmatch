"""Lightweight memory snapshots for stage-by-stage diagnostics."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

try:
    from ..config import DEFAULT_PII_CONFIG
    from ..logging.safe_logger import get_safe_logger

    logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)
except ImportError:
    import logging

    logger = logging.getLogger(__name__)

try:
    import psutil
except Exception:  # pragma: no cover - optional dependency at runtime
    psutil = None  # type: ignore[assignment]

try:
    import torch

    TORCH_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency at runtime
    torch = None  # type: ignore[assignment]
    TORCH_AVAILABLE = False


def _format_gb(value: Optional[float]) -> str:
    if value is None:
        return "-"
    return f"{float(value):.2f}GB"


def collect_memory_snapshot(
    *,
    label: str,
    stage: str = "",
    attempt: Optional[int] = None,
    attempts: Optional[int] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Collect a compact process/system/CUDA memory snapshot for logs."""

    snapshot: Dict[str, Any] = {
        "label": str(label or "").strip(),
        "stage": str(stage or "").strip(),
        "attempt": attempt,
        "attempts": attempts,
        "pid": os.getpid(),
    }

    if psutil is not None:
        try:
            process = psutil.Process()
            snapshot["rss_gb"] = process.memory_info().rss / (1024**3)
        except Exception:
            snapshot["rss_gb"] = None
        try:
            vm = psutil.virtual_memory()
            snapshot["ram_available_gb"] = vm.available / (1024**3)
            snapshot["ram_used_pct"] = float(vm.percent)
        except Exception:
            snapshot["ram_available_gb"] = None
            snapshot["ram_used_pct"] = None
    else:
        snapshot["rss_gb"] = None
        snapshot["ram_available_gb"] = None
        snapshot["ram_used_pct"] = None

    if TORCH_AVAILABLE and torch is not None:
        try:
            cuda_available = bool(torch.cuda.is_available())
        except Exception:
            cuda_available = False
        snapshot["cuda_available"] = cuda_available
        if cuda_available:
            try:
                free_bytes, total_bytes = torch.cuda.mem_get_info()
                snapshot["vram_free_gb"] = free_bytes / (1024**3)
                snapshot["vram_total_gb"] = total_bytes / (1024**3)
            except Exception:
                snapshot["vram_free_gb"] = None
                snapshot["vram_total_gb"] = None
            try:
                snapshot["cuda_allocated_gb"] = torch.cuda.memory_allocated() / (
                    1024**3
                )
            except Exception:
                snapshot["cuda_allocated_gb"] = None
            try:
                snapshot["cuda_reserved_gb"] = torch.cuda.memory_reserved() / (1024**3)
            except Exception:
                snapshot["cuda_reserved_gb"] = None
        else:
            snapshot["vram_free_gb"] = None
            snapshot["vram_total_gb"] = None
            snapshot["cuda_allocated_gb"] = None
            snapshot["cuda_reserved_gb"] = None
    else:
        snapshot["cuda_available"] = False
        snapshot["vram_free_gb"] = None
        snapshot["vram_total_gb"] = None
        snapshot["cuda_allocated_gb"] = None
        snapshot["cuda_reserved_gb"] = None

    if isinstance(extra, dict):
        for key, value in extra.items():
            if value is None:
                continue
            snapshot[str(key)] = value

    return snapshot


def format_memory_snapshot(snapshot: Dict[str, Any]) -> str:
    """Format a memory snapshot into one stable log line."""

    parts = [
        "[MEMORY]",
        f"label={snapshot.get('label') or '-'}",
        f"stage={snapshot.get('stage') or '-'}",
        f"pid={snapshot.get('pid') or '-'}",
    ]
    attempt = snapshot.get("attempt")
    attempts = snapshot.get("attempts")
    if attempt is not None and attempts is not None:
        parts.append(f"attempt={attempt}/{attempts}")
    elif attempt is not None:
        parts.append(f"attempt={attempt}")

    parts.extend(
        [
            f"rss={_format_gb(snapshot.get('rss_gb'))}",
            f"ram_avail={_format_gb(snapshot.get('ram_available_gb'))}",
            f"ram_used={snapshot.get('ram_used_pct') if snapshot.get('ram_used_pct') is not None else '-'}%",
            f"vram_free={_format_gb(snapshot.get('vram_free_gb'))}",
            f"vram_total={_format_gb(snapshot.get('vram_total_gb'))}",
            f"cuda_alloc={_format_gb(snapshot.get('cuda_allocated_gb'))}",
            f"cuda_reserved={_format_gb(snapshot.get('cuda_reserved_gb'))}",
        ]
    )

    for key in sorted(snapshot.keys()):
        if key in {
            "label",
            "stage",
            "pid",
            "attempt",
            "attempts",
            "rss_gb",
            "ram_available_gb",
            "ram_used_pct",
            "vram_free_gb",
            "vram_total_gb",
            "cuda_allocated_gb",
            "cuda_reserved_gb",
            "cuda_available",
        }:
            continue
        parts.append(f"{key}={snapshot.get(key)}")

    return " ".join(parts)


def log_memory_snapshot(
    *,
    label: str,
    stage: str = "",
    attempt: Optional[int] = None,
    attempts: Optional[int] = None,
    extra: Optional[Dict[str, Any]] = None,
    logger_override: Any = None,
) -> Dict[str, Any]:
    """Collect and emit a memory snapshot log."""

    snapshot = collect_memory_snapshot(
        label=label,
        stage=stage,
        attempt=attempt,
        attempts=attempts,
        extra=extra,
    )
    active_logger = logger_override or logger
    try:
        active_logger.info(format_memory_snapshot(snapshot))
    except Exception:
        logger.info(format_memory_snapshot(snapshot))
    return snapshot
