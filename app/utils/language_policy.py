"""Language resolution policy helpers for offer-driven generation."""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Callable, Dict, Optional, Set, Tuple


_LANGUAGE_ALIASES: Dict[str, str] = {
    "en": "en",
    "eng": "en",
    "english": "en",
    "anglais": "en",
    "fr": "fr",
    "fra": "fr",
    "french": "fr",
    "francais": "fr",
    "français": "fr",
    "de": "de",
    "ger": "de",
    "deu": "de",
    "german": "de",
    "deutsch": "de",
    "allemand": "de",
    "es": "es",
    "spa": "es",
    "spanish": "es",
    "espanol": "es",
    "español": "es",
    "espagnol": "es",
    "it": "it",
    "ita": "it",
    "italian": "it",
    "italiano": "it",
    "italien": "it",
    "pt": "pt",
    "por": "pt",
    "portuguese": "pt",
    "portugues": "pt",
    "português": "pt",
    "portugais": "pt",
    "nl": "nl",
    "dut": "nl",
    "nld": "nl",
    "dutch": "nl",
    "nederlands": "nl",
    "neerlandais": "nl",
    "ja": "ja",
    "jpn": "ja",
    "japanese": "ja",
    "japonais": "ja",
    "日本語": "ja",
    "zh": "zh",
    "zho": "zh",
    "chi": "zh",
    "chinese": "zh",
    "chinois": "zh",
    "中文": "zh",
    "mandarin": "zh",
    "ko": "ko",
    "kor": "ko",
    "korean": "ko",
    "coréen": "ko",
    "coreen": "ko",
    "한국어": "ko",
    "ar": "ar",
    "ara": "ar",
    "arabic": "ar",
    "arabe": "ar",
    "ru": "ru",
    "rus": "ru",
    "russian": "ru",
    "russe": "ru",
    "el": "el",
    "ell": "el",
    "greek": "el",
    "grec": "el",
}

_LATIN_LANGUAGE_MARKERS: Dict[str, Set[str]] = {
    "en": {
        "with", "role", "position", "skills", "experience", "company", "team",
        "candidate", "development", "engineering", "quality", "testing",
        "delivered", "supported", "built", "led", "managed", "designed",
        "implemented", "executed", "tracked", "unit", "defect", "defects",
        "tracking", "exploratory", "business", "developer", "manager",
        "engineer", "responsibilities", "requirements",
    },
    "fr": {
        "avec", "pour", "dans", "sur", "profil", "mission", "missions",
        "competences", "entreprise", "equipe", "formation", "diplome",
        "alternance", "ingenieur", "qualite", "suivre", "rediger",
        "anomalies", "notamment", "consiste", "consistaient", "couvrent",
        "plusieurs", "fichiers", "outils", "bilans", "recettes", "poste",
    },
    "de": {
        "mit", "fur", "fuer", "erfahrung", "kenntnisse", "aufgaben",
        "verantwortlich", "entwicklung", "qualitat", "qualitaet", "ingenieur",
        "team", "unternehmen", "profil", "fertigkeiten", "testen", "fehler",
        "anforderungen", "zusammenarbeit",
    },
    "es": {
        "perfil", "experiencia", "habilidades", "empresa", "equipo",
        "desarrollo", "ingeniero", "calidad", "gestion", "pruebas",
        "seguimiento", "responsabilidades", "proyecto",
    },
    "it": {
        "profilo", "esperienza", "competenze", "azienda", "squadra",
        "sviluppo", "ingegnere", "qualita", "gestione", "test",
        "responsabilita", "progetto",
    },
    "pt": {
        "perfil", "experiencia", "habilidades", "empresa", "equipe",
        "desenvolvimento", "engenheiro", "qualidade", "gestao", "testes",
        "responsabilidades", "projeto",
    },
    "nl": {
        "profiel", "ervaring", "vaardigheden", "bedrijf", "team",
        "ontwikkeling", "ingenieur", "kwaliteit", "beheer", "testen",
        "verantwoordelijkheden", "project",
    },
}

