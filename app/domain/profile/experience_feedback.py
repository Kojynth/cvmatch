"""Editor-facing feedback helpers for profile experience entries."""

from __future__ import annotations

import re
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


def build_experience_editor_feedback(
    experience_data: Dict[str, Any] | None,
    *,
    language_code: str = "fr",
) -> Dict[str, str]:
    entry = experience_data if isinstance(experience_data, dict) else {}
    return {
        "editorial_feedback": _build_editorial_feedback(
            str(entry.get("description") or ""),
            language_code=language_code,
        ),
        "date_feedback": _build_date_feedback(
            entry.get("start_date"),
            entry.get("end_date"),
        ),
    }
