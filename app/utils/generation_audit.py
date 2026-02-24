"""Utilities to build and compare generation audit scores."""

from __future__ import annotations

from typing import Any, Dict


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _clamp_0_100(value: Any, default: float = 0.0) -> float:
    numeric = _as_float(value, default=default)
    if numeric < 0.0:
        return 0.0
    if numeric > 100.0:
        return 100.0
    return numeric


def build_generation_audit(
    *,
    alignment_audit: Dict[str, Any] | None,
    cover_letter_review: Dict[str, Any] | None,
    cv_weight: float = 0.60,
    letter_weight: float = 0.40,
    letter_min_score: float = 78.0,
) -> Dict[str, Any]:
    alignment = alignment_audit if isinstance(alignment_audit, dict) else {}
    review = cover_letter_review if isinstance(cover_letter_review, dict) else {}

    cv_score = _clamp_0_100(alignment.get("overall_score"), default=0.0)
    letter_score = _clamp_0_100(review.get("relevance_score"), default=60.0)

    structure_ok = bool(review.get("structure_ok", True))
    if not structure_ok:
        letter_score = min(letter_score, 69.0)

    cv_ok = bool(alignment.get("sufficient", False))
    letter_ok = structure_ok and (letter_score >= float(letter_min_score))

    total_weight = max(0.001, float(cv_weight) + float(letter_weight))
    norm_cv_weight = float(cv_weight) / total_weight
    norm_letter_weight = float(letter_weight) / total_weight

    global_score = (cv_score * norm_cv_weight) + (letter_score * norm_letter_weight)

    return {
        "cv_score": round(cv_score, 2),
        "letter_score": round(letter_score, 2),
        "global_score": round(global_score, 2),
        "sufficient": bool(cv_ok and letter_ok),
        "weights": {
            "cv": round(norm_cv_weight, 4),
            "letter": round(norm_letter_weight, 4),
        },
        "breakdown": {
            "cv": {
                "sufficient": bool(cv_ok),
                "exact_keyword_score": _clamp_0_100(
                    alignment.get("exact_keyword_score"), default=0.0
                ),
                "lexical_family_score": _clamp_0_100(
                    alignment.get("lexical_family_score"), default=0.0
                ),
                "overall_score": cv_score,
            },
            "letter": {
                "sufficient": bool(letter_ok),
                "relevance_score": letter_score,
                "structure_ok": bool(structure_ok),
                "language": str(review.get("language") or ""),
            },
        },
    }


def is_generation_audit_better(
    *,
    candidate: Dict[str, Any] | None,
    baseline: Dict[str, Any] | None,
    epsilon: float = 0.01,
) -> bool:
    """Return True if candidate should replace baseline."""
    cand = candidate if isinstance(candidate, dict) else {}
    base = baseline if isinstance(baseline, dict) else {}

    cand_global = _clamp_0_100(cand.get("global_score"), default=0.0)
    base_global = _clamp_0_100(base.get("global_score"), default=0.0)
    if cand_global > (base_global + float(epsilon)):
        return True
    if base_global > (cand_global + float(epsilon)):
        return False

    cand_cv = _clamp_0_100(cand.get("cv_score"), default=0.0)
    base_cv = _clamp_0_100(base.get("cv_score"), default=0.0)
    if cand_cv > (base_cv + float(epsilon)):
        return True
    if base_cv > (cand_cv + float(epsilon)):
        return False

    cand_letter = _clamp_0_100(cand.get("letter_score"), default=0.0)
    base_letter = _clamp_0_100(base.get("letter_score"), default=0.0)
    return cand_letter >= (base_letter - float(epsilon))

