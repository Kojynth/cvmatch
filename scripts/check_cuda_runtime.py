#!/usr/bin/env python3
"""Quick CUDA runtime probe for cvmatch.bat with explicit exit codes.

Exit codes:
- 0: torch installed and CUDA available
- 2: torch installed but CUDA unavailable
- 3: torch not installed
- 1: unexpected runtime error
"""

from __future__ import annotations

import sys


def main() -> int:
    try:
        import torch  # type: ignore
    except Exception as exc:
        print(f"TORCH_MISSING:{exc}", flush=True)
        return 3

    try:
        available = bool(torch.cuda.is_available())
        print(
            f"torch {torch.__version__} cuda_available {available} cuda {getattr(torch.version, 'cuda', None)}",
            flush=True,
        )
        return 0 if available else 2
    except Exception as exc:
        print(f"CUDA_CHECK_ERROR:{exc}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
