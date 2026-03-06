"""Utilities for stage subprocess orchestration and diagnostics."""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List


def is_stage_subprocess_noise_line(line: str) -> bool:
    lower = str(line or "").lower()
    if not lower:
        return True
    if "futurewarning" in lower:
        return True
    if "transformers_cache" in lower:
        return True
    if "warnings.warn" in lower:
        return True
    # Keep explicit failures even when log-formatted.
    if "error" in lower or "exception" in lower or "traceback" in lower:
        return False
    if re.search(r"\binfo\b", lower) or re.search(r"\bdebug\b", lower):
        return True
    return False


def extract_stage_subprocess_error(
    stdout: str,
    stderr: str,
    *,
    noise_filter: Callable[[str], bool] = is_stage_subprocess_noise_line,
) -> str:
    joined = "\n".join(part for part in [stderr, stdout] if part)
    if not joined.strip():
        return "unknown error"

    raw_lines = [line.strip() for line in joined.splitlines() if line.strip()]
    if not raw_lines:
        return "unknown error"

    # First preference: traceback terminal exception line.
    traceback_start = -1
    for idx, line in enumerate(raw_lines):
        if line.startswith("Traceback (most recent call last):"):
            traceback_start = idx

    error_pattern = re.compile(r"(?:^|\b)[A-Za-z_][\w.]*?(?:Error|Exception)\s*:")
    if traceback_start >= 0:
        traceback_lines: List[str] = []
        timestamp_line = re.compile(r"^\d{4}-\d{2}-\d{2}[ ,]")
        for line in raw_lines[traceback_start:]:
            if timestamp_line.match(line) and traceback_lines:
                break
            traceback_lines.append(line)
        for line in reversed(traceback_lines):
            lower = line.lower()
            if "futurewarning" in lower:
                continue
            if error_pattern.search(line):
                return line[:1200]
        if traceback_lines:
            return " | ".join(traceback_lines[-8:])[:1200]

    lines = [line for line in raw_lines if not noise_filter(line)] or raw_lines

    priority_markers = [
        "memoryerror:",
        "runtimeerror:",
        "torch.acceleratorerror:",
        "cuda error:",
        "cuda out of memory",
        "out of memory",
        "not enough free disk space",
        "no space left on device",
        "disk quota exceeded",
        "file reconstruction error",
        "internal writer error",
        "failed to send data",
        "receiver dropped",
        "cublas_status_execution_failed",
        "cublasgemmex",
        "cudnn",
        "device-side assert",
        "illegal memory access",
        "erreur chargement modèle:",
        "mémoire système insuffisante",
        "commit windows insuffisant",
    ]
    for line in reversed(lines):
        lower = line.lower()
        if any(marker in lower for marker in priority_markers):
            return line[:1200]
        if error_pattern.search(line) and "warning" not in lower:
            return line[:1200]

    tail_candidates = [line for line in lines if not noise_filter(line)] or lines
    tail = tail_candidates[-8:]
    return " | ".join(tail)[:1200]


def is_transient_stage_memory_error(details: str) -> bool:
    lowered = str(details or "").lower()
    if not lowered:
        return False
    markers = (
        "cuda error: out of memory",
        "cuda out of memory",
        "out of memory",
        "cublas_status_execution_failed",
        "cublasgemmex",
        "cannot copy out of meta tensor",
        "torch.acceleratorerror",
        "memoryerror",
    )
    return any(marker in lowered for marker in markers)


def build_stage_subprocess_env(
    *,
    base_env: Dict[str, str],
    stage: str,
    attempt: int,
    attempts: int,
    force_survival_retry: bool = False,
) -> Dict[str, str]:
    run_env = dict(base_env or {})
    run_env.setdefault("PYTHONUTF8", "1")
    run_env.setdefault("PYTHONIOENCODING", "utf-8")
    transformers_cache = run_env.get("TRANSFORMERS_CACHE")
    if transformers_cache:
        run_env.setdefault("HF_HOME", transformers_cache)
        run_env.pop("TRANSFORMERS_CACHE", None)

    run_env["CVMATCH_STAGE_NAME"] = str(stage)
    run_env["CVMATCH_STAGE_ATTEMPT"] = str(attempt)
    run_env["CVMATCH_STAGE_ATTEMPTS"] = str(attempts)

    # Retry policy in quality-first mode: keep model selection stable.
    if attempt > 1 and force_survival_retry:
        run_env.setdefault("CVMATCH_DISABLE_TORCH_COMPILE", "1")
    if attempt >= 3:
        run_env.setdefault("CVMATCH_VRAM_HEADROOM_GB", "2.5")
    return run_env


def persist_stage_subprocess_diagnostics(
    *,
    repo_root: Path,
    stage: str,
    attempt: int,
    attempts: int,
    return_code: int,
    stdout: str,
    stderr: str,
    details: str,
    max_chars: int = 120_000,
    logger_debug: Callable[[str, object], None] | None = None,
) -> str:
    try:
        diag_dir = Path(repo_root) / "logs" / "stage_subprocess_failures"
        diag_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{stamp}_{stage}_attempt{attempt}-of-{attempts}_rc{return_code}.log"
        output_path = diag_dir / filename

        stdout_text = str(stdout or "").strip()
        stderr_text = str(stderr or "").strip()
        stdout_lines = len([line for line in stdout_text.splitlines() if line.strip()])
        stderr_lines = len([line for line in stderr_text.splitlines() if line.strip()])

        if len(stdout_text) > max_chars:
            stdout_text = stdout_text[:max_chars] + "\n[...stdout truncated...]"
        if len(stderr_text) > max_chars:
            stderr_text = stderr_text[:max_chars] + "\n[...stderr truncated...]"

        with open(output_path, "w", encoding="utf-8") as handle:
            handle.write(f"stage={stage}\n")
            handle.write(f"attempt={attempt}/{attempts}\n")
            handle.write(f"return_code={return_code}\n")
            handle.write(f"stdout_lines={stdout_lines}\n")
            handle.write(f"stderr_lines={stderr_lines}\n")
            handle.write(f"details={details}\n")
            handle.write("\n[STDERR]\n")
            handle.write(stderr_text or "<empty>")
            handle.write("\n\n[STDOUT]\n")
            handle.write(stdout_text or "<empty>")

        return str(output_path)
    except Exception as exc:
        if callable(logger_debug):
            logger_debug("Unable to persist stage subprocess diagnostics: %s", exc)
        return ""
