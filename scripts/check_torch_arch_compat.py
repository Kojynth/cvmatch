#!/usr/bin/env python3
"""Check whether current torch build supports the active CUDA GPU architecture.

Output (KEY=VALUE lines):
- TORCH_CHECK_STATUS: supported|unsupported|cuda_unavailable|torch_missing|error
- TORCH_VERSION
- CUDA_VERSION
- GPU_NAME
- GPU_ARCH
- GPU_ARCH_LIST
- GPU_ARCH_SUPPORTED: 0|1

Exit codes:
- 0: supported
- 2: unsupported architecture
- 3: CUDA unavailable
- 4: torch missing
- 1: unexpected error
"""

from __future__ import annotations

import sys
from typing import List


def _print(key: str, value: object) -> None:
    print(f"{key}={value}", flush=True)


def main() -> int:
    try:
        import torch  # type: ignore
    except Exception as exc:
        _print("TORCH_CHECK_STATUS", "torch_missing")
        _print("TORCH_CHECK_ERROR", str(exc))
        return 4

    _print("TORCH_VERSION", getattr(torch, "__version__", "unknown"))
    _print("CUDA_VERSION", getattr(torch.version, "cuda", None))

    try:
        cuda_available = bool(torch.cuda.is_available())
    except Exception as exc:
        _print("TORCH_CHECK_STATUS", "error")
        _print("TORCH_CHECK_ERROR", str(exc))
        return 1

    if not cuda_available:
        _print("TORCH_CHECK_STATUS", "cuda_unavailable")
        _print("GPU_ARCH_SUPPORTED", 0)
        return 3

    gpu_name = "unknown"
    try:
        gpu_name = str(torch.cuda.get_device_name(0) or "unknown")
    except Exception:
        pass
    _print("GPU_NAME", gpu_name)

    gpu_arch = "unknown"
    try:
        major, minor = torch.cuda.get_device_capability(0)
        gpu_arch = f"sm_{major}{minor}"
    except Exception:
        pass
    _print("GPU_ARCH", gpu_arch)

    arch_list: List[str] = []
    try:
        arch_list = list(torch.cuda.get_arch_list() or [])
    except Exception:
        arch_list = []
    _print("GPU_ARCH_LIST", " ".join(arch_list))

    supported = gpu_arch != "unknown" and gpu_arch in arch_list
    _print("GPU_ARCH_SUPPORTED", 1 if supported else 0)
    _print("TORCH_CHECK_STATUS", "supported" if supported else "unsupported")
    return 0 if supported else 2


if __name__ == "__main__":
    raise SystemExit(main())
