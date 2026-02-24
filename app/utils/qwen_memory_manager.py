"""
QwenMemoryManager Module (Sprint 8.1)

Centralizes memory management logic extracted from QwenManager.
Handles VRAM tracking, survival mode state, RAM profiling, and
memory budget calculations.

This module reduces QwenManager's responsibilities by extracting
all memory-related state and methods into a dedicated class.

Key features:
- LowRAM profile detection (normal, tight, critical)
- Survival mode tracking and model selection
- VRAM/RAM budget calculations
- Memory pressure detection
- Failure tracking for adaptive behavior
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Tuple, TYPE_CHECKING

try:
    from ..logging.safe_logger import get_safe_logger
    from ..config import DEFAULT_PII_CONFIG
    logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

# Import from existing utility modules
from .survival_mode_selector import (
    is_survival_mode_enabled,
    is_memory_pressure_failure,
    get_survival_config,
    get_survival_gpu_budget_cap_gb,
    pick_survival_model,
    SurvivalConfig,
)
from .runtime_memory_policy import (
    get_lowram_profile as get_lowram_profile_util,
    can_load_model as can_load_model_util,
)
from .gpu_memory_budget import (
    get_free_vram_gb as get_free_vram_util,
    get_total_vram_gb as get_total_vram_util,
    is_low_vram_mode as is_low_vram_mode_util,
    is_med_vram_mode as is_med_vram_mode_util,
)


@dataclass
class MemoryState:
    """Tracks memory-related state for QwenManager."""
    # LowRAM profile caching
    last_lowram_profile: Dict[str, Any] = field(default_factory=dict)
    last_lowram_profile_ts: float = 0.0
    lowram_cache_ttl_seconds: float = 3.0

    # Survival mode state
    consecutive_failures: int = 0
    survival_mode_forced: bool = False
    survival_last_reason: str = ""

    # Run tracking
    runs_since_last_load: int = 0


class QwenMemoryManager:
    """
    Manages memory-related state and operations for QwenManager.

    This class extracts memory management responsibilities from the
    monolithic QwenManager class, providing cleaner separation of concerns.

    Usage:
        memory_manager = QwenMemoryManager(custom_parameters=custom_params)
        profile = memory_manager.get_lowram_profile()
        if memory_manager.is_survival_mode():
            override = memory_manager.pick_survival_model_override(...)
    """

    def __init__(
        self,
        *,
        custom_parameters: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize memory manager.

        Args:
            custom_parameters: Custom parameters from model config
        """
        self._custom_parameters = custom_parameters or {}
        self._state = MemoryState()
        self._survival_config = get_survival_config(
            custom_parameters=custom_parameters,
        )

    @property
    def custom_parameters(self) -> Dict[str, Any]:
        """Get custom parameters."""
        return self._custom_parameters

    def update_custom_parameters(self, params: Dict[str, Any]) -> None:
        """Update custom parameters and refresh survival config."""
        self._custom_parameters = params or {}
        self._survival_config = get_survival_config(
            custom_parameters=self._custom_parameters,
        )

    # -------------------------------------------------------------------------
    # LowRAM Profile
    # -------------------------------------------------------------------------

    def get_lowram_profile(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Get current LowRAM profile with caching.

        Returns a profile dict with:
        - level: "normal", "tight", or "critical"
        - platform: os.name
        - ram_available_gb: Available RAM
        - swap_available_gb: Available swap
        - effective_available_gb: Combined available memory
        - commit_available_gb: Windows commit charge available
        - reason: Explanation for the level

        Args:
            force_refresh: If True, bypass cache

        Returns:
            LowRAM profile dictionary
        """
        now = time.time()
        if (
            not force_refresh
            and self._state.last_lowram_profile
            and (now - self._state.last_lowram_profile_ts) < self._state.lowram_cache_ttl_seconds
        ):
            return dict(self._state.last_lowram_profile)

        profile = self._compute_lowram_profile()

        self._state.last_lowram_profile = dict(profile)
        self._state.last_lowram_profile_ts = now
        return profile

    def _compute_lowram_profile(self) -> Dict[str, Any]:
        """Compute LowRAM profile from current memory state."""
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
            ram_available_gb = float(mem.available) / (1024**3)
            profile["ram_available_gb"] = ram_available_gb

            swap_available_gb = 0.0
            try:
                swap_available_gb = float(psutil.swap_memory().free) / (1024**3)
            except Exception:
                swap_available_gb = 0.0
            profile["swap_available_gb"] = swap_available_gb

            if os.name == "nt":
                _, commit_available_gb = self.get_windows_commit_status_gb()
                profile["commit_available_gb"] = commit_available_gb
                effective_available_gb = (
                    commit_available_gb if commit_available_gb > 0 else ram_available_gb
                )
                profile["effective_available_gb"] = effective_available_gb

                # Windows: rely primarily on commit headroom
                if (commit_available_gb > 0 and commit_available_gb < 2.0) or (
                    ram_available_gb < 1.0 and (commit_available_gb <= 0 or commit_available_gb < 4.0)
                ):
                    profile["level"] = "critical"
                    profile["reason"] = (
                        f"windows_low_commit={commit_available_gb:.1f}GB "
                        f"ram={ram_available_gb:.1f}GB"
                    )
                elif (commit_available_gb > 0 and commit_available_gb < 4.0) or (
                    ram_available_gb < 2.0 and (commit_available_gb <= 0 or commit_available_gb < 6.0)
                ):
                    profile["level"] = "tight"
                    profile["reason"] = (
                        f"windows_tight_commit={commit_available_gb:.1f}GB "
                        f"ram={ram_available_gb:.1f}GB"
                    )
            else:
                effective_available_gb = ram_available_gb + swap_available_gb
                profile["effective_available_gb"] = effective_available_gb
                if effective_available_gb < 2.0 or ram_available_gb < 1.5:
                    profile["level"] = "critical"
                    profile["reason"] = (
                        f"linux_low_mem+swap={effective_available_gb:.1f}GB "
                        f"ram={ram_available_gb:.1f}GB"
                    )
                elif effective_available_gb <= 6.0 or ram_available_gb < 6.0:
                    profile["level"] = "tight"
                    profile["reason"] = (
                        f"linux_tight_mem+swap={effective_available_gb:.1f}GB "
                        f"ram={ram_available_gb:.1f}GB"
                    )
        except Exception as exc:
            profile["reason"] = f"lowram_probe_error:{exc}"

        return profile

    def is_lowram_tight_or_critical(self) -> bool:
        """Check if current memory state is tight or critical."""
        try:
            level = str(self.get_lowram_profile().get("level") or "normal")
        except Exception:
            level = "normal"
        return level in {"tight", "critical"}

    def get_runtime_memory_mode(self) -> str:
        """
        Get human-readable memory mode string.

        Returns:
            One of: "LowRAM", "LowVRAM", "MedVRAM", "HighVRAM", "CPU/Unknown"
        """
        lowram_level = str(self.get_lowram_profile().get("level") or "normal")
        if lowram_level in {"tight", "critical"}:
            return "LowRAM"
        total_vram = self.get_total_vram_gb()
        if total_vram > 0 and total_vram <= 8.0:
            return "LowVRAM"
        if total_vram > 8.0 and total_vram <= 12.0:
            return "MedVRAM"
        if total_vram > 12.0:
            return "HighVRAM"
        return "CPU/Unknown"

    # -------------------------------------------------------------------------
    # Windows Commit Status
    # -------------------------------------------------------------------------

    def get_windows_commit_status_gb(self) -> Tuple[float, float]:
        """
        Get Windows commit charge status.

        Returns:
            Tuple of (total_pagefile_gb, available_commit_gb)
        """
        if os.name != "nt":
            return 0.0, 0.0

        try:
            import ctypes
            from ctypes import wintypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", wintypes.DWORD),
                    ("dwMemoryLoad", wintypes.DWORD),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            mem_status = MEMORYSTATUSEX()
            mem_status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem_status))

            total_pagefile_gb = float(mem_status.ullTotalPageFile) / (1024**3)
            avail_commit_gb = float(mem_status.ullAvailPageFile) / (1024**3)
            return total_pagefile_gb, avail_commit_gb
        except Exception:
            return 0.0, 0.0

    # -------------------------------------------------------------------------
    # VRAM Methods
    # -------------------------------------------------------------------------

    def get_total_vram_gb(self) -> float:
        """Get total GPU VRAM in GB."""
        return get_total_vram_util()

    def get_free_vram_gb(self) -> float:
        """Get free GPU VRAM in GB."""
        return get_free_vram_util()

    def is_low_vram_mode(self) -> bool:
        """Check if running in low VRAM mode (<=8GB)."""
        return is_low_vram_mode_util()

    def is_med_vram_mode(self) -> bool:
        """Check if running in medium VRAM mode (8-12GB)."""
        return is_med_vram_mode_util()

    def get_vram_mode(self) -> str:
        """
        Get VRAM mode string.

        Returns:
            One of: "low_vram", "med_vram", "high_vram", "auto"
        """
        custom = self._custom_parameters or {}

        if "vram_mode" in custom:
            raw = str(custom.get("vram_mode") or "").strip().lower()
            if raw in ("low", "low_vram", "lowvram"):
                return "low_vram"
            if raw in ("med", "med_vram", "medvram", "medium"):
                return "med_vram"
            if raw in ("high", "high_vram", "highvram"):
                return "high_vram"

        total_vram = self.get_total_vram_gb()
        if total_vram <= 0:
            return "auto"
        if total_vram <= 8.0:
            return "low_vram"
        if total_vram <= 12.0:
            return "med_vram"
        return "high_vram"

    def get_vram_headroom_gb(
        self,
        *,
        used_vram_gb: float = 0.0,
        safety_margin_gb: float = 0.5,
    ) -> float:
        """
        Calculate available VRAM headroom.

        Args:
            used_vram_gb: Currently used VRAM
            safety_margin_gb: Safety margin to reserve

        Returns:
            Available VRAM headroom in GB
        """
        free_vram = self.get_free_vram_gb()
        return max(0.0, free_vram - used_vram_gb - safety_margin_gb)

    # -------------------------------------------------------------------------
    # Survival Mode
    # -------------------------------------------------------------------------

    def is_survival_mode(self) -> bool:
        """
        Check if survival mode is enabled.

        Quality-first policy: survival is explicit env opt-in only.
        """
        return is_survival_mode_enabled()

    def is_memory_pressure_failure(self, reason: str) -> bool:
        """Check if failure reason indicates memory pressure."""
        return is_memory_pressure_failure(reason)

    def record_failure(self, reason: str) -> None:
        """
        Record a failure event for survival mode tracking.

        Args:
            reason: Failure reason string
        """
        self._state.consecutive_failures += 1
        logger.warning(
            "Failure recorded (%s consecutive): %s",
            self._state.consecutive_failures,
            str(reason or "")[:240],
        )

        # Check if we should force survival mode
        if self._state.consecutive_failures >= self._survival_config.failure_threshold:
            if self.is_memory_pressure_failure(reason):
                self._state.survival_mode_forced = True
                self._state.survival_last_reason = reason

    def record_success(self, reason: str = "") -> None:
        """
        Record a success event, resetting failure counter.

        Args:
            reason: Success reason for logging
        """
        self._state.consecutive_failures = 0

        if not self._survival_config.sticky:
            self._state.survival_mode_forced = False
            self._state.survival_last_reason = ""

        if reason:
            logger.info("Reset failure counter after success: %s", reason)

    @property
    def consecutive_failures(self) -> int:
        """Get current consecutive failure count."""
        return self._state.consecutive_failures

    @property
    def is_survival_forced(self) -> bool:
        """Check if survival mode has been forced by failures."""
        return self._state.survival_mode_forced

    def get_survival_gpu_budget_cap_gb(self, total_vram_gb: float) -> float:
        """Get GPU budget cap for survival mode."""
        lowram_level = str(self.get_lowram_profile().get("level") or "normal")
        return get_survival_gpu_budget_cap_gb(
            total_vram_gb=total_vram_gb,
            lowram_level=lowram_level,
        )

    def get_survival_max_model_len(
        self,
        *,
        stage_name: str = "",
        is_writer_stage: bool = False,
    ) -> int:
        """
        Get maximum model context length for survival mode.

        Args:
            stage_name: Current pipeline stage
            is_writer_stage: Whether this is a writer stage

        Returns:
            Maximum context length in tokens
        """
        lowram_level = str(self.get_lowram_profile().get("level") or "normal")
        total_vram = self.get_total_vram_gb()

        if lowram_level == "critical":
            return 1536 if is_writer_stage else 1024
        if lowram_level == "tight":
            return 2048 if is_writer_stage else 1536
        if total_vram > 0 and total_vram <= 6.5:
            return 2048 if is_writer_stage else 1536
        return 2048

    # -------------------------------------------------------------------------
    # Unload Policies
    # -------------------------------------------------------------------------

    def should_unload_between_stages(self) -> bool:
        """
        Check if model should be unloaded between pipeline stages.

        Returns True if memory is constrained and unloading helps.
        """
        if self.is_survival_mode():
            return True
        if self.is_lowram_tight_or_critical():
            return True
        if self.is_low_vram_mode():
            return True
        return False

    def should_unload_after_generation(self) -> bool:
        """
        Check if model should be unloaded after generation completes.

        Returns True if memory headroom is low.
        """
        if self.is_survival_mode():
            return True
        if self.is_lowram_tight_or_critical():
            return True

        custom = self._custom_parameters or {}
        if "unload_after_generation" in custom:
            return self._to_bool(custom.get("unload_after_generation"), False)

        # Check VRAM headroom
        free_vram = self.get_free_vram_gb()
        if free_vram > 0 and free_vram < 2.0:
            return True

        return False

    def get_recycle_every_runs(self) -> int:
        """
        Get number of runs after which model should be recycled.

        Returns 0 if recycling is disabled.
        """
        custom = self._custom_parameters or {}
        try:
            value = int(custom.get("recycle_every_runs") or 0)
            return max(0, value)
        except Exception:
            return 0

    def mark_run_completed(self) -> None:
        """Mark a generation run as completed."""
        self._state.runs_since_last_load += 1

    def should_recycle_model(self) -> bool:
        """Check if model should be recycled based on run count."""
        recycle_every = self.get_recycle_every_runs()
        if recycle_every <= 0:
            return False
        return self._state.runs_since_last_load >= recycle_every

    def reset_run_counter(self) -> None:
        """Reset the run counter after model reload."""
        self._state.runs_since_last_load = 0

    # -------------------------------------------------------------------------
    # Utilities
    # -------------------------------------------------------------------------

    def _to_bool(self, value: Any, default: bool = False) -> bool:
        """Convert value to boolean."""
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("1", "true", "yes", "y", "on")

    def cleanup_state(self) -> None:
        """Reset memory state (for testing)."""
        self._state = MemoryState()
