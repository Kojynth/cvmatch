#!/usr/bin/env python3
"""Check whether required AI model caches exist for CVMatch."""
import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional, Set, Union


BASE_MODELS = [
    "joeddav/xlm-roberta-large-xnli",
    "CATIE-AQ/NERmembert-large-3entities",
    "Davlan/xlm-roberta-base-ner-hrl",
]

LITE_MODELS = [
    "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli",
    "Davlan/xlm-roberta-base-ner-hrl",
    "dslim/bert-base-NER",
]

DEFAULT_LLM_MODELS = [
    "Qwen/Qwen2.5-7B-Instruct",
    "mistralai/Mistral-7B-Instruct-v0.3",
    "Qwen/Qwen2.5-0.5B-Instruct",
]

MODE_CHOICES = ("full", "lite", "llm-only", "base-only")


def build_cache_dirs(project_root: Path) -> List[Path]:
    candidates: Set[Path] = set()

    def add(path: Optional[Union[str, Path]]) -> None:
        if not path:
            return
        candidates.add(Path(path).expanduser())

    add(os.environ.get("CVMATCH_HF_CACHE"))
    add(os.environ.get("HUGGINGFACE_HUB_CACHE"))
    add(os.environ.get("HF_HUB_CACHE"))
    add(os.environ.get("TRANSFORMERS_CACHE"))
    hf_home = os.environ.get("HF_HOME")
    if hf_home:
        add(Path(hf_home) / "hub")

    add(project_root / "cache" / "hf_models")
    add(project_root / ".hf_cache")
    add(Path.home() / ".cache" / "huggingface" / "hub")

    return [path for path in candidates if path]


def _dedupe_models(models: List[str]) -> List[str]:
    seen = set()
    result = []
    for model in models:
        model = (model or "").strip()
        if not model or model in seen:
            continue
        seen.add(model)
        result.append(model)
    return result


def _resolve_llm_models(args: argparse.Namespace) -> List[str]:
    if args.llm_models:
        return _dedupe_models(args.llm_models)

    env_models = os.environ.get("CVMATCH_LLM_MODELS") or os.environ.get(
        "CVMATCH_LLM_MODEL_ID"
    )
    if env_models:
        parts = [item.strip() for item in env_models.split(",") if item.strip()]
        if parts:
            return _dedupe_models(parts)

    return list(DEFAULT_LLM_MODELS)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check required AI model caches.")
    parser.add_argument(
        "--mode",
        choices=MODE_CHOICES,
        default=os.environ.get("CVMATCH_AI_MODE", "full"),
        help="Model set to check: full, lite, llm-only, base-only.",
    )
    parser.add_argument(
        "--include-llm",
        action="store_true",
        help="Require a lightweight LLM cache for structured extraction.",
    )
    parser.add_argument(
        "--llm-model",
        action="append",
        dest="llm_models",
        default=[],
        help="LLM model id to check (repeatable).",
    )
    args = parser.parse_args()

    mode = (args.mode or "full").strip().lower()
    include_llm = args.include_llm or os.environ.get("CVMATCH_CHECK_LLM") == "1"
    project_root = Path(__file__).resolve().parents[1]
    cache_dirs = build_cache_dirs(project_root)
    missing = []

    base_models = list(BASE_MODELS)
    if mode == "lite":
        base_models = list(LITE_MODELS)
    elif mode == "llm-only":
        base_models = []
        include_llm = True
    elif mode == "base-only":
        include_llm = False

    base_models = _dedupe_models(base_models)
    llm_models = _resolve_llm_models(args) if include_llm else []

    for model_id in base_models:
        model_dir = f"models--{model_id.replace('/', '--')}"
        found = any((cache_dir / model_dir).exists() for cache_dir in cache_dirs)
        if not found:
            missing.append(model_id)

    if include_llm:
        llm_found = False
        for model_id in llm_models:
            model_dir = f"models--{model_id.replace('/', '--')}"
            if any((cache_dir / model_dir).exists() for cache_dir in cache_dirs):
                llm_found = True
                break
        if not llm_found:
            missing.extend(llm_models)

    if missing:
        print("MISSING")
        for model_id in missing:
            print(model_id)
        return 2

    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
