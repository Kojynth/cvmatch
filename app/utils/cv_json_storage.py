"""Helpers to store CV JSON snapshots on disk."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


def _slugify(value: str, fallback: str = "unknown") -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", (value or "").strip().lower())
    cleaned = cleaned.strip("_")
    return (cleaned or fallback)[:40]


def save_cv_json_draft(
    cv_json: Dict[str, Any],
    *,
    profile_id: Optional[int] = None,
    job_title: Optional[str] = None,
    company: Optional[str] = None,
) -> str:
    folder = Path.cwd() / "logs" / "cv_json_drafts"
    folder.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    safe_job = _slugify(job_title or "job")
    safe_company = _slugify(company or "company")
    safe_profile = _slugify(str(profile_id) if profile_id is not None else "na")
    filename = f"cv_json_draft_{safe_profile}_{safe_job}_{safe_company}_{timestamp}.json"
    path = folder / filename
    with path.open("w", encoding="utf-8") as handle:
        json.dump(cv_json, handle, indent=2, ensure_ascii=True)
    return str(path)
