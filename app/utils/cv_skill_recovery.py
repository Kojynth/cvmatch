"""Helpers to recover a robust skills section from profile data."""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, Iterable, List

from .cv_offer_term_routing import route_term_to_section
from .cv_skill_evidence import (
    classify_skill_bucket,
    collect_supported_skill_terms,
    looks_like_noise_skill_term,
    should_keep_skill_term,
    skills_section_has_supported_signal,
)
from .cv_skill_ranking import rank_skill_blocks_by_relevance
from .keyword_alignment import normalize_keyword_for_match

try:
    from ..domain.generation.tool_signals import collect_named_tool_hints
except Exception:
    collect_named_tool_hints = None

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


def _clean_skill_candidate(
    value: Any,
    profile_json: Dict[str, Any] | None = None,
) -> str:
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
    if looks_like_noise_skill_term(cleaned):
        return ""

    role_norm = _normalize_role_text(cleaned)
    tokens = [tok for tok in role_norm.split() if tok]
    if not tokens or len(tokens) > 6:
        return ""
    if len(tokens) <= 3 and all(tok in _ROLE_LIKE_SKILL_TOKENS for tok in tokens):
        return ""
    if not should_keep_skill_term(cleaned, profile_json):
        return ""

    return cleaned


def _split_list_like_skill_string(value: str) -> List[str]:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text:
        return []
    if not re.search(r"[,;|·•\n]", str(value or "")):
        return []
    return [
        item.strip(" ,;:.-")
        for item in re.split(r"\s*(?:,|;|\||·|•|\n)\s*", str(value or ""))
        if item.strip(" ,;:.-")
    ]


def skills_section_low_signal(
    skills_section: Any,
    profile_json: Dict[str, Any] | None = None,
) -> bool:
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
    if valid_items < 2:
        return True
    if isinstance(profile_json, dict) and profile_json:
        supported, plausible, hard_unsupported = skills_section_has_supported_signal(
            skills_section, profile_json
        )
        if supported + plausible < 2:
            return True
        if hard_unsupported > max(2, supported + plausible):
            return True
    return False


def _extend_candidates(
    output: List[str],
    value: Any,
    profile_json: Dict[str, Any] | None = None,
) -> None:
    if isinstance(value, str):
        cleaned = _clean_skill_candidate(value, profile_json)
        if cleaned:
            output.append(cleaned)
            return
        for item in _split_list_like_skill_string(value):
            cleaned_item = _clean_skill_candidate(item, profile_json)
            if cleaned_item:
                output.append(cleaned_item)
        return
    if isinstance(value, list):
        for item in value:
            _extend_candidates(output, item, profile_json)
        return
    if isinstance(value, dict):
        for key in ("name", "skill", "label", "technology", "tool"):
            _extend_candidates(output, value.get(key), profile_json)
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
            _extend_candidates(technical_candidates, entry.get("name"), profile)
            _extend_candidates(technical_candidates, entry.get("skill"), profile)
            _extend_candidates(technical_candidates, entry.get("items"), profile)
        else:
            _extend_candidates(technical_candidates, entry, profile)

    for entry in profile.get("projects") or []:
        if not isinstance(entry, dict):
            continue
        _extend_candidates(technical_candidates, entry.get("technologies"), profile)
        _extend_candidates(technical_candidates, entry.get("tech_stack"), profile)
        _extend_candidates(technical_candidates, entry.get("skills"), profile)
        _extend_candidates(technical_candidates, entry.get("tools"), profile)

    for entry in profile.get("education") or []:
        if not isinstance(entry, dict):
            continue
        for key in (
            "field_of_study",
            "details",
            "description",
            "courses",
            "modules",
            "specialization",
            "specialisation",
            "skills",
        ):
            _extend_candidates(technical_candidates, entry.get(key), profile)

    for entry in profile.get("certifications") or []:
        if isinstance(entry, dict):
            _extend_candidates(technical_candidates, entry.get("name"), profile)

    for entry in profile.get("soft_skills") or []:
        if isinstance(entry, dict):
            _extend_candidates(soft_candidates, entry.get("name"), profile)
            _extend_candidates(soft_candidates, entry.get("items"), profile)
        else:
            _extend_candidates(soft_candidates, entry, profile)

    if collect_named_tool_hints is not None:
        technical_candidates.extend(collect_named_tool_hints(profile, max_items=24))

    supported_extra_terms = collect_supported_skill_terms(extra_terms, profile)
    technical_candidates.extend(supported_extra_terms.get("technical") or [])
    soft_candidates.extend(supported_extra_terms.get("soft") or [])

    technical_items = _dedup_preserve(technical_candidates)
    soft_items = _dedup_preserve(soft_candidates)

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

    if supported_extra_terms.get("soft"):
        blocks.sort(
            key=lambda block: (
                0
                if classify_skill_bucket(" ".join(block.get("items") or []))
                == "technical"
                else 1
            )
        )

    ranked = rank_skill_blocks_by_relevance(blocks, list(offer_terms or []))
    selected_blocks = ranked if ranked else blocks

    technical_limit = max(1, int(max_items_per_block))
    soft_limit = max(0, min(6, int(max_items_per_block)))
    clamped: List[Dict[str, Any]] = []
    for block in selected_blocks:
        if not isinstance(block, dict):
            continue
        items = [
            item
            for item in (block.get("items") or [])
            if isinstance(item, str) and item.strip()
        ]
        category_norm = normalize_keyword_for_match(block.get("category") or "")
        is_soft_block = category_norm in {
            "soft skills",
            "soft skill",
            "qualites",
            "qualites personnelles",
            "strengths",
        }
        limit = soft_limit if is_soft_block else technical_limit
        if limit <= 0:
            continue
        next_block = dict(block)
        next_block["items"] = items[:limit]
        if next_block["items"]:
            clamped.append(next_block)

    return clamped if clamped else selected_blocks
