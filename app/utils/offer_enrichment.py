"""
Offer Enrichment Module

Centralized offer keyword collection, merging, and enrichment logic.
This module extracts offer-related keyword processing from CVGenerationWorker
to provide reusable functions for offer analysis enrichment.

Key features:
- Offer keyword collection from multiple sources (analysis, LLM extraction)
- Keyword merging into offer analysis
- ATS keyword filtering and deduplication
- Lexical term extraction for keyword families
- Required term selection for CV alignment

These functions operate on offer_data dictionaries and do not depend on
any worker state, making them suitable for both in-process and subprocess
pipeline stages.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Callable, Dict, List, Optional, Set

try:
    from ..logging.safe_logger import get_safe_logger
    from ..config import DEFAULT_PII_CONFIG
    logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

# Import from existing utility modules
from .offer_keywords_utils import (
    DEFAULT_ANALYSIS_KEY_FIELDS,
    DEFAULT_OFFER_KEY_FIELDS,
    collect_offer_keywords_from_source,
    dedup_preserve,
    merge_offer_keywords_into_analysis,
)
from .keyword_alignment import (
    normalize_keyword_for_match,
    keyword_tokens,
)


# Stop words for keyword filtering (bilingual FR/EN)
STOP_WORDS_EN = frozenset({
    "the", "and", "for", "with", "from", "that", "this", "your", "you",
    "our", "role", "job", "position", "team", "company", "work", "will",
    "are", "have", "has", "been", "was", "were", "can", "may", "must",
})

STOP_WORDS_FR = frozenset({
    "poste", "offre", "avec", "pour", "dans", "votre", "vous", "nous",
    "notre", "entreprise", "profil", "mission", "des", "les", "une",
    "sur", "par", "est", "sont", "etre", "avoir", "fait", "faire",
})

STOP_WORDS_ALL = STOP_WORDS_EN | STOP_WORDS_FR


def get_offer_keywords_json(
    offer_data: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """
    Retrieve offer keywords JSON from offer analysis.

    The offer keywords JSON is typically stored under:
    offer_data["analysis"]["offer_keywords_llm"]

    Args:
        offer_data: Job offer dictionary

    Returns:
        Offer keywords JSON dict, or None if not available
    """
    if not isinstance(offer_data, dict):
        return None

    analysis = offer_data.get("analysis")
    if not isinstance(analysis, dict):
        return None

    offer_keywords = analysis.get("offer_keywords_llm")
    if isinstance(offer_keywords, dict):
        return offer_keywords

    return None


def collect_offer_keywords(
    offer_data: Optional[Dict[str, Any]],
    *,
    critic_json: Optional[Dict[str, Any]] = None,
    include_job_title: bool = True,
    include_missing_keywords: bool = True,
    max_items: int = 60,
) -> List[str]:
    """
    Collect offer keywords from multiple sources.

    Sources checked in order:
    1. offer_keywords_llm from analysis (LLM extraction)
    2. Fallback to analysis fields (structured parsing)
    3. Missing keywords from critic JSON
    4. Job title tokens

    Args:
        offer_data: Job offer dictionary
        critic_json: Optional critic feedback with missing_keywords
        include_job_title: Whether to include job title tokens
        include_missing_keywords: Whether to include critic's missing keywords
        max_items: Maximum keywords to return

    Returns:
        Deduplicated list of offer keywords
    """
    keywords: List[str] = []

    # Try offer_keywords_llm first (LLM extraction)
    offer_keywords = get_offer_keywords_json(offer_data)
    if isinstance(offer_keywords, dict):
        keywords.extend(
            collect_offer_keywords_from_source(
                offer_keywords,
                keys=DEFAULT_OFFER_KEY_FIELDS,
                include_keyword_families=True,
                include_family_keys=True,
                include_job_title=True,
                max_items=80,
            )
        )
    else:
        # Fallback to analysis fields
        analysis = (
            offer_data.get("analysis") if isinstance(offer_data, dict) else None
        )
        if isinstance(analysis, dict):
            keywords.extend(
                collect_offer_keywords_from_source(
                    analysis,
                    keys=DEFAULT_ANALYSIS_KEY_FIELDS,
                    include_keyword_families=True,
                    include_family_keys=True,
                    include_job_title=False,
                    max_items=80,
                )
            )

    # Add missing keywords from critic
    if include_missing_keywords and critic_json and isinstance(critic_json, dict):
        missing = critic_json.get("missing_keywords")
        if isinstance(missing, list):
            keywords.extend(str(item) for item in missing if item)

    # Add job title tokens
    if include_job_title:
        job_title = offer_data.get("job_title") if isinstance(offer_data, dict) else ""
        if job_title:
            keywords.extend(part for part in str(job_title).split() if part)

    return dedup_preserve(
        [k for k in keywords if isinstance(k, str) and k.strip()],
        max_items=max_items,
    )


def collect_offer_keywords_with_candidates(
    offer_data: Optional[Dict[str, Any]],
    candidate_keywords: Optional[List[str]] = None,
    *,
    max_items: int = 60,
) -> List[str]:
    """
    Collect offer keywords including candidate profile terms.

    This variant includes candidate profile keywords to enable
    better matching and alignment scoring.

    Args:
        offer_data: Job offer dictionary
        candidate_keywords: Keywords extracted from candidate profile
        max_items: Maximum keywords to return

    Returns:
        Deduplicated list of combined keywords
    """
    keywords: List[str] = []

    # Get analysis keywords
    analysis = (
        offer_data.get("analysis") if isinstance(offer_data, dict) else None
    )
    if isinstance(analysis, dict):
        keywords.extend(
            collect_offer_keywords_from_source(
                analysis,
                keys=DEFAULT_ANALYSIS_KEY_FIELDS,
                include_keyword_families=True,
                include_family_keys=True,
                include_job_title=False,
                max_items=80,
            )
        )

    # Add job title tokens
    job_title = offer_data.get("job_title") if isinstance(offer_data, dict) else ""
    if job_title:
        keywords.extend(part for part in str(job_title).split() if part)

    # Add candidate keywords
    if candidate_keywords:
        keywords.extend(candidate_keywords)

    return dedup_preserve(
        [k for k in keywords if isinstance(k, str) and k.strip()],
        max_items=max_items,
    )


def merge_offer_keywords(
    offer_data: Dict[str, Any],
    offer_keywords: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Merge extracted offer keywords into offer analysis.

    This function updates offer_data in place with the merged analysis.

    Args:
        offer_data: Job offer dictionary (modified in place)
        offer_keywords: Extracted offer keywords from LLM

    Returns:
        Updated offer_data dictionary
    """
    if not isinstance(offer_data, dict) or not isinstance(offer_keywords, dict):
        return offer_data

    analysis = offer_data.get("analysis")
    updated_analysis = merge_offer_keywords_into_analysis(analysis, offer_keywords)
    offer_data["analysis"] = updated_analysis

    return offer_data


