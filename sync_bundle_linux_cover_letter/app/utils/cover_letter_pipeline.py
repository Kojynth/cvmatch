"""
Cover Letter Pipeline Utilities

Centralized cover letter generation, validation, and scoring logic.
This module extracts cover letter-related processing from CVGenerationWorker
and CoverLetterGenerationWorker to provide reusable functions.

Key features:
- Language consistency validation
- Structure coherence checking
- Keyword relevance scoring
- Generation audit building for letters
- Critic prompt building
- Rewrite prompt building

These functions operate on plain data (strings, dicts) and do not depend on
any worker state, making them suitable for both in-process and subprocess
pipeline stages.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    from ..logging.safe_logger import get_safe_logger
    from ..config import DEFAULT_PII_CONFIG

    logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)
except ImportError:
    import logging

    logger = logging.getLogger(__name__)

# Import from existing utility modules
from .cover_letter_rules import is_cover_letter_structure_coherent
from .language_policy import (
    detect_language_from_text_default,
    is_mixed_or_mismatched_language,
    normalize_language_code as normalize_language,
)
from .keyword_alignment import (
    normalize_keyword_for_match,
    keyword_similarity,
)
from .offer_keywords_utils import (
    DEFAULT_ANALYSIS_KEY_FIELDS,
    collect_offer_keywords_from_source,
    dedup_preserve,
)
from .generation_audit import build_generation_audit


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------


@dataclass
class CoverLetterValidationResult:
    """Result of cover letter validation."""

    is_valid: bool
    language_ok: bool
    structure_ok: bool
    relevance_score: int
    issues: List[str] = field(default_factory=list)


@dataclass
class CoverLetterReviewPayload:
    """Sanitized cover letter review payload."""

    should_improve: bool
    structure_ok: bool
    relevance_score: int
    language: str
    issues: List[Dict[str, str]]
    keywords_to_add: List[str]
    rewrite_plan: List[str]


# ---------------------------------------------------------------------------
# Text Helpers
# ---------------------------------------------------------------------------


def _trim_text(text: Optional[str], max_chars: int) -> str:
    """Trim text to max_chars, appending '...' if truncated."""
    if not text:
        return ""
    text = str(text).strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "..."


# ---------------------------------------------------------------------------
# Language Validation
# ---------------------------------------------------------------------------


def ensure_cover_letter_language_consistency(
    text: str,
    target_language: str,
    *,
    normalize_language_fn: Optional[Callable[[str], str]] = None,
    detect_language_fn: Optional[Callable[[str], str]] = None,
) -> str:
    """
    Validate that cover letter text matches target language.

    Args:
        text: Cover letter text to validate
        target_language: Expected language code (e.g., "fr", "en")
        normalize_language_fn: Optional language normalizer function
        detect_language_fn: Optional language detection function

    Returns:
        The validated cover letter text

    Raises:
        RuntimeError: If text is empty or language mismatch detected
    """
    letter = str(text or "").strip()
    if not letter:
        raise RuntimeError("Cover letter generation returned empty output.")

    # Use provided functions or fall back to defaults
    norm_fn = normalize_language_fn or normalize_language
    detect_fn = detect_language_fn or detect_language_from_text_default

    normalized_target = norm_fn(target_language)

    if is_mixed_or_mismatched_language(
        letter,
        normalized_target,
        normalize_language=norm_fn,
        detect_language_from_text=detect_fn,
    ):
        raise RuntimeError(
            f"Cover letter language mismatch detected (target={normalized_target})."
        )

    return letter


def check_cover_letter_structure(
    text: str,
    language_code: str,
    *,
    normalize_language_fn: Optional[Callable[[str], str]] = None,
) -> bool:
    """
    Check if cover letter has proper structure.

    Args:
        text: Cover letter text to check
        language_code: Language code for structure rules
        normalize_language_fn: Optional language normalizer

    Returns:
        True if structure is coherent
    """
    norm_fn = normalize_language_fn or normalize_language
    lang = norm_fn(language_code)
    return is_cover_letter_structure_coherent(text, language_code=lang)


# ---------------------------------------------------------------------------
# Relevance Scoring
# ---------------------------------------------------------------------------


def estimate_cover_letter_relevance_score(
    text: str,
    offer_data: Optional[Dict[str, Any]],
    *,
    language_code: str = "fr",
    min_score: int = 58,
    max_score: int = 100,
    default_score: int = 72,
    similarity_threshold: float = 0.72,
) -> int:
    """
    Estimate relevance score based on offer keyword coverage.

    Scoring formula:
    - Base score: 58
    - Coverage bonus: up to 42 points based on keyword coverage
    - Structure penalty: cap at 68 if structure is incoherent

    Args:
        text: Cover letter text to score
        offer_data: Job offer dictionary with analysis
        language_code: Language code for structure check
        min_score: Minimum possible score
        max_score: Maximum possible score
        default_score: Score when no offer terms available
        similarity_threshold: Minimum similarity for keyword match

    Returns:
        Relevance score (0-100)
    """
    letter = str(text or "").strip()
    if not letter:
        return 0

    # Extract offer terms
    analysis = offer_data.get("analysis", {}) if isinstance(offer_data, dict) else {}
    offer_terms = collect_offer_keywords_from_source(
        analysis if isinstance(analysis, dict) else None,
        keys=DEFAULT_ANALYSIS_KEY_FIELDS,
        include_keyword_families=True,
        include_family_keys=True,
        include_job_title=False,
        max_items=24,
    )
    offer_terms = dedup_preserve(
        [str(item).strip() for item in offer_terms if str(item).strip()]
    )

    if not offer_terms:
        return default_score

    # Calculate coverage
    normalized_letter = normalize_keyword_for_match(letter)
    covered = 0

    for term in offer_terms:
        # Check similarity match
        if keyword_similarity(term, normalized_letter) >= similarity_threshold:
            covered += 1
            continue

        # Check substring match
        norm_term = normalize_keyword_for_match(term)
        if norm_term and norm_term in normalized_letter:
            covered += 1

    coverage = float(covered) / float(max(1, len(offer_terms)))
    score = int(round(float(min_score) + (coverage * 42.0)))

    # Apply structure penalty
    if not check_cover_letter_structure(letter, language_code):
        score = min(score, 68)

    return max(0, min(max_score, score))


# ---------------------------------------------------------------------------
# Review Sanitization
# ---------------------------------------------------------------------------


def sanitize_cover_letter_review(
    payload: Any,
    *,
    default_language: str = "fr",
    max_issues: int = 6,
    max_keywords: int = 10,
    max_plan_items: int = 8,
) -> CoverLetterReviewPayload:
    """
    Sanitize and validate a cover letter review payload.

    Args:
        payload: Raw review payload (dict expected)
        default_language: Default language if not provided
        max_issues: Maximum issues to keep
        max_keywords: Maximum keywords to keep
        max_plan_items: Maximum rewrite plan items

    Returns:
        Sanitized CoverLetterReviewPayload
    """
    data = payload if isinstance(payload, dict) else {}

    # Clean issues
    issues = data.get("issues")
    if not isinstance(issues, list):
        issues = []
    cleaned_issues: List[Dict[str, str]] = []
    for item in issues[:max_issues]:
        if isinstance(item, dict):
            issue = str(item.get("issue") or "").strip()
            fix = str(item.get("fix") or "").strip()
            if issue or fix:
                cleaned_issues.append({"issue": issue, "fix": fix})

    # Clean keywords
    keywords = data.get("keywords_to_add")
    if not isinstance(keywords, list):
        keywords = []
    cleaned_keywords = [
        str(item).strip() for item in keywords[:max_keywords] if str(item).strip()
    ]

    # Clean rewrite plan
    rewrite_plan = data.get("rewrite_plan")
    if not isinstance(rewrite_plan, list):
        rewrite_plan = []
    cleaned_plan = [
        str(item).strip() for item in rewrite_plan[:max_plan_items] if str(item).strip()
    ]

    # Parse relevance score
    try:
        relevance_score = int(data.get("relevance_score", 60))
    except (ValueError, TypeError):
        relevance_score = 60
    relevance_score = max(0, min(100, relevance_score))

    # Parse language
    language = data.get("language")
    if not isinstance(language, str) or not language.strip():
        language = default_language
    language = normalize_language(language)

    return CoverLetterReviewPayload(
        should_improve=bool(data.get("should_improve", False)),
        structure_ok=bool(data.get("structure_ok", False)),
        relevance_score=relevance_score,
        language=language,
        issues=cleaned_issues,
        keywords_to_add=cleaned_keywords,
        rewrite_plan=cleaned_plan,
    )


# ---------------------------------------------------------------------------
# Generation Audit Building
# ---------------------------------------------------------------------------


def build_generation_audit_for_letter(
    *,
    letter_score: int,
    structure_ok: bool,
    language_code: str,
    previous_audit: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build generation audit for a cover letter.

    This function creates an audit payload that includes both CV alignment
    data (from previous audit) and cover letter review data.

    Args:
        letter_score: Cover letter relevance score (0-100)
        structure_ok: Whether letter structure is coherent
        language_code: Language code of the letter
        previous_audit: Optional previous generation audit with CV data

    Returns:
        Generation audit dictionary
    """
    previous = previous_audit if isinstance(previous_audit, dict) else {}

    # Extract CV score from previous audit
    prev_cv_score = 0.0
    prev_cv_ok = False

    if previous:
        try:
            prev_cv_score = float(previous.get("cv_score") or 0.0)
        except (ValueError, TypeError):
            prev_cv_score = 0.0

        breakdown = previous.get("breakdown")
        if isinstance(breakdown, dict):
            cv_block = breakdown.get("cv")
            if isinstance(cv_block, dict):
                prev_cv_ok = bool(cv_block.get("sufficient", False))

    # Build alignment stub from previous CV data
    alignment_stub = {
        "overall_score": max(0.0, min(100.0, prev_cv_score)),
        "exact_keyword_score": max(0.0, min(100.0, prev_cv_score)),
        "lexical_family_score": max(0.0, min(100.0, prev_cv_score)),
        "sufficient": bool(prev_cv_ok),
    }

    # Build cover letter review
    cover_review = {
        "relevance_score": int(max(0, min(100, letter_score))),
        "structure_ok": bool(structure_ok),
        "language": str(language_code or ""),
    }

    return build_generation_audit(
        alignment_audit=alignment_stub,
        cover_letter_review=cover_review,
    )


