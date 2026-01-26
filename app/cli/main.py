"""Command-line entry point for cvmatch-cli."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.workers.cv_extractor import CVExtractorWorker


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cvmatch-cli",
        description="Extract CV sections using the modular pipeline.",
    )
    parser.add_argument("--input", "-i", type=Path, required=True, help="Chemin vers un fichier texte (une ligne par segment).")
    parser.add_argument("--output", "-o", type=Path, help="Fichier de sortie JSON (stdout si omis).")
    return parser


def read_lines(path: Path) -> list[str]:
    content = path.read_text(encoding="utf-8")
    return [line.rstrip("\n") for line in content.splitlines()]


def cli(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.input.exists():
        parser.error(f"Input file not found: {args.input}")

    worker = CVExtractorWorker()
    lines = read_lines(args.input)

    result = worker.extract_from_lines(lines)

    payload = {
        "input": str(args.input),
        "used_legacy": result["used_legacy"],
        "used_pipeline": result.get("used_pipeline", not result["used_legacy"]),
        "payload": result["payload"],
        "modules": result["modules"],
        "errors": result["errors"],
    }

    serialized = json.dumps(payload, indent=2, ensure_ascii=False)
    if args.output:
        args.output.write_text(serialized + "\n", encoding="utf-8")
    else:
        print(serialized)

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(cli())