_SCRIPT_PATTERNS: Dict[str, str] = {
    "hiragana": r"[\u3040-\u309f]",
    "katakana": r"[\u30a0-\u30ff]",
    "han": r"[\u4e00-\u9fff]",
    "hangul": r"[\uac00-\ud7af]",
    "arabic": r"[\u0600-\u06ff]",
    "cyrillic": r"[\u0400-\u04ff]",
    "greek": r"[\u0370-\u03ff]",
}

_TARGET_SCRIPTS: Dict[str, Set[str]] = {
    "ja": {"hiragana", "katakana", "han"},
    "zh": {"han"},
    "ko": {"hangul"},
    "ar": {"arabic"},
    "ru": {"cyrillic"},
    "el": {"greek"},
}


def _ascii_fold(text: str) -> str:
    return (
        unicodedata.normalize("NFKD", str(text or ""))
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
        .strip()
    )


def _is_han_only_text(text: Optional[str]) -> bool:
    raw = str(text or "")
    scripts = _script_flags(raw)
    return bool(raw.strip()) and scripts == {"han"}


def _language_marker_scores(text: Optional[str]) -> Dict[str, int]:
    folded = _ascii_fold(str(text or ""))
    tokens = re.findall(r"[a-z]+", folded)
    scores = {lang: 0 for lang in _LATIN_LANGUAGE_MARKERS}
    if not tokens:
        return scores
    for lang, markers in _LATIN_LANGUAGE_MARKERS.items():
        scores[lang] = sum(1 for token in tokens if token in markers)
    return scores


def _script_flags(text: Optional[str]) -> Set[str]:
    raw = str(text or "")
    flags: Set[str] = set()
    for name, pattern in _SCRIPT_PATTERNS.items():
        if re.search(pattern, raw):
            flags.add(name)
    return flags


def normalize_language_code(language: Optional[str]) -> str:
    raw = str(language or "").strip()
    if not raw:
        return "fr"
    normalized = _ascii_fold(raw)
    if raw in _LANGUAGE_ALIASES:
        return _LANGUAGE_ALIASES[raw]
    if normalized in _LANGUAGE_ALIASES:
        return _LANGUAGE_ALIASES[normalized]
    for alias, code in _LANGUAGE_ALIASES.items():
        if normalized.startswith(alias):
            return code
    return "fr"


def detect_language_from_text_default(text: Optional[str]) -> str:
    if not text or not str(text).strip():
        return "fr"
    raw = str(text)
    scripts = _script_flags(raw)
    if "hiragana" in scripts or "katakana" in scripts:
        return "ja"
    if "hangul" in scripts:
        return "ko"
    if "arabic" in scripts:
        return "ar"
    if "cyrillic" in scripts:
        return "ru"
    if "greek" in scripts:
        return "el"
    if "han" in scripts:
        return "zh"

    scores = _language_marker_scores(raw)
    best_lang = "fr"
    best_score = -1
    second_best = -1
    for lang, score in scores.items():
        if score > best_score:
            second_best = best_score
            best_score = score
            best_lang = lang
        elif score > second_best:
            second_best = score

    if best_score > 0 and best_score > second_best:
        return best_lang
    if scores.get("en", 0) > scores.get("fr", 0) + 1:
        return "en"
    return "fr"


def language_token_scores(text: Optional[str]) -> Tuple[int, int, int]:
    if not text or not str(text).strip():
        return 0, 0, 0
    lowered = _ascii_fold(str(text))
    tokens = re.findall(r"[a-z]+", lowered)
    if not tokens:
        return 0, 0, 0
    scores = _language_marker_scores(text)
    fr_score = scores.get("fr", 0)
    en_score = scores.get("en", 0)
    return fr_score, en_score, len(tokens)


def is_mixed_or_mismatched_language(
    text: Optional[str],
    target_language: str,
    *,
    normalize_language: Optional[Callable[[Optional[str]], str]] = None,
    detect_language_from_text: Optional[Callable[[Optional[str]], str]] = None,
) -> bool:
    normalize_fn = normalize_language or normalize_language_code
    target = normalize_fn(target_language)
    return not text_matches_target_language(text, target)