# ---------------------------------------------------------------------------
# Prompt Building
# ---------------------------------------------------------------------------


def build_cover_letter_critic_messages(
    *,
    cover_letter: str,
    language_code: str,
    job_title: str,
    company: str,
    offer_text: str,
    offer_keywords: Optional[Dict[str, Any]] = None,
    candidate_terms: Optional[List[str]] = None,
    max_offer_text_chars: int = 2200,
    max_keywords_chars: int = 1200,
    max_letter_chars: int = 2600,
) -> Dict[str, str]:
    """
    Build system and user prompts for cover letter critique.

    Args:
        cover_letter: Cover letter text to critique
        language_code: Target language code
        job_title: Target job title
        company: Target company name
        offer_text: Job offer text
        offer_keywords: Optional offer keywords JSON
        candidate_terms: Optional candidate profile terms
        max_offer_text_chars: Max chars for offer text
        max_keywords_chars: Max chars for keywords JSON
        max_letter_chars: Max chars for letter

    Returns:
        Dict with "system" and "user" prompt keys
    """
    offer_keywords_text = (
        _trim_text(json.dumps(offer_keywords, ensure_ascii=False), max_keywords_chars)
        if isinstance(offer_keywords, dict)
        else "N/A"
    )

    candidate_terms_text = ", ".join(str(term) for term in (candidate_terms or [])[:30])

    system_prompt = (
        "You are a strict cover letter reviewer for ATS relevance and structure quality. "
        "Return JSON only with keys: "
        "should_improve, structure_ok, relevance_score, language, issues, keywords_to_add, rewrite_plan. "
        "issues is an array of {issue, fix}. "
        "Do not invent facts. Keep corrections grounded in provided candidate data."
    )

    user_prompt = f"""
TARGET_LANGUAGE: {language_code}
JOB_TITLE: {job_title}
COMPANY: {company}
JOB_OFFER_TEXT:
{_trim_text(offer_text, max_offer_text_chars)}

OFFER_KEYWORDS_JSON:
{offer_keywords_text}

CANDIDATE_TERMS:
{candidate_terms_text}

COVER_LETTER:
{_trim_text(cover_letter, max_letter_chars)}

Rules:
- structure_ok=true only if the letter has subject/objet, salutation, >=2 body paragraphs, and closing.
- keywords_to_add: only terms relevant to offer and candidate profile.
- relevance_score in [0..100].
- language must be "fr" or "en".
""".strip()

    return {"system": system_prompt, "user": user_prompt}


