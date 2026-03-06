"""Narrative text quality helpers for generated CV content."""

from __future__ import annotations

import re
from typing import List


def _normalize_for_match(text: str) -> str:
    lowered = (text or "").strip().lower()
    lowered = re.sub(r"\s+", " ", lowered)
    lowered = re.sub(r"[^a-z0-9à-ÿ ]+", "", lowered)
    return lowered.strip()


def _dedupe_overlapping_blocks(text: str) -> str:
    blocks = [part.strip() for part in re.split(r"(?:\r?\n)+", text or "") if part.strip()]
    if len(blocks) <= 1:
        return text.strip()

    kept: List[str] = []
    kept_norms: List[str] = []

    for block in blocks:
        norm = _normalize_for_match(block)
        if not norm:
            continue
        if kept_norms and norm == kept_norms[-1]:
            continue

        # If the new block fully contains the previous block (common LLM repetition),
        # keep only the richer block.
        if kept_norms and len(kept_norms[-1]) >= 60 and norm.startswith(kept_norms[-1]):
            kept[-1] = block
            kept_norms[-1] = norm
            continue

        # If the previous block contains this one, ignore this shorter duplicate.
        if kept_norms and len(norm) >= 60 and kept_norms[-1].startswith(norm):
            continue

        kept.append(block)
        kept_norms.append(norm)

    return "\n".join(kept).strip()


def _split_sentences(text: str) -> List[str]:
    if not text:
        return []
    chunks = re.split(r"(?<=[.!?])\s+", text.strip())
    output: List[str] = []
    for chunk in chunks:
        item = chunk.strip()
        if item:
            output.append(item)
    return output


def dedupe_sentences(text: str) -> str:
    sentences = _split_sentences(text)
    if len(sentences) <= 1:
        return text.strip()

    kept: List[str] = []
    seen = set()
    for sentence in sentences:
        norm = _normalize_for_match(sentence)
        if not norm:
            continue
        if norm in seen:
            continue
        if kept and norm == _normalize_for_match(kept[-1]):
            continue
        seen.add(norm)
        kept.append(sentence.strip())

    return " ".join(kept).strip()


def clean_narrative_text(text: str) -> str:
    """Remove common repetition artifacts while preserving meaning."""
    if not text:
        return ""
    cleaned = str(text or "").strip()
    cleaned = _dedupe_overlapping_blocks(cleaned)
    cleaned = dedupe_sentences(cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()
