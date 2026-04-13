#!/usr/bin/env python3
"""Map changed files to a minimal pytest command set."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def select_targets(paths: list[str]) -> list[str]:
    targets: list[str] = []
    joined = " ".join(paths)
    if any("mass_apply" in path or "job_sources" in path for path in paths):
        targets.append("tests/mass_apply")
    if any(
        key in joined
        for key in (
            "app/schemas",
            "app/models",
            "profile_json",
            "cv_postprocessing",
            "llm_worker",
            "qwen_manager",
        )
    ):
        targets.append("tests/contracts")
    if any("views" in path or "controllers" in path for path in paths):
        targets.append("tests/integration/test_main_window_workflow.py")
    return targets or ["tests/contracts", "tests/mass_apply"]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.add_argument("paths", nargs="*")
    args = parser.parse_args(argv)

    targets = select_targets(args.paths)
    targets = [target for target in targets if Path(target).exists()]
    if not targets:
        targets = [
            target
            for target in ("tests/contracts", "tests/mass_apply")
            if Path(target).exists()
        ]
    print("[TESTS] targets:", " ".join(targets))
    if not args.run:
        return 0
    return subprocess.call([sys.executable, "-m", "pytest", *targets, "-q"])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