def update_ats_keywords(
    cv_json: Dict[str, Any],
    offer_keywords: List[str],
    *,
    max_keywords: int = 15,
) -> None:
    """
    Update ATS keywords in CV JSON based on offer keywords.

    Filters existing ATS keywords to keep only those matching offer keywords,
    then appends remaining offer keywords up to the limit.

    Args:
        cv_json: CV JSON dictionary (modified in place)
        offer_keywords: List of offer keywords
        max_keywords: Maximum ATS keywords to include
    """
    if not isinstance(cv_json, dict) or not offer_keywords:
        return

    offer_keywords = dedup_preserve(
        [item for item in offer_keywords if isinstance(item, str) and item.strip()]
    )
    offer_norm = {normalize_keyword_for_match(item) for item in offer_keywords}

    existing = cv_json.get("ats_keywords")
    existing_list = (
        [item for item in existing if isinstance(item, str)]
        if isinstance(existing, list)
        else []
    )

    # Keep only existing keywords that match offer keywords
    filtered_existing = [
        item
        for item in existing_list
        if normalize_keyword_for_match(item) in offer_norm
    ]

    combined = dedup_preserve(filtered_existing + offer_keywords)
    cv_json["ats_keywords"] = combined[:max_keywords]


def select_required_offer_terms(
    offer_keywords: List[str],
    *,
    mapping: Optional[Dict[str, str]] = None,
    max_terms: int = 8,
    stop_words: Optional[Set[str]] = None,
) -> List[str]:
    """
    Select the most important offer terms for ATS matching.

    Prioritizes:
    1. Mapped terms (from keyword alignment)
    2. Multi-word terms (better ATS signal)
    3. Longer terms

    Args:
        offer_keywords: List of offer keywords
        mapping: Optional keyword alignment mapping
        max_terms: Maximum terms to return
        stop_words: Optional custom stop words set

    Returns:
        List of selected required terms
    """
    if stop_words is None:
        stop_words = {
            "the", "and", "for", "with", "job", "role",
            "poste", "avec", "pour", "dans", "des", "les",
        }

    terms: List[str] = []
    mapping = mapping or {}

    # Add mapped terms first
    mapped = dedup_preserve(
        [item for item in mapping.values() if isinstance(item, str) and item.strip()]
    )
    terms.extend(mapped)

    # Clean and filter offer keywords
    cleaned_offer: List[str] = []
    for raw in offer_keywords or []:
        if not isinstance(raw, str):
            continue
        term = raw.strip()
        if len(term) < 3 or len(term) > 60:
            continue
        norm = normalize_keyword_for_match(term)
        if not norm or norm in stop_words:
            continue
        if not re.search(r"[a-zA-Z]", term):
            continue
        cleaned_offer.append(term)

    # Prefer multi-word terms (usually better ATS signal)
    cleaned_offer = dedup_preserve(cleaned_offer)
    cleaned_offer.sort(
        key=lambda item: (
            0 if (" " in item.strip() or "/" in item.strip() or "-" in item.strip()) else 1,
            -len(item.strip()),
        )
    )

    terms.extend(cleaned_offer)
    return dedup_preserve(terms)[:max(1, int(max_terms))]


