#!/usr/bin/env python3
"""Set the default LLM model profile for CVMatch."""
import argparse
import sys
from pathlib import Path


def _ensure_project_root_on_path() -> None:
    # scripts/ -> project root
    project_root = Path(__file__).resolve().parent.parent
    root_str = str(project_root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)


def main() -> int:
    _ensure_project_root_on_path()

    parser = argparse.ArgumentParser(description="Set CVMatch default model profile.")
    parser.add_argument("--model-id", required=True, help="Model profile id to set.")
    args = parser.parse_args()

    try:
        from app.utils.model_config_manager import model_config_manager
    except Exception as exc:
        print(f"ERROR: Failed to import model config manager: {exc}", file=sys.stderr)
        return 1

    ok = model_config_manager.update_model(args.model_id)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
