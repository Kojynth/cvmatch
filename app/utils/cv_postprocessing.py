"""
CV Postprocessing Module 

Centralized CV JSON postprocessing utilities.
Extracted from CVGenerationWorker in llm_worker.py.

Key features:
- Fallback CV JSON generation (deterministic)
- CV JSON sanitization and validation
- Contact information fallback
- Section merging and repair
- Text sanitization (placeholders, review markers)
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

from .cv_text_quality import clean_narrative_text

try:
    from ..logging.safe_logger import get_safe_logger
    from ..config import DEFAULT_PII_CONFIG
    logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


# Review marker patterns that indicate LLM produced meta-commentary instead of content
REVIEW_MARKERS_EN = (
    "the cv",
    "this cv",
    "resume",
    "curriculum vitae",
    "the candidate",
    "candidate should",
    "candidate must",
    "should be",
    "should include",
    "must be",
    "needs",
    "missing",
    "revise",
    "improve",
    "job offer",
    "job description",
)

REVIEW_MARKERS_FR = (
    "le cv",
    "ce cv",
    "le candidat",
    "devrait",
    "doit",
    "manque",
    "a revoir",
    "ameliorer",
)

REVIEW_MARKERS = REVIEW_MARKERS_EN + REVIEW_MARKERS_FR

# Placeholder patterns to strip from generated text
PLACEHOLDER_PATTERN = re.compile(
    r"\[(?:A COMPLETER|TO COMPLETE|VOTRE|YOUR|PROFILE_JSON|YEAR_OF_PROFILE_JSON|IMPACT)[^\]]*\]",
    re.IGNORECASE,
)

INTERNAL_MARKER_PATTERN = re.compile(
    r"(PROFILE_JSON|YEAR_OF_PROFILE_JSON)",
    re.IGNORECASE,
)

ROLE_LIKE_SKILL_TOKENS = {
    "ingenieur",
    "engineer",
    "developpeur",
    "developer",
    "consultant",
    "manager",
    "lead",
    "architecte",
    "architect",
    "analyste",
    "analyst",
    "alternant",
    "stagiaire",
    "intern",
}

SKILL_LABEL_PREFIX_PATTERN = re.compile(
    r"(?i)^(?:skills?|comp[eé]tences?|technical skills|competences techniques)\s*[:\-]\s*"
)

SKILL_SPLIT_PATTERN = re.compile(r"[;\n\|•]+")
SKILL_SENTENCE_NOISE_PATTERN = re.compile(
    r"(?i)\b("
    r"i|we|my|our|je|j ai|nous|mon|notre|candidate|candidat|"
    r"experience|worked|responsible|mission|project|projet|"
    r"should|must|need|needs|please|job offer|offre|profile json|instruction"
    r")\b"
)
SKILL_GLUE_WORDS = {
    "and",
    "or",
    "with",
    "for",
    "the",
    "a",
    "an",
    "to",
    "of",
    "in",
    "on",
    "de",
    "des",
    "du",
    "et",
    "ou",
    "en",
    "pour",
    "avec",
    "sur",
}
SHORT_TECH_TOKENS = {
    "ai",
    "ml",
    "nlp",
    "qa",
    "ui",
    "ux",
    "bi",
    "ci",
    "cd",
    "etl",
    "api",
    "sql",
    "nosql",
    "go",
    "js",
    "ts",
    "c",
    "r",
}


def _dedup_preserve(items: Sequence[str]) -> List[str]:
    """Deduplicate list while preserving order."""
    seen: set = set()
    output: List[str] = []
    for raw in items or []:
        text = str(raw or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(text)
    return output


def _trim_text(value: Any, max_chars: int) -> str:
    """Trim text to max characters with ellipsis."""
    text = "" if value is None else str(value)
    text = text.strip()
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars - 1].rstrip() + "…"


def text_has_review_markers(text: str) -> bool:
    """Check if text contains LLM review markers (meta-commentary).

    These markers indicate the LLM produced commentary about
    the CV rather than actual CV content.

    Args:
        text: Text to check

    Returns:
        True if review markers detected
    """
    if not text:
        return False

    lowered = text.strip().lower()

    # Check for common markers
    if any(marker in lowered for marker in REVIEW_MARKERS):
        return True

    # Check for English modal patterns
    if re.search(r"\b(should|must|needs)\b", lowered):
        return True

    return False


def strip_placeholders(text: str) -> str:
    """Remove placeholder tokens from generated text.

    Args:
        text: Text with potential placeholders

    Returns:
        Cleaned text, or empty string if internal markers remain
    """
    if not text:
        return ""

    cleaned = str(text)
    cleaned = PLACEHOLDER_PATTERN.sub("", cleaned)

    # If internal markers remain, text is invalid
    if INTERNAL_MARKER_PATTERN.search(cleaned):
        return ""

    return cleaned.strip()


def clean_text_field(
    value: Any,
    *,
    max_length: int = 0,
    check_review_markers: bool = True,
    dedupe_narrative: bool = False,
) -> str:
    """Clean a text field by removing placeholders and review markers.

    Args:
        value: Value to clean
        max_length: Maximum length (0 = no limit)
        check_review_markers: If True, return empty for review text

    Returns:
        Cleaned text
    """
    if not isinstance(value, str):
        return ""

    cleaned = strip_placeholders(value)
    if not cleaned:
        return ""

    if dedupe_narrative:
        cleaned = clean_narrative_text(cleaned)
        if not cleaned:
            return ""

    if check_review_markers and text_has_review_markers(cleaned):
        return ""

    if max_length > 0 and len(cleaned) > max_length:
        return ""

    return cleaned


def apply_contact_fallback(
    cv_json: Dict[str, Any],
    profile_json: Dict[str, Any],
    *,
    profile_name: str = "",
    profile_email: str = "",
    profile_phone: str = "",
    profile_linkedin: str = "",
) -> None:
    """Apply fallback values to CV contact section.

    Fills in missing contact fields from profile data.

    Args:
        cv_json: CV JSON to modify in place
        profile_json: Source profile JSON
        profile_name: Fallback name
        profile_email: Fallback email
        profile_phone: Fallback phone
        profile_linkedin: Fallback LinkedIn URL
    """
    if not isinstance(cv_json, dict) or not isinstance(profile_json, dict):
        return

    contact = cv_json.get("contact")
    if not isinstance(contact, dict):
        contact = {}
        cv_json["contact"] = contact

    personal = profile_json.get("personal_info")
    if not isinstance(personal, dict):
        personal = {}

    fallback = {
        "full_name": profile_name or "",
        "email": profile_email or "",
        "phone": profile_phone or "",
        "linkedin_url": profile_linkedin or "",
    }

    for field in ("full_name", "email", "phone", "linkedin_url", "location"):
        if contact.get(field):
            continue
        value = personal.get(field) or fallback.get(field)
        if value:
            contact[field] = value


def apply_target_fallback(
    cv_json: Dict[str, Any],
    *,
    job_title: str = "",
    company: str = "",
) -> None:
    """Apply fallback values for target job title and company.

    Args:
        cv_json: CV JSON to modify in place
        job_title: Fallback job title
        company: Fallback company name
    """
    if not isinstance(cv_json, dict):
        return

    if not cv_json.get("target_job_title") and job_title:
        cv_json["target_job_title"] = job_title
    if not cv_json.get("target_company") and company:
        cv_json["target_company"] = company


def summary_needs_rewrite(summary: str) -> bool:
    """Check if summary needs regeneration.

    Args:
        summary: Summary text to check

    Returns:
        True if summary is empty or contains review markers
    """
    if not summary or not summary.strip():
        return True
    return text_has_review_markers(summary)


def repair_summary_if_needed(
    cv_json_final: Dict[str, Any],
    cv_json_draft: Dict[str, Any],
) -> None:
    """Repair final summary using draft if needed.

    Args:
        cv_json_final: Final CV JSON to modify
        cv_json_draft: Draft CV JSON for fallback
    """
    if not isinstance(cv_json_final, dict):
        return

    summary = cv_json_final.get("summary") or ""
    if not summary_needs_rewrite(summary):
        return

    draft_summary = ""
    if isinstance(cv_json_draft, dict):
        draft_summary = cv_json_draft.get("summary") or ""

    if draft_summary and not summary_needs_rewrite(draft_summary):
        cv_json_final["summary"] = draft_summary
        logger.warning("Final summary looked like review text; reverted to draft summary.")
    else:
        cv_json_final["summary"] = ""
        logger.warning("Final summary looked like review text; cleared summary.")


def sanitize_cv_json_output(
    cv_json: Dict[str, Any],
    *,
    language_code: str = "fr",
) -> None:
    """Sanitize CV JSON by cleaning all text fields.

    Removes placeholders, review markers, and invalid entries.

    Args:
        cv_json: CV JSON to modify in place
        language_code: Language for default labels
    """
    if not isinstance(cv_json, dict):
        return

    fallback_category = "Skills" if language_code == "en" else "Competences"
    def normalize_text_for_match(value: Any) -> str:
        text = str(value or "").strip().casefold()
        if not text:
            return ""
        # Keep Unicode letters (Arabic/Japanese/etc.) so non-Latin labels are preserved.
        text = re.sub(r"[^\w]+", " ", text, flags=re.UNICODE)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def normalize_text_for_role_detection(value: Any) -> str:
        text = str(value or "").strip().casefold()
        if not text:
            return ""
        # Role heuristics use a Latin token list; fold accents for robust matching.
        text = (
            unicodedata.normalize("NFKD", text)
            .encode("ascii", "ignore")
            .decode("ascii")
        )
        text = re.sub(r"[^\w]+", " ", text, flags=re.UNICODE)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    target_job_title_norm = normalize_text_for_match(cv_json.get("target_job_title") or "")
    target_job_title_role_norm = normalize_text_for_role_detection(
        cv_json.get("target_job_title") or ""
    )
    target_job_title_token_set = {
        tok for tok in target_job_title_role_norm.split() if tok
    }

    def has_role_like_title_overlap(label_tokens: Sequence[str]) -> bool:
        if not target_job_title_token_set:
            return False
        label_token_set = {tok for tok in label_tokens if tok}
        if not label_token_set:
            return False
        if label_token_set == target_job_title_token_set:
            return True
        if label_token_set.issubset(target_job_title_token_set):
            return any(tok in ROLE_LIKE_SKILL_TOKENS for tok in label_token_set)
        if target_job_title_token_set.issubset(label_token_set):
            return any(tok in ROLE_LIKE_SKILL_TOKENS for tok in target_job_title_token_set)
        return False

    def is_role_like_phrase(tokens: Sequence[str]) -> bool:
        normalized_tokens = [tok for tok in tokens if tok]
        if not normalized_tokens:
            return False

        role_tokens = [tok for tok in normalized_tokens if tok in ROLE_LIKE_SKILL_TOKENS]
        if not role_tokens:
            return False

        # Ignore tiny glue tokens introduced by punctuation variants:
        # "Ingenieur(e)" -> ["ingenieur", "e"].
        non_role_long_tokens = [
            tok for tok in normalized_tokens if tok not in ROLE_LIKE_SKILL_TOKENS and len(tok) > 2
        ]
        if not non_role_long_tokens and len(normalized_tokens) <= 4:
            return True

        # If phrase clearly overlaps target job title and contains a role token,
        # treat it as role/title wording, not a technical skill.
        if target_job_title_token_set and (
            {tok for tok in normalized_tokens} & target_job_title_token_set
        ):
            return True

        return False

    def normalize_skill_category_label(raw_label: Any) -> str:
        label = clean_text_field(raw_label or "", max_length=80)
        if not label:
            return fallback_category
        label = SKILL_LABEL_PREFIX_PATTERN.sub("", label).strip(" :-")
        label_norm = normalize_text_for_match(label)
        if not label_norm and label.strip():
            # Preserve original non-empty label when Unicode tokenization yields no tokens.
            return label
        if not label_norm:
            return fallback_category

        label_role_norm = normalize_text_for_role_detection(label)
        tokens = [tok for tok in label_role_norm.split() if tok]
        role_like = False
        if target_job_title_norm and (
            label_norm == target_job_title_norm
            or has_role_like_title_overlap(tokens)
        ):
            role_like = True
        elif is_role_like_phrase(tokens):
            role_like = True

        if role_like or len(label) > 40:
            return fallback_category
        return label

    def split_skill_item_candidates(raw_item: str) -> List[str]:
        cleaned = clean_text_field(
            raw_item,
            max_length=220,
            check_review_markers=False,
            dedupe_narrative=False,
        )
        if not cleaned:
            return []

        cleaned = SKILL_LABEL_PREFIX_PATTERN.sub("", cleaned).strip(" :-")
        cleaned = re.sub(r"^[\-\*\d\.\)\(]+\s*", "", cleaned).strip()
        if not cleaned:
            return []

        chunks: List[str] = []
        for chunk in SKILL_SPLIT_PATTERN.split(cleaned):
            part = chunk.strip(" ,:-")
            if not part:
                continue
            # Split comma-separated flat skill lists: "Python, SQL, Airflow"
            if "," in part:
                subparts = [value.strip(" ,:-") for value in part.split(",")]
                subparts = [value for value in subparts if value]
                if len(subparts) >= 2 and all(0 < len(value.split()) <= 4 for value in subparts):
                    chunks.extend(subparts)
                    continue
            chunks.append(part)

        return _dedup_preserve(chunks)

    def is_skill_like_phrase(text: str) -> bool:
        if not text:
            return False
        if any(mark in text for mark in (".", "!", "?", "\n")):
            return False
        if SKILL_SENTENCE_NOISE_PATTERN.search(text):
            return False

        text_norm = normalize_text_for_match(text)
        tokens = [tok for tok in text_norm.split() if tok]
        if not tokens:
            return False
        if len(tokens) > 6:
            return False
        if all(tok in SKILL_GLUE_WORDS for tok in tokens):
            return False
        if len(tokens) == 1:
            token = tokens[0]
            if token in SHORT_TECH_TOKENS:
                return True
            if token in SKILL_GLUE_WORDS:
                return False
            if len(token) < 2:
                return False
        return True

    # Clean top-level text fields
    contact = cv_json.get("contact")
    if isinstance(contact, dict):
        for field in ("full_name", "email", "phone", "linkedin_url", "location"):
            contact[field] = clean_text_field(contact.get(field))

    cv_json["summary"] = clean_text_field(
        cv_json.get("summary") or "",
        dedupe_narrative=True,
    )
    cv_json["target_job_title"] = clean_text_field(cv_json.get("target_job_title") or "")
    cv_json["target_company"] = clean_text_field(cv_json.get("target_company") or "")

    # Clean skills
    cleaned_skills = []
    for category in cv_json.get("skills", []) or []:
        if not isinstance(category, dict):
            continue
        label = normalize_skill_category_label(category.get("category") or "")
        items = category.get("items") or []
        if not isinstance(items, list):
            items = []
        cleaned_items = []
        for item in items:
            if not isinstance(item, str):
                continue
            for candidate in split_skill_item_candidates(item):
                text = clean_text_field(candidate, max_length=80)
                if not text or text_has_review_markers(text):
                    continue
                if not is_skill_like_phrase(text):
                    continue
                text_norm = normalize_text_for_match(text)
                text_role_norm = normalize_text_for_role_detection(text)
                # Filter role titles accidentally emitted as skills.
                if text_role_norm in ROLE_LIKE_SKILL_TOKENS:
                    continue
                item_tokens = [tok for tok in text_role_norm.split() if tok]
                if is_role_like_phrase(item_tokens):
                    continue
                if target_job_title_norm and text_norm == target_job_title_norm:
                    continue
                cleaned_items.append(text)
        cleaned_items = _dedup_preserve(cleaned_items)
        if cleaned_items:
            cleaned_skills.append({
                "category": label or fallback_category,
                "items": cleaned_items,
            })
    merged_skills: List[Dict[str, Any]] = []
    skills_index: Dict[str, int] = {}
    for block in cleaned_skills:
        category_label = str(block.get("category") or fallback_category).strip() or fallback_category
        category_key = normalize_text_for_match(category_label) or category_label.lower()
        items = [
            item for item in (block.get("items") or [])
            if isinstance(item, str) and item.strip()
        ]
        if not items:
            continue
        if category_key not in skills_index:
            skills_index[category_key] = len(merged_skills)
            merged_skills.append(
                {
                    "category": category_label,
                    "items": _dedup_preserve(items),
                }
            )
            continue
        idx = skills_index[category_key]
        existing_items = merged_skills[idx].get("items") or []
        merged_skills[idx]["items"] = _dedup_preserve(
            [*existing_items, *items]
        )

    cv_json["skills"] = merged_skills

    # Clean experience
    cleaned_experience = []
    for entry in cv_json.get("experience", []) or []:
        if not isinstance(entry, dict):
            continue
        cleaned_entry = {
            "title": clean_text_field(entry.get("title") or ""),
            "company": clean_text_field(entry.get("company") or ""),
            "start_date": clean_text_field(entry.get("start_date") or ""),
            "end_date": clean_text_field(entry.get("end_date") or ""),
            "location": clean_text_field(entry.get("location") or ""),
            "summary": clean_text_field(
                entry.get("summary") or "",
                dedupe_narrative=True,
            ),
        }
        highlights = []
        for item in entry.get("highlights", []) or []:
            if isinstance(item, str):
                text = clean_text_field(item, dedupe_narrative=True)
                if text:
                    highlights.append(text)
        cleaned_entry["highlights"] = _dedup_preserve(highlights)
        if any(cleaned_entry.values()) or cleaned_entry["highlights"]:
            cleaned_experience.append(cleaned_entry)
    cv_json["experience"] = cleaned_experience

    # Clean education
    cleaned_education = []
    for entry in cv_json.get("education", []) or []:
        if not isinstance(entry, dict):
            continue
        cleaned_entry = {
            "school": clean_text_field(entry.get("school") or ""),
            "degree": clean_text_field(entry.get("degree") or ""),
            "field_of_study": clean_text_field(entry.get("field_of_study") or ""),
            "start_date": clean_text_field(entry.get("start_date") or ""),
            "end_date": clean_text_field(entry.get("end_date") or ""),
            "location": clean_text_field(entry.get("location") or ""),
            "details": [],
        }
        details = []
        for item in entry.get("details", []) or []:
            if isinstance(item, str):
                text = clean_text_field(item)
                if text:
                    details.append(text)
        cleaned_entry["details"] = _dedup_preserve(details)
        if any(
            cleaned_entry.get(f)
            for f in ("school", "degree", "field_of_study", "start_date", "end_date", "location")
        ) or cleaned_entry["details"]:
            cleaned_education.append(cleaned_entry)
    cv_json["education"] = cleaned_education

    # Clean projects
    cleaned_projects = []
    for entry in cv_json.get("projects", []) or []:
        if not isinstance(entry, dict):
            continue
        cleaned_entry = {
            "name": clean_text_field(entry.get("name") or ""),
            "description": clean_text_field(
                entry.get("description") or "",
                dedupe_narrative=True,
            ),
            "technologies": clean_text_field(entry.get("technologies") or ""),
            "url": clean_text_field(entry.get("url") or ""),
        }
        if any(cleaned_entry.values()):
            cleaned_projects.append(cleaned_entry)
    cv_json["projects"] = cleaned_projects

    # Clean languages
    cleaned_languages = []
    for entry in cv_json.get("languages", []) or []:
        if not isinstance(entry, dict):
            continue
        language = clean_text_field(entry.get("language") or "")
        level = clean_text_field(entry.get("level") or "")
        certification = clean_text_field(entry.get("certification") or "")
        if language:
            cleaned_languages.append(
                {
                    "language": language,
                    "level": level,
                    "certification": certification,
                }
            )
    cv_json["languages"] = cleaned_languages

    # Clean certifications
    cleaned_certs = []
    for entry in cv_json.get("certifications", []) or []:
        if not isinstance(entry, dict):
            continue
        cleaned_entry = {
            "name": clean_text_field(entry.get("name") or ""),
            "organization": clean_text_field(entry.get("organization") or ""),
            "date": clean_text_field(entry.get("date") or ""),
            "url": clean_text_field(entry.get("url") or ""),
        }
        if cleaned_entry.get("name"):
            cleaned_certs.append(cleaned_entry)
    cv_json["certifications"] = cleaned_certs

    # Clean ATS keywords
    if isinstance(cv_json.get("ats_keywords"), list):
        cleaned_keywords = []
        for item in cv_json.get("ats_keywords") or []:
            if isinstance(item, str):
                text = clean_text_field(item)
                if text:
                    cleaned_keywords.append(text)
        cv_json["ats_keywords"] = _dedup_preserve(cleaned_keywords)


def merge_cv_json_missing_sections(
    cv_json_final: Dict[str, Any],
    cv_json_draft: Dict[str, Any],
) -> None:
    """Merge missing sections from draft into final CV JSON.

    Args:
        cv_json_final: Final CV JSON to modify
        cv_json_draft: Draft CV JSON with potential fallback data
    """
    if not isinstance(cv_json_final, dict) or not isinstance(cv_json_draft, dict):
        return

    for key in (
        "skills",
        "experience",
        "education",
        "projects",
        "languages",
        "certifications",
    ):
        if not cv_json_final.get(key) and cv_json_draft.get(key):
            cv_json_final[key] = cv_json_draft[key]
            logger.warning("Final CVJSON missing %s; copied from draft.", key)


def _normalize_for_match(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    text = re.sub(r"[\W_]+", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _token_overlap(left: str, right: str) -> float:
    left_tokens = {tok for tok in _normalize_for_match(left).split() if len(tok) > 2}
    right_tokens = {tok for tok in _normalize_for_match(right).split() if len(tok) > 2}
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / float(max(len(left_tokens), len(right_tokens)))


def _text_similarity(left: str, right: str) -> float:
    left_norm = _normalize_for_match(left)
    right_norm = _normalize_for_match(right)
    if not left_norm or not right_norm:
        return 0.0
    return SequenceMatcher(None, left_norm, right_norm).ratio()


def _is_same_narrative(left: str, right: str) -> bool:
    left_norm = _normalize_for_match(left)
    right_norm = _normalize_for_match(right)
    if not left_norm or not right_norm:
        return False
    if left_norm == right_norm:
        return True
    if len(left_norm) >= 40 and left_norm in right_norm:
        return True
    if len(right_norm) >= 40 and right_norm in left_norm:
        return True
    return _token_overlap(left, right) >= 0.9


_CORPORATE_DESCRIPTION_HINTS = (
    " est ",
    " is ",
    "offre",
    "offres",
    "services",
    "service",
    "plateforme",
    "platform",
    "propose",
    "provides",
    "permet",
    "allows",
    "mission",
    "strategie",
    "strategy",
    "groupe",
    "group",
    "entreprise",
    "company",
    "filiale",
    "subsidiary",
    "leader",
)

_ACTION_EXPERIENCE_HINTS = (
    "managed",
    "developed",
    "implemented",
    "built",
    "designed",
    "led",
    "supported",
    "collaborated",
    "tested",
    "coordinated",
    "created",
    "analyzed",
    "improved",
    "delivered",
    "gere",
    "geree",
    "developpe",
    "realise",
    "mis en oeuvre",
    "contribue",
    "pilote",
    "assure",
    "coordonne",
    "analyse",
    "ameliore",
)


def _looks_like_company_description(text: str, company: str = "") -> bool:
    normalized = _normalize_for_match(text)
    if not normalized or len(normalized) < 50:
        return False

    company_norm = _normalize_for_match(company)
    corporate_hits = sum(
        1 for marker in _CORPORATE_DESCRIPTION_HINTS if marker in normalized
    )
    action_hits = sum(
        1 for marker in _ACTION_EXPERIENCE_HINTS if marker in normalized
    )

    company_as_subject = False
    if company_norm:
        if normalized.startswith(f"{company_norm} "):
            company_as_subject = True
        if company_norm in normalized and (
            " est " in normalized
            or " is " in normalized
            or " propose " in normalized
            or " provides " in normalized
            or " permet " in normalized
        ):
            company_as_subject = True

    if action_hits >= 2 and corporate_hits <= 1:
        return False
    if company_as_subject and corporate_hits >= 1:
        return True
    if corporate_hits >= 3 and action_hits == 0:
        return True
    return False


def _select_action_summary(
    summary: str,
    *,
    highlights: List[str],
    fallback_description: str,
    company: str,
) -> str:
    summary_text = clean_narrative_text(summary or "")
    if summary_text and not _looks_like_company_description(summary_text, company):
        return _trim_text(summary_text, 420)

    for item in highlights:
        text = clean_narrative_text(item)
        if not text:
            continue
        if _looks_like_company_description(text, company):
            continue
        return _trim_text(text, 280)

    fallback_text = clean_narrative_text(fallback_description or "")
    if fallback_text and not _looks_like_company_description(fallback_text, company):
        return _trim_text(fallback_text, 420)

    return ""


def _extract_profile_experiences(profile_json: Dict[str, Any]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    if not isinstance(profile_json, dict):
        return rows
    for item in profile_json.get("experiences") or []:
        if not isinstance(item, dict):
            continue
        row = {
            "title": clean_text_field(item.get("title") or ""),
            "company": clean_text_field(item.get("company") or ""),
            "start_date": clean_text_field(item.get("start_date") or ""),
            "end_date": clean_text_field(item.get("end_date") or ""),
            "location": clean_text_field(item.get("location") or ""),
            "description": clean_text_field(
                item.get("description") or "",
                check_review_markers=False,
                dedupe_narrative=True,
            ),
        }
        if not any(
            row.get(field)
            for field in ("title", "company", "start_date", "end_date", "location", "description")
        ):
            continue
        row["_title_norm"] = _normalize_for_match(row["title"])
        row["_company_norm"] = _normalize_for_match(row["company"])
        row["_start_norm"] = _normalize_for_match(row["start_date"])
        row["_end_norm"] = _normalize_for_match(row["end_date"])
        rows.append(row)
    return rows


def _score_profile_experience_match(entry: Dict[str, Any], profile_entry: Dict[str, Any]) -> float:
    score = 0.0

    title_norm = _normalize_for_match(entry.get("title"))
    company_norm = _normalize_for_match(entry.get("company"))
    start_norm = _normalize_for_match(entry.get("start_date"))
    end_norm = _normalize_for_match(entry.get("end_date"))

    profile_title = profile_entry.get("_title_norm", "")
    profile_company = profile_entry.get("_company_norm", "")
    profile_start = profile_entry.get("_start_norm", "")
    profile_end = profile_entry.get("_end_norm", "")

    if title_norm and profile_title:
        if title_norm == profile_title:
            score += 0.65
        else:
            score += 0.35 * _text_similarity(title_norm, profile_title)

    if company_norm and profile_company:
        if company_norm == profile_company:
            score += 0.60
        else:
            score += 0.30 * _text_similarity(company_norm, profile_company)

    if start_norm and profile_start and start_norm == profile_start:
        score += 0.12
    if end_norm and profile_end and end_norm == profile_end:
        score += 0.12

    return score


def _reconcile_experience_section(cv_json: Dict[str, Any], profile_json: Dict[str, Any]) -> None:
    if not isinstance(cv_json, dict):
        return
    experience_entries = cv_json.get("experience")
    if not isinstance(experience_entries, list):
        return

    profile_experiences = _extract_profile_experiences(profile_json)
    if not profile_experiences:
        return

    reconciled: List[Dict[str, Any]] = []
    reassigned_count = 0

    for raw_entry in experience_entries:
        if not isinstance(raw_entry, dict):
            continue

        entry = {
            "title": clean_text_field(raw_entry.get("title") or ""),
            "company": clean_text_field(raw_entry.get("company") or ""),
            "start_date": clean_text_field(raw_entry.get("start_date") or ""),
            "end_date": clean_text_field(raw_entry.get("end_date") or ""),
            "location": clean_text_field(raw_entry.get("location") or ""),
            "summary": clean_text_field(
                raw_entry.get("summary") or "",
                dedupe_narrative=True,
            ),
            "highlights": [],
        }

        highlights: List[str] = []
        for value in raw_entry.get("highlights") or []:
            if not isinstance(value, str):
                continue
            text = clean_text_field(value, dedupe_narrative=True)
            if text:
                highlights.append(text)
        highlights = _dedup_preserve(highlights)

        best_idx = -1
        best_score = 0.0
        for idx, profile_entry in enumerate(profile_experiences):
            score = _score_profile_experience_match(entry, profile_entry)
            if score > best_score:
                best_score = score
                best_idx = idx

        matched_profile = profile_experiences[best_idx] if best_idx >= 0 and best_score >= 0.45 else None
        expected_description = ""
        if matched_profile:
            expected_description = matched_profile.get("description") or ""
            for field in ("title", "company", "start_date", "end_date", "location"):
                if not entry.get(field) and matched_profile.get(field):
                    entry[field] = matched_profile[field]

        if expected_description:
            if not entry["summary"]:
                entry["summary"] = _select_action_summary(
                    "",
                    highlights=highlights,
                    fallback_description=expected_description,
                    company=entry.get("company") or "",
                )
            else:
                current_summary = entry["summary"]
                expected_overlap = _token_overlap(current_summary, expected_description)
                other_overlap = 0.0
                other_company_hit = False
                summary_norm = _normalize_for_match(current_summary)
                for idx, other in enumerate(profile_experiences):
                    if idx == best_idx:
                        continue
                    other_description = other.get("description") or ""
                    if other_description:
                        other_overlap = max(other_overlap, _token_overlap(current_summary, other_description))
                    other_company_norm = other.get("_company_norm", "")
                    if other_company_norm and other_company_norm in summary_norm:
                        other_company_hit = True

                if other_company_hit or (
                    other_overlap >= 0.42 and other_overlap > (expected_overlap + 0.12)
                ):
                    entry["summary"] = _select_action_summary(
                        "",
                        highlights=highlights,
                        fallback_description=expected_description,
                        company=entry.get("company") or "",
                    )
                    highlights = extract_experience_highlights(expected_description)
                    reassigned_count += 1

            if highlights:
                highlight_blob = " ".join(highlights)
                expected_overlap = _token_overlap(highlight_blob, expected_description)
                other_overlap = 0.0
                for idx, other in enumerate(profile_experiences):
                    if idx == best_idx:
                        continue
                    other_description = other.get("description") or ""
                    if other_description:
                        other_overlap = max(other_overlap, _token_overlap(highlight_blob, other_description))
                if other_overlap >= 0.42 and other_overlap > (expected_overlap + 0.12):
                    highlights = extract_experience_highlights(expected_description)

        summary_text = _select_action_summary(
            entry.get("summary") or "",
            highlights=highlights,
            fallback_description=expected_description,
            company=entry.get("company") or "",
        )
        summary_norm = _normalize_for_match(summary_text)
        cleaned_highlights: List[str] = []
        for highlight in highlights:
            text = clean_narrative_text(highlight)
            if not text:
                continue
            if _looks_like_company_description(text, entry.get("company") or ""):
                continue
            if summary_norm and _is_same_narrative(summary_text, text):
                continue
            cleaned_highlights.append(text)

        entry["summary"] = _trim_text(summary_text, 420)
        entry["highlights"] = _dedup_preserve(cleaned_highlights)[:4]

        if any(
            entry.get(field) for field in ("title", "company", "start_date", "end_date", "location", "summary")
        ) or entry["highlights"]:
            reconciled.append(entry)

    cv_json["experience"] = reconciled
    if reassigned_count:
        logger.warning("Experience reconciliation fixed %s likely misassigned summaries.", reassigned_count)


def _extract_profile_education(profile_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not isinstance(profile_json, dict):
        return rows

    for item in profile_json.get("education") or []:
        if not isinstance(item, dict):
            continue
        details: List[str] = []
        raw_details = item.get("details")
        if isinstance(raw_details, list):
            for value in raw_details:
                if isinstance(value, str):
                    text = clean_text_field(value, check_review_markers=False, dedupe_narrative=True)
                    if text:
                        details.append(text)
        description_text = item.get("description")
        if isinstance(description_text, str) and description_text.strip():
            text = clean_text_field(description_text, check_review_markers=False, dedupe_narrative=True)
            if text:
                details.append(text)
        grade_text = item.get("grade")
        if isinstance(grade_text, str) and grade_text.strip():
            details.append(grade_text.strip())

        row = {
            "school": clean_text_field(item.get("school") or "", check_review_markers=False),
            "degree": clean_text_field(item.get("degree") or "", check_review_markers=False),
            "field_of_study": clean_text_field(item.get("field_of_study") or "", check_review_markers=False),
            "start_date": clean_text_field(item.get("start_date") or "", check_review_markers=False),
            "end_date": clean_text_field(item.get("end_date") or "", check_review_markers=False),
            "location": clean_text_field(item.get("location") or "", check_review_markers=False),
            "details": _dedup_preserve(details)[:4],
        }
        if not any(
            row.get(field)
            for field in ("school", "degree", "field_of_study", "start_date", "end_date", "location")
        ) and not row["details"]:
            continue
        row["_school_norm"] = _normalize_for_match(row["school"])
        row["_degree_norm"] = _normalize_for_match(row["degree"])
        row["_start_norm"] = _normalize_for_match(row["start_date"])
        row["_end_norm"] = _normalize_for_match(row["end_date"])
        rows.append(row)

    return rows


def _score_profile_education_match(entry: Dict[str, Any], profile_entry: Dict[str, Any]) -> float:
    score = 0.0

    school_norm = _normalize_for_match(entry.get("school"))
    degree_norm = _normalize_for_match(entry.get("degree"))
    start_norm = _normalize_for_match(entry.get("start_date"))
    end_norm = _normalize_for_match(entry.get("end_date"))

    profile_school = profile_entry.get("_school_norm", "")
    profile_degree = profile_entry.get("_degree_norm", "")
    profile_start = profile_entry.get("_start_norm", "")
    profile_end = profile_entry.get("_end_norm", "")

    if school_norm and profile_school:
        if school_norm == profile_school:
            score += 0.65
        else:
            score += 0.30 * _text_similarity(school_norm, profile_school)

    if degree_norm and profile_degree:
        if degree_norm == profile_degree:
            score += 0.55
        else:
            score += 0.25 * _text_similarity(degree_norm, profile_degree)

    if start_norm and profile_start and start_norm == profile_start:
        score += 0.12
    if end_norm and profile_end and end_norm == profile_end:
        score += 0.12

    return score


def _education_identity(entry: Dict[str, Any]) -> str:
    parts = (
        _normalize_for_match(entry.get("school")),
        _normalize_for_match(entry.get("degree")),
        _normalize_for_match(entry.get("start_date")),
        _normalize_for_match(entry.get("end_date")),
    )
    key = "|".join(parts).strip("|")
    if key:
        return key
    return _normalize_for_match(entry.get("field_of_study"))


def _reconcile_education_section(cv_json: Dict[str, Any], profile_json: Dict[str, Any]) -> None:
    if not isinstance(cv_json, dict):
        return
    current_entries = cv_json.get("education")
    if not isinstance(current_entries, list):
        current_entries = []

    profile_education = _extract_profile_education(profile_json)
    if not profile_education:
        return

    reconciled: List[Dict[str, Any]] = []
    used_profile_indices: set = set()
    appended_count = 0

    for raw_entry in current_entries:
        if not isinstance(raw_entry, dict):
            continue
        entry = {
            "school": clean_text_field(raw_entry.get("school") or ""),
            "degree": clean_text_field(raw_entry.get("degree") or ""),
            "field_of_study": clean_text_field(raw_entry.get("field_of_study") or ""),
            "start_date": clean_text_field(raw_entry.get("start_date") or ""),
            "end_date": clean_text_field(raw_entry.get("end_date") or ""),
            "location": clean_text_field(raw_entry.get("location") or ""),
            "details": [],
        }

        details: List[str] = []
        for value in raw_entry.get("details") or []:
            if isinstance(value, str):
                text = clean_text_field(value, dedupe_narrative=True)
                if text:
                    details.append(text)
        entry["details"] = _dedup_preserve(details)[:4]

        best_idx = -1
        best_score = 0.0
        for idx, profile_entry in enumerate(profile_education):
            score = _score_profile_education_match(entry, profile_entry)
            if score > best_score:
                best_score = score
                best_idx = idx

        if best_idx >= 0 and best_score >= 0.45:
            used_profile_indices.add(best_idx)
            matched = profile_education[best_idx]
            for field in ("school", "degree", "field_of_study", "start_date", "end_date", "location"):
                if not entry.get(field) and matched.get(field):
                    entry[field] = matched[field]
            merged_details = _dedup_preserve((entry.get("details") or []) + (matched.get("details") or []))
            entry["details"] = merged_details[:4]

        if any(
            entry.get(field)
            for field in ("school", "degree", "field_of_study", "start_date", "end_date", "location")
        ) or entry["details"]:
            reconciled.append(entry)

    for idx, profile_entry in enumerate(profile_education):
        if idx in used_profile_indices:
            continue
        addition = {
            "school": profile_entry.get("school") or "",
            "degree": profile_entry.get("degree") or "",
            "field_of_study": profile_entry.get("field_of_study") or "",
            "start_date": profile_entry.get("start_date") or "",
            "end_date": profile_entry.get("end_date") or "",
            "location": profile_entry.get("location") or "",
            "details": profile_entry.get("details") or [],
        }
        if any(
            addition.get(field)
            for field in ("school", "degree", "field_of_study", "start_date", "end_date", "location")
        ) or addition["details"]:
            reconciled.append(addition)
            appended_count += 1

    deduped: List[Dict[str, Any]] = []
    seen_keys: set = set()
    for entry in reconciled:
        key = _education_identity(entry)
        if key and key in seen_keys:
            continue
        if key:
            seen_keys.add(key)
        deduped.append(entry)

    cv_json["education"] = deduped
    if appended_count:
        logger.warning("Education reconciliation appended %s missing profile entries.", appended_count)


def _extract_profile_languages(profile_json: Dict[str, Any]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    if not isinstance(profile_json, dict):
        return rows
    for item in profile_json.get("languages") or []:
        if not isinstance(item, dict):
            continue
        language = clean_text_field(item.get("language") or item.get("name") or "")
        level = clean_text_field(item.get("level") or item.get("proficiency") or "")
        certification = clean_text_field(
            item.get("certification")
            or item.get("certificate")
            or item.get("organization")
            or item.get("issuer")
            or ""
        )
        if not language:
            continue
        rows.append(
            {
                "language": language,
                "level": level,
                "certification": certification,
                "_language_norm": _normalize_for_match(language),
            }
        )
    return rows


def _reconcile_languages_section(cv_json: Dict[str, Any], profile_json: Dict[str, Any]) -> None:
    if not isinstance(cv_json, dict):
        return
    current_entries = cv_json.get("languages")
    if not isinstance(current_entries, list):
        current_entries = []

    profile_languages = _extract_profile_languages(profile_json)
    profile_map: Dict[str, Dict[str, str]] = {}
    profile_order: List[str] = []
    for entry in profile_languages:
        key = entry.get("_language_norm") or ""
        if not key:
            continue
        if key not in profile_map:
            profile_map[key] = {
                "language": entry.get("language") or "",
                "level": entry.get("level") or "",
                "certification": entry.get("certification") or "",
            }
            profile_order.append(key)
            continue
        existing = profile_map[key]
        if not existing.get("level") and entry.get("level"):
            existing["level"] = entry["level"]
        if not existing.get("certification") and entry.get("certification"):
            existing["certification"] = entry["certification"]
        if len(entry.get("language") or "") > len(existing.get("language") or ""):
            existing["language"] = entry.get("language") or existing.get("language") or ""

    reconciled: List[Dict[str, str]] = []
    seen: set = set()
    appended_count = 0

    for raw_entry in current_entries:
        if not isinstance(raw_entry, dict):
            continue
        language = clean_text_field(raw_entry.get("language") or raw_entry.get("name") or "")
        if not language:
            continue
        key = _normalize_for_match(language)
        if not key or key in seen:
            continue

        level = clean_text_field(raw_entry.get("level") or raw_entry.get("proficiency") or "")
        certification = clean_text_field(
            raw_entry.get("certification")
            or raw_entry.get("certificate")
            or raw_entry.get("organization")
            or raw_entry.get("issuer")
            or ""
        )

        profile_entry = profile_map.get(key)
        if profile_entry:
            language = profile_entry.get("language") or language
            level = level or profile_entry.get("level") or ""
            certification = certification or profile_entry.get("certification") or ""

        reconciled.append(
            {
                "language": language,
                "level": level,
                "certification": certification,
            }
        )
        seen.add(key)

    for key in profile_order:
        if key in seen:
            continue
        entry = profile_map[key]
        reconciled.append(
            {
                "language": entry.get("language") or "",
                "level": entry.get("level") or "",
                "certification": entry.get("certification") or "",
            }
        )
        seen.add(key)
        appended_count += 1

    cv_json["languages"] = reconciled[:4]
    if appended_count:
        logger.warning("Language reconciliation appended %s missing profile entries.", appended_count)


def reconcile_cv_sections_with_profile(cv_json: Dict[str, Any], profile_json: Dict[str, Any]) -> None:
    if not isinstance(cv_json, dict) or not isinstance(profile_json, dict):
        return
    _reconcile_experience_section(cv_json, profile_json)
    _reconcile_education_section(cv_json, profile_json)
    _reconcile_languages_section(cv_json, profile_json)


_SUMMARY_CONTACT_PATTERNS = (
    re.compile(r"(?i)\bcontact(?: details?)?\s*:\s*"),
    re.compile(r"(?i)\b(?:email|e-mail)\s*:\s*[\w\.\-+%]+@[\w\.\-]+\.\w+"),
    re.compile(r"(?i)\b(?:phone|tel|telephone|mobile)\s*:\s*[+\d][\d\-\s\(\)\.]{6,}"),
    re.compile(r"(?i)\blinkedin(?:_url)?\s*:\s*\S+"),
    re.compile(r"(?i)https?://(?:www\.)?linkedin\.com/\S+"),
)


def _strip_contact_blobs_from_summary(text: str) -> str:
    cleaned = str(text or "").strip()
    if not cleaned:
        return ""
    for pattern in _SUMMARY_CONTACT_PATTERNS:
        cleaned = pattern.sub("", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,;:-")
    return cleaned


def _split_sentences(text: str) -> List[str]:
    cleaned = clean_narrative_text(text or "")
    if not cleaned:
        return []
    parts = re.split(r"(?<=[\.\!\?])\s+|\n+", cleaned)
    return [part.strip(" \t\r\n-") for part in parts if part and part.strip()]


def _best_profile_match(
    entry: Dict[str, Any],
    profile_experiences: List[Dict[str, str]],
) -> Optional[Dict[str, str]]:
    best_score = 0.0
    best_entry: Optional[Dict[str, str]] = None
    for candidate in profile_experiences:
        score = _score_profile_experience_match(entry, candidate)
        if score > best_score:
            best_score = score
            best_entry = candidate
    if best_score >= 0.35:
        return best_entry
    return None


def _seed_experience_from_profile(
    cv_json: Dict[str, Any],
    profile_json: Dict[str, Any],
) -> int:
    if not isinstance(cv_json, dict):
        return 0
    existing = cv_json.get("experience")
    if isinstance(existing, list) and existing:
        return 0

    seeded: List[Dict[str, Any]] = []
    for item in _extract_profile_experiences(profile_json)[:4]:
        fallback_description = item.get("description") or ""
        summary = _select_action_summary(
            "",
            highlights=[],
            fallback_description=fallback_description,
            company=item.get("company") or "",
        )
        highlights = _dedup_preserve(
            [
                clean_narrative_text(value)
                for value in extract_experience_highlights(fallback_description)
                if clean_narrative_text(value)
            ]
        )[:4]
        if summary and highlights and _is_same_narrative(summary, highlights[0]):
            highlights = highlights[1:]

        seeded.append(
            {
                "title": item.get("title") or "",
                "company": item.get("company") or "",
                "start_date": item.get("start_date") or "",
                "end_date": item.get("end_date") or "",
                "location": item.get("location") or "",
                "summary": _trim_text(summary, 280),
                "highlights": highlights[:4],
            }
        )

    if seeded:
        cv_json["experience"] = seeded
    return len(seeded)


def rebalance_cv_narrative(
    cv_json: Dict[str, Any],
    *,
    profile_json: Dict[str, Any],
) -> None:
    """Rebalance narrative density between summary and experience bullets.

    This deterministic pass addresses weak generations where model output
    collapses most content into one long summary paragraph while experience
    bullets stay sparse.
    """
    if not isinstance(cv_json, dict):
        return

    profile_experiences = _extract_profile_experiences(profile_json)

    summary = _strip_contact_blobs_from_summary(cv_json.get("summary") or "")
    summary = clean_narrative_text(summary)
    summary_sentences = _split_sentences(summary)
    summary_overflow: List[str] = []

    if summary and (len(summary) > 420 or len(summary_sentences) > 4):
        kept: List[str] = []
        length_budget = 0
        for sentence in summary_sentences:
            projected = length_budget + len(sentence) + (1 if kept else 0)
            if len(kept) < 3 and projected <= 420:
                kept.append(sentence)
                length_budget = projected
            else:
                summary_overflow.append(sentence)
        if not kept:
            kept = [_trim_text(summary, 420)]
        cv_json["summary"] = " ".join(kept).strip()
    else:
        cv_json["summary"] = _trim_text(summary, 420)

    seeded_count = _seed_experience_from_profile(cv_json, profile_json)
    if seeded_count:
        logger.info("Experience section rebuilt from profile data: entries=%s", seeded_count)

    experience_entries = cv_json.get("experience")
    if not isinstance(experience_entries, list):
        return

    synthesized_highlights = 0
    for entry in experience_entries:
        if not isinstance(entry, dict):
            continue

        entry_summary = _strip_contact_blobs_from_summary(entry.get("summary") or "")
        entry_summary = clean_narrative_text(entry_summary)
        entry_sentences = _split_sentences(entry_summary)
        entry_overflow: List[str] = []
        if entry_summary and (len(entry_summary) > 300 or len(entry_sentences) > 3):
            kept = entry_sentences[:2]
            entry_overflow = entry_sentences[2:]
            entry_summary = _trim_text(" ".join(kept), 280) if kept else _trim_text(entry_summary, 280)
        else:
            entry_summary = _trim_text(entry_summary, 280)

        highlights: List[str] = []
        for value in entry.get("highlights") or []:
            if not isinstance(value, str):
                continue
            text = clean_narrative_text(value)
            if not text:
                continue
            highlights.append(text)
        highlights = _dedup_preserve(highlights)

        matched_profile = _best_profile_match(entry, profile_experiences)
        profile_description = matched_profile.get("description") if isinstance(matched_profile, dict) else ""

        if not entry_summary and profile_description:
            entry_summary = _select_action_summary(
                "",
                highlights=highlights,
                fallback_description=profile_description,
                company=str(entry.get("company") or ""),
            )

        highlight_candidates: List[str] = []
        highlight_candidates.extend(entry_overflow)
        if profile_description:
            highlight_candidates.extend(extract_experience_highlights(profile_description))
        if not highlight_candidates and entry_sentences:
            highlight_candidates.extend(entry_sentences[1:])

        for candidate in highlight_candidates:
            text = clean_narrative_text(candidate)
            if not text:
                continue
            if entry_summary and _is_same_narrative(entry_summary, text):
                continue
            if _looks_like_company_description(text, str(entry.get("company") or "")):
                continue
            highlights.append(text)

        highlights = _dedup_preserve(highlights)
        if len(highlights) < 2 and profile_description:
            for candidate in extract_experience_highlights(profile_description):
                text = clean_narrative_text(candidate)
                if not text:
                    continue
                if entry_summary and _is_same_narrative(entry_summary, text):
                    continue
                highlights.append(text)
                if len(_dedup_preserve(highlights)) >= 2:
                    break
            highlights = _dedup_preserve(highlights)

        original_highlights = entry.get("highlights")
        original_count = len(original_highlights) if isinstance(original_highlights, list) else 0
        if highlights:
            synthesized_highlights += max(0, len(highlights) - original_count)

        if not entry_summary and highlights:
            entry_summary = _trim_text(highlights[0], 220)

        entry["summary"] = _trim_text(entry_summary, 280)
        entry["highlights"] = highlights[:4]

        if isinstance(matched_profile, dict):
            for field in ("title", "company", "start_date", "end_date", "location"):
                if not entry.get(field) and matched_profile.get(field):
                    entry[field] = matched_profile.get(field)

    if summary_overflow and experience_entries:
        first = experience_entries[0] if isinstance(experience_entries[0], dict) else None
        if isinstance(first, dict):
            first_highlights = first.get("highlights")
            if not isinstance(first_highlights, list):
                first_highlights = []
            for sentence in summary_overflow:
                text = clean_narrative_text(sentence)
                if not text:
                    continue
                if first.get("summary") and _is_same_narrative(first.get("summary"), text):
                    continue
                first_highlights.append(text)
            first["highlights"] = _dedup_preserve(first_highlights)[:4]

    if summary_overflow:
        logger.info(
            "Summary rebalanced into experience bullets: moved_sentences=%s",
            len(summary_overflow),
        )
    if synthesized_highlights > 0:
        logger.info(
            "Experience highlights synthesized from profile/generated text: added=%s",
            synthesized_highlights,
        )


def coerce_generated_cv_payload(
    *,
    payload: Dict[str, Any],
    profile_json: Dict[str, Any],
    fallback_generator: Callable[[Dict[str, Any], str], Dict[str, Any]],
    critic_json: Optional[Dict[str, Any]] = None,
    job_title: str = "",
    company: str = "",
    profile_name: str = "",
    profile_email: str = "",
    profile_phone: str = "",
    profile_linkedin: str = "",
    language_code: str = "fr",
    keyword_alignment_fn: Optional[Callable[[Dict[str, Any], Optional[Dict[str, Any]]], None]] = None,
    offer_adaptation_fn: Optional[Callable[[Dict[str, Any], Optional[Dict[str, Any]]], None]] = None,
) -> Dict[str, Any]:
    """Merge partial/invalid generated payload onto a valid skeleton.

    This ensures the output always has valid structure even when
    the LLM produces incomplete or malformed JSON.

    Args:
        payload: Generated CV JSON (may be partial)
        profile_json: Source profile data
        fallback_generator: Function to generate fallback CV JSON
        critic_json: Optional critic analysis
        job_title: Target job title
        company: Target company
        profile_name: Profile name for fallback
        profile_email: Profile email for fallback
        profile_phone: Profile phone for fallback
        profile_linkedin: Profile LinkedIn for fallback
        language_code: Language code for labels
        keyword_alignment_fn: Optional function to apply keyword alignment
        offer_adaptation_fn: Optional function to enforce offer adaptation

    Returns:
        Merged and validated CV JSON
    """
    # Generate deterministic base
    base = fallback_generator(profile_json, "")
    if not isinstance(base, dict):
        base = {}
    if not isinstance(payload, dict):
        payload = {}

    merged: Dict[str, Any] = dict(base)

    # Merge top-level text fields
    for key in ("schema_version", "summary", "target_job_title", "target_company"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            merged[key] = value.strip()

    # Merge contact
    incoming_contact = payload.get("contact")
    contact = dict(merged.get("contact") or {}) if isinstance(merged.get("contact"), dict) else {}
    if isinstance(incoming_contact, dict):
        for field in ("full_name", "email", "phone", "linkedin_url", "location"):
            value = incoming_contact.get(field)
            if isinstance(value, str) and value.strip():
                contact[field] = value.strip()
    merged["contact"] = contact

    # Merge list sections
    list_sections = (
        "skills",
        "experience",
        "education",
        "projects",
        "languages",
        "certifications",
        "ats_keywords",
    )
    for key in list_sections:
        value = payload.get(key)
        if isinstance(value, list) and value:
            merged[key] = value

    # Merge render hints
    render_hints = payload.get("render_hints")
    if isinstance(render_hints, dict) and render_hints:
        merged["render_hints"] = render_hints

    # Apply fallbacks
    apply_contact_fallback(
        merged,
        profile_json,
        profile_name=profile_name,
        profile_email=profile_email,
        profile_phone=profile_phone,
        profile_linkedin=profile_linkedin,
    )
    apply_target_fallback(merged, job_title=job_title, company=company)

    # Sanitize
    sanitize_cv_json_output(merged, language_code=language_code)
    reconcile_cv_sections_with_profile(merged, profile_json)

    # Apply keyword alignment if provided
    if keyword_alignment_fn:
        keyword_alignment_fn(merged, critic_json)

    # Apply offer adaptation if provided
    if offer_adaptation_fn:
        offer_adaptation_fn(merged, critic_json)

    # Deterministic quality pass: avoid overstuffed summary + empty bullets.
    rebalance_cv_narrative(
        merged,
        profile_json=profile_json,
    )

    # Re-sanitize after optional post-merge transformations.
    sanitize_cv_json_output(merged, language_code=language_code)
    reconcile_cv_sections_with_profile(merged, profile_json)

    return merged


def extract_experience_highlights(description: str) -> List[str]:
    """Extract bullet-point highlights from experience description.

    Args:
        description: Experience description text

    Returns:
        List of highlight strings
    """
    if not description:
        return []

    highlights: List[str] = []
    for part in re.split(r"[\r\n]+|(?<=[\.\!\?])\s+", description):
        cleaned = part.strip(" -*\t")
        if cleaned:
            highlights.append(cleaned)

    return _dedup_preserve(highlights)[:3]


def rank_experiences_by_relevance(
    experiences: List[Dict[str, Any]],
    offer_keywords: List[str],
    job_title: str = "",
) -> List[Dict[str, Any]]:
    """Rank experiences by relevance to job offer.

    Args:
        experiences: List of experience dicts
        offer_keywords: Keywords from job offer
        job_title: Target job title

    Returns:
        Experiences sorted by relevance score
    """
    from .keyword_alignment import normalize_keyword_for_match

    if not experiences or not offer_keywords:
        return experiences

    ranked: List[Tuple[float, int, Dict[str, Any]]] = []
    role_norm = normalize_keyword_for_match(job_title)
    normalized_keywords = [
        normalize_keyword_for_match(item) for item in offer_keywords[:20]
    ]
    normalized_keywords = [item for item in normalized_keywords if item]

    for idx, item in enumerate(experiences):
        if not isinstance(item, dict):
            continue
        blob = " ".join(
            str(item.get(field) or "")
            for field in ("title", "company", "description", "summary")
        )
        norm_blob = normalize_keyword_for_match(blob)
        score = 0.0
        for kw in normalized_keywords:
            if kw in norm_blob:
                score += 2.0 if " " in kw else 1.0
        if role_norm and role_norm in norm_blob:
            score += 2.5
        ranked.append((score, -idx, item))

    ranked.sort(key=lambda payload: (-payload[0], payload[1]))
    return [payload[2] for payload in ranked]


# =============================================================================
# Sprint 8.3: CV Offer Adaptation Enforcement (extracted from CVGenerationWorker)
# =============================================================================


def enforce_cv_offer_adaptation(
    cv_json: Dict[str, Any],
    *,
    job_title: str = "",
    company: str = "",
    aligned_terms: List[str],
    missing_summary_terms: List[str],
    missing_experience_terms: List[str],
    language_code: str = "fr",
    profile_json: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Enforce CV adaptation to job offer requirements.

    This function ensures the CV summary and experience sections
    contain references to the target job title, company, and aligned keywords.

    Args:
        cv_json: CV JSON dictionary (modified in place)
        job_title: Target job title
        company: Target company name
        aligned_terms: List of offer-aligned keyword terms
        missing_summary_terms: Terms missing from summary
        missing_experience_terms: Terms missing from experience
        language_code: Language code for generated text

    Returns:
        The modified cv_json
    """
    if not isinstance(cv_json, dict):
        return cv_json

    try:
        from .keyword_alignment import normalize_keyword_for_match
    except Exception:
        return cv_json

    is_en = language_code == "en"

    # Enforce job title and company in summary
    summary = str(cv_json.get("summary") or "").strip()
    summary_norm = normalize_keyword_for_match(summary)
    summary_additions: List[str] = []

    if job_title and normalize_keyword_for_match(job_title) not in summary_norm:
        summary_additions.append(
            f"Target role: {job_title}." if is_en else f"Poste cible: {job_title}."
        )

    if company and normalize_keyword_for_match(company) not in summary_norm:
        summary_additions.append(
            f"Target company: {company}." if is_en else f"Entreprise cible: {company}."
        )

    # Add missing aligned terms to summary
    missing_summary_terms = missing_summary_terms[:3]
    if missing_summary_terms:
        summary_additions.append(
            f"Offer-aligned strengths: {', '.join(missing_summary_terms)}."
            if is_en
            else f"Forces alignees offre: {', '.join(missing_summary_terms)}."
        )

    if summary_additions:
        summary = (
            f"{summary} {' '.join(summary_additions)}".strip()
            if summary
            else " ".join(summary_additions)
        )
        cv_json["summary"] = clean_narrative_text(summary)

    # Add missing keywords to experience bullets with profile-grounded phrasing
    experience_entries = [
        item for item in (cv_json.get("experience") or []) if isinstance(item, dict)
    ]
    if experience_entries and missing_experience_terms:
        profile_experiences = _extract_profile_experiences(profile_json or {})

        def entry_probe(entry: Dict[str, Any]) -> str:
            parts: List[str] = []
            for key in ("title", "company", "summary"):
                value = entry.get(key)
                if isinstance(value, str) and value.strip():
                    parts.append(value)
            highlights = entry.get("highlights")
            if isinstance(highlights, list):
                for item in highlights:
                    if isinstance(item, str) and item.strip():
                        parts.append(item)
            return " ".join(parts)

        def choose_target_entry(term_norm: str) -> Tuple[Dict[str, Any], Optional[Dict[str, str]]]:
            best_idx = 0
            best_score = -1.0
            best_profile: Optional[Dict[str, str]] = None

            for idx, entry in enumerate(experience_entries):
                score = 0.0
                probe_norm = normalize_keyword_for_match(entry_probe(entry))
                if term_norm and term_norm in probe_norm:
                    score += 6.0
                if entry.get("summary"):
                    score += 1.0
                highlights = entry.get("highlights")
                if isinstance(highlights, list):
                    score += min(2.0, 0.4 * len(highlights))
                matched_profile = _best_profile_match(entry, profile_experiences)
                if isinstance(matched_profile, dict):
                    score += 0.5
                    profile_desc_norm = normalize_keyword_for_match(
                        matched_profile.get("description") or ""
                    )
                    if term_norm and term_norm in profile_desc_norm:
                        score += 2.5
                if score > best_score:
                    best_score = score
                    best_idx = idx
                    best_profile = matched_profile

            return experience_entries[best_idx], best_profile

        def build_keyword_bullet(
            entry: Dict[str, Any],
            keyword: str,
            profile_hint: Optional[Dict[str, str]],
        ) -> str:
            keyword_text = str(keyword or "").strip()
            keyword_norm = normalize_keyword_for_match(keyword_text)
            if not keyword_text or not keyword_norm:
                return ""

            context_candidates: List[str] = []
            if isinstance(profile_hint, dict):
                profile_desc = str(profile_hint.get("description") or "").strip()
                context_candidates.extend(extract_experience_highlights(profile_desc))

            context_candidates.extend(_split_sentences(str(entry.get("summary") or "")))
            highlights = entry.get("highlights")
            if isinstance(highlights, list):
                for item in highlights:
                    if isinstance(item, str) and item.strip():
                        context_candidates.append(item)

            base = ""
            for candidate in context_candidates:
                text = clean_narrative_text(candidate)
                if not text:
                    continue
                if _looks_like_company_description(text, str(entry.get("company") or "")):
                    continue
                base = text.rstrip(" .")
                break

            if base:
                if keyword_norm in normalize_keyword_for_match(base):
                    bullet = f"{base}."
                else:
                    tail = (
                        f"with focus on {keyword_text}"
                        if is_en
                        else f"avec un focus sur {keyword_text}"
                    )
                    bullet = f"{base} {tail}."
            else:
                role_hint = clean_text_field(entry.get("title") or "")
                if is_en:
                    bullet = (
                        f"Applied {keyword_text} in delivery tasks aligned with {role_hint or 'project requirements'}."
                    )
                else:
                    bullet = (
                        f"Mise en oeuvre de {keyword_text} dans des activites de livraison alignees sur {role_hint or 'les exigences projet'}."
                    )

            bullet = clean_narrative_text(_trim_text(bullet, 240))
            if keyword_norm not in normalize_keyword_for_match(bullet):
                bullet = clean_narrative_text(
                    _trim_text(
                        f"{bullet.rstrip('.')} ({keyword_text}).",
                        240,
                    )
                )
            return bullet

        missing_experience_terms = _dedup_preserve(
            [str(term or "").strip() for term in missing_experience_terms if str(term or "").strip()]
        )[:3]

        added = 0
        for keyword in missing_experience_terms:
            keyword_norm = normalize_keyword_for_match(keyword)
            if not keyword_norm:
                continue

            already_present = False
            for entry in experience_entries:
                probe_norm = normalize_keyword_for_match(entry_probe(entry))
                if keyword_norm in probe_norm:
                    already_present = True
                    break
            if already_present:
                continue

            target_entry, target_profile = choose_target_entry(keyword_norm)
            highlights = target_entry.get("highlights")
            if not isinstance(highlights, list):
                highlights = []

            new_bullet = build_keyword_bullet(target_entry, keyword, target_profile)
            if not new_bullet:
                continue

            highlights.append(new_bullet)
            target_entry["highlights"] = _dedup_preserve(
                [item for item in highlights if isinstance(item, str) and item.strip()]
            )[:4]
            added += 1

        if added:
            logger.info(
                "Offer adaptation injected critic keywords into experience bullets: added=%s",
                added,
            )

    return cv_json