def build_cover_letter_rewrite_prompt(
    *,
    base_prompt: str,
    cover_letter: str,
    review: Dict[str, Any],
    language_code: str,
    rewrite_reason: str = "",
    max_review_chars: int = 1800,
    max_letter_chars: int = 2600,
) -> str:
    """
    Build rewrite prompt for cover letter improvement.

    Args:
        base_prompt: Base cover letter generation prompt
        cover_letter: Current cover letter text
        review: Quality review JSON
        language_code: Target language code
        rewrite_reason: Optional rewrite reason (e.g. language_mismatch)
        max_review_chars: Max chars for review JSON
        max_letter_chars: Max chars for letter

    Returns:
        Complete rewrite prompt string
    """
    review_block = _trim_text(
        json.dumps(review or {}, ensure_ascii=False, indent=2),
        max_review_chars,
    )
    normalized_reason = str(rewrite_reason or "").strip().lower()
    language_name = (
        "French" if str(language_code or "").strip().lower() == "fr" else "English"
    )
    if normalized_reason == "language_mismatch":
        return f"""
{base_prompt}

QUALITY_REVIEW_JSON:
{review_block}

CURRENT_COVER_LETTER:
{_trim_text(cover_letter, max_letter_chars)}

TASK:
- Rewrite the full letter in {language_name}.
- Correct the detected language mismatch completely.
- Translate every sentence to {language_name}; do not keep mixed-language phrasing.
- Keep ONLY verifiable candidate facts.
- Keep coherent structure (subject/objet, salutation, 2-3 body paragraphs, closing).
- Keep proper nouns, company names, product names, acronyms, and tool names unchanged when appropriate.
- Use EXACTLY one language: {language_code}.
- Output only the final letter text.
""".strip()

    return f"""
{base_prompt}

QUALITY_REVIEW_JSON:
{review_block}

CURRENT_COVER_LETTER:
{_trim_text(cover_letter, max_letter_chars)}

TASK:
- Rewrite the full letter from scratch.
- Keep ONLY verifiable candidate facts.
- Improve relevance to the offer by integrating review keywords/instructions.
- Ensure at least 4 offer keywords appear in body paragraphs (exact term preferred, professional synonym/acronym allowed).
- Use EXACTLY one language: {language_code}.
- Keep coherent structure (subject/objet, salutation, 2-3 body paragraphs, closing).
- Output only the final letter text.
""".strip()


