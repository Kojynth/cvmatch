"""Helpers to recover a robust skills section from profile data."""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, Iterable, List

from .cv_offer_term_routing import route_term_to_section
from .cv_skill_ranking import rank_skill_blocks_by_relevance
from .keyword_alignment import normalize_keyword_for_match

_GENERIC_SKILL_LABELS = {
    "skill",
    "skills",
    "competence",
    "competences",
    "technical skill",
    "technical skills",
    "soft skill",
    "soft skills",
    "tool",
    "tools",
    "technology",
    "technologies",
}

_ROLE_LIKE_SKILL_TOKENS = {
    "ingenieur",
    "engineer",
    "developpeur",
    "developer",
    "consultant",
    "manager",
    "architecte",
    "architect",
    "analyste",
    "analyst",
    "stagiaire",
    "intern",
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


def _normalize_role_text(value: Any) -> str:
    text = str(value or "").strip().casefold()
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^\w]+", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def _clean_skill_candidate(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    cleaned = re.sub(r"\s+", " ", value).strip(" ,;:-")
    if not cleaned or len(cleaned) > 80:
        return ""
    if any(mark in cleaned for mark in ("!", "?", "\n")):
        return ""

    compact = cleaned.strip()
    if "." in compact:
        dotted_tech = bool(
            re.fullmatch(r"(?:[A-Za-z0-9+#]+(?:\.[A-Za-z0-9+#]+)+)", compact)
        )
        if not dotted_tech and (re.search(r"\.\s", compact) or compact.endswith(".")):
            return ""

    norm = normalize_keyword_for_match(cleaned)
    if not norm or norm in _GENERIC_SKILL_LABELS:
        return ""

    role_norm = _normalize_role_text(cleaned)
    tokens = [tok for tok in role_norm.split() if tok]
    if not tokens or len(tokens) > 6:
        return ""
    if len(tokens) <= 3 and all(tok in _ROLE_LIKE_SKILL_TOKENS for tok in tokens):
        return ""
    if route_term_to_section(cleaned) != "skills":
        return ""

    return cleaned


def skills_section_low_signal(skills_section: Any) -> bool:
    if not isinstance(skills_section, list) or not skills_section:
        return True
    valid_items = 0
    for block in skills_section:
        if not isinstance(block, dict):
            continue
        items = block.get("items")
        if not isinstance(items, list):
            continue
        for item in items:
            if _clean_skill_candidate(str(item or "")):
                valid_items += 1
    return valid_items < 2


def _extend_candidates(output: List[str], value: Any) -> None:
    if isinstance(value, str):
        cleaned = _clean_skill_candidate(value)
        if cleaned:
            output.append(cleaned)
        return
    if isinstance(value, list):
        for item in value:
            _extend_candidates(output, item)
        return
    if isinstance(value, dict):
        for key in ("name", "skill", "label", "technology", "tool"):
            _extend_candidates(output, value.get(key))
        return


def build_skill_blocks_from_profile(
    profile_json: Dict[str, Any],
    *,
    offer_terms: Iterable[Any] = (),
    extra_terms: Iterable[Any] = (),
    language_code: str = "fr",
    max_items_per_block: int = 10,
) -> List[Dict[str, Any]]:
    profile = profile_json if isinstance(profile_json, dict) else {}
    technical_candidates: List[str] = []
    soft_candidates: List[str] = []

    for entry in profile.get("skills") or []:
        if isinstance(entry, dict):
            _extend_candidates(technical_candidates, entry.get("name"))
            _extend_candidates(technical_candidates, entry.get("skill"))
            _extend_candidates(technical_candidates, entry.get("items"))
        else:
            _extend_candidates(technical_candidates, entry)

    for entry in profile.get("projects") or []:
        if not isinstance(entry, dict):
            continue
        _extend_candidates(technical_candidates, entry.get("technologies"))
        _extend_candidates(technical_candidates, entry.get("tech_stack"))

    for entry in profile.get("certifications") or []:
        if isinstance(entry, dict):
            _extend_candidates(technical_candidates, entry.get("name"))

    for entry in profile.get("soft_skills") or []:
        if isinstance(entry, dict):
            _extend_candidates(soft_candidates, entry.get("name"))
            _extend_candidates(soft_candidates, entry.get("items"))
        else:
            _extend_candidates(soft_candidates, entry)

    for raw in extra_terms or []:
        cleaned = _clean_skill_candidate(str(raw or ""))
        if cleaned:
            technical_candidates.append(cleaned)

    technical_items = _dedup_preserve(technical_candidates)[
        : max(1, int(max_items_per_block))
    ]
    soft_items = _dedup_preserve(soft_candidates)[
        : max(0, min(6, int(max_items_per_block)))
    ]

    blocks: List[Dict[str, Any]] = []
    if technical_items:
        blocks.append(
            {
                "category": (
                    "Technical Skills"
                    if language_code == "en"
                    else "Competences techniques"
                ),
                "items": technical_items,
            }
        )
    if soft_items:
        blocks.append(
            {
                "category": "Soft Skills" if language_code == "en" else "Qualites",
                "items": soft_items,
            }
        )

    if not blocks:
        return []

    ranked = rank_skill_blocks_by_relevance(blocks, list(offer_terms or []))
    return ranked if ranked else blocks
