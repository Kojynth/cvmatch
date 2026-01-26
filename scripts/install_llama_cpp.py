#!/usr/bin/env python
"""Install a llama.cpp prebuilt `llama-server` binary.

This script downloads the latest llama.cpp release asset matching the current
platform/architecture, extracts it, and places the `llama-server` binary under
`tools/llama.cpp/`.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple
from urllib.parse import urlparse


GITHUB_RELEASES_LATEST = "https://api.github.com/repos/ggerganov/llama.cpp/releases/latest"
ALLOWED_DOWNLOAD_HOSTS = {
    "github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _default_dest_dir() -> Path:
    return _repo_root() / "tools" / "llama.cpp"


def _platform_key() -> str:
    plat = sys.platform.lower()
    if plat.startswith("win"):
        return "windows"
    if plat.startswith("linux"):
        return "linux"
    if plat.startswith("darwin"):
        return "macos"
    return plat


def _arch_key() -> str:
    machine = platform.machine().lower()
    if machine in {"x86_64", "amd64"}:
        return "x86_64"
    if machine in {"aarch64", "arm64"}:
        return "arm64"
    return machine


def _binary_target_name() -> str:
    return "llama-server.exe" if _platform_key() == "windows" else "llama-server"


def _supports_archive(name: str) -> bool:
    lowered = name.lower()
    return lowered.endswith(".zip") or lowered.endswith(".tar.gz") or lowered.endswith(".tgz")


def _score_asset(name: str, *, platform_key: str, arch_key: str) -> int:
    lowered = name.lower()
    if not _supports_archive(lowered):
        return -10_000

    score = 0
    if platform_key == "windows":
        score += 200 if ("win" in lowered or "windows" in lowered) else -10_000
    elif platform_key == "linux":
        score += 200 if ("linux" in lowered or "ubuntu" in lowered) else -10_000
    elif platform_key == "macos":
        score += 200 if ("mac" in lowered or "darwin" in lowered or "osx" in lowered) else -10_000

    # Architecture hints
    if arch_key == "x86_64":
        if any(token in lowered for token in ("x64", "x86_64", "amd64")):
            score += 100
        else:
            score -= 200
    elif arch_key == "arm64":
        if any(token in lowered for token in ("arm64", "aarch64")):
            score += 100
        else:
            score -= 200

    # Prefer CPU-friendly builds
    if "avx2" in lowered:
        score += 30
    elif "avx" in lowered:
        score += 15

    # Avoid GPU-specific builds unless that's all we have.
    if any(token in lowered for token in ("cuda", "cublas", "rocm", "metal", "vulkan")):
        score -= 10

    # Prefer smaller, easy-to-extract formats
    if lowered.endswith(".zip"):
        score += 5

    return score


def _pick_best_asset(assets: Iterable[Dict[str, Any]], *, platform_key: str, arch_key: str) -> Optional[Dict[str, Any]]:
    best: Optional[Tuple[int, Dict[str, Any]]] = None
    for asset in assets:
        name = str(asset.get("name") or "")
        score = _score_asset(name, platform_key=platform_key, arch_key=arch_key)
        if best is None or score > best[0]:
            best = (score, asset)
    if best and best[0] > 0:
        return best[1]
    return None


def _http_get_json(url: str) -> Dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "cvmatch-installer",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "cvmatch-installer"},
    )
    with urllib.request.urlopen(request, timeout=120) as response, open(dest, "wb") as fout:
        shutil.copyfileobj(response, fout)


def _is_within_directory(base_dir: Path, target: Path) -> bool:
    try:
        base_path = os.path.abspath(str(base_dir))
        target_path = os.path.abspath(str(target))
        return os.path.commonpath([base_path, target_path]) == base_path
    except ValueError:
        return False


def _validate_download_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        return False
    return parsed.netloc.lower() in ALLOWED_DOWNLOAD_HOSTS


def _extract_archive(archive_path: Path, dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    lowered = archive_path.name.lower()
    if lowered.endswith(".zip"):
        with zipfile.ZipFile(archive_path) as zf:
            for member in zf.namelist():
                dest_path = dest_dir / member
                if not _is_within_directory(dest_dir, dest_path):
                    raise ValueError(f"Unsafe path in zip archive: {member}")
            zf.extractall(dest_dir)
        return
    if lowered.endswith(".tar.gz") or lowered.endswith(".tgz"):
        with tarfile.open(archive_path, "r:gz") as tf:
            for member in tf.getmembers():
                dest_path = dest_dir / member.name
                if not _is_within_directory(dest_dir, dest_path):
                    raise ValueError(f"Unsafe path in tar archive: {member.name}")
            tf.extractall(dest_dir)
        return
    raise ValueError(f"Unsupported archive: {archive_path}")


def _find_binary(root: Path) -> Optional[Path]:
    candidates = {"llama-server", "llama-server.exe", "server", "server.exe"}
    for path in root.rglob("*"):
        if path.is_file() and path.name.lower() in candidates:
            return path
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Install llama.cpp (llama-server) for CVMatch.")
    parser.add_argument("--dest-dir", default=str(_default_dest_dir()), help="Destination directory (default: %(default)s)")
    parser.add_argument("--api-url", default=GITHUB_RELEASES_LATEST, help="GitHub releases API URL (default: %(default)s)")
    parser.add_argument("--force", action="store_true", help="Re-download even if already installed")
    args = parser.parse_args()

    dest_dir = Path(args.dest_dir).expanduser()
    dest_dir.mkdir(parents=True, exist_ok=True)

    target = dest_dir / _binary_target_name()
    if target.exists() and not args.force:
        print(f"[OK] llama.cpp already installed: {target}")
        return 0

    platform_key = _platform_key()
    arch_key = _arch_key()

    try:
        release = _http_get_json(str(args.api_url))
    except urllib.error.HTTPError as exc:
        print(f"[WARN] Could not query llama.cpp release metadata ({exc}).")
        return 2
    except Exception as exc:
        print(f"[WARN] Could not query llama.cpp release metadata ({exc}).")
        return 2

    assets = release.get("assets") or []
    asset = _pick_best_asset(assets, platform_key=platform_key, arch_key=arch_key)
    if not asset:
        print("[WARN] No suitable llama.cpp prebuilt binary found for this platform.")
        print("       Install llama.cpp manually and set CVMATCH_LLAMA_CPP_BINARY if needed.")
        return 3

    asset_name = str(asset.get("name") or "llama.cpp-asset")
    asset_name = Path(asset_name).name
    download_url = str(asset.get("browser_download_url") or "")
    if not download_url:
        print("[WARN] Release asset has no download URL.")
        return 3
    if not _validate_download_url(download_url):
        print("[WARN] Release asset download URL is not trusted.")
        return 3

    print(f"Downloading llama.cpp: {asset_name}")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            archive_path = tmp_dir / asset_name
            _download(download_url, archive_path)

            extract_dir = tmp_dir / "extract"
            _extract_archive(archive_path, extract_dir)

            binary = _find_binary(extract_dir)
            if not binary:
                print("[WARN] Could not find llama-server binary in the downloaded archive.")
                return 4

            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(binary, target)
            if platform_key != "windows":
                try:
                    target.chmod(target.stat().st_mode | 0o111)
                except Exception:
                    pass

    except Exception as exc:
        print(f"[WARN] Failed to download/install llama.cpp: {exc}")
        return 5

    print(f"[OK] Installed llama.cpp server binary: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
