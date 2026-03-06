"""Utility helpers for offer-alignment scoring."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Sequence, Tuple


def _dedup_preserve(items: Sequence[str]) -> List[str]:
    seen = set()
    output: List[str] = []
    for raw in items or []:
        text = str(raw or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(text)
    return output


def compute_exact_keyword_coverage(
    normalized_probe: str,
    required_terms: Sequence[str],
    *,
    term_present_fn: Callable[[str, str], bool],
) -> Tuple[List[str], List[str]]:
    present: List[str] = []
    missing: List[str] = []
    for term in required_terms or []:
        text = str(term or "").strip()
        if not text:
            continue
        if term_present_fn(normalized_probe, text):
            present.append(text)
        else:
            missing.append(text)
    return _dedup_preserve(present), _dedup_preserve(missing)


def compute_keyword_family_coverage(
    normalized_probe: str,
    keyword_families: Dict[str, Sequence[str]],
    *,
    term_present_fn: Callable[[str, str], bool],
) -> Tuple[List[str], List[str]]:
    present: List[str] = []
    missing: List[str] = []

    for family, terms in (keyword_families or {}).items():
        family_key = str(family or "").strip()
        if not family_key:
            continue
        candidates: List[str] = [family_key]
        if isinstance(terms, list):
            candidates.extend(
                str(item).strip() for item in terms if str(item).strip()
            )
        covered = any(
            term_present_fn(normalized_probe, candidate)
            for candidate in _dedup_preserve(candidates)
        )
        if covered:
            present.append(family_key)
        else:
            missing.append(family_key)
    return _dedup_preserve(present), _dedup_preserve(missing)


def build_alignment_audit(
    *,
    normalized_probe: str,
    required_exact_terms: Sequence[str],
    keyword_families: Dict[str, Sequence[str]],
    thresholds: Dict[str, float],
    term_present_fn: Callable[[str, str], bool],
    exact_weight: float = 0.55,
    family_weight: float = 0.45,
) -> Dict[str, Any]:
    exact_terms = _dedup_preserve([str(item).strip() for item in required_exact_terms or [] if str(item).strip()])
    exact_present, exact_missing = compute_exact_keyword_coverage(
        normalized_probe,
        exact_terms,
        term_present_fn=term_present_fn,
    )
    family_present, family_missing = compute_keyword_family_coverage(
        normalized_probe,
        keyword_families,
        term_present_fn=term_present_fn,
    )

    exact_score = (
        (len(exact_present) / float(max(1, len(exact_terms)))) * 100.0
        if exact_terms
        else 100.0
    )
    family_score = (
        (len(family_present) / float(max(1, len(keyword_families or {})))) * 100.0
        if keyword_families
        else 100.0
    )
    overall = (exact_score * float(exact_weight)) + (family_score * float(family_weight))

    exact_min = float(thresholds.get("exact_min", 55.0))
    family_min = float(thresholds.get("family_min", 45.0))
    overall_min = float(thresholds.get("overall_min", 52.0))

    sufficient = (
        exact_score >= exact_min
        and family_score >= family_min
        and overall >= overall_min
    )

    return {
        "exact_keyword_score": round(exact_score, 2),
        "lexical_family_score": round(family_score, 2),
        "overall_score": round(overall, 2),
        "exact_required_terms": exact_terms,
        "exact_present_terms": exact_present,
        "exact_missing_terms": exact_missing,
        "keyword_families": keyword_families or {},
        "present_keyword_families": family_present,
        "missing_keyword_families": family_missing,
        "thresholds": {
            "exact_min": max(0.0, min(100.0, exact_min)),
            "family_min": max(0.0, min(100.0, family_min)),
            "overall_min": max(0.0, min(100.0, overall_min)),
        },
        "sufficient": bool(sufficient),
    }

