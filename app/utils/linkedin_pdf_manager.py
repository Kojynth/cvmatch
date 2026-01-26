"""Utilities for handling LinkedIn PDF uploads."""

from __future__ import annotations

from datetime import datetime
import hashlib
import shutil
from pathlib import Path
from typing import Optional, Tuple

from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG

LOGGER = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)

_STORAGE_DIR = Path.cwd() / "reports" / "linkedin"
_STORAGE_DIR.mkdir(parents=True, exist_ok=True)


def compute_checksum(file_path: Path) -> str:
    """Return SHA256 checksum for the provided file."""
    hash_obj = hashlib.sha256()
    with file_path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hash_obj.update(chunk)
    return hash_obj.hexdigest()


def _build_target_filename(checksum: str, profile_id: Optional[int]) -> str:
    prefix = f"p{profile_id}" if profile_id else "anon"
    return f"{prefix}_{checksum[:16]}.pdf"


def store_linkedin_pdf(source_path: str, profile_id: Optional[int] = None) -> Tuple[str, str, datetime]:
    """
    Copy the LinkedIn export PDF into the managed storage directory.

    Returns a tuple (absolute_path, checksum, uploaded_at).
    """
    src = Path(source_path)
    if not src.exists():
        raise FileNotFoundError(f"LinkedIn PDF introuvable: {source_path}")
    checksum = compute_checksum(src)
    target_name = _build_target_filename(checksum, profile_id)
    dest = _STORAGE_DIR / target_name
    if not dest.exists():
        shutil.copy2(src, dest)
        LOGGER.info("LinkedIn PDF stocké | dest=%s checksum=%s", dest, checksum[:12])
    else:
        LOGGER.info("LinkedIn PDF déjà présent, réutilisation | dest=%s", dest)
    uploaded_at = datetime.now()
    return str(dest), checksum, uploaded_at


def copy_for_download(stored_path: str, destination_path: str) -> None:
    """Copy the stored PDF to a destination chosen by the user."""
    src = Path(stored_path)
    dest = Path(destination_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    LOGGER.info("LinkedIn PDF téléchargé | dest=%s", dest)


def remove_stored_pdf(stored_path: Optional[str]) -> None:
    """Delete a stored LinkedIn PDF if it exists."""
    if not stored_path:
        return
    path = Path(stored_path)
    if path.exists():
        try:
            path.unlink()
            LOGGER.info("LinkedIn PDF supprimé | path=%s", path)
        except Exception as exc:
            LOGGER.warning("Impossible de supprimer le PDF LinkedIn | path=%s err=%s", path, exc)
