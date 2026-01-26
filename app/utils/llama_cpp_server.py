"""
llama.cpp Server Client
======================

Minimal helper to run a local `llama-server` process (llama.cpp) and query it.

The implementation tries the OpenAI-compatible endpoint first:
`POST /v1/chat/completions`
and falls back to the legacy llama.cpp endpoint:
`POST /completion`.

This module intentionally avoids logging prompts or generated content.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from loguru import logger


@dataclass(frozen=True)
class LlamaCppServerConfig:
    model_path: Path
    host: str = "127.0.0.1"
    port: int = 8080
    ctx_size: int = 4096
    threads: Optional[int] = None
    binary_path: Optional[Path] = None


class LlamaCppServer:
    def __init__(self, config: LlamaCppServerConfig) -> None:
        self.config = config
        self.process: Optional[subprocess.Popen] = None
        self.base_url = f"http://{config.host}:{config.port}"

    def is_alive(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def is_ready(self) -> bool:
        return self._check_ready()

    def start(self, *, timeout_s: float = 30.0) -> None:
        if self.is_alive():
            return
        # If a server is already running (started externally), just reuse it.
        if self._check_ready():
            logger.info("Using existing llama.cpp server at %s", self.base_url)
            return

        binary = self._resolve_binary()
        model_path = self.config.model_path
        if not model_path.exists():
            raise FileNotFoundError(
                f"Fichier GGUF introuvable: {model_path}. "
                "Téléchargez un modèle GGUF et placez-le à l'emplacement attendu."
            )

        threads = int(self.config.threads or (os.cpu_count() or 4))
        threads = max(1, threads)

        args = [
            str(binary),
            "-m",
            str(model_path),
            "--host",
            str(self.config.host),
            "--port",
            str(int(self.config.port)),
            "-c",
            str(int(self.config.ctx_size)),
            "-t",
            str(threads),
        ]

        creationflags = 0
        if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
            creationflags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]

        logger.info(
            "Starting llama.cpp server (binary=%s, model=%s, port=%s)",
            binary,
            model_path,
            self.config.port,
        )
        self.process = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
        )

        start_time = time.time()
        while time.time() - start_time < timeout_s:
            if self.process.poll() is not None:
                code = self.process.returncode
                self.process = None
                raise RuntimeError(
                    f"llama.cpp server a quitté prématurément (code={code}). "
                    "Vérifiez le chemin du binaire, du modèle GGUF, et relancez."
                )
            if self._check_ready():
                return
            time.sleep(0.5)

        raise TimeoutError(
            "Timeout: llama.cpp server n'est pas devenu prêt. "
            "Essayez de lancer `llama-server` manuellement pour voir les logs."
        )

    def stop(self) -> None:
        proc = self.process
        self.process = None
        if proc is None:
            return
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def chat(
        self,
        *,
        messages: List[Dict[str, str]],
        max_tokens: int,
        temperature: float = 0.7,
        top_p: float = 0.9,
        timeout_s: float = 180.0,
    ) -> str:
        # 1) OpenAI-compatible endpoint (preferred).
        try:
            payload = {
                "messages": messages,
                "temperature": float(temperature),
                "top_p": float(top_p),
                "max_tokens": int(max_tokens),
                "stream": False,
            }
            response = requests.post(
                f"{self.base_url}/v1/chat/completions",
                json=payload,
                timeout=timeout_s,
            )
            if response.status_code != 404:
                response.raise_for_status()
                data = response.json()
                choices = data.get("choices") or []
                message = (choices[0] or {}).get("message") if choices else {}
                content = (message or {}).get("content")
                if isinstance(content, str) and content.strip():
                    return content
        except Exception as exc:
            logger.warning("llama.cpp chat endpoint failed: %s", exc)

        # 2) Fallback to legacy endpoint.
        prompt = "\n\n".join(
            m.get("content", "")
            for m in messages
            if isinstance(m, dict) and isinstance(m.get("content"), str)
        )
        payload = {
            "prompt": prompt,
            "n_predict": int(max_tokens),
            "temperature": float(temperature),
            "top_p": float(top_p),
        }
        response = requests.post(
            f"{self.base_url}/completion",
            json=payload,
            timeout=timeout_s,
        )
        response.raise_for_status()
        data = response.json()
        content = data.get("content") or data.get("completion") or data.get("response")
        if isinstance(content, str):
            return content
        return str(content or "").strip()

    def _check_ready(self) -> bool:
        # Common endpoints depending on llama.cpp version.
        for path in ("/health", "/v1/models", "/"):
            try:
                resp = requests.get(f"{self.base_url}{path}", timeout=1.0)
                if 200 <= resp.status_code < 500:
                    return True
            except Exception:
                continue
        return False

    def _resolve_binary(self) -> Path:
        if self.config.binary_path:
            return Path(self.config.binary_path)

        env = os.getenv("CVMATCH_LLAMA_CPP_BINARY") or os.getenv("CVMATCH_LLAMA_CPP_BIN")
        if env:
            return Path(env).expanduser()

        for candidate in ("llama-server", "llama-server.exe", "server", "server.exe"):
            resolved = shutil.which(candidate)
            if resolved:
                return Path(resolved)

        repo_root = Path(__file__).resolve().parents[2]
        local_candidates = [
            repo_root / "tools" / "llama.cpp" / "llama-server.exe",
            repo_root / "tools" / "llama.cpp" / "llama-server",
            repo_root / "tools" / "llama.cpp" / "server.exe",
            repo_root / "tools" / "llama.cpp" / "server",
        ]
        for path in local_candidates:
            if path.exists():
                return path

        raise FileNotFoundError(
            "Binaire llama.cpp introuvable. "
            "Installez llama.cpp et ajoutez `llama-server` au PATH, "
            "ou définissez CVMATCH_LLAMA_CPP_BINARY."
        )