def collect_offer_lexical_terms(
    offer_data: Optional[Dict[str, Any]],
    *,
    offer_keywords: Optional[List[str]] = None,
    offer_text: Optional[str] = None,
    max_terms: int = 36,
) -> List[str]:
    """
    Collect lexical terms from offer for keyword family building.

    This function extracts significant terms from:
    1. Offer keywords and their tokens
    2. Frequently occurring terms in offer text

    Args:
        offer_data: Job offer dictionary
        offer_keywords: Optional pre-collected offer keywords
        offer_text: Optional offer text (avoids re-extraction)
        max_terms: Maximum terms to return

    Returns:
        List of lexical terms for keyword family matching
    """
    lexical: List[str] = []

    # Get seed keywords
    seed_keywords = offer_keywords or collect_offer_keywords(offer_data)

    for raw in seed_keywords:
        if not isinstance(raw, str):
            continue
        term = raw.strip()
        if len(term) < 3 or len(term) > 72:
            continue
        lexical.append(term)

        # Add individual tokens
        for token in keyword_tokens(term):
            if len(token) >= 4 and token not in STOP_WORDS_ALL:
                lexical.append(token)

    # Extract frequent terms from offer text
    if offer_text is None:
        offer_text = offer_data.get("text") if isinstance(offer_data, dict) else ""

    if offer_text:
        norm_offer = normalize_keyword_for_match(offer_text)
        if norm_offer:
            tokens = [
                token
                for token in norm_offer.split()
                if (
                    len(token) >= 4
                    and token not in STOP_WORDS_ALL
                    and re.search(r"[a-zA-Z]", token)
                )
            ]
            token_counts = Counter(tokens)
            common_tokens = [
                token
                for token, count in token_counts.most_common(max(8, max_terms // 2))
                if count >= 2
            ]
            lexical.extend(common_tokens)

    return dedup_preserve(
        [item for item in lexical if isinstance(item, str) and item.strip()]
    )[:max(1, int(max_terms))]


def keyword_present_in_text(
    text: str,
    term: str,
) -> bool:
    """
    Check if a keyword is present in text (word boundary aware).

    Args:
        text: Text to search in (should be normalized)
        term: Term to search for

    Returns:
        True if term is found with word boundaries
    """
    if not text or not term:
        return False

    normalized_term = normalize_keyword_for_match(term)
    if not normalized_term:
        return False

    pattern = re.compile(
        rf"(?<![a-z0-9]){re.escape(normalized_term)}(?![a-z0-9])",
        flags=re.IGNORECASE,
    )
    return bool(pattern.search(text))


def build_lexical_family(
    term: str,
    *,
    offer_lexical_terms: Optional[List[str]] = None,
    max_terms: int = 12,
) -> List[str]:
    """
    Build a lexical family for a term based on offer lexical terms.

    A lexical family includes terms that share a common root or
    are semantically related (e.g., "develop", "developer", "development").

    Args:
        term: Base term for the family
        offer_lexical_terms: Pool of offer lexical terms
        max_terms: Maximum family members

    Returns:
        List of related terms
    """
    if not isinstance(term, str) or not term.strip():
        return []

    family: List[str] = []
    normalized = normalize_keyword_for_match(term)
    if not normalized:
        return []

    # Find terms that share the normalized root
    root_length = min(len(normalized), 4)
    root = normalized[:root_length]

    for lexical_term in (offer_lexical_terms or []):
        if not isinstance(lexical_term, str):
            continue
        norm_lex = normalize_keyword_for_match(lexical_term)
        if not norm_lex:
            continue

        # Check if shares root
        if norm_lex.startswith(root) or normalized.startswith(norm_lex[:root_length]):
            family.append(lexical_term)

    return dedup_preserve(family)[:max_terms]


def set_generation_audit(
    offer_data: Dict[str, Any],
    generation_audit: Dict[str, Any],
) -> None:
    """
    Store generation audit in offer_data's analysis section.

    Args:
        offer_data: Job offer dictionary (modified in place)
        generation_audit: Audit dictionary to store
    """
    if not isinstance(offer_data, dict) or not isinstance(generation_audit, dict):
        return

    analysis = offer_data.get("analysis")
    updated_analysis = dict(analysis) if isinstance(analysis, dict) else {}
    updated_analysis["generation_audit"] = generation_audit
    offer_data["analysis"] = updated_analysis


def extract_job_metadata(
    offer_data: Optional[Dict[str, Any]],
) -> Dict[str, str]:
    """
    Extract common job metadata from offer data.

    Args:
        offer_data: Job offer dictionary

    Returns:
        Dict with job_title, company, and text keys
    """
    if not isinstance(offer_data, dict):
        return {"job_title": "", "company": "", "text": ""}

    return {
        "job_title": str(offer_data.get("job_title") or "").strip(),
        "company": str(offer_data.get("company") or "").strip(),
        "text": str(offer_data.get("text") or "").strip(),
    }


def prepare_offer_text(
    offer_data: Optional[Dict[str, Any]],
    *,
    max_chars: int,
    keywords: Optional[List[str]] = None,
    select_relevant_blocks_fn: Optional[Callable[[str, int, List[str], int], str]] = None,
) -> str:
    """
    Prepare offer text for prompts, optionally truncating intelligently.

    If the offer text exceeds max_chars, uses keyword-based block selection
    to keep the most relevant parts.

    Args:
        offer_data: Job offer dictionary
        max_chars: Maximum character count
        keywords: Optional keywords for relevance scoring
        select_relevant_blocks_fn: Optional function for intelligent truncation

    Returns:
        Prepared offer text
    """
    offer_text = offer_data.get("text") if isinstance(offer_data, dict) else ""
    offer_text = offer_text or ""

    if not offer_text:
        return ""

    if len(offer_text) <= max_chars:
        return offer_text

    # Use intelligent block selection if available
    if select_relevant_blocks_fn and keywords:
        return select_relevant_blocks_fn(
            offer_text,
            max_chars,
            keywords,
            900,  # max_block_chars
        )

    # Simple truncation fallback
    return offer_text[:max_chars]
