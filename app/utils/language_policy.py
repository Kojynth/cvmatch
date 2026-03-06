"""Language resolution policy helpers for offer-driven generation."""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, Optional, Tuple


def normalize_language_code(language: Optional[str]) -> str:
    normalized = str(language or "").strip().lower()
    if normalized.startswith("en"):
        return "en"
    return "fr"


def detect_language_from_text_default(text: Optional[str]) -> str:
    if not text or not str(text).strip():
        return "fr"
    raw = str(text)
    lowered = raw.lower()
    tokens = re.findall(r"[a-zA-Z]+", lowered)
    if not tokens:
        return "fr"

    fr_tokens = {
        "le",
        "la",
        "les",
        "des",
        "une",
        "un",
        "pour",
        "avec",
        "dans",
        "sur",
        "poste",
        "profil",
        "mission",
        "competences",
        "candidature",
        "nous",
        "vous",
        "entreprise",
        "equipe",
        "formation",
        "diplome",
        "alternance",
        "stage",
        "ingenieur",
        "responsabilites",
        "developpement",
        "qualite",
    }
    en_tokens = {
        "the",
        "and",
        "with",
        "role",
        "position",
        "responsibilities",
        "requirements",
        "skills",
        "experience",
        "company",
        "team",
        "apply",
        "candidate",
        "development",
        "engineering",
        "job",
        "we",
        "you",
    }

    fr_score = sum(1 for token in tokens if token in fr_tokens)
    en_score = sum(1 for token in tokens if token in en_tokens)
    if any(ord(ch) > 127 for ch in raw):
        fr_score += 2
    if en_score > fr_score + 1:
        return "en"
    return "fr"


def language_token_scores(text: Optional[str]) -> Tuple[int, int, int]:
    if not text or not str(text).strip():
        return 0, 0, 0
    lowered = str(text).lower()
    tokens = re.findall(r"[a-zA-Z]+", lowered)
    if not tokens:
        return 0, 0, 0

    fr_tokens = {
        "le",
        "la",
        "les",
        "des",
        "une",
        "un",
        "pour",
        "avec",
        "dans",
        "sur",
        "poste",
        "profil",
        "mission",
        "competences",
        "candidature",
        "nous",
        "vous",
        "entreprise",
        "equipe",
        "formation",
        "diplome",
        "alternance",
        "stage",
        "ingenieur",
        "responsabilites",
        "developpement",
        "qualite",
        "objet",
        "madame",
        "monsieur",
    }
    en_tokens = {
        "the",
        "and",
        "with",
        "role",
        "position",
        "responsibilities",
        "requirements",
        "skills",
        "experience",
        "company",
        "team",
        "apply",
        "candidate",
        "development",
        "engineering",
        "job",
        "we",
        "you",
        "subject",
        "dear",
        "sincerely",
    }
    fr_score = sum(1 for token in tokens if token in fr_tokens)
    en_score = sum(1 for token in tokens if token in en_tokens)
    return fr_score, en_score, len(tokens)


def is_mixed_or_mismatched_language(
    text: Optional[str],
    target_language: str,
    *,
    normalize_language: Optional[Callable[[Optional[str]], str]] = None,
    detect_language_from_text: Optional[Callable[[Optional[str]], str]] = None,
) -> bool:
    normalize_fn = normalize_language or normalize_language_code
    detect_fn = detect_language_from_text or detect_language_from_text_default
    target = normalize_fn(target_language)

    fr_score, en_score, token_count = language_token_scores(text)
    if token_count <= 0:
        return False

    dominant = "en" if en_score > fr_score else "fr"
    if dominant != target and abs(en_score - fr_score) >= 2:
        return True

    mixed_ratio = min(fr_score, en_score) / max(1, (fr_score + en_score))
    if min(fr_score, en_score) >= 4 and mixed_ratio >= 0.28:
        return True

    if token_count < 80 and (fr_score + en_score) <= 3:
        detected = detect_fn(text)
        if detected != target:
            return True
    return False