def build_simple_rewrite_prompt(
    *,
    base_prompt: str,
    cover_letter: str,
    language_code: str,
    max_letter_chars: int = 2600,
) -> str:
    """
    Build simple rewrite prompt for cover letter improvement.

    Used by CoverLetterGenerationWorker for quick rewrites.

    Args:
        base_prompt: Base cover letter generation prompt
        cover_letter: Current cover letter text
        language_code: Target language code
        max_letter_chars: Max chars for letter

    Returns:
        Rewrite prompt string
    """
    return f"""
{base_prompt}

CURRENT_COVER_LETTER:
{_trim_text(cover_letter, max_letter_chars)}

TASK:
- Rewrite the full letter to improve relevance to the job offer.
- Use offer keywords and lexical field when facts allow it.
- Include at least 4 offer keywords in the body (exact terms preferred, professional synonym/acronym allowed).
- Keep ONLY candidate facts from the provided profile context.
- Keep coherent structure: subject/objet, salutation, 2-3 body paragraphs, closing.
- Use EXACTLY one language: {language_code}.
- Output only the final letter text.
""".strip()


# ---------------------------------------------------------------------------
# Validation Orchestration
# ---------------------------------------------------------------------------


def validate_cover_letter(
    text: str,
    offer_data: Optional[Dict[str, Any]],
    *,
    language_code: str = "fr",
    min_relevance_score: int = 70,
    normalize_language_fn: Optional[Callable[[str], str]] = None,
    detect_language_fn: Optional[Callable[[str], str]] = None,
) -> CoverLetterValidationResult:
    """
    Perform complete validation of a cover letter.

    Args:
        text: Cover letter text to validate
        offer_data: Job offer dictionary
        language_code: Expected language code
        min_relevance_score: Minimum acceptable relevance score
        normalize_language_fn: Optional language normalizer
        detect_language_fn: Optional language detector

    Returns:
        CoverLetterValidationResult with validation details
    """
    issues: List[str] = []
    letter = str(text or "").strip()

    if not letter:
        return CoverLetterValidationResult(
            is_valid=False,
            language_ok=False,
            structure_ok=False,
            relevance_score=0,
            issues=["Cover letter is empty."],
        )

    norm_fn = normalize_language_fn or normalize_language
    detect_fn = detect_language_fn or detect_language_from_text_default
    normalized_lang = norm_fn(language_code)

    # Check language consistency
    language_ok = not is_mixed_or_mismatched_language(
        letter,
        normalized_lang,
        normalize_language=norm_fn,
        detect_language_from_text=detect_fn,
    )
    if not language_ok:
        issues.append(f"Language mismatch detected (target={normalized_lang}).")

    # Check structure
    structure_ok = is_cover_letter_structure_coherent(
        letter, language_code=normalized_lang
    )
    if not structure_ok:
        issues.append("Cover letter structure is incoherent.")

    # Calculate relevance score
    relevance_score = estimate_cover_letter_relevance_score(
        letter,
        offer_data,
        language_code=normalized_lang,
    )
    if relevance_score < min_relevance_score:
        issues.append(
            f"Relevance score too low ({relevance_score} < {min_relevance_score})."
        )

    is_valid = language_ok and structure_ok and relevance_score >= min_relevance_score

    return CoverLetterValidationResult(
        is_valid=is_valid,
        language_ok=language_ok,
        structure_ok=structure_ok,
        relevance_score=relevance_score,
        issues=issues,
    )


