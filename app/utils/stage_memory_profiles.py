"""Stage-specific subprocess memory profiles."""

from __future__ import annotations

from typing import Dict


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

    # Override generic launcher defaults for cover-letter subprocesses.
    # The parent process may already export an anti-OOM profile tuned for
    # generic writer stages; cover-letter cold-loads need a stricter RAM-first
    # balance, so these keys must be explicit here.
    env["CVMATCH_PREFER_RAM_OFFLOAD"] = "1"
    env["CVMATCH_FORCE_DISK_OFFLOAD"] = "0"
    env["CVMATCH_FORCE_GPU"] = "0"
    env["CVMATCH_DISABLE_TORCH_COMPILE"] = "1"
    env["CVMATCH_KEEP_SELECTED_STAGE_MODEL"] = "1"
    env["CVMATCH_SURVIVAL_IGNORE_SELECTED_MODEL"] = "0"
    env["CVMATCH_MAX_MEMORY_GPU_GB"] = f"{gpu_cap_gb:.2f}"

    if attempt > 1:
        env["CVMATCH_SURVIVAL_MODE"] = "1"
        env["CVMATCH_VRAM_HEADROOM_GB"] = "3.25"
    else:
        env["CVMATCH_VRAM_HEADROOM_GB"] = "3.0"

    return env
