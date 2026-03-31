"""Stage-specific subprocess memory profiles."""

from __future__ import annotations

from typing import Dict


_GENERIC_PARENT_DEFAULTS = {
    "CVMATCH_PREFER_RAM_OFFLOAD": {"0"},
    "CVMATCH_FORCE_DISK_OFFLOAD": {"1"},
    "CVMATCH_MAX_MEMORY_GPU_GB": {"6.5"},
    "CVMATCH_VRAM_HEADROOM_GB": {"2.0", "2.5"},
}
_GENERIC_NUMERIC_KEYS = {
    "CVMATCH_MAX_MEMORY_GPU_GB",
    "CVMATCH_VRAM_HEADROOM_GB",
}


def _matches_generic_default(
    key: str,
    current: str,
    generic_defaults: set[str],
) -> bool:
    normalized = str(current or "").strip()
    if not normalized:
        return False
    if normalized in generic_defaults:
        return True
    if key not in _GENERIC_NUMERIC_KEYS:
        return False

    try:
        current_value = float(normalized)
    except Exception:
        return False

    for candidate in generic_defaults:
        try:
            if abs(current_value - float(candidate)) <= 1e-9:
                return True
        except Exception:
            continue
    return False


def _recommend_cover_letter_gpu_cap_gb(
    total_vram_gb: float,
    *,
    attempt: int = 1,
) -> float:
    """Return a stage-specific GPU cap without over-constraining high-VRAM hosts."""

    total_vram = float(total_vram_gb or 0.0)
    if total_vram <= 0:
        return 6.0 if attempt > 1 else 6.25
    if total_vram <= 12.0:
        if attempt > 1:
            return max(4.75, min(6.0, total_vram * 0.54))
        return max(5.5, min(6.35, total_vram * 0.57))
    if total_vram <= 16.0:
        if attempt > 1:
            return max(6.0, min(7.0, total_vram * 0.48))
        return max(6.5, min(9.5, total_vram * 0.62))
    if attempt > 1:
        return 7.0
    return max(8.0, min(14.0, total_vram * 0.68))


def _recommend_cover_letter_headroom_gb(
    total_vram_gb: float,
    *,
    attempt: int = 1,
) -> float:
    """Return a cover-letter-specific VRAM headroom target."""

    total_vram = float(total_vram_gb or 0.0)
    if attempt > 1:
        if total_vram > 12.0:
            return 2.75
        return 3.25
    if total_vram > 16.0:
        return 2.25
    if total_vram > 12.0:
        return 2.5
    return 2.5


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

    allowed_defaults = generic_defaults or set()
    if _matches_generic_default(key, str(current), allowed_defaults):
        env[key] = value


def apply_cover_letter_subprocess_memory_profile(
    run_env: Dict[str, str],
    *,
    total_vram_gb: float = 0.0,
    attempt: int = 1,
) -> Dict[str, str]:
    """Bias cover-letter subprocesses toward writer-aligned disk-offload placement.

    Cover-letter stages cold-load the selected writer model in a fresh
    subprocess. On 10-12GB GPUs this can fail even when CV stages passed,
    because the subprocess model load sits right on the VRAM edge.

    Keep the selected model and stay aligned with the generic writer
    disk-offload path that already succeeds for draft/final stages, while
    tightening GPU budget and headroom on retries.
    """

    env = dict(run_env or {})

    gpu_cap_gb = _recommend_cover_letter_gpu_cap_gb(
        total_vram_gb,
        attempt=attempt,
    )
    headroom_gb = _recommend_cover_letter_headroom_gb(
        total_vram_gb,
        attempt=attempt,
    )

    # Override generic launcher defaults for cover-letter subprocesses while
    # preserving host-specific explicit overrides inherited from the parent env.
    _set_stage_value(
        env,
        "CVMATCH_PREFER_RAM_OFFLOAD",
        "0",
        generic_defaults=_GENERIC_PARENT_DEFAULTS["CVMATCH_PREFER_RAM_OFFLOAD"],
    )
    _set_stage_value(
        env,
        "CVMATCH_FORCE_DISK_OFFLOAD",
        "1",
        generic_defaults=_GENERIC_PARENT_DEFAULTS["CVMATCH_FORCE_DISK_OFFLOAD"],
    )
    env.setdefault("CVMATCH_FORCE_GPU", "0")
    env.setdefault("CVMATCH_DISABLE_TORCH_COMPILE", "1")
    env.setdefault("CVMATCH_KEEP_SELECTED_STAGE_MODEL", "1")
    # Intentional: cover-letter stages keep the user-selected writer model
    # locked even under survival-mode retries. Product policy here is to
    # rebalance memory, not silently downshift to a smaller writer model.
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
            f"{headroom_gb:.2f}",
            generic_defaults=_GENERIC_PARENT_DEFAULTS["CVMATCH_VRAM_HEADROOM_GB"],
        )
    else:
        _set_stage_value(
            env,
            "CVMATCH_VRAM_HEADROOM_GB",
            f"{headroom_gb:.2f}",
            generic_defaults=_GENERIC_PARENT_DEFAULTS["CVMATCH_VRAM_HEADROOM_GB"],
        )

    return env
