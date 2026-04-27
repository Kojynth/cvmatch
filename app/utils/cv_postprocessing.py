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


# Review marker patterns that indicate LLM produced meta-commentary instead of content.
#
# PHRASE markers: safe to use as plain substrings — these multi-word sequences
# never appear legitimately inside a CV bullet.
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
    "job offer",
    "job description",
)

REVIEW_MARKERS_FR = (
    "le cv",
    "ce cv",
    "le candidat",
    "a revoir",
)

REVIEW_MARKERS = REVIEW_MARKERS_EN + REVIEW_MARKERS_FR

# SINGLE-WORD markers: must use word-boundary matching to avoid false positives
# on past-tense action verbs common in CV bullets (e.g. "improved", "revised",
# "missing from …", "manquant").
_REVIEW_WORD_PATTERN = re.compile(
    r"\b(should|must|needs|improve|revise|missing|ameliorer|manque|devrait|doit)\b",
    re.IGNORECASE,
)

# Placeholder patterns to strip from generated text
PLACEHOLDER_PATTERN = re.compile(
    r"\[(?:A COMPLETER|TO COMPLETE|VOTRE|YOUR|PROFILE_JSON|YEAR_OF_PROFILE_JSON|IMPACT)[^\]]*\]",
    re.IGNORECASE,
)

INTERNAL_MARKER_PATTERN = re.compile(
    r"(PROFILE_JSON|YEAR_OF_PROFILE_JSON)",
    re.IGNORECASE,
)

FORBIDDEN_GENERATED_TEXT_CHARS_PATTERN = re.compile(r"[•«»\^\{\}\[\]]+")
URL_LIKE_PATTERN = re.compile(r"^(?:https?://|www\.)", re.IGNORECASE)
EMAIL_LIKE_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

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

PROJECT_TECH_NOISE_TERMS = {
    "ai powered",
    "are",
    "collaborative",
    "design",
    "design update",
    "design updates",
    "dynamic",
    "project",
    "product",
    "products",
    "proactive",
    "projet",
    "recruteur",
    "resume",
    "resumes",
    "robustness",
    "robustness design updates",
    "seeking",
    "skilled",
    "summary",
    "summaries",
    "team spirited",
    "team-spirited",
    "you",
    "your",
}

BENCHMARK_TOOL_COMPARISON_PATTERN = re.compile(
    r"(?i)^benchmark\s+[A-Za-z0-9_.+#-]+"
    r"(?:\s*/\s*[A-Za-z0-9_.+#-]+){1,5}$"
)


def _looks_like_benchmark_tool_comparison(value: Any) -> bool:
    return bool(BENCHMARK_TOOL_COMPARISON_PATTERN.fullmatch(str(value or "").strip()))

SKILL_LABEL_PREFIX_PATTERN = re.compile(
    r"(?i)^(?:skills?|comp[eé]tences?|technical skills|competences techniques)\s*[:\-]\s*"
)

