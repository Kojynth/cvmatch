"""Offer-aware ordering helpers for CV skill blocks."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .keyword_alignment import normalize_keyword_for_match, normalized_term_in_probe


def _normalized_terms(terms: List[Any]) -> List[str]:
    normalized: List[str] = []
    seen: set[str] = set()
    for term in terms:
        text = normalize_keyword_for_match(str(term or ""))
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def _score_skill_item(item_text: str, offer_terms: List[str]) -> float:
    item_norm = normalize_keyword_for_match(item_text)
    if not item_norm:
        return 0.0

    item_tokens = {token for token in item_norm.split() if token}
    score = 0.0
    total_terms = max(1, len(offer_terms))
    strong_ai_offer_markers = (
        "ai",
        "ia",
        "ml",
        "llm",
        "machine learning",
        "intelligence artificielle",
    )
    ai_offer_context = any(
        _norm_contains_marker(term_norm, marker)
        for term_norm in offer_terms
        for marker in strong_ai_offer_markers
    )

    for idx, term_norm in enumerate(offer_terms):
        priority = max(0.25, 1.0 - (idx / float(total_terms + 1)))
        if item_norm == term_norm:
            score += 8.0 + priority
            continue
        if normalized_term_in_probe(item_norm, term_norm) or normalized_term_in_probe(
            term_norm, item_norm
        ):
            score += 5.0 + priority
            continue

        overlap = len(item_tokens & {token for token in term_norm.split() if token})
        if overlap:
            score += min(3.0, float(overlap)) + priority

        ai_offer_markers = strong_ai_offer_markers + (
            "model",
            "models",
            "modele",
            "modeles",
            "inference",
        )
        ai_profile_markers = (
            "ai",
            "ia",
            "ml",
            "llm",
            "llmops",
            "mlops",
            "machine learning",
            "intelligence artificielle",
            "ia avancee",
            "ia avance",
            "prompt engineering",
            "rag",
            "model",
            "modele",
            "benchmark",
        )
        if (
            ai_offer_context
            and any(
                _norm_contains_marker(term_norm, marker) for marker in ai_offer_markers
            )
        ) and any(
            _norm_contains_marker(item_norm, marker) for marker in ai_profile_markers
        ):
            score += 4.0 + priority

    return score


def score_skill_text_for_offer(item_text: Any, offer_terms: List[Any]) -> float:
    """Score a single skill/category label against normalized offer terms."""

    normalized_offer_terms = _normalized_terms(list(offer_terms or []))
    if not normalized_offer_terms:
        return 0.0
    return _score_skill_item(str(item_text or ""), normalized_offer_terms)


def _norm_contains_marker(norm: str, marker: str) -> bool:
    marker_norm = normalize_keyword_for_match(marker)
    if not norm or not marker_norm:
        return False
    if len(marker_norm) <= 3 and marker_norm.isalnum():
        return marker_norm in {token for token in norm.split() if token}
    return normalized_term_in_probe(norm, marker_norm)


def rank_skill_blocks_by_relevance(
    skill_blocks: List[Dict[str, Any]],
    offer_terms: List[Any],
) -> List[Dict[str, Any]]:
    """Sort skills and skill categories by offer relevance while preserving ties."""
    if not isinstance(skill_blocks, list) or not skill_blocks:
        return skill_blocks

    normalized_offer_terms = _normalized_terms(list(offer_terms or []))
    if not normalized_offer_terms:
        return skill_blocks

    ranked_blocks: List[Tuple[float, int, Dict[str, Any]]] = []

    for block_idx, block in enumerate(skill_blocks):
        if not isinstance(block, dict):
            continue

        items = [
            item
            for item in (block.get("items") or [])
            if isinstance(item, str) and item.strip()
        ]
        ranked_items: List[Tuple[float, int, str]] = []
        for item_idx, item in enumerate(items):
            ranked_items.append(
                (_score_skill_item(item, normalized_offer_terms), item_idx, item)
            )
        ranked_items.sort(key=lambda payload: (-payload[0], payload[1]))

        reordered_block = dict(block)
        reordered_block["items"] = [payload[2] for payload in ranked_items]

        category_score = _score_skill_item(
            str(block.get("category") or ""),
            normalized_offer_terms,
        )
        positive_scores = [score for score, _idx, _item in ranked_items if score > 0]
        block_score = (
            (positive_scores[0] if positive_scores else 0.0)
            + min(3.0, sum(positive_scores[1:3]) * 0.2)
            + (category_score * 0.35)
        )
        ranked_blocks.append((block_score, block_idx, reordered_block))

    ranked_blocks.sort(key=lambda payload: (-payload[0], payload[1]))
    return [payload[2] for payload in ranked_blocks]
