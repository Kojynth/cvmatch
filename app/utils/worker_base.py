"""
Worker Base Utilities Module 

Common utilities and helper functions shared between CVGenerationWorker
and CoverLetterGenerationWorker. This module eliminates code duplication
and provides a centralized place for shared worker logic.

Key features:
- Language resolution for generation
- Generation audit management
- Offer keyword collection helpers
- Common sanitization functions
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional, Tuple, TYPE_CHECKING

try:
    from ..logging.safe_logger import get_safe_logger
    from ..config import DEFAULT_PII_CONFIG
    logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

from .language_policy import (
    detect_language_from_text_default as detect_language_from_text,
    normalize_language_code,
    resolve_offer_language,
    sync_offer_analysis_language,
)
from .offer_keywords_utils import (
    DEFAULT_ANALYSIS_KEY_FIELDS,
    DEFAULT_OFFER_KEY_FIELDS,
    collect_offer_keywords_from_source,
    dedup_preserve as dedup_offer_keywords,
)


def resolve_generation_language(
    offer_data: Optional[Dict[str, Any]],
    *,
    default_language: str = "fr",
    sync_back: bool = True,
) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Resolve the language code for generation from offer data.

    This function determines the target language for CV/cover letter
    generation based on the offer analysis and text content.

    Args:
        offer_data: Job offer dictionary
        default_language: Fallback language code
        sync_back: If True, sync the resolved language back to offer_data

    Returns:
        Tuple of (language_code, updated_offer_data)
    """
    language_code = resolve_offer_language(
        offer_data if isinstance(offer_data, dict) else None,
        normalize_language=normalize_language_code,
        detect_language_from_text=detect_language_from_text,
        default_language=default_language,
    )

    updated_offer_data = offer_data
    if sync_back and isinstance(offer_data, dict):
        updated_offer_data = sync_offer_analysis_language(
            offer_data,
            language_code,
        )

    return language_code, updated_offer_data


def set_generation_audit_in_offer(
    offer_data: Dict[str, Any],
    generation_audit: Dict[str, Any],
) -> None:
    """Store generation audit in offer_data's analysis section.

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


def get_generation_language_code(
    offer_data: Optional[Dict[str, Any]],
    *,
    default: str = "fr",
) -> str:
    """Get language code from offer data without syncing back.

    This is a read-only version of language resolution for cases
    where you don't want to modify offer_data.

    Args:
        offer_data: Job offer dictionary
        default: Fallback language code

    Returns:
        Normalized language code
    """
    if not isinstance(offer_data, dict):
        return default

    analysis = offer_data.get("analysis", {})
    for key in ("cv_language", "target_language", "language_code"):
        explicit_language = offer_data.get(key)
        if explicit_language:
            normalized = normalize_language_code(str(explicit_language))
            if normalized:
                return normalized
    if isinstance(analysis, dict):
        for key in ("cv_language", "target_language"):
            explicit_language = analysis.get(key)
            if explicit_language:
                normalized = normalize_language_code(str(explicit_language))
                if normalized:
                    return normalized
    analysis_language = analysis.get("language") if isinstance(analysis, dict) else None
    offer_text = offer_data.get("text")

    detected = detect_language_from_text(offer_text)

    if analysis_language:
        analysis_norm = normalize_language_code(analysis_language)
        if analysis_norm:
            if detected and detected != analysis_norm:
                return normalize_language_code(detected) or default
            return analysis_norm

    if detected:
        return normalize_language_code(detected) or default

    return default


def collect_offer_keywords_merged(
    *,
    offer_keywords_json: Optional[Dict[str, Any]] = None,
    offer_analysis: Optional[Dict[str, Any]] = None,
    critic_json: Optional[Dict[str, Any]] = None,
    job_title: str = "",
    max_items: int = 60,
) -> List[str]:
    """Collect and merge offer keywords from multiple sources.

    This function provides a centralized way to collect keywords from:
    - Offer keywords JSON (from LLM extraction)
    - Offer analysis (from structured parsing)
    - Critic feedback (missing keywords)
    - Job title tokens

    Args:
        offer_keywords_json: Extracted offer keywords from LLM
        offer_analysis: Structured offer analysis
        critic_json: Critic feedback (may contain missing_keywords)
        job_title: Job title string
        max_items: Maximum keywords to return

    Returns:
        Deduplicated list of keywords
    """
    keywords: List[str] = []

    # Collect from offer_keywords_json
    if isinstance(offer_keywords_json, dict):
        keywords.extend(
            collect_offer_keywords_from_source(
                offer_keywords_json,
                keys=DEFAULT_OFFER_KEY_FIELDS,
                include_keyword_families=True,
                include_family_keys=True,
                include_job_title=True,
                max_items=80,
            )
        )
    elif isinstance(offer_analysis, dict):
        # Fallback to analysis if no offer_keywords_json
        keywords.extend(
            collect_offer_keywords_from_source(
                offer_analysis,
                keys=DEFAULT_ANALYSIS_KEY_FIELDS,
                include_keyword_families=True,
                include_family_keys=True,
                include_job_title=False,
                max_items=80,
            )
        )

    # Add missing keywords from critic feedback
    if critic_json and isinstance(critic_json, dict):
        missing = critic_json.get("missing_keywords")
        if isinstance(missing, list):
            keywords.extend(str(item) for item in missing if item)

    # Add job title tokens
    if job_title:
        keywords.extend(part for part in job_title.split() if part)

    return dedup_offer_keywords(
        [k for k in keywords if isinstance(k, str) and k.strip()],
        max_items=max_items,
    )


def normalize_text_for_compare(text: str) -> str:
    """Normalize text for comparison (lowercase, collapse whitespace).

    Args:
        text: Input text

    Returns:
        Normalized text
    """
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def trim_text(value: Any, max_chars: int) -> str:
    """Trim text to max characters with ellipsis.

    Args:
        value: Value to convert and trim
        max_chars: Maximum character count

    Returns:
        Trimmed string
    """
    text = "" if value is None else str(value)
    text = text.strip()
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars - 1].rstrip() + "…"


def extract_offer_metadata(
    offer_data: Optional[Dict[str, Any]],
) -> Dict[str, str]:
    """Extract common metadata from offer data.

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


