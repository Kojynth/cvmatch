"""Editor-facing feedback helpers for profile experience entries."""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Dict, List


_YEAR_ONLY_PATTERN = re.compile(r"^\d{4}$")
_ACTION_VERB_HEADS = {
    "fr": {
        "accompagne",
        "ameliore",
        "analyse",
        "anime",
        "assure",
        "automatise",
        "collabore",
        "concoit",
        "conseille",
        "consolide",
        "contribue",
        "coordonne",
        "cree",
        "definit",
        "deploie",
        "developpe",
        "documente",
        "execute",
        "fiabilise",
        "gere",
        "identifie",
        "implemente",
        "met",
        "mene",
        "optimise",
        "pilote",
        "prepare",
        "qualifie",
        "realise",
        "redige",
        "renforce",
        "revoit",
        "structure",
        "suit",
        "teste",
        "valide",
    },
    "en": {
        "accelerated",
        "analyzed",
        "automated",
        "built",
        "coordinated",
        "created",
        "defined",
        "delivered",
        "designed",
        "developed",
        "documented",
        "drove",
        "executed",
        "implemented",
        "improved",
        "led",
        "managed",
        "optimized",
        "prepared",
        "qualified",
        "reduced",
        "reviewed",
        "streamlined",
        "structured",
        "supported",
        "tested",
        "tracked",
        "validated",
    },
}
_WEAK_LEADIN_PATTERN = re.compile(
    r"^(?:mes missions(?: couvrent| consistent| ont notamment consist[ée]?\s+[àa])?|"
    r"responsabilit[ée]s(?: principales)?|missions principales|"
    r"my responsibilities(?: included)?|responsibilities included|scope)\b",
    re.IGNORECASE,
)
_FIRST_PERSON_PATTERNS = {
    "fr": re.compile(r"\b(?:je|j'|moi|mon|ma|mes|nous|notre|nos)\b", re.IGNORECASE),
    "en": re.compile(r"\b(?:i|my|mine|we|our|ours)\b", re.IGNORECASE),
}
_QUALITATIVE_IMPACT_CUES = {
    "fr": (
        "afin de",
        "pour",
        "permettant",
        "ameliore",
        "améliore",
        "fiabilise",
        "optimise",
        "renforce",
        "facilite",
        "clarifie",
        "fluidifie",
        "reduit",
        "réduit",
    ),
    "en": (
        "to ",
        "improved",
        "improving",
        "reduced",
        "reducing",
        "strengthened",
        "optimized",
        "streamlined",
        "supported",
        "enabled",
        "clarified",
    ),
}


