"""Stage-specific subprocess memory profiles."""

from __future__ import annotations

from typing import Dict


_GENERIC_PARENT_DEFAULTS = {
    "CVMATCH_PREFER_RAM_OFFLOAD": {"0"},
    "CVMATCH_FORCE_DISK_OFFLOAD": {"1"},
    "CVMATCH_MAX_MEMORY_GPU_GB": {"6.5"},
    "CVMATCH_VRAM_HEADROOM_GB": {"2.0", "2.5"},
}


def _set_stage_value(
    env: Dict[str, str],
    key: str,
    value: str,
    *,
    generic_defaults: set[str] | None = None,
) -> None:
    """Set a stage value unless a non-generic explicit override already exists."""

    current = env.get(key)
    if current is None:
        env[key] = value
        return

    normalized = str(current).strip()
    allowed_defaults = generic_defaults or set()
    if normalized in allowed_defaults:
        env[key] = value


def apply_cover_letter_subprocess_memory_profile(
    run_env: Dict[str, str],
    *,
    total_vram_gb: float = 0.0,
    attempt: int = 1,
) -> Dict[str, str]:
    """Bias cover-letter subprocesses toward RAM-first hybrid placement.

    Cover-letter stages cold-load the selected writer model in a fresh
    subprocess. On 10-12GB GPUs this can fail even when CV stages passed,
    because the subprocess model load sits right on the VRAM edge.

    Keep the selected model, but constrain GPU placement harder and prefer
    CPU/RAM offload so the same model can still load.
    """

    env = dict(run_env or {})

    gpu_cap_gb = 6.0
    if total_vram_gb > 0:
        gpu_cap_gb = max(4.75, min(6.0, float(total_vram_gb) * 0.54))

    # Override generic launcher defaults for cover-letter subprocesses while
    # preserving host-specific explicit overrides inherited from the parent env.
    _set_stage_value(
        env,
        "CVMATCH_PREFER_RAM_OFFLOAD",
        "1",
        generic_defaults=_GENERIC_PARENT_DEFAULTS["CVMATCH_PREFER_RAM_OFFLOAD"],
    )
    _set_stage_value(
        env,
        "CVMATCH_FORCE_DISK_OFFLOAD",
        "0",
        generic_defaults=_GENERIC_PARENT_DEFAULTS["CVMATCH_FORCE_DISK_OFFLOAD"],
    )
    env.setdefault("CVMATCH_FORCE_GPU", "0")
    env.setdefault("CVMATCH_DISABLE_TORCH_COMPILE", "1")
    env.setdefault("CVMATCH_KEEP_SELECTED_STAGE_MODEL", "1")
    env.setdefault("CVMATCH_SURVIVAL_IGNORE_SELECTED_MODEL", "0")
    _set_stage_value(
        env,
        "CVMATCH_MAX_MEMORY_GPU_GB",
        f"{gpu_cap_gb:.2f}",
        generic_defaults=_GENERIC_PARENT_DEFAULTS["CVMATCH_MAX_MEMORY_GPU_GB"],
    )

    if attempt > 1:
        env.setdefault("CVMATCH_SURVIVAL_MODE", "1")
        _set_stage_value(
            env,
            "CVMATCH_VRAM_HEADROOM_GB",
            "3.25",
            generic_defaults=_GENERIC_PARENT_DEFAULTS["CVMATCH_VRAM_HEADROOM_GB"],
        )
    else:
        _set_stage_value(
            env,
            "CVMATCH_VRAM_HEADROOM_GB",
            "3.0",
            generic_defaults=_GENERIC_PARENT_DEFAULTS["CVMATCH_VRAM_HEADROOM_GB"],
        )

    return env
