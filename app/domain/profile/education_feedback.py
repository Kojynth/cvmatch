"""Editor-facing feedback for profile education entries.

Surfaces grammar warnings for school / degree / field_of_study fields — the
primary S8-class typos (Datas, d'Informations, LaPoste) all live here.
Permissive: warn only, never rewrite.
"""

from __future__ import annotations

from typing import Any, Dict


def _grammar_hint(text: Any, *, language_code: str) -> str:
    try:
        from .content_quality_validators import detect_grammar_issues
    except Exception:
        return ""

    issues = detect_grammar_issues(text, language_code=language_code)
    if not issues:
        return ""
    hints = "; ".join(
        f"« {i['found']} » → {i['suggestion']}" for i in issues[:2]
    )
    return f"⚠️ Orthographe: {hints}."


def build_education_editor_feedback(
    education_data: Dict[str, Any] | None,
    *,
    language_code: str = "fr",
) -> Dict[str, str]:
    entry = education_data if isinstance(education_data, dict) else {}
    return {
        "school_feedback": _grammar_hint(entry.get("school"), language_code=language_code),
        "degree_feedback": _grammar_hint(entry.get("degree"), language_code=language_code),
        "field_feedback": _grammar_hint(entry.get("field_of_study"), language_code=language_code),
    }
