#!/usr/bin/env python3
"""Best-effort scan for obvious PII in tracked text files."""

from __future__ import annotations

import re
import sys
from pathlib import Path


EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
ALLOWED_DOMAINS = {"example.com", "example.org", "example.net", "example.local"}
TEXT_SUFFIXES = {".py", ".md", ".txt", ".json", ".yaml", ".yml", ".toml"}


def _scan_file(path: Path) -> list[str]:
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return []
    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        return []

    failures: list[str] = []
    for match in EMAIL_PATTERN.finditer(content):
        domain = match.group(1).lower()
        if domain not in ALLOWED_DOMAINS:
            failures.append(f"{path}: possible real email address `{match.group(0)}`")
    return failures


def main(argv: list[str]) -> int:
    failures: list[str] = []
    for raw in argv:
        path = Path(raw)
        if path.exists() and path.is_file():
            failures.extend(_scan_file(path))

    if failures:
        print("[PII] failed")
        for failure in failures:
            print(f" - {failure}")
        return 1

    print("[PII] ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
