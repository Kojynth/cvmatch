#!/usr/bin/env python3
"""Reject accidental commits of runtime artifacts and ghost source files."""

from __future__ import annotations

import sys
from pathlib import Path


FORBIDDEN_SEGMENTS = (
    "__pycache__",
    "logs",
    "exports",
    "output",
    "runtime",
    ".hf_cache",
)
FORBIDDEN_SUFFIXES = (
    ".pyc",
    ".pyo",
    ".bak",
    ".backup",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".log",
)


def _is_forbidden(path: Path) -> str | None:
    normalized = path.as_posix()
    if any(segment in normalized.split("/") for segment in FORBIDDEN_SEGMENTS):
        return "runtime/artifact directory is not allowed in versioned changes"
    if path.suffix.lower() in FORBIDDEN_SUFFIXES:
        return f"forbidden file suffix: {path.suffix}"
    if normalized.endswith(".py.backup") or normalized.endswith(".py.old"):
        return "backup source files are not allowed"
    return None


def main(argv: list[str]) -> int:
    candidates = [Path(arg) for arg in argv] if argv else [Path(".")]
    failures: list[str] = []

    for candidate in candidates:
        if candidate == Path("."):
            for path in Path(".").rglob("*"):
                if path.is_file():
                    reason = _is_forbidden(path)
                    if reason:
                        failures.append(f"{path}: {reason}")
            break
        if candidate.exists():
            reason = _is_forbidden(candidate)
            if reason:
                failures.append(f"{candidate}: {reason}")

    if failures:
        print("[HYGIENE] failed")
        for failure in failures:
            print(f" - {failure}")
        return 1

    print("[HYGIENE] ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
