#!/usr/bin/env python3
"""Run the modular cv_extractor pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.workers.cv_extractor import CVExtractorWorker


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the modular cv_extractor pipeline.")
    parser.add_argument("--input", "-i", type=Path, required=True, help="Chemin vers un fichier texte (une ligne par segment).")
    parser.add_argument("--output", "-o", type=Path, help="Chemin de sortie JSON (stdout si omis).")
    return parser.parse_args(argv)


def load_lines(path: Path) -> list[str]:
    content = path.read_text(encoding="utf-8")
    return [line.rstrip("\n") for line in content.splitlines()]


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    if not args.input.exists():
        print(f"[error] Input file not found: {args.input}", file=sys.stderr)
        return 1

    lines = load_lines(args.input)

    worker = CVExtractorWorker()
    result = worker.extract_from_lines(lines)

    output = {
        "input": str(args.input),
        "used_pipeline": result.get("used_pipeline", not result["used_legacy"]),
        "used_legacy": result["used_legacy"],
        "payload": result["payload"],
        "modules": result["modules"],
        "errors": result["errors"],
    }

    serialized = json.dumps(output, indent=2, ensure_ascii=False)
    if args.output:
        args.output.write_text(serialized + "\n", encoding="utf-8")
    else:
        print(serialized)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
