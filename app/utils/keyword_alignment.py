"""Keyword normalization and alignment helpers."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Dict, List, Tuple


JOB_KEYWORD_EQUIVALENTS: Dict[str, Tuple[str, ...]] = {
    "business intelligence": (
        "bi",
        "informatique decisionnelle",
        "reporting",
        "decision intelligence",
    ),
    "data analysis": ("data analytics", "analytics", "analyse de donnees"),
    "data analytics": ("data analysis", "analytics", "analyse de donnees"),
    "machine learning": ("ml", "apprentissage automatique", "predictive modeling"),
    "deep learning": ("apprentissage profond", "neural networks", "reseaux de neurones"),
    "artificial intelligence": ("ai", "ia", "intelligence artificielle"),
    "data visualization": ("dataviz", "visualisation de donnees", "dashboard"),
    "dashboard": ("tableau de bord", "reporting"),
    "etl": ("elt", "data pipeline", "pipeline de donnees", "integration de donnees"),
    "project management": ("gestion de projet", "agile", "scrum", "delivery"),
    "stakeholder management": (
        "gestion des parties prenantes",
        "stakeholder communication",
    ),
    "sql": ("structured query language", "postgresql", "mysql", "t-sql", "pl/sql"),
    "power bi": ("powerbi", "dax", "power query"),
    "excel": ("advanced excel", "vba", "power query"),
    "aws": ("amazon web services", "cloud aws"),
    "azure": ("microsoft azure", "cloud azure"),
    "gcp": ("google cloud", "google cloud platform"),
    "kpi": (
        "key performance indicator",
        "indicateur cle de performance",
        "indicateurs cles",
    ),
    "a/b testing": ("ab testing", "experimentation", "test and learn"),
    "software engineering": ("software development", "developpement logiciel"),
}

_TERM_DELIMITER_PATTERN = re.compile(r"[./-]+")


def normalize_keyword_for_match(text: str) -> str:
    if not text:
        return ""
    value = str(text).strip()
    if not value:
        return ""
    folded = unicodedata.normalize("NFKD", value)
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    lowered = folded.lower()
    cleaned = re.sub(r"[^a-z0-9+.#/ -]+", " ", lowered)
    return " ".join(cleaned.split())


def _canonicalize_term_presence_text(text: str) -> str:
    normalized = normalize_keyword_for_match(text)
    if not normalized:
        return ""
    # Treat punctuation separators as token boundaries so
    # "aws/azure", "aws.azure", and "aws azure" match consistently.
    canonical = _TERM_DELIMITER_PATTERN.sub(" ", normalized)
    return " ".join(canonical.split())


def normalized_term_in_probe(probe: str, term: str) -> bool:
    """Check whether a normalized keyword term is present on token boundaries."""
    probe_text = _canonicalize_term_presence_text(probe)
    term_text = _canonicalize_term_presence_text(term)
    if not probe_text or not term_text:
        return False
    if probe_text == term_text:
        return True
    return f" {term_text} " in f" {probe_text} "


def keyword_tokens(text: str) -> List[str]:
    normalized = normalize_keyword_for_match(text)
    if not normalized:
        return []
    return [token for token in normalized.split() if len(token) > 1]


def acronym_for_text(text: str) -> str:
    normalized = normalize_keyword_for_match(text)
    if not normalized:
        return ""
    parts = re.split(r"[\s/-]+", normalized)
    letters = [part[0] for part in parts if part]
    return "".join(letters)


def is_acronym_match(candidate: str, target: str) -> bool:
    candidate_clean = re.sub(r"[^A-Za-z]", "", candidate or "")
    if not candidate_clean or not (2 <= len(candidate_clean) <= 6):
        return False
    target_acronym = acronym_for_text(target)
    if not target_acronym:
        return False
    return candidate_clean.lower() == target_acronym.lower()


def keyword_similarity(a: str, b: str) -> float:
    norm_a = normalize_keyword_for_match(a)
    norm_b = normalize_keyword_for_match(b)
    if not norm_a or not norm_b:
        return 0.0
    if norm_a == norm_b:
        return 1.0

    score = 0.0
    if norm_a in norm_b or norm_b in norm_a:
        score = 0.9
    else:
        score = SequenceMatcher(None, norm_a, norm_b).ratio()

    tokens_a = keyword_tokens(norm_a)
    tokens_b = keyword_tokens(norm_b)
    if tokens_a and tokens_b:
        overlap = len(set(tokens_a) & set(tokens_b)) / float(min(len(tokens_a), len(tokens_b)))
        score = max(score, overlap)

    if is_acronym_match(a, b) or is_acronym_match(b, a):
        score = max(score, 0.86)

    return score


def build_keyword_alignment(
    candidate_terms: List[str],
    offer_keywords: List[str],
    *,
    max_pairs: int = 12,
    min_score: float = 0.82,
) -> Dict[str, str]:
    if not candidate_terms or not offer_keywords:
        return {}

    seen = set()
    deduped_offer_keywords: List[str] = []
    for raw in offer_keywords or []:
        text = str(raw or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped_offer_keywords.append(text)

    pairs: List[Tuple[str, str, float]] = []
    for candidate in candidate_terms:
        if not isinstance(candidate, str):
            continue
        candidate_text = candidate.strip()
        if len(candidate_text) < 2:
            continue
        best_offer = ""
        best_score = 0.0
        for offer in deduped_offer_keywords:
            score = keyword_similarity(candidate_text, offer)
            if score > best_score:
                best_score = score
                best_offer = offer
        if best_offer and best_score >= float(min_score):
            if candidate_text.lower() != best_offer.strip().lower():
                pairs.append((candidate_text, best_offer, best_score))

    pairs.sort(key=lambda item: (item[2], len(item[0])), reverse=True)
    mapping: Dict[str, str] = {}
    used_offers = set()
    for candidate, offer, _score in pairs:
        offer_key = offer.lower().strip()
        if offer_key in used_offers:
            continue
        mapping[candidate] = offer
        used_offers.add(offer_key)
        if len(mapping) >= int(max_pairs):
            break
    return mapping


def build_term_pattern(term: str) -> re.Pattern:
    escaped = re.escape(term)
    if re.search(r"[^A-Za-z0-9]", term):
        return re.compile(rf"(?i)(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])")
    return re.compile(rf"(?i)\\b{escaped}\\b")


def replace_terms_in_text(text: str, mapping: Dict[str, str]) -> Tuple[str, int]:
    if not isinstance(text, str) or not text or not mapping:
        return text, 0
    updated = text
    total = 0
    for src, dst in sorted(mapping.items(), key=lambda item: len(item[0]), reverse=True):
        if not src or not dst:
            continue
        pattern = build_term_pattern(src)
        updated, count = pattern.subn(dst, updated)
        total += count
    return updated, total


# =============================================================================
# Sprint 8.2: CV Keyword Alignment Application (extracted from CVGenerationWorker)
# =============================================================================

from typing import Any, Callable, Optional, Set


def _dedup_preserve_local(items: List[str]) -> List[str]:
    """Local dedup helper to avoid circular imports."""
    seen: Set[str] = set()
    output: List[str] = []
    for item in items:
        text = str(item).strip() if item else ""
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(text)
    return output


def apply_keyword_alignment_to_cv(
    cv_json: Dict[str, Any],
    *,
    mapping: Dict[str, str],
    offer_keywords: List[str],
    candidate_terms: List[str],
    language_code: str = "fr",
    strip_placeholders_fn: Optional[Callable[[str], str]] = None,
    has_review_markers_fn: Optional[Callable[[str], bool]] = None,
    extract_terms_fn: Optional[Callable[[str, Dict[str, str], List[str]], List[str]]] = None,
) -> int:
    """Apply keyword alignment to a CV JSON structure.

    This function replaces candidate terms with offer-aligned terms throughout
    the CV, ensuring ATS compatibility and offer relevance.

    Args:
        cv_json: CV JSON dictionary (modified in place)
        mapping: Keyword mapping (candidate -> offer term)
        offer_keywords: List of offer keywords
        candidate_terms: List of candidate profile terms
        language_code: Language code for fallback category names
        strip_placeholders_fn: Optional function to strip placeholders from text
        has_review_markers_fn: Optional function to check for review markers
        extract_terms_fn: Optional function to extract terms from problematic text

    Returns:
        Number of replacements made
    """
    if not isinstance(cv_json, dict):
        return 0

    fallback_category = "Skills" if language_code == "en" else "Competences"
    offer_norm = {normalize_keyword_for_match(item) for item in offer_keywords}
    replacements = 0

    # Default implementations for optional callbacks
    def _default_strip(text: str) -> str:
        return text.strip() if text else ""

    def _default_has_markers(text: str) -> bool:
        return False

    def _default_extract(text: str, m: Dict[str, str], c: List[str]) -> List[str]:
        return [text] if text else []

    strip_fn = strip_placeholders_fn or _default_strip
    markers_fn = has_review_markers_fn or _default_has_markers
    extract_fn = extract_terms_fn or _default_extract

    # Handle empty mapping - just add fallback skills
    if not mapping:
        fallback_items = []
        for term in candidate_terms:
            if normalize_keyword_for_match(term) in offer_norm:
                fallback_items.append(term)
        fallback_items = _dedup_preserve_local(fallback_items)
        if fallback_items and not cv_json.get("skills"):
            cv_json["skills"] = [
                {"category": fallback_category, "items": fallback_items[:8]}
            ]
        return 0

    # Replace in summary
    summary = cv_json.get("summary")
    if isinstance(summary, str):
        cv_json["summary"], count = replace_terms_in_text(summary, mapping)
        replacements += count

    # Replace in skills
    skills_present = False
    for category in cv_json.get("skills", []) or []:
        if not isinstance(category, dict):
            continue
        items = category.get("items")
        if isinstance(items, list):
            updated_items: List[str] = []
            for item in items:
                if not isinstance(item, str):
                    updated_items.append(str(item) if item else "")
                    continue
                cleaned = strip_fn(item)
                if not cleaned:
                    continue
                if markers_fn(cleaned) or len(cleaned) > 80:
                    extracted = extract_fn(cleaned, mapping, candidate_terms)
                    updated_items.extend(extracted)
                    continue
                updated, count = replace_terms_in_text(cleaned, mapping)
                replacements += count
                updated_items.append(updated)
            category["items"] = _dedup_preserve_local(
                [item for item in updated_items if isinstance(item, str) and item.strip()]
            )
            if category["items"]:
                skills_present = True

    # Replace in experience
    for entry in cv_json.get("experience", []) or []:
        if not isinstance(entry, dict):
            continue
        entry_title = entry.get("title")
        if isinstance(entry_title, str):
            entry["title"], count = replace_terms_in_text(entry_title, mapping)
            replacements += count
        entry_summary = entry.get("summary")
        if isinstance(entry_summary, str):
            entry["summary"], count = replace_terms_in_text(entry_summary, mapping)
            replacements += count
        highlights = entry.get("highlights")
        if isinstance(highlights, list):
            updated_highlights: List[str] = []
            for highlight in highlights:
                if not isinstance(highlight, str):
                    updated_highlights.append(str(highlight) if highlight else "")
                    continue
                updated, count = replace_terms_in_text(highlight, mapping)
                replacements += count
                updated_highlights.append(updated)
            entry["highlights"] = _dedup_preserve_local(
                [item for item in updated_highlights if isinstance(item, str) and item.strip()]
            )

    # Replace in projects
    for project in cv_json.get("projects", []) or []:
        if not isinstance(project, dict):
            continue
        for key in ("description", "technologies"):
            value = project.get(key)
            if isinstance(value, str) and value.strip():
                project[key], count = replace_terms_in_text(value, mapping)
                replacements += count

    # Replace in education
    for edu in cv_json.get("education", []) or []:
        if not isinstance(edu, dict):
            continue
        field = edu.get("field_of_study")
        if isinstance(field, str) and field.strip():
            edu["field_of_study"], count = replace_terms_in_text(field, mapping)
            replacements += count
        details = edu.get("details")
        if isinstance(details, list):
            updated_details: List[str] = []
            for detail in details:
                if not isinstance(detail, str):
                    updated_details.append(str(detail) if detail else "")
                    continue
                updated, count = replace_terms_in_text(detail, mapping)
                replacements += count
                updated_details.append(updated)
            edu["details"] = _dedup_preserve_local(
                [item for item in updated_details if isinstance(item, str) and item.strip()]
            )

    # Add fallback skills if none present
    if not skills_present:
        fallback_items = _dedup_preserve_local(list(mapping.values()))
        if not fallback_items:
            for term in candidate_terms:
                if normalize_keyword_for_match(term) in offer_norm:
                    fallback_items.append(term)
            fallback_items = _dedup_preserve_local(fallback_items)
        if fallback_items:
            cv_json["skills"] = [
                {"category": fallback_category, "items": fallback_items[:8]}
            ]

    return replacements


def inject_missing_keywords_to_experience(
    cv_json: Dict[str, Any],
    *,
    mapped_terms: List[str],
    present_terms: Set[str],
    language_code: str = "fr",
) -> None:
    """Inject missing keywords into experience highlights.

    Args:
        cv_json: CV JSON dictionary (modified in place)
        mapped_terms: List of mapped keyword terms
        present_terms: Set of terms already present (normalized)
        language_code: Language for keyword line text
    """
    if not isinstance(cv_json, dict):
        return

    missing_terms = [
        term
        for term in mapped_terms
        if normalize_keyword_for_match(term) not in present_terms
    ]
    if not missing_terms:
        return

    experience_entries = [
        item for item in (cv_json.get("experience", []) or []) if isinstance(item, dict)
    ]
    if not experience_entries:
        return

    cursor = 0
    for entry in experience_entries:
        if cursor >= len(missing_terms):
            break
        chunk = missing_terms[cursor : cursor + 2]
        cursor += len(chunk)
        if not chunk:
            continue
        line = (
            f"Keywords aligned with target role: {', '.join(chunk)}."
            if language_code == "en"
            else f"Mots-cles alignes avec le poste cible: {', '.join(chunk)}."
        )
        highlights = entry.get("highlights")
        if not isinstance(highlights, list):
            highlights = []
        highlights.append(line)
        entry["highlights"] = _dedup_preserve_local(
            [item for item in highlights if isinstance(item, str) and item.strip()]
        )


# =============================================================================
# Sprint 8.4: Required Offer Keywords Enforcement (extracted from CVGenerationWorker)
# =============================================================================


def enforce_required_offer_keywords(
    cv_json: Dict[str, Any],
    *,
    missing_terms: List[str],
    language_code: str = "fr",
) -> None:
    """Enforce required offer keywords in CV sections.

    Distributes missing required keywords across:
    1. Summary (anchor terms, max 3)
    2. Skills first block (remaining terms)
    3. Experience highlights (overflow terms)

    Args:
        cv_json: CV JSON dictionary (modified in place)
        missing_terms: List of terms that need to be added
        language_code: Language code for generated text
    """
    if not isinstance(cv_json, dict) or not missing_terms:
        return

    is_en = language_code == "en"
    remaining = list(missing_terms)

    # Add anchor terms to summary
    summary = str(cv_json.get("summary") or "").strip()
    if summary and remaining:
        anchor_terms = remaining[:3]
        if anchor_terms:
            anchor = (
                f"Focus areas for this target role: {', '.join(anchor_terms)}."
                if is_en
                else f"Axes prioritaires pour le poste cible: {', '.join(anchor_terms)}."
            )
            cv_json["summary"] = f"{summary} {anchor}".strip()
            remaining = remaining[len(anchor_terms):]

    # Add remaining terms to skills first block
    skills = cv_json.get("skills")
    if not isinstance(skills, list):
        skills = []
        cv_json["skills"] = skills
    if not skills:
        skills.append({
            "category": "Skills" if is_en else "Competences",
            "items": [],
        })

    first_block = skills[0] if isinstance(skills[0], dict) else {
        "category": "Skills" if is_en else "Competences",
        "items": []
    }
    items = first_block.get("items")
    if not isinstance(items, list):
        items = []

    existing_norm = {normalize_keyword_for_match(item) for item in items if isinstance(item, str)}
    for term in list(remaining):
        norm = normalize_keyword_for_match(term)
        if norm and norm not in existing_norm:
            items.append(term)
            existing_norm.add(norm)
            remaining.remove(term)
        if len(items) >= 12 or not remaining:
            break

    first_block["items"] = _dedup_preserve_local(
        [item for item in items if isinstance(item, str) and item.strip()]
    )[:12]
    skills[0] = first_block

    # Add overflow to experience highlights
    experience_entries = [
        entry for entry in (cv_json.get("experience") or []) if isinstance(entry, dict)
    ]
    if experience_entries and remaining:
        cursor = 0
        for entry in experience_entries:
            if cursor >= len(remaining):
                break
            chunk = remaining[cursor : cursor + 2]
            cursor += len(chunk)
            if not chunk:
                continue
            line = (
                f"Offer-focused contributions: {', '.join(chunk)}."
                if is_en
                else f"Contributions alignees offre: {', '.join(chunk)}."
            )
            highlights = entry.get("highlights")
            if not isinstance(highlights, list):
                highlights = []
            highlights.append(line)
            entry["highlights"] = _dedup_preserve_local(
                [item for item in highlights if isinstance(item, str) and item.strip()]
            )[:5]
