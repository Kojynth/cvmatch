"""Post-processing helpers for the modular CV extraction pipeline."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from cvextractor.pipeline.context import ExtractionContext

SectionReport = Dict[str, Any]
PostProcessorResult = Tuple[Dict[str, Any], List[SectionReport]]


def apply_post_processors(
    payload: Dict[str, Any],
    context: "ExtractionContext",
) -> PostProcessorResult:
    """Clean and deduplicate list-based sections produced by the pipeline."""
    processed = dict(payload or {})
    reports: List[SectionReport] = []

    for section, rules in _SECTION_RULES.items():
        if section not in processed:
            continue
        cleaned, summary = _process_sequence(
            processed[section],
            keys=rules["keys"],
            required=rules.get("required"),
            max_items=rules.get("max_items"),
        )
        processed[section] = cleaned
        if summary["dropped"] or summary.get("trimmed", 0):
            summary["section"] = section
            reports.append(summary)

    return processed, reports


def _process_sequence(
    value: Any,
    *,
    keys: Sequence[str],
    required: Sequence[str] | None = None,
    max_items: int | None = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    items = _ensure_mapping_sequence(value)
    cleaned: List[Dict[str, Any]] = []
    seen: set[Tuple[str, ...]] = set()
    dropped = 0

    for item in items:
        if required and not _has_required(item, required):
            dropped += 1
            continue

        key = tuple(_normalize(item.get(field)) for field in keys)
        if not any(key):
            dropped += 1
            continue

        if key in seen:
            dropped += 1
            continue

        seen.add(key)
        cleaned.append(dict(item))

    trimmed = 0
    if max_items is not None and max_items >= 0 and len(cleaned) > max_items:
        trimmed = len(cleaned) - max_items
        cleaned = cleaned[:max_items]

    summary = {
        "dropped": dropped,
        "retained": len(cleaned),
        "trimmed": trimmed,
    }
    return cleaned, summary


def _ensure_mapping_sequence(value: Any) -> List[Mapping[str, Any]]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [item for item in value if isinstance(item, Mapping)]
    return []


def _has_required(item: Mapping[str, Any], required: Sequence[str]) -> bool:
    for field in required:
        if not _normalize(item.get(field)):
            return False
    return True


def _normalize(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


_SECTION_RULES: Dict[str, Dict[str, Any]] = {
    "languages": {"keys": ("name", "level"), "required": ("name",)},
    "skills": {"keys": ("name",), "required": ("name",)},
    "certifications": {"keys": ("name",), "required": ("name",)},
    "interests": {"keys": ("label",), "required": ("label",)},
    "projects": {"keys": ("title",), "required": ("title",)},
}