def extract_profile_contact_info(profile_data: Any) -> Dict[str, str]:
    """Extract contact info from profile data object.

    Args:
        profile_data: UserProfile or ProfileWorkerData object

    Returns:
        Dict with name, email, phone, linkedin_url keys
    """
    return {
        "name": str(getattr(profile_data, "name", "") or "").strip(),
        "email": str(getattr(profile_data, "email", "") or "").strip(),
        "phone": str(getattr(profile_data, "phone", "") or "").strip(),
        "linkedin_url": str(getattr(profile_data, "linkedin_url", "") or "").strip(),
    }


def should_use_subprocess_stages(
    qwen_manager: Any,
    *,
    env_flag: Optional[str] = None,
) -> bool:
    """Determine if pipeline stages should use subprocess isolation.

    Subprocess isolation helps prevent OOM errors and allows for
    better memory management between generation stages.

    Args:
        qwen_manager: QwenManager instance
        env_flag: Optional environment flag value (CVMATCH_SUBPROCESS_STAGES)

    Returns:
        True if subprocess stages should be used
    """
    import os

    # Check survival mode first
    try:
        if qwen_manager._is_survival_mode():
            return True
    except Exception:
        pass

    # Check environment variable
    if env_flag is None:
        env_flag = os.getenv("CVMATCH_SUBPROCESS_STAGES")
    if env_flag is not None:
        return env_flag.strip().lower() in ("1", "true", "yes", "y")

    # Check custom parameters
    custom = getattr(qwen_manager, "custom_parameters", None) or {}
    if "subprocess_stages" in custom:
        return bool(custom.get("subprocess_stages"))

    # Check VRAM mode
    try:
        return bool(
            qwen_manager._is_low_vram_mode()
            or qwen_manager._is_med_vram_mode()
        )
    except Exception:
        return False


def is_stage_model_routing_enabled(
    *,
    env_flag: Optional[str] = None,
) -> bool:
    """Check if per-stage model routing is enabled.

    Quality-first policy: routing is explicit env opt-in only.

    Args:
        env_flag: Optional environment flag value (CVMATCH_STAGE_MODEL_ROUTING)

    Returns:
        True if stage model routing is enabled
    """
    import os

    if env_flag is None:
        env_flag = os.getenv("CVMATCH_STAGE_MODEL_ROUTING")

    if env_flag is None:
        return False

    return str(env_flag).strip().lower() in ("1", "true", "yes", "y", "on", "auto")


def format_stage_progress_message(
    stage: str,
    *,
    language_code: str = "fr",
    emoji: str = "",
) -> str:
    """Format a progress message for a pipeline stage.

    Args:
        stage: Stage identifier
        language_code: Target language
        emoji: Optional emoji prefix

    Returns:
        Formatted progress message
    """
    is_en = language_code == "en"

    stage_messages = {
        "offer_keywords": (
            "Analyzing job offer keywords..." if is_en
            else "Analyse des mots-cles de l'offre..."
        ),
        "critic": (
            "Running critic analysis..." if is_en
            else "Analyse critique en cours..."
        ),
        "draft": (
            "Generating CV draft..." if is_en
            else "Generation du brouillon du CV..."
        ),
        "final": (
            "Finalizing CV..." if is_en
            else "Finalisation du CV..."
        ),
        "cover_letter": (
            "Generating cover letter..." if is_en
            else "Generation de la lettre de motivation..."
        ),
        "cover_letter_critic": (
            "Reviewing cover letter..." if is_en
            else "Relecture de la lettre de motivation..."
        ),
        "autocheck": (
            "Running ATS compatibility check..." if is_en
            else "Verification de la compatibilite ATS..."
        ),
    }

    message = stage_messages.get(stage, f"Stage: {stage}")
    if emoji:
        return f"{emoji} {message}"
    return message