def text_matches_target_language(
    text: Optional[str],
    target_language: str,
    *,
    min_tokens: int = 3,
) -> bool:
    """Return True when visible text is compatible with the target language.

    Short neutral labels such as technical skill names are treated as compatible,
    while clearly mismatched or mixed narrative fragments are rejected.
    """
    raw = str(text or "").strip()
    if not raw:
        return True

    target = normalize_language_code(target_language)
    folded = _ascii_fold(raw)
    latin_tokens = re.findall(r"[a-z]+", folded)
    token_count = len(latin_tokens)
    scripts = _script_flags(raw)
    if token_count <= 0 and not scripts:
        return True

    lowered_tokens = [token.casefold() for token in re.findall(r"[a-zA-Z+#]+", folded)]
    technical_singletons = {
        "sql",
        "python",
        "java",
        "c",
        "c++",
        "c#",
        "api",
        "qa",
        "ui",
        "ux",
        "aws",
        "azure",
        "gcp",
        "etl",
        "elt",
        "jira",
        "scrum",
        "gherkin",
        "tableau",
        "powerbi",
        "looker",
        "excel",
        "github",
    }
    if len(lowered_tokens) == 1 and lowered_tokens[0] in technical_singletons:
        return True
    marker_scores = _language_marker_scores(raw)
    target_score = marker_scores.get(target, 0)
    foreign_best = max(
        (score for lang, score in marker_scores.items() if lang != target),
        default=0,
    )
    has_non_ascii = any(ord(ch) > 127 for ch in raw)

    if target in _TARGET_SCRIPTS:
        compatible_scripts = _TARGET_SCRIPTS[target]
        incompatible_scripts = scripts - compatible_scripts
        if incompatible_scripts:
            return False
        if scripts & compatible_scripts:
            if target == "ja" and scripts == {"han"}:
                detected = detect_language_from_text_default(raw)
                return detected == target
            return True
        if 0 < token_count <= 2 and all(token in technical_singletons for token in lowered_tokens):
            return True
        if foreign_best > 0 and token_count >= 1:
            return False
        detected = detect_language_from_text_default(raw)
        if detected == target:
            return True
        if scripts:
            return False
        if token_count >= min_tokens:
            return False
        return True

    if scripts:
        return False

    short_foreign_rejectors = {
        "en": {"anomalie", "anomalies", "critique", "critiques", "unitaire", "unitaires"},
        "de": {"with", "skills", "experience", "business", "developer", "manager", "engineer", "unit", "bug", "tracking"},
        "fr": {"with", "skills", "business", "developer", "manager", "engineer", "unit", "bug", "tracking"},
        "es": {"with", "skills", "business", "developer", "manager", "engineer", "unit", "bug", "tracking"},
        "it": {"with", "skills", "business", "developer", "manager", "engineer", "unit", "bug", "tracking"},
        "pt": {"with", "skills", "business", "developer", "manager", "engineer", "unit", "bug", "tracking"},
        "nl": {"with", "skills", "business", "developer", "manager", "engineer", "unit", "bug", "tracking"},
    }
    reject_markers = short_foreign_rejectors.get(target, set())
    if token_count <= 2 and any(token in reject_markers for token in lowered_tokens):
        return False

    if target_score > 0 and target_score >= foreign_best:
        return True
    if foreign_best >= 2 and foreign_best > target_score:
        return False
    if target != "en" and marker_scores.get("en", 0) >= 2 and target_score == 0:
        return False
    if target != "fr" and marker_scores.get("fr", 0) >= 2 and target_score == 0:
        return False

    detected = detect_language_from_text_default(raw)
    if detected == target:
        return True
    if token_count >= min_tokens and detected != target:
        return False
    return True


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
            if (
                analysis_norm == "ja"
                and normalize_fn(detected) == "zh"
                and _is_han_only_text(offer_text)
            ):
                return analysis_norm
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
