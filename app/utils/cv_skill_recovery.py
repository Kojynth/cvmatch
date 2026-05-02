"""Helpers to recover a robust skills section from profile data."""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from .cv_offer_term_routing import route_term_to_section
from .cv_skill_evidence import (
    classify_skill_bucket,
    collect_supported_skill_terms,
    looks_like_noise_skill_term,
    should_keep_skill_term,
    skills_section_has_supported_signal,
)
from .cv_skill_ranking import rank_skill_blocks_by_relevance, score_skill_text_for_offer
from .keyword_alignment import normalize_keyword_for_match, normalized_term_in_probe

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
        split_items = _split_list_like_skill_string(value)
        if split_items:
            added_split = False
            for item in split_items:
                cleaned_item = _clean_skill_candidate(item, profile_json)
                if cleaned_item:
                    output.append(cleaned_item)
                    added_split = True
            if added_split:
                return
        cleaned = _clean_skill_candidate(value, profile_json)
        if cleaned:
            output.append(cleaned)
            return
        return
    if isinstance(value, list):
        for item in value:
            _extend_candidates(output, item, profile_json)
        return
    if isinstance(value, dict):
        for key in ("name", "skill", "label", "technology", "tool"):
            _extend_candidates(output, value.get(key), profile_json)
        return


def _collect_source_probe(profile_json: Dict[str, Any], extra_items: Iterable[Any]) -> str:
    parts: List[str] = []

    def add(value: Any) -> None:
        if isinstance(value, str):
            text = value.strip()
            if text:
                parts.append(text)
            return
        if isinstance(value, list):
            for item in value:
                add(item)
            return
        if isinstance(value, dict):
            for nested in value.values():
                add(nested)

    add(list(extra_items or []))
    for key in (
        "skills",
        "projects",
        "education",
        "certifications",
        "experiences",
        "experience",
    ):
        add((profile_json or {}).get(key))
    return normalize_keyword_for_match(" ".join(parts))


def _collect_source_fragments(profile_json: Dict[str, Any]) -> List[str]:
    fragments: List[str] = []

    def add(value: Any) -> None:
        if isinstance(value, str):
            text = value.strip()
            if text:
                fragments.append(text)
            return
        if isinstance(value, list):
            for item in value:
                add(item)
            return
        if isinstance(value, dict):
            for nested in value.values():
                add(nested)

    for key in (
        "skills",
        "projects",
        "education",
        "certifications",
        "experiences",
        "experience",
    ):
        add((profile_json or {}).get(key))
    return fragments


def _probe_has_any(probe: str, aliases: Iterable[str]) -> bool:
    for alias in aliases or []:
        alias_norm = normalize_keyword_for_match(alias)
        if alias_norm and normalized_term_in_probe(probe, alias_norm):
            return True
    return False


def _source_entry_probe(entry: Any) -> str:
    parts: List[str] = []

    def add(value: Any) -> None:
        if isinstance(value, str):
            text = value.strip()
            if text:
                parts.append(text)
            return
        if isinstance(value, list):
            for item in value:
                add(item)
            return
        if isinstance(value, dict):
            for nested in value.values():
                add(nested)

    add(entry)
    return normalize_keyword_for_match(" ".join(parts))


def _offer_aligned_source_count(
    profile_json: Dict[str, Any],
    offer_terms: Sequence[Any],
) -> int:
    if not isinstance(profile_json, dict) or not offer_terms:
        return 0
    offer_terms_list = list(offer_terms or [])
    count = 0
    seen_entries: set[str] = set()
    for key in ("experiences", "experience", "projects"):
        entries = profile_json.get(key) or []
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            probe = _source_entry_probe(entry)
            if not probe or probe in seen_entries:
                continue
            seen_entries.add(probe)
            if score_skill_text_for_offer(probe, offer_terms_list) >= 5.0:
                count += 1
    return count


