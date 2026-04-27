"""Profile-domain helpers for deterministic date support metadata."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Any, Dict


_YEAR_ONLY_RE = re.compile(r"^\d{4}$")
_MONTH_YEAR_RE = re.compile(r"^(0?[1-9]|1[0-2])/\d{4}$")
_DAY_MONTH_YEAR_RE = re.compile(r"^(0?[1-9]|[12]\d|3[01])/(0?[1-9]|1[0-2])/\d{4}$")


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


_PRESENT_TOKEN_FALLBACKS = {
    "a ce jour",
    "actuel",
    "actuellement",
    "current",
    "currently",
    "en cours",
    "maintenant",
    "now",
    "ongoing",
    "present",
    "to date",
    "to present",
    "toujours",
}


def _normalize_present_probe(value: Any) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).replace("\u00A0", " ")
    normalized = normalized.strip().lower()
    decomposed = unicodedata.normalize("NFD", normalized)
    without_accents = "".join(
        char for char in decomposed if unicodedata.category(char) != "Mn"
    )
    return re.sub(r"\s+", " ", without_accents).strip()


def _is_present_token_fallback(value: Any) -> bool:
    return _normalize_present_probe(value) in _PRESENT_TOKEN_FALLBACKS


def infer_date_precision(raw_value: Any) -> str:
    text = _clean_text(raw_value)
    if not text:
        return ""
    if _YEAR_ONLY_RE.fullmatch(text):
        return "year"
    if _MONTH_YEAR_RE.fullmatch(text):
        return "month"
    if _DAY_MONTH_YEAR_RE.fullmatch(text):
        return "day"
    return "unknown"


def derive_date_support_fields(start_date: Any, end_date: Any) -> Dict[str, Any]:
    """Build deterministic date metadata from raw profile date fields."""
    start_raw = _clean_text(start_date)
    end_raw = _clean_text(end_date)
    metadata: Dict[str, Any] = {
        "start_date_raw": start_raw,
        "end_date_raw": end_raw,
        "start_date_norm": "",
        "end_date_norm": "",
        "is_current": False,
        "start_date_precision": infer_date_precision(start_raw),
        "end_date_precision": infer_date_precision(end_raw),
        "date_precision": "",
        "duration_months": None,
    }

    try:
        from ...rules.date_normalize import _normalize_single_date, normalize_present_token
    except Exception:
        _normalize_single_date = None
        normalize_present_token = None

    start_norm = ""
    end_norm = ""
    is_current = False

    if start_raw and _normalize_single_date:
        start_norm = _normalize_single_date(start_raw) or ""

    if end_raw:
        normalized_present = (
            normalize_present_token(end_raw) if normalize_present_token else end_raw
        )
        is_current = (
            str(normalized_present or "").strip().upper() == "PRESENT"
            or _is_present_token_fallback(end_raw)
        )
        if is_current:
            end_norm = datetime.now().strftime("%Y-%m")
            metadata["end_date_precision"] = "present"
        elif _normalize_single_date:
            end_norm = _normalize_single_date(end_raw) or ""

    metadata["start_date_norm"] = start_norm
    metadata["end_date_norm"] = end_norm
    metadata["is_current"] = is_current

    start_precision = metadata["start_date_precision"]
    end_precision = metadata["end_date_precision"]
    if start_precision and end_precision and start_precision != end_precision:
        metadata["date_precision"] = f"{start_precision}/{end_precision}"
    else:
        metadata["date_precision"] = start_precision or end_precision or ""

    if start_norm and end_norm:
        try:
            start_year = int(start_norm[:4])
            start_month = int(start_norm[5:7])
            end_year = int(end_norm[:4])
            end_month = int(end_norm[5:7])
            months = (end_year - start_year) * 12 + (end_month - start_month)
            if months >= 1:
                metadata["duration_months"] = months
        except (TypeError, ValueError, IndexError):
            metadata["duration_months"] = None

    return metadata
