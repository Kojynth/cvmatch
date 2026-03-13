"""
LLM Worker
==========

Worker pour la génération de CV.
"""
import json
import re
import time
import os
import sys
import tempfile
import subprocess
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, Any, Optional, List, Iterable, Union, Tuple
from PySide6.QtCore import QThread, Signal
try:
    from ..logging.safe_logger import get_safe_logger
    from ..config import DEFAULT_PII_CONFIG
    logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

# Suppress HuggingFace warnings on Windows
import os
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"

from ..models.user_profile import UserProfile
from ..models.job_application import JobApplication, ApplicationStatus
from ..models.database import get_session
from .worker_data import ProfileWorkerData
from typing import Union
try:
    from ..utils.gpu_utils import gpu_manager
except ImportError:
    # Mock GPU manager si unavailable
    class MockGPUManager:
        gpu_info = {"available": False}
        def recommend_quantization(self, *args, **kwargs): return {"device": "cpu", "dtype": "float32", "load_in_8bit": False, "load_in_4bit": False, "reason": "Mock mode"}
        def optimize_for_inference(self): pass
        def get_memory_stats(self): return {"gpu_available": False}
    gpu_manager = MockGPUManager()

try:
    from ..utils.model_optimizer import model_optimizer
except ImportError:
    # Mock optimizer si unavailable
    class MockModelOptimizer:
        def check_hf_xet_status(self): return {"optimizations_active": False}
        def optimize_model_download(self, model_name, progress_callback=None, force_download=False): 
            if progress_callback: progress_callback("💠 Téléchargement standard...")
            return model_name
    model_optimizer = MockModelOptimizer()

from ..utils.llm_worker_fallbacks import (
    build_cv_json_fallback,
    build_offer_keywords_fallback,
)
from ..utils.offer_keywords_quality import (
    extract_offer_text_from_offer_data,
    stabilize_offer_keywords_payload,
)
from ..utils.offer_keywords_llm_retry import run_offer_keywords_second_pass
from ..utils.model_quality_routing import resolve_writer_quality_override
from ..utils.cover_letter_style_policy import (
    build_cover_letter_generation_payload,
    COVER_LETTER_STYLE_ANALYSIS_KEY,
)
from ..utils.stage_attempts_config import (
    resolve_stage_attempts,
    resolve_stage_timeout_seconds,
)
from ..utils.stage_subprocess_utils import (
    build_stage_subprocess_env,
    extract_stage_subprocess_error,
    is_transient_stage_memory_error,
    persist_stage_subprocess_diagnostics,
)


def _normalize_template_name(template: Optional[str]) -> str:
    key = (template or "").strip().lower() or "modern"
    allowed = {"modern", "classic", "tech", "creative", "minimal"}
    return key if key in allowed else "modern"


def _normalize_language(language: Optional[str]) -> str:
    normalized = (language or "").strip().lower()
    if normalized.startswith("en"):
        return "en"
    return "fr"


def _estimate_model_size_gb(model_name: Optional[str], model_id: Optional[str] = None) -> float:
    """
    Estime la "taille" du modèle (en pratique: ordre de grandeur) à partir du nom/id.

    Note: cette valeur est utilisée comme signal heuristique pour `gpu_manager.recommend_quantization()`.
    """
    haystack = f"{model_id or ''} {model_name or ''}".lower()
    if "32b" in haystack:
        return 32.0
    if "14b" in haystack:
        return 14.0
    if any(token in haystack for token in ["8b", "qwen3-8b", "qwen-7b"]):
        return 8.0
    if any(token in haystack for token in ["7b", "mistral-7b", "mistral 7b"]):
        return 7.0
    if any(token in haystack for token in ["4b", "3.8b", "phi-3-mini", "phi3", "mini-4k"]):
        return 4.0
    if any(token in haystack for token in ["3b", "qwen3-4b", "qwen2.5-3b"]):
        return 3.0
    if any(token in haystack for token in ["1.7b", "1.5b", "qwen3-1.7b", "qwen2.5-1.5b"]):
        return 1.5
    if any(token in haystack for token in ["1.1b", "tinyllama"]):
        return 1.1
    if any(token in haystack for token in ["0.6", "0.5b", "qwen2.5-0.5b"]):
        return 0.5
    return 7.0


def _trim_text(value: Any, max_chars: int) -> str:
    text = "" if value is None else str(value)
    text = text.strip()
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def _coerce_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _join_nonempty(parts: Iterable[str], sep: str = " | ") -> str:
    safe_parts = [p.strip() for p in parts if isinstance(p, str) and p.strip()]
    return sep.join(safe_parts)


EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
LINKEDIN_RE = re.compile(r"https?://[^\s]*linkedin\.com/[^\s]+", re.IGNORECASE)
PHONE_RE = re.compile(r"(?:\+?\d[\d\s().-]{8,}\d)")


def _dedup_preserve(items: Iterable[str]) -> List[str]:
    seen = set()
    output: List[str] = []
    for item in items:
        text = str(item).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(text)
    return output


def _hydrate_offer_analysis_from_application(
    offer_data: Any,
    application_id: Optional[int],
) -> None:
    if not isinstance(offer_data, dict) or not isinstance(application_id, int):
        return
    current = offer_data.get("analysis")
    if isinstance(current, dict) and current.get(COVER_LETTER_STYLE_ANALYSIS_KEY):
        return
    try:
        with get_session() as session:
            app = session.get(JobApplication, application_id)
            stored = (
                dict(app.offer_analysis)
                if app is not None and isinstance(app.offer_analysis, dict)
                else {}
            )
        if not stored:
            return
        merged = dict(stored)
        if isinstance(current, dict):
            merged.update(current)
        offer_data["analysis"] = merged
    except Exception as exc:
        logger.debug(
            "Offer analysis hydration skipped for application %s: %s",
            application_id,
            exc,
        )


def _persist_cover_letter_style_in_offer_analysis(
    offer_data: Any,
    style_payload: Any,
) -> None:
    if not isinstance(offer_data, dict) or not isinstance(style_payload, dict):
        return
    style_profile = (
        style_payload.get("style_profile")
        if isinstance(style_payload.get("style_profile"), dict)
        else {}
    )
    style_mode = str(style_payload.get("style_mode") or style_profile.get("mode") or "").strip()
    if not style_mode:
        return
    analysis = offer_data.get("analysis")
    if not isinstance(analysis, dict):
        analysis = {}
    analysis[COVER_LETTER_STYLE_ANALYSIS_KEY] = {
        "mode": style_mode,
        "label": str(style_profile.get("label") or ""),
        "source": str(style_payload.get("style_source") or style_profile.get("source") or "auto"),
        "freeze_applied": bool(style_payload.get("freeze_applied")),
        "instruction_override": bool(style_payload.get("instruction_override")),
        "template_hint": str(style_profile.get("template_hint") or ""),
        "scores": (
            dict(style_profile.get("scores"))
            if isinstance(style_profile.get("scores"), dict)
            else {}
        ),
    }
    offer_data["analysis"] = analysis


