"""Helpers for controlled chunking and block selection."""

from __future__ import annotations

import re
from typing import Iterable, List, Optional


TAG_RE = re.compile(r"<[^>]+>")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _normalize_text(text: str) -> str:
    return (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def strip_html(text: str) -> str:
    return TAG_RE.sub(" ", text or "")


def split_text_blocks(
    text: str,
    *,
    max_block_chars: int,
    max_blocks: Optional[int] = None,
) -> List[str]:
    normalized = _normalize_text(text)
    if not normalized:
        return []

    paragraphs = [p.strip() for p in normalized.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [normalized]

    blocks: List[str] = []
    current: List[str] = []
    current_len = 0

    def flush() -> None:
        nonlocal current, current_len
        if current:
            blocks.append("\n\n".join(current).strip())
            current = []
            current_len = 0

    def add_piece(piece: str) -> None:
        nonlocal current_len
        piece = piece.strip()
        if not piece:
            return
        piece_len = len(piece)
        if piece_len > max_block_chars:
            _split_long_piece(piece)
            return
        if current_len + piece_len + (2 if current else 0) > max_block_chars:
            flush()
        current.append(piece)
        current_len += piece_len + (2 if current_len else 0)

    def _split_long_piece(piece: str) -> None:
        parts = SENTENCE_SPLIT_RE.split(piece)
        if len(parts) == 1:
            for idx in range(0, len(piece), max_block_chars):
                add_piece(piece[idx : idx + max_block_chars])
            return
        for part in parts:
            if part.strip():
                add_piece(part.strip())

    for paragraph in paragraphs:
        add_piece(paragraph)

    flush()

    if max_blocks and len(blocks) > max_blocks:
        head = max_blocks // 2
        tail = max_blocks - head
        blocks = blocks[:head] + blocks[-tail:]

    return [block for block in blocks if block]


def merge_blocks(
    blocks: Iterable[str],
    *,
    max_chars: int,
    separator: str = "\n\n",
) -> str:
    if max_chars <= 0:
        return ""
    merged: List[str] = []
    total = 0
    for block in blocks:
        piece = (block or "").strip()
        if not piece:
            continue
        piece_len = len(piece) + (len(separator) if merged else 0)
        if total + piece_len > max_chars and merged:
            break
        merged.append(piece)
        total += piece_len
    return separator.join(merged).strip()


def select_relevant_blocks(
    text: str,
    *,
    max_chars: int,
    keywords: Optional[Iterable[str]] = None,
    max_block_chars: int = 900,
    max_blocks: Optional[int] = None,
    strip_html_tags: bool = False,
) -> str:
    normalized = _normalize_text(text)
    if not normalized:
        return ""

    blocks = split_text_blocks(
        normalized, max_block_chars=max_block_chars, max_blocks=max_blocks
    )
    if not blocks:
        return ""

    keyword_list = [k.strip().lower() for k in (keywords or []) if k and str(k).strip()]

    if not keyword_list:
        return merge_blocks(blocks, max_chars=max_chars)

    scored = []
    for idx, block in enumerate(blocks):
        haystack = strip_html(block) if strip_html_tags else block
        haystack = haystack.lower()
        score = sum(1 for kw in keyword_list if kw in haystack)
        scored.append((score, idx, block))

    scored.sort(key=lambda item: (-item[0], item[1]))

    selected = []
    total = 0
    for score, idx, block in scored:
        if total >= max_chars:
            break
        if not block:
            continue
        block_len = len(block) + (2 if selected else 0)
        if selected and total + block_len > max_chars:
            continue
        selected.append((idx, block))
        total += block_len

    if not selected:
        return merge_blocks(blocks, max_chars=max_chars)

    selected.sort(key=lambda item: item[0])
    merged_blocks = [block for _, block in selected]
    return merge_blocks(merged_blocks, max_chars=max_chars)
