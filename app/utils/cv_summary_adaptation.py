"""Helpers for concise, stable summary adaptation."""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any, Dict, Iterable, List


_ACRONYM_TOKEN_PATTERN = re.compile(r"^[A-Z0-9]{2,6}$")
_COMPOSITE_ACRONYM_PATTERN = re.compile(r"^[A-Z0-9]+(?:[&/+#.-][A-Z0-9]+)+$")
_GENERIC_SKILL_LABELS = {
    "skill",
    "skills",
    "competence",
    "competences",
    "competency",
    "competencies",
    "technical skill",
    "technical skills",
    "soft skill",
    "soft skills",
    "tool",
    "tools",
    "technology",
    "technologies",
    "langage",
    "langages",
    "language",
    "languages",
}
_SKILL_NOISE_TOKENS = {
    "worked",
    "working",
    "responsible",
    "managed",
    "delivered",
    "developed",
    "designed",
    "built",
    "led",
    "experience",
    "mission",
}
_ROLE_HEAD_TOKENS = {
    "engineer",
    "ingenieur",
    "developer",
    "developpeur",
    "manager",
    "consultant",
    "architect",
    "analyst",
    "analyste",
    "tester",
    "testeur",
    "director",
    "directeur",
    "owner",
}
_SUMMARY_INLINE_LOWERCASE_TOKENS = {
    "analyse",
    "analysis",
    "benchmark",
    "conception",
    "execution",
    "executer",
    "maintenance",
    "participation",
    "preparation",
    "preparer",
    "redaction",
    "rediger",
    "suivi",
    "suivre",
    "testing",
    "validation",
    "verification",
    "writing",
}
_SUMMARY_INLINE_CONNECTOR_PATTERN = re.compile(
    r"^\s+(?:d['’]|de|des|du|la|le|les|et|a|au|aux|with|for|and|of)\b",
    re.IGNORECASE,
)

_SUMMARY_FRAGMENT_STOPWORDS = {
    # English function words / pronouns that slip through as lone tokens.
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from",
    "he", "her", "here", "his", "if", "in", "is", "it", "its", "less",
    "me", "more", "most", "my", "nor", "not", "of", "on", "or", "our",
    "she", "so", "than", "the", "their", "them", "there", "they", "this",
    "to", "too", "us", "we", "with", "you", "your",
    # French function words.
    "au", "aux", "avec", "ce", "ces", "cet", "cette", "dans", "de", "des",
    "du", "en", "est", "et", "la", "le", "les", "leur", "leurs", "ma",
    "mes", "mon", "nos", "notre", "ou", "par", "pour", "sa", "sans", "se",
    "ses", "son", "sur", "ta", "tes", "ton", "un", "une", "votre", "vos",
    # Generic English words that rarely stand alone as a real skill label.
    "power", "people", "role", "roles", "skill", "skills", "team", "teams",
    "value", "values", "work", "works",
}


def _term_looks_like_fragment_value(text: Any) -> bool:
    """Return True for items that aren't presentable as standalone skill labels.

    Catches single-token pronouns or bare words like ``our`` or ``power`` that
    slip through keyword extraction and make the targeted summary look like a
    list of tokens rather than skills. Multi-token phrases pass through.
    """

    value = str(text or "").strip()
    if not value:
        return True
    if len(value) < 2:
        return True
    norm = _normalize_marker(value)
    if not norm:
        return True
    tokens = [t for t in norm.split() if t]
    if not tokens:
        return True
    if len(tokens) == 1:
        single = tokens[0]
        if len(single) < 2:
            return True
        if single in _SUMMARY_FRAGMENT_STOPWORDS:
            return True
    return False


_SUMMARY_ACTION_REJECTORS = {
    "fr": {
        "rediger",
        "suivre",
        "proposer",
        "automatiser",
        "consolider",
        "fiabiliser",
        "assurer",
        "realiser",
        "gerer",
        "coordonner",
        "concevoir",
        "executer",
    },
    "en": {
        "write",
        "track",
        "support",
        "deliver",
        "develop",
        "manage",
        "build",
        "design",
        "lead",
        "coordinate",
        "automate",
    },
}


