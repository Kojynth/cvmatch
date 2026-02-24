"""
Memory Preflight Check Module (Sprint 4)

High-level memory validation before model loading.
Combines runtime_memory_policy.py and gpu_memory_budget.py to provide
a comprehensive pre-flight check for safe model loading.

Key features:
- Combined RAM + VRAM validation
- Platform-specific checks (Windows commit, Linux swap)
- Stage-aware memory requirements
- Clear error messages for users
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple

try:
    from ..logging.safe_logger import get_safe_logger
    from ..config import DEFAULT_PII_CONFIG
    logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

from .runtime_memory_policy import (
    get_lowram_profile,
    get_windows_commit_status_gb,
    estimate_required_ram_gb,
    get_system_ram_info,
)
from .gpu_memory_budget import (
    get_free_vram_gb,
    get_total_vram_gb,
    get_vram_headroom_gb,
    estimate_model_size_gb,
)


@dataclass
class PreflightResult:
    """Result of a memory preflight check."""
    can_proceed: bool
    error_message: Optional[str] = None
    warnings: Optional[list] = None
    memory_profile: Optional[Dict[str, Any]] = None

    def __bool__(self) -> bool:
        return self.can_proceed


# Minimum thresholds
MIN_VRAM_GB = 0.75
MIN_COMMIT_GB = 1.5
CRITICAL_RAM_GB = 1.0
LOW_SWAP_GB = 8.0
RECOMMENDED_PAGEFILE_GB = 16.0


def check_memory_before_load(
    *,
    model_name: Optional[str] = None,
    model_id: Optional[str] = None,
    device: str = "cpu",
    custom_parameters: Optional[Dict[str, Any]] = None,
    optimization_config: Optional[Dict[str, Any]] = None,
    is_survival_mode: bool = False,
    stage_name: str = "",
    stage_attempt: int = 1,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> PreflightResult:
    """Comprehensive memory check before model loading.

    This function validates that there's enough memory (RAM and/or VRAM)
    to safely load a model without crashing the system.

    Args:
        model_name: Model name/path for display
        model_id: Model identifier
        device: Target device ("cpu" or "cuda")
        custom_parameters: Custom configuration parameters
        optimization_config: Model optimization settings
        is_survival_mode: Whether survival mode is active
        stage_name: Current pipeline stage name
        stage_attempt: Current attempt number (1-based)
        progress_callback: Optional callback for progress updates

    Returns:
        PreflightResult with can_proceed flag and any error/warnings
    """
    warnings = []
    memory_profile: Dict[str, Any] = {}

    try:
        import psutil
        mem = psutil.virtual_memory()
        available_ram = mem.available / (1024 ** 3)
        total_ram = mem.total / (1024 ** 3)
        memory_profile["ram_available_gb"] = available_ram
        memory_profile["ram_total_gb"] = total_ram
    except ImportError:
        logger.warning("psutil not available - memory check skipped")
        return PreflightResult(
            can_proceed=True,
            warnings=["Memory check skipped: psutil not available"],
        )
    except Exception as e:
        logger.warning("Memory check error: %s", e)
        return PreflightResult(
            can_proceed=True,
            warnings=[f"Memory check error: {e}"],
        )

    # Get low RAM profile
    lowram_profile = get_lowram_profile(force_refresh=True)
    lowram_level = str(lowram_profile.get("level") or "normal")
    memory_profile["lowram_level"] = lowram_level
    memory_profile["lowram_profile"] = lowram_profile

    # Determine if this is a writer stage (more lenient for quality)
    writer_stage = _is_writer_stage(stage_name)
    writer_first_attempt = writer_stage and stage_attempt <= 1

    # Platform-specific checks
    swap_total_gb = 0.0
    pagefile_total_gb = 0.0
    commit_available_gb = 0.0

    try:
        import psutil
        swap_total_gb = psutil.swap_memory().total / (1024 ** 3)
        memory_profile["swap_total_gb"] = swap_total_gb
    except Exception:
        pass

    if os.name == "nt":
        # Windows-specific checks
        pagefile_total_gb, commit_available_gb = get_windows_commit_status_gb()
        memory_profile["pagefile_total_gb"] = pagefile_total_gb
        memory_profile["commit_available_gb"] = commit_available_gb

        effective_pagefile_gb = max(swap_total_gb, pagefile_total_gb)
        if effective_pagefile_gb > 0 and effective_pagefile_gb < RECOMMENDED_PAGEFILE_GB:
            warnings.append(
                f"Windows pagefile is small: {effective_pagefile_gb:.1f}GB "
                f"(recommended {RECOMMENDED_PAGEFILE_GB:.0f}GB or more for LLM loading)"
            )
            logger.warning(
                "Windows pagefile is small: %.1fGB (recommended %.0f-32GB on low RAM).",
                effective_pagefile_gb,
                RECOMMENDED_PAGEFILE_GB,
            )

        # Check commit memory
        if commit_available_gb > 0 and commit_available_gb < MIN_COMMIT_GB:
            if writer_first_attempt and commit_available_gb >= 0.8:
                warnings.append(
                    f"Low commit memory ({commit_available_gb:.1f}GB): "
                    "allowing one quality-first load attempt"
                )
                logger.warning(
                    "Writer stage first attempt with low commit (%.1fGB): "
                    "allowing one quality-first load try.",
                    commit_available_gb,
                )
            else:
                error_msg = (
                    f"Insufficient Windows commit memory: {commit_available_gb:.1f}GB available. "
                    "Model loading cancelled to prevent system crash. "
                    "Try increasing your pagefile size or closing other applications."
                )
                return PreflightResult(
                    can_proceed=False,
                    error_message=error_msg,
                    memory_profile=memory_profile,
                )

        if lowram_level in {"tight", "critical"}:
            logger.warning(
                "LowRAM Windows detected: level=%s ram=%.1fGB commit=%.1fGB",
                lowram_level,
                available_ram,
                commit_available_gb,
            )

    else:
        # Linux/Mac checks
        if device != "cpu" and is_survival_mode and swap_total_gb < LOW_SWAP_GB:
            warnings.append(
                f"Low swap in survival mode: {swap_total_gb:.1f}GB (recommended >= {LOW_SWAP_GB:.0f}GB)"
            )
            logger.warning(
                "Swap Linux low in Survival mode: %.1fGB (recommended >= %.0fGB).",
                swap_total_gb,
                LOW_SWAP_GB,
            )

        if lowram_level in {"tight", "critical"}:
            effective_available = float(lowram_profile.get("effective_available_gb") or 0.0)
            logger.warning(
                "LowRAM Linux detected: level=%s ram=%.1fGB swap=%.1fGB effective=%.1fGB",
                lowram_level,
                available_ram,
                swap_total_gb,
                effective_available,
            )

    # GPU-specific checks
    if device != "cpu":
        free_vram = get_free_vram_gb()
        total_vram = get_total_vram_gb()
        memory_profile["vram_free_gb"] = free_vram
        memory_profile["vram_total_gb"] = total_vram

        if free_vram > 0:
            headroom = get_vram_headroom_gb(
                custom_parameters=custom_parameters,
                free_vram_gb=free_vram,
                total_vram_gb=total_vram,
            )
            memory_profile["vram_headroom_gb"] = headroom

            if free_vram < MIN_VRAM_GB:
                model_display = model_name or model_id or "model"
                error_msg = (
                    f"Insufficient VRAM to load {model_display}: "
                    f"{free_vram:.2f}GB free (total {total_vram:.2f}GB). "
                    "Model loading cancelled due to insufficient VRAM."
                )
                return PreflightResult(
                    can_proceed=False,
                    error_message=error_msg,
                    memory_profile=memory_profile,
                )

            if free_vram < max(1.0, headroom):
                warnings.append(
                    f"VRAM is tight: {free_vram:.2f}GB free "
                    f"(target headroom {headroom:.2f}GB, total {total_vram:.2f}GB)"
                )
                logger.warning(
                    "VRAM before load is tight: free=%.2fGB headroom_target=%.2fGB total=%.2fGB",
                    free_vram,
                    headroom,
                    total_vram,
                )

        # RAM check for GPU mode
        result = _check_ram_for_gpu_load(
            available_ram=available_ram,
            total_ram=total_ram,
            commit_available_gb=commit_available_gb,
            swap_total_gb=swap_total_gb,
            writer_first_attempt=writer_first_attempt,
            model_name=model_name,
            memory_profile=memory_profile,
        )
        if result:
            return result

        return PreflightResult(
            can_proceed=True,
            warnings=warnings if warnings else None,
            memory_profile=memory_profile,
        )

    # CPU-only checks
    required_ram = estimate_required_ram_gb(
        model_name=model_name,
        model_id=model_id,
        optimization_config=optimization_config,
    )
    memory_profile["required_ram_gb"] = required_ram

    # Check with 20% safety margin
    if available_ram < required_ram * 0.8:
        model_display = model_name or model_id or "model"
        error_msg = (
            f"Insufficient memory to load {model_display}: "
            f"{available_ram:.1f}GB available (of {total_ram:.1f}GB total), "
            f"~{required_ram:.1f}GB required. "
            "Model loading cancelled due to insufficient RAM."
        )
        return PreflightResult(
            can_proceed=False,
            error_message=error_msg,
            memory_profile=memory_profile,
        )

    # Warning if memory is tight
    if available_ram < required_ram * 1.2:
        warnings.append(
            f"Memory is limited: {available_ram:.1f}GB available "
            f"(recommended: {required_ram:.1f}GB). Loading may be slow."
        )
        logger.warning(
            "Memory available limited (%.1fGB) for %s (recommended: %.1fGB). "
            "Loading might be slow.",
            available_ram,
            model_name or "model",
            required_ram,
        )

    return PreflightResult(
        can_proceed=True,
        warnings=warnings if warnings else None,
        memory_profile=memory_profile,
    )


def _check_ram_for_gpu_load(
    *,
    available_ram: float,
    total_ram: float,
    commit_available_gb: float,
    swap_total_gb: float,
    writer_first_attempt: bool,
    model_name: Optional[str],
    memory_profile: Dict[str, Any],
) -> Optional[PreflightResult]:
    """Check RAM availability for GPU model loading.

    Returns PreflightResult if check fails, None if OK.
    """
    if available_ram < CRITICAL_RAM_GB:
        if os.name == "nt":
            if commit_available_gb > 1.5:
                logger.warning(
                    "RAM very low (%.1fGB) but commit sufficient (%.1fGB): "
                    "attempting degraded mode load.",
                    available_ram,
                    commit_available_gb,
                )
                return None
            elif writer_first_attempt and commit_available_gb >= 0.8:
                logger.warning(
                    "Writer stage first attempt with very low RAM (%.1fGB) "
                    "and borderline commit (%.1fGB): trying selected model once.",
                    available_ram,
                    commit_available_gb,
                )
                return None
            else:
                error_msg = (
                    f"Insufficient system memory to load {model_name or 'model'}: "
                    f"{available_ram:.1f}GB available (of {total_ram:.1f}GB), "
                    f"commit={commit_available_gb:.1f}GB. "
                    "Model loading cancelled due to insufficient RAM/commit."
                )
                return PreflightResult(
                    can_proceed=False,
                    error_message=error_msg,
                    memory_profile=memory_profile,
                )
        else:
            # Linux/Mac
            if swap_total_gb >= LOW_SWAP_GB:
                logger.warning(
                    "RAM very low (%.1fGB) but swap present (%.1fGB): "
                    "attempting degraded mode load.",
                    available_ram,
                    swap_total_gb,
                )
                return None
            elif writer_first_attempt and swap_total_gb >= 4.0:
                logger.warning(
                    "Writer stage first attempt with low RAM (%.1fGB) "
                    "and moderate swap (%.1fGB): trying selected model once.",
                    available_ram,
                    swap_total_gb,
                )
                return None
            else:
                error_msg = (
                    f"Insufficient system memory to load {model_name or 'model'}: "
                    f"{available_ram:.1f}GB available (of {total_ram:.1f}GB), "
                    f"swap={swap_total_gb:.1f}GB. "
                    "Model loading cancelled due to insufficient RAM/swap."
                )
                return PreflightResult(
                    can_proceed=False,
                    error_message=error_msg,
                    memory_profile=memory_profile,
                )
    elif available_ram < 2.0:
        logger.warning(
            "RAM available limited for GPU loading: %.1fGB (total %.1fGB).",
            available_ram,
            total_ram,
        )

    return None


def _is_writer_stage(stage_name: str) -> bool:
    """Check if stage is a writer stage (requires higher quality model)."""
    stage_key = str(stage_name or "").strip().lower()
    writer_stages = {"draft", "final", "cover_letter", "cover_letter_critic"}
    return stage_key in writer_stages


def log_memory_status(
    context: str = "",
    *,
    include_gpu: bool = True,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """Log current memory status for debugging.

    Args:
        context: Context label for logging
        include_gpu: Include GPU memory info
        progress_callback: Optional callback for progress updates

    Returns:
        Dict with memory statistics
    """
    prefix = f"[{context}] " if context else ""
    stats: Dict[str, Any] = {}

    # RAM stats
    ram_info = get_system_ram_info()
    stats["ram"] = ram_info
    logger.info(
        "%sRAM: %.1fGB available / %.1fGB total (%.0f%% used)",
        prefix,
        ram_info["available_gb"],
        ram_info["total_gb"],
        ram_info["percent_used"],
    )

    # Low RAM profile
    lowram = get_lowram_profile()
    stats["lowram_level"] = lowram.get("level", "unknown")
    if lowram.get("level") != "normal":
        logger.warning(
            "%sLowRAM profile: level=%s reason=%s",
            prefix,
            lowram.get("level"),
            lowram.get("reason"),
        )

    # Windows commit
    if os.name == "nt":
        pagefile, commit = get_windows_commit_status_gb()
        stats["pagefile_total_gb"] = pagefile
        stats["commit_available_gb"] = commit
        logger.info(
            "%sWindows commit: %.1fGB available / %.1fGB pagefile",
            prefix,
            commit,
            pagefile,
        )

    # GPU stats
    if include_gpu:
        free_vram = get_free_vram_gb()
        total_vram = get_total_vram_gb()
        if total_vram > 0:
            stats["vram_free_gb"] = free_vram
            stats["vram_total_gb"] = total_vram
            logger.info(
                "%sVRAM: %.2fGB free / %.2fGB total",
                prefix,
                free_vram,
                total_vram,
            )

    return stats


def format_memory_error_hint(error_msg: str) -> Optional[str]:
    """Generate a helpful hint based on error message.

    Args:
        error_msg: The error message

    Returns:
        Helpful hint string, or None if no hint available
    """
    lowered = error_msg.lower()

    if "cuda out of memory" in lowered or "out of memory" in lowered:
        return (
            "Hint: GPU/RAM memory insufficient. "
            "Adjust memory budget or choose a smaller model."
        )
    if "commit" in lowered and "insuffisant" in lowered:
        return (
            "Hint: Windows pagefile too small. "
            "Increase pagefile size in System Settings or close other applications."
        )
    if "vram insuffisante" in lowered:
        return (
            "Hint: Insufficient VRAM. "
            "Close GPU-heavy applications or choose a smaller/quantized model."
        )

    return None
