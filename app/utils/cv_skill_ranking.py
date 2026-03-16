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

    for idx, term_norm in enumerate(offer_terms):
        priority = max(0.25, 1.0 - (idx / float(total_terms + 1)))
        if item_norm == term_norm:
            score += 8.0 + priority
            continue
        if normalized_term_in_probe(item_norm, term_norm) or normalized_term_in_probe(term_norm, item_norm):
            score += 5.0 + priority
            continue

        overlap = len(item_tokens & {token for token in term_norm.split() if token})
        if overlap:
            score += min(3.0, float(overlap)) + priority

    return score


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
            item for item in (block.get("items") or [])
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

        block_score = ranked_items[0][0] if ranked_items else 0.0
        ranked_blocks.append((block_score, block_idx, reordered_block))

    ranked_blocks.sort(key=lambda payload: (-payload[0], payload[1]))
    return [payload[2] for payload in ranked_blocks]
