#!/usr/bin/env python
"""Utility to download CVMatch AI models into a local cache."""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
from typing import Dict, List, Tuple

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
    "Qwen/Qwen2.5-7B-Instruct",
]
ALLOWED_LLM_PREFIXES = ("qwen/", "mistralai/")
DEFAULT_GGUF_PROFILES = [
    "qwen3.5-9b-gguf-q4",
    "qwen3-8b-gguf-q5",
]
GGUF_PROFILES: Dict[str, Dict[str, str]] = {
    "mistral-7b-gguf-q4": {
        "repo_id": "second-state/Mistral-7B-Instruct-v0.3-GGUF",
        "filename": "Mistral-7B-Instruct-v0.3-Q4_K_M.gguf",
        "target_filename": "Mistral-7B-Instruct-v0.3.Q4_K_M.gguf",
    },
    "qwen3-14b-gguf-q4": {
        "repo_id": "Qwen/Qwen3-14B-GGUF",
        "filename": "Qwen3-14B-Q4_K_M.gguf",
        "target_filename": "Qwen3-14B-Q4_K_M.gguf",
    },
    "qwen3-14b-gguf-q5": {
        "repo_id": "Qwen/Qwen3-14B-GGUF",
        "filename": "Qwen3-14B-Q5_K_M.gguf",
        "target_filename": "Qwen3-14B-Q5_K_M.gguf",
    },
    "mistral-small-3.2-24b-gguf-q4": {
        "repo_id": "bartowski/mistralai_Mistral-Small-3.2-24B-Instruct-2506-GGUF",
        "filename": "mistralai_Mistral-Small-3.2-24B-Instruct-2506-Q4_K_M.gguf",
        "target_filename": "Mistral-Small-3.2-24B-Instruct-2506.Q4_K_M.gguf",
    },
    "qwen3.5-9b-gguf-q4": {
        "repo_id": "jc-builds/Qwen3.5-9B-Q4_K_M-GGUF",
        "filename": "Qwen3.5-9B-Q4_K_M.gguf",
        "target_filename": "Qwen3.5-9B-Q4_K_M.gguf",
    },
    "qwen3-8b-gguf-q5": {
        "repo_id": "Qwen/Qwen3-8B-GGUF",
        "filename": "Qwen3-8B-Q5_K_M.gguf",
        "target_filename": "Qwen3-8B-Q5_K_M.gguf",
    },
}

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


def _resolve_default_gguf_dir() -> str:
    env_dir = os.environ.get("CVMATCH_GGUF_DIR") or os.environ.get(
        "CVMATCH_LLAMA_CPP_MODEL_DIR"
    )
    if env_dir:
        return os.path.abspath(env_dir)
    return os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "cache", "gguf_models")
    )


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


def _split_profile_tokens(raw_values: List[str]) -> List[str]:
    tokens: List[str] = []
    for raw in raw_values:
        for token in str(raw or "").replace(";", ",").split(","):
            token = token.strip()
            if token:
                tokens.append(token)
    return tokens


def _resolve_gguf_profiles(raw_values: List[str]) -> Tuple[List[str], List[str]]:
    requested = _split_profile_tokens(raw_values)
    if not requested:
        env_profiles = os.environ.get("CVMATCH_GGUF_PROFILE_IDS") or os.environ.get(
            "CVMATCH_GGUF_PROFILE_ID"
        )
        requested = _split_profile_tokens([env_profiles or "recommended"])

    resolved: List[str] = []
    unknown: List[str] = []
    for token in requested:
        lowered = token.lower()
        if lowered in {"recommended", "default", "practical"}:
            resolved.extend(DEFAULT_GGUF_PROFILES)
        elif lowered == "all":
            resolved.extend(GGUF_PROFILES)
        elif token in GGUF_PROFILES:
            resolved.append(token)
        else:
            unknown.append(token)
    return _dedupe_models(resolved), unknown


def _is_allowed_llm_model(model_id: str) -> bool:
    lowered = str(model_id or "").strip().lower()
    return any(lowered.startswith(prefix) for prefix in ALLOWED_LLM_PREFIXES)


def _filter_llm_models(models: List[str]) -> Tuple[List[str], List[str]]:
    allowed: List[str] = []
    blocked: List[str] = []
    for model in _dedupe_models(models):
        if _is_allowed_llm_model(model):
            allowed.append(model)
        else:
            blocked.append(model)
    return allowed, blocked


