"""
GPU Memory Budget Module (PR-10)

Centralized VRAM and GPU memory management utilities.
Extracted from QwenManager in llm_worker.py.

Key features:
- VRAM tracking and budget calculation
- Device mapping helpers
- Memory mode detection (low/med/high VRAM)
- Headroom calculations for safe model loading
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional, Tuple

try:
    from ..logging.safe_logger import get_safe_logger
    from ..config import DEFAULT_PII_CONFIG
    logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


# Try to import torch for VRAM queries
try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    torch = None  # type: ignore


# VRAM mode thresholds in GB
VRAM_LOW_THRESHOLD = 8.0
VRAM_MED_THRESHOLD = 12.0

# Default headroom values
DEFAULT_VRAM_HEADROOM_GB = 1.5
MIN_VRAM_HEADROOM_GB = 0.75


def get_free_vram_gb() -> float:
    """Get current free VRAM in GB.

    Returns:
        Free VRAM in GB, or 0.0 if not available.
    """
    if not TORCH_AVAILABLE or not torch.cuda.is_available():
        return 0.0

    try:
        if hasattr(torch.cuda, "mem_get_info"):
            free_bytes, _ = torch.cuda.mem_get_info()
            return free_bytes / (1024 ** 3)
    except Exception:
        pass

    # Fallback: try gpu_manager if available
    try:
        from .gpu_utils import gpu_manager
        if hasattr(gpu_manager, "get_available_vram"):
            return float(gpu_manager.get_available_vram())
    except Exception:
        pass

    return 0.0


def get_total_vram_gb() -> float:
    """Get total VRAM in GB.

    Returns:
        Total VRAM in GB, or 0.0 if not available.
    """
    # Try gpu_manager first
    try:
        from .gpu_utils import gpu_manager
        total = float(
            getattr(gpu_manager, "gpu_info", {}).get("total_memory_gb", 0) or 0
        )
        if total > 0:
            return total
        total = float(
            getattr(gpu_manager, "gpu_info", {}).get("vram_gb", 0) or 0
        )
        if total > 0:
            return total
    except Exception:
        pass

    # Fallback to torch
    if TORCH_AVAILABLE and torch.cuda.is_available():
        try:
            if hasattr(torch.cuda, "mem_get_info"):
                _, total_bytes = torch.cuda.mem_get_info()
                return total_bytes / (1024 ** 3)
        except Exception:
            pass

    return 0.0


def get_vram_mode(
    custom_parameters: Optional[Dict[str, Any]] = None,
) -> str:
    """Determine VRAM mode: auto, low, med, or high.

    Args:
        custom_parameters: Optional custom parameters dict with vram_mode override

    Returns:
        One of: "auto", "low", "med", "high"
    """
    # Check environment variable first
    env_mode = os.getenv("CVMATCH_VRAM_MODE")
    if env_mode:
        mode = env_mode.strip().lower()
        if mode in {"auto", "low", "med", "high"}:
            return mode

    # Check custom parameters
    if custom_parameters:
        custom_mode = custom_parameters.get("vram_mode")
        if isinstance(custom_mode, str):
            mode = custom_mode.strip().lower()
            if mode in {"auto", "low", "med", "high"}:
                return mode

    return "auto"


def is_low_vram_mode(
    custom_parameters: Optional[Dict[str, Any]] = None,
) -> bool:
    """Check if running in low VRAM mode (<=8GB).

    Args:
        custom_parameters: Optional custom parameters

    Returns:
        True if in low VRAM mode
    """
    mode = get_vram_mode(custom_parameters)
    if mode == "low":
        return True
    if mode in {"med", "high"}:
        return False

    # Auto-detect based on total VRAM
    total_vram = get_total_vram_gb()
    return total_vram > 0 and total_vram <= VRAM_LOW_THRESHOLD


def is_med_vram_mode(
    custom_parameters: Optional[Dict[str, Any]] = None,
) -> bool:
    """Check if running in medium VRAM mode (8-12GB).

    Args:
        custom_parameters: Optional custom parameters

    Returns:
        True if in medium VRAM mode
    """
    mode = get_vram_mode(custom_parameters)
    if mode == "med":
        return True
    if mode in {"low", "high"}:
        return False

    # Auto-detect
    total_vram = get_total_vram_gb()
    return total_vram > VRAM_LOW_THRESHOLD and total_vram <= VRAM_MED_THRESHOLD


def is_high_vram_mode(
    custom_parameters: Optional[Dict[str, Any]] = None,
) -> bool:
    """Check if running in high VRAM mode (>12GB).

    Args:
        custom_parameters: Optional custom parameters

    Returns:
        True if in high VRAM mode
    """
    mode = get_vram_mode(custom_parameters)
    if mode == "high":
        return True
    if mode in {"low", "med"}:
        return False

    # Auto-detect
    total_vram = get_total_vram_gb()
    return total_vram > VRAM_MED_THRESHOLD


def get_vram_headroom_gb(
    custom_parameters: Optional[Dict[str, Any]] = None,
    free_vram_gb: Optional[float] = None,
    total_vram_gb: Optional[float] = None,
    *,
    survival_mode: bool = False,
) -> float:
    """Calculate VRAM headroom to reserve for safe operation.

    This headroom ensures stability during generation by leaving
    some free VRAM for KV cache and other temporary allocations.

    Priority order:
    1. Custom parameter override (vram_headroom_gb)
    2. Environment variable (CVMATCH_VRAM_HEADROOM_GB)
    3. Survival mode calculation (more conservative)
    4. Dynamic calculation based on free VRAM and factor
    5. Total VRAM percentage fallback

    Args:
        custom_parameters: Optional custom parameters with vram_headroom_gb
        free_vram_gb: Current free VRAM (for dynamic calculation)
        total_vram_gb: Total VRAM (for percentage-based calculation)
        survival_mode: If True, use more conservative headroom

    Returns:
        Recommended headroom in GB
    """
    custom = custom_parameters or {}

    # Check custom override
    try:
        override = float(custom.get("vram_headroom_gb", 0) or 0)
        if override > 0:
            return override
    except Exception:
        pass

    # Check environment override
    env_override = os.getenv("CVMATCH_VRAM_HEADROOM_GB")
    if env_override:
        try:
            parsed = float(env_override)
            if parsed > 0:
                return parsed
        except Exception:
            pass

    # Get memory values
    free = float(free_vram_gb or 0.0)
    if free <= 0:
        free = get_free_vram_gb()

    total = float(total_vram_gb or 0.0)
    if total <= 0:
        total = get_total_vram_gb()

    # Survival mode: conservative headroom (reduced to allow ~82% utilisation)
    if survival_mode:
        if total > 0 and total <= 8.0:
            return max(0.75, min(1.5, total * 0.15))
        if total > 0:
            return max(0.5, min(1.5, total * 0.10))
        return 0.75

    # Get headroom factor from params/env
    try:
        factor = float(custom.get("vram_headroom_factor", 0.05) or 0.05)
    except Exception:
        factor = 0.15
    env_factor = os.getenv("CVMATCH_VRAM_HEADROOM_FACTOR")
    if env_factor:
        try:
            factor = float(env_factor)
        except Exception:
            pass
    if factor <= 0:
        factor = 0.05

    # Determine min/max bounds
    default_min = 0.25
    default_max = 1.5 if (total > 0 and total <= 12.0) else 2.5

    try:
        min_headroom = float(custom.get("vram_headroom_min_gb", default_min) or default_min)
    except Exception:
        min_headroom = default_min
    env_min = os.getenv("CVMATCH_VRAM_HEADROOM_MIN_GB")
    if env_min:
        try:
            min_headroom = float(env_min)
        except Exception:
            pass

    try:
        max_headroom = float(custom.get("vram_headroom_max_gb", default_max) or default_max)
    except Exception:
        max_headroom = default_max
    env_max = os.getenv("CVMATCH_VRAM_HEADROOM_MAX_GB")
    if env_max:
        try:
            max_headroom = float(env_max)
        except Exception:
            pass

    if min_headroom <= 0:
        min_headroom = default_min
    if max_headroom < min_headroom:
        max_headroom = min_headroom

    # Dynamic calculation based on free VRAM
    if free > 0:
        dynamic = free * factor
        return max(min_headroom, min(max_headroom, dynamic))

    # Fallback to total VRAM percentage
    if total > 0:
        return max(min_headroom, min(max_headroom, total * 0.12))

    return 1.0


def should_disable_kv_cache(
    custom_parameters: Optional[Dict[str, Any]] = None,
) -> bool:
    """Determine if KV cache should be disabled due to low VRAM.

    Disabling KV cache reduces VRAM usage but slows generation.

    Args:
        custom_parameters: Optional custom parameters

    Returns:
        True if KV cache should be disabled
    """
    free_vram = get_free_vram_gb()
    if free_vram <= 0:
        return False  # Not on GPU, no need to disable

    headroom = get_vram_headroom_gb(
        custom_parameters=custom_parameters,
        free_vram_gb=free_vram,
    )

    # Disable KV cache if VRAM is below headroom threshold
    return free_vram < max(1.0, headroom)


def get_survival_gpu_budget_cap_gb(
    total_vram_gb: float,
    lowram_level: str = "normal",
) -> float:
    """Calculate maximum GPU budget in survival mode.

    Survival mode uses conservative memory budgets to ensure
    stability on low-memory systems.

    Args:
        total_vram_gb: Total VRAM available
        lowram_level: RAM pressure level ("normal", "tight", "critical")

    Returns:
        Maximum GPU budget in GB
    """
    total_vram = float(total_vram_gb or 0.0)

    if total_vram <= 0:
        return 3.5 if lowram_level == "critical" else 4.0

    # Absolute caps based on VRAM tier
    if total_vram <= 6.5:
        abs_cap = 3.5 if lowram_level == "critical" else 4.0
    elif total_vram <= 8.5:
        abs_cap = 4.5 if lowram_level in {"tight", "critical"} else 5.0
    elif total_vram <= 12.0:
        abs_cap = 6.5
    else:
        abs_cap = 8.0

    # Percentage-based cap
    percent_cap = 0.55 if lowram_level in {"tight", "critical"} else 0.60

    return min(abs_cap, total_vram * percent_cap)


def get_runtime_memory_mode(
    lowram_level: str = "normal",
    custom_parameters: Optional[Dict[str, Any]] = None,
) -> str:
    """Get descriptive memory mode for logging/UI.

    Args:
        lowram_level: RAM pressure level
        custom_parameters: Optional custom parameters

    Returns:
        One of: "LowRAM", "LowVRAM", "MedVRAM", "HighVRAM", "CPU/Unknown"
    """
    if lowram_level in {"tight", "critical"}:
        return "LowRAM"

    total_vram = get_total_vram_gb()

    if total_vram > 0 and total_vram <= VRAM_LOW_THRESHOLD:
        return "LowVRAM"
    if total_vram > VRAM_LOW_THRESHOLD and total_vram <= VRAM_MED_THRESHOLD:
        return "MedVRAM"
    if total_vram > VRAM_MED_THRESHOLD:
        return "HighVRAM"

    return "CPU/Unknown"


def get_recycle_every_runs(
    survival_mode: bool = False,
    custom_parameters: Optional[Dict[str, Any]] = None,
) -> int:
    """Get model recycling frequency based on VRAM constraints.

    Model recycling (unload/reload) helps prevent memory fragmentation
    and VRAM exhaustion on low-memory systems.

    Args:
        survival_mode: If True, recycle every run
        custom_parameters: Optional custom parameters

    Returns:
        Number of runs between recycling (0 = no recycling)
    """
    if survival_mode:
        return 1

    # Check environment override
    env_value = os.getenv("CVMATCH_RECYCLE_EVERY_RUNS")
    if env_value is not None:
        try:
            return max(0, int(env_value))
        except Exception:
            return 0

    # Check custom parameters
    if custom_parameters and "recycle_every_runs" in custom_parameters:
        try:
            return max(0, int(custom_parameters.get("recycle_every_runs")))
        except Exception:
            return 0

    # Auto-determine based on VRAM
    if is_low_vram_mode(custom_parameters):
        return 1
    if is_med_vram_mode(custom_parameters):
        return 2

    return 0


def estimate_model_size_gb(
    model_name: Optional[str],
    model_id: Optional[str] = None,
) -> float:
    """Estimate model size from name/id heuristics.

    This is a rough estimate used for memory planning.

    Args:
        model_name: Model name/path
        model_id: Optional model identifier

    Returns:
        Estimated size in GB
    """
    haystack = f"{model_id or ''} {model_name or ''}".lower()

    if "32b" in haystack:
        return 32.0
    if "14b" in haystack:
        return 14.0
    if any(token in haystack for token in ["8b", "qwen3-8b", "qwen-7b"]):
        return 8.0
    if any(token in haystack for token in ["7b", "mistral-7b", "mistral 7b"]):
        return 7.0
    if any(token in haystack for token in ["4b", "3.8b", "phi-3-mini", "phi3", "mini-4k"]):
        return 4.0
    if any(token in haystack for token in ["3b", "qwen3-4b", "qwen2.5-3b"]):
        return 3.0
    if any(token in haystack for token in ["1.7b", "1.5b", "qwen3-1.7b", "qwen2.5-1.5b"]):
        return 1.5
    if any(token in haystack for token in ["1.1b", "tinyllama"]):
        return 1.1
    if any(token in haystack for token in ["0.6", "0.5b", "qwen2.5-0.5b"]):
        return 0.5

    return 7.0  # Default assumption


def get_max_memory_map(
    total_vram_gb: float,
    *,
    gpu_fraction: float = 0.85,
    cpu_offload_gb: float = 0.0,
    custom_parameters: Optional[Dict[str, Any]] = None,
) -> Dict[int, str]:
    """Build max_memory map for transformers device_map.

    Args:
        total_vram_gb: Total VRAM available
        gpu_fraction: Fraction of VRAM to use (0-1)
        cpu_offload_gb: Amount of RAM to use for CPU offload
        custom_parameters: Optional custom parameters

    Returns:
        Dict mapping device index to memory limit string
    """
    if total_vram_gb <= 0:
        return {}

    # Calculate GPU budget
    gpu_budget_gb = total_vram_gb * min(max(0.1, gpu_fraction), 1.0)

    # Apply headroom
    headroom = get_vram_headroom_gb(custom_parameters=custom_parameters)
    gpu_budget_gb = max(1.0, gpu_budget_gb - headroom)

    result: Dict[int, str] = {0: f"{gpu_budget_gb:.1f}GiB"}

    if cpu_offload_gb > 0:
        result["cpu"] = f"{cpu_offload_gb:.1f}GiB"  # type: ignore

    return result


def clear_vram_cache() -> None:
    """Clear CUDA cache to free fragmented VRAM."""
    if not TORCH_AVAILABLE:
        return

    try:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            if hasattr(torch.cuda, "ipc_collect"):
                torch.cuda.ipc_collect()
            logger.debug("VRAM cache cleared")
    except Exception as exc:
        logger.debug("Failed to clear VRAM cache: %s", exc)


def get_vram_stats() -> Dict[str, float]:
    """Get current VRAM statistics.

    Returns:
        Dict with total, used, free VRAM in GB
    """
    total = get_total_vram_gb()
    free = get_free_vram_gb()
    used = max(0.0, total - free) if total > 0 else 0.0

    return {
        "total_gb": total,
        "free_gb": free,
        "used_gb": used,
        "utilization_pct": (used / total * 100) if total > 0 else 0.0,
    }


# =============================================================================
# Sprint 8.1: Advanced Memory Map Building (extracted from QwenManager)
# =============================================================================

from dataclasses import dataclass, field
from typing import Union


@dataclass
class MemoryMapResult:
    """Result of memory map computation."""
    memory_map: Optional[Dict[Union[int, str], str]] = None
    details: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = False
    reason: str = ""


def _get_percent_from_params(
    custom_parameters: Optional[Dict[str, Any]],
    key: str,
    default_value: int,
    env_key: Optional[str] = None,
) -> int:
    """Get percentage value from custom parameters.

    Args:
        custom_parameters: Custom parameters dict
        key: Parameter key
        default_value: Default value if not found
        env_key: Optional environment variable override

    Returns:
        Percentage value (10-99) or default
    """
    def _parse_percent(raw: Any) -> Optional[int]:
        try:
            value = int(raw)
        except Exception:
            return None
        if value < 10 or value > 99:
            return None
        return value

    if env_key:
        env_raw = os.getenv(env_key)
        if env_raw is not None and str(env_raw).strip():
            env_value = _parse_percent(env_raw)
            if env_value is not None:
                return env_value

    custom_value = _parse_percent((custom_parameters or {}).get(key))
    if custom_value is not None:
        return custom_value

    return default_value


def _get_gb_from_params_or_env(
    custom_parameters: Optional[Dict[str, Any]],
    custom_key: str,
    env_key: str,
) -> Optional[float]:
    """Get GB value from custom parameters or environment.

    Args:
        custom_parameters: Custom parameters dict
        custom_key: Parameter key
        env_key: Environment variable name

    Returns:
        GB value or None
    """
    value: Optional[float] = None
    try:
        raw_custom = (custom_parameters or {}).get(custom_key)
        if raw_custom is not None:
            parsed = float(raw_custom)
            if parsed > 0:
                value = parsed
    except Exception:
        value = None
    raw_env = os.getenv(env_key)
    if raw_env:
        try:
            parsed_env = float(raw_env)
            if parsed_env > 0:
                value = parsed_env
        except Exception:
            pass
    return value


def build_max_memory_map_detailed(
    *,
    custom_parameters: Optional[Dict[str, Any]] = None,
    is_survival_mode: bool = False,
    lowram_level: str = "normal",
    total_vram_gb: float = 0.0,
    free_vram_gb: float = 0.0,
    headroom_gb: float = 1.5,
    survival_cap_gb: float = 0.0,
) -> MemoryMapResult:
    """Build a detailed max_memory map for auto device placement.

    This is the core memory map computation extracted from QwenManager.
    It computes GPU and CPU memory budgets based on available resources
    and configuration parameters.

    Args:
        custom_parameters: Custom configuration parameters
        is_survival_mode: Whether survival mode is active
        lowram_level: Low RAM profile level ("normal", "tight", "critical")
        total_vram_gb: Total VRAM in GB
        free_vram_gb: Free VRAM in GB
        headroom_gb: VRAM headroom to reserve
        survival_cap_gb: Survival mode GPU budget cap (0 = no cap)

    Returns:
        MemoryMapResult with memory_map and details
    """
    # Check CUDA availability
    if not TORCH_AVAILABLE or not torch.cuda.is_available():
        return MemoryMapResult(
            enabled=False,
            reason="torch_or_cuda_unavailable",
            details={"enabled": False, "reason": "torch_or_cuda_unavailable"},
        )

    # Get free VRAM if not provided
    free_vram_source = "provided"
    if free_vram_gb <= 0:
        try:
            if hasattr(torch.cuda, "mem_get_info"):
                free_bytes, _ = torch.cuda.mem_get_info()
                free_vram_gb = free_bytes / (1024**3)
                free_vram_source = "mem_get_info"
        except Exception:
            free_vram_gb = 0.0
            free_vram_source = "mem_get_info_error"

        if not free_vram_gb and total_vram_gb > 0:
            free_vram_gb = total_vram_gb
            free_vram_source = "total_vram_fallback"

    if free_vram_gb <= 0:
        return MemoryMapResult(
            enabled=False,
            reason="free_vram_unknown",
            details={
                "enabled": False,
                "reason": "free_vram_unknown",
                "total_vram_gb": round(total_vram_gb, 3),
            },
        )

    # Determine default GPU percentage based on mode and VRAM
    if is_survival_mode:
        default_gpu_percent = 72 if lowram_level in {"tight", "critical"} else 78
    elif total_vram_gb and total_vram_gb <= 8.0:
        default_gpu_percent = 90
    elif total_vram_gb and total_vram_gb <= 12:
        default_gpu_percent = 90
    else:
        default_gpu_percent = 90

    gpu_percent = _get_percent_from_params(
        custom_parameters, "max_memory_gpu_percent", default_gpu_percent
    )
    requested_gpu_gb = _get_gb_from_params_or_env(
        custom_parameters, "max_memory_gpu_gb", "CVMATCH_MAX_MEMORY_GPU_GB"
    )

    # Compute GPU budget
    gpu_mode = "percent_total" if total_vram_gb > 0 else "percent_free"
    if requested_gpu_gb is not None:
        gpu_mode = "absolute_gb"
        requested_vram_budget_gb = float(requested_gpu_gb)
    else:
        requested_base = total_vram_gb if total_vram_gb > 0 else free_vram_gb
        requested_vram_budget_gb = requested_base * (gpu_percent / 100.0)

    # Apply survival mode cap
    applied_survival_cap = 0.0
    if is_survival_mode and survival_cap_gb > 0:
        if requested_vram_budget_gb > survival_cap_gb:
            requested_vram_budget_gb = survival_cap_gb
            gpu_mode = "survival_cap_gb"
            applied_survival_cap = survival_cap_gb

    # Compute available VRAM after headroom
    available_vram_gb = max(0.0, free_vram_gb - headroom_gb)
    clamp_reason = ""
    if available_vram_gb <= 0:
        fallback_available = max(0.25, free_vram_gb * 0.7)
        available_vram_gb = fallback_available
        clamp_reason = "free_minus_headroom_non_positive"

    # Final GPU budget
    vram_budget_gb = min(requested_vram_budget_gb, available_vram_gb, free_vram_gb)
    if vram_budget_gb < requested_vram_budget_gb and not clamp_reason:
        clamp_reason = "capped_by_free_minus_headroom"

    if vram_budget_gb <= 0:
        return MemoryMapResult(
            enabled=False,
            reason="gpu_budget_non_positive",
            details={
                "enabled": False,
                "reason": "gpu_budget_non_positive",
                "free_vram_gb": round(free_vram_gb, 3),
                "headroom_gb": round(headroom_gb, 3),
                "requested_vram_budget_gb": round(requested_vram_budget_gb, 3),
            },
        )

    vram_budget_mib = max(256, int(vram_budget_gb * 1024))
    memory_map: Dict[Union[int, str], str] = {0: f"{vram_budget_mib}MiB"}

    # CPU memory budget
    cpu_percent_value = _get_percent_from_params(
        custom_parameters,
        "max_memory_cpu_percent",
        80,
        env_key="CVMATCH_MAX_MEMORY_CPU_PERCENT",
    )
    cpu_available_ram_gb = 0.0
    cpu_headroom_gb = 2.0
    cpu_mode = "percent_available"
    cpu_requested_gb: Optional[float] = None
    cpu_applied_gb = 0.0
    cpu_clamp_reason = ""

    try:
        import psutil

        cpu_available_ram_gb = psutil.virtual_memory().available / (1024**3)
        cpu_requested_gb = _get_gb_from_params_or_env(
            custom_parameters, "max_memory_cpu_gb", "CVMATCH_MAX_MEMORY_CPU_GB"
        )

        # Get CPU headroom
        try:
            custom_headroom = (custom_parameters or {}).get("cpu_headroom_gb")
            if custom_headroom is not None:
                cpu_headroom_gb = max(0.5, float(custom_headroom))
            env_headroom = os.getenv("CVMATCH_CPU_HEADROOM_GB")
            if env_headroom:
                cpu_headroom_gb = max(0.5, float(env_headroom))
        except Exception:
            cpu_headroom_gb = 2.0

        available_cpu_for_model_gb = max(0.0, cpu_available_ram_gb - cpu_headroom_gb)

        if cpu_requested_gb is not None:
            cpu_mode = "absolute_gb"
            requested_cpu_budget_gb = float(cpu_requested_gb)
        else:
            requested_cpu_budget_gb = cpu_available_ram_gb * (cpu_percent_value / 100.0)

        if available_cpu_for_model_gb <= 0:
            cpu_applied_gb = max(0.0, min(requested_cpu_budget_gb, cpu_available_ram_gb))
            cpu_clamp_reason = "available_ram_below_headroom"
        else:
            cpu_applied_gb = min(requested_cpu_budget_gb, available_cpu_for_model_gb)
            if cpu_applied_gb < requested_cpu_budget_gb:
                cpu_clamp_reason = "capped_by_available_ram_minus_headroom"

        if cpu_applied_gb >= 1.0:
            ram_budget_mib = max(1024, int(cpu_applied_gb * 1024))
            memory_map["cpu"] = f"{ram_budget_mib}MiB"
    except Exception:
        pass

    # Build details
    details = {
        "enabled": True,
        "free_vram_source": free_vram_source,
        "total_vram_gb": round(total_vram_gb, 3),
        "free_vram_gb": round(free_vram_gb, 3),
        "headroom_gb": round(headroom_gb, 3),
        "available_vram_gb": round(available_vram_gb, 3),
        "gpu_mode": gpu_mode,
        "gpu_percent": gpu_percent,
        "gpu_budget_requested_gb": round(requested_vram_budget_gb, 3),
        "gpu_budget_final_gb": round(vram_budget_gb, 3),
        "gpu_budget_final_mib": vram_budget_mib,
        "gpu_clamp_reason": clamp_reason,
        "cpu_percent": cpu_percent_value,
        "cpu_mode": cpu_mode,
        "cpu_available_ram_gb": round(cpu_available_ram_gb, 3),
        "cpu_headroom_gb": round(cpu_headroom_gb, 3),
        "cpu_budget_requested_gb": (
            round(float(cpu_requested_gb), 3)
            if cpu_requested_gb is not None
            else (
                round(cpu_available_ram_gb * (cpu_percent_value / 100.0), 3)
                if cpu_available_ram_gb > 0
                else 0.0
            )
        ),
        "cpu_budget_final_gb": round(cpu_applied_gb, 3),
        "cpu_clamp_reason": cpu_clamp_reason,
        "memory_map": dict(memory_map),
        "survival_mode": is_survival_mode,
        "survival_gpu_cap_gb": round(applied_survival_cap, 3) if applied_survival_cap > 0 else 0.0,
        "lowram_level": lowram_level,
    }

    logger.info("Max memory map computed: %s", details)

    return MemoryMapResult(
        memory_map=memory_map,
        details=details,
        enabled=True,
        reason="success",
    )