def _normalize_marker(text: Any) -> str:
    raw = str(text or "").strip().casefold()
    if not raw:
        return ""
    folded = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii")
    folded = re.sub(r"[^a-z0-9]+", " ", folded)
    return re.sub(r"\s+", " ", folded).strip()


_POSITIONING_HARD_BLOCKLIST = frozenset({
    "into", "onto", "with", "from", "about", "through", "within", "over",
    "under", "across", "upon", "toward", "towards", "around",
    "the", "a", "an", "les", "la", "le", "des", "du", "de", "and", "or", "but",
    "et", "ou", "mais", "donc", "car",
    "seamlessly", "easily", "simply", "really", "very", "just", "well",
    "innovative", "cutting edge", "leading", "best", "top", "world class",
    "technology", "solution", "approach", "field", "industry", "domain",
    "experience", "knowledge", "background", "skills", "abilities", "power",
    "our", "your", "their", "nos", "vos", "leurs",
    "designed", "integrate", "integrated", "integrating",
    "developed", "developing", "implemented", "implementing",
    "conçu", "concu", "integre", "integrer",
})

_POSITIONING_SCORE_VERB_SUFFIXES = ("ed", "ing", "ify", "ize", "ise")
_POSITIONING_SCORE_ADVERB_SUFFIX = "ly"
_POSITIONING_SCORE_TECH_SUFFIXES = ("ops", "db", "sql", "js", "ai", "ml", "py")


def _is_positioning_blocked(norm: str) -> bool:
    """Hard reject: obvious junk that must never land in a positioning sentence."""
    if not norm:
        return True
    tokens = norm.split()
    if len(tokens) == 1:
        tok = tokens[0]
        if tok in _POSITIONING_HARD_BLOCKLIST:
            return True
        if len(tok) > 4 and tok.endswith(_POSITIONING_SCORE_ADVERB_SUFFIX):
            return True
    if norm in _POSITIONING_HARD_BLOCKLIST:
        return True
    return False


def _profile_skill_vocabulary(profile_json: Dict[str, Any] | None) -> set[str]:
    """Aggregate normalized skill-like lemmas from a profile JSON.

    Used as the Tier-1 positive signal in skillishness scoring: an offer
    keyword that aligns with a profile lemma is a reformulation candidate,
    which is the product's stated goal.
    """
    lemmas: set[str] = set()
    if not isinstance(profile_json, dict):
        return lemmas

    def _collect(value: Any) -> None:
        if isinstance(value, str):
            norm = _normalize_marker(value)
            if norm and len(norm) >= 2:
                lemmas.add(norm)
                for token in norm.split():
                    if len(token) >= 3:
                        lemmas.add(token)
        elif isinstance(value, dict):
            for sub in value.values():
                _collect(sub)
        elif isinstance(value, (list, tuple)):
            for sub in value:
                _collect(sub)

    for key in ("skills", "soft_skills", "technologies", "tools"):
        _collect(profile_json.get(key))

    for key in ("experience", "experiences", "projects", "certifications"):
        items = profile_json.get(key)
        if not isinstance(items, list):
            continue
        for entry in items:
            if not isinstance(entry, dict):
                continue
            for field in ("title", "role", "name", "technologies", "tools", "skills", "stack"):
                _collect(entry.get(field))
    return lemmas