SKILL_SPLIT_PATTERN = re.compile(r"[;\n\|•]+")
PROJECT_TECH_SPLIT_PATTERN = re.compile(r"\s*[,;|]\s*|\s+/\s+")
SKILL_SENTENCE_NOISE_PATTERN = re.compile(
    r"(?i)\b("
    r"i|we|my|our|je|j ai|nous|mon|notre|candidate|candidat|"
    r"worked|responsible|mission|"
    r"should|must|need|needs|please|including|implicites?|recruteur|"
    r"job offer|offre|profile json|instruction"
    r")\b"
)
DOTTED_TECH_SKILL_PATTERN = re.compile(
    r"(?i)^(?:(?:[a-z0-9+#]+(?:\.[a-z0-9+#]+)+)|(?:\.[a-z0-9+#]+))(?:\s+[a-z0-9+#]{2,16}){0,2}$"
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


def _split_project_technology_items(value: Any) -> List[str]:
    raw = str(value or "").strip()
    if not raw:
        return []
    return [
        chunk.strip()
        for chunk in PROJECT_TECH_SPLIT_PATTERN.split(raw)
        if chunk.strip()
    ]


def _trim_text(value: Any, max_chars: int) -> str:
    """Trim text to max characters with ellipsis."""
    text = "" if value is None else str(value)
    text = text.strip()
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


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

    # Check for phrase markers (safe substring match — these are unambiguous phrases
    # that never appear in legitimate CV bullets).
    if any(marker in lowered for marker in REVIEW_MARKERS):
        return True

    # Check for single-word markers using word boundaries to avoid false positives
    # on past-tense action verbs (e.g. "improved" must not match "improve").
    if _REVIEW_WORD_PATTERN.search(lowered):
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

    if not URL_LIKE_PATTERN.match(cleaned) and not EMAIL_LIKE_PATTERN.match(cleaned):
        cleaned = FORBIDDEN_GENERATED_TEXT_CHARS_PATTERN.sub(" ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
        cleaned = cleaned.strip()
        if not cleaned:
            return ""

    if max_length > 0 and len(cleaned) > max_length:
        return ""

    return cleaned


def _normalize_contact_links(raw_links: Any) -> List[Dict[str, str]]:
    links: List[Dict[str, str]] = []
    if not isinstance(raw_links, list):
        return links

    seen = set()
    for entry in raw_links:
        label = ""
        url = ""
        if isinstance(entry, dict):
            label = clean_text_field(
                entry.get("label") or entry.get("platform") or "", max_length=80
            )
            url = clean_text_field(
                entry.get("url") or entry.get("link") or "", max_length=500
            )
        elif isinstance(entry, str):
            url = clean_text_field(entry, max_length=500)
        if not url:
            continue
        if not re.match(r"^https?://", url, flags=re.IGNORECASE) and re.match(
            r"^[a-z0-9][a-z0-9.-]+\.[a-z]{2,}(?:[/?#].*)?$",
            url,
            flags=re.IGNORECASE,
        ):
            url = f"https://{url}"
        if not label:
            label = f"Lien {len(links) + 1}"
        key = (label.lower(), url.lower())
        if key in seen:
            continue
        seen.add(key)
        links.append({"label": label, "url": url})
    return links


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

    existing_links = _normalize_contact_links(contact.get("links"))
    if existing_links:
        contact["links"] = existing_links
    else:
        links = _normalize_contact_links(personal.get("links"))
        if links:
            contact["links"] = links


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

    try:
        from .cv_quality_audit import clean_target_job_title
    except Exception:
        clean_target_job_title = lambda value: str(value or "").strip()

    if not cv_json.get("target_job_title") and job_title:
        cv_json["target_job_title"] = clean_target_job_title(job_title)
    elif cv_json.get("target_job_title"):
        cv_json["target_job_title"] = clean_target_job_title(
            cv_json.get("target_job_title")
        )
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
        logger.warning(
            "Final summary looked like review text; reverted to draft summary."
        )
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

    try:
        from .cv_skill_evidence import looks_like_noise_skill_term, should_keep_skill_term
    except Exception:
        def looks_like_noise_skill_term(_term: Any) -> bool:
            return False

        def should_keep_skill_term(_term: Any) -> bool:
            return True

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

    target_job_title_norm = normalize_text_for_match(
        cv_json.get("target_job_title") or ""
    )
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
            return any(
                tok in ROLE_LIKE_SKILL_TOKENS for tok in target_job_title_token_set
            )
        return False

    def is_role_like_phrase(tokens: Sequence[str]) -> bool:
        normalized_tokens = [tok for tok in tokens if tok]
        if not normalized_tokens:
            return False

        role_tokens = [
            tok for tok in normalized_tokens if tok in ROLE_LIKE_SKILL_TOKENS
        ]
        if not role_tokens:
            return False

        # Ignore tiny glue tokens introduced by punctuation variants:
        # "Ingenieur(e)" -> ["ingenieur", "e"].
        non_role_long_tokens = [
            tok
            for tok in normalized_tokens
            if tok not in ROLE_LIKE_SKILL_TOKENS and len(tok) > 2
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
            label_norm == target_job_title_norm or has_role_like_title_overlap(tokens)
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
        # Strip list markers like "-", "*" or "1)" / "1." without stripping
        # leading dots from technology names such as ".NET".
        cleaned = re.sub(r"^(?:[-\*]|(?:\d+[.)]))\s*", "", cleaned).strip()
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
                if len(subparts) >= 2 and all(
                    0 < len(value.split()) <= 4 for value in subparts
                ):
                    chunks.extend(subparts)
                    continue
            chunks.append(part)

        return _dedup_preserve(chunks)

    def is_skill_like_phrase(text: str) -> bool:
        if not text:
            return False
        if any(mark in text for mark in ("!", "?", "\n")):
            return False
        if "." in text:
            compact = str(text).strip()
            dotted_tech = bool(DOTTED_TECH_SKILL_PATTERN.fullmatch(compact))
            # Keep dotted technology names, but reject sentence-like forms.
            if not dotted_tech and (
                re.search(r"\.\s", compact) or compact.endswith(".")
            ):
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

    def clean_project_technologies(value: Any) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        cleaned_items: List[str] = []
        seen_tech: set[str] = set()
        for chunk in _split_project_technology_items(raw):
            text = clean_text_field(chunk, max_length=80).strip(" ,;:-")
            if not text:
                continue
            norm = normalize_text_for_match(text)
            if not norm or norm in seen_tech or norm in PROJECT_TECH_NOISE_TERMS:
                continue
            if len(norm.split()) > 4:
                continue
            if looks_like_noise_skill_term(text):
                continue
            if not should_keep_skill_term(text):
                continue
            seen_tech.add(norm)
            cleaned_items.append(text)
        return ", ".join(cleaned_items)

    # Clean top-level text fields
    contact = cv_json.get("contact")
    if isinstance(contact, dict):
        for field in ("full_name", "email", "phone", "linkedin_url", "location"):
            if field == "location":
                contact[field] = _normalize_location_display(contact.get(field))
            else:
                contact[field] = clean_text_field(contact.get(field))
        links = _normalize_contact_links(contact.get("links"))
        if links:
            contact["links"] = links
        else:
            contact.pop("links", None)

    cv_json["summary"] = clean_text_field(
        cv_json.get("summary") or "",
        dedupe_narrative=True,
    )
    cv_json["target_job_title"] = clean_text_field(
        cv_json.get("target_job_title") or ""
    )
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
                is_benchmark_comparison = _looks_like_benchmark_tool_comparison(text)
                if not is_benchmark_comparison and not is_skill_like_phrase(text):
                    continue
                if not is_benchmark_comparison and looks_like_noise_skill_term(text):
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
            cleaned_skills.append(
                {
                    "category": label or fallback_category,
                    "items": cleaned_items,
                }
            )
    merged_skills: List[Dict[str, Any]] = []
    skills_index: Dict[str, int] = {}
    for block in cleaned_skills:
        category_label = (
            str(block.get("category") or fallback_category).strip() or fallback_category
        )
        category_key = (
            normalize_text_for_match(category_label) or category_label.lower()
        )
        items = [
            item
            for item in (block.get("items") or [])
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
        merged_skills[idx]["items"] = _dedup_preserve([*existing_items, *items])

    all_skill_items = [
        item
        for block in merged_skills
        if isinstance(block, dict)
        for item in (block.get("items") or [])
        if isinstance(item, str) and item.strip()
    ]
    if all_skill_items:
        for block in merged_skills:
            if not isinstance(block, dict):
                continue
            block["items"] = clean_skill_item_residues(
                block.get("items") or [],
                other_items=all_skill_items,
                category_label=block.get("category") or "",
            )
        merged_skills = [
            block
            for block in merged_skills
            if isinstance(block, dict) and block.get("items")
        ]

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
            "duration": clean_text_field(entry.get("duration") or ""),
            "location": _normalize_location_display(entry.get("location") or ""),
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
        cleaned_entry["highlights"] = _dedup_fuzzy_highlights(
            _dedup_preserve(highlights)
        )
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
            "location": _normalize_location_display(entry.get("location") or ""),
            "details": [],
        }
        details = []
        for item in entry.get("details", []) or []:
            if isinstance(item, str):
                text = clean_text_field(item)
                if text:
                    details.append(text)
        cleaned_entry["details"] = _dedup_preserve(details)
        if (
            any(
                cleaned_entry.get(f)
                for f in (
                    "school",
                    "degree",
                    "field_of_study",
                    "start_date",
                    "end_date",
                    "location",
                )
            )
            or cleaned_entry["details"]
        ):
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
            "technologies": clean_project_technologies(entry.get("technologies") or ""),
            "url": clean_text_field(entry.get("url") or ""),
            "duration": clean_text_field(entry.get("duration") or ""),
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

    # Clean interests / hobbies
    cleaned_interests = []
    raw_interests = cv_json.get("interests")
    if isinstance(raw_interests, str):
        raw_interests = [raw_interests]
    if isinstance(raw_interests, list):
        for item in raw_interests:
            if not isinstance(item, str):
                continue
            for value in re.split(r"[\n;|]+", item):
                text = clean_text_field(value)
                if text:
                    cleaned_interests.append(text)
    cv_json["interests"] = _dedup_preserve(cleaned_interests)[:6]

    # Clean ATS keywords
    if isinstance(cv_json.get("ats_keywords"), list):
        cleaned_keywords = []
        for item in cv_json.get("ats_keywords") or []:
            if isinstance(item, str):
                text = clean_text_field(item)
                if text:
                    cleaned_keywords.append(text)
        cv_json["ats_keywords"] = _dedup_preserve(cleaned_keywords)

    # Clean render_hints.notes of forbidden chars (^{}[] artifacts from LLM/extraction)
    render_hints = cv_json.get("render_hints")
    if isinstance(render_hints, dict):
        notes = render_hints.get("notes")
        if isinstance(notes, str):
            cleaned_notes = FORBIDDEN_GENERATED_TEXT_CHARS_PATTERN.sub(" ", notes)
            cleaned_notes = re.sub(r"\s+", " ", cleaned_notes).strip()
            render_hints["notes"] = cleaned_notes

    _normalize_cv_punctuation_all(cv_json, language_code=language_code)


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
        "interests",
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


_GENERIC_SKILL_RESIDUE_HEAD_BLOCKLIST = {
    "activity",
    "analyse",
    "analysis",
    "automation",
    "automatisation",
    "business",
    "competence",
    "competences",
    "data",
    "debug",
    "delivery",
    "design",
    "development",
    "documentation",
    "gestion",
    "management",
    "method",
    "methode",
    "model",
    "modele",
    "platform",
    "plateform",
    "plateforme",
    "process",
    "processus",
    "product",
    "produit",
    "project",
    "projet",
    "quality",
    "qualite",
    "role",
    "service",
    "software",
    "strategy",
    "strategie",
    "system",
    "systeme",
    "task",
    "test",
    "testing",
    "tests",
    "tool",
    "tooling",
    "tools",
    "workflow",
}

_NON_SKILL_RESIDUE_HEAD_BLOCKLIST = {
    "advanced",
    "agile",
    "avance",
    "beginner",
    "basic",
    "certified",
    "client",
    "customer",
    "digital",
    "experienced",
    "expert",
    "functional",
    "general",
    "global",
    "intermediate",
    "internal",
    "junior",
    "lead",
    "mobile",
    "principal",
    "professional",
    "senior",
    "staff",
    "strategic",
    "technical",
    "web",
}

_NON_SKILL_RESIDUE_HEAD_SUFFIXES = (
    "able",
    "al",
    "ary",
    "ible",
    "ic",
    "if",
    "ique",
    "ive",
    "ory",
    "ous",
)

_TOOLISH_RESIDUE_CATEGORY_TOKENS = {
    "application",
    "applications",
    "automation",
    "automatisation",
    "ci",
    "cd",
    "delivery",
    "devops",
    "framework",
    "frameworks",
    "library",
    "libraries",
    "logiciel",
    "logiciels",
    "outillage",
    "outil",
    "outils",
    "platform",
    "platforms",
    "plateforme",
    "plateformes",
    "scripting",
    "software",
    "stack",
    "suite",
    "suites",
    "system",
    "systems",
    "tech",
    "technique",
    "techniques",
    "technical",
    "technologie",
    "technologies",
    "technology",
    "tool",
    "tooling",
    "tools",
}


def _category_suggests_compact_tool_list(category_label: Any) -> bool:
    tokens = set(_normalize_for_match(category_label).split())
    if not tokens:
        return False
    return bool(tokens & _TOOLISH_RESIDUE_CATEGORY_TOKENS)


def _looks_like_non_skill_residue_head(value: Any, norm: str) -> bool:
    if norm in _NON_SKILL_RESIDUE_HEAD_BLOCKLIST:
        return True
    text = str(value or "").strip()
    if (
        norm.endswith(_NON_SKILL_RESIDUE_HEAD_SUFFIXES)
        and not re.search(r"[+#./0-9]", text)
        and not re.search(r"[a-z][A-Z]", text)
    ):
        return True
    return False


def _looks_like_compact_residue_head(
    value: Any,
    *,
    category_label: Any = "",
) -> bool:
    text = str(value or "").strip(" ,;:-")
    if not text or len(text.split()) != 1:
        return False
    norm = _normalize_for_match(text)
    if not norm:
        return False
    if norm in SKILL_GLUE_WORDS:
        return False
    if norm in ROLE_LIKE_SKILL_TOKENS:
        return False
    if norm in _GENERIC_SKILL_RESIDUE_HEAD_BLOCKLIST:
        return False
    if _looks_like_non_skill_residue_head(text, norm):
        return False
    if len(norm) < 3 or len(norm) > 32:
        return False
    if re.search(r"[+#./0-9]", text):
        return True
    letters = [char for char in text if char.isalpha()]
    if letters and len(letters) <= 8 and all(char.isupper() for char in letters):
        return True
    if bool(re.search(r"[a-z][A-Z]", text)):
        return True
    if bool(re.fullmatch(r"[A-Z][A-Za-z0-9_.+#-]{2,31}", text)):
        return _category_suggests_compact_tool_list(category_label)
    return False


def clean_skill_item_residues(
    items: Sequence[Any],
    *,
    other_items: Sequence[Any] = (),
    category_label: Any = "",
) -> List[str]:
    """Remove glued skill residues without inventing replacement labels.

    Typical LLM failure: ``"ToolX Data pipeline"`` when ``"Data pipeline"``
    already exists elsewhere. In that case the compact leading label is the
    useful signal and the repeated tail is residue.
    """

    raw_items = [str(item or "").strip() for item in items or [] if str(item or "").strip()]
    if not raw_items:
        return []

    global_norms = {
        _normalize_for_match(item)
        for item in list(other_items or []) + raw_items
        if _normalize_for_match(item)
    }
    category_norm = _normalize_for_match(category_label)
    cleaned: List[str] = []
    for item in raw_items:
        text = re.sub(r"\s+", " ", item).strip(" ,;:-")
        if not text:
            continue
        parts = text.split()
        text_norm = _normalize_for_match(text)
        replacement = text
        if len(parts) >= 3:
            first = parts[0].strip(" ,;:-")
            tail_norm = _normalize_for_match(" ".join(parts[1:]))
            if (
                _looks_like_compact_residue_head(
                    first,
                    category_label=category_label,
                )
                and tail_norm
            ):
                residue_seen = False
                for other_norm in global_norms:
                    if (
                        not other_norm
                        or other_norm == text_norm
                        or len(other_norm.split()) < 2
                    ):
                        continue
                    if other_norm in tail_norm:
                        residue_seen = True
                        break
                if not residue_seen and category_norm:
                    category_tokens = {
                        token
                        for token in category_norm.split()
                        if len(token) >= 2 and token not in SKILL_GLUE_WORDS
                    }
                    tail_tokens = set(tail_norm.split())
                    residue_seen = bool(category_tokens and tail_tokens <= category_tokens)
                if residue_seen:
                    replacement = first
        cleaned.append(replacement)
    return _dedup_preserve(cleaned)


def _token_overlap(left: str, right: str) -> float:
    left_tokens = {tok for tok in _normalize_for_match(left).split() if len(tok) > 2}
    right_tokens = {tok for tok in _normalize_for_match(right).split() if len(tok) > 2}
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / float(
        max(len(left_tokens), len(right_tokens))
    )


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


def _dedup_fuzzy_highlights(
    highlights: Sequence[str],
    *,
    prefix_threshold: int = 30,
    token_overlap_threshold: float = 0.7,
    startswith_min_len: int = 15,
) -> List[str]:
    """Drop near-duplicate highlights, keeping the longer/more complete form.

    Two highlights are considered duplicates when ANY of the following holds:
    - they share a normalized prefix of ``prefix_threshold`` chars;
    - their token overlap (Jaccard) exceeds ``token_overlap_threshold``;
    - one's normalized form is a full starts-with prefix of the other, and
      the shorter side is at least ``startswith_min_len`` normalized chars
      long (catches truncated variants that survived ``_repair_clipped_bullets``
      and are now short enough to slip under ``prefix_threshold``).

    Example of the third case:
        "Concevoir, executer et suivre des" (27 chars normalized)
        vs "Concevoir, executer et suivre des plans de test sur ..."
    The short form is a strict prefix of the long form. Keep the long form.
    """

    items = [h for h in highlights if isinstance(h, str) and h.strip()]
    if len(items) < 2:
        return list(items)

    kept: List[str] = []
    for candidate in items:
        cand_norm = _normalize_for_match(candidate)
        cand_prefix = cand_norm[:prefix_threshold]
        superseded_index = -1
        is_redundant = False
        for idx, existing in enumerate(kept):
            ex_norm = _normalize_for_match(existing)
            ex_prefix = ex_norm[:prefix_threshold]
            same_prefix = bool(
                len(cand_prefix) >= prefix_threshold
                and len(ex_prefix) >= prefix_threshold
                and cand_prefix == ex_prefix
            )
            jaccard_match = _token_overlap(candidate, existing) >= token_overlap_threshold
            shorter, longer = (
                (cand_norm, ex_norm)
                if len(cand_norm) <= len(ex_norm)
                else (ex_norm, cand_norm)
            )
            startswith_match = bool(
                shorter
                and len(shorter) >= startswith_min_len
                and longer.startswith(shorter)
            )
            if not (same_prefix or jaccard_match or startswith_match):
                continue
            if len(candidate.strip()) > len(existing.strip()):
                superseded_index = idx
            else:
                is_redundant = True
            break
        if is_redundant:
            continue
        if superseded_index >= 0:
            kept[superseded_index] = candidate
        else:
            kept.append(candidate)
    return kept


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
    "spécialisée",
    "spécialisé",
    "specialisee",
    "specialise",
    "specialized",
    "digitalisation",
    "digitalization",
    "leader",
)

_ACTION_EXPERIENCE_HINTS = (
    "analyzes",
    "automates",
    "builds",
    "coordinates",
    "creates",
    "defines",
    "delivers",
    "designs",
    "develops",
    "documents",
    "drives",
    "executes",
    "implements",
    "improves",
    "leads",
    "manages",
    "operates",
    "optimizes",
    "prepares",
    "qualifies",
    "reduces",
    "reviews",
    "streamlines",
    "structures",
    "supports",
    "tests",
    "tracks",
    "validates",
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

_EXPERIENCE_LEADIN_PATTERNS = {
    "fr": (
        re.compile(
            r"^(?:mes missions(?: couvrent| consistent| ont notamment consist[ée]?\s+[àa])?|"
            r"responsabilit[ée]s(?: principales)?|missions principales)\s*:?\s*",
            re.IGNORECASE,
        ),
        re.compile(
            r"^(?:[^,]{0,80},\s*)?j['’](?:interviens|assure|accompagne|coordonne|pilote|"
            r"ai(?:\s+participe|\s+contribu[ée])?)\s+(?:sur|[àa]|au sein de|dans|pour)\s*",
            re.IGNORECASE,
        ),
    ),
    "en": (
        re.compile(
            r"^(?:my responsibilities(?: included)?|responsibilities included|key responsibilities|scope)\s*:?\s*",
            re.IGNORECASE,
        ),
        re.compile(
            r"^(?:as [^,]{0,60},\s*)?i\s+(?:worked|supported|led|handled|managed|focused|"
            r"contributed|was responsible)\s+(?:on|for|across|within)\s*",
            re.IGNORECASE,
        ),
    ),
}

_ARTICLE_PREFIX_PATTERNS = {
    "fr": (
        re.compile(r"^(?:la|le|les)\s+", re.IGNORECASE),
        re.compile(r"^l['’]", re.IGNORECASE),
    ),
    "en": (
        re.compile(r"^the\s+", re.IGNORECASE),
    ),
}

_ACTION_LEAD_TOKENS = {
    "fr": {
        "accompagne",
        "ameliore",
        "analyse",
        "anime",
        "assure",
        "automatise",
        "collabore",
        "concoit",
        "conseille",
        "consolide",
        "contribue",
        "coordonne",
        "cree",
        "definit",
        "deploie",
        "developpe",
        "documente",
        "execute",
        "fiabilise",
        "gere",
        "identifie",
        "implemente",
        "met",
        "mene",
        "optimise",
        "pilote",
        "prepare",
        "qualifie",
        "realise",
        "redige",
        "renforce",
        "revoit",
        "soutient",
        "structure",
        "suit",
        "supervise",
        "teste",
        "valide",
    },
    "en": {
        "accelerated",
        "analyzes",
        "analyzed",
        "automates",
        "automated",
        "builds",
        "built",
        "coordinates",
        "coordinated",
        "creates",
        "created",
        "defines",
        "defined",
        "delivers",
        "delivered",
        "designs",
        "designed",
        "develops",
        "developed",
        "documents",
        "documented",
        "drives",
        "drove",
        "executes",
        "executed",
        "implements",
        "implemented",
        "improves",
        "improved",
        "leads",
        "led",
        "manages",
        "managed",
        "operates",
        "optimizes",
        "optimized",
        "prepares",
        "prepared",
        "qualifies",
        "qualified",
        "reduces",
        "reduced",
        "reviews",
        "reviewed",
        "streamlines",
        "streamlined",
        "structures",
        "structured",
        "supports",
        "supported",
        "tests",
        "tested",
        "tracks",
        "tracked",
        "validates",
        "validated",
    },
}

_ACTIONIZED_SERIES_PATTERNS = {
    "fr": (
        (
            re.compile(
                r"^(?:la\s+)?conception,\s*(?:l[\u0027\u2019])?execution\s+et\s+le\s+suivi\s+"
                r"(?P<object>(?:des?|du|de la|de l[\u0027\u2019])\s+.+)$",
                re.IGNORECASE,
            ),
            lambda match: f"Concevoir, executer et suivre {match.group('object')}",
        ),
        (
            re.compile(
                r"^(?:la\s+)?redaction\s+et\s+le\s+suivi\s+"
                r"(?P<object>(?:des?|du|de la|de l[\u0027\u2019])\s+.+)$",
                re.IGNORECASE,
            ),
            lambda match: f"Rediger et suivre {match.group('object')}",
        ),
    ),
}

_ACTIONIZED_PREFIX_PATTERNS = {
    "fr": (
        (re.compile(r"^(?:la\s+)?validation\b", re.IGNORECASE), "Assurer la validation"),
        (re.compile(r"^(?:la\s+)?qualit[eé]\b", re.IGNORECASE), "Renforcer la qualite"),
        (re.compile(r"^(?:la\s+)?qualification\b", re.IGNORECASE), "Assurer la qualification"),
        (re.compile(r"^(?:la\s+)?coordination\b", re.IGNORECASE), "Coordonner"),
        (re.compile(r"^(?:la\s+)?conception\b", re.IGNORECASE), "Piloter la conception"),
        (re.compile(r"^(?:l[\u0027\u2019])?execution\b", re.IGNORECASE), "Piloter l'execution"),
        (re.compile(r"^(?:le\s+)?suivi\b", re.IGNORECASE), "Assurer le suivi"),
        (re.compile(r"^(?:la\s+)?redaction\b", re.IGNORECASE), "Rediger"),
        (re.compile(r"^(?:la\s+)?revue\b", re.IGNORECASE), "Revoir"),
        (re.compile(r"^(?:l[\u0027\u2019])?analyse\b", re.IGNORECASE), "Analyser"),
        (re.compile(r"^(?:l[\u0027\u2019])?optimisation\b", re.IGNORECASE), "Optimiser"),
        (re.compile(r"^(?:l[\u0027\u2019])?automatisation\b", re.IGNORECASE), "Automatiser"),
        (re.compile(r"^(?:le\s+)?benchmark\b", re.IGNORECASE), "Mener un benchmark"),
        (re.compile(r"^(?:le\s+)?pilotage\b", re.IGNORECASE), "Piloter"),
        (re.compile(r"^(?:la\s+)?gestion\b", re.IGNORECASE), "Gerer"),
        (re.compile(r"^(?:la\s+)?documentation\b", re.IGNORECASE), "Documenter"),
        (re.compile(r"^(?:les?\s+)?tests?\b", re.IGNORECASE), "Executer des tests"),
    ),
    "en": (
        (re.compile(r"^validation\b", re.IGNORECASE), "Led validation"),
        (re.compile(r"^testing\b", re.IGNORECASE), "Executed testing"),
        (re.compile(r"^test\b", re.IGNORECASE), "Executed tests"),
        (re.compile(r"^automation\b", re.IGNORECASE), "Automated"),
        (re.compile(r"^analysis\b", re.IGNORECASE), "Analyzed"),
        (re.compile(r"^review\b", re.IGNORECASE), "Reviewed"),
        (re.compile(r"^documentation\b", re.IGNORECASE), "Documented"),
        (re.compile(r"^tracking\b", re.IGNORECASE), "Tracked"),
        (re.compile(r"^coordination\b", re.IGNORECASE), "Coordinated"),
        (re.compile(r"^optimization\b", re.IGNORECASE), "Optimized"),
        (re.compile(r"^implementation\b", re.IGNORECASE), "Implemented"),
        (re.compile(r"^support\b", re.IGNORECASE), "Supported"),
    ),
}


def _starts_with_action_phrase(text: Any, *, language_code: str = "fr") -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False

    language = str(language_code or "fr").strip().lower().split("-", 1)[0]
    normalized = _normalize_for_match(raw)
    if not normalized:
        return False

    if language == "fr" and normalized.startswith(("mettre en place ", "mis en place ")):
        return True
    if language == "en" and normalized.startswith(("set up ", "setting up ")):
        return True

    first_token = normalized.split(" ", 1)[0]
    if not first_token:
        return False

    if first_token in _ACTION_LEAD_TOKENS.get(language, set()):
        return True
    if language == "fr" and re.fullmatch(r"[a-z]+(?:er|ir|re)", first_token):
        return True
    if language == "en" and (
        first_token.endswith("ed")
        or first_token in {"build", "drive", "lead", "manage", "review", "support", "test", "track", "validate"}
    ):
        return True
    return False


def _actionize_experience_fragment(text: Any, *, language_code: str = "fr") -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""

    language = str(language_code or "fr").strip().lower().split("-", 1)[0]
    if _starts_with_action_phrase(raw, language_code=language):
        return raw

    for pattern, builder in _ACTIONIZED_SERIES_PATTERNS.get(language, ()):
        match = pattern.match(raw)
        if not match:
            continue
        rewritten = str(builder(match) or "").strip(" ;,.-")
        if rewritten:
            return rewritten

    for pattern, replacement in _ACTIONIZED_PREFIX_PATTERNS.get(language, ()):
        match = pattern.match(raw)
        if not match:
            continue
        remainder = raw[match.end() :].lstrip(" ,;:-")
        rewritten = f"{replacement} {remainder}".strip(" ;,.-")
        if rewritten:
            return rewritten

    return raw


_COMPANY_DESCRIPTOR_PHRASES = (
    "filiale de",
    "filiale du",
    "filiale numerique",
    "filiale numérique",
    "filiale digitale",
    "filiale specialisee",
    "filiale spécialisée",
    "specialisee dans",
    "specialise dans",
    "spécialisée dans",
    "spécialisé dans",
    "specialisee en",
    "specialise en",
    "spécialisée en",
    "spécialisé en",
    "entreprise specialisee",
    "entreprise spécialisée",
    "societe specialisee",
    "société spécialisée",
    "subsidiary of",
    "branch of",
    "est un leader",
    "is a leader",
    "leader mondial",
    "groupe mondial",
    "est la filiale",
    "is the subsidiary",
)


def _looks_like_company_description(text: str, company: str = "") -> bool:
    normalized = _normalize_for_match(text)
    if not normalized:
        return False

    company_norm = _normalize_for_match(company)
    raw = str(text or "").strip()

    company_colon_prefix = False
    if company and raw:
        lowered = raw.lower()
        cname = company.strip().lower()
        if cname and (lowered.startswith(f"{cname}:") or lowered.startswith(f"{cname} :")):
            company_colon_prefix = True

    for phrase in _COMPANY_DESCRIPTOR_PHRASES:
        if phrase in normalized:
            if company_colon_prefix:
                return True
            action_hits_quick = sum(
                1 for marker in _ACTION_EXPERIENCE_HINTS if marker in normalized
            )
            if action_hits_quick == 0:
                return True
            break

    if len(normalized) < 50:
        return False

    corporate_hits = sum(
        1 for marker in _CORPORATE_DESCRIPTION_HINTS if marker in normalized
    )
    action_hits = sum(1 for marker in _ACTION_EXPERIENCE_HINTS if marker in normalized)

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


def _normalize_location_display(value: Any) -> str:
    text = clean_text_field(value or "", dedupe_narrative=False)
    if not text:
        return ""
    return re.sub(r"\s+-\s+", ", ", text)


def _strip_experience_leadins(text: str, *, language_code: str) -> str:
    output = str(text or "").strip()
    if not output:
        return ""

    language = str(language_code or "fr").strip().lower().split("-", 1)[0]
    patterns = _EXPERIENCE_LEADIN_PATTERNS.get(language, ()) + _EXPERIENCE_LEADIN_PATTERNS.get("en", ())
    changed = True
    while changed and output:
        changed = False
        for pattern in patterns:
            updated = pattern.sub("", output, count=1).strip()
            if updated != output:
                output = updated
                changed = True
    return output.strip()


def _polish_experience_fragment(
    text: Any,
    *,
    company: str = "",
    language_code: str = "fr",
    prefer_articleless: bool = False,
) -> str:
    raw = clean_narrative_text(text or "")
    if not raw:
        return ""

    # Clipped-tail repair at source (R1 regression, see AGENTS.md invariant
    # "Duplicate-bullet repair"). Every fragment-polish path flows here;
    # stripping trailing U+2026/'...' and dangling stopwords up-front lets
    # fuzzy dedup recognize the clipped twin as a prefix of the full bullet.
    stripped_tail = re.sub(r"\s*(?:\.\.\.|\u2026)+\s*$", "", raw)
    if stripped_tail != raw:
        cleaned = stripped_tail.rstrip(" ,;:-\u2013\u2014")
        for _ in range(8):
            tokens = cleaned.split()
            if not tokens:
                break
            last_lower = tokens[-1].lower().strip("'\u2019\"`")
            if last_lower not in _CLIPPED_TRAILING_STOPWORDS_POSTPROCESS:
                break
            cleaned = cleaned[: -len(tokens[-1])].rstrip(" ,;:-\u2013\u2014")
        raw = cleaned
        if not raw:
            return ""

    raw = _strip_experience_leadins(raw, language_code=language_code)
    raw = re.sub(r"^[\-\*\u2022\u25AA\u279C]+\s*", "", raw).strip(" ;,.-")
    if not raw or raw.endswith(":"):
        return ""
    if _looks_like_company_description(raw, company):
        return ""

    language = str(language_code or "fr").strip().lower().split("-", 1)[0]
    if language == "fr":
        raw = re.sub(
            r"\b([Ee]x[ée]cute)\s+et\s+suis\b",
            lambda match: f"{match.group(1)} et suit",
            raw,
        )
    if prefer_articleless:
        for pattern in _ARTICLE_PREFIX_PATTERNS.get(language, ()):
            updated = pattern.sub("", raw, count=1).strip()
            if updated and updated != raw:
                raw = updated
                break
        raw = _actionize_experience_fragment(raw, language_code=language)

    raw = re.sub(r"\s{2,}", " ", raw).strip(" ;,.-")
    if not raw or _looks_like_company_description(raw, company):
        return ""
    if raw[:1].islower():
        raw = raw[:1].upper() + raw[1:]
    return _trim_text(raw, 240)


def _select_action_summary(
    summary: str,
    *,
    highlights: List[str],
    fallback_description: str,
    company: str,
    language_code: str = "fr",
) -> str:
    summary_text = _polish_experience_fragment(
        summary,
        company=company,
        language_code=language_code,
    )
    if summary_text:
        return _trim_text(summary_text, 420)

    for item in highlights:
        text = _polish_experience_fragment(
            item,
            company=company,
            language_code=language_code,
            prefer_articleless=True,
        )
        if not text:
            continue
        return _trim_text(text, 280)

    fallback_text = _polish_experience_fragment(
        fallback_description,
        company=company,
        language_code=language_code,
    )
    if fallback_text:
        return _trim_text(fallback_text, 420)

    return ""


def _derive_profile_date_support(start_date: Any, end_date: Any) -> Dict[str, Any]:
    try:
        from .profile_json import derive_date_support_fields

        return derive_date_support_fields(start_date, end_date)
    except Exception:
        return {
            "start_date_raw": str(start_date or "").strip(),
            "end_date_raw": str(end_date or "").strip(),
            "start_date_norm": "",
            "end_date_norm": "",
            "is_current": False,
            "start_date_precision": "",
            "end_date_precision": "",
            "date_precision": "",
            "duration_months": None,
        }


def _format_duration_label(months: int, *, language_code: str = "fr") -> str:
    def normalize_language(value: Any) -> str:
        normalized = str(value or "").strip().lower()
        if not normalized:
            return "fr"
        normalized = re.split(r"[-_]", normalized, maxsplit=1)[0]
        return normalized or "fr"

    def format_word_parts(
        total_months: int,
        *,
        year_singular: str,
        year_plural: str,
        month_singular: str,
        month_plural: str,
    ) -> str:
        years, rem = divmod(total_months, 12)
        parts: List[str] = []
        if years:
            year_label = year_singular if years == 1 else year_plural
            parts.append(f"{years} {year_label}")
        if rem:
            month_label = month_singular if rem == 1 else month_plural
            parts.append(f"{rem} {month_label}")
        if parts:
            return " ".join(parts)
        return f"1 {month_singular}"

    def format_compact_parts(
        total_months: int,
        *,
        year_unit: str,
        month_unit: str,
    ) -> str:
        years, rem = divmod(total_months, 12)
        parts: List[str] = []
        if years:
            parts.append(f"{years}{year_unit}")
        if rem:
            parts.append(f"{rem}{month_unit}")
        if parts:
            return " ".join(parts)
        return f"1{month_unit}"

    language = normalize_language(language_code)
    compact_units = {
        "ja": ("\u5e74", "\u304b\u6708"),
        "zh": ("\u5e74", "\u4e2a\u6708"),
        "ko": ("\ub144", "\uac1c\uc6d4"),
        "ru": (" \u0433.", " \u043c\u0435\u0441."),
        "pl": (" r.", " mies."),
        "cs": (" r.", " m\u011bs."),
    }
    if language in compact_units:
        year_unit, month_unit = compact_units[language]
        return format_compact_parts(months, year_unit=year_unit, month_unit=month_unit)

    word_units = {
        "fr": ("an", "ans", "mois", "mois"),
        "en": ("yr", "yrs", "mo", "mos"),
        "de": ("Jahr", "Jahre", "Monat", "Monate"),
        "es": ("a\u00f1o", "a\u00f1os", "mes", "meses"),
        "it": ("anno", "anni", "mese", "mesi"),
        "pt": ("ano", "anos", "m\u00eas", "meses"),
        "nl": ("jaar", "jaar", "maand", "maanden"),
        "ar": (
            "\u0633\u0646\u0629",
            "\u0633\u0646\u0648\u0627\u062a",
            "\u0634\u0647\u0631",
            "\u0623\u0634\u0647\u0631",
        ),
        "hi": ("\u0935\u0930\u094d\u0937", "\u0935\u0930\u094d\u0937", "\u092e\u093e\u0939", "\u092e\u093e\u0939"),
        "tr": ("y\u0131l", "y\u0131l", "ay", "ay"),
        "sv": ("\u00e5r", "\u00e5r", "m\u00e5nad", "m\u00e5nader"),
        "no": ("\u00e5r", "\u00e5r", "m\u00e5ned", "m\u00e5neder"),
        "da": ("\u00e5r", "\u00e5r", "m\u00e5ned", "m\u00e5neder"),
        "fi": ("vuosi", "vuotta", "kuukausi", "kuukautta"),
        "el": (
            "\u03ad\u03c4\u03bf\u03c2",
            "\u03ad\u03c4\u03b7",
            "\u03bc\u03ae\u03bd\u03b1\u03c2",
            "\u03bc\u03ae\u03bd\u03b5\u03c2",
        ),
        "ro": ("an", "ani", "lun\u0103", "luni"),
        "hu": ("\u00e9v", "\u00e9v", "h\u00f3nap", "h\u00f3nap"),
    }
    year_singular, year_plural, month_singular, month_plural = word_units.get(
        language,
        word_units["en"] if language != "fr" else word_units["fr"],
    )
    return format_word_parts(
        months,
        year_singular=year_singular,
        year_plural=year_plural,
        month_singular=month_singular,
        month_plural=month_plural,
    )


def _compute_duration_label(
    start_date: Any,
    end_date: Any,
    *,
    language_code: str = "fr",
) -> str:
    date_support = _derive_profile_date_support(start_date, end_date)
    months = date_support.get("duration_months")
    if isinstance(months, int) and months >= 1:
        return _format_duration_label(months, language_code=language_code)
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
        date_support = _derive_profile_date_support(
            row.get("start_date") or "",
            row.get("end_date") or "",
        )
        if not any(
            row.get(field)
            for field in (
                "title",
                "company",
                "start_date",
                "end_date",
                "location",
                "description",
            )
        ):
            continue
        row["_title_norm"] = _normalize_for_match(row["title"])
        row["_company_norm"] = _normalize_for_match(row["company"])
        row["_start_norm"] = date_support.get("start_date_norm") or _normalize_for_match(
            row["start_date"]
        )
        row["_end_norm"] = date_support.get("end_date_norm") or _normalize_for_match(
            row["end_date"]
        )
        row["_date_support"] = date_support
        rows.append(row)
    return rows


def _score_profile_experience_match(
    entry: Dict[str, Any], profile_entry: Dict[str, Any]
) -> float:
    score = 0.0

    title_norm = _normalize_for_match(entry.get("title"))
    company_norm = _normalize_for_match(entry.get("company"))
    entry_date_support = _derive_profile_date_support(
        entry.get("start_date") or "",
        entry.get("end_date") or "",
    )
    start_norm = entry_date_support.get("start_date_norm") or _normalize_for_match(
        entry.get("start_date")
    )
    end_norm = entry_date_support.get("end_date_norm") or _normalize_for_match(
        entry.get("end_date")
    )

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


def _is_profile_experience_match_ambiguous(
    entry: Dict[str, Any],
    matched_profile: Dict[str, Any],
    profile_experiences: List[Dict[str, Any]],
) -> bool:
    if not isinstance(entry, dict) or not isinstance(matched_profile, dict):
        return True

    best_title = matched_profile.get("_title_norm") or ""
    best_company = matched_profile.get("_company_norm") or ""
    best_dates = (
        matched_profile.get("_start_norm") or "",
        matched_profile.get("_end_norm") or "",
    )
    if not best_title and not best_company:
        return True

    entry_date_support = _derive_profile_date_support(
        entry.get("start_date") or "",
        entry.get("end_date") or "",
    )
    entry_start = entry_date_support.get("start_date_norm") or ""
    entry_end = entry_date_support.get("end_date_norm") or ""

    competing_dates: List[Tuple[str, str]] = []
    for profile_entry in profile_experiences:
        if not isinstance(profile_entry, dict) or profile_entry is matched_profile:
            continue
        if best_title and profile_entry.get("_title_norm") != best_title:
            continue
        if best_company and profile_entry.get("_company_norm") != best_company:
            continue
        other_dates = (
            profile_entry.get("_start_norm") or "",
            profile_entry.get("_end_norm") or "",
        )
        if other_dates != best_dates:
            competing_dates.append(other_dates)

    if not competing_dates:
        return False

    if entry_start and best_dates[0] and entry_start != best_dates[0]:
        return True
    if entry_end and best_dates[1] and entry_end != best_dates[1]:
        return True
    if not entry_start and not entry_end:
        return True
    return False


def _experience_identity(entry: Dict[str, Any]) -> str:
    parts = (
        _normalize_for_match(entry.get("company")),
        _normalize_for_match(entry.get("title")),
        _normalize_for_match(entry.get("start_date")),
        _normalize_for_match(entry.get("end_date")),
    )
    key = "|".join(parts).strip("|")
    if key:
        return key
    return _normalize_for_match(entry.get("title"))


def _merge_experience_entries(
    existing: Dict[str, Any], incoming: Dict[str, Any]
) -> None:
    combined_highlights = _dedup_preserve(
        list(existing.get("highlights") or []) + list(incoming.get("highlights") or [])
    )
    existing["highlights"] = _dedup_fuzzy_highlights(combined_highlights)[:4]
    incoming_summary = str(incoming.get("summary") or "")
    existing_summary = str(existing.get("summary") or "")
    if len(incoming_summary) > len(existing_summary):
        existing["summary"] = incoming_summary
    for field in ("location", "duration", "start_date", "end_date"):
        if not existing.get(field) and incoming.get(field):
            existing[field] = incoming[field]


def _experience_fuzzy_fingerprint(entry: Dict[str, Any]) -> str:
    """Looser identity than `_experience_identity`: (company, title_prefix).

    The strict identity tuple `company|title|start_date|end_date` used by
    `_reconcile_experience_section` breaks whenever two retries emit the same
    role with different date formatting (e.g. `09/2021` vs `2021-09`). This
    fingerprint ignores dates and trims the title to its first three
    normalized tokens so minor wording drift still collapses.
    """
    company = _normalize_for_match(entry.get("company")) or ""
    title_norm = _normalize_for_match(entry.get("title")) or ""
    title_prefix = " ".join(title_norm.split()[:3])
    if not company and not title_prefix:
        return ""
    return f"{company}|{title_prefix}"


def _experience_period_fingerprint(entry: Dict[str, Any]) -> Tuple[str, str]:
    date_support = _derive_profile_date_support(
        entry.get("start_date") or "",
        entry.get("end_date") or "",
    )
    start_norm = date_support.get("start_date_norm") or _normalize_for_match(
        entry.get("start_date")
    )
    end_norm = date_support.get("end_date_norm") or _normalize_for_match(
        entry.get("end_date")
    )
    return start_norm, end_norm


def _experience_periods_compatible(
    left: Dict[str, Any], right: Dict[str, Any]
) -> bool:
    """Merge only when periods match or one side omits the conflicting date."""

    left_start, left_end = _experience_period_fingerprint(left)
    right_start, right_end = _experience_period_fingerprint(right)
    if left_start and right_start and left_start != right_start:
        return False
    if left_end and right_end and left_end != right_end:
        return False
    return True


def _dedup_experience_entries(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Collapse cross-entry duplicates that survived reconciliation.

    Entries with the same fuzzy fingerprint and compatible normalized period
    are merged via
    `_merge_experience_entries` (longer summary wins, highlights union, first
    non-empty date wins). Entries without a usable fingerprint are kept
    as-is to preserve legitimate placeholder rows.
    """
    if not isinstance(entries, list):
        return entries
    survivors: List[Dict[str, Any]] = []
    by_fingerprint: Dict[str, List[Dict[str, Any]]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            survivors.append(entry)
            continue
        fingerprint = _experience_fuzzy_fingerprint(entry)
        if not fingerprint:
            survivors.append(entry)
            continue
        bucket = by_fingerprint.get(fingerprint)
        if bucket is None:
            by_fingerprint[fingerprint] = [entry]
            survivors.append(entry)
            continue
        merged = False
        for existing in bucket:
            if not _experience_periods_compatible(existing, entry):
                continue
            _merge_experience_entries(existing, entry)
            merged = True
            break
        if merged:
            continue
        bucket.append(entry)
        survivors.append(entry)
    return survivors


def _dedup_experience_sections_in_place(cv_json: Dict[str, Any]) -> None:
    if not isinstance(cv_json, dict):
        return
    for section in ("experience", "experiences"):
        entries = cv_json.get(section)
        if not isinstance(entries, list):
            continue
        deduped_entries = _dedup_experience_entries(entries)
        cv_json[section] = deduped_entries
        for entry in deduped_entries:
            if not isinstance(entry, dict):
                continue
            highlights = entry.get("highlights")
            if isinstance(highlights, list) and len(highlights) > 1:
                entry["highlights"] = _dedup_fuzzy_highlights(highlights)


def _reconcile_experience_section(
    cv_json: Dict[str, Any],
    profile_json: Dict[str, Any],
    *,
    language_code: str = "fr",
    offer_keywords: Optional[Sequence[str]] = None,
    job_title: str = "",
) -> None:
    if not isinstance(cv_json, dict):
        return
    experience_entries = cv_json.get("experience")
    if not isinstance(experience_entries, list):
        return
    if not experience_entries:
        seeded_count = _seed_experience_from_profile(
            cv_json,
            profile_json,
            language_code=language_code,
            offer_keywords=offer_keywords,
            job_title=job_title,
        )
        if seeded_count:
            logger.warning(
                "Experience reconciliation rebuilt %s missing profile entries.",
                seeded_count,
            )
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
            "duration": clean_text_field(raw_entry.get("duration") or ""),
            "location": clean_text_field(raw_entry.get("location") or ""),
            "summary": clean_text_field(
                raw_entry.get("summary") or "",
                dedupe_narrative=True,
            ),
            "highlights": [],
        }
        entry["description"] = _collect_experience_source_candidates(
            raw_entry.get("description"),
            company=entry.get("company") or "",
            language_code=language_code,
        )

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

        matched_profile = (
            profile_experiences[best_idx]
            if best_idx >= 0 and best_score >= 0.45
            else None
        )
        if matched_profile and _is_profile_experience_match_ambiguous(
            entry,
            matched_profile,
            profile_experiences,
        ):
            matched_profile = None
        expected_description = ""
        if matched_profile:
            expected_description = matched_profile.get("description") or ""
            for field in ("title", "company", "location"):
                if not entry.get(field) and matched_profile.get(field):
                    entry[field] = matched_profile[field]
            for field in ("start_date", "end_date"):
                if matched_profile.get(field):
                    entry[field] = matched_profile[field]

        if expected_description:
            profile_candidates = _collect_experience_source_candidates(
                expected_description,
                company=entry.get("company") or "",
                language_code=language_code,
            )
            if profile_candidates:
                entry["description"] = _dedup_fuzzy_highlights(
                    _dedup_preserve([*entry.get("description", []), *profile_candidates])
                )[:12]

            if not entry["summary"]:
                entry["summary"] = _select_action_summary(
                    "",
                    highlights=highlights,
                    fallback_description=expected_description,
                    company=entry.get("company") or "",
                    language_code=language_code,
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
                        other_overlap = max(
                            other_overlap,
                            _token_overlap(current_summary, other_description),
                        )
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
                        language_code=language_code,
                    )
                    highlights = extract_experience_highlights(
                        expected_description,
                        company=entry.get("company") or "",
                        language_code=language_code,
                    )
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
                        other_overlap = max(
                            other_overlap,
                            _token_overlap(highlight_blob, other_description),
                        )
                if other_overlap >= 0.42 and other_overlap > (expected_overlap + 0.12):
                    highlights = extract_experience_highlights(
                        expected_description,
                        company=entry.get("company") or "",
                        language_code=language_code,
                    )

        summary_text = _select_action_summary(
            entry.get("summary") or "",
            highlights=highlights,
            fallback_description=expected_description,
            company=entry.get("company") or "",
            language_code=language_code,
        )
        summary_norm = _normalize_for_match(summary_text)
        cleaned_highlights: List[str] = []
        for highlight in highlights:
            text = _polish_experience_fragment(
                highlight,
                company=entry.get("company") or "",
                language_code=language_code,
                prefer_articleless=True,
            )
            if not text:
                continue
            if (
                summary_norm
                and len(cleaned_highlights) >= 3
                and _is_same_narrative(summary_text, text)
            ):
                continue
            cleaned_highlights.append(text)

        if expected_description and len(cleaned_highlights) < 3:
            supplemental_highlights = extract_experience_highlights(
                expected_description,
                company=entry.get("company") or "",
                language_code=language_code,
            )
            for supplemental in supplemental_highlights:
                text = _polish_experience_fragment(
                    supplemental,
                    company=entry.get("company") or "",
                    language_code=language_code,
                    prefer_articleless=True,
                )
                if not text:
                    continue
                if (
                    summary_norm
                    and len(cleaned_highlights) >= 3
                    and _is_same_narrative(summary_text, text)
                ):
                    continue
                candidate_lines = _dedup_fuzzy_highlights(
                    _dedup_preserve([*cleaned_highlights, text])
                )
                if len(candidate_lines) == len(cleaned_highlights):
                    continue
                cleaned_highlights = candidate_lines
                if len(cleaned_highlights) >= 4:
                    break

        entry["summary"] = _trim_text(summary_text, 420)
        deduped_highlights = _dedup_fuzzy_highlights(_dedup_preserve(cleaned_highlights))
        entry["highlights"] = deduped_highlights[:4]
        duration = _compute_duration_label(
            entry.get("start_date") or "",
            entry.get("end_date") or "",
            language_code=language_code,
        )
        if duration:
            entry["duration"] = duration

        if (
            any(
                entry.get(field)
                for field in (
                    "title",
                    "company",
                    "start_date",
                    "end_date",
                    "duration",
                    "location",
                    "summary",
                )
            )
            or entry["highlights"]
        ):
            identity = _experience_identity(entry)
            merged = False
            if identity:
                for existing in reconciled:
                    if _experience_identity(existing) == identity:
                        _merge_experience_entries(existing, entry)
                        merged = True
                        break
            if not merged:
                reconciled.append(entry)

    cv_json["experience"] = reconciled
    if reassigned_count:
        logger.warning(
            "Experience reconciliation fixed %s likely misassigned summaries.",
            reassigned_count,
        )


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
                    text = clean_text_field(
                        value, check_review_markers=False, dedupe_narrative=True
                    )
                    if text:
                        details.append(text)
        description_text = item.get("description")
        if isinstance(description_text, str) and description_text.strip():
            text = clean_text_field(
                description_text, check_review_markers=False, dedupe_narrative=True
            )
            if text:
                details.append(text)
        grade_text = item.get("grade")
        if isinstance(grade_text, str) and grade_text.strip():
            details.append(grade_text.strip())

        row = {
            "school": clean_text_field(
                item.get("school") or "", check_review_markers=False
            ),
            "degree": clean_text_field(
                item.get("degree") or "", check_review_markers=False
            ),
            "field_of_study": clean_text_field(
                item.get("field_of_study") or "", check_review_markers=False
            ),
            "start_date": clean_text_field(
                item.get("start_date") or "", check_review_markers=False
            ),
            "end_date": clean_text_field(
                item.get("end_date") or "", check_review_markers=False
            ),
            "location": clean_text_field(
                item.get("location") or "", check_review_markers=False
            ),
            "details": _dedup_preserve(details)[:4],
        }
        if (
            not any(
                row.get(field)
                for field in (
                    "school",
                    "degree",
                    "field_of_study",
                    "start_date",
                    "end_date",
                    "location",
                )
            )
            and not row["details"]
        ):
            continue
        row["_school_norm"] = _normalize_for_match(row["school"])
        row["_degree_norm"] = _normalize_for_match(row["degree"])
        row["_start_norm"] = _normalize_for_match(row["start_date"])
        row["_end_norm"] = _normalize_for_match(row["end_date"])
        rows.append(row)

    return rows


def _score_profile_education_match(
    entry: Dict[str, Any], profile_entry: Dict[str, Any]
) -> float:
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


def _reconcile_education_section(
    cv_json: Dict[str, Any], profile_json: Dict[str, Any]
) -> None:
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
            for field in (
                "school",
                "degree",
                "field_of_study",
                "start_date",
                "end_date",
                "location",
            ):
                if not entry.get(field) and matched.get(field):
                    entry[field] = matched[field]
            merged_details = _dedup_preserve(
                (entry.get("details") or []) + (matched.get("details") or [])
            )
            entry["details"] = merged_details[:4]

        if (
            any(
                entry.get(field)
                for field in (
                    "school",
                    "degree",
                    "field_of_study",
                    "start_date",
                    "end_date",
                    "location",
                )
            )
            or entry["details"]
        ):
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
        if (
            any(
                addition.get(field)
                for field in (
                    "school",
                    "degree",
                    "field_of_study",
                    "start_date",
                    "end_date",
                    "location",
                )
            )
            or addition["details"]
        ):
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
        logger.warning(
            "Education reconciliation appended %s missing profile entries.",
            appended_count,
        )


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


def _reconcile_languages_section(
    cv_json: Dict[str, Any], profile_json: Dict[str, Any]
) -> None:
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
            existing["language"] = (
                entry.get("language") or existing.get("language") or ""
            )

    reconciled: List[Dict[str, str]] = []
    seen: set = set()
    appended_count = 0

    for raw_entry in current_entries:
        if not isinstance(raw_entry, dict):
            continue
        language = clean_text_field(
            raw_entry.get("language") or raw_entry.get("name") or ""
        )
        if not language:
            continue
        key = _normalize_for_match(language)
        if not key or key in seen:
            continue

        level = clean_text_field(
            raw_entry.get("level") or raw_entry.get("proficiency") or ""
        )
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
        logger.warning(
            "Language reconciliation appended %s missing profile entries.",
            appended_count,
        )


def _extract_profile_projects(profile_json: Dict[str, Any]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    if not isinstance(profile_json, dict):
        return rows
    for item in profile_json.get("projects") or []:
        if not isinstance(item, dict):
            continue
        name = clean_text_field(item.get("name") or "", check_review_markers=False)
        description = clean_text_field(
            item.get("description") or "",
            check_review_markers=False,
            dedupe_narrative=True,
        )
        technologies = clean_text_field(
            item.get("technologies") or item.get("tech_stack") or "",
            check_review_markers=False,
        )
        url = clean_text_field(item.get("url") or "", check_review_markers=False)
        duration = clean_text_field(
            item.get("duration") or "", check_review_markers=False
        )
        if not any((name, description, technologies, url, duration)):
            continue
        rows.append(
            {
                "name": name,
                "description": description,
                "technologies": technologies,
                "url": url,
                "duration": duration,
            }
        )
    return rows


def _score_profile_project_match(
    project: Dict[str, Any], profile_project: Dict[str, Any]
) -> float:
    project_name = _normalize_for_match(project.get("name"))
    profile_name = _normalize_for_match(profile_project.get("name"))
    if not project_name or not profile_name:
        return 0.0
    if project_name == profile_name:
        return 1.0
    return _text_similarity(project_name, profile_name)


def _project_profile_has_missing_signal(
    project: Dict[str, Any],
    profile_project: Dict[str, Any],
) -> bool:
    current_probe = _normalize_for_match(
        " ".join(
            str(project.get(key) or "")
            for key in ("description", "technologies", "name")
        )
    )
    profile_probe = _normalize_for_match(
        " ".join(
            str(profile_project.get(key) or "")
            for key in ("description", "technologies", "name")
        )
    )
    if not profile_probe:
        return False

    missing_markers = (
        "llm",
        "pytest",
        "tests unitaires",
        "validation",
        "sorties",
        "generation",
        "cv cible",
        "pipeline",
    )
    if any(
        marker in profile_probe and marker not in current_probe
        for marker in missing_markers
    ):
        return True

    current_words = len(current_probe.split())
    profile_words = len(profile_probe.split())
    return profile_words >= max(18, current_words + 8)


def _merge_project_technology_values(*values: Any) -> str:
    items: List[str] = []
    seen: set[str] = set()
    for value in values:
        for chunk in _split_project_technology_items(value):
            text = clean_text_field(
                chunk,
                max_length=80,
                check_review_markers=False,
            ).strip(" ,;:-")
            if not text:
                continue
            key = _normalize_for_match(text)
            if not key or key in seen:
                continue
            seen.add(key)
            items.append(text)
    return ", ".join(items)


def _merge_project_with_profile_evidence(
    project: Dict[str, Any],
    profile_project: Dict[str, Any],
) -> Dict[str, Any]:
    merged = dict(project)
    for field in ("name", "url", "duration"):
        if not str(merged.get(field) or "").strip() and profile_project.get(field):
            merged[field] = profile_project[field]

    current_description = str(merged.get("description") or "").strip()
    profile_description = str(profile_project.get("description") or "").strip()
    if profile_description and (
        not current_description
        or _project_profile_has_missing_signal(merged, profile_project)
    ):
        merged["description"] = profile_description

    current_technologies = str(merged.get("technologies") or "").strip()
    profile_technologies = str(profile_project.get("technologies") or "").strip()
    if profile_technologies:
        merged["technologies"] = _merge_project_technology_values(
            current_technologies,
            profile_technologies,
        )
    return merged


def _extract_profile_interests(profile_json: Dict[str, Any]) -> List[str]:
    rows: List[str] = []
    if not isinstance(profile_json, dict):
        return rows
    raw_interests = profile_json.get("interests") or profile_json.get("hobbies") or []
    if isinstance(raw_interests, str):
        raw_interests = [raw_interests]
    if not isinstance(raw_interests, list):
        return rows
    for item in raw_interests:
        if not isinstance(item, str):
            continue
        for value in re.split(r"[\n;|]+", item):
            text = clean_text_field(value, check_review_markers=False)
            if text:
                rows.append(text)
    return _dedup_preserve(rows)[:6]


def _reconcile_projects_and_interests_sections(
    cv_json: Dict[str, Any],
    profile_json: Dict[str, Any],
) -> None:
    if not isinstance(cv_json, dict) or not isinstance(profile_json, dict):
        return

    projects = cv_json.get("projects")
    if not isinstance(projects, list) or not projects:
        profile_projects = _extract_profile_projects(profile_json)
        if profile_projects:
            cv_json["projects"] = profile_projects[:2]
            logger.warning(
                "Project reconciliation appended %s missing profile entries.",
                min(2, len(profile_projects)),
            )
    else:
        profile_projects = _extract_profile_projects(profile_json)
        if profile_projects:
            reconciled_projects: List[Dict[str, Any]] = []
            changed_count = 0
            for project in projects:
                if not isinstance(project, dict):
                    continue
                best_profile = None
                best_score = 0.0
                for profile_project in profile_projects:
                    score = _score_profile_project_match(project, profile_project)
                    if score > best_score:
                        best_score = score
                        best_profile = profile_project
                if best_profile is not None and best_score >= 0.72:
                    merged_project = _merge_project_with_profile_evidence(
                        project, best_profile
                    )
                    if merged_project != project:
                        changed_count += 1
                    reconciled_projects.append(merged_project)
                else:
                    reconciled_projects.append(project)
            if reconciled_projects:
                cv_json["projects"] = reconciled_projects
            if changed_count:
                logger.warning(
                    "Project reconciliation enriched %s profile-backed entries.",
                    changed_count,
                )

    interests = cv_json.get("interests")
    if not isinstance(interests, list) or not interests:
        profile_interests = _extract_profile_interests(profile_json)
        if profile_interests:
            cv_json["interests"] = profile_interests
            logger.warning(
                "Interest reconciliation appended %s missing profile entries.",
                len(profile_interests),
            )


def _rebuild_skills_section_from_profile(
    cv_json: Dict[str, Any],
    profile_json: Dict[str, Any],
    *,
    language_code: str = "fr",
    offer_terms: Optional[Sequence[str]] = None,
) -> None:
    if not isinstance(cv_json, dict) or not isinstance(profile_json, dict):
        return

    try:
        from .cv_skill_recovery import (
            build_skill_blocks_from_profile,
            skills_section_claims_benchmark_only_tools,
            skills_section_low_signal,
        )
        from .cv_skill_evidence import (
            looks_like_noise_skill_term,
            skills_section_has_supported_signal,
        )
    except Exception:
        return

    def current_skills_need_theming(skills_section: Any) -> bool:
        if not isinstance(skills_section, list) or not skills_section:
            return False
        generic_categories = {
            "competence",
            "competences",
            "competence technique",
            "competences techniques",
            "hard skill",
            "hard skills",
            "skill",
            "skills",
            "technical skill",
            "technical skills",
        }
        non_soft_blocks: List[Dict[str, Any]] = []
        item_count = 0
        noisy_count = 0
        long_count = 0
        generic_count = 0
        for block in skills_section:
            if not isinstance(block, dict):
                continue
            category_norm = _normalize_for_match(block.get("category") or "")
            if category_norm in {"soft skills", "soft skill", "qualites"}:
                continue
            non_soft_blocks.append(block)
            if category_norm in generic_categories:
                generic_count += 1
            for item in block.get("items") or []:
                if not isinstance(item, str) or not item.strip():
                    continue
                item_count += 1
                item_norm = _normalize_for_match(item)
                if looks_like_noise_skill_term(item):
                    noisy_count += 1
                if len(item_norm.split()) >= 5 or re.search(
                    r"\b(?:including|recruteur|ai powered|products?|you)\b",
                    item_norm,
                ):
                    long_count += 1
        if not non_soft_blocks or item_count < 6:
            return False
        return bool(generic_count and (len(non_soft_blocks) <= 1 or noisy_count or long_count))

    current_skills = cv_json.get("skills")
    current_is_usable = False
    if isinstance(current_skills, list) and current_skills:
        current_is_usable = not skills_section_low_signal(current_skills, profile_json)
        if current_is_usable:
            supported, plausible, hard_unsupported = (
                skills_section_has_supported_signal(current_skills, profile_json)
            )
            if supported < 2 and (plausible + hard_unsupported) >= 2:
                current_is_usable = False
        if current_is_usable and current_skills_need_theming(current_skills):
            current_is_usable = False
        if current_is_usable and skills_section_claims_benchmark_only_tools(
            current_skills,
            profile_json,
            language_code=language_code,
        ):
            current_is_usable = False
    if current_is_usable:
        return

    recovered = build_skill_blocks_from_profile(
        profile_json,
        language_code=language_code,
        offer_terms=list(offer_terms) if offer_terms else (),
    )
    if not recovered:
        return

    cv_json["skills"] = recovered
    logger.warning(
        "Skills reconciliation rebuilt %s profile-backed blocks.",
        len(recovered),
    )


def reconcile_cv_sections_with_profile(
    cv_json: Dict[str, Any],
    profile_json: Dict[str, Any],
    *,
    language_code: str = "fr",
    offer_terms: Optional[Sequence[str]] = None,
    job_title: str = "",
) -> None:
    if not isinstance(cv_json, dict) or not isinstance(profile_json, dict):
        return
    _reconcile_experience_section(
        cv_json,
        profile_json,
        language_code=language_code,
        offer_keywords=offer_terms,
        job_title=job_title,
    )
    _rebuild_skills_section_from_profile(
        cv_json,
        profile_json,
        language_code=language_code,
        offer_terms=offer_terms,
    )
    _reconcile_education_section(cv_json, profile_json)
    _reconcile_languages_section(cv_json, profile_json)
    _reconcile_projects_and_interests_sections(cv_json, profile_json)


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
    *,
    language_code: str = "fr",
    offer_keywords: Optional[Sequence[str]] = None,
    job_title: str = "",
) -> int:
    if not isinstance(cv_json, dict):
        return 0
    existing = cv_json.get("experience")
    if isinstance(existing, list) and existing:
        return 0

    profile_experiences = _extract_profile_experiences(profile_json)
    if offer_keywords and profile_experiences:
        try:
            from app.utils.cv_fallback_generator import rank_experiences_by_offer_relevance

            profile_experiences = rank_experiences_by_offer_relevance(
                profile_experiences, list(offer_keywords), job_title=job_title or ""
            )
        except Exception as exc:
            logger.debug("Seed offer-ranking skipped: %s", exc)

    seeded: List[Dict[str, Any]] = []
    for item in profile_experiences[:4]:
        fallback_description = item.get("description") or ""
        description_candidates = _collect_experience_source_candidates(
            fallback_description,
            company=item.get("company") or "",
            language_code=language_code,
        )
        summary = _select_action_summary(
            "",
            highlights=[],
            fallback_description=fallback_description,
            company=item.get("company") or "",
            language_code=language_code,
        )
        highlights = _dedup_fuzzy_highlights(
            [
                value
                for value in extract_experience_highlights(
                    fallback_description,
                    company=item.get("company") or "",
                    language_code=language_code,
                )
                if str(value or "").strip()
            ]
        )[:4]
        if summary and len(highlights) > 1 and _is_same_narrative(summary, highlights[0]):
            highlights = highlights[1:]

        seeded.append(
            {
                "title": item.get("title") or "",
                "company": item.get("company") or "",
                "start_date": item.get("start_date") or "",
                "end_date": item.get("end_date") or "",
                "duration": _compute_duration_label(
                    item.get("start_date") or "",
                    item.get("end_date") or "",
                    language_code=language_code,
                ),
                "location": item.get("location") or "",
                "summary": _trim_text(summary, 280),
                "highlights": highlights[:4],
                "description": description_candidates,
            }
        )

    if seeded:
        cv_json["experience"] = seeded
    return len(seeded)


def rebalance_cv_narrative(
    cv_json: Dict[str, Any],
    *,
    profile_json: Dict[str, Any],
    language_code: str = "fr",
    offer_keywords: Optional[Sequence[str]] = None,
    job_title: str = "",
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

    seeded_count = _seed_experience_from_profile(
        cv_json,
        profile_json,
        language_code=language_code,
        offer_keywords=offer_keywords,
        job_title=job_title,
    )
    if seeded_count:
        logger.info(
            "Experience section rebuilt from profile data: entries=%s", seeded_count
        )

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
            entry_summary = (
                _trim_text(" ".join(kept), 280)
                if kept
                else _trim_text(entry_summary, 280)
            )
        else:
            entry_summary = _trim_text(entry_summary, 280)

        highlights: List[str] = []
        for value in entry.get("highlights") or []:
            if not isinstance(value, str):
                continue
            text = _polish_experience_fragment(
                value,
                company=str(entry.get("company") or ""),
                language_code=language_code,
                prefer_articleless=True,
            )
            if not text:
                continue
            highlights.append(text)
        highlights = _dedup_preserve(highlights)

        matched_profile = _best_profile_match(entry, profile_experiences)
        profile_description = (
            matched_profile.get("description")
            if isinstance(matched_profile, dict)
            else ""
        )
        description_candidates = _collect_experience_source_candidates(
            entry.get("description"),
            company=str(entry.get("company") or ""),
            language_code=language_code,
        )
        if profile_description:
            description_candidates = _dedup_fuzzy_highlights(
                _dedup_preserve(
                    [
                        *description_candidates,
                        *_collect_experience_source_candidates(
                            profile_description,
                            company=str(entry.get("company") or ""),
                            language_code=language_code,
                        ),
                    ]
                )
            )[:12]

        if not entry_summary and profile_description:
            entry_summary = _select_action_summary(
                "",
                highlights=highlights,
                fallback_description=profile_description,
                company=str(entry.get("company") or ""),
                language_code=language_code,
            )

        highlight_candidates: List[str] = []
        highlight_candidates.extend(entry_overflow)
        if profile_description:
            highlight_candidates.extend(
                extract_experience_highlights(
                    profile_description,
                    company=str(entry.get("company") or ""),
                    language_code=language_code,
                )
            )
        if not highlight_candidates and entry_sentences:
            highlight_candidates.extend(entry_sentences[1:])

        for candidate in highlight_candidates:
            text = _polish_experience_fragment(
                candidate,
                company=str(entry.get("company") or ""),
                language_code=language_code,
                prefer_articleless=True,
            )
            if not text:
                continue
            if entry_summary and _is_same_narrative(entry_summary, text):
                continue
            highlights.append(text)

        highlights = _dedup_preserve(highlights)
        if len(highlights) < 2 and profile_description:
            for candidate in extract_experience_highlights(
                profile_description,
                company=str(entry.get("company") or ""),
                language_code=language_code,
            ):
                text = _polish_experience_fragment(
                    candidate,
                    company=str(entry.get("company") or ""),
                    language_code=language_code,
                    prefer_articleless=True,
                )
                if not text:
                    continue
                if entry_summary and _is_same_narrative(entry_summary, text):
                    continue
                highlights.append(text)
                if len(_dedup_preserve(highlights)) >= 2:
                    break
            highlights = _dedup_preserve(highlights)

        original_highlights = entry.get("highlights")
        original_count = (
            len(original_highlights) if isinstance(original_highlights, list) else 0
        )
        if highlights:
            synthesized_highlights += max(0, len(highlights) - original_count)

        entry_summary = _select_action_summary(
            entry_summary,
            highlights=highlights,
            fallback_description=profile_description,
            company=str(entry.get("company") or ""),
            language_code=language_code,
        )
        if not entry_summary and highlights:
            entry_summary = _trim_text(highlights[0], 220)

        entry["summary"] = _trim_text(entry_summary, 280)
        entry["highlights"] = _dedup_fuzzy_highlights(highlights)[:4]
        if description_candidates:
            entry["description"] = description_candidates

        if isinstance(matched_profile, dict):
            for field in ("title", "company", "start_date", "end_date", "location"):
                if not entry.get(field) and matched_profile.get(field):
                    entry[field] = matched_profile.get(field)
        duration = _compute_duration_label(
            entry.get("start_date") or "",
            entry.get("end_date") or "",
            language_code=language_code,
        )
        if duration:
            entry["duration"] = duration

    if summary_overflow and experience_entries:
        first = (
            experience_entries[0] if isinstance(experience_entries[0], dict) else None
        )
        if isinstance(first, dict):
            first_highlights = first.get("highlights")
            if not isinstance(first_highlights, list):
                first_highlights = []
            for sentence in summary_overflow:
                text = clean_narrative_text(sentence)
                text = _polish_experience_fragment(
                    text,
                    company=str(first.get("company") or ""),
                    language_code=language_code,
                    prefer_articleless=True,
                )
                if not text:
                    continue
                if first.get("summary") and _is_same_narrative(
                    first.get("summary"), text
                ):
                    continue
                first_highlights.append(text)
            first["highlights"] = _dedup_fuzzy_highlights(first_highlights)[:4]

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


def _compute_experience_durations(
    cv_json: Dict[str, Any],
    language_code: str = "fr",
) -> None:
    """Compute deterministic duration labels from normalized date support."""

    for entry in cv_json.get("experience") or []:
        if not isinstance(entry, dict):
            continue
        duration = _compute_duration_label(
            entry.get("start_date") or "",
            entry.get("end_date") or "",
            language_code=language_code,
        )
        if duration:
            entry["duration"] = duration
    return

def _normalize_experience_date_formats(
    cv_json: Dict[str, Any],
    *,
    language_code: str = "fr",
) -> None:
    """Rewrite visible dates without inventing unsupported month precision."""
    try:
        from ..rules.date_normalize import _normalize_single_date, normalize_present_token
    except Exception:
        return

    lang = str(language_code or "fr").strip().lower().split("-", 1)[0] or "fr"
    present_tokens = {
        "fr": "Actuellement",
        "en": "Present",
        "de": "Aktuell",
        "es": "Actualidad",
        "it": "Attuale",
        "pt": "Atual",
    }
    present_display = present_tokens.get(lang, "Present")

    def _to_display(raw: str, *, display_mode: str) -> str:
        s = raw.strip()
        if not s:
            return s
        normalized_present = normalize_present_token(s)
        if str(normalized_present or "").strip().upper() == "PRESENT":
            return present_display
        # Year-only source → keep as bare YYYY (no invented month placeholder)
        if re.fullmatch(r"\d{4}", s):
            return s
        norm = _normalize_single_date(s)
        if not norm:
            return s
        if not re.fullmatch(r"\d{4}-\d{2}", str(norm)):
            return s
        # YYYY-MM → MM/YYYY
        if display_mode == "year":
            return norm[:4]
        return f"{norm[5:7]}/{norm[:4]}"

    for section in ("experience", "education"):
        for entry in cv_json.get(section) or []:
            if not isinstance(entry, dict):
                continue
            metadata = _derive_profile_date_support(
                entry.get("start_date") or "",
                entry.get("end_date") or "",
            )
            precision_values = {
                str(metadata.get("start_date_precision") or ""),
                str(metadata.get("end_date_precision") or ""),
            }
            precision_values.discard("")
            precision_values.discard("present")
            if "year" in precision_values and precision_values & {"month", "day"}:
                display_mode = "year"
            else:
                display_mode = "month"
            for field in ("start_date", "end_date"):
                raw = str(entry.get(field) or "")
                if raw:
                    entry[field] = _to_display(raw, display_mode=display_mode)


_VERB_HEAD_PATTERN = re.compile(r"^[A-Za-zÀ-ÿ']+")

_FR_PAST_PARTICIPLE_MAP: Dict[str, str] = {
    "accompagne": "accompagné",
    "accompagner": "accompagné",
    "ameliore": "amélioré",
    "améliore": "amélioré",
    "ameliorer": "amélioré",
    "améliorer": "amélioré",
    "analyse": "analysé",
    "analyser": "analysé",
    "assure": "assuré",
    "assurer": "assuré",
    "automatise": "automatisé",
    "automatiser": "automatisé",
    "collabore": "collaboré",
    "collaborer": "collaboré",
    "concoit": "conçu",
    "conçoit": "conçu",
    "concevoir": "conçu",
    "consolide": "consolidé",
    "consolider": "consolidé",
    "contribue": "contribué",
    "contribuer": "contribué",
    "coordonne": "coordonné",
    "coordonner": "coordonné",
    "cree": "créé",
    "crée": "créé",
    "creer": "créé",
    "créer": "créé",
    "definit": "défini",
    "définit": "défini",
    "definir": "défini",
    "définir": "défini",
    "deploie": "déployé",
    "déploie": "déployé",
    "deployer": "déployé",
    "déployer": "déployé",
    "developpe": "développé",
    "développe": "développé",
    "developper": "développé",
    "développer": "développé",
    "documente": "documenté",
    "documenter": "documenté",
    "execute": "exécuté",
    "exécute": "exécuté",
    "executer": "exécuté",
    "exécuter": "exécuté",
    "fiabilise": "fiabilisé",
    "fiabiliser": "fiabilisé",
    "gere": "géré",
    "gère": "géré",
    "gerer": "géré",
    "gérer": "géré",
    "identifie": "identifié",
    "identifier": "identifié",
    "implemente": "implémenté",
    "implémente": "implémenté",
    "implementer": "implémenté",
    "implémenter": "implémenté",
    "mene": "mené",
    "mène": "mené",
    "mener": "mené",
    "optimise": "optimisé",
    "optimiser": "optimisé",
    "pilote": "piloté",
    "piloter": "piloté",
    "prepare": "préparé",
    "prépare": "préparé",
    "preparer": "préparé",
    "préparer": "préparé",
    "qualifie": "qualifié",
    "qualifier": "qualifié",
    "realise": "réalisé",
    "réalise": "réalisé",
    "realiser": "réalisé",
    "réaliser": "réalisé",
    "redige": "rédigé",
    "rédige": "rédigé",
    "rediger": "rédigé",
    "rédiger": "rédigé",
    "renforce": "renforcé",
    "renforcer": "renforcé",
    "revoit": "revu",
    "revoir": "revu",
    "structure": "structuré",
    "structurer": "structuré",
    "suit": "suivi",
    "suivre": "suivi",
    "teste": "testé",
    "tester": "testé",
    "valide": "validé",
    "valider": "validé",
}

_EN_PAST_MAP: Dict[str, str] = {
    "analyze": "analyzed",
    "automate": "automated",
    "build": "built",
    "coordinate": "coordinated",
    "create": "created",
    "define": "defined",
    "deliver": "delivered",
    "design": "designed",
    "develop": "developed",
    "document": "documented",
    "drive": "drove",
    "execute": "executed",
    "implement": "implemented",
    "improve": "improved",
    "lead": "led",
    "manage": "managed",
    "optimize": "optimized",
    "prepare": "prepared",
    "qualify": "qualified",
    "reduce": "reduced",
    "review": "reviewed",
    "streamline": "streamlined",
    "structure": "structured",
    "support": "supported",
    "test": "tested",
    "track": "tracked",
    "validate": "validated",
}


def _strip_verb_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", str(text or ""))
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


_CLAUSE_SPLIT_PATTERN = re.compile(
    r"(\s*(?:,|;|\bet\b|\band\b|\bpuis\b|\bthen\b)\s+)",
    re.IGNORECASE,
)


def _rewrite_clause_head(clause: str, mapping: Dict[str, str], lang: str) -> str:
    """Normalize the leading verb of a clause to its past form, preserving case.

    Returns the clause unchanged if its head isn't in the mapping (permissive
    default — unknown verbs are left as authored).
    """
    raw = clause.lstrip()
    if not raw:
        return clause
    leading_ws = clause[: len(clause) - len(raw)]
    match = _VERB_HEAD_PATTERN.match(raw)
    if not match:
        return clause
    head = match.group(0)
    head_lower = head.lower()
    replacement = mapping.get(head_lower)
    if replacement is None and lang == "fr":
        replacement = mapping.get(_strip_verb_accents(head_lower))
    if replacement is None:
        return clause
    if head[0].isupper():
        replacement = replacement[0].upper() + replacement[1:]
    return leading_ws + replacement + raw[len(head):]


def _strip_french_past_auxiliary_head(value: str) -> str:
    text = str(value or "")
    stripped = text.lstrip()
    leading_ws = text[: len(text) - len(stripped)]
    if not re.match(r"(?i)^a\s+\S+", stripped):
        return text
    without_aux = re.sub(r"(?i)^a\s+", "", stripped, count=1)
    if stripped[:1].isupper() and without_aux:
        without_aux = without_aux[:1].upper() + without_aux[1:]
    return leading_ws + without_aux


def _rewrite_past_role_tense(
    cv_json: Dict[str, Any],
    *,
    language_code: str,
) -> None:
    """Rewrite present-tense verb heads to past forms for non-current experiences.

    Scans EVERY clause head in each highlight (split by ``,``, ``;``, ``et``,
    ``and``, ``puis``, ``then``) and normalises it when a mapping exists. Unknown
    heads are left untouched. Capitalisation of the original head is carried
    over to the replacement.
    """
    if not isinstance(cv_json, dict):
        return
    lang = "en" if str(language_code or "").strip().lower().startswith("en") else "fr"
    mapping = _EN_PAST_MAP if lang == "en" else _FR_PAST_PARTICIPLE_MAP

    for entry in cv_json.get("experience") or []:
        if not isinstance(entry, dict):
            continue
        support = _derive_profile_date_support(
            entry.get("start_date") or "",
            entry.get("end_date") or "",
        )
        if bool(support.get("is_current")):
            continue
        highlights = entry.get("highlights")
        if not isinstance(highlights, list):
            continue
        for index, bullet in enumerate(highlights):
            if not isinstance(bullet, str):
                continue
            raw = bullet.strip()
            if not raw:
                continue
            original_raw = raw
            if lang == "fr":
                raw = _strip_french_past_auxiliary_head(raw)
            parts = _CLAUSE_SPLIT_PATTERN.split(raw)
            if len(parts) == 1:
                rewritten = _rewrite_clause_head(parts[0], mapping, lang)
                if rewritten != original_raw:
                    highlights[index] = rewritten + bullet[len(bullet.rstrip()):]
                continue
            # Odd indices are separators (kept verbatim), even indices are
            # clauses whose head verbs we try to normalise.
            rewritten_parts: List[str] = []
            for piece_idx, piece in enumerate(parts):
                if piece_idx % 2 == 0:
                    rewritten_parts.append(_rewrite_clause_head(piece, mapping, lang))
                else:
                    rewritten_parts.append(piece)
            joined = "".join(rewritten_parts)
            if joined != original_raw:
                # Preserve any trailing whitespace/punctuation stripped above.
                trailing = bullet[len(bullet.rstrip()):]
                highlights[index] = joined + trailing


_FR_CURRENT_THIRD_PERSON_MAP: Dict[str, str] = {
    "concois": "con\u00e7oit",
    "dois": "doit",
    "fais": "fait",
    "mets": "met",
    "peux": "peut",
    "prends": "prend",
    "suis": "suit",
    "vais": "va",
    "vois": "voit",
}


def _rewrite_current_role_present_tense(
    cv_json: Dict[str, Any],
    *,
    language_code: str,
) -> None:
    """Repair obvious first-person heads in current-role French bullets."""
    if not isinstance(cv_json, dict):
        return
    if str(language_code or "").strip().lower().startswith("en"):
        return

    for entry in cv_json.get("experience") or []:
        if not isinstance(entry, dict):
            continue
        support = _derive_profile_date_support(
            entry.get("start_date") or "",
            entry.get("end_date") or "",
        )
        if not bool(support.get("is_current")):
            continue
        highlights = entry.get("highlights")
        if not isinstance(highlights, list):
            continue
        for index, bullet in enumerate(highlights):
            if not isinstance(bullet, str):
                continue
            raw = bullet.strip()
            if not raw:
                continue
            parts = _CLAUSE_SPLIT_PATTERN.split(raw)
            rewritten_parts: List[str] = []
            changed = False
            for piece_idx, piece in enumerate(parts):
                if piece_idx % 2 != 0:
                    rewritten_parts.append(piece)
                    continue
                updated = _rewrite_clause_head(
                    piece,
                    _FR_CURRENT_THIRD_PERSON_MAP,
                    "fr",
                )
                if updated == piece:
                    # _rewrite_clause_head checks exact lowercase before the
                    # accent-stripped fallback. Keep an explicit stripped path
                    # for present-tense repair too.
                    raw_piece = piece.lstrip()
                    leading_ws = piece[: len(piece) - len(raw_piece)]
                    match = _VERB_HEAD_PATTERN.match(raw_piece)
                    if match:
                        head = match.group(0)
                        replacement = _FR_CURRENT_THIRD_PERSON_MAP.get(
                            _strip_verb_accents(head.lower())
                        )
                        if replacement:
                            if head[0].isupper():
                                replacement = replacement[0].upper() + replacement[1:]
                            updated = leading_ws + replacement + raw_piece[len(head):]
                if updated != piece:
                    changed = True
                rewritten_parts.append(updated)
            if changed:
                trailing = bullet[len(bullet.rstrip()):]
                highlights[index] = "".join(rewritten_parts) + trailing


_CLIPPED_TRAILING_STOPWORDS_POSTPROCESS = {
    "a", "afin", "au", "aux", "avec", "chez", "dans", "de", "des", "du",
    "en", "entre", "et", "la", "le", "les", "ou", "par", "pour", "sans",
    "sur", "un", "une", "vers",
    "an", "and", "at", "by", "for", "from", "in", "into", "of",
    "on", "onto", "or", "the", "to", "with", "without",
}

_CLIPPED_CLAUSE_BREAKS = re.compile(r"[,;:]")


def _repair_clipped_bullet(text: str) -> str:
    """Peel off trailing ellipsis and orphan stopwords to salvage a clean clause.

    Drops the bullet entirely (returns ``""``) when the residual is shorter
    than 5 tokens. Runs after verb-tense rewriting so the verb head is already
    in its final form.
    """

    raw = str(text or "").strip()
    if not raw:
        return ""

    cleaned = re.sub(r"[\s]*(?:\.\.\.|\u2026)+\s*$", "", raw).rstrip(" ,;:-\u2013\u2014")
    if not cleaned:
        return ""

    # Peel trailing stopwords until the tail looks terminal. Bounded loop so
    # a bullet that is nothing but stopwords eventually drops out.
    for _ in range(8):
        tokens = cleaned.split()
        if not tokens:
            break
        last_lower = tokens[-1].lower().strip("'’\"`")
        if last_lower not in _CLIPPED_TRAILING_STOPWORDS_POSTPROCESS:
            break
        cleaned = cleaned[: -len(tokens[-1])].rstrip(" ,;:-\u2013\u2014")

    if not cleaned or len(cleaned.split()) < 5:
        return ""

    if cleaned[-1] not in ".!?":
        cleaned = cleaned + "."
    return cleaned


def _bullet_looks_clipped(text: str) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False
    if raw.endswith("...") or raw.endswith("\u2026"):
        return True
    tail = raw.rstrip(" .,;:-\u2013\u2014")
    tokens = tail.split()
    if not tokens:
        return False
    last_lower = tokens[-1].lower().strip("'’\"`")
    return last_lower in _CLIPPED_TRAILING_STOPWORDS_POSTPROCESS


# Dash variants that legitimately introduce a new clause inside a bullet.
# Colon ``:`` is intentionally excluded — French convention keeps the word
# after a colon lowercase (apposition / descriptor), and touching it risks
# mangling proper nouns (e.g. ``Careside: filiale numérique de La Poste``).
_INNER_DASH_SEPARATOR_PATTERN = re.compile(r"(\s[\u2013\u2014\-]\s+)([a-zà-ÿ])")


def _normalize_bullet_punctuation(bullet: str) -> str:
    """Capitalise the first letter after an inner dash-separator clause.

    Converts ``"Careside - ingénieur qa"`` → ``"Careside - Ingénieur qa"``.
    Leaves colons alone (FR apposition convention). Leaves already-capital
    letters alone. Returns the bullet unchanged if no inner dash is found.
    """
    if not isinstance(bullet, str) or not bullet.strip():
        return bullet

    def _upper(match: "re.Match[str]") -> str:
        return match.group(1) + match.group(2).upper()

    return _INNER_DASH_SEPARATOR_PATTERN.sub(_upper, bullet)


def _normalize_bullet_punctuation_all(cv_json: Dict[str, Any]) -> None:
    """Apply :func:`_normalize_bullet_punctuation` across experience/education
    highlights as a final pass.
    """
    if not isinstance(cv_json, dict):
        return
    for section_key in ("experience", "education"):
        section = cv_json.get(section_key)
        if not isinstance(section, list):
            continue
        for entry in section:
            if not isinstance(entry, dict):
                continue
            highlights = entry.get("highlights")
            if not isinstance(highlights, list):
                continue
            for idx, bullet in enumerate(highlights):
                if isinstance(bullet, str):
                    highlights[idx] = _normalize_bullet_punctuation(bullet)


def _normalize_punctuation_spacing_text(value: Any, *, language_code: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    is_fr = str(language_code or "").strip().lower().startswith("fr")
    text = re.sub(r"\s+([,.])", r"\1", text)
    if is_fr:
        text = re.sub(r"\s*([;:!?])", r" \1", text)
    else:
        text = re.sub(r"\s+([;:!?])", r"\1", text)
    text = re.sub(r"([,.;:!?])(?=\S)", r"\1 ", text)
    return re.sub(r"\s+", " ", text).strip()


def _normalize_cv_punctuation_all(
    cv_json: Dict[str, Any],
    *,
    language_code: str,
) -> None:
    if not isinstance(cv_json, dict):
        return

    def fix_field(container: Dict[str, Any], key: str) -> None:
        value = container.get(key)
        if isinstance(value, str) and value.strip():
            if key == "technologies":
                cleaned_technologies = _merge_project_technology_values(value)
                if cleaned_technologies:
                    container[key] = cleaned_technologies
                return
            container[key] = _normalize_punctuation_spacing_text(
                value,
                language_code=language_code,
            )

    for key in ("summary",):
        fix_field(cv_json, key)

    for block in cv_json.get("skills") or []:
        if not isinstance(block, dict):
            continue
        fix_field(block, "category")
        items = block.get("items")
        if isinstance(items, list):
            block["items"] = [
                _normalize_punctuation_spacing_text(
                    item,
                    language_code=language_code,
                )
                if isinstance(item, str)
                else item
                for item in items
            ]

    for section_key in ("experience", "education", "projects", "certifications"):
        section = cv_json.get(section_key)
        if not isinstance(section, list):
            continue
        for entry in section:
            if not isinstance(entry, dict):
                continue
            for key in (
                "title",
                "company",
                "summary",
                "degree",
                "school",
                "field_of_study",
                "name",
                "description",
                "technologies",
                "organization",
            ):
                fix_field(entry, key)
            for list_key in ("highlights", "details"):
                values = entry.get(list_key)
                if isinstance(values, list):
                    entry[list_key] = [
                        _normalize_punctuation_spacing_text(
                            item,
                            language_code=language_code,
                        )
                        if isinstance(item, str)
                        else item
                        for item in values
                    ]


def _repair_clipped_bullets(cv_json: Dict[str, Any]) -> None:
    """Trim or drop clipped bullets across all experience entries."""

    if not isinstance(cv_json, dict):
        return
    for entry in cv_json.get("experience") or []:
        if not isinstance(entry, dict):
            continue
        highlights = entry.get("highlights")
        if not isinstance(highlights, list):
            continue
        repaired: List[str] = []
        for bullet in highlights:
            if not isinstance(bullet, str):
                continue
            if not _bullet_looks_clipped(bullet):
                repaired.append(bullet)
                continue
            fixed = _repair_clipped_bullet(bullet)
            if fixed:
                repaired.append(fixed)
        entry["highlights"] = _dedup_fuzzy_highlights(repaired)


def _ensure_company_name_in_summary(
    cv_json: Dict[str, Any],
    company: str,
    language_code: str = "fr",
) -> None:
    """Append a brief targeting phrase if the company name is absent from all visible text.

    Checks summary, experience summaries, and highlights. Only appends to a non-empty
    summary. Must be called before rebalance_cv_narrative so that any overflow trimming
    happens naturally on the enriched text.
    """
    if not isinstance(cv_json, dict) or not company:
        return
    company_norm = _normalize_for_match(company)
    if not company_norm:
        return

    parts = [str(cv_json.get("summary") or "")]
    for exp in cv_json.get("experience") or []:
        if not isinstance(exp, dict):
            continue
        parts.append(str(exp.get("summary") or ""))
        for h in exp.get("highlights") or []:
            parts.append(str(h or ""))

    if company_norm in _normalize_for_match(" ".join(parts)):
        return  # company name already present

    summary = str(cv_json.get("summary") or "")
    if not summary:
        return  # nothing to append to
    if len(re.findall(r"\b\w+\b", summary, flags=re.UNICODE)) >= 10:
        return  # avoid appending a mechanical company tagline onto a substantive summary

    phrase = (
        f"Application targeting {company}."
        if language_code == "en"
        else f"Candidature ciblée chez {company}."
    )
    cv_json["summary"] = summary.rstrip(" .") + f" {phrase}"


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
    keyword_alignment_fn: Optional[
        Callable[[Dict[str, Any], Optional[Dict[str, Any]]], None]
    ] = None,
    offer_adaptation_fn: Optional[
        Callable[[Dict[str, Any], Optional[Dict[str, Any]]], None]
    ] = None,
    offer_terms: Optional[Sequence[str]] = None,
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
    try:
        from .cv_payload_diagnostics import classify_cv_payload_source
    except Exception:
        classify_cv_payload_source = None

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
    contact = (
        dict(merged.get("contact") or {})
        if isinstance(merged.get("contact"), dict)
        else {}
    )
    if isinstance(incoming_contact, dict):
        for field in ("full_name", "email", "phone", "linkedin_url", "location"):
            value = incoming_contact.get(field)
            if isinstance(value, str) and value.strip():
                contact[field] = value.strip()
        incoming_links = _normalize_contact_links(incoming_contact.get("links"))
        if incoming_links:
            contact["links"] = incoming_links
    merged["contact"] = contact

    # Merge list sections
    list_sections = (
        "skills",
        "experience",
        "education",
        "projects",
        "languages",
        "certifications",
        "interests",
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

    # Compute durations before date normalization (parser needs original date strings).
    _compute_experience_durations(merged, language_code=language_code)
    # Normalize date formats to MM/YYYY after duration is already computed.
    _normalize_experience_date_formats(merged, language_code=language_code)
    # Rewrite present-tense verb heads to past forms for non-current roles.
    _rewrite_past_role_tense(merged, language_code=language_code)
    # Repair obvious first-person heads in current-role French bullets.
    _rewrite_current_role_present_tense(merged, language_code=language_code)
    # Trim or drop clipped bullets (ellipsis endings or trailing stopwords).
    _repair_clipped_bullets(merged)
    # Final style pass: capitalise first letter after inner dash separators.
    _normalize_bullet_punctuation_all(merged)
    # Inject company name into visible summary text if absent.
    # Must run before rebalance_cv_narrative which may trim the summary.
    _ensure_company_name_in_summary(merged, company=company, language_code=language_code)

    # Sanitize
    sanitize_cv_json_output(merged, language_code=language_code)
    reconcile_cv_sections_with_profile(
        merged,
        profile_json,
        language_code=language_code,
        offer_terms=offer_terms,
        job_title=job_title,
    )
    # Reconcile may assign raw profile date strings (e.g. 'Présent' → 'PRESENT')
    # onto entry.end_date, clobbering the earlier localization. Re-localize.
    _normalize_experience_date_formats(merged, language_code=language_code)

    # Apply keyword alignment if provided
    if keyword_alignment_fn:
        try:
            keyword_alignment_fn(merged, critic_json)
        except Exception as exc:
            logger.warning(
                "Keyword alignment postprocess failed; keeping deterministic candidate: %s",
                exc,
            )

    # Apply offer adaptation if provided
    if offer_adaptation_fn:
        try:
            offer_adaptation_fn(merged, critic_json)
        except Exception as exc:
            logger.warning(
                "Offer adaptation postprocess failed; keeping deterministic candidate: %s",
                exc,
            )

    # Deterministic quality pass: avoid overstuffed summary + empty bullets.
    rebalance_cv_narrative(
        merged,
        profile_json=profile_json,
        language_code=language_code,
        offer_keywords=offer_terms,
        job_title=job_title,
    )

    # Re-sanitize after optional post-merge transformations.
    sanitize_cv_json_output(merged, language_code=language_code)
    reconcile_cv_sections_with_profile(
        merged,
        profile_json,
        language_code=language_code,
        offer_terms=offer_terms,
        job_title=job_title,
    )
    _normalize_experience_date_formats(merged, language_code=language_code)

    # Second offer-adaptation pass: rebalance/reconcile may overwrite
    # earlier keyword injections in summary/experience.
    if offer_adaptation_fn:
        try:
            offer_adaptation_fn(merged, critic_json)
        except Exception as exc:
            logger.warning(
                "Second-pass offer adaptation failed; keeping deterministic candidate: %s",
                exc,
            )
        else:
            sanitize_cv_json_output(merged, language_code=language_code)
            reconcile_cv_sections_with_profile(
                merged,
                profile_json,
                language_code=language_code,
                offer_terms=offer_terms,
                job_title=job_title,
            )
            _normalize_experience_date_formats(merged, language_code=language_code)
            rebalance_cv_narrative(
                merged,
                profile_json=profile_json,
                language_code=language_code,
                offer_keywords=offer_terms,
                job_title=job_title,
            )
            sanitize_cv_json_output(merged, language_code=language_code)
            reconcile_cv_sections_with_profile(
                merged,
                profile_json,
                language_code=language_code,
                offer_terms=offer_terms,
                job_title=job_title,
            )
            _normalize_experience_date_formats(merged, language_code=language_code)

    if callable(classify_cv_payload_source):
        try:
            source, stats = classify_cv_payload_source(payload, merged)
            logger.info(
                "Final CV candidate source: source=%s payload_text=%s payload_lists=%s "
                "payload_contact=%s payload_render_hints=%s payload_signals=%s "
                "merged_signals=%s fill_ratio=%s%%",
                source,
                stats.get("payload_text_fields", 0),
                stats.get("payload_list_fields", 0),
                stats.get("payload_contact_fields", 0),
                stats.get("payload_render_hints", 0),
                stats.get("payload_total_signals", 0),
                stats.get("merged_total_signals", 0),
                stats.get("fill_ratio_pct", 0),
            )
        except Exception as exc:
            logger.warning("Final CV candidate source diagnostic failed: %s", exc)

    _rewrite_past_role_tense(merged, language_code=language_code)
    _rewrite_current_role_present_tense(merged, language_code=language_code)
    _normalize_bullet_punctuation_all(merged)
    _normalize_cv_punctuation_all(merged, language_code=language_code)
    _dedup_experience_sections_in_place(merged)
    _enforce_single_page_budget(merged)
    return merged


# Soft cap for total bullet count across all experience entries. At typical
# A4 density (~10.5pt, normal margins, 3-4 roles, summary + skills + project
# + education/certifications), 22 bullets remains a safe upper bound before
# the measured fit-to-page pass has to compress too aggressively. The render
# pipeline now prefers prioritized content + measured compression over hard
# clipping, and this budget keeps experience verbosity within that envelope.
_ONE_PAGE_TOTAL_BULLET_BUDGET = 22
_ONE_PAGE_MAX_BULLETS_PER_ROLE = 4


def _enforce_single_page_budget(cv_json: Dict[str, Any]) -> None:
    """Trim experience highlights so the rendered CV still fits one A4 page.

    Safety net complementing the measured fit-to-page render pass: drops the
    LAST bullet of the LONGEST role iteratively until total bullet count is
    within budget.
    Each role keeps at least one bullet (preserves signal per experience).
    Also caps each role at ``_ONE_PAGE_MAX_BULLETS_PER_ROLE``.
    """

    if not isinstance(cv_json, dict):
        return
    experiences = cv_json.get("experience")
    if not isinstance(experiences, list):
        return

    entries: List[Dict[str, Any]] = [
        item for item in experiences if isinstance(item, dict)
    ]
    if not entries:
        return

    # Per-role cap first (cheap; catches upstream paths that bypassed [:4]).
    for entry in entries:
        highlights = entry.get("highlights")
        if isinstance(highlights, list) and len(highlights) > _ONE_PAGE_MAX_BULLETS_PER_ROLE:
            entry["highlights"] = highlights[:_ONE_PAGE_MAX_BULLETS_PER_ROLE]

    def _total_bullets() -> int:
        return sum(
            len(e.get("highlights") or [])
            for e in entries
            if isinstance(e.get("highlights"), list)
        )

    trimmed = 0
    while _total_bullets() > _ONE_PAGE_TOTAL_BULLET_BUDGET:
        longest_idx = -1
        longest_len = 1  # keep at least one bullet per role
        for idx, entry in enumerate(entries):
            highlights = entry.get("highlights")
            if not isinstance(highlights, list):
                continue
            if len(highlights) > longest_len:
                longest_len = len(highlights)
                longest_idx = idx
        if longest_idx < 0:
            break  # no role has > 1 bullet; cannot trim further safely
        entries[longest_idx]["highlights"] = entries[longest_idx]["highlights"][:-1]
        trimmed += 1

    if trimmed:
        logger.info(
            "One-page budget enforced: dropped %s last-bullets to stay within %s total.",
            trimmed,
            _ONE_PAGE_TOTAL_BULLET_BUDGET,
        )


def extract_experience_highlights(
    description: str,
    *,
    company: str = "",
    language_code: str = "fr",
    max_items: int = 4,
) -> List[str]:
    """Extract bullet-point highlights from experience description.

    Args:
        description: Experience description text

    Returns:
        List of highlight strings
    """
    if not description:
        return []

    normalized = str(description or "").replace("•", "-").replace("▪", "-")
    normalized = normalized.replace("➜", "-").replace("✓", "-")
    normalized = re.sub(r"\s*;\s*", "\n", normalized)
    normalized = re.sub(r"(?:(?<=:)|^)\s*-\s+", "\n", normalized)

    highlights: List[str] = []
    for part in re.split(r"[\r\n]+|(?<=[\.\!\?])\s+", normalized):
        cleaned = _polish_experience_fragment(
            part.strip(" -*\t"),
            company=company,
            language_code=language_code,
            prefer_articleless=True,
        )
        if cleaned:
            highlights.append(cleaned)

    return _dedup_preserve(highlights)[: max(1, int(max_items or 1))]


def _collect_experience_source_candidates(
    description: Any,
    *,
    company: str = "",
    language_code: str = "fr",
    max_items: int = 12,
) -> List[str]:
    if isinstance(description, str):
        raw_items = [description] if description.strip() else []
    elif isinstance(description, list):
        raw_items = [
            item for item in description if isinstance(item, str) and item.strip()
        ]
    else:
        raw_items = []

    candidates: List[str] = []
    for raw in raw_items:
        candidates.extend(
            extract_experience_highlights(
                raw,
                company=company,
                language_code=language_code,
                max_items=max_items,
            )
        )
    return _dedup_fuzzy_highlights(_dedup_preserve(candidates))[:max_items]


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
    missing_skills_terms: Optional[List[str]] = None,
    missing_projects_terms: Optional[List[str]] = None,
    missing_education_terms: Optional[List[str]] = None,
    missing_certification_terms: Optional[List[str]] = None,
    missing_language_terms: Optional[List[str]] = None,
    summary_term_limit: Optional[int] = None,
    experience_term_limit: Optional[int] = None,
    language_code: str = "fr",
    profile_json: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Enforce CV adaptation to job offer requirements.

    This function primarily enforces alignment in summary and experience,
    and can also reinforce skills, projects, education, certifications and
    language ordering when those sections are present.

    Adaptation policy:
    - Creative reformulation is allowed.
    - Facts should stay grounded in existing CV/profile sections.
    - No new top-level experience/certification entries are created.

    Args:
        cv_json: CV JSON dictionary (modified in place)
        job_title: Target job title
        company: Target company name
        aligned_terms: List of offer-aligned keyword terms
        missing_summary_terms: Terms missing from summary
        missing_experience_terms: Terms missing from experience
        missing_skills_terms: Terms missing from skills section
        missing_projects_terms: Terms missing from projects section
        missing_education_terms: Terms missing from education section
        missing_certification_terms: Terms missing from certifications section
        missing_language_terms: Terms missing from languages section
        summary_term_limit: Optional max terms injected into summary adaptation
        experience_term_limit: Optional max terms injected into experience adaptation
        language_code: Language code for generated text

    Returns:
        The modified cv_json
    """
    if not isinstance(cv_json, dict):
        return cv_json

    initial_experience_count = (
        len(cv_json.get("experience"))
        if isinstance(cv_json.get("experience"), list)
        else None
    )
    initial_certification_count = (
        len(cv_json.get("certifications"))
        if isinstance(cv_json.get("certifications"), list)
        else None
    )

    try:
        from .cv_offer_term_routing import route_term_to_section
        from .cv_skill_evidence import (
            classify_skill_bucket,
            collect_supported_skill_terms,
            looks_like_noise_skill_term,
        )
        from .keyword_alignment import (
            normalize_keyword_for_match,
            normalized_term_in_probe as normalized_term_present,
        )
        from .cv_skill_ranking import rank_skill_blocks_by_relevance
        from .cv_summary_adaptation import (
            build_targeted_summary_focus_sentence,
            collect_targeted_offer_terms,
            build_summary_focus_sentence,
            is_minimum_summary_template,
            strip_deterministic_summary_appendices,
            strip_positioning_sentences,
        )
    except Exception:
        return cv_json

    is_en = language_code == "en"
    missing_skills_terms = list(missing_skills_terms or [])
    missing_projects_terms = list(missing_projects_terms or [])
    missing_education_terms = list(missing_education_terms or [])
    missing_certification_terms = list(missing_certification_terms or [])
    missing_language_terms = list(missing_language_terms or [])

    def _prepare_terms(
        raw_terms: List[Any], *, limit: Optional[int] = None
    ) -> List[str]:
        terms = _dedup_preserve(
            [str(term or "").strip() for term in raw_terms if str(term or "").strip()]
        )
        if isinstance(limit, int) and limit > 0:
            return terms[:limit]
        return terms

    def _append_render_hint_note(note: str) -> None:
        clean_note = clean_text_field(
            note or "",
            max_length=240,
            check_review_markers=False,
        )
        if not clean_note:
            return
        render_hints = cv_json.get("render_hints")
        if not isinstance(render_hints, dict):
            render_hints = {}
            cv_json["render_hints"] = render_hints
        existing_notes = clean_text_field(
            render_hints.get("notes") or "",
            max_length=0,
            check_review_markers=False,
        )
        chunks = [part.strip() for part in existing_notes.split(" | ") if part.strip()]
        if clean_note not in chunks:
            chunks.append(clean_note)
        render_hints["notes"] = _trim_text(" | ".join(chunks), 1200)

    def _sanitize_adapted_skill_term(raw_term: Any) -> str:
        term = clean_text_field(
            raw_term or "",
            max_length=80,
            check_review_markers=False,
        )
        if not term:
            return ""
        term = SKILL_LABEL_PREFIX_PATTERN.sub("", term).strip(" :-")
        if not term:
            return ""
        if looks_like_noise_skill_term(term):
            return ""
        term_norm = normalize_keyword_for_match(term)
        if not term_norm:
            return ""
        if term_norm in {
            "skill",
            "skills",
            "competence",
            "competences",
            "technical skill",
            "technical skills",
        }:
            return ""
        role_norm = (
            unicodedata.normalize("NFKD", term.casefold())
            .encode("ascii", "ignore")
            .decode("ascii")
        )
        role_norm = re.sub(r"[^\w]+", " ", role_norm, flags=re.UNICODE)
        role_norm = re.sub(r"\s+", " ", role_norm).strip()
        tokens = [tok for tok in role_norm.split() if tok]
        if not tokens:
            return ""
        role_tokens = [tok for tok in tokens if tok in ROLE_LIKE_SKILL_TOKENS]
        if role_tokens:
            non_role_tokens = [
                tok
                for tok in tokens
                if tok not in ROLE_LIKE_SKILL_TOKENS and len(tok) > 2
            ]
            if not non_role_tokens and len(tokens) <= 4:
                return ""
        return term

    def _is_supported_experience_term(raw_term: Any) -> bool:
        term = clean_text_field(
            raw_term or "",
            max_length=120,
            check_review_markers=False,
        )
        if not term:
            return False
        if route_term_to_section(term) != "experience":
            return False
        if looks_like_noise_skill_term(term):
            return False
        term_norm = normalize_keyword_for_match(term)
        if not term_norm:
            return False
        if term_norm in {"mission", "missions", "responsibility", "responsibilities"}:
            return False
        return True

    # Enforce job title and company in summary
    original_summary = str(cv_json.get("summary") or "").strip()
    summary = strip_deterministic_summary_appendices(original_summary)
    summary_norm = normalize_keyword_for_match(summary)
    summary_additions: List[str] = []
    summary_is_minimum = is_minimum_summary_template(summary)

    # Add missing aligned terms to summary
    missing_summary_terms = _prepare_terms(
        missing_summary_terms,
        limit=summary_term_limit,
    )
    focus_sentence = ""
    summary_focus_limit = (
        min(4, int(summary_term_limit or 3))
        if isinstance(summary_term_limit, int) and summary_term_limit > 0
        else 3
    )
    aligned_summary_terms = _prepare_terms(aligned_terms)
    candidate_summary_terms = missing_summary_terms or aligned_summary_terms
    summary_supported_terms: List[str] = []
    if isinstance(profile_json, dict) and profile_json:
        support_seed_terms = aligned_summary_terms or candidate_summary_terms
        supported_summary_buckets = collect_supported_skill_terms(
            support_seed_terms,
            profile_json,
            require_profile_evidence=True,
        )
        summary_supported_terms = _dedup_preserve(
            list(supported_summary_buckets.get("technical") or [])
            + list(supported_summary_buckets.get("soft") or [])
        )
    targeted_summary_terms = collect_targeted_offer_terms(
        summary_supported_terms + candidate_summary_terms,
        profile_json=profile_json if isinstance(profile_json, dict) else None,
        max_terms=summary_focus_limit,
        excluded_terms=[job_title, company],
        job_title=job_title,
    )
    summary_missing_target_signal = not any(
        normalized_term_present(summary_norm, normalize_keyword_for_match(term))
        for term in targeted_summary_terms
        if normalize_keyword_for_match(term)
    )
    if summary and targeted_summary_terms:
        summary = strip_positioning_sentences(summary, language_code)
        summary_norm = _normalize_for_match(summary) if summary else ""
        summary_missing_target_signal = not any(
            normalized_term_present(summary_norm, normalize_keyword_for_match(term))
            for term in targeted_summary_terms
            if normalize_keyword_for_match(term)
        )
    if (
        targeted_summary_terms
        and (
            not summary
            or summary_is_minimum
            or summary_missing_target_signal
        )
    ):
        focus_sentence = build_targeted_summary_focus_sentence(
            targeted_summary_terms,
            company=company,
            language_code=language_code,
            max_terms=summary_focus_limit,
        )
    elif not summary and missing_summary_terms and not summary_is_minimum:
        focus_sentence = build_summary_focus_sentence(
            missing_summary_terms,
            language_code=language_code,
            max_terms=summary_focus_limit,
        )
    if focus_sentence:
        summary_additions.append(focus_sentence)

    if summary_additions:
        summary = (
            f"{summary} {' '.join(summary_additions)}".strip()
            if summary
            else " ".join(summary_additions)
        )
        cv_json["summary"] = clean_narrative_text(summary)
    elif summary != original_summary:
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

        def choose_target_entry(
            term_norm: str,
        ) -> Tuple[Dict[str, Any], Optional[Dict[str, str]]]:
            best_idx = 0
            best_score = -1.0
            best_profile: Optional[Dict[str, str]] = None

            for idx, entry in enumerate(experience_entries):
                score = 0.0
                probe_norm = normalize_keyword_for_match(entry_probe(entry))
                if term_norm and normalized_term_present(probe_norm, term_norm):
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
                    if term_norm and normalized_term_present(
                        profile_desc_norm, term_norm
                    ):
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
                context_candidates.extend(
                    extract_experience_highlights(
                        profile_desc,
                        company=str(entry.get("company") or ""),
                        language_code=language_code,
                    )
                )

            context_candidates.extend(_split_sentences(str(entry.get("summary") or "")))
            highlights = entry.get("highlights")
            if isinstance(highlights, list):
                for item in highlights:
                    if isinstance(item, str) and item.strip():
                        context_candidates.append(item)

            best_candidate = ""
            best_score = -1
            for candidate in context_candidates:
                text = _polish_experience_fragment(
                    candidate,
                    company=str(entry.get("company") or ""),
                    language_code=language_code,
                    prefer_articleless=True,
                )
                if not text:
                    continue
                text_norm = normalize_keyword_for_match(text)
                score = 0
                if normalized_term_present(text_norm, keyword_norm):
                    score += 5
                if len(text.split()) <= 20:
                    score += 1
                if score > best_score:
                    best_score = score
                    best_candidate = text.rstrip(" .")

            if not best_candidate:
                return ""
            if not normalized_term_present(
                normalize_keyword_for_match(best_candidate), keyword_norm
            ):
                return ""

            bullet = clean_narrative_text(_trim_text(f"{best_candidate}.", 240))
            if not normalized_term_present(
                normalize_keyword_for_match(bullet), keyword_norm
            ):
                return ""
            return bullet

        missing_experience_terms = _prepare_terms(
            missing_experience_terms,
            limit=experience_term_limit,
        )
        missing_experience_terms = [
            term
            for term in missing_experience_terms
            if _is_supported_experience_term(term)
        ]

        added = 0
        for keyword in missing_experience_terms:
            keyword_norm = normalize_keyword_for_match(keyword)
            if not keyword_norm:
                continue

            already_present = False
            for entry in experience_entries:
                probe_norm = normalize_keyword_for_match(entry_probe(entry))
                if normalized_term_present(probe_norm, keyword_norm):
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

            cleaned_highlights = [
                item for item in highlights if isinstance(item, str) and item.strip()
            ]
            # Keep injected bullet even when target entry already has 4 highlights.
            target_entry["highlights"] = _dedup_fuzzy_highlights(
                [new_bullet] + cleaned_highlights
            )[:4]
            added += 1

        if added:
            logger.info(
                "Offer adaptation injected critic keywords into experience bullets: added=%s",
                added,
            )

    # Add missing terms to skills section when present.
    skills_section = cv_json.get("skills")
    if isinstance(skills_section, list) and missing_skills_terms:
        skills_entries = [item for item in skills_section if isinstance(item, dict)]
        if skills_entries:
            supported_skill_terms: Dict[str, List[str]] = {
                "technical": [],
                "soft": [],
            }
            if isinstance(profile_json, dict) and profile_json:
                supported_skill_terms = collect_supported_skill_terms(
                    missing_skills_terms, profile_json
                )
            else:
                for term in _prepare_terms(missing_skills_terms):
                    clean_term = _sanitize_adapted_skill_term(term)
                    if not clean_term:
                        continue
                    term_norm = normalize_keyword_for_match(clean_term)
                    if not term_norm:
                        continue
                    if route_term_to_section(clean_term) != "skills":
                        continue
                    bucket = classify_skill_bucket(clean_term)
                    supported_skill_terms.setdefault(bucket, []).append(clean_term)
                for bucket, values in list(supported_skill_terms.items()):
                    supported_skill_terms[bucket] = _dedup_preserve(values)

            def _skill_block_bucket(block: Dict[str, Any]) -> str:
                category_norm = normalize_keyword_for_match(block.get("category"))
                if any(
                    marker in category_norm
                    for marker in (
                        "soft",
                        "qualite",
                        "qualites",
                        "behavior",
                        "behaviour",
                        "interpersonal",
                    )
                ):
                    return "soft"
                return "technical"

            def _select_skill_block(bucket: str) -> Dict[str, Any]:
                target = None
                target_len = 10_000
                for block in skills_entries:
                    if _skill_block_bucket(block) != bucket:
                        continue
                    items = block.get("items")
                    if not isinstance(items, list):
                        continue
                    items_len = len(items)
                    if items_len < target_len:
                        target = block
                        target_len = items_len
                if target is not None:
                    return target
                if bucket == "soft":
                    target = {
                        "category": "Soft Skills" if is_en else "Qualites",
                        "items": [],
                    }
                else:
                    target = {
                        "category": (
                            "Technical Skills" if is_en else "Competences techniques"
                        ),
                        "items": [],
                    }
                skills_section.append(target)
                skills_entries.append(target)
                return target

            def skills_probe() -> str:
                parts: List[str] = []
                for block in skills_entries:
                    category = block.get("category")
                    if isinstance(category, str) and category.strip():
                        parts.append(category)
                    items = block.get("items")
                    if isinstance(items, list):
                        for item in items:
                            if isinstance(item, str) and item.strip():
                                parts.append(item)
                return normalize_keyword_for_match(" ".join(parts))

            current_probe = skills_probe()
            added_skills = 0
            for bucket in ("technical", "soft"):
                skill_terms = _prepare_terms(supported_skill_terms.get(bucket) or [])
                for term in skill_terms:
                    clean_term = _sanitize_adapted_skill_term(term)
                    if not clean_term:
                        continue
                    term_norm = normalize_keyword_for_match(clean_term)
                    if not term_norm:
                        continue
                    if normalized_term_present(current_probe, term_norm):
                        continue

                    target = _select_skill_block(bucket)
                    items = target.get("items")
                    if not isinstance(items, list):
                        items = []
                    target["items"] = _dedup_preserve(
                        [
                            clean_term,
                            *[
                                item
                                for item in items
                                if isinstance(item, str) and item.strip()
                            ],
                        ]
                    )[:10]
                    current_probe = skills_probe()
                    added_skills += 1

            if added_skills:
                logger.info(
                    "Offer adaptation reinforced skills section: added=%s",
                    added_skills,
                )

    if isinstance(skills_section, list) and skills_section:
        ranked_skills = rank_skill_blocks_by_relevance(
            [item for item in skills_section if isinstance(item, dict)],
            _dedup_preserve([*missing_skills_terms, *aligned_terms]),
        )
        if ranked_skills and ranked_skills != skills_section:
            cv_json["skills"] = ranked_skills
            skills_section = ranked_skills
            logger.info("Offer adaptation reordered skills section by offer relevance.")

    # Add missing terms to projects section when present.
    projects_section = cv_json.get("projects")
    if isinstance(projects_section, list) and missing_projects_terms:
        project_entries = [item for item in projects_section if isinstance(item, dict)]
        if project_entries:

            def project_probe() -> str:
                parts: List[str] = []
                for entry in project_entries:
                    for key in ("name", "description", "technologies"):
                        value = entry.get(key)
                        if isinstance(value, str) and value.strip():
                            parts.append(value)
                return normalize_keyword_for_match(" ".join(parts))

            current_probe = project_probe()
            added_projects = 0
            project_terms = _prepare_terms(missing_projects_terms)

            def choose_project_target() -> Dict[str, Any]:
                best_entry = project_entries[0]
                best_score = -1.0
                for entry in project_entries:
                    score = 0.0
                    description = str(entry.get("description") or "").strip()
                    technologies = str(entry.get("technologies") or "").strip()
                    if description:
                        score += 2.0
                    if technologies:
                        score += 1.0
                    score += min(2.0, float(len(description)) / 220.0)
                    if score > best_score:
                        best_score = score
                        best_entry = entry
                return best_entry

            for term in project_terms:
                term_norm = normalize_keyword_for_match(term)
                if not term_norm:
                    continue
                if normalized_term_present(current_probe, term_norm):
                    continue

                target = choose_project_target()
                injected = False

                technologies = str(target.get("technologies") or "").strip()
                tech_items = _split_project_technology_items(technologies)
                tech_probe = normalize_keyword_for_match(" ".join(tech_items))
                if not normalized_term_present(tech_probe, term_norm):
                    tech_items = _dedup_preserve([*tech_items, term])[:10]
                    target["technologies"] = ", ".join(tech_items)
                    injected = True

                description = clean_narrative_text(str(target.get("description") or ""))
                description_norm = normalize_keyword_for_match(description)
                if not normalized_term_present(description_norm, term_norm):
                    sentence = (
                        f"Contribution focused on {term}."
                        if is_en
                        else f"Contribution orientee sur {term}."
                    )
                    target["description"] = clean_narrative_text(
                        _trim_text(
                            (
                                f"{description} {sentence}".strip()
                                if description
                                else sentence
                            ),
                            320,
                        )
                    )
                    injected = True

                if injected:
                    added_projects += 1
                    current_probe = project_probe()

            if added_projects:
                logger.info(
                    "Offer adaptation reinforced projects section: added=%s",
                    added_projects,
                )

    # Education remains generation-led. Deterministic keyword injection is
    # intentionally disabled here to avoid synthetic bullets such as
    # "Approfondissement aligne sur ...".

    # Certifications adaptation: keep factual fields unchanged and store extra
    # offer emphasis as render hints.
    certifications_section = cv_json.get("certifications")
    if isinstance(certifications_section, list) and missing_certification_terms:
        certification_entries = [
            item for item in certifications_section if isinstance(item, dict)
        ]
        if certification_entries:

            def cert_probe() -> str:
                parts: List[str] = []
                for entry in certification_entries:
                    for key in ("name", "organization"):
                        value = entry.get(key)
                        if isinstance(value, str) and value.strip():
                            parts.append(value)
                return normalize_keyword_for_match(" ".join(parts))

            current_probe = cert_probe()
            stored_terms: List[str] = []
            cert_terms = _prepare_terms(missing_certification_terms)

            for term in cert_terms:
                term_norm = normalize_keyword_for_match(term)
                if not term_norm:
                    continue
                if normalized_term_present(current_probe, term_norm):
                    continue
                stored_terms.append(term)
                current_probe = normalize_keyword_for_match(
                    f"{current_probe} {term}".strip()
                )

            if stored_terms:
                hint = (
                    f"Certifications emphasis: {', '.join(_dedup_preserve(stored_terms))}."
                    if is_en
                    else f"Certifications a valoriser: {', '.join(_dedup_preserve(stored_terms))}."
                )
                _append_render_hint_note(hint)
                logger.info(
                    "Offer adaptation stored certification emphasis in render_hints: terms=%s",
                    len(stored_terms),
                )

    # Reorder languages by offer relevance when language section is present.
    languages_section = cv_json.get("languages")
    if isinstance(languages_section, list) and languages_section:
        language_entries = [
            item for item in languages_section if isinstance(item, dict)
        ]
        if language_entries:

            def normalize_language_token(value: Any) -> str:
                raw = str(value or "").strip().casefold()
                if not raw:
                    return ""
                folded = (
                    unicodedata.normalize("NFKD", raw)
                    .encode("ascii", "ignore")
                    .decode("ascii")
                )
                compact = re.sub(r"[^a-z]+", "", folded)
                aliases = {
                    "fr": "french",
                    "fra": "french",
                    "french": "french",
                    "francais": "french",
                    "en": "english",
                    "eng": "english",
                    "english": "english",
                    "anglais": "english",
                    "de": "german",
                    "ger": "german",
                    "german": "german",
                    "allemand": "german",
                    "es": "spanish",
                    "spa": "spanish",
                    "spanish": "spanish",
                    "espagnol": "spanish",
                    "it": "italian",
                    "ita": "italian",
                    "italian": "italian",
                    "italien": "italian",
                    "pt": "portuguese",
                    "por": "portuguese",
                    "portuguese": "portuguese",
                    "portugais": "portuguese",
                    "ja": "japanese",
                    "jpn": "japanese",
                    "japanese": "japanese",
                    "japonais": "japanese",
                    "zh": "chinese",
                    "chi": "chinese",
                    "chinese": "chinese",
                    "chinois": "chinese",
                    "mandarin": "chinese",
                }
                return aliases.get(compact, "")

            language_targets: List[str] = []
            for term in [*aligned_terms, *missing_language_terms]:
                token = normalize_language_token(term)
                if token:
                    language_targets.append(token)
            language_targets = _dedup_preserve(language_targets)

            if language_targets:
                ranked_payloads: List[Tuple[int, int, Dict[str, Any]]] = []
                for idx, entry in enumerate(language_entries):
                    language_name = entry.get("language")
                    token = normalize_language_token(language_name)
                    score = 1 if token in language_targets else 0
                    ranked_payloads.append((score, idx, entry))
                if any(score > 0 for score, _, _ in ranked_payloads):
                    ranked_payloads.sort(key=lambda payload: (-payload[0], payload[1]))
                    reordered = [payload[2] for payload in ranked_payloads]
                    if reordered != language_entries:
                        cv_json["languages"] = reordered
                        logger.info(
                            "Offer adaptation reordered languages section by offer relevance."
                        )

    # Guardrail: keep experience/certification entry cardinality stable.
    if initial_experience_count is not None and isinstance(
        cv_json.get("experience"), list
    ):
        cv_json["experience"] = cv_json["experience"][:initial_experience_count]
    if initial_certification_count is not None and isinstance(
        cv_json.get("certifications"), list
    ):
        cv_json["certifications"] = cv_json["certifications"][
            :initial_certification_count
        ]

    # Re-enforce the one-page bullet budget after offer-driven enrichment.
    _enforce_single_page_budget(cv_json)

    return cv_json
