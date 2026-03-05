#!/usr/bin/env python3
"""Fast critical dependency import check used by cvmatch.bat."""

from __future__ import annotations

import importlib
import sys


MODULES = [
    "PySide6",
    "loguru",
    "sqlmodel",
    "pandas",
    "numpy",
    "requests",
    "dateutil",
    "pydantic",
    "pypdf",
    "docx",
    "bs4",
    "fitz",
    "PIL",
    "jinja2",
    "psutil",
    "selenium",
]


def main() -> int:
    for module in MODULES:
        print(f"CHECK:{module}", flush=True)
        try:
            importlib.import_module(module)
        except Exception as exc:
            print(f"FAIL:{module}:{exc}", flush=True)
            return 1

    print("ALL_OK", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
