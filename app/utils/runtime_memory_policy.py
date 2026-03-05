"""
Runtime Memory Policy Module

Centralized system RAM management and memory pressure detection.
Extracted from QwenManager in llm_worker.py.

Key features:
- Low RAM profile detection (normal/tight/critical)
- Windows commit memory tracking
- Linux swap tracking
- Memory pressure detection for safe model loading
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional, Tuple

try:
    from ..logging.safe_logger import get_safe_logger
    from ..config import DEFAULT_PII_CONFIG
    logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


# Memory level thresholds
CRITICAL_RAM_THRESHOLD_GB = 1.5
CRITICAL_EFFECTIVE_THRESHOLD_GB = 2.0
TIGHT_RAM_THRESHOLD_GB = 6.0
TIGHT_EFFECTIVE_THRESHOLD_GB = 6.0

# Windows commit thresholds
WINDOWS_CRITICAL_COMMIT_GB = 2.0
WINDOWS_TIGHT_COMMIT_GB = 4.0
WINDOWS_CRITICAL_RAM_COMMIT_GB = 4.0
WINDOWS_TIGHT_RAM_COMMIT_GB = 6.0

# Cache settings
LOWRAM_PROFILE_CACHE_TTL_SECONDS = 3.0


class LowRAMProfileCache:
    """Thread-safe cache for low RAM profile to avoid frequent probing."""

    def __init__(self) -> None:
        self._profile: Dict[str, Any] = {}
        self._timestamp: float = 0.0

    def get(self, ttl: float = LOWRAM_PROFILE_CACHE_TTL_SECONDS) -> Optional[Dict[str, Any]]:
        """Get cached profile if still valid."""
        now = time.time()
        if self._profile and (now - self._timestamp) < ttl:
            return dict(self._profile)
        return None

    def set(self, profile: Dict[str, Any]) -> None:
        """Update cached profile."""
        self._profile = dict(profile)
        self._timestamp = time.time()

    def clear(self) -> None:
        """Clear cached profile."""
        self._profile = {}
        self._timestamp = 0.0


# Global cache instance
_profile_cache = LowRAMProfileCache()


def get_windows_commit_status_gb() -> Tuple[float, float]:
    """Get Windows pagefile (commit) memory status.

    Returns:
        Tuple of (total_pagefile_gb, available_commit_gb)
    """
    if os.name != "nt":
        return 0.0, 0.0

    try:
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MEMORYSTATUSEX()
        status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)

        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return 0.0, 0.0

        total_pagefile_gb = float(status.ullTotalPageFile) / (1024 ** 3)
        avail_commit_gb = float(status.ullAvailPageFile) / (1024 ** 3)
        return total_pagefile_gb, avail_commit_gb

    except Exception:
        return 0.0, 0.0


def get_lowram_profile(
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """Get current low RAM profile with caching.

    The profile contains:
    - level: "normal", "tight", or "critical"
    - platform: "nt" (Windows) or "posix" (Linux/Mac)
    - ram_available_gb: Available RAM
    - swap_available_gb: Available swap/pagefile
    - effective_available_gb: Usable memory (platform-specific)
    - commit_available_gb: Windows commit only
    - reason: Explanation string

    Args:
        force_refresh: If True, bypass cache

    Returns:
        Profile dict with memory status
    """
    if not force_refresh:
        cached = _profile_cache.get()
        if cached:
            return cached

    profile: Dict[str, Any] = {
        "level": "normal",
        "platform": os.name,
        "ram_available_gb": 0.0,
        "swap_available_gb": 0.0,
        "effective_available_gb": 0.0,
        "commit_available_gb": 0.0,
        "reason": "",
    }

    try:
        import psutil

        mem = psutil.virtual_memory()
        ram_available_gb = float(mem.available) / (1024 ** 3)
        profile["ram_available_gb"] = ram_available_gb

        # Get swap/pagefile
        swap_available_gb = 0.0
        try:
            swap_available_gb = float(psutil.swap_memory().free) / (1024 ** 3)
        except Exception:
            swap_available_gb = 0.0
        profile["swap_available_gb"] = swap_available_gb

        if os.name == "nt":
            # Windows: rely primarily on commit headroom
            _, commit_available_gb = get_windows_commit_status_gb()
            profile["commit_available_gb"] = commit_available_gb

            effective_available_gb = (
                commit_available_gb if commit_available_gb > 0 else ram_available_gb
            )
            profile["effective_available_gb"] = effective_available_gb

            # Windows memory level detection
            if (commit_available_gb > 0 and commit_available_gb < WINDOWS_CRITICAL_COMMIT_GB) or (
                ram_available_gb < 1.0
                and (commit_available_gb <= 0 or commit_available_gb < WINDOWS_CRITICAL_RAM_COMMIT_GB)
            ):
                profile["level"] = "critical"
                profile["reason"] = (
                    f"windows_low_commit={commit_available_gb:.1f}GB "
                    f"ram={ram_available_gb:.1f}GB"
                )
            elif (commit_available_gb > 0 and commit_available_gb < WINDOWS_TIGHT_COMMIT_GB) or (
                ram_available_gb < 2.0
                and (commit_available_gb <= 0 or commit_available_gb < WINDOWS_TIGHT_RAM_COMMIT_GB)
            ):
                profile["level"] = "tight"
                profile["reason"] = (
                    f"windows_tight_commit={commit_available_gb:.1f}GB "
                    f"ram={ram_available_gb:.1f}GB"
                )
        else:
            # Linux/Mac: combine RAM + swap
            effective_available_gb = ram_available_gb + swap_available_gb
            profile["effective_available_gb"] = effective_available_gb

            if (
                effective_available_gb < CRITICAL_EFFECTIVE_THRESHOLD_GB
                or ram_available_gb < CRITICAL_RAM_THRESHOLD_GB
            ):
                profile["level"] = "critical"
                profile["reason"] = (
                    f"linux_low_mem+swap={effective_available_gb:.1f}GB "
                    f"ram={ram_available_gb:.1f}GB"
                )
            elif (
                effective_available_gb <= TIGHT_EFFECTIVE_THRESHOLD_GB
                or ram_available_gb < TIGHT_RAM_THRESHOLD_GB
            ):
                profile["level"] = "tight"
                profile["reason"] = (
                    f"linux_tight_mem+swap={effective_available_gb:.1f}GB "
                    f"ram={ram_available_gb:.1f}GB"
                )

    except Exception as exc:
        profile["reason"] = f"lowram_probe_error:{exc}"

    _profile_cache.set(profile)
    return profile


def is_lowram_tight_or_critical(
    force_refresh: bool = False,
) -> bool:
    """Check if memory is in tight or critical state.

    Args:
        force_refresh: If True, bypass cache

    Returns:
        True if memory pressure is detected
    """
    try:
        level = str(get_lowram_profile(force_refresh=force_refresh).get("level") or "normal")
    except Exception:
        level = "normal"
    return level in {"tight", "critical"}


def is_lowram_critical(
    force_refresh: bool = False,
) -> bool:
    """Check if memory is in critical state.

    Args:
        force_refresh: If True, bypass cache

    Returns:
        True if critical memory pressure
    """
    try:
        level = str(get_lowram_profile(force_refresh=force_refresh).get("level") or "normal")
    except Exception:
        level = "normal"
    return level == "critical"


def get_effective_available_memory_gb(
    force_refresh: bool = False,
) -> float:
    """Get effective available memory in GB.

    On Windows, this is commit memory.
    On Linux/Mac, this is RAM + swap.

    Args:
        force_refresh: If True, bypass cache

    Returns:
        Available memory in GB
    """
    profile = get_lowram_profile(force_refresh=force_refresh)
    return float(profile.get("effective_available_gb") or 0.0)


def estimate_required_ram_gb(
    model_name: Optional[str] = None,
    model_id: Optional[str] = None,
    optimization_config: Optional[Dict[str, Any]] = None,
) -> float:
    """Estimate RAM required to load a model.

    Args:
        model_name: Model name/path
        model_id: Optional model identifier
        optimization_config: Quantization/optimization settings

    Returns:
        Estimated RAM requirement in GB
    """
    from .gpu_memory_budget import estimate_model_size_gb

    # Get base model size estimate
    model_size = estimate_model_size_gb(model_name, model_id)

    # Get device from optimization config
    device = "cpu"
    if optimization_config:
        device = str(optimization_config.get("device") or "cpu")

    # Check for quantization
    load_in_4bit = False
    load_in_8bit = False
    if optimization_config:
        load_in_4bit = bool(optimization_config.get("load_in_4bit"))
        load_in_8bit = bool(optimization_config.get("load_in_8bit"))

    # Quantization multipliers
    if load_in_4bit:
        size_multiplier = 0.6  # 4-bit is ~0.6x of base size in RAM
    elif load_in_8bit:
        size_multiplier = 0.75  # 8-bit is ~0.75x of base size in RAM
    else:
        size_multiplier = 1.3  # FP16 with overhead

    # Add loading overhead
    loading_overhead_gb = 2.0  # Transformers loading overhead

    # CPU needs more RAM (no GPU offload)
    if device == "cpu":
        loading_overhead_gb += 1.5

    return (model_size * size_multiplier) + loading_overhead_gb


def can_load_model(
    required_ram_gb: float,
    *,
    safety_margin: float = 0.8,
    force_refresh: bool = False,
) -> Tuple[bool, str]:
    """Check if there's enough memory to safely load a model.

    Args:
        required_ram_gb: Estimated RAM requirement
        safety_margin: Fraction of available memory to use (0-1)
        force_refresh: If True, refresh memory profile

    Returns:
        Tuple of (can_proceed, reason_string)
    """
    profile = get_lowram_profile(force_refresh=force_refresh)
    available = float(profile.get("effective_available_gb") or 0.0)
    level = str(profile.get("level") or "normal")

    # Check if in critical state
    if level == "critical":
        return False, f"Critical memory pressure: {profile.get('reason', 'unknown')}"

    # Check if enough memory available
    required_with_margin = required_ram_gb / safety_margin
    if available < required_with_margin:
        return False, (
            f"Insufficient memory: need ~{required_ram_gb:.1f}GB, "
            f"have {available:.1f}GB available"
        )

    # Warn if tight
    if level == "tight":
        logger.warning(
            "Memory is tight (level=%s): %.1fGB available, %.1fGB required",
            level,
            available,
            required_ram_gb,
        )

    return True, ""


def is_memory_pressure_failure_reason(reason: str) -> bool:
    """Check if an error reason indicates memory pressure.

    Args:
        reason: Error message or reason string

    Returns:
        True if the error suggests OOM or memory pressure
    """
    lowered = str(reason or "").lower()
    if not lowered:
        return False

    markers = (
        "memoryerror",
        "out of memory",
        "cuda out of memory",
        "mémoire système insuffisante",
        "memoire systeme insuffisante",
        "commit windows insuffisant",
        "lowram",
        "vram insuffisante",
        "oom",
    )
    return any(marker in lowered for marker in markers)


def get_memory_recovery_wait_seconds(
    lowram_level: str = "normal",
    attempt: int = 1,
) -> float:
    """Calculate wait time for memory recovery between retries.

    Args:
        lowram_level: Current memory pressure level
        attempt: Current retry attempt number

    Returns:
        Recommended wait time in seconds
    """
    base_wait = 10.0

    # Increase wait for critical memory
    if lowram_level == "critical":
        base_wait = 20.0
    elif lowram_level == "tight":
        base_wait = 15.0

    # Exponential backoff with cap
    wait = min(base_wait * (1.5 ** (attempt - 1)), 120.0)

    return wait


def get_system_ram_info() -> Dict[str, float]:
    """Get system RAM statistics.

    Returns:
        Dict with total, available, used RAM in GB
    """
    try:
        import psutil
        mem = psutil.virtual_memory()
        return {
            "total_gb": float(mem.total) / (1024 ** 3),
            "available_gb": float(mem.available) / (1024 ** 3),
            "used_gb": float(mem.used) / (1024 ** 3),
            "percent_used": float(mem.percent),
        }
    except Exception:
        return {
            "total_gb": 0.0,
            "available_gb": 0.0,
            "used_gb": 0.0,
            "percent_used": 0.0,
        }


def clear_profile_cache() -> None:
    """Clear the low RAM profile cache."""
    _profile_cache.clear()