def _skillish_score(
    term: str,
    norm: str,
    *,
    profile_lemmas: set[str],
) -> int:
    """Soft signal ranking a candidate by how skill-shaped it is.

    Small magnitudes (profile alignment +3, shape bonuses +1 each, verb/adverb
    penalties -1 each) so the scoring informs ranking without dominating.
    Hard blocking is handled separately by _is_positioning_blocked.
    """
    if not norm:
        return 0
    tokens = norm.split()
    score = 0

    for lemma in profile_lemmas:
        if not lemma:
            continue
        if lemma == norm or (len(lemma) >= 3 and (lemma in norm or norm in lemma)):
            score += 3
            break

    if len(tokens) >= 2:
        score += 1
    if re.fullmatch(r"[A-Z0-9]{2,6}", term.strip() or ""):
        score += 1
    if re.search(r"[A-Z][a-z]+[A-Z]", term or ""):
        score += 1
    if any(tok.endswith(_POSITIONING_SCORE_TECH_SUFFIXES) for tok in tokens):
        score += 1

    if len(tokens) == 1:
        tok = tokens[0]
        if len(tok) > 3 and tok.endswith(_POSITIONING_SCORE_VERB_SUFFIXES):
            score -= 1
        if len(tok) > 4 and tok.endswith(_POSITIONING_SCORE_ADVERB_SUFFIX):
            score -= 1

    return score


def _iter_profile_skill_fallback(profile_json: Dict[str, Any] | None) -> List[str]:
    """Ordered profile skill labels for Tier-3 fallback when offer yields too few candidates.

    Accepts three shapes seen in the codebase:
      - ``profile["skills"] = ["Python", "Django"]`` (bare strings)
      - ``profile["skills"] = [{"name": "Python"}, …]`` (labelled dicts)
      - ``profile["skills"] = [{"category": "Backend", "items": ["Python"]}, …]``
        (CV-JSON grouped categories — the common runtime shape)
    """
    out: List[str] = []
    if not isinstance(profile_json, dict):
        return out
    for key in ("skills", "technologies", "tools"):
        items = profile_json.get(key)
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, str) and item.strip():
                out.append(item.strip())
            elif isinstance(item, dict):
                label = item.get("name") or item.get("label") or item.get("title")
                if isinstance(label, str) and label.strip():
                    out.append(label.strip())
                nested = item.get("items")
                if isinstance(nested, list):
                    for sub in nested:
                        if isinstance(sub, str) and sub.strip():
                            out.append(sub.strip())
    return out


_DETERMINISTIC_APPENDIX_PREFIXES = tuple(
    _normalize_marker(value)
    for value in (
        "Target role",
        "Poste cible",
        "Target company",
        "Entreprise cible",
        "Offer-aligned strengths",
        "Forces alignees offre",
    )
)

_MINIMUM_SUMMARY_PREFIXES = tuple(
    _normalize_marker(value)
    for value in (
        "Profile aligned with",
        "Profil aligne sur le poste",
    )
)