def resolve_offer_language(
    offer_data: Optional[Dict[str, Any]],
    *,
    normalize_language: Optional[Callable[[Optional[str]], str]] = None,
    detect_language_from_text: Optional[Callable[[Optional[str]], str]] = None,
    default_language: str = "fr",
) -> str:
    normalize_fn = normalize_language or normalize_language_code
    detect_fn = detect_language_from_text or detect_language_from_text_default
    data = offer_data if isinstance(offer_data, dict) else {}
    analysis = data.get("analysis") if isinstance(data.get("analysis"), dict) else None
    analysis_language = analysis.get("language") if isinstance(analysis, dict) else None
    offer_text = data.get("text")
    detected = detect_fn(offer_text)

    if analysis_language and normalize_fn(analysis_language):
        analysis_norm = normalize_fn(analysis_language)
        if detected and detected != analysis_norm:
            return normalize_fn(detected)
        return analysis_norm

    if detected:
        return normalize_fn(detected)
    return normalize_fn(default_language)


def sync_offer_analysis_language(
    offer_data: Optional[Dict[str, Any]],
    language_code: str,
) -> Dict[str, Any]:
    data = dict(offer_data or {})
    analysis = data.get("analysis")
    if not isinstance(analysis, dict):
        analysis = {}
    else:
        analysis = dict(analysis)
    analysis["language"] = str(language_code or "").strip() or "fr"
    data["analysis"] = analysis
    return data


class OfferLanguageResolver:
    """Stateful language resolver for offer-driven generation.

    This class encapsulates the language resolution logic that was
    duplicated in CVGenerationWorker and CoverLetterGenerationWorker.

    Usage:
        resolver = OfferLanguageResolver(offer_data)
        language_code = resolver.resolve()
        # offer_data is now updated with synchronized language
        updated_offer_data = resolver.offer_data
    """

    def __init__(
        self,
        offer_data: Optional[Dict[str, Any]],
        *,
        default_language: str = "fr",
    ):
        """Initialize resolver with offer data.

        Args:
            offer_data: Offer data dict (will be modified in place)
            default_language: Default language if detection fails
        """
        self._offer_data = dict(offer_data) if isinstance(offer_data, dict) else {}
        self._default_language = default_language
        self._resolved_language: Optional[str] = None

    @property
    def offer_data(self) -> Dict[str, Any]:
        """Get the offer data (possibly updated with language sync)."""
        return self._offer_data

    def resolve(self) -> str:
        """Resolve and synchronize language code.

        Determines the language from offer data, syncs it back to the
        analysis section, and returns the resolved language code.

        Returns:
            Resolved language code ("fr" or "en")
        """
        if self._resolved_language is not None:
            return self._resolved_language

        language_code = resolve_offer_language(
            self._offer_data,
            normalize_language=normalize_language_code,
            detect_language_from_text=detect_language_from_text_default,
            default_language=self._default_language,
        )

        # Sync back to offer data
        self._offer_data = sync_offer_analysis_language(
            self._offer_data,
            language_code,
        )

        self._resolved_language = language_code
        return language_code

    def reset(self) -> None:
        """Reset resolved language to force re-resolution."""
        self._resolved_language = None


def resolve_and_sync_offer_language(
    offer_data: Optional[Dict[str, Any]],
    *,
    default_language: str = "fr",
) -> Tuple[str, Dict[str, Any]]:
    """Resolve language and sync to offer data in one call.

    This is the preferred functional interface for workers that need
    to both determine the language and update offer_data.

    Args:
        offer_data: Offer data dict
        default_language: Default language if detection fails

    Returns:
        Tuple of (language_code, updated_offer_data)

    Example:
        language_code, self.offer_data = resolve_and_sync_offer_language(
            self.offer_data, default_language="fr"
        )
    """
    resolver = OfferLanguageResolver(offer_data, default_language=default_language)
    language_code = resolver.resolve()
    return language_code, resolver.offer_data