def _download_gguf_profiles(
    *,
    profile_ids: List[str],
    gguf_dir: str,
    cache_dir: str,
    max_workers: int,
    retries: int,
    retry_wait: float,
) -> int:
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        print(
            "ERROR: huggingface_hub package is not installed. Run `pip install huggingface_hub` and retry.",
            file=sys.stderr,
        )
        return 1

    os.makedirs(gguf_dir, exist_ok=True)
    attempts = max(0, retries) + 1
    for profile_id in profile_ids:
        spec = GGUF_PROFILES[profile_id]
        repo_id = spec["repo_id"]
        filename = spec["filename"]
        target_filename = spec["target_filename"]
        target_path = os.path.abspath(os.path.join(gguf_dir, target_filename))
        if os.path.exists(target_path) and os.path.getsize(target_path) > 0:
            print(f"GGUF already present for {profile_id}: {target_path}")
            continue

        print(f"Downloading GGUF {profile_id}: {repo_id}/{filename} -> {target_path}")
        for attempt in range(1, attempts + 1):
            try:
                kwargs = {
                    "repo_id": repo_id,
                    "filename": filename,
                    "cache_dir": cache_dir,
                    "local_dir": gguf_dir,
                    "local_files_only": False,
                }
                downloaded_path = os.path.abspath(hf_hub_download(**kwargs))
                if downloaded_path != target_path:
                    temp_path = f"{target_path}.part"
                    shutil.copyfile(downloaded_path, temp_path)
                    os.replace(temp_path, target_path)
                break
            except Exception as exc:
                if attempt >= attempts:
                    print(
                        f"ERROR: Could not download GGUF profile {profile_id}. {exc}",
                        file=sys.stderr,
                    )
                    print(
                        "If the error mentions '401', run `huggingface-cli login` and retry.",
                        file=sys.stderr,
                    )
                    return 2
                wait = max(0.0, retry_wait) * attempt
                print(
                    f"WARN: GGUF download failed for {profile_id} (attempt {attempt}/{attempts}). Retrying in {wait:.1f}s...",
                    file=sys.stderr,
                )
                time.sleep(wait)
    return 0


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
        help="Download the default LLM for structured extraction.",
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
        "--include-gguf",
        action="store_true",
        help="Download local GGUF writer files used by llama.cpp profiles.",
    )
    parser.add_argument(
        "--gguf-profile",
        action="append",
        dest="gguf_profiles",
        default=[],
        help=(
            "GGUF profile id to download, comma-separated list, 'recommended', "
            "or 'all' (repeatable)."
        ),
    )
    parser.add_argument(
        "--gguf-dir",
        default=_resolve_default_gguf_dir(),
        help="Destination directory for GGUF files (default: %(default)s)",
    )
    parser.add_argument(
        "--skip-gguf",
        action="store_true",
        help="Skip GGUF downloads even if include-gguf is set.",
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
    include_gguf = bool(args.include_gguf)
    if args.skip_gguf:
        include_gguf = False

    models = list(base_models)
    llm_models: List[str] = []
    if include_llm:
        if args.llm_models:
            llm_models = args.llm_models
        else:
            llm_models = DEFAULT_LLM_MODELS
        llm_models, blocked_llm = _filter_llm_models(llm_models)
        for blocked in blocked_llm:
            print(
                f"WARN: Skipping non-approved LLM model '{blocked}' (allowed: Qwen/*, mistralai/*).",
                file=sys.stderr,
            )
        if not llm_models:
            llm_models = list(DEFAULT_LLM_MODELS)
            print(
                "WARN: No approved LLM model requested, falling back to Qwen/Qwen2.5-7B-Instruct.",
                file=sys.stderr,
            )

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

    if include_gguf:
        gguf_profiles, unknown_profiles = _resolve_gguf_profiles(args.gguf_profiles)
        for profile_id in unknown_profiles:
            print(
                f"WARN: Unknown GGUF profile '{profile_id}' skipped.",
                file=sys.stderr,
            )
        if not gguf_profiles:
            print("WARN: No valid GGUF profiles requested; skipping GGUF downloads.")
        else:
            print("Including GGUF profiles:")
            for profile_id in gguf_profiles:
                print(f"- {profile_id}")
            rc = _download_gguf_profiles(
                profile_ids=gguf_profiles,
                gguf_dir=os.path.abspath(args.gguf_dir),
                cache_dir=cache_dir,
                max_workers=args.max_workers,
                retries=args.retries,
                retry_wait=args.retry_wait,
            )
            if rc:
                return rc

    print("All AI models downloaded successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
