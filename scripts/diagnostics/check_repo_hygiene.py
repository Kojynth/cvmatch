#!/usr/bin/env python3
"""Reject accidental commits of runtime artifacts and ghost source files."""

from __future__ import annotations

import subprocess
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
SKIP_SEGMENTS = (
    ".git",
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


def _should_skip(path: Path) -> bool:
    return any(segment in path.as_posix().split("/") for segment in SKIP_SEGMENTS)


def _iter_git_visible_files() -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        files: list[Path] = []
        for path in Path(".").rglob("*"):
            if _should_skip(path):
                continue
            if path.is_file():
                files.append(path)
        return files

    output: list[Path] = []
    seen: set[str] = set()
    for raw_line in result.stdout.splitlines():
        raw = raw_line.strip()
        if not raw:
            continue
        path = Path(raw)
        if _should_skip(path):
            continue
        if not path.exists() or not path.is_file():
            continue
        key = path.as_posix()
        if key in seen:
            continue
        seen.add(key)
        output.append(path)
    return output


def main(argv: list[str]) -> int:
    candidates = [Path(arg) for arg in argv] if argv else [Path(".")]
    failures: list[str] = []

    for candidate in candidates:
        if candidate == Path("."):
            for path in _iter_git_visible_files():
                reason = _is_forbidden(path)
                if reason:
                    failures.append(f"{path}: {reason}")
            break
        if candidate.exists():
            if _should_skip(candidate):
                continue
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
