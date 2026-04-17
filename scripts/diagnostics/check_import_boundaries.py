#!/usr/bin/env python3
"""Enforce lightweight architectural boundaries on touched files."""

from __future__ import annotations

import ast
import sys
from pathlib import Path


FORBIDDEN_VIEW_IMPORTS = {
    "requests",
    "aiohttp",
    "selenium",
    "app.integrations",
}
FORBIDDEN_CONTROLLER_IMPORTS = {
    "requests",
    "aiohttp",
    "selenium",
    "app.integrations.job_sources",
}


def _import_name(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if isinstance(node, ast.ImportFrom):
        module = node.module or ""
        return [module]
    return []


def _check_file(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    except Exception as exc:
        return [f"{path}: unable to parse imports ({exc})"]

    normalized = path.as_posix()
    failures: list[str] = []
    forbidden = None
    if normalized.startswith("app/views/") or "/app/views/" in normalized:
        forbidden = FORBIDDEN_VIEW_IMPORTS
    elif normalized.startswith("app/controllers/") or "/app/controllers/" in normalized:
        forbidden = FORBIDDEN_CONTROLLER_IMPORTS

    if forbidden is None:
        return failures

    for node in ast.walk(tree):
        for import_name in _import_name(node):
            if any(
                import_name == name or import_name.startswith(f"{name}.")
                for name in forbidden
            ):
                failures.append(f"{path}: forbidden import `{import_name}`")
    return failures


def main(argv: list[str]) -> int:
    failures: list[str] = []
    for raw in argv:
        path = Path(raw)
        if path.exists() and path.suffix == ".py":
            failures.extend(_check_file(path))

    if failures:
        print("[BOUNDARIES] failed")
        for failure in failures:
            print(f" - {failure}")
        return 1

    print("[BOUNDARIES] ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
