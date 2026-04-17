#!/usr/bin/env python3
"""Minimal syntax validation helper used by startup checks and CI."""

from __future__ import annotations

import argparse
import ast
from pathlib import Path
from typing import Iterable


DEFAULT_CRITICAL_MODULES = (
    "main.py",
    "app/models/database.py",
    "app/views/main_window.py",
    "app/workers/cv_extractor.py",
    "app/workers/llm_worker.py",
)


class SyntaxValidator:
    """Validate Python syntax and bytecode compilation for selected files."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root

    def validate_all(self, critical_only: bool = False) -> dict[str, object]:
        files = (
            [self.project_root / rel for rel in DEFAULT_CRITICAL_MODULES]
            if critical_only
            else list(self._iter_python_files())
        )
        validated = 0
        failures: list[str] = []
        for file_path in files:
            if not file_path.exists():
                failures.append(f"missing: {file_path}")
                continue
            validated += 1
            try:
                source = file_path.read_text(encoding="utf-8-sig")
                ast.parse(source, filename=str(file_path))
                compile(source, str(file_path), "exec")
            except Exception as exc:
                failures.append(f"{file_path}: {exc}")
        return {
            "validated_count": validated,
            "critical_failures": failures,
            "success": not failures,
        }

    def _iter_python_files(self) -> Iterable[Path]:
        for base in ("app", "cvextractor", "scripts", "tests"):
            root = self.project_root / base
            if not root.exists():
                continue
            yield from root.rglob("*.py")
        yield self.project_root / "main.py"


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Python syntax.")
    parser.add_argument("--critical-only", action="store_true")
    args = parser.parse_args()

    validator = SyntaxValidator(Path(__file__).resolve().parents[1])
    results = validator.validate_all(critical_only=args.critical_only)

    if results["success"]:
        print(
            f"[VALIDATE] OK - {results['validated_count']} file(s) checked"
        )
        return 0

    print("[VALIDATE] FAILED")
    for failure in results["critical_failures"]:
        print(f" - {failure}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
