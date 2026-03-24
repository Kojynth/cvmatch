"""Route missing offer terms to the most suitable CV sections."""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, Iterable, List

from .keyword_alignment import normalize_keyword_for_match

SECTION_KEYS = (
    "summary",
    "experience",
    "skills",
    "projects",
    "education",
    "certifications",
    "languages",
)

_LANGUAGE_ALIASES = {
    "fr": "french",
    "fra": "french",
    "french": "french",
    "francais": "french",
    "en": "english",
    "eng": "english",
    "english": "english",
    "anglais": "english",
    "de": "german",
    "ger": "german",
    "german": "german",
    "allemand": "german",
    "es": "spanish",
    "spa": "spanish",
    "spanish": "spanish",
    "espagnol": "spanish",
    "it": "italian",
    "ita": "italian",
    "italian": "italian",
    "italien": "italian",
    "pt": "portuguese",
    "por": "portuguese",
    "portuguese": "portuguese",
    "portugais": "portuguese",
    "ja": "japanese",
    "jpn": "japanese",
    "japanese": "japanese",
    "japonais": "japanese",
    "zh": "chinese",
    "chi": "chinese",
    "chinese": "chinese",
    "chinois": "chinese",
    "mandarin": "chinese",
}

_EDUCATION_TOKENS = {
    "academic",
    "academique",
    "academics",
    "bachelor",
    "campus",
    "course",
    "coursework",
    "cours",
    "curriculum",
    "degree",
    "diploma",
    "diplome",
    "doctorat",
    "education",
    "educational",
    "engineering school",
    "ecole",
    "formation",
    "graduation",
    "license",
    "licence",
    "master",
    "msc",
    "phd",
    "school",
    "student",
    "training",
    "universite",
    "university",
}

_CERTIFICATION_TOKENS = {
    "aws certified",
    "az-",
    "certificate",
    "certification",
    "certified",
    "ccna",
    "cisa",
    "cissp",
    "csm",
    "itil",
    "istqb",
    "oracle certified",
    "pmp",
    "prince2",
    "scrum master",
    "toeic",
    "toefl",
    "ielts",
}

_PROJECT_TOKENS = {
    "deployment",
    "deploiement",
    "implementation",
    "integration",
    "migration",
    "plateforme",
    "platform",
    "rollout",
}

_EXPERIENCE_ACTION_PREFIXES = {
    "accompagner",
    "analyse",
    "analyser",
    "automate",
    "automatiser",
    "build",
    "conceive",
    "concevoir",
    "contribute",
    "contribuer",
    "coordinate",
    "coordonner",
    "deliver",
    "delivrer",
    "design",
    "develop",
    "developper",
    "ensure",
    "execute",
    "executer",
    "implement",
    "implementer",
    "maintain",
    "maintenir",
    "manage",
    "participate",
    "participer",
    "prepare",
    "preparer",
    "rediger",
    "run",
    "support",
    "suivre",
    "test",
    "tester",
    "validate",
    "validation",
}

_EXPERIENCE_NOMINAL_HEADS = {
    "conception",
    "execution",
    "maintenance",
    "participation",
    "preparation",
    "redaction",
    "satisfaction",
}

_EXPERIENCE_LINK_TOKENS = {
    "a",
    "au",
    "aux",
    "de",
    "des",
    "du",
    "et",
    "for",
    "of",
    "pour",
    "sur",
    "to",
}

_EXPERIENCE_OBJECT_TOKENS = {
    "team",
    "teams",
    "client",
    "clients",
    "customer",
    "customers",
    "stakeholder",
    "stakeholders",
    "budget",
    "delivery",
    "operations",
    "process",
    "processes",
    "project",
    "projects",
    "service",
    "services",
    "product",
    "products",
    "program",
    "programs",
}


def _dedup_preserve(items: Iterable[Any]) -> List[str]:
    output: List[str] = []
    seen: set[str] = set()
    for raw in items or []:
        text = str(raw or "").strip()
        if not text:
            continue
        norm = normalize_keyword_for_match(text)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        output.append(text)
    return output


def _normalize_ascii_letters(text: Any) -> str:
    raw = str(text or "").strip().casefold()
    if not raw:
        return ""
    folded = unicodedata.normalize("NFKD", raw)
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", folded).strip()


def canonical_language_token(term: Any) -> str:
    raw_source = str(term or "").strip()
    raw = _normalize_ascii_letters(raw_source)
    if not raw:
        return ""
    compact = re.sub(r"[^a-z]+", "", raw)
    # "IT" is commonly used as Information Technology in job offers.
    # Keep uppercase IT as a technical term, while lowercase "it" still maps to italian.
    raw_letters = re.sub(r"[^A-Za-z]+", "", raw_source)
    if compact == "it" and raw_letters == "IT":
        return ""
    return _LANGUAGE_ALIASES.get(compact, "")


def _contains_any(term_norm: str, needles: Iterable[str]) -> bool:
    return any(needle in term_norm for needle in needles if needle)