def _normalize_language_code(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return "fr"
    normalized = re.split(r"[-_]", normalized, maxsplit=1)[0]
    return normalized or "fr"


def _word_count(text: Any) -> int:
    return len(re.findall(r"\b\S+\b", str(text or "").strip(), flags=re.UNICODE))


def _split_segments(text: Any) -> List[str]:
    raw = str(text or "").strip()
    if not raw:
        return []
    normalized = (
        raw.replace("•", "\n")
        .replace("▪", "\n")
        .replace("➜", "\n")
        .replace("✓", "\n")
    )
    normalized = re.sub(r"\s*;\s*", "\n", normalized)
    parts = re.split(r"[\r\n]+|(?<=[.!?])\s+", normalized)
    segments: List[str] = []
    for part in parts:
        cleaned = str(part or "").strip(" -*\t\r\n")
        if cleaned:
            segments.append(cleaned)
    return segments


def _starts_with_action_phrase(text: Any, *, language_code: str) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False

    language = _normalize_language_code(language_code)
    first_token_match = re.match(r"[A-Za-zÀ-ÿ]+", raw)
    if not first_token_match:
        return False
    first_token = first_token_match.group(0).lower()
    if first_token in _ACTION_VERB_HEADS.get(language, set()):
        return True
    if language == "fr" and re.fullmatch(r"[a-zà-ÿ]+(?:er|ir|re)", first_token):
        return True
    if language == "en" and (
        first_token.endswith("ed")
        or first_token
        in {"build", "drive", "lead", "manage", "review", "support", "test", "track", "validate"}
    ):
        return True
    return False


def _has_partial_year_only_date(text: Any) -> bool:
    return bool(_YEAR_ONLY_PATTERN.fullmatch(str(text or "").strip()))


def _has_date_order_issue(start_date: Any, end_date: Any) -> bool:
    start = str(start_date or "").strip()
    end = str(end_date or "").strip()
    if not start or not end:
        return False

    try:
        from ...rules.date_normalize import _normalize_single_date, normalize_present_token
    except Exception:
        return False

    if str(normalize_present_token(end) or "").strip().upper() == "PRESENT":
        return False

    start_norm = str(_normalize_single_date(start) or "").strip()
    end_norm = str(_normalize_single_date(end) or "").strip()
    if not start_norm or not end_norm:
        return False
    return start_norm > end_norm


def _build_editorial_feedback(description: str, *, language_code: str = "fr") -> str:
    text = str(description or "").strip()
    if not text:
        return ""

    language = _normalize_language_code(language_code)
    notes: List[str] = []
    first_person_pattern = _FIRST_PERSON_PATTERNS.get(language)
    segments = _split_segments(text)

    if _WEAK_LEADIN_PATTERN.search(text):
        notes.append("Supprimez les amorces du type « Mes missions » et allez directement à l'action.")

    if first_person_pattern and first_person_pattern.search(text):
        notes.append("Préférez une formulation CV sans première personne.")

    if _word_count(text) >= 30 and len(segments) <= 2:
        notes.append("Découpez la description en 2 à 4 actions courtes plutôt qu'un paragraphe narratif.")

    if segments:
        action_led_segments = sum(
            1 for segment in segments[:4] if _starts_with_action_phrase(segment, language_code=language)
        )
        if action_led_segments == 0:
            notes.append("Commencez les actions par un verbe d'action clair.")
        elif action_led_segments < min(len(segments), 2):
            notes.append("Uniformisez les formulations pour que chaque action démarre par un verbe.")

    if _word_count(text) < 8:
        notes.append("Ajoutez 1 ou 2 détails concrets sur le périmètre ou le livrable.")

    lowered = text.lower()
    if _word_count(text) >= 10 and not any(
        cue in lowered for cue in _QUALITATIVE_IMPACT_CUES.get(language, ())
    ):
        notes.append("Si possible, précisez l'effet obtenu: fiabilisation, gain de fluidité, réduction du manuel, meilleure visibilité.")

    return "Conseil CV: " + " ".join(notes[:2]) if notes else ""


def _build_date_feedback(start_date: Any, end_date: Any) -> str:
    start = str(start_date or "").strip()
    end = str(end_date or "").strip()

    notes: List[str] = []
    if start and not end:
        notes.append("Ajoutez une date de fin ou indiquez explicitement Present/En cours pour clarifier la periode.")
    if _has_partial_year_only_date(start) or _has_partial_year_only_date(end):
        notes.append("Format conseillé: MM/YYYY. YYYY reste accepté si le mois est inconnu.")
    if _has_date_order_issue(start, end):
        notes.append("Vérifiez l'ordre des dates: la fin semble antérieure au début.")
    return "Dates: " + " ".join(notes) if notes else ""


_CURRENT_ROLE_END_TOKENS = {
    "present",
    "présent",
    "en cours",
    "aujourd'hui",
    "current",
    "actuel",
    "actuellement",
    "ongoing",
    "now",
    "today",
    "à ce jour",
    "a ce jour",
}


def _is_past_role(end_date: Any) -> bool:
    token = str(end_date or "").strip().lower()
    if not token:
        return False
    if token in _CURRENT_ROLE_END_TOKENS:
        return False
    end_month = _normalize_end_date_month(end_date)
    if end_month:
        return end_month < date.today().strftime("%Y-%m")
    return True


def _is_current_role(end_date: Any) -> bool:
    token = str(end_date or "").strip().lower()
    if not token:
        return False
    if token in _CURRENT_ROLE_END_TOKENS:
        return True
    end_month = _normalize_end_date_month(end_date)
    if end_month:
        return end_month >= date.today().strftime("%Y-%m")
    return False


def _normalize_end_date_month(end_date: Any) -> str:
    raw = str(end_date or "").strip()
    if not raw:
        return ""
    try:
        from ...rules.date_normalize import _normalize_single_date, normalize_present_token
    except Exception:
        return ""

    if str(normalize_present_token(raw) or "").strip().upper() == "PRESENT":
        return date.today().strftime("%Y-%m")
    normalized = str(_normalize_single_date(raw) or "").strip()
    if re.fullmatch(r"\d{4}-\d{2}", normalized):
        return normalized
    return ""


def _has_missing_end_date(end_date: Any) -> bool:
    return not str(end_date or "").strip()


def _build_tense_style_feedback(
    *,
    is_past_role: bool,
    is_current_role: bool,
    has_missing_end_date: bool,
    language_code: str,
) -> str:
    language = _normalize_language_code(language_code)
    if language == "en":
        if has_missing_end_date:
            return (
                "Verb tense: end date missing. If this role is current, use "
                "present-tense action verbs; if it is finished, add an end date "
                "and use past-tense action verbs."
            )
        if is_current_role:
            return (
                "Verb tense: current role, write actions in present tense "
                "(e.g. “Analyzes”, “Structures”, “Automates”)."
            )
        if is_past_role:
            return (
                "Verb tense: past role, write actions in past tense "
                "(e.g. “Analyzed”, “Structured”, “Automated”)."
            )
        return ""

    if language == "ja":
        if has_missing_end_date:
            return (
                "Temps des verbes : date de fin manquante. Pour une sortie "
                "japonaise, utilisez une formulation en cours/non passée si le "
                "poste est actuel ; sinon ajoutez une date de fin et utilisez "
                "une formulation passée/accomplie."
            )
        if is_current_role:
            return (
                "Temps des verbes : poste en cours. Pour une sortie japonaise, "
                "utilisez une formulation en cours/non passée et conservez des "
                "actions courtes."
            )
        if is_past_role:
            return (
                "Temps des verbes : poste terminé. Pour une sortie japonaise, "
                "utilisez une formulation passée/accomplie et conservez des "
                "actions courtes."
            )
        return ""

    if has_missing_end_date:
        return (
            "Temps des verbes : date de fin manquante. Si le poste est en cours, "
            "indiquez Présent/En cours et rédigez au présent ; s'il est terminé, "
            "ajoutez une date de fin et rédigez au passé composé."
        )
    if is_current_role:
        return (
            "Temps des verbes : poste en cours, rédigez les actions au présent "
            "(ex. « Analyse », « Structure », « Suit »). Pour les anciens postes, "
            "utilisez le passé composé."
        )
    if is_past_role:
        return (
            "Temps des verbes : poste terminé, rédigez les actions au passé "
            "composé (ex. « A analysé », « A structuré », « A automatisé »)."
        )
    return ""


def _build_company_feedback(company: Any, *, language_code: str) -> str:
    try:
        from .content_quality_validators import detect_grammar_issues
    except Exception:
        return ""

    issues = detect_grammar_issues(company, language_code=language_code)
    if not issues:
        return ""
    hints = "; ".join(
        f"« {i['found']} » → {i['suggestion']}" for i in issues[:2]
    )
    return f"⚠️ Orthographe: {hints}."


def _build_quality_feedback(description: Any, *, is_past_role: bool, language_code: str) -> str:
    try:
        from .content_quality_validators import build_quality_warnings, format_warnings
    except Exception:
        return ""

    warnings = build_quality_warnings(
        description,
        is_past_role=is_past_role,
        language_code=language_code,
    )
    return format_warnings(warnings)


def build_experience_editor_feedback(
    experience_data: Dict[str, Any] | None,
    *,
    language_code: str = "fr",
) -> Dict[str, str]:
    entry = experience_data if isinstance(experience_data, dict) else {}
    description = str(entry.get("description") or "")
    is_past_role = _is_past_role(entry.get("end_date"))
    is_current_role = _is_current_role(entry.get("end_date"))
    has_missing_end_date = _has_missing_end_date(entry.get("end_date"))

    editorial = _build_editorial_feedback(description, language_code=language_code)
    quality = _build_quality_feedback(
        description,
        is_past_role=is_past_role,
        language_code=language_code,
    )
    merged_editorial = " ".join(part for part in (editorial, quality) if part)

    return {
        "editorial_feedback": merged_editorial,
        "date_feedback": _build_date_feedback(
            entry.get("start_date"),
            entry.get("end_date"),
        ),
        "tense_feedback": _build_tense_style_feedback(
            is_past_role=is_past_role,
            is_current_role=is_current_role,
            has_missing_end_date=has_missing_end_date,
            language_code=language_code,
        ),
        "company_feedback": _build_company_feedback(
            entry.get("company"),
            language_code=language_code,
        ),
    }