def _skill_block_offer_score(block: Dict[str, Any], offer_terms: Sequence[Any]) -> float:
    if not isinstance(block, dict) or not offer_terms:
        return 0.0
    offer_terms_list = list(offer_terms or [])
    scores = [
        score_skill_text_for_offer(item, offer_terms_list)
        for item in (block.get("items") or [])
        if isinstance(item, str) and item.strip()
    ]
    scores = sorted((score for score in scores if score > 0), reverse=True)
    category_score = score_skill_text_for_offer(
        block.get("category") or "",
        offer_terms_list,
    )
    return (
        (scores[0] if scores else 0.0)
        + min(3.0, sum(scores[1:3]) * 0.2)
        + (category_score * 0.35)
    )


def _resolve_skill_block_limit(
    profile_json: Dict[str, Any],
    ordered_blocks: Sequence[Dict[str, Any]],
    offer_terms: Sequence[Any],
) -> int:
    if len(ordered_blocks or []) <= 4 or not offer_terms:
        return 4
    if _offer_aligned_source_count(profile_json, offer_terms) < 2:
        return 4
    fifth_block = ordered_blocks[4]
    if _skill_block_offer_score(fifth_block, offer_terms) <= 0:
        return 4
    return 5


def _localized_skill_label(labels: Tuple[str, str], language_code: str) -> str:
    return labels[1] if str(language_code or "").startswith("en") else labels[0]


_DIRECT_USE_MARKERS = (
    "automated test",
    "automates tests",
    "automatise",
    "automatiser",
    "developed tests",
    "developpe des tests",
    "implemented tests",
    "implemente des tests",
    "script",
    "suite de test",
    "test suite",
    "tests automatises",
    "utilise",
    "utiliser",
    "using",
    "used",
)
_BENCHMARK_CONTEXT_MARKERS = (
    "benchmark",
    "benchmarke",
    "benchmarker",
    "compare",
    "comparatif",
    "evaluation",
    "evaluer",
    "explore",
    "exploration",
)
_AUTOMATION_BENCHMARK_TOOL_SPECS: Tuple[Tuple[Tuple[str, str], Tuple[str, ...]], ...] = (
    (("Playwright", "Playwright"), ("playwright",)),
    (("Cypress", "Cypress"), ("cypress",)),
    (("Selenium", "Selenium"), ("selenium",)),
    (("Agilitest", "Agilitest"), ("agilitest",)),
)


def _tool_has_context(
    source_fragments: Sequence[str],
    tool_aliases: Iterable[str],
    markers: Iterable[str],
) -> bool:
    for fragment in source_fragments:
        fragment_norm = normalize_keyword_for_match(fragment)
        if not fragment_norm:
            continue
        if not _probe_has_any(fragment_norm, tool_aliases):
            continue
        if _probe_has_any(fragment_norm, markers):
            return True
    return False


def _benchmark_only_tool_labels(
    profile_json: Dict[str, Any],
    *,
    language_code: str = "fr",
) -> List[str]:
    profile_probe = _collect_source_probe(profile_json, ())
    source_fragments = _collect_source_fragments(profile_json)
    explicit_skill_probe = _collect_source_probe(
        {"skills": (profile_json or {}).get("skills") or []},
        (),
    )

    def profile_has(*aliases: str) -> bool:
        return _probe_has_any(profile_probe, aliases)

    def explicit_skill_has(*aliases: str) -> bool:
        return _probe_has_any(explicit_skill_probe, aliases)

    labels: List[str] = []
    for localized_labels, aliases in _AUTOMATION_BENCHMARK_TOOL_SPECS:
        if not profile_has(*aliases):
            continue
        if explicit_skill_has(*aliases):
            continue
        if _tool_has_context(source_fragments, aliases, _DIRECT_USE_MARKERS):
            continue
        if _tool_has_context(source_fragments, aliases, _BENCHMARK_CONTEXT_MARKERS):
            labels.append(_localized_skill_label(localized_labels, language_code))
    return labels