def _looks_like_certification(term: str) -> bool:
    term_norm = normalize_keyword_for_match(term)
    if not term_norm:
        return False
    if _contains_any(term_norm, _CERTIFICATION_TOKENS):
        return True
    return bool(re.search(r"\b(?:az|dp|ai|sc|pl|ms)-?\d{3}\b", term_norm))


def _looks_like_education(term: str) -> bool:
    term_norm = normalize_keyword_for_match(term)
    if not term_norm:
        return False
    return _contains_any(term_norm, _EDUCATION_TOKENS)


def _looks_like_project(term: str) -> bool:
    term_norm = normalize_keyword_for_match(term)
    if not term_norm:
        return False
    return _contains_any(term_norm, _PROJECT_TOKENS)


def _looks_like_experience_action(term: str) -> bool:
    term_norm = normalize_keyword_for_match(term)
    if not term_norm:
        return False
    tokens = [token for token in term_norm.split() if token]
    if not tokens:
        return False
    first = tokens[0]
    second = tokens[1] if len(tokens) > 1 else ""
    if first in _EXPERIENCE_ACTION_PREFIXES:
        # Keep short noun compounds such as "test automation" in skills.
        if len(tokens) == 2:
            return second in _EXPERIENCE_OBJECT_TOKENS
        return True
    if first in _EXPERIENCE_NOMINAL_HEADS:
        # Keep isolated noun labels like "maintenance" as skills, but route
        # full activity phrases such as "preparation des tests" to experience.
        if len(tokens) <= 1:
            return False
        if any(token in _EXPERIENCE_LINK_TOKENS for token in tokens[1:3]):
            return len(tokens) >= 3
        if any(token in _EXPERIENCE_OBJECT_TOKENS for token in tokens[1:]):
            return len(tokens) >= 3
        return len(tokens) >= 4
    if any(token in _EXPERIENCE_ACTION_PREFIXES for token in tokens[:2]):
        # Avoid over-routing very short compounds into experience.
        return len(tokens) >= 3
    return False


def _looks_like_skill_term(term: str) -> bool:
    term_norm = normalize_keyword_for_match(term)
    if not term_norm:
        return False
    if (
        canonical_language_token(term)
        or _looks_like_certification(term)
        or _looks_like_education(term)
    ):
        return False
    tokens = [token for token in term_norm.split() if token]
    if not tokens or len(tokens) > 6:
        return False
    if _looks_like_experience_action(term):
        return False
    return True


def route_term_to_section(term: Any) -> str:
    text = str(term or "").strip()
    if not text:
        return "experience"
    if canonical_language_token(text):
        return "languages"
    if _looks_like_certification(text):
        return "certifications"
    if _looks_like_education(text):
        return "education"
    if _looks_like_project(text):
        return "projects"
    if _looks_like_experience_action(text):
        return "experience"
    if _looks_like_skill_term(text):
        return "skills"
    return "experience"


def route_terms_to_sections(
    terms: Iterable[Any],
) -> Dict[str, List[str]]:
    routed: Dict[str, List[str]] = {key: [] for key in SECTION_KEYS}
    for raw in _dedup_preserve(terms):
        section = route_term_to_section(raw)
        routed.setdefault(section, []).append(raw)
        routed["summary"].append(raw)
    for key in list(routed.keys()):
        routed[key] = _dedup_preserve(routed[key])
    return routed


def merge_section_term_maps(*maps: Dict[str, List[str]]) -> Dict[str, List[str]]:
    merged: Dict[str, List[str]] = {key: [] for key in SECTION_KEYS}
    for payload in maps:
        if not isinstance(payload, dict):
            continue
        for key in SECTION_KEYS:
            values = payload.get(key)
            if isinstance(values, list):
                merged[key].extend(values)
    for key in SECTION_KEYS:
        merged[key] = _dedup_preserve(merged[key])
    return merged


def format_section_keyword_guidance(
    routed_terms: Dict[str, List[str]],
    *,
    language_code: str = "fr",
    max_terms_per_section: int = 6,
) -> str:
    if not isinstance(routed_terms, dict):
        return ""
    labels = {
        "en": {
            "skills": "skills",
            "experience": "experience",
            "projects": "projects",
            "education": "education",
            "certifications": "certifications",
            "languages": "languages",
        },
        "fr": {
            "skills": "competences",
            "experience": "experience",
            "projects": "projets",
            "education": "formation",
            "certifications": "certifications",
            "languages": "langues",
        },
    }
    active_labels = labels["en"] if language_code == "en" else labels["fr"]
    lines: List[str] = []
    for key in (
        "skills",
        "experience",
        "projects",
        "education",
        "certifications",
        "languages",
    ):
        values = routed_terms.get(key)
        if not isinstance(values, list) or not values:
            continue
        joined = ", ".join(
            _dedup_preserve(values)[: max(1, int(max_terms_per_section))]
        )
        if not joined:
            continue
        lines.append(f"- {active_labels[key]}: {joined}")
    return "\n".join(lines)
