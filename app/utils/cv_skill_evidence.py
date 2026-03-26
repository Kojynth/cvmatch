"""Evidence-aware helpers for coherent CV skills sections."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Tuple

from .cv_offer_term_routing import route_term_to_section
from .keyword_alignment import (
    normalize_keyword_for_match,
    normalized_term_in_probe,
)

_STOPWORDS = {
    "a",
    "an",
    "and",
    "au",
    "aux",
    "avec",
    "dans",
    "de",
    "des",
    "du",
    "en",
    "et",
    "for",
    "la",
    "le",
    "les",
    "of",
    "on",
    "ou",
    "pour",
    "sur",
    "the",
    "to",
    "un",
    "une",
    "with",
}

_GENERIC_NOISE_TERMS = {
    "activite",
    "activites",
    "avenir",
    "candidature",
    "client",
    "competence",
    "competences",
    "confiance",
    "construisons",
    "ensemble",
    "entreprise",
    "est",
    "france",
    "hautes",
    "hf",
    "h f",
    "leader",
    "lieu",
    "logiciel",
    "mondial",
    "offre",
    "poste",
    "projet",
    "projets",
    "qualite",
    "secteur",
    "secteurs",
    "service",
    "skills",
    "technologies",
    "thales",
    "verification",
}

_SOFT_SKILL_HINTS = {
    "adaptabilite",
    "adaptability",
    "autonomie",
    "autonomy",
    "communication",
    "creativite",
    "creativity",
    "curiosite",
    "curiosity",
    "esprit d equipe",
    "influence",
    "leadership",
    "organisation",
    "organization",
    "problem solving",
    "relation client",
    "rigueur",
    "service client",
    "stakeholder",
    "teamwork",
}

_AMBIGUOUS_SINGLE_WORD_SKILL_TERMS = {
    "analysis",
    "analyse",
    "analytics",
    "automation",
    "conception",
    "design",
    "integration",
    "ivvq",
    "qa",
    "qualification",
    "quality",
    "test",
    "testing",
    "validation",
    "verification",
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


def looks_like_noise_skill_term(term: Any) -> bool:
    norm = normalize_keyword_for_match(term)
    if not norm:
        return True
    if norm in _GENERIC_NOISE_TERMS:
        return True
    if re.fullmatch(r"\(?h\s*/?\s*f\)?", str(term or "").strip(), flags=re.IGNORECASE):
        return True
    tokens = [token for token in norm.split() if token]
    if not tokens:
        return True
    if len(tokens) == 1 and tokens[0] in _GENERIC_NOISE_TERMS:
        return True
    return False


def classify_skill_bucket(term: Any) -> str:
    norm = normalize_keyword_for_match(term)
    if not norm:
        return "technical"
    if any(hint in norm for hint in _SOFT_SKILL_HINTS):
        return "soft"
    return "technical"


def _normalized_skill_tokens(term: Any) -> List[str]:
    norm = normalize_keyword_for_match(term)
    if not norm:
        return []
    return [token for token in norm.split() if token]


def _tokenize_for_support(term: Any) -> List[str]:
    norm = normalize_keyword_for_match(term)
    if not norm:
        return []
    return [
        token
        for token in re.split(r"[^a-z0-9+#]+", norm)
        if len(token) > 2 and token not in _STOPWORDS
    ]


def _collect_profile_support_fragments(profile_json: Dict[str, Any]) -> Tuple[str, str]:
    profile = profile_json if isinstance(profile_json, dict) else {}
    technical_parts: List[str] = []
    soft_parts: List[str] = []

    def add_technical(value: Any) -> None:
        if isinstance(value, str):
            text = str(value or "").strip()
            if text:
                technical_parts.append(text)
            return
        if isinstance(value, list):
            for item in value:
                add_technical(item)
            return
        if isinstance(value, dict):
            for key in ("name", "skill", "items", "technologies", "tech_stack"):
                add_technical(value.get(key))

    def add_soft(value: Any) -> None:
        if isinstance(value, str):
            text = str(value or "").strip()
            if text:
                soft_parts.append(text)
            return
        if isinstance(value, list):
            for item in value:
                add_soft(item)
            return
        if isinstance(value, dict):
            for key in ("name", "skill", "items"):
                add_soft(value.get(key))

    for entry in profile.get("skills") or []:
        add_technical(entry)
    for entry in profile.get("soft_skills") or []:
        add_soft(entry)
    for entry in profile.get("projects") or []:
        if not isinstance(entry, dict):
            continue
        add_technical(entry.get("technologies"))
        add_technical(entry.get("tech_stack"))
        add_technical(entry.get("description"))
    for entry in profile.get("certifications") or []:
        if isinstance(entry, dict):
            add_technical(entry.get("name"))
    for entry in profile.get("education") or []:
        if not isinstance(entry, dict):
            continue
        add_technical(entry.get("degree"))
        add_technical(entry.get("field_of_study"))
        add_technical(entry.get("details"))
    # Canonical profile_json key is "experiences"; keep "experience"
    # for backward compatibility with legacy payloads.
    experience_entries = profile.get("experiences") or profile.get("experience") or []
    for entry in experience_entries:
        if not isinstance(entry, dict):
            continue
        add_technical(entry.get("summary"))
        add_technical(entry.get("highlights"))
        add_technical(entry.get("description"))
        add_soft(entry.get("summary"))
        add_soft(entry.get("highlights"))
        add_soft(entry.get("description"))

    return (
        normalize_keyword_for_match(" ".join(technical_parts)),
        normalize_keyword_for_match(" ".join(soft_parts)),
    )


def skill_term_supported_by_profile(term: Any, profile_json: Dict[str, Any]) -> bool:
    if looks_like_noise_skill_term(term):
        return False
    norm = normalize_keyword_for_match(term)
    if not norm:
        return False
    technical_probe, soft_probe = _collect_profile_support_fragments(profile_json)
    probe = " ".join(part for part in (technical_probe, soft_probe) if part).strip()
    if not probe:
        return False
    if normalized_term_in_probe(probe, norm):
        return True

    term_tokens = _tokenize_for_support(term)
    if not term_tokens:
        return False
    probe_tokens = set(_tokenize_for_support(probe))
    if not probe_tokens:
        return False
    shared = sum(1 for token in term_tokens if token in probe_tokens)
    if len(term_tokens) == 1:
        return shared >= 1
    required = max(2, int(len(term_tokens) * 0.6 + 0.5))
    return shared >= required


def should_keep_skill_term(
    term: Any,
    profile_json: Dict[str, Any] | None = None,
) -> bool:
    if looks_like_noise_skill_term(term):
        return False
    if route_term_to_section(term) == "skills":
        return True

    tokens = _normalized_skill_tokens(term)
    if len(tokens) != 1:
        return False

    token = tokens[0]
    if token in _AMBIGUOUS_SINGLE_WORD_SKILL_TERMS:
        return True

    if isinstance(profile_json, dict) and profile_json:
        return skill_term_supported_by_profile(term, profile_json)

    return False


def collect_supported_skill_terms(
    terms: Iterable[Any],
    profile_json: Dict[str, Any],
) -> Dict[str, List[str]]:
    buckets: Dict[str, List[str]] = {"technical": [], "soft": []}
    for raw in _dedup_preserve(terms):
        if not should_keep_skill_term(raw, profile_json):
            continue
        if not skill_term_supported_by_profile(raw, profile_json):
            continue
        bucket = classify_skill_bucket(raw)
        buckets[bucket].append(raw)
    for key in list(buckets.keys()):
        buckets[key] = _dedup_preserve(buckets[key])
    return buckets


def skills_section_has_supported_signal(
    skills_section: Any,
    profile_json: Dict[str, Any],
) -> Tuple[int, int, int]:
    supported = 0
    plausible = 0
    hard_unsupported = 0
    if not isinstance(skills_section, list):
        return supported, plausible, hard_unsupported
    for block in skills_section:
        if not isinstance(block, dict):
            continue
        for item in block.get("items") or []:
            text = str(item or "").strip()
            if not text:
                continue
            if skill_term_supported_by_profile(text, profile_json):
                supported += 1
            elif should_keep_skill_term(text, profile_json):
                plausible += 1
            else:
                hard_unsupported += 1
    return supported, plausible, hard_unsupported