def should_rewrite_cover_letter(
    text: str,
    review: CoverLetterReviewPayload,
    language_code: str,
    *,
    min_relevance_score: int = 78,
    normalize_language_fn: Optional[Callable[[str], str]] = None,
    detect_language_fn: Optional[Callable[[str], str]] = None,
) -> bool:
    """
    Determine if a cover letter should be rewritten based on review.

    Args:
        text: Cover letter text
        review: Sanitized review payload
        language_code: Target language code
        min_relevance_score: Minimum acceptable relevance score
        normalize_language_fn: Optional language normalizer
        detect_language_fn: Optional language detector

    Returns:
        True if rewrite is recommended
    """
    if review.should_improve:
        return True

    norm_fn = normalize_language_fn or normalize_language
    detect_fn = detect_language_fn or (lambda t: "fr")
    normalized_lang = norm_fn(language_code)

    structure_ok = is_cover_letter_structure_coherent(
        text, language_code=normalized_lang
    )
    if not structure_ok:
        return True

    if not review.structure_ok:
        return True

    if is_mixed_or_mismatched_language(
        text,
        normalized_lang,
        normalize_language=norm_fn,
        detect_language_from_text=detect_fn,
    ):
        return True

    if review.relevance_score < min_relevance_score:
        return True

    return False
