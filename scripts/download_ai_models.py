#!/usr/bin/env python
"""Utility to download CVMatch AI models into a local cache."""
from __future__ import annotations

import argparse
import os
import sys
import time
from typing import List

if os.name == "nt":
    # Avoid symlink privilege errors on Windows by forcing file copies.
    os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"
    os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

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
    "Qwen/Qwen2.5-0.5B-Instruct",
]

MODE_CHOICES = ("full", "lite", "llm-only", "base-only")


def _resolve_default_cache() -> str:
    env_cache = (
        os.environ.get("CVMATCH_HF_CACHE")
        or os.environ.get("HUGGINGFACE_HUB_CACHE")
        or os.environ.get("HF_HUB_CACHE")
    )
    if env_cache:
        return os.path.abspath(env_cache)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".hf_cache"))


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Download the AI models required by CVMatch.")
    default_cache = _resolve_default_cache()
    parser.add_argument(
        "--cache-dir",
        default=default_cache,
        help="Destination directory for downloaded models (default: %(default)s)",
    )
    parser.add_argument(
        "--mode",
        choices=MODE_CHOICES,
        default=os.environ.get("CVMATCH_AI_MODE", "full"),
        help="Download set to use: full, lite, llm-only, base-only.",
    )
    parser.add_argument(
        "--include-llm",
        action="store_true",
        help="Download a lightweight LLM for structured extraction.",
    )
    parser.add_argument(
        "--llm-model",
        action="append",
        dest="llm_models",
        default=[],
        help="LLM model id to download (repeatable).",
    )
    parser.add_argument(
        "--skip-llm",
        action="store_true",
        help="Skip LLM downloads even if include-llm is set.",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=_env_int("CVMATCH_HF_MAX_WORKERS", 0),
        help="Max concurrent download workers (default: auto).",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=_env_int("CVMATCH_HF_RETRIES", 2),
        help="Number of retries per model on failure.",
    )
    parser.add_argument(
        "--retry-wait",
        type=float,
        default=_env_float("CVMATCH_HF_RETRY_WAIT", 5.0),
        help="Seconds to wait between retries (base backoff).",
    )
    args = parser.parse_args()

    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("ERROR: huggingface_hub package is not installed. Run `pip install huggingface_hub` and retry.", file=sys.stderr)
        return 1

    cache_dir = os.path.abspath(args.cache_dir)
    os.makedirs(cache_dir, exist_ok=True)

    mode = (args.mode or "full").strip().lower()
    base_models = list(BASE_MODELS)
    include_llm = args.include_llm
    if mode == "lite":
        base_models = list(LITE_MODELS)
    elif mode == "llm-only":
        base_models = []
        include_llm = True
    elif mode == "base-only":
        include_llm = False

    if args.skip_llm:
        include_llm = False

    models = list(base_models)
    llm_models: List[str] = []
    if include_llm:
        if args.llm_models:
            llm_models = args.llm_models
        else:
            llm_models = DEFAULT_LLM_MODELS

    if llm_models:
        print("Including LLM models:")
        for model in llm_models:
            print(f"- {model}")
        models.extend(llm_models)

    models = _dedupe_models(models)

    for model in models:
        print(f"Downloading {model} into {cache_dir} ...")
        attempts = max(0, args.retries) + 1
        workers = args.max_workers if args.max_workers > 0 else None
        for attempt in range(1, attempts + 1):
            try:
                kwargs = {
                    "repo_id": model,
                    "cache_dir": cache_dir,
                    "resume_download": True,
                    "local_files_only": False,
                }
                if workers:
                    kwargs["max_workers"] = workers
                snapshot_download(**kwargs)
                break
            except Exception as exc:
                if attempt >= attempts:
                    print(f"ERROR: Could not download {model}. {exc}", file=sys.stderr)
                    print(
                        "If the error mentions '401', run `huggingface-cli login` and retry.",
                        file=sys.stderr,
                    )
                    return 2
                wait = max(0.0, args.retry_wait) * attempt
                if workers != 1:
                    workers = 1
                print(
                    f"WARN: Download failed for {model} (attempt {attempt}/{attempts}). Retrying in {wait:.1f}s...",
                    file=sys.stderr,
                )
                time.sleep(wait)

    print("All AI models downloaded successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