def strip_deterministic_summary_appendices(summary: str) -> str:
    """Remove synthetic offer-appendix sentences from a summary."""
    text = str(summary or "").strip()
    if not text:
        return ""

    kept: List[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        clean_sentence = sentence.strip()
        if not clean_sentence:
            continue
        marker = _normalize_marker(clean_sentence)
        if any(marker.startswith(prefix) for prefix in _DETERMINISTIC_APPENDIX_PREFIXES):
            continue
        kept.append(clean_sentence)
    return " ".join(kept).strip()


def is_minimum_summary_template(summary: str) -> bool:
    """Detect deterministic fallback summary templates."""
    marker = _normalize_marker(str(summary or "")[:200])
    if not marker:
        return False
    return any(marker.startswith(prefix) for prefix in _MINIMUM_SUMMARY_PREFIXES)


def select_summary_focus_terms(
    terms: Iterable[Any],
    *,
    max_terms: int = 3,
) -> List[str]:
    """Pick a few representative terms for the summary hook."""
    selected: List[str] = []
    seen: set[str] = set()
    target_count = max(1, int(max_terms or 1))

    for raw in terms:
        text = _clean_candidate_term(raw)
        if not text:
            continue
        if len(text) > 72:
            continue
        if _term_looks_like_fragment_value(text):
            continue
        norm = _normalize_marker(text)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        selected.append(text)
        if len(selected) >= target_count:
            break

    return selected


def build_summary_focus_sentence(
    terms: Iterable[Any],
    *,
    language_code: str = "fr",
    max_terms: int = 3,
) -> str:
    """Build a short summary emphasis sentence from representative terms."""
    focus_terms = select_summary_focus_terms(terms, max_terms=max_terms)
    if not focus_terms:
        return ""
    joined = ", ".join(_format_term_for_inline_summary(item) for item in focus_terms)
    if language_code == "en":
        return f"Relevant strengths include {joined}."
    return f"Atouts pertinents : {joined}."


def collect_targeted_offer_terms(
    offer_terms: Iterable[Any],
    *,
    profile_json: Dict[str, Any] | None = None,
    max_terms: int = 3,
    excluded_terms: Iterable[Any] = (),
) -> List[str]:
    """Select offer terms to surface in the targeted summary sentence.

    Hierarchy (Generation → Offer → Profile):
      1. Offer keyword matching a profile lemma (reformulation — product goal).
      2. Skill-shaped offer keyword not in profile (cross-domain positioning).
      3. Profile skill verbatim (fallback when offer yields too few candidates).

    Hard blocklist rejects verbs, prepositions, adverbs, and generic field
    nouns ("technology", "solution", "into", "designed", "seamlessly"…) that
    could never read as a skill. Scoring is soft — profile alignment is the
    dominant positive signal; structural bonuses (multi-word compound,
    acronym, tech suffix) and verb/adverb penalties are small (+/-1) so they
    inform ranking without dominating.

    Prefer emitting no sentence over a sentence with junk tokens.
    """
    excluded = {
        _normalize_marker(item)
        for item in (excluded_terms or [])
        if _normalize_marker(item)
    }
    target_count = max(1, int(max_terms or 1))
    profile_lemmas = _profile_skill_vocabulary(profile_json)

    scored: List[tuple[int, int, str, str]] = []
    seen: set[str] = set()

    for order, raw in enumerate(offer_terms or []):
        text = _clean_candidate_term(raw)
        if not text or len(text) > 72:
            continue
        if _term_looks_like_fragment_value(text):
            continue
        norm = _normalize_marker(text)
        if not norm or norm in seen or norm in excluded:
            continue
        tokens = [token for token in norm.split() if token]
        if not tokens or len(tokens) > 6:
            continue
        if _is_positioning_blocked(norm):
            continue
        seen.add(norm)
        score = _skillish_score(text, norm, profile_lemmas=profile_lemmas)
        scored.append((score, order, text, norm))

    scored.sort(key=lambda item: (-item[0], item[1]))
    selected: List[str] = [text for _s, _o, text, _n in scored[:target_count]]

    if len(selected) < target_count:
        selected_norms = {_normalize_marker(text) for text in selected}
        for fallback in _iter_profile_skill_fallback(profile_json):
            if len(selected) >= target_count:
                break
            text = _clean_candidate_term(fallback)
            if not text or len(text) > 72:
                continue
            norm = _normalize_marker(text)
            if not norm or norm in selected_norms or norm in excluded:
                continue
            if _is_positioning_blocked(norm):
                continue
            if _term_looks_like_fragment_value(text):
                continue
            selected.append(text)
            selected_norms.add(norm)

    return selected


def build_targeted_summary_focus_sentence(
    terms: Iterable[Any],
    *,
    company: str = "",
    language_code: str = "fr",
    max_terms: int = 3,
) -> str:
    focus_terms = select_summary_focus_terms(terms, max_terms=max_terms)
    if not focus_terms:
        return ""
    joined = ", ".join(_format_term_for_inline_summary(item) for item in focus_terms)
    company_name = str(company or "").strip()
    is_en = str(language_code or "").lower().startswith("en")
    if company_name:
        if is_en:
            return f"Relevant strengths for {company_name} include {joined}."
        return f"Atouts pertinents pour {company_name} : {joined}."
    return build_summary_focus_sentence(
        focus_terms,
        language_code=language_code,
        max_terms=max_terms,
    )


_POSITIONING_SENTENCE_PATTERNS = {
    "fr": re.compile(
        r"\s*Atouts\s+pertinents(?:\s+pour\s+[^.:]{1,80})?\s*[:\-]\s*[^.]*\.",
        re.IGNORECASE,
    ),
    "en": re.compile(
        r"\s*Relevant\s+strengths(?:\s+for\s+[^.:]{1,80})?\s+include\s+[^.]*\.",
        re.IGNORECASE,
    ),
}


def strip_positioning_sentences(summary: Any, language_code: str = "fr") -> str:
    text = str(summary or "")
    if not text:
        return ""
    lang_key = "en" if str(language_code or "").lower().startswith("en") else "fr"
    pattern = _POSITIONING_SENTENCE_PATTERNS.get(lang_key)
    if pattern is None:
        return text.strip()
    stripped = pattern.sub("", text)
    return re.sub(r"\s+", " ", stripped).strip()


def _clean_candidate_term(text: Any) -> str:
    value = re.sub(r"\s+", " ", str(text or "").strip())
    if not value:
        return ""
    return re.sub(r"^[,.;:\s]+|[,.;:\s]+$", "", value)


def _format_term_for_inline_summary(text: Any) -> str:
    """Lowercase leading action fragments when embedded inside a sentence."""
    value = _clean_candidate_term(text)
    if not value:
        return ""

    match = re.match(r"^(?P<head>[^\s,;:()]+)(?P<tail>.*)$", value)
    if not match:
        return value

    head = str(match.group("head") or "")
    tail = str(match.group("tail") or "")
    head_norm = _normalize_marker(head)
    if not head_norm:
        return value
    if _is_acronym_like_token(head):
        return value
    if re.search(r"[A-Z]", head[1:]):
        return value
    should_lower = head_norm in _SUMMARY_INLINE_LOWERCASE_TOKENS
    if not should_lower and _SUMMARY_INLINE_CONNECTOR_PATTERN.match(tail):
        should_lower = True
    if not should_lower:
        return value

    return f"{head[:1].lower()}{head[1:]}{tail}"


def _is_acronym_like_token(token: str) -> bool:
    stripped = str(token or "").strip()
    if not stripped:
        return False
    letters_only = re.sub(r"[^A-Za-z0-9]", "", stripped)
    if not letters_only:
        return False
    if _ACRONYM_TOKEN_PATTERN.fullmatch(letters_only):
        return letters_only.upper() == letters_only
    return bool(_COMPOSITE_ACRONYM_PATTERN.fullmatch(stripped))


def _humanize_role_token(token: str) -> str:
    if _is_acronym_like_token(token):
        return token
    lowered = token.lower()
    return lowered[:1].upper() + lowered[1:] if lowered else ""


def _humanize_role_text(text: Any) -> str:
    role_text = re.sub(r"\s+", " ", str(text or "").strip())
    if not role_text:
        return ""

    letters = [char for char in role_text if char.isalpha()]
    if letters:
        uppercase_ratio = sum(1 for char in letters if char.isupper()) / float(len(letters))
        if uppercase_ratio >= 0.65:
            role_text = " ".join(
                _humanize_role_token(part)
                for part in role_text.split()
                if part
            )

    return role_text


def _is_skill_summary_candidate(
    text: Any,
    *,
    excluded_terms: Iterable[str],
) -> bool:
    candidate = _clean_candidate_term(text)
    if not candidate or len(candidate) > 72:
        return False
    if any(mark in candidate for mark in ("!", "?", "\n")):
        return False

    normalized = _normalize_marker(candidate)
    if not normalized:
        return False
    if normalized in _GENERIC_SKILL_LABELS:
        return False
    if normalized in excluded_terms:
        return False

    tokens = [token for token in normalized.split() if token]
    if not tokens or len(tokens) > 5:
        return False
    if tokens[0] in _SUMMARY_ACTION_REJECTORS["fr"] or tokens[0] in _SUMMARY_ACTION_REJECTORS["en"]:
        return False
    if any(token in _SKILL_NOISE_TOKENS for token in tokens):
        return False
    if len(tokens) <= 2 and any(token in _ROLE_HEAD_TOKENS for token in tokens):
        return False

    compact = candidate.strip()
    if "." in compact:
        dotted_tech = bool(re.fullmatch(r"(?:[A-Za-z0-9+#]+(?:\.[A-Za-z0-9+#]+)+)", compact))
        if not dotted_tech and (re.search(r"\.\s", compact) or compact.endswith(".")):
            return False

    return True


def _collect_profile_skill_terms(
    profile_json: Dict[str, Any],
    *,
    max_terms: int = 4,
    excluded_terms: Iterable[str] = (),
) -> List[str]:
    skills: List[str] = []
    seen: set[str] = set()
    excluded = {
        _normalize_marker(item)
        for item in (excluded_terms or [])
        if _normalize_marker(item)
    }

    for entry in profile_json.get("skills") or []:
        candidates: List[Any] = []
        if isinstance(entry, str):
            candidates.append(entry)
        elif isinstance(entry, dict):
            candidates.extend([entry.get("name"), entry.get("skill")])
            items = entry.get("items")
            if isinstance(items, list):
                candidates.extend(items)
            elif not candidates:
                candidates.append(entry.get("label"))

        for raw in candidates:
            text = _clean_candidate_term(raw)
            if not _is_skill_summary_candidate(text, excluded_terms=excluded):
                continue
            norm = _normalize_marker(text)
            if norm in seen:
                continue
            seen.add(norm)
            skills.append(text)
            if len(skills) >= max_terms:
                return skills

    return skills


def build_minimum_profile_summary(
    profile_json: Dict[str, Any],
    *,
    target_job_title: str = "",
    language_code: str = "fr",
) -> str:
    """Build a concise candidate-centric fallback summary."""
    profile_data = profile_json if isinstance(profile_json, dict) else {}
    experiences = profile_data.get("experiences") or []

    experience_titles: List[str] = []
    for entry in experiences:
        if not isinstance(entry, dict):
            continue
        title = str(
            entry.get("title")
            or entry.get("position")
            or entry.get("role")
            or entry.get("job_title")
            or ""
        ).strip()
        if not title:
            continue
        normalized = _normalize_marker(title)
        if not normalized:
            continue
        if normalized in {_normalize_marker(item) for item in experience_titles}:
            continue
        experience_titles.append(title)
        if len(experience_titles) >= 2:
            break

    role_hint = _humanize_role_text(
        target_job_title or (experience_titles[0] if experience_titles else "")
    )
    skill_terms = _collect_profile_skill_terms(
        profile_data,
        max_terms=3,
        excluded_terms=[
            target_job_title,
            role_hint,
            *experience_titles,
        ],
    )

    if language_code == "en":
        subject = role_hint or "Technical profile"
        if skill_terms:
            formatted_terms = [
                _format_term_for_inline_summary(item) for item in skill_terms if item
            ]
            return f"{subject} with experience in {_join_summary_terms(formatted_terms, language_code='en')}."
        if len(experience_titles) > 1:
            return f"{subject} with experience spanning {experience_titles[0]} and {experience_titles[1]}."
        return f"{subject} with software delivery experience."

    if skill_terms:
        formatted_terms = [
            _format_term_for_inline_summary(item) for item in skill_terms if item
        ]
        return f"{role_hint or 'Profil technique'} avec une experience en {_join_summary_terms(formatted_terms, language_code='fr')}."

    subject = role_hint or "Profil technique"
    if skill_terms:
        formatted_terms = [
            _format_term_for_inline_summary(item) for item in skill_terms if item
        ]
        return f"{subject} orienté {_join_summary_terms(formatted_terms, language_code='fr')}."
    if len(experience_titles) > 1:
        return f"{subject} avec une experience couvrant {experience_titles[0]} et {experience_titles[1]}."
    return f"{subject} avec une experience sur des projets logiciels."


def _join_summary_terms(terms: Iterable[Any], *, language_code: str = "fr") -> str:
    values = [str(item or "").strip() for item in terms if str(item or "").strip()]
    if not values:
        return ""
    if len(values) == 1:
        return values[0]

    conjunction = "and" if str(language_code or "").lower().startswith("en") else "et"
    if len(values) == 2:
        return f"{values[0]} {conjunction} {values[1]}"
    return f"{', '.join(values[:-1])} {conjunction} {values[-1]}"
