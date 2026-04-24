"""Generic detection of named tool/software/platform signals.

This module centralizes two cross-domain behaviors used by CV generation:

1. Prefer explicit named tools/products/platforms when the profile or the job
   offer contains them.
2. Detect vague tooling formulations ("outils de facturation",
   "automation tools", "CRM software") so prompts can rewrite them into more
   specific wording when source evidence exists.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable, List

_EXPLICIT_TOOL_KEYS = frozenset(
    {
        "tool",
        "tools",
        "technology",
        "technologies",
        "tech_stack",
        "stack",
        "framework",
        "frameworks",
        "software",
        "softwares",
        "platform",
        "platforms",
        "system",
        "systems",
        "suite",
        "suites",
        "application",
        "applications",
        "environment",
        "environments",
        "products",
        "product",
    }
)

_TEXTUAL_TOOL_KEYS = frozenset(
    {
        "skills",
        "skills_list",
        "items",
        "summary",
        "description",
        "highlights",
        "responsibilities",
        "achievements",
        "details",
        "content",
        "projects",
        "project",
        "experiences",
        "experience",
        "work",
    }
)

_LISTLIKE_TOOL_KEYS = frozenset(
    {
        "skills",
        "skills_list",
        "items",
    }
)

_RECURSIVE_TOOL_KEYS = _EXPLICIT_TOOL_KEYS | _TEXTUAL_TOOL_KEYS

_GENERIC_TOOL_WORDS = frozenset(
    {
        "api",
        "apis",
        "application",
        "applications",
        "automation",
        "automatisation",
        "billing",
        "bi",
        "cloud",
        "crm",
        "erp",
        "facturation",
        "framework",
        "frameworks",
        "logiciel",
        "logiciels",
        "model",
        "models",
        "outillage",
        "outil",
        "outils",
        "platform",
        "platforms",
        "plateforme",
        "plateformes",
        "qa",
        "reporting",
        "software",
        "solution",
        "solutions",
        "stack",
        "suite",
        "suites",
        "system",
        "systems",
        "systeme",
        "systemes",
        "tech",
        "testing",
        "tests",
        "tool",
        "tools",
    }
)

_LOW_SIGNAL_LOWERCASE_WORDS = _GENERIC_TOOL_WORDS | frozenset(
    {
        "about",
        "advanced",
        "analysis",
        "analyse",
        "assurance",
        "based",
        "campaign",
        "candidate",
        "collaboration",
        "communication",
        "company",
        "content",
        "coordination",
        "delivery",
        "details",
        "domain",
        "experience",
        "general",
        "gestion",
        "highlight",
        "highlights",
        "improvement",
        "items",
        "join",
        "knowledge",
        "leadership",
        "management",
        "method",
        "methodology",
        "mission",
        "missions",
        "niveau",
        "offer",
        "operations",
        "our",
        "process",
        "processes",
        "product",
        "products",
        "project",
        "projects",
        "profile",
        "profil",
        "quality",
        "reporting",
        "requirements",
        "responsibilities",
        "role",
        "skills",
        "summary",
        "support",
        "target",
        "teamwork",
        "technical",
        "what",
        "workflow",
        "workflows",
        "you",
    }
)

_TITLECASE_BLOCKLIST = frozenset(
    {
        "about",
        "candidate",
        "company",
        "current",
        "experience",
        "ideal",
        "join",
        "mission",
        "missions",
        "offer",
        "our",
        "poste",
        "profile",
        "profil",
        "requirements",
        "responsibilities",
        "role",
        "skills",
        "summary",
        "target",
        "what",
        "you",
    }
)

_TOOL_CONTEXT_PATTERNS = (
    re.compile(
        r"\b(?:outils?|tools?|logiciels?|software|frameworks?|plateformes?|platforms?|"
        r"syst[eè]mes?|systems?|suites?|stack|technologies?|applications?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:ma[iî]trise de|utilisation de|usage de|benchmark(?:s|ing)? de|"
        r"comparatif de|exp[eé]rience avec|connaissance de|stack(?: technique)?|"
        r"built with|used|using|experience with|knowledge of|proficient in|"
        r"worked with|implemented with|benchmark(?:s|ing)?(?: on| of)?|"
        r"comparison of)\b",
        re.IGNORECASE,
    ),
)

_VAGUE_TOOL_PATTERNS = (
    re.compile(
        r"\b(?:outils?|tools?|logiciels?|software|frameworks?|plateformes?|platforms?|"
        r"syst[eè]mes?|systems?|suites?)\s+(?:d['’]|de|des|for|of)\s+"
        r"(?!and\b|et\b|or\b|ou\b)"
        r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9+.#/-]*"
        r"(?:\s+(?!and\b|et\b|or\b|ou\b)[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9+.#/-]*){0,2}\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:automation|automatisation|billing|facturation|ticketing|reporting|"
        r"testing|qa|crm|erp|bi|analytics|analyse|analysis)\s+"
        r"(?:tools?|software|frameworks?|platforms?|systems?|suites?)\b",
        re.IGNORECASE,
    ),
)

_LEADING_CONTEXT_PATTERNS = (
    re.compile(
        r"^(?:benchmark(?:s|ing)?|comparatif|[ée]valuation|evaluation|usage|utilisation|"
        r"ma[iî]trise|expertise|connaissance|mise en place|gestion|suivi|"
        r"implemented|implementing|used|using|tested|testing|validated|validating|"
        r"benchmarked|benchmarking|configured|configuring|deployed|deploying|"
        r"developed|developing|created|creating|built|building|"
        r"d[eé]ploiement|impl[eé]mentation|developpement|d[eé]veloppement|"
        r"cr[eé]ation|creation|use|using|experience|knowledge|proficiency)"
        r"\s+(?:d['’]|de|des|of|with|en|sur)?\s*",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:outils?|tools?|logiciels?|software|frameworks?|plateformes?|platforms?|"
        r"syst[eè]mes?|systems?|suites?|stack|technologies?)\s*(?::|-)?\s*",
        re.IGNORECASE,
    ),
)

_TRAILING_CONTEXT_PATTERNS = (
    re.compile(
        r"\s+(?:or similar(?: platforms?| tools?)?|ou [ée]quivalent(?:s)?|"
        r"similaire(?:s)?|etc\.?|is a plus|nice to have|preferred|required|"
        r"est un plus|serait un plus)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"\s+(?:for|pour)\s+[a-zà-ÿ][a-zà-ÿ0-9\s/-]{1,40}$",
        re.IGNORECASE,
    ),
)

_CONTEXT_CAPTURE_PATTERNS = (
    re.compile(
        r"\b(?:proficient in|experience with|knowledge of|worked with|built with|"
        r"using|used|use of|ma[iî]trise de|utilisation de|usage de|"
        r"benchmark(?:s|ing)?(?: on| of| de)?|comparatif de)\s+((?:(?!\.\s|;\s|\n).)+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:such as|like|including|incluant|comme|notamment)\s+((?:(?!\.\s|;\s|\n).)+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:implemented|tested|validated|built|created|configured|used|using|"
        r"developed|con[cç]u|construit|utilis[eé]|mis en place)\b"
        r"(?:(?!\.\s|;\s|\n).){0,40}\b(?:with|avec)\s+((?:(?!\.\s|;\s|\n).)+)",
        re.IGNORECASE,
    ),
)


def _normalize(text: Any) -> str:
    value = unicodedata.normalize("NFKD", str(text or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
    return re.sub(r"\s+", " ", value)


def _has_tool_context(text: str) -> bool:
    candidate = str(text or "")
    return any(pattern.search(candidate) for pattern in _TOOL_CONTEXT_PATTERNS)


def _is_acronym(token: str) -> bool:
    return bool(re.fullmatch(r"[A-Z]{2,10}", token))


def _is_titlecaseish(token: str) -> bool:
    return bool(re.fullmatch(r"[A-Z][A-Za-z0-9#+./-]{1,30}", token))


def _clean_fragment(text: str) -> str:
    value = str(text or "").strip(" -•\t\r\n")
    if not value:
        return ""
    for pattern in _LEADING_CONTEXT_PATTERNS:
        value = pattern.sub("", value).strip()
    for pattern in _TRAILING_CONTEXT_PATTERNS:
        value = pattern.sub("", value).strip()
    value = re.sub(
        r"^(?:d['’]|de|des|of|for)\s+[a-zà-ÿ-]+(?:\s+[a-zà-ÿ-]+){0,2}\s*:\s*",
        "",
        value,
        flags=re.IGNORECASE,
    )
    value = value.strip(" ,;:()[]{}.!?")
    value = re.sub(r"\s+", " ", value)
    return value


def _clean_vague_phrase(text: str) -> str:
    value = str(text or "").strip(" -•\t\r\n")
    if not value:
        return ""
    value = value.strip(" ,;:()[]{}.!?")
    value = re.sub(r"\s+", " ", value)
    return value


def _split_fragments(text: str, *, explicit_context: bool) -> List[str]:
    raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    if not raw.strip():
        return []

    seeds: List[str] = [raw]
    if ":" in raw:
        left, right = raw.split(":", 1)
        if explicit_context or _has_tool_context(left):
            seeds.append(right)

    for match in re.finditer(r"\(([^()]{2,120})\)", raw):
        inner = str(match.group(1) or "").strip()
        if inner and (explicit_context or _has_tool_context(raw) or "," in inner):
            seeds.append(inner)

    out: List[str] = []
    for seed in seeds:
        for block in re.split(r"[\n;|]+", seed):
            block = str(block or "").strip()
            if not block:
                continue
            block_context = explicit_context or _has_tool_context(block)
            parts = re.split(r",", block) if (block_context or "," in block) else [block]
            for part in parts:
                for piece in re.split(r"\s+(?:and|et|or|ou)\s+", part):
                    cleaned = _clean_fragment(piece)
                    if cleaned:
                        out.append(cleaned)
    return out


def _looks_like_named_tool(text: str, *, explicit_context: bool) -> bool:
    raw = str(text or "").strip()
    if not raw or len(raw) > 48:
        return False
    if len(raw.split()) > 4:
        return False
    if re.search(r"[.!?]\s", raw):
        return False

    normalized = _normalize(raw)
    if not normalized or any(pattern.search(raw) for pattern in _VAGUE_TOOL_PATTERNS):
        return False
    if normalized in _LOW_SIGNAL_LOWERCASE_WORDS:
        return False

    words = raw.split()
    normalized_words = [_normalize(word) for word in words if _normalize(word)]
    if normalized_words and all(word in _GENERIC_TOOL_WORDS for word in normalized_words):
        return False
    if normalized_words and normalized_words[0] in _TITLECASE_BLOCKLIST and len(normalized_words) == 1:
        return False

    if re.fullmatch(r"[A-Z]{2,10}(?:\s+[A-Z0-9]{2,10}){0,2}", raw):
        return True
    if (
        re.search(r"[A-Za-z0-9][+#/][A-Za-z0-9]", raw)
        or re.search(r"[A-Za-z0-9]\.[A-Za-z0-9]", raw)
        or any(ch.isdigit() for ch in raw)
    ):
        return True
    if re.search(r"\b[A-Z][a-z]+[A-Z][A-Za-z0-9#+./-]*\b", raw):
        return True

    if explicit_context and 1 <= len(words) <= 3:
        if all(_is_titlecaseish(token) or _is_acronym(token) for token in words):
            return True
        if all(re.fullmatch(r"[a-z0-9][a-z0-9#+./-]{1,30}", token) for token in words):
            return not any(word in _LOW_SIGNAL_LOWERCASE_WORDS for word in normalized_words)

    return False


def _looks_like_list_item_tool(text: str) -> bool:
    raw = str(text or "").strip()
    normalized = _normalize(raw)
    if not raw or not normalized or normalized in _LOW_SIGNAL_LOWERCASE_WORDS:
        return False

    words = raw.split()
    if len(words) == 1:
        return _is_titlecaseish(raw) or _is_acronym(raw)
    if 1 < len(words) <= 3:
        return any(_is_acronym(token) for token in words) and all(
            _is_titlecaseish(token) or _is_acronym(token) for token in words
        )
    return False


def _iter_contextual_chunks(text: str) -> Iterable[str]:
    candidate = str(text or "")
    for pattern in _CONTEXT_CAPTURE_PATTERNS:
        for match in pattern.finditer(candidate):
            cleaned = _clean_fragment(match.group(1))
            if cleaned:
                yield cleaned


def extract_named_tool_hints_from_text(
    text: str,
    *,
    explicit_context: bool = False,
    listlike_context: bool = False,
    max_items: int = 12,
) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    text_context = explicit_context or _has_tool_context(text)
    fragments = _split_fragments(text, explicit_context=text_context)
    if text_context:
        for chunk in _iter_contextual_chunks(text):
            fragments.extend(_split_fragments(chunk, explicit_context=True))
    for fragment in fragments:
        if not _looks_like_named_tool(fragment, explicit_context=text_context):
            if not (listlike_context and _looks_like_list_item_tool(fragment)):
                continue
        key = _normalize(fragment)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(fragment)
        if len(out) >= max(1, int(max_items or 1)):
            break
    return out


def collect_named_tool_hints(value: Any, *, max_items: int = 8) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()

    def add(item: Any, *, explicit_context: bool = False, key_hint: str = "") -> None:
        if len(out) >= max(1, int(max_items or 1)):
            return
        if item is None:
            return
        if isinstance(item, str):
            normalized_key = _normalize(key_hint)
            if not (explicit_context or normalized_key in _RECURSIVE_TOOL_KEYS):
                return
            contextual = explicit_context or normalized_key in _EXPLICIT_TOOL_KEYS
            listlike_context = normalized_key in _LISTLIKE_TOOL_KEYS
            for candidate in extract_named_tool_hints_from_text(
                item,
                explicit_context=contextual,
                listlike_context=listlike_context,
                max_items=max_items,
            ):
                key = _normalize(candidate)
                if not key or key in seen:
                    continue
                seen.add(key)
                out.append(candidate)
                if len(out) >= max(1, int(max_items or 1)):
                    break
            return
        if isinstance(item, list):
            for child in item:
                add(child, explicit_context=explicit_context, key_hint=key_hint)
                if len(out) >= max(1, int(max_items or 1)):
                    break
            return
        if isinstance(item, dict):
            for key, child in item.items():
                normalized_key = _normalize(key)
                if not (explicit_context or normalized_key in _RECURSIVE_TOOL_KEYS):
                    continue
                add(
                    child,
                    explicit_context=explicit_context or normalized_key in _EXPLICIT_TOOL_KEYS,
                    key_hint=str(key or ""),
                )
                if len(out) >= max(1, int(max_items or 1)):
                    break

    add(value)
    return out[: max(1, int(max_items or 1))]


def find_vague_tool_phrases(value: Any, *, max_items: int = 8) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()

    def visit(item: Any, *, key_hint: str = "") -> None:
        if len(out) >= max(1, int(max_items or 1)):
            return
        if item is None:
            return
        if isinstance(item, str):
            normalized_key = _normalize(key_hint)
            if key_hint and normalized_key not in _RECURSIVE_TOOL_KEYS:
                return
            for pattern in _VAGUE_TOOL_PATTERNS:
                for match in pattern.finditer(item):
                    phrase = _clean_vague_phrase(match.group(0))
                    key = _normalize(phrase)
                    if not phrase or not key or key in seen:
                        continue
                    seen.add(key)
                    out.append(phrase)
                    if len(out) >= max(1, int(max_items or 1)):
                        return
            return
        if isinstance(item, list):
            for child in item:
                visit(child, key_hint=key_hint)
                if len(out) >= max(1, int(max_items or 1)):
                    return
            return
        if isinstance(item, dict):
            for key, child in item.items():
                normalized_key = _normalize(key)
                if key_hint and normalized_key not in _RECURSIVE_TOOL_KEYS:
                    continue
                visit(child, key_hint=str(key or ""))
                if len(out) >= max(1, int(max_items or 1)):
                    return

    visit(value)
    return out[: max(1, int(max_items or 1))]


__all__ = [
    "collect_named_tool_hints",
    "extract_named_tool_hints_from_text",
    "find_vague_tool_phrases",
]