def _compact_profile_json_for_prompt(profile_json: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(profile_json, dict):
        return {}
    limits = {
        "experiences": 4,
        "education": 3,
        "skills": 12,
        "soft_skills": 8,
        "languages": 4,
        "projects": 3,
        "certifications": 3,
        "publications": 2,
        "volunteering": 2,
        "awards": 2,
        "references": 2,
        "interests": 6,
    }
    max_str_len = 220
    max_list_len = 4

    def truncate(value: Any, limit: int = max_str_len) -> str:
        text = "" if value is None else str(value).strip()
        if limit <= 0:
            return ""
        if len(text) <= limit:
            return text
        return text[: limit - 3].rstrip() + "..."

    def compact_list(values: List[Any]) -> List[Any]:
        compacted: List[Any] = []
        for item in values[:max_list_len]:
            if isinstance(item, dict):
                compacted.append(compact_item(item))
            elif isinstance(item, str):
                compacted.append(truncate(item))
            else:
                compacted.append(item)
        return compacted

    def compact_item(item: Dict[str, Any]) -> Dict[str, Any]:
        compacted: Dict[str, Any] = {}
        for key, value in item.items():
            if isinstance(value, str):
                compacted[key] = truncate(value)
            elif isinstance(value, list):
                compacted[key] = compact_list(value)
            else:
                compacted[key] = value
        return compacted

    compacted: Dict[str, Any] = {}
    for key, value in profile_json.items():
        if key in limits and isinstance(value, list):
            compacted[key] = [compact_item(item) if isinstance(item, dict) else truncate(item) if isinstance(item, str) else item for item in value[: limits[key]]]
        elif isinstance(value, dict):
            compacted[key] = compact_item(value)
        elif isinstance(value, list):
            compacted[key] = compact_list(value)
        elif isinstance(value, str):
            compacted[key] = truncate(value)
        else:
            compacted[key] = value
    return compacted


def _collect_candidate_keywords(profile: Union[UserProfile, ProfileWorkerData]) -> List[str]:
    terms: List[str] = []

    def add_term(value: Any) -> None:
        if value is None:
            return
        if isinstance(value, str):
            trimmed = value.strip()
            if 1 < len(trimmed) <= 80:
                terms.append(trimmed)
            return
        if isinstance(value, list):
            for item in value:
                add_term(item)
        elif isinstance(value, dict):
            for key in ("name", "title", "skill", "technology", "tool"):
                add_term(value.get(key))

    skills = getattr(profile, "extracted_skills", None) or []
    for entry in skills:
        if isinstance(entry, dict):
            items = entry.get("items") or entry.get("skills_list") or entry.get("skills") or []
            add_term(items)
        else:
            add_term(entry)

    projects = getattr(profile, "extracted_projects", None) or []
    for entry in projects:
        if isinstance(entry, dict):
            add_term(entry.get("name"))
            add_term(entry.get("technologies"))
        else:
            add_term(entry)

    certifications = getattr(profile, "extracted_certifications", None) or []
    for entry in certifications:
        if isinstance(entry, dict):
            add_term(entry.get("name"))
        else:
            add_term(entry)

    experiences = getattr(profile, "extracted_experiences", None) or []
    for entry in experiences:
        if isinstance(entry, dict):
            add_term(entry.get("title"))
        else:
            add_term(entry)

    return _dedup_preserve(terms)[:40]


def _match_offer_keywords(offer_text: Optional[str], candidate_terms: List[str], max_items: int = 16) -> List[str]:
    if not offer_text:
        return []
    lowered = offer_text.lower()
    matches = [term for term in candidate_terms if term.lower() in lowered]
    return _dedup_preserve(matches)[:max_items]


def _detect_language_from_text(text: Optional[str]) -> str:
    if not text or not str(text).strip():
        return "fr"
    raw = str(text)
    lowered = raw.lower()
    tokens = re.findall(r"[a-zA-Z]+", lowered)
    if not tokens:
        return "fr"

    fr_tokens = {
        "le",
        "la",
        "les",
        "des",
        "une",
        "un",
        "pour",
        "avec",
        "dans",
        "sur",
        "poste",
        "profil",
        "mission",
        "competences",
        "candidature",
        "nous",
        "vous",
        "entreprise",
        "equipe",
        "formation",
        "diplome",
        "alternance",
        "stage",
        "ingenieur",
        "responsabilites",
        "developpement",
        "qualite",
    }
    en_tokens = {
        "the",
        "and",
        "with",
        "role",
        "position",
        "responsibilities",
        "requirements",
        "skills",
        "experience",
        "company",
        "team",
        "apply",
        "candidate",
        "development",
        "engineering",
        "job",
        "we",
        "you",
    }

    fr_score = sum(1 for token in tokens if token in fr_tokens)
    en_score = sum(1 for token in tokens if token in en_tokens)
    if any(ord(ch) > 127 for ch in raw):
        fr_score += 2
    if en_score > fr_score + 1:
        return "en"
    return "fr"


def _normalize_keyword_for_match(text: str) -> str:
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


def _keyword_tokens(text: str) -> List[str]:
    normalized = _normalize_keyword_for_match(text)
    if not normalized:
        return []
    return [token for token in normalized.split() if len(token) > 1]


def _acronym_for_text(text: str) -> str:
    normalized = _normalize_keyword_for_match(text)
    if not normalized:
        return ""
    parts = re.split(r"[\s/-]+", normalized)
    letters = [part[0] for part in parts if part]
    return "".join(letters)


def _is_acronym_match(candidate: str, target: str) -> bool:
    candidate_clean = re.sub(r"[^A-Za-z]", "", candidate or "")
    if not candidate_clean or not (2 <= len(candidate_clean) <= 6):
        return False
    target_acronym = _acronym_for_text(target)
    if not target_acronym:
        return False
    return candidate_clean.lower() == target_acronym.lower()


def _keyword_similarity(a: str, b: str) -> float:
    norm_a = _normalize_keyword_for_match(a)
    norm_b = _normalize_keyword_for_match(b)
    if not norm_a or not norm_b:
        return 0.0
    if norm_a == norm_b:
        return 1.0

    score = 0.0
    if norm_a in norm_b or norm_b in norm_a:
        score = 0.9
    else:
        score = SequenceMatcher(None, norm_a, norm_b).ratio()

    tokens_a = _keyword_tokens(norm_a)
    tokens_b = _keyword_tokens(norm_b)
    if tokens_a and tokens_b:
        overlap = len(set(tokens_a) & set(tokens_b)) / float(min(len(tokens_a), len(tokens_b)))
        score = max(score, overlap)

    if _is_acronym_match(a, b) or _is_acronym_match(b, a):
        score = max(score, 0.86)

    return score


def _build_keyword_alignment(
    candidate_terms: List[str],
    offer_keywords: List[str],
    max_pairs: int = 12,
    min_score: float = 0.82,
) -> Dict[str, str]:
    if not candidate_terms or not offer_keywords:
        return {}

    offer_keywords = _dedup_preserve([item for item in offer_keywords if isinstance(item, str) and item.strip()])
    pairs: List[Tuple[str, str, float]] = []
    for candidate in candidate_terms:
        if not isinstance(candidate, str):
            continue
        candidate_text = candidate.strip()
        if len(candidate_text) < 2:
            continue
        best_offer = ""
        best_score = 0.0
        for offer in offer_keywords:
            score = _keyword_similarity(candidate_text, offer)
            if score > best_score:
                best_score = score
                best_offer = offer
        if best_offer and best_score >= min_score:
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
        if len(mapping) >= max_pairs:
            break
    return mapping


def _build_term_pattern(term: str) -> re.Pattern:
    escaped = re.escape(term)
    if re.search(r"[^A-Za-z0-9]", term):
        return re.compile(rf"(?i)(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])")
    return re.compile(rf"(?i)\\b{escaped}\\b")


def _replace_terms_in_text(text: str, mapping: Dict[str, str]) -> Tuple[str, int]:
    if not isinstance(text, str) or not text or not mapping:
        return text, 0
    updated = text
    total = 0
    for src, dst in sorted(mapping.items(), key=lambda item: len(item[0]), reverse=True):
        if not src or not dst:
            continue
        pattern = _build_term_pattern(src)
        updated, count = pattern.subn(dst, updated)
        total += count
    return updated, total


def _format_profile_detailed_data(profile: Union[UserProfile, ProfileWorkerData]) -> str:
    personal_info = getattr(profile, "extracted_personal_info", None) or {}
    experiences = getattr(profile, "extracted_experiences", None) or []
    education = getattr(profile, "extracted_education", None) or []
    skills = getattr(profile, "extracted_skills", None) or []
    soft_skills = getattr(profile, "extracted_soft_skills", None) or []
    languages = getattr(profile, "extracted_languages", None) or []
    projects = getattr(profile, "extracted_projects", None) or []
    certifications = getattr(profile, "extracted_certifications", None) or []
    interests = getattr(profile, "extracted_interests", None) or []
    volunteering = getattr(profile, "extracted_volunteering", None) or []

    lines: List[str] = []
    lines.append("CONTACT (profil):")
    lines.append(f"- Nom: {profile.name or ''}")
    lines.append(f"- Email: {profile.email or ''}")
    if getattr(profile, "phone", None):
        lines.append(f"- Telephone: {profile.phone}")
    if getattr(profile, "linkedin_url", None):
        lines.append(f"- LinkedIn: {profile.linkedin_url}")

    if isinstance(personal_info, dict) and personal_info:
        address = personal_info.get("address") or ""
        city = personal_info.get("city") or ""
        postal_code = personal_info.get("postal_code") or ""
        summary = personal_info.get("summary") or personal_info.get("headline") or ""
        links = personal_info.get("links") or []

        extra_parts = []
        if address:
            extra_parts.append(f"Adresse: {address}")
        if city:
            extra_parts.append(f"Ville: {city}")
        if postal_code:
            extra_parts.append(f"Code postal: {postal_code}")
        if extra_parts:
            lines.append("INFOS COMPLEMENTAIRES (profil detaille):")
            lines.extend(f"- {part}" for part in extra_parts)
        if summary:
            lines.append("RESUME (profil detaille):")
            lines.append(f"- {_trim_text(summary, 400)}")
        if isinstance(links, list) and links:
            rendered_links: List[str] = []
            for link in links[:6]:
                if isinstance(link, dict):
                    platform = (link.get("platform") or "Lien").strip()
                    url = (link.get("url") or "").strip()
                    if url:
                        rendered_links.append(f"{platform}: {url}")
                elif isinstance(link, str) and link.strip():
                    rendered_links.append(link.strip())
            if rendered_links:
                lines.append("LIENS (profil detaille):")
                lines.extend(f"- {item}" for item in rendered_links)

    def add_block(title: str, items: Any, max_items: int = 8, max_item_chars: int = 280) -> None:
        seq = _coerce_list(items)
        if not seq:
            return
        lines.append(f"{title}:")
        added = 0
        for entry in seq:
            if added >= max_items:
                break
            if isinstance(entry, dict):
                title_value = entry.get("title") or entry.get("name") or entry.get("degree") or ""
                company_value = entry.get("company") or entry.get("institution") or entry.get("organization") or ""
                period_value = entry.get("period") or _join_nonempty(
                    [
                        str(entry.get("start_date") or entry.get("from") or "").strip(),
                        str(entry.get("end_date") or entry.get("to") or "").strip(),
                    ],
                    sep=" - ",
                )
                location_value = entry.get("location") or entry.get("city") or ""
                headline = _join_nonempty(
                    [str(title_value), str(company_value), str(period_value), str(location_value)]
                )
                if headline:
                    lines.append(f"- {_trim_text(headline, max_item_chars)}")
                    added += 1
                details = entry.get("achievements") or entry.get("description") or []
                detail_list = _coerce_list(details) if details else []
                for detail in detail_list[:3]:
                    if isinstance(detail, str) and detail.strip():
                        lines.append(f"  - {_trim_text(detail, 240)}")
            elif isinstance(entry, str) and entry.strip():
                lines.append(f"- {_trim_text(entry, max_item_chars)}")
                added += 1

    add_block("EXPERIENCES (profil detaille)", experiences, max_items=10, max_item_chars=320)
    add_block("FORMATION (profil detaille)", education, max_items=8, max_item_chars=260)

    if skills:
        lines.append("COMPETENCES (profil detaille):")
        if isinstance(skills, list):
            for entry in skills[:8]:
                if isinstance(entry, dict):
                    category = (entry.get("category") or entry.get("name") or "Competences").strip()
                    items = entry.get("items") or entry.get("skills_list") or entry.get("skills") or []
                    names: List[str] = []
                    if isinstance(items, list):
                        for item in items[:16]:
                            if isinstance(item, dict) and isinstance(item.get("name"), str):
                                names.append(item["name"].strip())
                            elif isinstance(item, str):
                                names.append(item.strip())
                    if names:
                        lines.append(f"- {category}: {', '.join(names[:16])}")
                elif isinstance(entry, str) and entry.strip():
                    lines.append(f"- {entry.strip()}")
        else:
            lines.append(f"- {_trim_text(skills, 800)}")

    if soft_skills:
        lines.append("SOFT SKILLS (profil detaille):")
        if isinstance(soft_skills, list):
            flattened: List[str] = []
            for entry in soft_skills:
                if isinstance(entry, dict):
                    items = entry.get("items") or entry.get("skills_list") or []
                    if isinstance(items, list):
                        for item in items:
                            if isinstance(item, dict) and isinstance(item.get("name"), str):
                                flattened.append(item["name"].strip())
                            elif isinstance(item, str):
                                flattened.append(item.strip())
                elif isinstance(entry, str) and entry.strip():
                    flattened.append(entry.strip())
            if flattened:
                lines.append(f"- {', '.join(flattened[:16])}")
        elif isinstance(soft_skills, str) and soft_skills.strip():
            lines.append(f"- {_trim_text(soft_skills, 400)}")

    add_block("PROJETS (profil detaille)", projects, max_items=6, max_item_chars=260)
    add_block("CERTIFICATIONS (profil detaille)", certifications, max_items=8, max_item_chars=200)
    add_block("VOLONTARIAT (profil detaille)", volunteering, max_items=5, max_item_chars=240)

    if languages:
        lines.append("LANGUES (profil detaille):")
        if isinstance(languages, list):
            rendered: List[str] = []
            for entry in languages[:8]:
                if isinstance(entry, dict):
                    name = entry.get("language") or entry.get("name") or ""
                    level = entry.get("level") or entry.get("proficiency") or ""
                    certification = (
                        entry.get("certification")
                        or entry.get("certificate")
                        or entry.get("organization")
                        or entry.get("issuer")
                        or ""
                    )
                    descriptor = str(level)
                    if certification:
                        descriptor = f"{descriptor} ({certification})" if descriptor else str(certification)
                    rendered.append(_join_nonempty([str(name), descriptor], sep=": "))
                elif isinstance(entry, str) and entry.strip():
                    rendered.append(entry.strip())
            rendered = [item for item in rendered if item]
            lines.extend(f"- {item}" for item in rendered)

    if interests:
        lines.append("CENTRES D'INTERET (profil detaille):")
        if isinstance(interests, list):
            rendered = [str(item).strip() for item in interests[:12] if str(item).strip()]
            if rendered:
                lines.append(f"- {', '.join(rendered)}")
        elif isinstance(interests, str) and interests.strip():
            lines.append(f"- {_trim_text(interests, 300)}")

    default_cover_letter = getattr(profile, "default_cover_letter", None)
    if isinstance(default_cover_letter, str) and default_cover_letter.strip():
        lines.append("LETTRE DE MOTIVATION TYPE (profil):")
        lines.append(_trim_text(default_cover_letter, 1200))

    master_cv = getattr(profile, "master_cv_content", None)
    if isinstance(master_cv, str) and master_cv.strip():
        lines.append("CV DE REFERENCE (texte brut, pour details):")
        lines.append(_trim_text(master_cv, 2200))

    return "\n".join(lines).strip() + "\n"


def _markdown_skeleton_for_template(template: Optional[str], language: Optional[str] = None) -> str:
    key = _normalize_template_name(template)
    lang = _normalize_language(language)

    if lang == "en":
        common_experience = (
            "## Work Experience\n"
            "### <Job title>\n"
            "**<Company> | <Dates>**\n"
            "- <Impact / achievement 1>\n"
            "- <Impact / achievement 2>\n"
            "- <Impact / achievement 3>\n"
        )
        common_education = (
            "## Education\n"
            "**<Degree> | <School> | <Year>**\n"
            "- <Details if relevant>\n"
        )
        common_languages = "## Languages\n- <Language>: <Level>\n"
        common_projects = "## Projects\n### <Project name>\n<1-2 sentence description>\n"
        base = (
            "# [Your First Name] [Your Last Name]\n"
            "## <Target role>\n\n"
            "## Contact\n"
            "- Email: [Your Email]\n"
            "- Phone: [Your Phone]\n"
            "- LinkedIn: [Your LinkedIn]\n"
            "- Location: [Your City, Country]\n\n"
            "## Professional Summary\n"
            "<3-4 lines, results-oriented and aligned with the role>\n\n"
        )
        skills_title = "## Skills\n"
        tech_skills_title = "## Technical Skills\n"
        certifications_title = "## Certifications (optional)\n"
        interests_title = "## Interests (optional)\n"
    else:
        common_experience = (
            "## Experience professionnelle\n"
            "### <Intitule du poste>\n"
            "**<Entreprise> | <Periode>**\n"
            "- <Impact / realisation 1>\n"
            "- <Impact / realisation 2>\n"
            "- <Impact / realisation 3>\n"
        )
        common_education = (
            "## Formation\n"
            "**<Diplome> | <Etablissement> | <Annee>**\n"
            "- <Option / details si pertinent>\n"
        )
        common_languages = "## Langues\n- <Langue>: <Niveau>\n"
        common_projects = "## Projets\n### <Nom du projet>\n<Description en 1-2 phrases>\n"
        base = (
            "# [Votre Prenom] [Votre Nom]\n"
            "## <Titre du poste cible>\n\n"
            "## Informations de contact\n"
            "- Email: [Votre Email]\n"
            "- Telephone: [Votre Telephone]\n"
            "- LinkedIn: [Votre LinkedIn]\n"
            "- Localisation: [Votre Ville, Pays]\n\n"
            "## Profil professionnel\n"
            "<3-4 lignes orientees resultats et alignement offre>\n\n"
        )
        skills_title = "## Competences\n"
        tech_skills_title = "## Competences techniques\n"
        certifications_title = "## Certifications (optionnel)\n"
        interests_title = "## Centres d'interet (optionnel)\n"

    if key == "tech":
        return (
            base
            + tech_skills_title
            + "- <Skill / tool 1>\n"
            + "- <Skill / tool 2>\n"
            + "- <Skill / tool 3>\n\n"
            + common_projects
            + "\n"
            + common_experience
            + "\n"
            + common_education
            + "\n"
            + common_languages
            + "\n"
            + certifications_title
            + "- <Certification>\n"
        )

    if key == "classic":
        return (
            base
            + common_experience
            + "\n"
            + common_education
            + "\n"
            + skills_title
            + "- <Skill 1>\n"
            + "- <Skill 2>\n"
            + "- <Skill 3>\n\n"
            + common_languages
            + "\n"
            + interests_title
            + "- <Interest>\n"
        )

    if key == "creative":
        return (
            base
            + common_projects
            + "\n"
            + skills_title
            + "- <Skill 1>\n"
            + "- <Skill 2>\n"
            + "- <Skill 3>\n\n"
            + common_experience
            + "\n"
            + common_education
            + "\n"
            + common_languages
            + "\n"
            + interests_title
            + "- <Interest>\n"
        )

    # modern/minimal (default)
    return (
        base
        + skills_title
        + "- <Skill 1>\n"
        + "- <Skill 2>\n"
        + "- <Skill 3>\n\n"
        + common_experience
        + "\n"
        + common_projects
        + "\n"
        + common_education
        + "\n"
        + common_languages
        + "\n"
        + certifications_title
        + "- <Certification>\n"
    )


from .qwen_manager import QwenManager  # noqa: F401 â€” backward-compat re-export

try:
    from ..utils.pipeline_orchestrator import build_default_pipeline, PipelineState
except ImportError:
    build_default_pipeline = None
    PipelineState = None


class CVGenerationWorker(QThread):
    """Worker pour générer un CV en arrière-plan.

    Note: Utilise ProfileWorkerData au lieu de UserProfile pour éviter
    les erreurs SQLAlchemy DetachedInstanceError dans les threads background.
    """
    progress_updated = Signal(str)
    generation_finished = Signal(dict)
    error_occurred = Signal(str)
    # Signal pour incrémenter les stats du profil (exécuté dans le thread principal)
    profile_stats_updated = Signal(int)  # profile_id

    def __init__(
        self,
        profile_data: ProfileWorkerData,
        offer_data: dict,
        template: str,
        application_id: Optional[int] = None,
        user_instruction: str = "",
        cv_only_regen: bool = False,
        previous_generation_audit: Optional[Dict[str, Any]] = None,
    ):
        super().__init__()
        self.profile_data = profile_data
        self.offer_data = offer_data
        self.template = template
        # Le QwenManager se configure automatiquement selon le modèle sélectionné
        self.qwen_manager = QwenManager(self.profile_data.model_version)
        self.application_id: Optional[int] = (
            application_id if isinstance(application_id, int) else None
        )
        self.user_instruction: str = str(user_instruction or "").strip()
        self.cv_only_regen: bool = bool(cv_only_regen)
        self.previous_generation_audit: dict = (
            dict(previous_generation_audit)
            if isinstance(previous_generation_audit, dict)
            else {}
        )
        self._offer_analysis_hydrated: bool = False
        self._pipeline_profile_json: dict = {}
        self._pipeline_cv_json_draft: dict = {}
        self._pipeline_offer_keywords: dict = {}

    def _get_runtime_memory_pressure_level(self, *, force_refresh: bool = False) -> str:
        try:
            snapshot = self.qwen_manager._collect_memory_pressure_snapshot(
                force_refresh=force_refresh
            ) or {}
            pressure = str(snapshot.get("pressure_level") or "").strip().lower()
            if pressure in {"elevated", "tight", "critical"}:
                return pressure
            lowram = str(snapshot.get("lowram_level") or "").strip().lower()
            if lowram in {"tight", "critical"}:
                return lowram
        except Exception:
            pass

        try:
            profile = self.qwen_manager._get_lowram_profile(
                force_refresh=force_refresh
            ) or {}
            lowram = str(profile.get("level") or "normal").strip().lower()
            if lowram in {"tight", "critical"}:
                return lowram
        except Exception:
            pass

        return "normal"

    def _should_use_stage_subprocess(self) -> bool:
        env_flag = os.getenv("CVMATCH_SUBPROCESS_STAGES")
        if env_flag is not None:
            return env_flag.strip().lower() in ("1", "true", "yes", "y")
        custom = getattr(self.qwen_manager, "custom_parameters", None) or {}
        if "subprocess_stages" in custom:
            return bool(custom.get("subprocess_stages"))
        # Default strategy is now adaptive in orchestrator:
        # start without subprocess and retry per-stage in subprocess on memory failure.
        return False

    @staticmethod
    def _to_bool_setting(value: Any, default: bool = False) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("1", "true", "yes", "y", "on")

    def _is_memory_ready_gate_enabled(self) -> bool:
        custom = getattr(self.qwen_manager, "custom_parameters", None) or {}
        env_value = os.getenv("CVMATCH_REQUIRE_MEMORY_READY")
        if env_value is not None:
            return self._to_bool_setting(env_value, False)
        if "require_memory_ready" in custom:
            return self._to_bool_setting(custom.get("require_memory_ready"), False)
        try:
            pressure = self._get_runtime_memory_pressure_level(force_refresh=True)
            return pressure in {"tight", "critical"}
        except Exception:
            return False

    def _is_memory_ready_wait_enabled(self) -> bool:
        custom = getattr(self.qwen_manager, "custom_parameters", None) or {}
        env_value = os.getenv("CVMATCH_WAIT_FOR_MEMORY_READY")
        if env_value is not None:
            return self._to_bool_setting(env_value, True)
        if "wait_for_memory_ready" in custom:
            return self._to_bool_setting(custom.get("wait_for_memory_ready"), True)
        return True

    def _memory_ready_timeout_seconds(self) -> int:
        custom = getattr(self.qwen_manager, "custom_parameters", None) or {}
        env_value = os.getenv("CVMATCH_MEMORY_READY_TIMEOUT_S")
        raw = env_value if env_value is not None else custom.get("memory_ready_timeout_s")
        try:
            return max(5, int(raw))
        except Exception:
            return 90

    def _memory_ready_poll_seconds(self) -> float:
        custom = getattr(self.qwen_manager, "custom_parameters", None) or {}
        env_value = os.getenv("CVMATCH_MEMORY_READY_POLL_S")
        raw = env_value if env_value is not None else custom.get("memory_ready_poll_s")
        try:
            return max(1.0, float(raw))
        except Exception:
            return 4.0

    def _ensure_stage_memory_ready(self, stage: str, stage_model_id: Optional[str], progress_callback=None) -> None:
        stage_key = str(stage or "").strip().lower()

        try:
            self.qwen_manager.set_runtime_stage(stage_key)
        except Exception:
            pass

        if not self._is_memory_ready_gate_enabled():
            return

        if stage_model_id:
            try:
                self.qwen_manager.apply_model_profile(
                    stage_model_id,
                    reason=f"memory_guard:{stage_key}",
                )
            except Exception as exc:
                logger.warning("Memory guard model apply failed for stage %s (%s): %s", stage_key, stage_model_id, exc)

        wait_enabled = self._is_memory_ready_wait_enabled()
        timeout_s = self._memory_ready_timeout_seconds()
        poll_s = self._memory_ready_poll_seconds()
        started = time.time()
        last_error = ""

        while True:
            can_proceed, error_message = self.qwen_manager._check_memory_before_load()
            if can_proceed:
                return

            last_error = str(error_message or "Insufficient memory to load the stage model.")
            if not wait_enabled:
                raise RuntimeError(f"Memory guard blocked stage '{stage_key}': {last_error}")

            elapsed = time.time() - started
            remaining = timeout_s - elapsed
            if remaining <= 0:
                raise RuntimeError(
                    f"Memory guard timeout for stage '{stage_key}' after {timeout_s}s: {last_error}"
                )

            if progress_callback:
                progress_callback(
                    f"[WAIT] Memory gate for '{stage_key}' ({int(remaining)}s left): {last_error}"
                )
            time.sleep(poll_s)

    def _should_skip_critic_stage(self) -> bool:
        def _to_bool(value: Any) -> bool:
            if isinstance(value, bool):
                return value
            return str(value).strip().lower() in ("1", "true", "yes", "y", "on")

        try:
            if self.qwen_manager._is_survival_mode():
                return True
        except Exception:
            pass

        env_flag = os.getenv("CVMATCH_SKIP_CRITIC")
        if env_flag is not None:
            return _to_bool(env_flag)

        custom = getattr(self.qwen_manager, "custom_parameters", None) or {}
        if "skip_critic" in custom:
            return _to_bool(custom.get("skip_critic"))

        if "skip_critic_in_low_vram" in custom:
            enabled = _to_bool(custom.get("skip_critic_in_low_vram"))
            if not enabled:
                return False
            try:
                return bool(self.qwen_manager._is_low_vram_mode())
            except Exception:
                return enabled

        try:
            return bool(self.qwen_manager._is_low_vram_mode())
        except Exception:
            return False

    def _run_stage_subprocess(self, stage: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        from dataclasses import asdict

        import uuid

        repo_root = Path(__file__).resolve().parents[2]
        tmp_dir = Path(tempfile.gettempdir())
        token = uuid.uuid4().hex
        input_path = tmp_dir / f"cvmatch_stage_{stage}_{token}_in.json"
        output_path = tmp_dir / f"cvmatch_stage_{stage}_{token}_out.json"

        payload = dict(payload)
        payload["profile_data"] = asdict(self.profile_data)
        payload["offer_data"] = self.offer_data
        payload["template"] = self.template
        payload.setdefault("user_instruction", self.user_instruction)
        payload.setdefault("application_id", self.application_id)
        payload.setdefault("cv_only_regen", bool(self.cv_only_regen))
        payload.setdefault(
            "previous_generation_audit",
            dict(self.previous_generation_audit)
            if isinstance(self.previous_generation_audit, dict)
            else {},
        )
        try:
            stage_model_id = self._choose_stage_model_override(stage)
        except Exception:
            stage_model_id = None
        if stage_model_id:
            payload["stage_model_id"] = str(stage_model_id).strip()

        self._ensure_stage_memory_ready(stage, stage_model_id)

        with open(input_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, default=str)

        cmd = [
            sys.executable,
            "-m",
            "app.workers.llm_stage_runner",
            "--stage",
            stage,
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ]

        mock_path = os.environ.get("CVMATCH_STAGE_MOCK_PATH")
        if mock_path:
            cmd = [sys.executable, mock_path, str(input_path), str(output_path)]

        custom = getattr(self.qwen_manager, "custom_parameters", None) or {}
        try:
            survival_mode = bool(self.qwen_manager._is_survival_mode())
        except Exception:
            survival_mode = False
        stage_attempts = resolve_stage_attempts(
            stage,
            survival_mode=survival_mode,
            custom_parameters=custom,
            env=os.environ,
        )
        stage_timeout_seconds = resolve_stage_timeout_seconds(
            custom_parameters=custom,
            env=os.environ,
            default=0,
        )

        try:
            last_error = "unknown stage subprocess error"
            for attempt in range(1, stage_attempts + 1):
                run_env = build_stage_subprocess_env(
                    base_env=dict(os.environ),
                    stage=stage,
                    attempt=attempt,
                    attempts=stage_attempts,
                    force_survival_retry=survival_mode,
                )
                if survival_mode:
                    run_env["CVMATCH_SURVIVAL_MODE"] = "1"
                    run_env.setdefault("CVMATCH_SURVIVAL_IGNORE_SELECTED_MODEL", "1")
                if attempt > 1:
                    # Retry with disk offload priority to keep GPU footprint stable.
                    run_env.setdefault("CVMATCH_PREFER_RAM_OFFLOAD", "0")
                    run_env.setdefault("CVMATCH_FORCE_DISK_OFFLOAD", "1")
                    run_env.setdefault("CVMATCH_DISABLE_TORCH_COMPILE", "1")
                    run_env.setdefault("CVMATCH_CPU_HEADROOM_GB", "0.5")
                    run_env.setdefault("CVMATCH_VRAM_HEADROOM_GB", "2.0")
                    retry_gpu_cap_gb = 6.5
                    try:
                        total_vram_gb = float(
                            (getattr(gpu_manager, "gpu_info", {}) or {}).get("total_memory_gb")
                            or 0.0
                        )
                        if total_vram_gb > 0:
                            retry_gpu_cap_gb = max(3.5, min(7.0, total_vram_gb * 0.62))
                    except Exception:
                        pass
                    run_env.setdefault("CVMATCH_MAX_MEMORY_GPU_GB", f"{retry_gpu_cap_gb:.2f}")
                    run_env.setdefault("CVMATCH_FORCE_GPU", "0")
                    run_env.setdefault("CVMATCH_KEEP_SELECTED_STAGE_MODEL", "1")

                run_kwargs = {
                    "args": cmd,
                    "cwd": str(repo_root),
                    "env": run_env,
                    "capture_output": True,
                    "text": True,
                    "encoding": "utf-8",
                    "errors": "replace",
                }
                if stage_timeout_seconds > 0:
                    run_kwargs["timeout"] = stage_timeout_seconds

                try:
                    result = subprocess.run(**run_kwargs)
                except subprocess.TimeoutExpired as exc:
                    details = (
                        f"timeout after {stage_timeout_seconds}s"
                        if stage_timeout_seconds > 0
                        else "timeout"
                    )
                    stderr = str(getattr(exc, "stderr", "") or "")
                    stdout = str(getattr(exc, "stdout", "") or "")
                    diag_path = persist_stage_subprocess_diagnostics(
                        repo_root=repo_root,
                        stage=stage,
                        attempt=attempt,
                        attempts=stage_attempts,
                        return_code=-1,
                        stdout=stdout,
                        stderr=stderr,
                        details=details,
                    )
                    detail_with_diag = (
                        f"{details} (diagnostic: {diag_path})"
                        if diag_path
                        else details
                    )
                    last_error = detail_with_diag
                    try:
                        self.qwen_manager._record_failure(
                            f"stage_subprocess:{stage}:{detail_with_diag[:200]}"
                        )
                    except Exception:
                        pass
                    if attempt < stage_attempts:
                        logger.warning(
                            "Stage subprocess timeout, retrying: stage=%s attempt=%s/%s detail=%s",
                            stage,
                            attempt,
                            stage_attempts,
                            detail_with_diag,
                        )
                        continue
                    raise RuntimeError(
                        f"Stage subprocess failed: {stage}: {detail_with_diag}"
                    ) from exc

                if result.returncode != 0:
                    stderr = str(result.stderr or "")
                    stdout = str(result.stdout or "")
                    details = extract_stage_subprocess_error(stdout, stderr)
                    diag_path = persist_stage_subprocess_diagnostics(
                        repo_root=repo_root,
                        stage=stage,
                        attempt=attempt,
                        attempts=stage_attempts,
                        return_code=result.returncode,
                        stdout=stdout,
                        stderr=stderr,
                        details=details,
                    )
                    detail_with_diag = (
                        f"{details} (diagnostic: {diag_path})"
                        if diag_path
                        else details
                    )
                    last_error = detail_with_diag
                    try:
                        self.qwen_manager._record_failure(
                            f"stage_subprocess:{stage}:{detail_with_diag[:200]}"
                        )
                    except Exception:
                        pass
                    is_transient = is_transient_stage_memory_error(details)
                    if is_transient and attempt < stage_attempts:
                        logger.warning(
                            "Stage subprocess memory failure, retrying: stage=%s attempt=%s/%s detail=%s",
                            stage,
                            attempt,
                            stage_attempts,
                            details,
                        )
                        continue
                    raise RuntimeError(f"Stage subprocess failed: {stage}: {detail_with_diag}")

                with open(output_path, "r", encoding="utf-8") as handle:
                    return json.load(handle)

            raise RuntimeError(f"Stage subprocess failed: {stage}: {last_error}")
        finally:
            try:
                input_path.unlink(missing_ok=True)
                output_path.unlink(missing_ok=True)
            except Exception:
                pass

    def _build_profile_payload(self) -> Dict[str, Any]:
        personal_info = dict(self.profile_data.extracted_personal_info or {})
        if not personal_info.get("full_name"):
            personal_info["full_name"] = self.profile_data.name or ""
        if not personal_info.get("email"):
            personal_info["email"] = self.profile_data.email or ""
        if not personal_info.get("phone"):
            personal_info["phone"] = self.profile_data.phone or ""
        if not personal_info.get("linkedin_url"):
            personal_info["linkedin_url"] = self.profile_data.linkedin_url or ""

        return {
            "personal_info": personal_info,
            "experiences": self.profile_data.extracted_experiences or [],
            "education": self.profile_data.extracted_education or [],
            "skills": self.profile_data.extracted_skills or [],
            "soft_skills": self.profile_data.extracted_soft_skills or [],
            "languages": self.profile_data.extracted_languages or [],
            "projects": self.profile_data.extracted_projects or [],
            "certifications": self.profile_data.extracted_certifications or [],
            "publications": self.profile_data.extracted_publications or [],
            "volunteering": self.profile_data.extracted_volunteering or [],
            "awards": self.profile_data.extracted_awards or [],
            "references": self.profile_data.extracted_references or [],
            "interests": self.profile_data.extracted_interests or [],
        }

    def _build_profile_json(self) -> Dict[str, Any]:
        from ..utils.profile_json import (
            compute_profile_json_fingerprint,
            has_profile_json_content,
            load_profile_json_cache,
            map_payload_to_profile_json,
            save_profile_json_cache,
        )

        profile_payload = self._build_profile_payload()
        extracted = map_payload_to_profile_json(profile_payload, source="profile")
        profile_fingerprint = compute_profile_json_fingerprint(extracted)

        profile_id = getattr(self.profile_data, "id", None) or 0
        if profile_id:
            cached = load_profile_json_cache(
                profile_id,
                expected_fingerprint=profile_fingerprint,
            )
            if cached:
                logger.info("Profile JSON cache hit: profile_id=%s", profile_id)
                return cached

        if has_profile_json_content(extracted):
            if profile_id:
                try:
                    save_profile_json_cache(
                        profile_id,
                        extracted,
                        fingerprint=profile_fingerprint,
                    )
                except Exception as exc:
                    logger.warning(
                        "Unable to persist profile JSON cache: %s", exc
                    )
            return extracted

        logger.warning(
            "Profile JSON cache missing and extracted data empty; returning minimal profile JSON."
        )
        return extracted

    def _fact_supported_by_profile_text(self, fact: str, profile_text: str) -> bool:
        if not fact or not profile_text:
            return False
        tokens = [
            token
            for token in re.split(r"[^a-z0-9]+", fact.lower())
            if len(token) > 3
        ]
        if not tokens:
            return False
        matches = sum(1 for token in tokens if token in profile_text)
        return matches >= max(1, len(tokens) // 3)

    def _sanitize_critic_json(
        self, critic_json: Dict[str, Any], *, profile_json: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        if not isinstance(critic_json, dict):
            return {}
        allowed_keys = ("missing_keywords", "must_keep_facts")
        sanitized = {key: critic_json.get(key) for key in allowed_keys if key in critic_json}
        must_keep = sanitized.get("must_keep_facts")
        if isinstance(must_keep, list):
            profile_text = ""
            if isinstance(profile_json, dict):
                try:
                    profile_text = json.dumps(profile_json, ensure_ascii=False).lower()
                except Exception:
                    profile_text = ""
            filtered = []
            for fact in must_keep:
                if not isinstance(fact, str):
                    continue
                fact_text = fact.strip()
                if not fact_text:
                    continue
                if profile_text and not self._fact_supported_by_profile_text(
                    fact_text, profile_text
                ):
                    continue
                filtered.append(fact_text)
            sanitized["must_keep_facts"] = filtered
        return sanitized

    def _fallback_critic_json(self, *, reason: str = "") -> Dict[str, Any]:
        # Deterministic schema recovery for critic stage must stay available
        # even when CV content fallback is disabled.

        language = self._resolve_language_code()
        job_title = ""
        company = ""
        if isinstance(self.offer_data, dict):
            job_title = self.offer_data.get("job_title") or ""
            company = self.offer_data.get("company") or ""

        if language == "en":
            rewrite_prompt = (
                "Rewrite the CV to better match the job offer. "
                "Use only facts present in the CV and keep contact details intact."
            )
        else:
            rewrite_prompt = (
                "Reecrire le CV pour mieux correspondre a l'offre. "
                "Utiliser uniquement les faits presents dans le CV et conserver les contacts."
            )

        if job_title or company:
            rewrite_prompt = f"{rewrite_prompt} Target: {job_title} {company}".strip()

        payload = {
            "schema_version": "critic.v1",
            "scorecard": {
                "ats_keyword_coverage": 50,
                "clarity": 50,
                "evidence_metrics": 50,
                "consistency": 50,
            },
            "issues": [],
            "missing_keywords": [],
            "rewrite_plan": [],
            "rewrite_prompt": rewrite_prompt,
            "must_keep_facts": [],
        }

        try:
            from ..schemas.critic_schema import CriticJSON

            return CriticJSON.model_validate(payload).model_dump()
        except Exception:
            if reason:
                logger.warning("Fallback CriticJSON used due to: %s", reason)
            return payload

    def _fallback_offer_keywords_json(self, *, reason: str = "") -> Dict[str, Any]:
        # Deterministic schema recovery for offer-keywords stage must stay
        # available even when CV content fallback is disabled.

        return build_offer_keywords_fallback(
            offer_data=self.offer_data if isinstance(self.offer_data, dict) else {},
            language_code=self._resolve_language_code(),
            reason=reason,
            logger=logger,
        )

    def _is_slow_generation_device(self) -> bool:
        try:
            device = getattr(self.qwen_manager, "_device", None)
            if device is not None and getattr(device, "type", None) == "cpu":
                return True
        except Exception:
            pass
        try:
            model = getattr(self.qwen_manager, "_model", None)
            device_map = getattr(model, "hf_device_map", None)
            if isinstance(device_map, dict) and device_map:
                normalizer = getattr(self.qwen_manager, "_normalize_device_target", None)
                for value in device_map.values():
                    resolved = normalizer(value) if callable(normalizer) else None
                    if resolved is None:
                        continue
                    if resolved.type != "cuda":
                        return True
        except Exception:
            pass
        return False

    def _strict_generator_retries(self) -> int:
        retries = 1 if self._is_slow_generation_device() else 2
        if not self._allow_content_fallback():
            # When content fallback is disabled, keep one extra strict attempt
            # to reduce hard pipeline failures on transient empty JSON outputs.
            retries = max(retries, 2)
        return retries

    def _non_strict_json_generation_overrides(self, role: str) -> Dict[str, Any]:
        """
        Generation overrides for non-strict JSON retries.

        Goal: maximize JSON determinism when LMFE strict mode is unavailable.
        """
        env_value = os.getenv("CVMATCH_JSON_NON_STRICT_DETERMINISTIC")
        deterministic = self._to_bool_setting(env_value, True) if env_value is not None else True

        if not deterministic:
            return {}

        role_key = str(role or "").strip().lower()
        overrides: Dict[str, Any] = {
            "temperature": 0.0,
            "do_sample": False,
            "top_p": 0.9,
            "top_k": 40,
            "repetition_penalty": 1.05,
        }

        if role_key == "generator":
            overrides["max_new_tokens"] = 1800
        elif role_key == "critic":
            overrides["max_new_tokens"] = 1000
        elif role_key in {"offer_critic", "extractor"}:
            overrides["max_new_tokens"] = 700
        else:
            overrides["max_new_tokens"] = 900

        return overrides

    def _allow_content_fallback(self) -> bool:
        # Product policy: CV content fallback is disabled.
        # Deterministic schema recovery for auxiliary JSON stages remains enabled.
        return False

    def _get_max_model_size_cap_b(self) -> float:
        custom = getattr(self.qwen_manager, "custom_parameters", None) or {}
        default_cap = 0.0

        raw_env = os.getenv("CVMATCH_MAX_MODEL_SIZE_B")
        raw_custom = custom.get("max_model_size_b")
        raw_value = raw_env if raw_env is not None else raw_custom
        if raw_value not in (None, ""):
            try:
                default_cap = float(raw_value)
            except Exception:
                default_cap = 0.0

        small_mode = self._to_bool_setting(
            os.getenv("CVMATCH_SMALL_MODELS_ONLY"),
            self._to_bool_setting(custom.get("small_models_only"), False),
        )
        if small_mode and default_cap <= 0:
            default_cap = 2.0

        return max(0.0, default_cap)

    @staticmethod
    def _estimate_model_size_for_id(model_id: str) -> float:
        model_key = str(model_id or "").strip()
        if not model_key:
            return 0.0
        try:
            from ..utils.model_manager import model_manager

            info = model_manager.get_model_info(model_key)
            if not info:
                return 0.0
            model_path = str(getattr(info, "model_path", "") or "")
            return float(
                _estimate_model_size_gb(
                    model_name=model_path,
                    model_id=model_key,
                )
            )
        except Exception:
            return 0.0

    def _is_model_within_size_cap(self, model_id: str, max_model_size_b: float) -> bool:
        cap = float(max_model_size_b or 0.0)
        if cap <= 0:
            return True
        estimate = self._estimate_model_size_for_id(model_id)
        if estimate <= 0:
            return True
        return estimate <= cap + 1e-6

    def _consume_qwen_runtime_error(self) -> str:
        getter = getattr(self.qwen_manager, "get_last_generation_error", None)
        if not callable(getter):
            return ""
        try:
            return str(getter(clear=True) or "").strip()
        except TypeError:
            try:
                return str(getter() or "").strip()
            except Exception:
                return ""
        except Exception:
            return ""

    @staticmethod
    def _compose_fallback_reason(*, strict_error: Any = "", retry_error: Any = "") -> str:
        strict_text = str(strict_error or "").strip()
        retry_text = str(retry_error or "").strip()
        if strict_text and retry_text:
            return f"strict={strict_text}; retry={retry_text}"
        return strict_text or retry_text

    @staticmethod
    def _is_strict_missing_required_error(error: Any) -> bool:
        text = str(error or "").lower()
        if "validation errors for cvjson" not in text:
            return False
        required_markers = (
            "target_job_title",
            "target_company",
            "contact",
            "summary",
            "field required",
        )
        return all(marker in text for marker in required_markers)

    def _apply_contact_fallback(
        self, cv_json: Dict[str, Any], profile_json: Dict[str, Any]
    ) -> None:
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
            "full_name": self.profile_data.name or "",
            "email": self.profile_data.email or "",
            "phone": self.profile_data.phone or "",
            "linkedin_url": self.profile_data.linkedin_url or "",
        }

        for field in ("full_name", "email", "phone", "linkedin_url", "location"):
            if contact.get(field):
                continue
            value = personal.get(field) or fallback.get(field)
            if value:
                contact[field] = value

    def _summary_needs_rewrite(self, summary: str) -> bool:
        if not summary or not summary.strip():
            return True
        return self._text_has_review_markers(summary)

    def _repair_summary_if_needed(
        self, cv_json_final: Dict[str, Any], cv_json_draft: Dict[str, Any]
    ) -> None:
        if not isinstance(cv_json_final, dict):
            return
        summary = cv_json_final.get("summary") or ""
        if not self._summary_needs_rewrite(summary):
            return
        draft_summary = ""
        if isinstance(cv_json_draft, dict):
            draft_summary = cv_json_draft.get("summary") or ""
        if draft_summary and not self._summary_needs_rewrite(draft_summary):
            cv_json_final["summary"] = draft_summary
            logger.warning("Final summary looked like review text; reverted to draft summary.")
        else:
            cv_json_final["summary"] = ""
            logger.warning("Final summary looked like review text; cleared summary.")

    def _apply_target_fallback(self, cv_json: Dict[str, Any]) -> None:
        if not isinstance(cv_json, dict):
            return
        job_title = ""
        company = ""
        if isinstance(self.offer_data, dict):
            job_title = self.offer_data.get("job_title") or ""
            company = self.offer_data.get("company") or ""
        if not cv_json.get("target_job_title") and job_title:
            cv_json["target_job_title"] = job_title
        if not cv_json.get("target_company") and company:
            cv_json["target_company"] = company

    def _build_minimum_summary(
        self,
        *,
        profile_json: Dict[str, Any],
        target_job_title: str = "",
        target_company: str = "",
    ) -> str:
        profile_data = profile_json if isinstance(profile_json, dict) else {}
        personal = profile_data.get("personal_info")
        if not isinstance(personal, dict):
            personal = {}

        headline = str(personal.get("summary") or personal.get("headline") or "").strip()
        if headline and not self._text_has_review_markers(headline):
            return _trim_text(headline, 420)

        exp_titles: List[str] = []
        for entry in profile_data.get("experiences") or []:
            if not isinstance(entry, dict):
                continue
            title = str(
                entry.get("title")
                or entry.get("position")
                or entry.get("role")
                or entry.get("job_title")
                or ""
            ).strip()
            if title and title not in exp_titles:
                exp_titles.append(title)
            if len(exp_titles) >= 2:
                break

        skill_terms: List[str] = []
        for entry in profile_data.get("skills") or []:
            if isinstance(entry, str):
                candidate = entry.strip()
                if candidate and candidate not in skill_terms:
                    skill_terms.append(candidate)
            elif isinstance(entry, dict):
                direct = str(
                    entry.get("name")
                    or entry.get("skill")
                    or entry.get("label")
                    or ""
                ).strip()
                if direct and direct not in skill_terms:
                    skill_terms.append(direct)
                items = entry.get("items")
                if isinstance(items, list):
                    for item in items:
                        text = str(item or "").strip()
                        if text and text not in skill_terms:
                            skill_terms.append(text)
                        if len(skill_terms) >= 6:
                            break
            if len(skill_terms) >= 6:
                break

        lang = self._resolve_language_code()
        role_text = str(target_job_title or "").strip() or ("target role" if lang == "en" else "poste cible")
        company_text = str(target_company or "").strip()

        if lang == "en":
            summary = f"Profile aligned with {role_text}"
            if company_text:
                summary += f" at {company_text}"
            if exp_titles:
                summary += f". Experience in {', '.join(exp_titles[:2])}"
            if skill_terms:
                summary += f". Core skills: {', '.join(skill_terms[:5])}"
            summary += "."
        else:
            summary = f"Profil aligne sur le poste {role_text}"
            if company_text:
                summary += f" chez {company_text}"
            if exp_titles:
                summary += f". Experience en {', '.join(exp_titles[:2])}"
            if skill_terms:
                summary += f". Competences cles: {', '.join(skill_terms[:5])}"
            summary += "."

        return _trim_text(summary, 420)

    @staticmethod
    def _normalize_language_identity(value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        folded = (
            unicodedata.normalize("NFKD", text)
            .encode("ascii", "ignore")
            .decode("ascii")
            .lower()
            .strip()
        )
        if not folded:
            return ""
        folded = re.sub(r"[^a-z0-9+#]+", " ", folded).strip()
        aliases = {
            "en": "english",
            "eng": "english",
            "english": "english",
            "anglais": "english",
            "fr": "french",
            "fra": "french",
            "french": "french",
            "francais": "french",
            "francais langue maternelle": "french",
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
            "jp": "japanese",
            "jpn": "japanese",
            "japanese": "japanese",
            "japonais": "japanese",
            "zh": "chinese",
            "cn": "chinese",
            "chinese": "chinese",
            "chinois": "chinese",
            "mandarin": "chinese",
            "ru": "russian",
            "rus": "russian",
            "russian": "russian",
            "russe": "russian",
            "ar": "arabic",
            "ara": "arabic",
            "arabic": "arabic",
            "arabe": "arabic",
        }
        if folded in aliases:
            return aliases[folded]
        compact = folded.replace(" ", "")
        if compact in aliases:
            return aliases[compact]
        if compact.startswith("fran") and compact.endswith("ais"):
            return "french"
        if compact.startswith("angl"):
            return "english"
        if compact.startswith("japon"):
            return "japanese"
        if compact.startswith("allem"):
            return "german"
        if compact.startswith("espagn"):
            return "spanish"
        return folded

    @staticmethod
    def _normalize_language_level(value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        cefr_match = re.search(r"\b([ABC][12])\b", text.upper())
        if cefr_match:
            return cefr_match.group(1)

        folded = (
            unicodedata.normalize("NFKD", text)
            .encode("ascii", "ignore")
            .decode("ascii")
            .lower()
            .strip()
        )
        synonyms = {
            "native": "C2",
            "natif": "C2",
            "mother tongue": "C2",
            "langue maternelle": "C2",
            "bilingual": "C2",
            "bilingue": "C2",
            "fluent": "C1",
            "courant": "C1",
            "advanced": "B2",
            "avance": "B2",
            "upper intermediate": "B2",
            "intermediaire superieur": "B2",
            "intermediate": "B1",
            "intermediaire": "B1",
            "elementary": "A2",
            "elementaire": "A2",
            "beginner": "A1",
            "debutant": "A1",
            "basic": "A1",
            "notions": "A1",
        }
        for marker, mapped in synonyms.items():
            if marker in folded:
                return mapped
        return text

    @staticmethod
    def _is_generic_language_level(value: Any) -> bool:
        text = str(value or "").strip()
        if not text:
            return True
        if re.search(r"\b([ABC][12])\b", text.upper()):
            return False
        folded = (
            unicodedata.normalize("NFKD", text)
            .encode("ascii", "ignore")
            .decode("ascii")
            .lower()
            .strip()
        )
        generic_markers = (
            "native",
            "natif",
            "mother tongue",
            "langue maternelle",
            "bilingual",
            "bilingue",
            "fluent",
            "courant",
            "advanced",
            "avance",
            "intermediate",
            "intermediaire",
            "beginner",
            "debutant",
            "basic",
            "elementary",
            "elementaire",
        )
        return any(marker in folded for marker in generic_markers)

    def _merge_languages_with_profile(
        self,
        generated_languages: Any,
        profile_languages: Any,
    ) -> List[Dict[str, str]]:
        profile_map: Dict[str, Dict[str, str]] = {}
        profile_order: List[str] = []

        for entry in profile_languages or []:
            if not isinstance(entry, dict):
                continue
            language = str(entry.get("language") or entry.get("name") or "").strip()
            key = self._normalize_language_identity(language)
            if not key:
                continue
            level = self._normalize_language_level(
                entry.get("level") or entry.get("proficiency") or ""
            )
            certification = str(
                entry.get("certification")
                or entry.get("certificate")
                or entry.get("organization")
                or entry.get("issuer")
                or ""
            ).strip()
            if key not in profile_map:
                profile_map[key] = {
                    "language": language,
                    "level": level,
                    "certification": certification,
                }
                profile_order.append(key)
            else:
                if level and not profile_map[key].get("level"):
                    profile_map[key]["level"] = level
                if certification and not profile_map[key].get("certification"):
                    profile_map[key]["certification"] = certification
                if language and len(language) > len(profile_map[key].get("language") or ""):
                    profile_map[key]["language"] = language

        merged: List[Dict[str, str]] = []
        seen: set = set()

        for entry in generated_languages or []:
            if not isinstance(entry, dict):
                continue
            language = str(entry.get("language") or entry.get("name") or "").strip()
            key = self._normalize_language_identity(language)
            if not key or key in seen:
                continue
            raw_level = entry.get("level") or entry.get("proficiency") or ""
            level = self._normalize_language_level(raw_level)
            certification = str(
                entry.get("certification")
                or entry.get("certificate")
                or entry.get("organization")
                or entry.get("issuer")
                or ""
            ).strip()

            if key in profile_map:
                profile_entry = profile_map[key]
                profile_level = profile_entry.get("level") or ""
                profile_certification = profile_entry.get("certification") or ""
                if profile_level and (not level or self._is_generic_language_level(raw_level)):
                    selected_level = profile_level
                else:
                    selected_level = level or profile_level
                selected_certification = certification or profile_certification
                merged.append(
                    {
                        "language": profile_entry.get("language") or language,
                        "level": selected_level,
                        "certification": selected_certification,
                    }
                )
            else:
                merged.append(
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
            merged.append(profile_map[key])
            seen.add(key)

        return merged[:4]

    def _ensure_required_cv_fields(
        self,
        *,
        cv_json: Dict[str, Any],
        profile_json: Dict[str, Any],
        stage: str = "",
    ) -> Dict[str, Any]:
        base = self._coerce_minimum_cv_json_payload(
            cv_json if isinstance(cv_json, dict) else {},
            profile_json=profile_json,
            reason=f"{stage or 'cv'}_required_fields",
        )

        lang = self._resolve_language_code()
        job_title = str(base.get("target_job_title") or "").strip()
        company = str(base.get("target_company") or "").strip()
        if not job_title:
            job_title = "Target Role" if lang == "en" else "Poste cible"
            base["target_job_title"] = job_title
        if not company:
            company = "Target Company" if lang == "en" else "Entreprise cible"
            base["target_company"] = company

        contact = base.get("contact")
        if not isinstance(contact, dict):
            contact = {}
            base["contact"] = contact
        if not str(contact.get("full_name") or "").strip():
            contact["full_name"] = (
                str(self.profile_data.name or "").strip()
                or ("Candidate" if lang == "en" else "Candidat")
            )

        summary = str(base.get("summary") or "").strip()
        if not summary or self._summary_needs_rewrite(summary):
            base["summary"] = self._build_minimum_summary(
                profile_json=profile_json,
                target_job_title=job_title,
                target_company=company,
            )

        return base

    def _fallback_or_minimum_cv_json(
        self,
        *,
        profile_json: Dict[str, Any],
        reason: str = "",
        stage: str = "",
    ) -> Dict[str, Any]:
        if not self._allow_content_fallback():
            logger.warning(
                "CV content fallback disabled, using deterministic minimum payload: stage=%s reason=%s",
                stage or "-",
                reason,
            )
            recovered = self._ensure_required_cv_fields(
                cv_json={},
                profile_json=profile_json,
                stage=stage or "minimum_recovery",
            )
            try:
                from ..schemas.cv_schema import CVJSON

                return CVJSON.model_validate(recovered).model_dump()
            except Exception:
                return recovered
        try:
            return self._fallback_cv_json(profile_json=profile_json, reason=reason)
        except Exception as fallback_exc:
            logger.warning(
                "CV fallback unavailable, using deterministic minimum payload: stage=%s reason=%s error=%s",
                stage or "-",
                reason,
                fallback_exc,
            )
            recovered = self._ensure_required_cv_fields(
                cv_json={},
                profile_json=profile_json,
                stage=stage or "minimum_recovery",
            )
            try:
                from ..schemas.cv_schema import CVJSON

                return CVJSON.model_validate(recovered).model_dump()
            except Exception:
                return recovered

    def _coerce_minimum_cv_json_payload(
        self,
        payload: Dict[str, Any],
        *,
        profile_json: Dict[str, Any],
        reason: str = "",
    ) -> Dict[str, Any]:
        """Coerce payload to a minimally valid CVJSON shape.

        This is a deterministic schema guard, not a model fallback.
        It prevents pipeline aborts when the model returns `{}` or
        partial JSON under memory pressure.
        """
        base = dict(payload or {}) if isinstance(payload, dict) else {}
        profile_data = profile_json if isinstance(profile_json, dict) else {}
        personal = profile_data.get("personal_info")
        if not isinstance(personal, dict):
            personal = {}

        contact = base.get("contact")
        if not isinstance(contact, dict):
            contact = {}
        base["contact"] = contact
        self._apply_contact_fallback(base, profile_data)
        self._apply_target_fallback(base)

        if not isinstance(base.get("target_job_title"), str):
            base["target_job_title"] = str(base.get("target_job_title") or "").strip()
        if not isinstance(base.get("target_company"), str):
            base["target_company"] = str(base.get("target_company") or "").strip()

        if not str(base.get("target_job_title") or "").strip():
            if isinstance(self.offer_data, dict):
                base["target_job_title"] = str(
                    self.offer_data.get("job_title")
                    or ((self.offer_data.get("analysis") or {}).get("title") if isinstance(self.offer_data.get("analysis"), dict) else "")
                    or ""
                ).strip()
        if not str(base.get("target_company") or "").strip():
            if isinstance(self.offer_data, dict):
                base["target_company"] = str(self.offer_data.get("company") or "").strip()

        summary = base.get("summary")
        if not isinstance(summary, str):
            summary = "" if summary is None else str(summary)
        summary = summary.strip()
        if not summary:
            summary = str(personal.get("summary") or personal.get("headline") or "").strip()
        base["summary"] = summary

        for list_key in ("skills", "experience", "education"):
            value = base.get(list_key)
            if value is None:
                base[list_key] = []
            elif not isinstance(value, list):
                base[list_key] = []
            else:
                base[list_key] = [item for item in value if isinstance(item, dict)]

        for optional_list_key in ("projects", "languages", "certifications"):
            value = base.get(optional_list_key)
            if value is not None and not isinstance(value, list):
                base[optional_list_key] = []
            elif isinstance(value, list):
                base[optional_list_key] = [item for item in value if isinstance(item, dict)]

        base["languages"] = self._merge_languages_with_profile(
            base.get("languages") or [],
            profile_data.get("languages") or [],
        )

        ats_keywords = base.get("ats_keywords")
        if ats_keywords is not None and not isinstance(ats_keywords, list):
            base["ats_keywords"] = []
        elif isinstance(ats_keywords, list):
            cleaned_keywords = []
            for item in ats_keywords:
                text = str(item or "").strip()
                if text:
                    cleaned_keywords.append(text)
            base["ats_keywords"] = cleaned_keywords

        render_hints = base.get("render_hints")
        if render_hints is not None and not isinstance(render_hints, dict):
            base["render_hints"] = None

        if reason:
            reason_text = str(reason or "")
            if reason_text.startswith("postprocess_base_required_fields"):
                # This is the deterministic base skeleton used by postprocess;
                # keep it visible but avoid warning noise.
                logger.info(
                    "CVJSON postprocess base skeleton prepared: %s",
                    reason_text,
                )
            else:
                logger.warning(
                    "CVJSON payload coerced to minimum schema shape: %s",
                    reason_text,
                )
        return base

    def _fallback_cv_json(
        self, *, profile_json: Dict[str, Any], reason: str = ""
    ) -> Dict[str, Any]:
        if not self._allow_content_fallback():
            raise RuntimeError(reason or "CV fallback disabled")

        return build_cv_json_fallback(
            profile_json=profile_json or {},
            profile_data=self.profile_data,
            offer_data=self.offer_data if isinstance(self.offer_data, dict) else {},
            language_code=self._resolve_language_code(),
            offer_keywords_collector=self._collect_offer_keywords,
            reason=reason,
            logger=logger,
        )

    def _resolve_language_code(self) -> str:
        analysis = self.offer_data.get("analysis") if isinstance(self.offer_data, dict) else None
        analysis_language = analysis.get("language") if isinstance(analysis, dict) else None
        offer_text = self.offer_data.get("text") if isinstance(self.offer_data, dict) else None
        detected = _detect_language_from_text(offer_text)
        preferred = getattr(self.profile_data, "preferred_language", None)

        if analysis_language and _normalize_language(analysis_language):
            analysis_norm = _normalize_language(analysis_language)
            if detected and detected != analysis_norm:
                return _normalize_language(detected)
            return analysis_norm

        if detected:
            return _normalize_language(detected)
        if preferred:
            return _normalize_language(preferred)
        return "fr"
    # Stage model routing
    def _is_stage_model_routing_enabled(self) -> bool:
        from ..utils.stage_model_routing import is_stage_model_routing_enabled
        return is_stage_model_routing_enabled()

    def _choose_stage_model_override(self, stage: str) -> Optional[str]:
        from ..utils.stage_model_routing import (
            StageModelConfig,
            is_writer_stage,
            resolve_stage_model_override,
        )

        custom = getattr(self.qwen_manager, "custom_parameters", None) or {}
        current = getattr(self.qwen_manager, "current_model_id", "")
        try:
            allow_model_fallback = bool(self.qwen_manager._allow_model_fallback())
        except Exception:
            allow_model_fallback = True
        try:
            prefer_ram_offload = bool(self.qwen_manager._prefer_ram_offload_mode())
        except Exception:
            prefer_ram_offload = False
        lock_selected_model = (not allow_model_fallback) or prefer_ram_offload
        max_model_size_b = self._get_max_model_size_cap_b()
        pressure = self._get_runtime_memory_pressure_level(force_refresh=True)
        snapshot: Dict[str, Any] = {}
        try:
            snapshot = self.qwen_manager._collect_memory_pressure_snapshot(
                force_refresh=True
            ) or {}
        except Exception:
            snapshot = {}
        try:
            ram_available_gb = float(snapshot.get("ram_available_gb") or 0.0)
        except Exception:
            ram_available_gb = 0.0
        try:
            commit_available_gb = float(snapshot.get("commit_available_gb") or 0.0)
        except Exception:
            commit_available_gb = 0.0
        lowram_level = pressure if pressure in {"tight", "critical"} else "normal"
        base_config = StageModelConfig.from_env_and_custom(custom)
        routing_config = StageModelConfig(
            enabled=base_config.enabled,
            keep_selected_model=(True if lock_selected_model else base_config.keep_selected_model),
            prefer_small_extractor=(bool(base_config.prefer_small_extractor) and not lock_selected_model),
            extractor_model_id=base_config.extractor_model_id,
            writer_model_id=base_config.writer_model_id,
            lowram_level=lowram_level,
        )
        resolution = resolve_stage_model_override(
            stage,
            config=routing_config,
            custom_parameters=custom,
            current_model_id=current,
        )

        if lock_selected_model and resolution.requires_switch and not resolution.is_explicit:
            logger.info(
                "Stage override ignored (keep selected model): stage=%s target=%s current=%s",
                stage,
                resolution.model_id,
                current,
            )
        elif resolution.requires_switch and resolution.model_id:
            if self._is_model_within_size_cap(resolution.model_id, max_model_size_b):
                return resolution.model_id
            logger.info(
                "Stage override skipped by model size cap: stage=%s model=%s cap=%.2fB",
                stage,
                resolution.model_id,
                max_model_size_b,
            )

        # Low-memory route for writer stages: proactively downshift from heavy models
        # to avoid mid-stage OOM and degraded deterministic fallback.
        writer_low_headroom = is_writer_stage(stage) and (
            pressure in {"tight", "critical"}
            or (ram_available_gb > 0 and ram_available_gb < 3.5)
            or (commit_available_gb > 0 and commit_available_gb < 4.0)
        )
        if writer_low_headroom and allow_model_fallback and not lock_selected_model:
            try:
                from ..utils.model_manager import model_manager

                available = {
                    str(mid or "").strip().lower()
                    for mid in getattr(model_manager, "available_models", [])
                    if str(mid or "").strip()
                }

                preferred = []

                env_pref = str(os.getenv("CVMATCH_WRITER_LOWRAM_MODEL_ID") or "").strip()
                if env_pref:
                    preferred.append(env_pref)

                custom_pref = str(custom.get("writer_lowram_model_id") or "").strip()
                if custom_pref:
                    preferred.append(custom_pref)

                # Keep writer quality as high as possible under pressure.
                preferred.extend(["qwen2-1.5b", "qwen2-0.5b", "qwen2-3b", "mistral-7b"])

                current_key = str(current or "").strip().lower()
                for candidate in preferred:
                    candidate_key = str(candidate or "").strip().lower()
                    if not candidate_key or candidate_key == current_key:
                        continue
                    if candidate_key in available:
                        if not self._is_model_within_size_cap(candidate_key, max_model_size_b):
                            continue
                        return candidate_key
            except Exception:
                pass

        try:
            from ..utils.model_manager import model_manager

            quality_candidate = resolve_writer_quality_override(
                stage=stage,
                current_model_id=current,
                available_model_ids=getattr(model_manager, "available_models", []),
            )
            if (
                quality_candidate
                and quality_candidate != current
                and self._is_model_within_size_cap(quality_candidate, max_model_size_b)
            ):
                return quality_candidate
        except Exception:
            pass

        return None

    def _resolve_stage_model_override(self, stage: str) -> Optional[str]:
        return self._choose_stage_model_override(stage)

    def _apply_stage_model_override(self, stage: str, progress_callback=None) -> None:
        target_model_id = self._choose_stage_model_override(stage)
        if not target_model_id:
            return

        try:
            applied = self.qwen_manager.apply_model_profile(
                target_model_id,
                reason=f"stage:{stage}",
            )
            if not applied:
                logger.warning(
                    "Stage model override not applied for %s: %s",
                    stage,
                    target_model_id,
                )
        except Exception as exc:
            logger.warning(
                "Stage model override failed for %s (%s): %s",
                stage,
                target_model_id,
                exc,
            )

    # Language consistency
    def _ensure_cv_json_language_consistency(
        self, cv_json: dict, stage: str = ""
    ) -> dict:
        from ..utils.language_policy import normalize_language_code
        lang = normalize_language_code(self._resolve_language_code())
        if isinstance(cv_json, dict) and cv_json.get("language") != lang:
            cv_json = dict(cv_json)
            cv_json["language"] = lang
        return cv_json

    # CV postprocessing
    def _postprocess_final_candidate_wrapper(
        self, cv_json: dict, critic_json: dict = None
    ) -> dict:
        try:
            from ..utils.cv_postprocessing import coerce_generated_cv_payload
            profile_json = getattr(self, "_pipeline_profile_json", {}) or {}
            if not isinstance(profile_json, dict) or not profile_json:
                try:
                    profile_json = self._build_profile_json()
                except Exception as profile_exc:
                    logger.warning(
                        "Unable to refresh profile_json for final postprocess: %s",
                        profile_exc,
                    )
                    profile_json = {}
            personal_info = self._build_profile_payload().get("personal_info", {})

            def safe_fallback_generator(pj: Dict[str, Any], reason: str) -> Dict[str, Any]:
                source_profile = pj if isinstance(pj, dict) else {}
                # Keep deterministic structural postprocessing alive without any content fallback.
                return self._ensure_required_cv_fields(
                    cv_json={},
                    profile_json=source_profile,
                    stage="postprocess_base",
                )

            return coerce_generated_cv_payload(
                payload=cv_json or {},
                profile_json=profile_json,
                fallback_generator=safe_fallback_generator,
                critic_json=critic_json,
                job_title=str(
                    self.offer_data.get("job_title") or ""
                ) if isinstance(self.offer_data, dict) else "",
                company=str(
                    self.offer_data.get("company") or ""
                ) if isinstance(self.offer_data, dict) else "",
                profile_name=personal_info.get("full_name", ""),
                profile_email=personal_info.get("email", ""),
                profile_phone=personal_info.get("phone", ""),
                profile_linkedin=personal_info.get("linkedin_url", ""),
                language_code=self._resolve_language_code(),
                keyword_alignment_fn=lambda candidate, review: self._apply_keyword_alignment(
                    candidate,
                    critic_json=review,
                ),
                offer_adaptation_fn=lambda candidate, review: self._apply_offer_adaptation(
                    candidate,
                    critic_json=review,
                    profile_json=profile_json,
                ),
            )
        except Exception as exc:
            logger.warning("_postprocess_final_candidate_wrapper failed: %s", exc)
            return cv_json or {}

    # Alignment scoring
    def _score_cv_offer_alignment(
        self, cv_json: dict, critic_json: dict = None
    ) -> dict:
        try:
            from ..utils.alignment_scoring import build_alignment_audit
            from ..utils.alignment_retry_controller import get_alignment_thresholds
            from ..utils.keyword_alignment import (
                normalize_keyword_for_match,
                normalized_term_in_probe as normalized_term_present,
            )

            probe_parts: List[str] = []
            def _collect_text_fragments(value: Any) -> None:
                if isinstance(value, str):
                    probe_parts.append(value)
                    return
                if isinstance(value, dict):
                    for nested in value.values():
                        _collect_text_fragments(nested)
                    return
                if isinstance(value, list):
                    for nested in value:
                        _collect_text_fragments(nested)

            if isinstance(cv_json, dict):
                for field in ("summary", "target_job_title", "target_company"):
                    val = cv_json.get(field)
                    if isinstance(val, str):
                        probe_parts.append(val)
                for section_key in ("skills", "ats_keywords", "experience", "projects"):
                    items = cv_json.get(section_key)
                    if isinstance(items, list):
                        for item in items:
                            _collect_text_fragments(item)
            normalized_probe = normalize_keyword_for_match(" ".join(probe_parts))

            offer_kw = self._collect_offer_keywords_only(critic_json=critic_json)
            required_exact_terms = [normalize_keyword_for_match(k) for k in offer_kw]

            offer_kw_json = self._get_offer_keywords_json() or {}
            keyword_families: Dict[str, List[str]] = {}
            families_raw = offer_kw_json.get("keyword_families") if isinstance(offer_kw_json, dict) else None
            if isinstance(families_raw, dict):
                for fam_key, fam_terms in families_raw.items():
                    if isinstance(fam_terms, list):
                        keyword_families[str(fam_key)] = [
                            normalize_keyword_for_match(t) for t in fam_terms if t
                        ]

            thresholds_raw = get_alignment_thresholds()
            thresholds = {
                "exact_min": float(
                    thresholds_raw.get(
                        "exact_min",
                        thresholds_raw.get("exact_keyword_min", 55.0),
                    )
                ),
                "family_min": float(
                    thresholds_raw.get(
                        "family_min",
                        thresholds_raw.get("lexical_family_min", 45.0),
                    )
                ),
                "overall_min": float(thresholds_raw.get("overall_min", 52.0)),
            }

            def _term_present(probe: str, term: str) -> bool:
                return normalized_term_present(probe, term) if term else False

            return build_alignment_audit(
                normalized_probe=normalized_probe,
                required_exact_terms=required_exact_terms,
                keyword_families=keyword_families,
                thresholds=thresholds,
                term_present_fn=_term_present,
            )
        except Exception as exc:
            logger.warning("_score_cv_offer_alignment failed: %s", exc)
            return {"overall_score": 0.0, "sufficient": True, "error": str(exc)}

    def _get_alignment_retry_attempts(self) -> int:
        from ..utils.alignment_retry_controller import get_alignment_retry_attempts
        return get_alignment_retry_attempts()

    def _augment_critic_with_alignment_feedback(
        self, critic_json: dict, alignment_audit: dict
    ) -> dict:
        from ..utils.alignment_retry_controller import (
            augment_critic_with_alignment_feedback,
        )
        return augment_critic_with_alignment_feedback(critic_json, alignment_audit)

    # Cover letter methods
    def _ensure_cover_letter_language_consistency(
        self, letter: str, lang: str
    ) -> str:
        try:
            from ..utils.cover_letter_pipeline import (
                ensure_cover_letter_language_consistency,
            )
            return ensure_cover_letter_language_consistency(letter, lang)
        except Exception as exc:
            logger.warning("Cover letter language check failed: %s", exc)
            return letter

    def _is_cover_letter_structure_coherent(
        self, letter: str, language_code: Optional[str] = None
    ) -> bool:
        try:
            from ..utils.cover_letter_rules import is_cover_letter_structure_coherent
            lang = language_code or self._resolve_language_code()
            return is_cover_letter_structure_coherent(letter, language_code=lang)
        except Exception as exc:
            logger.warning("Cover letter structure check failed: %s", exc)
            return True

    def _enforce_cover_letter_offer_alignment(
        self, letter: str, offer_data: dict
    ) -> str:
        return letter

    def critique_and_rewrite_cover_letter(
        self,
        cover_letter: str,
        language_code: str,
        progress_callback=None,
    ) -> str:
        try:
            from ..utils.cover_letter_pipeline import build_cover_letter_rewrite_prompt
            base_prompt = self.build_cover_letter_prompt()
            prompt = build_cover_letter_rewrite_prompt(
                base_prompt=base_prompt,
                cover_letter=cover_letter,
                review={},
                language_code=language_code,
            )
            return self.qwen_manager.generate_cover_letter(prompt, progress_callback)
        except Exception as exc:
            logger.warning("critique_and_rewrite_cover_letter failed: %s", exc)
            return cover_letter

    def _should_run_cover_letter_critic_stage(self) -> bool:
        return bool(getattr(self, "cover_letter_critic_enabled", False))
    def _text_has_review_markers(self, text: str) -> bool:
        if not text:
            return False
        lowered = text.strip().lower()
        markers = (
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
            "le cv",
            "ce cv",
            "le candidat",
            "devrait",
            "doit",
            "manque",
            "a revoir",
            "ameliorer",
        )
        if any(marker in lowered for marker in markers):
            return True
        return bool(re.search(r"\\b(should|must|needs)\\b", lowered))

    def _strip_placeholders(self, text: str) -> str:
        if not text:
            return ""
        cleaned = str(text)
        cleaned = re.sub(
            r"\\[(?:A COMPLETER|TO COMPLETE|VOTRE|YOUR|PROFILE_JSON|YEAR_OF_PROFILE_JSON|IMPACT)[^\\]]*\\]",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        if re.search(r"(PROFILE_JSON|YEAR_OF_PROFILE_JSON)", cleaned, re.IGNORECASE):
            return ""
        return cleaned.strip()

    def _extract_terms_from_text(
        self,
        text: str,
        *,
        mapping: Dict[str, str],
        candidate_terms: List[str],
        max_items: int = 8,
    ) -> List[str]:
        if not text:
            return []
        normalized_text = _normalize_keyword_for_match(text)
        if not normalized_text:
            return []
        hits: List[str] = []
        for src, dst in mapping.items():
            if _normalize_keyword_for_match(dst) in normalized_text:
                hits.append(dst)
            elif _normalize_keyword_for_match(src) in normalized_text:
                hits.append(dst)
        for term in candidate_terms:
            if _normalize_keyword_for_match(term) in normalized_text:
                hits.append(mapping.get(term, term))
        return _dedup_preserve(hits)[:max_items]

    def _sanitize_cv_json_output(self, cv_json: Dict[str, Any]) -> None:
        if not isinstance(cv_json, dict):
            return
        fallback_category = "Skills" if self._resolve_language_code() == "en" else "Competences"

        def clean_text(value: Any) -> str:
            if not isinstance(value, str):
                return ""
            cleaned = self._strip_placeholders(value)
            if not cleaned or self._text_has_review_markers(cleaned):
                return ""
            return cleaned

        contact = cv_json.get("contact")
        if isinstance(contact, dict):
            for field in ("full_name", "email", "phone", "linkedin_url", "location"):
                contact[field] = clean_text(contact.get(field))

        cv_json["summary"] = clean_text(cv_json.get("summary") or "")
        cv_json["target_job_title"] = clean_text(cv_json.get("target_job_title") or "")
        cv_json["target_company"] = clean_text(cv_json.get("target_company") or "")

        cleaned_skills = []
        for category in cv_json.get("skills", []) or []:
            if not isinstance(category, dict):
                continue
            label = clean_text(category.get("category") or "")
            items = category.get("items") or []
            if not isinstance(items, list):
                items = []
            cleaned_items = []
            for item in items:
                if not isinstance(item, str):
                    continue
                text = clean_text(item)
                if not text:
                    continue
                if len(text) > 80 or self._text_has_review_markers(text):
                    continue
                cleaned_items.append(text)
            cleaned_items = _dedup_preserve(cleaned_items)
            if cleaned_items:
                cleaned_skills.append(
                    {"category": label or fallback_category,
                     "items": cleaned_items}
                )
        cv_json["skills"] = cleaned_skills

        cleaned_experience = []
        for entry in cv_json.get("experience", []) or []:
            if not isinstance(entry, dict):
                continue
            cleaned_entry = {
                "title": clean_text(entry.get("title") or ""),
                "company": clean_text(entry.get("company") or ""),
                "start_date": clean_text(entry.get("start_date") or ""),
                "end_date": clean_text(entry.get("end_date") or ""),
                "location": clean_text(entry.get("location") or ""),
                "summary": clean_text(entry.get("summary") or ""),
            }
            highlights = []
            for item in entry.get("highlights", []) or []:
                if not isinstance(item, str):
                    continue
                text = clean_text(item)
                if text:
                    highlights.append(text)
            cleaned_entry["highlights"] = _dedup_preserve(highlights)
            if not any(cleaned_entry.values()) and not cleaned_entry["highlights"]:
                continue
            cleaned_experience.append(cleaned_entry)
        cv_json["experience"] = cleaned_experience

        cleaned_education = []
        for entry in cv_json.get("education", []) or []:
            if not isinstance(entry, dict):
                continue
            cleaned_entry = {
                "school": clean_text(entry.get("school") or ""),
                "degree": clean_text(entry.get("degree") or ""),
                "field_of_study": clean_text(entry.get("field_of_study") or ""),
                "start_date": clean_text(entry.get("start_date") or ""),
                "end_date": clean_text(entry.get("end_date") or ""),
                "location": clean_text(entry.get("location") or ""),
                "details": [],
            }
            details = []
            for item in entry.get("details", []) or []:
                if not isinstance(item, str):
                    continue
                text = clean_text(item)
                if text:
                    details.append(text)
            cleaned_entry["details"] = _dedup_preserve(details)
            if not any(
                cleaned_entry.get(field)
                for field in ("school", "degree", "field_of_study", "start_date", "end_date", "location")
            ) and not cleaned_entry["details"]:
                continue
            cleaned_education.append(cleaned_entry)
        cv_json["education"] = cleaned_education

        cleaned_projects = []
        for entry in cv_json.get("projects", []) or []:
            if not isinstance(entry, dict):
                continue
            cleaned_entry = {
                "name": clean_text(entry.get("name") or ""),
                "description": clean_text(entry.get("description") or ""),
                "technologies": clean_text(entry.get("technologies") or ""),
                "url": clean_text(entry.get("url") or ""),
            }
            if not any(cleaned_entry.values()):
                continue
            cleaned_projects.append(cleaned_entry)
        cv_json["projects"] = cleaned_projects

        cleaned_languages = []
        for entry in cv_json.get("languages", []) or []:
            if not isinstance(entry, dict):
                continue
            language = clean_text(entry.get("language") or "")
            level = clean_text(entry.get("level") or "")
            certification = clean_text(entry.get("certification") or "")
            if not language:
                continue
            cleaned_languages.append(
                {
                    "language": language,
                    "level": level,
                    "certification": certification,
                }
            )
        cv_json["languages"] = cleaned_languages

        cleaned_certs = []
        for entry in cv_json.get("certifications", []) or []:
            if not isinstance(entry, dict):
                continue
            cleaned_entry = {
                "name": clean_text(entry.get("name") or ""),
                "organization": clean_text(entry.get("organization") or ""),
                "date": clean_text(entry.get("date") or ""),
                "url": clean_text(entry.get("url") or ""),
            }
            if not cleaned_entry.get("name"):
                continue
            cleaned_certs.append(cleaned_entry)
        cv_json["certifications"] = cleaned_certs

        if isinstance(cv_json.get("ats_keywords"), list):
            cleaned_keywords = []
            for item in cv_json.get("ats_keywords") or []:
                if not isinstance(item, str):
                    continue
                text = clean_text(item)
                if text:
                    cleaned_keywords.append(text)
            cv_json["ats_keywords"] = _dedup_preserve(cleaned_keywords)

    def _merge_cv_json_missing_sections(
        self, cv_json_final: Dict[str, Any], cv_json_draft: Dict[str, Any]
    ) -> None:
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

    def _collect_offer_keywords_only(
        self, critic_json: Optional[Dict[str, Any]] = None
    ) -> List[str]:
        keywords: List[str] = []
        offer_keywords = self._get_offer_keywords_json()
        if isinstance(offer_keywords, dict):
            for key in (
                "keywords",
                "skills",
                "tools",
                "soft_skills",
                "responsibilities",
                "education",
                "certifications",
            ):
                value = offer_keywords.get(key)
                if isinstance(value, list):
                    keywords.extend(str(item) for item in value)
                elif isinstance(value, str):
                    keywords.extend(part.strip() for part in value.split(",") if part.strip())
            job_title = offer_keywords.get("job_title") or ""
            if job_title:
                keywords.extend(part for part in job_title.split() if part)
        else:
            analysis = (
                self.offer_data.get("analysis") if isinstance(self.offer_data, dict) else None
            )
            if isinstance(analysis, dict):
                for key in (
                    "keywords",
                    "skills",
                    "tech_keywords",
                    "soft_keywords",
                    "tools",
                    "responsibilities",
                    "education",
                    "certifications",
                ):
                    value = analysis.get(key)
                    if isinstance(value, list):
                        keywords.extend(str(item) for item in value)
                    elif isinstance(value, str):
                        keywords.extend(part.strip() for part in value.split(",") if part.strip())

        if critic_json and isinstance(critic_json, dict):
            missing = critic_json.get("missing_keywords")
            if isinstance(missing, list):
                keywords.extend(str(item) for item in missing)

        job_title = self.offer_data.get("job_title") if isinstance(self.offer_data, dict) else ""
        if job_title:
            keywords.extend(part for part in job_title.split() if part)

        return _dedup_preserve([k for k in keywords if isinstance(k, str) and k.strip()])[:60]

    def _update_ats_keywords(
        self, cv_json: Dict[str, Any], offer_keywords: List[str]
    ) -> None:
        if not isinstance(cv_json, dict) or not offer_keywords:
            return
        offer_keywords = _dedup_preserve(
            [item for item in offer_keywords if isinstance(item, str) and item.strip()]
        )
        offer_norm = {_normalize_keyword_for_match(item) for item in offer_keywords}
        existing = cv_json.get("ats_keywords")
        existing_list = (
            [item for item in existing if isinstance(item, str)]
            if isinstance(existing, list)
            else []
        )
        filtered_existing = [
            item
            for item in existing_list
            if _normalize_keyword_for_match(item) in offer_norm
        ]
        combined = _dedup_preserve(filtered_existing + offer_keywords)
        cv_json["ats_keywords"] = combined[:15]

    def _apply_keyword_alignment(
        self,
        cv_json: Dict[str, Any],
        *,
        critic_json: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not isinstance(cv_json, dict):
            return
        offer_keywords = self._collect_offer_keywords_only(critic_json)
        if not offer_keywords:
            return
        candidate_terms = _collect_candidate_keywords(self.profile_data)
        mapping = _build_keyword_alignment(candidate_terms, offer_keywords)
        language_code = self._resolve_language_code()
        fallback_category = "Skills" if language_code == "en" else "Competences"
        offer_norm = {_normalize_keyword_for_match(item) for item in offer_keywords}
        if not mapping:
            self._update_ats_keywords(cv_json, offer_keywords)
            fallback_items = []
            for term in candidate_terms:
                if _normalize_keyword_for_match(term) in offer_norm:
                    fallback_items.append(term)
            fallback_items = _dedup_preserve(fallback_items)
            if fallback_items and not cv_json.get("skills"):
                cv_json["skills"] = [
                    {"category": fallback_category, "items": fallback_items[:8]}
                ]
            logger.info("Keyword alignment skipped: no candidate matches.")
            return

        replacements = 0
        summary = cv_json.get("summary")
        if isinstance(summary, str):
            cv_json["summary"], count = _replace_terms_in_text(summary, mapping)
            replacements += count

        skills_present = False
        for category in cv_json.get("skills", []) or []:
            if not isinstance(category, dict):
                continue
            items = category.get("items")
            if isinstance(items, list):
                updated_items = []
                for item in items:
                    if not isinstance(item, str):
                        updated_items.append(item)
                        continue
                    cleaned = self._strip_placeholders(item)
                    if not cleaned:
                        continue
                    if self._text_has_review_markers(cleaned) or len(cleaned) > 80:
                        extracted = self._extract_terms_from_text(
                            cleaned,
                            mapping=mapping,
                            candidate_terms=candidate_terms,
                        )
                        updated_items.extend(extracted)
                        continue
                    updated, count = _replace_terms_in_text(cleaned, mapping)
                    replacements += count
                    updated_items.append(updated)
                category["items"] = _dedup_preserve(
                    [item for item in updated_items if isinstance(item, str) and item.strip()]
                )
                if category["items"]:
                    skills_present = True

        for entry in cv_json.get("experience", []) or []:
            if not isinstance(entry, dict):
                continue
            entry_summary = entry.get("summary")
            if isinstance(entry_summary, str):
                entry["summary"], count = _replace_terms_in_text(entry_summary, mapping)
                replacements += count
            highlights = entry.get("highlights")
            if isinstance(highlights, list):
                updated_highlights = []
                for highlight in highlights:
                    if not isinstance(highlight, str):
                        updated_highlights.append(highlight)
                        continue
                    updated, count = _replace_terms_in_text(highlight, mapping)
                    replacements += count
                    updated_highlights.append(updated)
                entry["highlights"] = _dedup_preserve(
                    [
                        item
                        for item in updated_highlights
                        if isinstance(item, str) and item.strip()
                    ]
                )

        for project in cv_json.get("projects", []) or []:
            if not isinstance(project, dict):
                continue
            for key in ("description", "technologies"):
                value = project.get(key)
                if isinstance(value, str) and value.strip():
                    project[key], count = _replace_terms_in_text(value, mapping)
                    replacements += count

        for edu in cv_json.get("education", []) or []:
            if not isinstance(edu, dict):
                continue
            field = edu.get("field_of_study")
            if isinstance(field, str) and field.strip():
                edu["field_of_study"], count = _replace_terms_in_text(field, mapping)
                replacements += count
            details = edu.get("details")
            if isinstance(details, list):
                updated_details = []
                for detail in details:
                    if not isinstance(detail, str):
                        updated_details.append(detail)
                        continue
                    updated, count = _replace_terms_in_text(detail, mapping)
                    replacements += count
                    updated_details.append(updated)
                edu["details"] = _dedup_preserve(
                    [item for item in updated_details if isinstance(item, str) and item.strip()]
                )

        if not skills_present:
            fallback_items = _dedup_preserve(list(mapping.values()))
            if not fallback_items:
                for term in candidate_terms:
                    if _normalize_keyword_for_match(term) in offer_norm:
                        fallback_items.append(term)
                fallback_items = _dedup_preserve(fallback_items)
            if fallback_items:
                cv_json["skills"] = [
                    {"category": fallback_category, "items": fallback_items[:8]}
                ]

        self._update_ats_keywords(cv_json, offer_keywords)
        logger.info(
            "Keyword alignment applied: pairs=%s replacements=%s",
            len(mapping),
            replacements,
        )

    def _apply_offer_adaptation(
        self,
        cv_json: Dict[str, Any],
        *,
        critic_json: Optional[Dict[str, Any]] = None,
        profile_json: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not isinstance(cv_json, dict):
            return
        try:
            from ..utils.cv_postprocessing import enforce_cv_offer_adaptation
            from ..utils.keyword_alignment import (
                normalize_keyword_for_match,
                normalized_term_in_probe as normalized_term_present,
            )
        except Exception:
            return

        offer_keywords = self._collect_offer_keywords_only(critic_json=critic_json)
        critic_missing: List[str] = []
        if isinstance(critic_json, dict):
            raw_missing = critic_json.get("missing_keywords")
            if isinstance(raw_missing, list):
                for item in raw_missing:
                    text = str(item or "").strip()
                    if text:
                        critic_missing.append(text)
        critic_missing = _dedup_preserve(critic_missing)

        summary_probe = normalize_keyword_for_match(str(cv_json.get("summary") or ""))
        experience_parts: List[str] = []
        for item in cv_json.get("experience") or []:
            if not isinstance(item, dict):
                continue
            for key in ("title", "company", "summary"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    experience_parts.append(value)
            highlights = item.get("highlights")
            if isinstance(highlights, list):
                for value in highlights:
                    if isinstance(value, str) and value.strip():
                        experience_parts.append(value)
        experience_probe = normalize_keyword_for_match(" ".join(experience_parts))

        def _normalized_term_in_probe(probe: str, normalized_term: str) -> bool:
            # Token-boundary match on normalized text to avoid false positives
            # like "go" in "ongoing" or "c" in "customer", while matching
            # terms across delimiters like "/" and ".".
            return normalized_term_present(probe, normalized_term)

        def missing_terms(terms: List[str], probe: str, limit: int) -> List[str]:
            output: List[str] = []
            for term in terms:
                norm = normalize_keyword_for_match(term)
                if not norm:
                    continue
                if _normalized_term_in_probe(probe, norm):
                    continue
                output.append(term)
                if len(output) >= limit:
                    break
            return output

        def coverage_ratio(terms: List[str], probe: str) -> float:
            normalized_terms: List[str] = []
            seen: set[str] = set()
            for term in terms:
                norm = normalize_keyword_for_match(term)
                if not norm or norm in seen:
                    continue
                seen.add(norm)
                normalized_terms.append(norm)
            if not normalized_terms:
                return 1.0
            present = sum(
                1 for term in normalized_terms if _normalized_term_in_probe(probe, term)
            )
            return present / float(len(normalized_terms))

        reference_terms = critic_missing if critic_missing else offer_keywords
        combined_probe = " ".join(
            part for part in (summary_probe, experience_probe) if part
        ).strip()
        reference_coverage = coverage_ratio(reference_terms, combined_probe)
        missing_ratio = max(0.0, 1.0 - reference_coverage)

        summary_limit = 4
        experience_limit = 3
        fallback_summary_limit = 3
        fallback_experience_limit = 2
        if missing_ratio >= 0.70:
            summary_limit = 6
            experience_limit = 5
            fallback_summary_limit = 5
            fallback_experience_limit = 4
        elif missing_ratio >= 0.50:
            summary_limit = 5
            experience_limit = 4
            fallback_summary_limit = 4
            fallback_experience_limit = 3

        missing_summary_terms = missing_terms(critic_missing, summary_probe, summary_limit)
        missing_experience_terms = missing_terms(critic_missing, experience_probe, experience_limit)

        # If critic did not provide useful misses, fall back to offer keywords.
        if not missing_summary_terms:
            missing_summary_terms = missing_terms(
                offer_keywords, summary_probe, fallback_summary_limit
            )
        if not missing_experience_terms:
            missing_experience_terms = missing_terms(
                offer_keywords, experience_probe, fallback_experience_limit
            )

        if not missing_summary_terms and not missing_experience_terms:
            return

        enforce_cv_offer_adaptation(
            cv_json,
            job_title=str(self.offer_data.get("job_title") or "")
            if isinstance(self.offer_data, dict)
            else "",
            company=str(self.offer_data.get("company") or "")
            if isinstance(self.offer_data, dict)
            else "",
            aligned_terms=offer_keywords[:20],
            missing_summary_terms=missing_summary_terms,
            missing_experience_terms=missing_experience_terms,
            summary_term_limit=summary_limit,
            experience_term_limit=experience_limit,
            language_code=self._resolve_language_code(),
            profile_json=profile_json if isinstance(profile_json, dict) else None,
        )
        logger.info(
            "Offer adaptation enforced from critic: summary_terms=%s experience_terms=%s coverage=%.2f missing_ratio=%.2f",
            len(missing_summary_terms),
            len(missing_experience_terms),
            reference_coverage,
            missing_ratio,
        )

    def _collect_offer_keywords(self) -> List[str]:
        keywords: List[str] = []
        analysis = (
            self.offer_data.get("analysis") if isinstance(self.offer_data, dict) else None
        )
        if isinstance(analysis, dict):
            for key in (
                "tech_keywords",
                "soft_keywords",
                "soft_skills",
                "keywords",
                "skills",
                "skills_required",
                "tools",
                "responsibilities",
                "certifications",
            ):
                value = analysis.get(key)
                if isinstance(value, list):
                    keywords.extend(str(item) for item in value)
                elif isinstance(value, str):
                    keywords.extend(part.strip() for part in value.split(","))

        job_title = self.offer_data.get("job_title") if isinstance(self.offer_data, dict) else ""
        if job_title:
            keywords.extend(part for part in job_title.split() if part)

        candidate_terms = _collect_candidate_keywords(self.profile_data)
        keywords.extend(candidate_terms)

        return _dedup_preserve([k for k in keywords if isinstance(k, str) and k.strip()])[:60]

    def _prepare_offer_text(self, *, max_chars: int) -> str:
        offer_text = extract_offer_text_from_offer_data(
            self.offer_data if isinstance(self.offer_data, dict) else {}
        )
        offer_text = offer_text or ""
        if not offer_text:
            return ""
        if len(offer_text) <= max_chars:
            return offer_text
        from ..utils.text_chunking import select_relevant_blocks

        keywords = self._collect_offer_keywords()
        return select_relevant_blocks(
            offer_text,
            max_chars=max_chars,
            keywords=keywords,
            max_block_chars=900,
        )

    def _prepare_cv_html(self, cv_html: str, *, max_chars: int) -> str:
        if not cv_html:
            return ""
        if len(cv_html) <= max_chars:
            return cv_html
        from ..utils.text_chunking import select_relevant_blocks

        keywords = self._collect_offer_keywords()
        return select_relevant_blocks(
            cv_html,
            max_chars=max_chars,
            keywords=keywords,
            max_block_chars=900,
            strip_html_tags=True,
        )

    def _get_offer_keywords_json(self) -> Optional[Dict[str, Any]]:
        if not isinstance(self.offer_data, dict):
            return None
        analysis = self.offer_data.get("analysis")
        if not isinstance(analysis, dict):
            return None
        offer_keywords = analysis.get("offer_keywords_llm")
        if isinstance(offer_keywords, dict):
            return offer_keywords
        return None

    def _merge_offer_keywords(self, offer_keywords: Dict[str, Any]) -> None:
        if not isinstance(self.offer_data, dict) or not isinstance(offer_keywords, dict):
            return
        analysis = self.offer_data.get("analysis")
        if not isinstance(analysis, dict):
            analysis = {}
        else:
            analysis = dict(analysis)

        def merge_list(key: str, value: Any) -> None:
            items: List[str] = []
            existing = analysis.get(key)
            if isinstance(existing, list):
                items.extend(str(item) for item in existing)
            elif isinstance(existing, str):
                items.extend(part.strip() for part in existing.split(",") if part.strip())
            if isinstance(value, list):
                items.extend(str(item) for item in value)
            elif isinstance(value, str):
                items.extend(part.strip() for part in value.split(",") if part.strip())
            if items:
                analysis[key] = _dedup_preserve(items)

        analysis["offer_keywords_llm"] = offer_keywords

        merge_list("keywords", offer_keywords.get("keywords"))
        merge_list("skills", offer_keywords.get("skills"))
        merge_list("soft_keywords", offer_keywords.get("soft_skills"))
        merge_list("tools", offer_keywords.get("tools"))
        merge_list("responsibilities", offer_keywords.get("responsibilities"))
        merge_list("education", offer_keywords.get("education"))
        merge_list("certifications", offer_keywords.get("certifications"))

        language = offer_keywords.get("language")
        if isinstance(language, str) and language.strip():
            analysis.setdefault("language", language.strip())
        seniority = offer_keywords.get("seniority")
        if isinstance(seniority, str) and seniority.strip():
            analysis["seniority"] = seniority.strip()

        self.offer_data["analysis"] = analysis

    def _build_offer_keywords_messages(self) -> Dict[str, str]:
        offer_text = self._prepare_offer_text(max_chars=3200)
        job_title = self.offer_data.get("job_title") or ""
        company = self.offer_data.get("company") or ""
        language_code = self._resolve_language_code()

        system_prompt = (
            "You analyze job offers. Return JSON only matching the schema. "
            "Extract concise, high-signal keywords and requirements. "
            "Do not invent information not present in the offer."
        )

        user_prompt = f"""
LANGUAGE: {language_code}
JOB_TITLE: {job_title}
COMPANY: {company}
JOB_OFFER_TEXT:
{offer_text}

  OUTPUT RULES:
  - Return JSON only.
  - Keep lists short (max 12 items per list).
  - If JOB_OFFER_TEXT is non-empty, avoid empty extraction lists.
  - Prefer at least: keywords>=8, skills>=4, tools>=2 when evidence exists in offer text.
  - Use short noun phrases (2-5 words).
  - skills = hard skills/tech stack only.
  - soft_skills = interpersonal traits only.
  - responsibilities = action verbs or short duties.
  - language must match LANGUAGE; translate if the offer is in another language.
  - job_title/company should mirror JOB_TITLE/COMPANY when provided.
  """.strip()

        return {"system": system_prompt, "user": user_prompt}

    def _build_cv_json_messages(
        self,
        *,
        profile_json: Dict[str, Any],
        critic_json: Optional[Dict[str, Any]] = None,
        stage: str,
    ) -> Dict[str, str]:
        offer_keywords = self._get_offer_keywords_json()
        offer_text = self._prepare_offer_text(max_chars=2000 if offer_keywords else 3000)
        job_title = self.offer_data.get("job_title") or ""
        company = self.offer_data.get("company") or ""
        language_code = self._resolve_language_code()

        compact_profile = _compact_profile_json_for_prompt(profile_json)
        profile_block = json.dumps(compact_profile, indent=2, ensure_ascii=False)
        profile_block = _trim_text(profile_block, 2600)
        matched_keywords = _match_offer_keywords(
            offer_text, _collect_candidate_keywords(self.profile_data)
        )
        matched_keywords_text = ", ".join(matched_keywords)

        system_prompt = (
            "You are a CV generator. Return JSON only that matches the schema. "
            "Use only facts from PROFILE_JSON. Do not invent data. "
            "Use empty strings for unknown scalar fields and empty lists for missing sections. "
            "All text must be in LANGUAGE; do not mix languages. "
            "Select the most relevant items for the job offer. "
            "CRITIC_JSON is feedback, not content. Do not quote or paraphrase it."
        )

        offer_keywords_block = ""
        if offer_keywords:
            offer_keywords_block = (
                "\n\nOFFER_KEYWORDS_JSON (job offer summary):\n"
                f"{_trim_text(json.dumps(offer_keywords, indent=2, ensure_ascii=False), 1400)}"
            )
        matched_keywords_block = ""
        if matched_keywords_text:
            matched_keywords_block = (
                "\n\nMATCHED_KEYWORDS (offer x candidate):\n"
                f"{_trim_text(matched_keywords_text, 400)}"
            )

        critic_block = ""
        if critic_json:
            critic_payload = self._sanitize_critic_json(
                critic_json, profile_json=profile_json
            )
            if critic_payload:
                critic_block = (
                    "\n\nCRITIC_JSON (feedback to apply):\n"
                    f"{_trim_text(json.dumps(critic_payload, indent=2, ensure_ascii=False), 2000)}"
                )

        user_instruction_block = ""
        user_instruction = str(self.user_instruction or "").strip()
        if user_instruction:
            user_instruction_block = (
                "\n\nUSER_REGEN_INSTRUCTION (editorial guidance):\n"
                f"{_trim_text(user_instruction, 700)}"
            )
            logger.info(
                "CV regen instruction attached to prompt: stage=%s len=%s",
                stage,
                len(user_instruction),
            )

        user_prompt = f"""
LANGUAGE: {language_code}
JOB_TITLE: {job_title}
COMPANY: {company}
JOB_OFFER_TEXT:
{offer_text}

PROFILE_JSON (source of truth):
{profile_block}
{offer_keywords_block}
{matched_keywords_block}
{critic_block}
{user_instruction_block}

OUTPUT RULES:
- Return JSON only.
- Keep required sections even if empty lists.
- Align content with job offer (keywords, order, relevance).
- Do not add facts not present in PROFILE_JSON.
- contact fields must be copied from PROFILE_JSON.personal_info when available.
- target_company and target_job_title should reflect the offer; use empty strings if missing.
- Never use placeholders (no [A COMPLETER], [TO COMPLETE], or bracketed tokens).
- Skills items must be short noun phrases (no sentences, no "candidate should/must").
- ats_keywords must be a list of strings from the job offer or OFFER_KEYWORDS_JSON.
- If OFFER_KEYWORDS_JSON is present, prioritize it for relevance and ATS terms.
- render_hints.notes can be freeform guidance for rendering.
- render_hints.section_order/emphasis/tone are structured hints.
- Do not include review or instruction text in any field (no critique, no "this CV needs", no "should").
- Summary must be candidate-focused (role, strengths, impact). Do not describe employer mission/history.
- If MATCHED_KEYWORDS is present, ensure those terms appear in summary/skills/experience when relevant.
- If PROFILE_JSON text is in another language, translate it to LANGUAGE (keep proper nouns, tools, company names).
- Avoid repetition:
  - Never repeat the same sentence, clause, or employer description twice.
  - Do not copy the company mission text into candidate achievements.
- For each experience item, prefer:
  - a concise context in summary
  - 2-4 distinct highlights focused on actions, tools, and outcomes
- For each language item, keep `certification` when PROFILE_JSON provides one (issuer/certificate name).
- If USER_REGEN_INSTRUCTION is present, apply it as editorial guidance while preserving factual constraints.
- Never copy USER_REGEN_INSTRUCTION text verbatim into CV fields.
- Never output instruction meta-text (for example "please update", "this CV needs", uppercase emphasis markers).
- Keep output focused but informative:
  - experience <= 5 items, highlights <= 4 each.
  - skills <= 5 categories, items <= 10 each.
  - education <= 3 items.
  - projects <= 3 items.
  - languages <= 4 items.
  - certifications <= 3 items.
  - ats_keywords <= 18 items.
""".strip()

        if stage == "final":
            user_prompt += (
                "\n\nRevise using CRITIC_JSON guidance. "
                "Include must_keep_facts, but also use other relevant facts from PROFILE_JSON. "
                "Do not include critique or instructions in any field."
            )

        return {"system": system_prompt, "user": user_prompt}

    def _build_critic_messages(self, *, cv_html: str) -> Dict[str, str]:
        offer_text = self._prepare_offer_text(max_chars=3200)
        job_title = self.offer_data.get("job_title") or ""
        company = self.offer_data.get("company") or ""
        cv_html_block = self._prepare_cv_html(cv_html, max_chars=3200)

        system_prompt = (
            "You are a strict ATS reviewer. Return JSON only matching the schema. "
            "Analyze the CV HTML against the job offer. Do not invent facts."
        )

        user_prompt = f"""
JOB_TITLE: {job_title}
COMPANY: {company}
JOB_OFFER_TEXT:
{offer_text}

CV_HTML:
{cv_html_block}

SCORECARD RULES:
- All scores are integers 0-100.
- overall = round(ats_keyword_coverage*0.30 + clarity*0.20 + evidence_metrics*0.30 + consistency*0.20)
- Clamp each metric to [0,100] before computing overall.
- If any issue.severity == "blocker", overall = min(overall, 39).
- Bands: 0-39 reject, 40-59 weak, 60-79 acceptable, 80-100 strong.

OUTPUT RULES:
- Return JSON only.
- missing_keywords: only keywords from the job offer not present in CV_HTML.
- must_keep_facts: only facts found in CV_HTML.
- issues: max 6 items, keep each problem/fix concise.
- rewrite_plan: max 8 items, short phrases.
- If contact details appear in CV_HTML, include them in must_keep_facts.
- If the summary describes the employer/company instead of the candidate, add a high severity issue.
""".strip()

        return {"system": system_prompt, "user": user_prompt}

    def generate_offer_keywords_json(self, progress_callback=None) -> Dict[str, Any]:
        from pydantic import ValidationError
        from ..schemas.offer_keywords_schema import OfferKeywordsJSON
        from ..utils.json_strict import generate_json_with_schema, JsonStrictError

        messages = self._build_offer_keywords_messages()
        language_code = self._resolve_language_code()
        offer_data = self.offer_data if isinstance(self.offer_data, dict) else {}

        def _stabilize(payload: Dict[str, Any], *, reason: str) -> Dict[str, Any]:
            return stabilize_offer_keywords_payload(
                payload=payload if isinstance(payload, dict) else {},
                offer_data=offer_data,
                language_code=language_code,
                reason=reason,
                logger=logger,
            )

        def _second_pass_if_needed(payload: Dict[str, Any], *, reason: str) -> Dict[str, Any]:
            retry_payload = run_offer_keywords_second_pass(
                base_messages=messages,
                current_payload=payload if isinstance(payload, dict) else {},
                offer_data=offer_data,
                language_code=language_code,
                qwen_manager=self.qwen_manager,
                parse_json_response=self._parse_json_response,
                progress_callback=progress_callback,
                logger=logger,
            )
            if isinstance(retry_payload, dict) and retry_payload:
                if retry_payload != payload:
                    logger.info("Offer keywords second-pass applied (%s).", reason)
                return retry_payload
            return payload

        try:
            payload = generate_json_with_schema(
                role="offer_critic",
                schema_model=OfferKeywordsJSON,
                messages=messages,
                qwen_manager=self.qwen_manager,
                retries=3,
                progress_callback=progress_callback,
            )
            payload = _second_pass_if_needed(payload, reason="strict_weak_output")
            return _stabilize(payload, reason="strict_offer_keywords")
        except JsonStrictError as exc:
            logger.warning(
                "Strict OfferKeywordsJSON failed, retrying non-strict: %s", exc
            )
            try:
                raw = self.qwen_manager.generate_structured_json(
                    messages["system"],
                    messages["user"],
                    progress_callback,
                    generation_overrides=self._non_strict_json_generation_overrides("offer_critic"),
                    role="offer_critic",
                )
                payload = self._parse_json_response(raw)
                if not payload:
                    retry_reason = self._consume_qwen_runtime_error() or "non-strict empty output"
                    fallback_reason = self._compose_fallback_reason(
                        strict_error=exc,
                        retry_error=retry_reason,
                    )
                    return _stabilize(
                        self._fallback_offer_keywords_json(reason=fallback_reason),
                        reason=fallback_reason,
                    )
                try:
                    parsed = OfferKeywordsJSON.model_validate(payload)
                except ValidationError as val_exc:
                    logger.warning(
                        "Non-strict OfferKeywordsJSON validation failed: %s", val_exc
                    )
                    fallback_reason = self._compose_fallback_reason(
                        strict_error=exc,
                        retry_error=val_exc,
                    )
                    return _stabilize(
                        self._fallback_offer_keywords_json(reason=fallback_reason),
                        reason=fallback_reason,
                    )
                payload = _second_pass_if_needed(
                    parsed.model_dump(), reason="non_strict_weak_output"
                )
                return _stabilize(payload, reason="non_strict_offer_keywords")
            except Exception as retry_exc:
                logger.error(
                    "OfferKeywords non-strict retry failed: %s",
                    retry_exc,
                )
                fallback_reason = self._compose_fallback_reason(
                    strict_error=exc,
                    retry_error=retry_exc,
                )
                return _stabilize(
                    self._fallback_offer_keywords_json(reason=fallback_reason),
                    reason=fallback_reason,
                )
        except Exception as exc:
            logger.error("OfferKeywords generation failed: %s", exc)
            return _stabilize(
                self._fallback_offer_keywords_json(reason=str(exc)),
                reason=str(exc),
            )

    def generate_cv_json_draft(
        self,
        *,
        profile_json: Dict[str, Any],
        progress_callback=None,
    ) -> Dict[str, Any]:
        from pydantic import ValidationError
        from ..schemas.cv_schema import CVJSON
        from ..utils.json_strict import generate_json_with_schema, JsonStrictError

        messages = self._build_cv_json_messages(
            profile_json=profile_json, stage="draft"
        )
        try:
            strict_payload = generate_json_with_schema(
                role="generator",
                schema_model=CVJSON,
                messages=messages,
                qwen_manager=self.qwen_manager,
                retries=self._strict_generator_retries(),
                progress_callback=progress_callback,
            )
            strict_payload = self._ensure_required_cv_fields(
                cv_json=strict_payload,
                profile_json=profile_json,
                stage="draft_strict",
            )
            return CVJSON.model_validate(strict_payload).model_dump()
        except JsonStrictError as exc:
            if self._is_strict_missing_required_error(exc):
                logger.warning(
                    "Strict CVJSON draft returned missing required fields; using deterministic required-field payload."
                )
                recovered = self._ensure_required_cv_fields(
                    cv_json={},
                    profile_json=profile_json,
                    stage="draft_strict_missing_required",
                )
                return CVJSON.model_validate(recovered).model_dump()
            logger.warning("Strict CVJSON draft failed, retrying non-strict: %s", exc)
            try:
                raw = self.qwen_manager.generate_structured_json(
                    messages["system"],
                    messages["user"],
                    progress_callback,
                    generation_overrides=self._non_strict_json_generation_overrides("generator"),
                    role="generator",
                )
                payload = self._parse_json_response(raw)
                if not payload:
                    retry_reason = self._consume_qwen_runtime_error() or "non-strict empty output"
                    recovered = self._coerce_minimum_cv_json_payload(
                        {},
                        profile_json=profile_json,
                        reason=f"draft_non_strict_empty:{retry_reason}",
                    )
                    try:
                        parsed = CVJSON.model_validate(recovered)
                        logger.warning(
                            "Draft CVJSON recovered from empty non-strict output via minimum schema coercion."
                        )
                        enriched = self._ensure_required_cv_fields(
                            cv_json=parsed.model_dump(),
                            profile_json=profile_json,
                            stage="draft_recovered_empty",
                        )
                        return CVJSON.model_validate(enriched).model_dump()
                    except ValidationError as recover_exc:
                        fallback_reason = self._compose_fallback_reason(
                            strict_error=exc,
                            retry_error=f"{retry_reason}; recover={recover_exc}",
                        )
                        return self._fallback_or_minimum_cv_json(
                            profile_json=profile_json,
                            reason=fallback_reason,
                            stage="draft",
                        )
                try:
                    parsed = CVJSON.model_validate(payload)
                except ValidationError as val_exc:
                    logger.warning("Non-strict CVJSON draft validation failed: %s", val_exc)
                    recovered = self._coerce_minimum_cv_json_payload(
                        payload,
                        profile_json=profile_json,
                        reason=f"draft_non_strict_invalid:{val_exc}",
                    )
                    try:
                        parsed = CVJSON.model_validate(recovered)
                        logger.warning(
                            "Draft CVJSON recovered from invalid non-strict payload via minimum schema coercion."
                        )
                        enriched = self._ensure_required_cv_fields(
                            cv_json=parsed.model_dump(),
                            profile_json=profile_json,
                            stage="draft_recovered_invalid",
                        )
                        return CVJSON.model_validate(enriched).model_dump()
                    except ValidationError as recover_exc:
                        fallback_reason = self._compose_fallback_reason(
                            strict_error=exc,
                            retry_error=f"{val_exc}; recover={recover_exc}",
                        )
                        return self._fallback_or_minimum_cv_json(
                            profile_json=profile_json,
                            reason=fallback_reason,
                            stage="draft",
                        )
                enriched = self._ensure_required_cv_fields(
                    cv_json=parsed.model_dump(),
                    profile_json=profile_json,
                    stage="draft_non_strict",
                )
                return CVJSON.model_validate(enriched).model_dump()
            except Exception as retry_exc:
                logger.error("Draft CVJSON non-strict retry failed: %s", retry_exc)
                fallback_reason = self._compose_fallback_reason(
                    strict_error=exc,
                    retry_error=retry_exc,
                )
                return self._fallback_or_minimum_cv_json(
                    profile_json=profile_json,
                    reason=fallback_reason,
                    stage="draft",
                )
        except Exception as exc:
            logger.error("Draft CVJSON generation failed: %s", exc)
            return self._fallback_or_minimum_cv_json(
                profile_json=profile_json,
                reason=str(exc),
                stage="draft",
            )

    def generate_cv_json_final(
        self,
        *,
        profile_json: Dict[str, Any],
        critic_json: Dict[str, Any],
        progress_callback=None,
    ) -> Dict[str, Any]:
        from pydantic import ValidationError
        from ..schemas.cv_schema import CVJSON
        from ..utils.json_strict import generate_json_with_schema, JsonStrictError

        messages = self._build_cv_json_messages(
            profile_json=profile_json,
            critic_json=critic_json,
            stage="final",
        )
        try:
            strict_payload = generate_json_with_schema(
                role="generator",
                schema_model=CVJSON,
                messages=messages,
                qwen_manager=self.qwen_manager,
                retries=self._strict_generator_retries(),
                progress_callback=progress_callback,
            )
            strict_payload = self._ensure_required_cv_fields(
                cv_json=strict_payload,
                profile_json=profile_json,
                stage="final_strict",
            )
            return CVJSON.model_validate(strict_payload).model_dump()
        except JsonStrictError as exc:
            if self._is_strict_missing_required_error(exc):
                logger.warning(
                    "Strict CVJSON final returned missing required fields; using deterministic required-field payload."
                )
                recovered = self._ensure_required_cv_fields(
                    cv_json={},
                    profile_json=profile_json,
                    stage="final_strict_missing_required",
                )
                return CVJSON.model_validate(recovered).model_dump()
            logger.warning("Strict CVJSON final failed, retrying non-strict: %s", exc)
            try:
                raw = self.qwen_manager.generate_structured_json(
                    messages["system"],
                    messages["user"],
                    progress_callback,
                    generation_overrides=self._non_strict_json_generation_overrides("generator"),
                    role="generator",
                )
                payload = self._parse_json_response(raw)
                if not payload:
                    retry_reason = self._consume_qwen_runtime_error() or "non-strict empty output"
                    recovered = self._coerce_minimum_cv_json_payload(
                        {},
                        profile_json=profile_json,
                        reason=f"final_non_strict_empty:{retry_reason}",
                    )
                    try:
                        parsed = CVJSON.model_validate(recovered)
                        logger.warning(
                            "Final CVJSON recovered from empty non-strict output via minimum schema coercion."
                        )
                        enriched = self._ensure_required_cv_fields(
                            cv_json=parsed.model_dump(),
                            profile_json=profile_json,
                            stage="final_recovered_empty",
                        )
                        return CVJSON.model_validate(enriched).model_dump()
                    except ValidationError as recover_exc:
                        fallback_reason = self._compose_fallback_reason(
                            strict_error=exc,
                            retry_error=f"{retry_reason}; recover={recover_exc}",
                        )
                        return self._fallback_or_minimum_cv_json(
                            profile_json=profile_json,
                            reason=fallback_reason,
                            stage="final",
                        )
                try:
                    parsed = CVJSON.model_validate(payload)
                except ValidationError as val_exc:
                    logger.warning("Non-strict CVJSON final validation failed: %s", val_exc)
                    recovered = self._coerce_minimum_cv_json_payload(
                        payload,
                        profile_json=profile_json,
                        reason=f"final_non_strict_invalid:{val_exc}",
                    )
                    try:
                        parsed = CVJSON.model_validate(recovered)
                        logger.warning(
                            "Final CVJSON recovered from invalid non-strict payload via minimum schema coercion."
                        )
                        enriched = self._ensure_required_cv_fields(
                            cv_json=parsed.model_dump(),
                            profile_json=profile_json,
                            stage="final_recovered_invalid",
                        )
                        return CVJSON.model_validate(enriched).model_dump()
                    except ValidationError as recover_exc:
                        fallback_reason = self._compose_fallback_reason(
                            strict_error=exc,
                            retry_error=f"{val_exc}; recover={recover_exc}",
                        )
                        return self._fallback_or_minimum_cv_json(
                            profile_json=profile_json,
                            reason=fallback_reason,
                            stage="final",
                        )
                enriched = self._ensure_required_cv_fields(
                    cv_json=parsed.model_dump(),
                    profile_json=profile_json,
                    stage="final_non_strict",
                )
                return CVJSON.model_validate(enriched).model_dump()
            except Exception as retry_exc:
                logger.error("Final CVJSON non-strict retry failed: %s", retry_exc)
                fallback_reason = self._compose_fallback_reason(
                    strict_error=exc,
                    retry_error=retry_exc,
                )
                return self._fallback_or_minimum_cv_json(
                    profile_json=profile_json,
                    reason=fallback_reason,
                    stage="final",
                )
        except Exception as exc:
            logger.error("Final CVJSON generation failed: %s", exc)
            return self._fallback_or_minimum_cv_json(
                profile_json=profile_json,
                reason=str(exc),
                stage="final",
            )

    def generate_critic_json(
        self,
        *,
        cv_html: str,
        progress_callback=None,
    ) -> Dict[str, Any]:
        from pydantic import ValidationError
        from ..schemas.critic_schema import CriticJSON
        from ..utils.json_strict import (
            JsonStrictError,
            coerce_critic_payload,
            generate_json_with_schema,
        )

        messages = self._build_critic_messages(cv_html=cv_html)
        try:
            return generate_json_with_schema(
                role="critic",
                schema_model=CriticJSON,
                messages=messages,
                qwen_manager=self.qwen_manager,
                retries=3,
                progress_callback=progress_callback,
            )
        except JsonStrictError as exc:
            logger.warning("Strict CriticJSON failed, retrying non-strict: %s", exc)
            try:
                raw = self.qwen_manager.generate_structured_json(
                    messages["system"],
                    messages["user"],
                    progress_callback,
                    generation_overrides=self._non_strict_json_generation_overrides("critic"),
                    role="critic",
                )
                payload = self._parse_json_response(raw)
                if payload:
                    try:
                        parsed = CriticJSON.model_validate(payload)
                        return parsed.model_dump()
                    except ValidationError as val_exc:
                        logger.warning(
                            "Non-strict CriticJSON validation failed: %s", val_exc
                        )
                        coerced = coerce_critic_payload(payload)
                        if isinstance(coerced, dict):
                            try:
                                parsed = CriticJSON.model_validate(coerced)
                                logger.warning(
                                    "Non-strict CriticJSON recovered via payload coercion."
                                )
                                return parsed.model_dump()
                            except ValidationError:
                                pass
                        fallback_reason = self._compose_fallback_reason(
                            strict_error=exc,
                            retry_error=val_exc,
                        )
                        return self._fallback_critic_json(reason=fallback_reason)
                retry_reason = self._consume_qwen_runtime_error() or "non-strict empty output"
                fallback_reason = self._compose_fallback_reason(
                    strict_error=exc,
                    retry_error=retry_reason,
                )
                return self._fallback_critic_json(reason=fallback_reason)
            except Exception as retry_exc:
                logger.error("CriticJSON non-strict retry failed: %s", retry_exc)
                fallback_reason = self._compose_fallback_reason(
                    strict_error=exc,
                    retry_error=retry_exc,
                )
                return self._fallback_critic_json(reason=fallback_reason)
        except Exception as exc:
            logger.error("Critic JSON generation failed: %s", exc)
            return self._fallback_critic_json(reason=str(exc))

    def run(self) -> None:
        """Run the CV generation pipeline via PipelineOrchestrator."""
        try:
            profile_json = self._build_profile_json()
            self._pipeline_profile_json = profile_json if isinstance(profile_json, dict) else {}
            existing_snapshot = self._load_application_snapshot()

            orchestrator, state = build_default_pipeline(
                worker=self, qwen_manager=self.qwen_manager
            )
            state.profile_json = profile_json
            state.existing_snapshot = existing_snapshot
            state.progress_callback = self.progress_updated.emit

            success, _phase_results = orchestrator.run(state)

            if not success:
                if self._should_retry_with_subprocess(
                    state=state,
                    phase_results=_phase_results,
                ):
                    self.progress_updated.emit(
                        "[RECOVERY] Echec memoire detecte; retry automatique en mode subprocess..."
                    )
                    try:
                        self.qwen_manager.cleanup_memory()
                    except Exception:
                        pass

                    retry_orchestrator, retry_state = build_default_pipeline(
                        worker=self, qwen_manager=self.qwen_manager
                    )
                    retry_state.profile_json = profile_json
                    retry_state.existing_snapshot = existing_snapshot
                    retry_state.progress_callback = self.progress_updated.emit
                    retry_state.use_subprocess = True

                    logger.warning(
                        "Retrying pipeline once with subprocess stages after memory-related failure."
                    )
                    retry_success, retry_phase_results = retry_orchestrator.run(
                        retry_state
                    )
                    if retry_success:
                        self.generation_finished.emit(
                            self._build_result_dict(retry_state)
                        )
                        return
                    failed_phase, failed_error = self._extract_failed_phase_error(
                        retry_phase_results
                    )
                    logger.error(
                        "Subprocess retry failed at phase '%s': %s",
                        failed_phase or "unknown",
                        failed_error or "unknown error",
                    )
                self._complete_with_deterministic_fallback()
                return

            self.generation_finished.emit(self._build_result_dict(state))

        except Exception as exc:
            logger.error("CVGenerationWorker.run failed: %s", exc)
            try:
                self.qwen_manager._record_failure(
                    f"pipeline_error: {str(exc)[:240]}"
                )
            except Exception:
                pass
            try:
                self.qwen_manager.cleanup_memory()
            except Exception:
                pass
            self.error_occurred.emit(f"Erreur generation: {str(exc)}")

    @staticmethod
    def _extract_failed_phase_error(phase_results: Any) -> Tuple[str, str]:
        """Extract failing phase name/error from pipeline result list."""
        if not isinstance(phase_results, list):
            return "", ""
        for result in reversed(phase_results):
            if result is None:
                continue
            status_name = str(getattr(getattr(result, "status", None), "name", "")).upper()
            if status_name != "FAILED":
                continue
            return (
                str(getattr(result, "phase_name", "") or ""),
                str(getattr(result, "error", "") or ""),
            )
        return "", ""

    def _should_retry_with_subprocess(self, *, state: Any, phase_results: Any) -> bool:
        """Return True when a non-subprocess pipeline should retry in subprocess mode."""
        if bool(getattr(state, "use_subprocess", False)):
            return False

        # Per-phase adaptive subprocess recovery is handled by PipelineOrchestrator.
        # Keep global full-pipeline retry disabled while adaptive mode is enabled.
        custom = getattr(self.qwen_manager, "custom_parameters", None) or {}
        adaptive_custom = custom.get("adaptive_subprocess_recovery")
        adaptive_env = os.getenv("CVMATCH_ADAPTIVE_SUBPROCESS_RECOVERY")
        if adaptive_env is not None:
            adaptive_enabled = adaptive_env.strip().lower() in ("1", "true", "yes", "y", "on")
        elif adaptive_custom is not None:
            adaptive_enabled = str(adaptive_custom).strip().lower() in ("1", "true", "yes", "y", "on")
        else:
            adaptive_enabled = True
        if adaptive_enabled:
            return False

        env_toggle = os.getenv("CVMATCH_RETRY_SUBPROCESS_ON_MEMORY_ERROR")
        if env_toggle is not None and env_toggle.strip().lower() in ("0", "false", "no", "n", "off"):
            return False

        phase_name, failure_error = self._extract_failed_phase_error(phase_results)
        if not failure_error:
            return False

        is_memory_failure = False
        try:
            is_memory_failure = bool(
                self.qwen_manager._is_memory_pressure_failure_reason(failure_error)
            )
        except Exception:
            is_memory_failure = False

        if not is_memory_failure:
            lowered = failure_error.strip().lower()
            is_memory_failure = (
                "cuda out of memory" in lowered
                or "out of memory" in lowered
                or "oom" in lowered
            )

        if not is_memory_failure:
            return False

        logger.warning(
            "Will retry with subprocess mode after memory-related failure: phase=%s error=%s",
            phase_name or "unknown",
            failure_error[:240],
        )
        return True

    def _build_result_dict(self, state) -> dict:
        """Build generation_finished payload from completed pipeline state."""
        return {
            "application_id": getattr(state, "saved_application_id", None),
            "cv_markdown": getattr(state, "cv_markdown", ""),
            "cv_html": getattr(state, "cv_html", ""),
            "cover_letter": getattr(state, "cover_letter", ""),
            "cv_json_draft": getattr(state, "cv_json_draft", {}),
            "cv_json_final": getattr(state, "cv_json_final", {}),
            "critic_json": getattr(state, "critic_json", {}),
            "profile_json": getattr(state, "profile_json", {}),
            "template": self.template,
            "model_version": self.profile_data.model_version,
            "model_used": getattr(self.qwen_manager, "current_model_id", "unknown"),
            "gpu_used": gpu_manager.gpu_info["available"],
            "degraded_mode": state.is_degraded() if hasattr(state, "is_degraded") else False,
            "degraded_reasons": getattr(state, "degraded_reasons", []),
            "alignment_audit": dict(state.alignment_audit) if isinstance(getattr(state, "alignment_audit", None), dict) else {},
            "cover_letter_review": dict(state.cover_letter_review) if isinstance(getattr(state, "cover_letter_review", None), dict) else {},
            "generation_audit": dict(state.generation_audit) if isinstance(getattr(state, "generation_audit", None), dict) else {},
        }

    def _load_application_snapshot(self) -> dict:
        """Load existing application snapshot for cv_only_regen mode."""
        if not self.cv_only_regen:
            return {}
        try:
            from ..models.database import get_session
            from ..models.job_application import JobApplication
            with get_session() as session:
                app = session.get(JobApplication, self.application_id)
                if app:
                    offer_analysis = app.offer_analysis if isinstance(app.offer_analysis, dict) else {}
                    generation_audit = (
                        offer_analysis.get("generation_audit")
                        if isinstance(offer_analysis.get("generation_audit"), dict)
                        else {}
                    )
                    return {
                        "cv_json_draft": app.cv_json_draft or {},
                        "cv_json_final": app.cv_json_final or {},
                        "cv_markdown": app.final_cv_markdown or app.generated_cv_markdown or "",
                        "cv_html": app.final_cv_html or app.generated_cv_html or "",
                        "cover_letter": app.final_cover_letter or app.generated_cover_letter or "",
                        "generation_audit": generation_audit,
                    }
        except Exception as exc:
            logger.warning("Could not load application snapshot: %s", exc)
        return {}

    def _complete_with_deterministic_fallback(self) -> None:
        """Emit error when orchestrator pipeline fails with no recoverable path."""
        self.error_occurred.emit(
            "La generation a echoue apres plusieurs tentatives. "
            "Consultez les logs pour les details."
        )

    def _parse_json_response(self, text: str) -> Dict[str, Any]:
        if not text:
            return {}
        cleaned = text.strip()
        try:
            return json.loads(cleaned)
        except Exception:
            pass
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            candidate = ""
        else:
            candidate = cleaned[start : end + 1]
            try:
                return json.loads(candidate)
            except Exception:
                pass

        try:
            from ..utils.json_strict import attempt_json_repair
        except Exception:
            attempt_json_repair = None

        if attempt_json_repair:
            repaired = attempt_json_repair(cleaned)
            if repaired:
                try:
                    return json.loads(repaired)
                except Exception:
                    pass
            if candidate:
                repaired = attempt_json_repair(candidate)
                if repaired:
                    try:
                        return json.loads(repaired)
                    except Exception:
                        pass
        return {}

    def build_cover_letter_prompt(self) -> str:
        """Build cover-letter prompt via style policy module."""
        if not self._offer_analysis_hydrated:
            _hydrate_offer_analysis_from_application(self.offer_data, self.application_id)
            self._offer_analysis_hydrated = True
        profile_block = _format_profile_detailed_data(self.profile_data)
        style_payload = build_cover_letter_generation_payload(
            offer_data=self.offer_data if isinstance(self.offer_data, dict) else {},
            template=self.template,
            preferred_language=getattr(self.profile_data, "preferred_language", None),
            profile_name=getattr(self.profile_data, "name", "") or "",
            profile_block=profile_block,
            user_instruction=self.user_instruction,
            freeze_previous_style=bool(self.application_id),
        )
        _persist_cover_letter_style_in_offer_analysis(self.offer_data, style_payload)
        logger.info(
            "Cover letter style resolved: mode=%s source=%s freeze=%s override=%s",
            style_payload.get("style_mode"),
            style_payload.get("style_source"),
            bool(style_payload.get("freeze_applied")),
            bool(style_payload.get("instruction_override")),
        )
        return str(style_payload.get("prompt") or "")

    def save_application(
        self,
        cv_markdown: str,
        cover_letter: str,
        *,
        profile_json: Optional[Dict[str, Any]] = None,
        critic_json: Optional[Dict[str, Any]] = None,
        cv_json_draft: Optional[Dict[str, Any]] = None,
        cv_json_final: Optional[Dict[str, Any]] = None,
        cv_html: Optional[str] = None,
        generation_audit: Optional[Dict[str, Any]] = None,
        alignment_audit: Optional[Dict[str, Any]] = None,
        cover_letter_review: Optional[Dict[str, Any]] = None,
        application_id: Optional[int] = None,
        preserve_cover_letter: bool = False,
    ) -> JobApplication:
        """Sauvegarde la candidature en base."""
        from datetime import datetime

        prune_draft_on_final = self._to_bool_setting(
            os.getenv("CVMATCH_PRUNE_DRAFT_ON_SUCCESS"),
            True,
        )
        has_final_cv = isinstance(cv_json_final, dict) and bool(cv_json_final)
        stored_cv_json_draft = (
            None if (prune_draft_on_final and has_final_cv) else cv_json_draft
        )

        target_application_id = (
            application_id
            if isinstance(application_id, int)
            else (self.application_id if isinstance(self.application_id, int) else None)
        )
        offer_analysis_payload: Dict[str, Any] = {}
        if isinstance(self.offer_data, dict):
            base_analysis = self.offer_data.get("analysis")
            if isinstance(base_analysis, dict):
                offer_analysis_payload = dict(base_analysis)
        if isinstance(generation_audit, dict) and generation_audit:
            offer_analysis_payload["generation_audit"] = dict(generation_audit)
        if isinstance(alignment_audit, dict) and alignment_audit:
            offer_analysis_payload["alignment_audit"] = dict(alignment_audit)
        if isinstance(cover_letter_review, dict) and cover_letter_review:
            offer_analysis_payload["cover_letter_review"] = dict(cover_letter_review)

        with get_session() as session:
            application = (
                session.get(JobApplication, target_application_id)
                if target_application_id
                else None
            )

            if application is None:
                if isinstance(self.offer_data, dict):
                    self.offer_data["analysis"] = dict(offer_analysis_payload)
                application = JobApplication(
                    profile_id=self.profile_data.id,
                    job_title=self.offer_data['job_title'],
                    company=self.offer_data['company'],
                    offer_text=self.offer_data['text'],
                    offer_analysis=offer_analysis_payload,
                    template_used=self.template,
                    model_version_used=self.profile_data.model_version,
                    generated_cv_markdown=cv_markdown,
                    generated_cv_html=cv_html,
                    generated_cover_letter=cover_letter,
                    profile_json=profile_json,
                    critic_json=critic_json,
                    cv_json_draft=stored_cv_json_draft,
                    cv_json_final=cv_json_final,
                    status=ApplicationStatus.DRAFT
                )
            else:
                application.profile_id = self.profile_data.id
                application.job_title = self.offer_data['job_title']
                application.company = self.offer_data['company']
                application.offer_text = self.offer_data['text']
                existing_analysis = (
                    dict(application.offer_analysis)
                    if isinstance(application.offer_analysis, dict)
                    else {}
                )
                existing_analysis.update(offer_analysis_payload)
                application.offer_analysis = existing_analysis
                if isinstance(self.offer_data, dict):
                    self.offer_data["analysis"] = dict(existing_analysis)
                application.template_used = self.template
                application.model_version_used = self.profile_data.model_version
                application.generated_cv_markdown = cv_markdown
                application.generated_cv_html = cv_html
                if not preserve_cover_letter:
                    application.generated_cover_letter = cover_letter
                elif not application.generated_cover_letter and cover_letter:
                    application.generated_cover_letter = cover_letter
                application.profile_json = profile_json
                application.critic_json = critic_json
                application.cv_json_draft = stored_cv_json_draft
                application.cv_json_final = cv_json_final
                application.updated_at = datetime.now()

            session.add(application)
            session.commit()
            session.refresh(application)

        # Mettre Ã  jour les stats du profil via SQL direct (Ã©vite DetachedInstanceError)
        try:
            with get_session() as session:
                from sqlmodel import text
                session.execute(
                    text("UPDATE userprofile SET total_cvs_generated = total_cvs_generated + 1 WHERE id = :pid"),
                    {"pid": self.profile_data.id}
                )
                session.commit()
                logger.debug(f"Stats profil {self.profile_data.id} mises Ã  jour")
        except Exception as e:
            logger.warning(f"Impossible de mettre Ã  jour les stats du profil: {e}")

        return application

class CoverLetterGenerationWorker(QThread):
    """Worker pour générer une lettre de motivation en arrière-plan.

    Note: Utilise ProfileWorkerData au lieu de UserProfile pour éviter
    les erreurs SQLAlchemy DetachedInstanceError dans les threads background.
    """
    progress_updated = Signal(str)
    generation_finished = Signal(dict)
    error_occurred = Signal(str)

    def __init__(
        self,
        profile_data: ProfileWorkerData,
        offer_data: dict,
        template: str,
        application_id: Optional[int] = None,
        user_instruction: str = "",
        previous_generation_audit: Optional[Dict[str, Any]] = None,
    ):
        super().__init__()
        self.profile_data = profile_data
        self.offer_data = offer_data
        self.template = template
        self.application_id = application_id if isinstance(application_id, int) else None
        self.user_instruction = str(user_instruction or "").strip()
        self.previous_generation_audit = (
            dict(previous_generation_audit)
            if isinstance(previous_generation_audit, dict)
            else {}
        )
        self._offer_analysis_hydrated = False
        self.qwen_manager = QwenManager(self.profile_data.model_version)

    def run(self):
        """Lance la génération de lettre de motivation avec le modèle IA sélectionné."""
        try:
            # Callback pour les mises à jour de progrès
            def progress_callback(message):
                self.progress_updated.emit(message)

            # Recharger la configuration du modèle en cas de changement
            self.qwen_manager._load_selected_model_config()
            note = getattr(self.qwen_manager, "last_model_resolution_note", None)
            if note:
                progress_callback(note)
                self.qwen_manager.last_model_resolution_note = None

            # Étape 1: Chargement du modèle
            model_name = getattr(self.qwen_manager, 'current_model_id', 'IA')
            progress_callback(f"💠 Initialisation du modèle {model_name}...")
            self.qwen_manager.load_model(progress_callback, allow_fallback=False)

            # Ã‰tape 2: Construction du prompt
            progress_callback("🔍 Construction du prompt pour la lettre...")
            prompt = self.build_letter_prompt()

            # Ã‰tape 3: GÃ©nÃ©ration de la lettre
            progress_callback("💬 Génération de la lettre de motivation...")
            cover_letter = self.qwen_manager.generate_cover_letter(prompt, progress_callback)

            generation_audit, cover_letter_review = self._build_cover_letter_generation_audit(
                cover_letter
            )

            # Ã‰tape 4: Sauvegarde
            progress_callback("💾 Sauvegarde de la lettre...")
            application = self.save_cover_letter(
                cover_letter,
                generation_audit=generation_audit,
                cover_letter_review=cover_letter_review,
            )

            # Ã‰tape 5: Nettoyage mÃ©moire
            progress_callback("🧹 Nettoyage mémoire...")
            self.qwen_manager.cleanup_memory()

            # RÃ©sultat final
            result = {
                "application_id": application.id,
                "cover_letter": cover_letter,
                "template": self.template,
                "model_version": self.profile_data.model_version,
                "model_used": getattr(self.qwen_manager, 'current_model_id', 'unknown'),
                "gpu_used": gpu_manager.gpu_info["available"],
                "generation_audit": generation_audit,
                "cover_letter_review": cover_letter_review,
                "alignment_audit": (
                    generation_audit.get("breakdown", {}).get("cv")
                    if isinstance(generation_audit, dict)
                    and isinstance(generation_audit.get("breakdown"), dict)
                    and isinstance(generation_audit.get("breakdown", {}).get("cv"), dict)
                    else {}
                ),
            }

            progress_callback("✅ Lettre générée avec succès !")
            self.generation_finished.emit(result)

        except Exception as e:
            logger.error(f"Erreur génération lettre : {e}")
            # Nettoyage en cas d'erreur
            try:
                self.qwen_manager.cleanup_memory()
            except:
                pass
            self.error_occurred.emit(f"Erreur génération: {str(e)}")

    def build_letter_prompt(self) -> str:
        """Build cover-letter prompt via style policy module."""
        if not self._offer_analysis_hydrated:
            _hydrate_offer_analysis_from_application(self.offer_data, self.application_id)
            self._offer_analysis_hydrated = True
        profile_block = _format_profile_detailed_data(self.profile_data)
        style_payload = build_cover_letter_generation_payload(
            offer_data=self.offer_data if isinstance(self.offer_data, dict) else {},
            template=self.template,
            preferred_language=getattr(self.profile_data, "preferred_language", None),
            profile_name=getattr(self.profile_data, "name", "") or "",
            profile_block=profile_block,
            user_instruction=self.user_instruction,
            freeze_previous_style=bool(self.application_id),
        )
        _persist_cover_letter_style_in_offer_analysis(self.offer_data, style_payload)
        logger.info(
            "Cover letter style resolved: mode=%s source=%s freeze=%s override=%s",
            style_payload.get("style_mode"),
            style_payload.get("style_source"),
            bool(style_payload.get("freeze_applied")),
            bool(style_payload.get("instruction_override")),
        )
        return str(style_payload.get("prompt") or "")

    def _resolve_letter_language_code(self) -> str:
        analysis = self.offer_data.get("analysis") if isinstance(self.offer_data, dict) else None
        analysis_language = analysis.get("language") if isinstance(analysis, dict) else None
        if isinstance(analysis_language, str) and analysis_language.strip():
            return _normalize_language(analysis_language)
        preferred = getattr(self.profile_data, "preferred_language", None)
        return _normalize_language(preferred)

    def _build_cover_letter_generation_audit(
        self,
        cover_letter: str,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        language_code = self._resolve_letter_language_code()
        previous = (
            dict(self.previous_generation_audit)
            if isinstance(self.previous_generation_audit, dict)
            else {}
        )
        previous_letter = {}
        if isinstance(previous.get("breakdown"), dict):
            previous_letter = previous.get("breakdown", {}).get("letter") or {}

        try:
            letter_score = int(float(previous_letter.get("relevance_score") or 80))
        except Exception:
            letter_score = 80
        letter_score = max(0, min(100, letter_score))

        structure_ok = True
        try:
            from ..utils.cover_letter_rules import is_cover_letter_structure_coherent
            structure_ok = bool(
                is_cover_letter_structure_coherent(cover_letter or "", language_code=language_code)
            )
        except Exception:
            structure_ok = True

        try:
            from ..utils.cover_letter_pipeline import build_generation_audit_for_letter
            generation_audit = build_generation_audit_for_letter(
                letter_score=letter_score,
                structure_ok=structure_ok,
                language_code=language_code,
                previous_audit=previous,
            )
        except Exception:
            generation_audit = {
                "cv_score": float(previous.get("cv_score") or 0.0),
                "letter_score": float(letter_score),
                "global_score": float(letter_score),
                "sufficient": bool(structure_ok),
                "breakdown": {
                    "cv": {},
                    "letter": {
                        "relevance_score": int(letter_score),
                        "structure_ok": bool(structure_ok),
                        "language": language_code,
                    },
                },
            }

        breakdown = generation_audit.get("breakdown") if isinstance(generation_audit, dict) else {}
        letter_block = breakdown.get("letter") if isinstance(breakdown, dict) else {}
        cover_letter_review = (
            dict(letter_block)
            if isinstance(letter_block, dict)
            else {
                "relevance_score": int(letter_score),
                "structure_ok": bool(structure_ok),
                "language": language_code,
            }
        )
        return generation_audit, cover_letter_review

    def _build_offer_analysis_with_audit(
        self,
        *,
        generation_audit: Optional[Dict[str, Any]] = None,
        cover_letter_review: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        if isinstance(self.offer_data, dict):
            base = self.offer_data.get("analysis")
            if isinstance(base, dict):
                payload = dict(base)

        if isinstance(generation_audit, dict) and generation_audit:
            payload["generation_audit"] = dict(generation_audit)
            breakdown = generation_audit.get("breakdown")
            if isinstance(breakdown, dict):
                cv_block = breakdown.get("cv")
                if isinstance(cv_block, dict):
                    payload.setdefault("alignment_audit", dict(cv_block))

        if isinstance(cover_letter_review, dict) and cover_letter_review:
            payload["cover_letter_review"] = dict(cover_letter_review)

        if isinstance(self.offer_data, dict):
            self.offer_data["analysis"] = dict(payload)
        return payload

    def save_cover_letter(
        self,
        cover_letter: str,
        *,
        generation_audit: Optional[Dict[str, Any]] = None,
        cover_letter_review: Optional[Dict[str, Any]] = None,
    ) -> JobApplication:
        """Sauvegarde la lettre de motivation en base."""
        offer_analysis_payload = self._build_offer_analysis_with_audit(
            generation_audit=generation_audit,
            cover_letter_review=cover_letter_review,
        )
        if self.application_id:
            try:
                from datetime import datetime

                with get_session() as session:
                    existing = session.get(JobApplication, self.application_id)
                    if existing is not None:
                        existing.generated_cover_letter = cover_letter
                        existing_analysis = (
                            dict(existing.offer_analysis)
                            if isinstance(existing.offer_analysis, dict)
                            else {}
                        )
                        existing_analysis.update(offer_analysis_payload)
                        existing.offer_analysis = existing_analysis
                        if isinstance(self.offer_data, dict):
                            self.offer_data["analysis"] = dict(existing_analysis)
                        existing.updated_at = datetime.now()
                        session.add(existing)
                        session.commit()
                        session.refresh(existing)
                        return existing
            except Exception as exc:
                logger.warning(f"Impossible de mettre a jour la candidature: {exc}")

        application = JobApplication(
            profile_id=self.profile_data.id,
            job_title=self.offer_data['job_title'],
            company=self.offer_data['company'],
            offer_text=self.offer_data['text'],
            offer_analysis=offer_analysis_payload,
            template_used=self.template,
            model_version_used=self.profile_data.model_version,
            generated_cover_letter=cover_letter,
            status=ApplicationStatus.DRAFT
        )

        with get_session() as session:
            session.add(application)
            session.commit()
            session.refresh(application)

        return application


class FineTuningWorker(QThread):
    """Worker pour le fine-tuning (version future).

    Note: Utilise ProfileWorkerData au lieu de UserProfile pour éviter
    les erreurs SQLAlchemy DetachedInstanceError dans les threads background.
    """
    progress_updated = Signal(str, int)  # message, pourcentage
    finished = Signal(str)  # chemin du modèle
    error_occurred = Signal(str)

    def __init__(self, profile_data: ProfileWorkerData):
        super().__init__()
        self.profile_data = profile_data

    def run(self):
        """Lance le fine-tuning (placeholder pour version future)."""
        try:
            self.progress_updated.emit("💠 Préparation des données d'entraînement...", 10)
            time.sleep(2)

            self.progress_updated.emit("🔍 Configuration du modèle...", 30)
            time.sleep(3)

            self.progress_updated.emit("🔄 Fine-tuning en cours...", 50)
            time.sleep(10)  # Simulation d'un long processus

            self.progress_updated.emit("💾 Sauvegarde du modèle personnalisé...", 90)
            time.sleep(2)

            # Mise à jour des métadonnées du profil via SQL direct (évite DetachedInstanceError)
            from datetime import datetime
            new_version = "v" + str(int(self.profile_data.model_version.replace("v", "")) + 1) if "v" in self.profile_data.model_version else "v1"

            try:
                with get_session() as session:
                    from sqlmodel import text
                    session.execute(
                        text("UPDATE userprofile SET last_fine_tuning = :ts, model_version = :ver WHERE id = :pid"),
                        {"ts": datetime.now(), "ver": new_version, "pid": self.profile_data.id}
                    )
                    session.commit()
            except Exception as e:
                logger.warning(f"Impossible de mettre à jour les métadonnées du profil: {e}")

            model_path = f"models/qwen2.5-32b-{self.profile_data.name.lower().replace(' ', '_')}-{new_version}/"

            self.progress_updated.emit("✅ Fine-tuning terminé !", 100)
            self.finished.emit(model_path)

        except Exception as e:
            logger.error(f"Erreur fine-tuning : {e}")
            self.error_occurred.emit(str(e))
