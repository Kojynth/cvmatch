#!/usr/bin/env python3
"""Compile touched Python files to catch syntax regressions early."""

from __future__ import annotations

import py_compile
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    failures: list[str] = []
    for raw in argv:
        path = Path(raw)
        if not path.exists() or path.suffix != ".py":
            continue
        try:
            py_compile.compile(str(path), doraise=True)
        except Exception as exc:
            failures.append(f"{path}: {exc}")

    if failures:
        print("[COMPILE] failed")
        for failure in failures:
            print(f" - {failure}")
        return 1

    print("[COMPILE] ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
