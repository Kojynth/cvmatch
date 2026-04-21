"""Editor-side content quality validators.

Permissive warnings (never auto-rewrite): flag known bad patterns so the user
can decide whether to fix them. These are a second line of defense at source
— the pipeline already repairs S5 (clichés), S6 (tense), S7 (punctuation)
downstream. The grammar detector (S8) is the primary fix for user-authored
typos that the pipeline correctly preserves per the sourcing principle.

Design:
- Narrow, high-precision patterns (leniency-first, CLAUDE.md §10bis).
- Multi-word regexes for clichés → a legitimate action verb alone never matches.
- Grammar list = literal, case-sensitive, known-bad strings only. No general
  spellcheck (that would produce false positives on proper nouns, acronyms,
  multilingual terms).
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Tuple


def _normalize_language_code(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return "fr"
    normalized = re.split(r"[-_]", normalized, maxsplit=1)[0]
    return normalized or "fr"


try:
    from app.utils.cv_quality_audit import _CLICHE_PATTERNS, _CLICHE_PHRASE_PATTERNS
except Exception:  # pragma: no cover - defensive: module always importable
    _CLICHE_PATTERNS = {}
    _CLICHE_PHRASE_PATTERNS = {}


_GRAMMAR_RULES_FR: Tuple[Tuple[re.Pattern, str, str], ...] = (
    (
        re.compile(r"\bLaPoste\b"),
        "LaPoste",
        "La Poste (avec espace)",
    ),
    (
        re.compile(r"\bd['’]automatisations\b", re.IGNORECASE),
        "d'automatisations",
        "d'automatisation (singulier)",
    ),
    (
        re.compile(r"\bDatas\b"),
        "Datas",
        "données",
    ),
    (
        re.compile(r"\bSyst[èe]mes\s+d['’]Informations\b", re.IGNORECASE),
        "Systèmes d'Informations",
        "Systèmes d'Information (singulier)",
    ),
    (
        re.compile(r"\bBig\s+Datas\b", re.IGNORECASE),
        "Big Datas",
        "Big Data (pas de pluriel)",
    ),
)

_GRAMMAR_RULES_EN: Tuple[Tuple[re.Pattern, str, str], ...] = (
    (
        re.compile(r"\bdatas\b"),
        "datas",
        "data (already plural)",
    ),
)

_GRAMMAR_RULES = {"fr": _GRAMMAR_RULES_FR, "en": _GRAMMAR_RULES_EN}


_FR_INFINITIVE_HEAD = re.compile(
    r"^\s*(?:[•\-–—*]\s*)?"
    r"(?P<verb>[A-Za-zÀ-ÿ]+(?:er|ir|re))\b",
    re.UNICODE,
)
_FR_PAST_PARTICIPLE_HEAD = re.compile(
    r"^\s*(?:[•\-–—*]\s*)?"
    r"(?P<verb>[A-Za-zÀ-ÿ]+(?:é|ée|és|ées|i|ie|is|ies|u|ue|us|ues))\b",
    re.UNICODE,
)
_EN_BASE_VERB_HEAD = re.compile(
    r"^\s*(?:[•\-*]\s*)?(?P<verb>[A-Za-z]+e?)\b",
)
_EN_PAST_VERB_HEAD = re.compile(
    r"^\s*(?:[•\-*]\s*)?(?P<verb>[A-Za-z]+ed)\b",
)

_EN_BASE_VERBS = frozenset(
    {
        "build",
        "drive",
        "lead",
        "manage",
        "review",
        "support",
        "test",
        "track",
        "validate",
        "design",
        "develop",
        "analyze",
        "implement",
        "coordinate",
        "execute",
        "document",
    }
)

_FR_INFINITIVE_EXCEPTIONS = frozenset(
    {
        "faire",
        "être",
        "etre",
        "avoir",
    }
)

_CLAUSE_SPLIT_PATTERN = re.compile(
    r"\s*(?:,|;|\bet\b|\band\b|\bpuis\b|\bthen\b|\n|\u2022|•)\s+",
    re.IGNORECASE,
)


def _split_clauses(text: str) -> List[str]:
    return [
        clause.strip(" -*\t\r\n")
        for clause in _CLAUSE_SPLIT_PATTERN.split(str(text or ""))
        if clause and clause.strip(" -*\t\r\n")
    ]


def detect_cliche_phrases(text: Any, *, language_code: str = "fr") -> List[str]:
    raw = str(text or "").strip()
    if not raw:
        return []
    lang = _normalize_language_code(language_code)
    findings: List[str] = []
    seen: set = set()

    phrase_patterns = _CLICHE_PHRASE_PATTERNS.get(lang, ()) if _CLICHE_PHRASE_PATTERNS else ()
    for pat in phrase_patterns:
        for match in pat.finditer(raw):
            token = match.group(0).strip()
            key = token.lower()
            if key not in seen:
                seen.add(key)
                findings.append(token)

    single_pattern = _CLICHE_PATTERNS.get(lang) if _CLICHE_PATTERNS else None
    if single_pattern is not None:
        for match in single_pattern.finditer(raw):
            token = match.group(0).strip()
            key = token.lower()
            if key not in seen:
                seen.add(key)
                findings.append(token)

    return findings


def detect_tense_mix(
    text: Any,
    *,
    is_past_role: bool,
    language_code: str = "fr",
) -> List[str]:
    """Flag clauses whose head verb uses a tense inconsistent with the role.

    Past role: infinitive heads (FR `Concevoir`) or base-form heads (EN `Design`)
    are inconsistent with past participles (`Conçu`) and should be flagged
    alongside so the user sees the mix.
    """

    raw = str(text or "").strip()
    if not raw:
        return []
    lang = _normalize_language_code(language_code)
    clauses = _split_clauses(raw)
    if len(clauses) < 2:
        return []

    infinitive_heads: List[str] = []
    past_heads: List[str] = []

    for clause in clauses:
        if lang == "fr":
            inf = _FR_INFINITIVE_HEAD.match(clause)
            if inf:
                verb = inf.group("verb")
                if verb.lower() not in _FR_INFINITIVE_EXCEPTIONS:
                    infinitive_heads.append(verb)
                    continue
            pp = _FR_PAST_PARTICIPLE_HEAD.match(clause)
            if pp:
                past_heads.append(pp.group("verb"))
        else:
            base = _EN_BASE_VERB_HEAD.match(clause)
            base_verb = base.group("verb").lower() if base else ""
            past = _EN_PAST_VERB_HEAD.match(clause)
            if past:
                past_heads.append(past.group("verb"))
            elif base_verb in _EN_BASE_VERBS:
                infinitive_heads.append(base.group("verb"))

    if infinitive_heads and past_heads:
        sample = infinitive_heads[:2] + past_heads[:2]
        return sample
    return []


_LEADING_DASH_COLON_LOWER = re.compile(
    r"^\s*[-–—]\s+[^:\n]{1,80}:\s+[a-zà-ÿ]",
    re.UNICODE,
)
_INNER_DASH_CAPITAL = re.compile(
    r"[^:\n]{4,80}\s[-–—]\s+[A-ZÀ-Ÿ]",
    re.UNICODE,
)


def detect_punctuation_mix(text: Any) -> List[str]:
    """Flag a bullet that mixes `- foo: bar` (lowercase after colon) with
    `- X - Bar` (capital after inner dash) — conflicting conventions inside
    the same line suggest inconsistent styling.
    """

    raw = str(text or "").strip()
    if not raw:
        return []
    lines = [ln.strip() for ln in re.split(r"[\r\n]+", raw) if ln.strip()]
    if not lines:
        return []

    has_colon_lower = any(_LEADING_DASH_COLON_LOWER.search(line) for line in lines)
    has_inner_dash_capital = any(_INNER_DASH_CAPITAL.search(line) for line in lines)

    if has_colon_lower and has_inner_dash_capital:
        return ["style-inconsistent"]
    return []


def detect_grammar_issues(text: Any, *, language_code: str = "fr") -> List[Dict[str, str]]:
    """Return list of {'found', 'suggestion'} dicts for known bad patterns.

    Narrow literal matches — NO general spellcheck (risk of false positives on
    proper nouns, acronyms, multilingual terms). Extend by adding explicit
    rules to `_GRAMMAR_RULES_FR` / `_GRAMMAR_RULES_EN`.
    """

    raw = str(text or "").strip()
    if not raw:
        return []
    lang = _normalize_language_code(language_code)
    rules = _GRAMMAR_RULES.get(lang, ())
    findings: List[Dict[str, str]] = []
    seen: set = set()
    for pattern, label, suggestion in rules:
        if not pattern.search(raw):
            continue
        key = (label.lower(), suggestion.lower())
        if key in seen:
            continue
        seen.add(key)
        findings.append({"found": label, "suggestion": suggestion})
    return findings


def build_quality_warnings(
    text: Any,
    *,
    is_past_role: bool = False,
    language_code: str = "fr",
    include_grammar: bool = True,
    include_cliches: bool = True,
    include_tense: bool = True,
    include_punct: bool = True,
) -> List[str]:
    """Aggregate permissive warnings for a single text field."""

    warnings: List[str] = []

    if include_cliches:
        cliches = detect_cliche_phrases(text, language_code=language_code)
        if cliches:
            sample = ", ".join(f"« {c} »" for c in cliches[:2])
            warnings.append(f"Clichés à remplacer par du concret: {sample}.")

    if include_tense and is_past_role:
        mixed = detect_tense_mix(
            text,
            is_past_role=True,
            language_code=language_code,
        )
        if mixed:
            warnings.append(
                "Temps verbaux mélangés dans un poste passé — harmonisez au passé."
            )

    if include_punct:
        mix = detect_punctuation_mix(text)
        if mix:
            warnings.append(
                "Ponctuation mélangée: uniformisez « - Texte » OU « : texte »."
            )

    if include_grammar:
        grammar = detect_grammar_issues(text, language_code=language_code)
        if grammar:
            hints = "; ".join(
                f"« {g['found']} » → {g['suggestion']}" for g in grammar[:2]
            )
            warnings.append(f"Orthographe: {hints}.")

    return warnings


def format_warnings(warnings: Iterable[str]) -> str:
    items = [str(w).strip() for w in warnings if str(w or "").strip()]
    if not items:
        return ""
    return "⚠️ " + " ".join(items)