def skills_section_claims_benchmark_only_tools(
    skills_section: Any,
    profile_json: Dict[str, Any],
    *,
    language_code: str = "fr",
) -> bool:
    """Detect direct tool claims when the profile only supports benchmark context."""

    if not isinstance(skills_section, list):
        return False
    benchmark_only = _benchmark_only_tool_labels(
        profile_json,
        language_code=language_code,
    )
    if not benchmark_only:
        return False
    benchmark_norms = {
        normalize_keyword_for_match(label)
        for label in benchmark_only
        if normalize_keyword_for_match(label)
    }
    for block in skills_section:
        if not isinstance(block, dict):
            continue
        for item in block.get("items") or []:
            item_norm = normalize_keyword_for_match(item)
            if not item_norm or item_norm.startswith("benchmark "):
                continue
            if item_norm in benchmark_norms or any(
                normalized_term_in_probe(item_norm, tool_norm)
                for tool_norm in benchmark_norms
            ):
                return True
    return False


def _build_themed_skill_blocks(
    profile_json: Dict[str, Any],
    technical_items: List[str],
    *,
    offer_terms: Iterable[Any],
    language_code: str,
    max_items_per_block: int,
) -> List[Dict[str, Any]]:
    """Specialized skill grouping is authored by the LLM, not fallback code."""
    return []


def _collapse_benchmark_only_tool_claims(
    technical_items: List[str],
    profile_json: Dict[str, Any],
    *,
    language_code: str,
) -> List[str]:
    benchmark_only = _benchmark_only_tool_labels(
        profile_json,
        language_code=language_code,
    )
    if not benchmark_only:
        return technical_items

    benchmark_norms = {
        normalize_keyword_for_match(label)
        for label in benchmark_only
        if normalize_keyword_for_match(label)
    }
    benchmark_label = f"Benchmark {' / '.join(benchmark_only)}"
    benchmark_label_norm = normalize_keyword_for_match(benchmark_label)
    cleaned_items: List[str] = []
    collapsed = False

    for item in technical_items:
        item_norm = normalize_keyword_for_match(item)
        if not item_norm:
            continue
        if item_norm == benchmark_label_norm:
            cleaned_items.append(item)
            collapsed = True
            continue
        if item_norm in benchmark_norms or any(
            normalized_term_in_probe(item_norm, tool_norm)
            for tool_norm in benchmark_norms
        ):
            collapsed = True
            continue
        if "benchmark" in item_norm and not any(
            normalized_term_in_probe(tool_norm, item_norm)
            for tool_norm in benchmark_norms
        ):
            collapsed = True
            continue
        cleaned_items.append(item)

    if collapsed and benchmark_label_norm:
        cleaned_items.append(benchmark_label)
    return _dedup_preserve(cleaned_items)


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
    technical_items = _collapse_benchmark_only_tool_claims(
        technical_items,
        profile,
        language_code=language_code,
    )
    soft_items = _dedup_preserve(soft_candidates)

    blocks: List[Dict[str, Any]] = []
    themed_blocks = _build_themed_skill_blocks(
        profile,
        technical_items,
        offer_terms=offer_terms,
        language_code=language_code,
        max_items_per_block=max_items_per_block,
    )
    if themed_blocks:
        blocks.extend(themed_blocks)
    elif technical_items:
        blocks.append(
            {
                "category": "Skills" if language_code == "en" else "Compétences",
                "items": technical_items,
            }
        )
    if soft_items:
        blocks.append(
            {
                "category": "Soft Skills" if language_code == "en" else "Qualités",
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

    offer_terms_list = list(offer_terms or [])
    ranked = rank_skill_blocks_by_relevance(blocks, offer_terms_list)
    ordered_blocks = ranked if ranked else blocks
    block_limit = _resolve_skill_block_limit(profile, ordered_blocks, offer_terms_list)
    selected_blocks = ordered_blocks[:block_limit]

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
