"""
LLM Worker
==========

Worker pour la génération de CV avec le modèle Qwen2.5-32B-Instruct.
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

try:
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
    from transformers.utils import logging as transformers_logging
    import os

    # Réduire les warnings/logs
    transformers_logging.set_verbosity_error()
    os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
    os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"  # Désactiver symlinks (Windows compat)
    os.environ["TRANSFORMERS_VERBOSITY"] = "error"

    TRANSFORMERS_AVAILABLE = True
    TORCH_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Dépendances IA non disponibles ({e}) - Mode simulation activé")
    TRANSFORMERS_AVAILABLE = False
    TORCH_AVAILABLE = False
    # Mock objects pour éviter les erreurs
    class MockTorch:
        device = lambda x: None
        cuda = type('cuda', (), {'is_available': lambda: False, 'empty_cache': lambda: None})()
        no_grad = lambda: type('context', (), {'__enter__': lambda self: None, '__exit__': lambda self, *args: None})()
        float16 = 'float16'
        float32 = 'float32'
    torch = MockTorch()

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
            if progress_callback: progress_callback("📥 Téléchargement standard...")
            return model_name
    model_optimizer = MockModelOptimizer()


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
                    rendered.append(_join_nonempty([str(name), str(level)], sep=": "))
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


from .qwen_manager import QwenManager  # noqa: F401 — backward-compat re-export

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

    def __init__(self, profile_data: ProfileWorkerData, offer_data: dict, template: str):
        super().__init__()
        self.profile_data = profile_data
        self.offer_data = offer_data
        self.template = template
        # Le QwenManager se configure automatiquement selon le modèle sélectionné
        self.qwen_manager = QwenManager(self.profile_data.model_version)
        self.application_id: Optional[int] = None
        self.user_instruction: str = ""
        self.cv_only_regen: bool = False
        self.previous_generation_audit: dict = {}
        self._pipeline_cv_json_draft: dict = {}
        self._pipeline_offer_keywords: dict = {}

    def _should_use_stage_subprocess(self) -> bool:
        try:
            if self.qwen_manager._is_survival_mode():
                return True
        except Exception:
            pass
        env_flag = os.getenv("CVMATCH_SUBPROCESS_STAGES")
        if env_flag is not None:
            return env_flag.strip().lower() in ("1", "true", "yes", "y")
        custom = getattr(self.qwen_manager, "custom_parameters", None) or {}
        if "subprocess_stages" in custom:
            return bool(custom.get("subprocess_stages"))
        try:
            return bool(
                self.qwen_manager._is_low_vram_mode()
                or self.qwen_manager._is_med_vram_mode()
            )
        except Exception:
            return False

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

        with open(input_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=True, default=str)

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

        run_env = dict(os.environ)
        try:
            if self.qwen_manager._is_survival_mode():
                run_env["CVMATCH_SURVIVAL_MODE"] = "1"
                run_env.setdefault("CVMATCH_SURVIVAL_IGNORE_SELECTED_MODEL", "1")
        except Exception:
            pass

        result = subprocess.run(
            cmd,
            cwd=str(repo_root),
            env=run_env,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            stdout = (result.stdout or "").strip()
            details = stderr or stdout or "unknown error"
            try:
                self.qwen_manager._record_failure(
                    f"stage_subprocess:{stage}:{details[:200]}"
                )
            except Exception:
                pass
            raise RuntimeError(f"Stage subprocess failed: {stage}: {details}")

        with open(output_path, "r", encoding="utf-8") as handle:
            result_payload = json.load(handle)

        try:
            input_path.unlink(missing_ok=True)
            output_path.unlink(missing_ok=True)
        except Exception:
            pass

        return result_payload

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
            build_profile_json_from_extracted_profile,
            has_profile_json_content,
            load_profile_json_cache,
            save_profile_json_cache,
        )

        profile_id = getattr(self.profile_data, "id", None) or 0
        if profile_id:
            cached = load_profile_json_cache(profile_id)
            if cached:
                logger.info("Profile JSON cache hit: profile_id=%s", profile_id)
                return cached

        extracted = build_profile_json_from_extracted_profile(self.profile_data)
        if has_profile_json_content(extracted):
            if profile_id:
                try:
                    save_profile_json_cache(profile_id, extracted)
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
                    profile_text = json.dumps(profile_json, ensure_ascii=True).lower()
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
        from ..schemas.offer_keywords_schema import OfferKeywordsJSON

        language = self._resolve_language_code()
        job_title = ""
        company = ""
        if isinstance(self.offer_data, dict):
            job_title = self.offer_data.get("job_title") or ""
            company = self.offer_data.get("company") or ""

        payload = {
            "schema_version": "offer_keywords.v1",
            "language": language,
            "job_title": job_title,
            "company": company,
            "seniority": "",
            "keywords": [],
            "skills": [],
            "tools": [],
            "soft_skills": [],
            "responsibilities": [],
            "education": [],
            "certifications": [],
        }

        try:
            parsed = OfferKeywordsJSON.model_validate(payload).model_dump()
        except Exception:
            parsed = payload

        if reason:
            logger.warning("Fallback OfferKeywordsJSON used due to: %s", reason)
        return parsed

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
        return 1 if self._is_slow_generation_device() else 2

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

    def _fallback_cv_json(
        self, *, profile_json: Dict[str, Any], reason: str = ""
    ) -> Dict[str, Any]:
        from ..schemas.cv_schema import CVJSON

        payload = {
            "schema_version": "cv.v1",
            "target_job_title": "",
            "target_company": "",
            "contact": {},
            "summary": "",
            "skills": [],
            "experience": [],
            "education": [],
            "projects": [],
            "languages": [],
            "certifications": [],
            "ats_keywords": [],
            "render_hints": {
                "notes": "",
                "section_order": [],
                "emphasis": [],
                "tone": "",
            },
        }

        try:
            parsed = CVJSON.model_validate(payload).model_dump()
        except Exception:
            parsed = payload

        if reason:
            logger.warning("Fallback CVJSON used due to: %s", reason)
        return parsed

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

    def _resolve_stage_model_override(self, stage: str) -> Optional[str]:
        from ..utils.stage_model_routing import resolve_stage_model_override
        custom = getattr(self.qwen_manager, "custom_parameters", None) or {}
        current = getattr(self.qwen_manager, "current_model_id", "")
        resolution = resolve_stage_model_override(
            stage, custom_parameters=custom, current_model_id=current
        )
        return resolution.model_id if resolution.requires_switch else None

    def _apply_stage_model_override(self, stage: str, progress_callback=None) -> None:
        from ..utils.stage_model_routing import resolve_stage_model_override
        custom = getattr(self.qwen_manager, "custom_parameters", None) or {}
        current = getattr(self.qwen_manager, "current_model_id", "")
        resolution = resolve_stage_model_override(
            stage, custom_parameters=custom, current_model_id=current
        )
        if resolution.requires_switch and resolution.model_id:
            try:
                self.qwen_manager._load_selected_model_config(
                    model_id=resolution.model_id
                )
            except Exception as exc:
                logger.warning(
                    "Stage model override failed for %s: %s", stage, exc
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
            profile_json = getattr(self, "_pipeline_cv_json_draft", {}) or {}
            personal_info = self._build_profile_payload().get("personal_info", {})
            return coerce_generated_cv_payload(
                payload=cv_json or {},
                profile_json=profile_json,
                fallback_generator=lambda pj, reason: self._fallback_cv_json(
                    profile_json=pj, reason=reason
                ),
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
            from ..utils.keyword_alignment import normalize_keyword_for_match

            probe_parts: List[str] = []
            if isinstance(cv_json, dict):
                for field in ("summary", "target_job_title", "target_company"):
                    val = cv_json.get(field)
                    if isinstance(val, str):
                        probe_parts.append(val)
                for section_key in ("skills", "ats_keywords", "experience", "projects"):
                    items = cv_json.get(section_key)
                    if isinstance(items, list):
                        for item in items:
                            if isinstance(item, str):
                                probe_parts.append(item)
                            elif isinstance(item, dict):
                                for v in item.values():
                                    if isinstance(v, str):
                                        probe_parts.append(v)
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

            thresholds = get_alignment_thresholds()

            def _term_present(term: str, probe: str) -> bool:
                return term in probe if term else False

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

    def _is_cover_letter_structure_coherent(self, letter: str) -> bool:
        try:
            from ..utils.cover_letter_rules import is_cover_letter_structure_coherent
            lang = self._resolve_language_code()
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

    def _fallback_cover_letter(
        self, offer_data: dict, lang: str, progress_callback=None
    ) -> str:
        try:
            from ..utils.cover_letter_fallback import generate_fallback_cover_letter
            return generate_fallback_cover_letter(
                profile_data=self.profile_data,
                offer_data=offer_data,
                language_code=lang,
                offer_keywords_collector=self._collect_offer_keywords,
            )
        except Exception as exc:
            logger.warning("_fallback_cover_letter failed: %s", exc)
            return ""

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
            if not language:
                continue
            cleaned_languages.append({"language": language, "level": level})
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
        offer_text = self.offer_data.get("text") if isinstance(self.offer_data, dict) else ""
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
        profile_block = json.dumps(compact_profile, indent=2, ensure_ascii=True)
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
                f"{_trim_text(json.dumps(offer_keywords, indent=2, ensure_ascii=True), 1400)}"
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
                    f"{_trim_text(json.dumps(critic_payload, indent=2, ensure_ascii=True), 2000)}"
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
  - Keep output compact:
  * experience <= 4 items, highlights <= 3 each.
  * skills <= 4 categories, items <= 8 each.
  * education <= 3 items.
  * projects <= 3 items.
  * languages <= 4 items.
  * certifications <= 3 items.
  * ats_keywords <= 15 items.
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
        try:
            return generate_json_with_schema(
                role="offer_critic",
                schema_model=OfferKeywordsJSON,
                messages=messages,
                qwen_manager=self.qwen_manager,
                retries=3,
                progress_callback=progress_callback,
            )
        except JsonStrictError as exc:
            logger.warning(
                "Strict OfferKeywordsJSON failed, retrying non-strict: %s", exc
            )
            raw = self.qwen_manager.generate_structured_json(
                messages["system"],
                messages["user"],
                progress_callback,
            )
            payload = self._parse_json_response(raw)
            if not payload:
                return self._fallback_offer_keywords_json(reason=str(exc))
            try:
                parsed = OfferKeywordsJSON.model_validate(payload)
            except ValidationError as val_exc:
                logger.warning(
                    "Non-strict OfferKeywordsJSON validation failed: %s", val_exc
                )
                return self._fallback_offer_keywords_json(reason=str(val_exc))
            return parsed.model_dump()

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
            return generate_json_with_schema(
                role="generator",
                schema_model=CVJSON,
                messages=messages,
                qwen_manager=self.qwen_manager,
                retries=self._strict_generator_retries(),
                progress_callback=progress_callback,
            )
        except JsonStrictError as exc:
            logger.warning("Strict CVJSON draft failed, retrying non-strict: %s", exc)
            raw = self.qwen_manager.generate_structured_json(
                messages["system"],
                messages["user"],
                progress_callback,
            )
            payload = self._parse_json_response(raw)
            if not payload:
                return self._fallback_cv_json(profile_json=profile_json, reason=str(exc))
            try:
                parsed = CVJSON.model_validate(payload)
            except ValidationError as val_exc:
                logger.warning("Non-strict CVJSON draft validation failed: %s", val_exc)
                return self._fallback_cv_json(profile_json=profile_json, reason=str(val_exc))
            return parsed.model_dump()

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
            return generate_json_with_schema(
                role="generator",
                schema_model=CVJSON,
                messages=messages,
                qwen_manager=self.qwen_manager,
                retries=self._strict_generator_retries(),
                progress_callback=progress_callback,
            )
        except JsonStrictError as exc:
            logger.warning("Strict CVJSON final failed, retrying non-strict: %s", exc)
            raw = self.qwen_manager.generate_structured_json(
                messages["system"],
                messages["user"],
                progress_callback,
            )
            payload = self._parse_json_response(raw)
            if not payload:
                return self._fallback_cv_json(profile_json=profile_json, reason=str(exc))
            try:
                parsed = CVJSON.model_validate(payload)
            except ValidationError as val_exc:
                logger.warning("Non-strict CVJSON final validation failed: %s", val_exc)
                return self._fallback_cv_json(profile_json=profile_json, reason=str(val_exc))
            return parsed.model_dump()

    def generate_critic_json(
        self,
        *,
        cv_html: str,
        progress_callback=None,
    ) -> Dict[str, Any]:
        from pydantic import ValidationError
        from ..schemas.critic_schema import CriticJSON
        from ..utils.json_strict import generate_json_with_schema, JsonStrictError

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
            raw = self.qwen_manager.generate_structured_json(
                messages["system"], messages["user"], progress_callback
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
            return self._fallback_critic_json(reason=str(exc))

    def run(self) -> None:
        """Run the CV generation pipeline via PipelineOrchestrator."""
        try:
            profile_json = self._build_profile_json()
            existing_snapshot = self._load_application_snapshot()

            orchestrator, state = build_default_pipeline(
                worker=self, qwen_manager=self.qwen_manager
            )
            state.profile_json = profile_json
            state.existing_snapshot = existing_snapshot
            state.progress_callback = self.progress_updated.emit

            success, _phase_results = orchestrator.run(state)

            if not success:
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
                    return {
                        "cv_json_draft": app.cv_json_draft or {},
                        "cv_json_final": app.cv_json_final or {},
                        "cv_markdown": app.cv_markdown or "",
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

    def build_prompt(self) -> str:
        """Construit le prompt optimisé pour Qwen2.5-32B."""
        analysis = self.offer_data.get("analysis", {}) if isinstance(self.offer_data, dict) else {}
        keywords: List[str] = []
        if isinstance(analysis, dict):
            for key in ("keywords", "skills", "tech_keywords", "soft_keywords", "tools"):
                value = analysis.get(key)
                if isinstance(value, list):
                    keywords.extend(str(item) for item in value)
                elif isinstance(value, str):
                    keywords.extend(part.strip() for part in value.split(",") if part.strip())
        keywords = _dedup_preserve([item for item in keywords if item])
        language = (
            (analysis.get("language") if isinstance(analysis, dict) else None)
            or getattr(self.profile_data, "preferred_language", None)
            or "fr"
        )
        language_code = _normalize_language(language)
        placeholder = "[TO COMPLETE]" if language_code == "en" else "[A COMPLETER]"
        sector = analysis.get("sector") if isinstance(analysis, dict) else None

        template_key = _normalize_template_name(self.template)
        style_hint = {
            "modern": "Style moderne: clair, concis, 1 page si possible, bullets orientées impact.",
            "classic": "Style classique/corporate: sobre, formel, chronologique, pas d'emojis.",
            "tech": "Style tech: focus competences techniques + projets, mots-cles ATS, bullets precises.",
            "creative": "Style creatif: focus projets/portfolio + centres d'interet, ton dynamique mais pro.",
        }.get(template_key, "Style professionnel, clair et concis.")

        job_title = self.offer_data.get("job_title") if isinstance(self.offer_data, dict) else None
        company = self.offer_data.get("company") if isinstance(self.offer_data, dict) else None
        offer_text = self.offer_data.get("text") if isinstance(self.offer_data, dict) else None
        offer_keywords = analysis.get("offer_keywords_llm") if isinstance(analysis, dict) else None

        profile_block = _format_profile_detailed_data(self.profile_data)
        skeleton = _markdown_skeleton_for_template(self.template, language=language_code)

        keywords_text = ", ".join(str(k) for k in keywords[:15] if str(k).strip())
        if not keywords_text:
            keywords_text = "None" if language_code == "en" else "Aucun"

        candidate_terms = _collect_candidate_keywords(self.profile_data)
        matched_keywords = _match_offer_keywords(offer_text, candidate_terms)
        matched_keywords_text = ", ".join(matched_keywords) if matched_keywords else ("None" if language_code == "en" else "Aucun")

        if language_code == "en":
            identity_block = "\n".join(
                [
                    "CANDIDATE IDENTITY (placeholders - keep exact):",
                    "- Name: [Your First Name] [Your Last Name]",
                    "- Email: [Your Email]",
                    "- Phone: [Your Phone]",
                    "- LinkedIn: [Your LinkedIn]",
                ]
            )
        else:
            identity_block = "\n".join(
                [
                    "IDENTITE CANDIDAT (placeholders - garder exact):",
                    "- Nom: [Votre Prenom] [Votre Nom]",
                    "- Email: [Votre Email]",
                    "- Telephone: [Votre Telephone]",
                    "- LinkedIn: [Votre LinkedIn]",
                ]
            )

        return f"""
LANGUE: {language_code}
STYLE (template): {self.template} ({style_hint})

OFFRE CIBLE:
- Poste: {job_title}
- Entreprise: {company}
- Secteur detecte: {sector or 'inconnu'}
- Mots-cles detectes: {keywords_text}
- Mots-cles OFFRE x CANDIDAT (a reutiliser si possible): {matched_keywords_text}
- Description (brut, tronquee si besoin):
{_trim_text(offer_text, 3500)}

{identity_block}

DONNEES CANDIDAT (Profil detaille + CV de reference):
{profile_block}

SORTIE OBLIGATOIRE (Markdown uniquement):
- Respecte STRICTEMENT cette structure et cet ordre de sections.
- Remplace les <...> par les informations reelles.
- Si une information manque, ecris {placeholder} au lieu d'inventer.
- Conserve les placeholders d'identite EXACTS (nom/email/telephone/linkedin); ils seront remplis apres generation.

{skeleton}

REGLES DE CONTENU:
- Priorise les experiences/projets/competences les plus pertinents pour l'offre.
- Mots-cles ATS: privilegie d'abord les mots-cles OFFRE x CANDIDAT. N'utilise pas de mots-cles absents des donnees candidat.
- Pour chaque experience: 3-5 puces orientees impact; chiffres uniquement si presents; sinon {placeholder} ou [impact a preciser].
        """.strip()

    def _get_language_code(self) -> str:
        analysis = self.offer_data.get("analysis", {}) if isinstance(self.offer_data, dict) else {}
        language = (
            (analysis.get("language") if isinstance(analysis, dict) else None)
            or getattr(self.profile_data, "preferred_language", None)
            or "fr"
        )
        return _normalize_language(language)

    def _normalize_for_compare(self, text: str) -> str:
        return re.sub(r"\s+", " ", (text or "").strip().lower())

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

    def _autocheck_unavailable_reason(self) -> str:
        loader = getattr(self.qwen_manager, "current_loader", "transformers")
        reasons: List[str] = []
        if loader == "llama_cpp":
            server = getattr(self.qwen_manager, "_llama_cpp_server", None)
            if server is None:
                reasons.append("llama.cpp server not initialized")
            else:
                try:
                    if hasattr(server, "is_ready") and not server.is_ready():
                        reasons.append("llama.cpp server not ready")
                except Exception:
                    reasons.append("llama.cpp server status unknown")
        else:
            if not TRANSFORMERS_AVAILABLE:
                reasons.append("transformers not available")
            if not TORCH_AVAILABLE:
                reasons.append("torch not available")
            if getattr(self.qwen_manager, "_model", None) is None:
                reasons.append("model not loaded")
        return "; ".join(reasons) if reasons else "LLM unavailable"

    def _llm_ready_for_autocheck(self) -> bool:
        loader = getattr(self.qwen_manager, "current_loader", "transformers")
        if loader == "llama_cpp":
            server = getattr(self.qwen_manager, "_llama_cpp_server", None)
            if server is None:
                return False
            try:
                return bool(getattr(server, "is_ready", lambda: False)())
            except Exception:
                return False
        if not TRANSFORMERS_AVAILABLE or not TORCH_AVAILABLE:
            return False
        return getattr(self.qwen_manager, "_model", None) is not None

    def _build_autocheck_prompts(self, cv_markdown: str) -> Dict[str, str]:
        analysis = self.offer_data.get("analysis", {}) if isinstance(self.offer_data, dict) else {}
        language_code = self._get_language_code()
        job_title = self.offer_data.get("job_title") if isinstance(self.offer_data, dict) else None
        company = self.offer_data.get("company") if isinstance(self.offer_data, dict) else None
        offer_text = self.offer_data.get("text") if isinstance(self.offer_data, dict) else None

        candidate_terms = _collect_candidate_keywords(self.profile_data)
        matched_keywords = _match_offer_keywords(offer_text, candidate_terms)
        matched_keywords_text = ", ".join(matched_keywords) if matched_keywords else ("None" if language_code == "en" else "Aucun")

        profile_block = _format_profile_detailed_data(self.profile_data)
        profile_block = _trim_text(profile_block, 2400)
        offer_block = _trim_text(offer_text, 2400)
        cv_block = _trim_text(cv_markdown, 3600)

        system_prompt = (
            "You are a strict ATS reviewer. Compare the CV to the offer and the candidate data. "
            "Return JSON only, with the exact schema requested. "
            "Do not invent facts. Use only candidate data as source of truth."
        )

        user_prompt = f"""
LANGUAGE: {language_code}
TARGET ROLE: {job_title}
COMPANY: {company}
MATCHED KEYWORDS (offer x candidate): {matched_keywords_text}
OFFER TEXT:
{offer_block}

CANDIDATE DATA (source of truth):
{profile_block}

CURRENT CV (markdown):
{cv_block}

Return JSON only with this schema:
{{
  "should_improve": true,
  "summary": "short reason",
  "issues": [
    {{"type": "missing_keyword|misaligned|format|fact_mismatch|missing_section", "detail": "...", "severity": "high|medium|low"}}
  ],
  "actions": [
    {{"instruction": "...", "target_section": "...", "priority": "high|medium|low"}}
  ],
  "missing_keywords": ["..."],
  "job_title_present": true
}}

Rules:
- If no improvements, set should_improve=false and return empty arrays.
- Do not add new facts. Only suggest reordering, rewriting, or removing.
""".strip()

        return {"system": system_prompt, "user": user_prompt}

    def _format_autocheck_feedback(self, review: Dict[str, Any]) -> str:
        actions = review.get("actions") if isinstance(review.get("actions"), list) else []
        issues = review.get("issues") if isinstance(review.get("issues"), list) else []
        missing = review.get("missing_keywords") if isinstance(review.get("missing_keywords"), list) else []

        lines: List[str] = []
        if issues:
            lines.append("Issues:")
            for item in issues[:8]:
                if isinstance(item, dict):
                    detail = (item.get("detail") or "").strip()
                    issue_type = (item.get("type") or "").strip()
                    if detail or issue_type:
                        lines.append(f"- {issue_type}: {detail}".strip())
        if actions:
            lines.append("Actions:")
            for item in actions[:8]:
                if isinstance(item, dict):
                    instruction = (item.get("instruction") or "").strip()
                    target = (item.get("target_section") or "").strip()
                    if instruction and target:
                        lines.append(f"- {target}: {instruction}")
                    elif instruction:
                        lines.append(f"- {instruction}")
        if missing:
            lines.append("Missing keywords to consider (only if present in candidate data):")
            for term in missing[:12]:
                if isinstance(term, str) and term.strip():
                    lines.append(f"- {term.strip()}")

        return "\n".join(lines).strip()

    def _build_revision_prompt(self, cv_markdown: str, review: Dict[str, Any], strict: bool = False) -> str:
        base_prompt = self.build_prompt()
        feedback = self._format_autocheck_feedback(review)
        cv_block = _trim_text(cv_markdown, 3600)
        strict_block = ""
        if strict:
            strict_block = (
                "STRICT OUTPUT RULES:\n"
                "- Output only the CV in Markdown.\n"
                "- Do not include feedback, JSON, or instructions.\n"
                "- Do not include reviewer labels (AUTO-CHECK, FEEDBACK, Issues, Actions, Missing keywords).\n"
                "- Start with a '# ' heading.\n"
            )
        return f"""
{base_prompt}

AUTO-CHECK FEEDBACK (use to revise; never copy into the CV):
{feedback or "No feedback."}

{strict_block}CURRENT CV (markdown):
{cv_block}

Regenerate the full CV in markdown, same structure and order as required.
""".strip()

    def _contains_review_artifacts(self, cv_markdown: str) -> bool:
        lowered = (cv_markdown or "").lower()
        signals = [
            "auto-check feedback",
            "missing_keywords",
            "should_improve",
            "issues:",
            "actions:",
            "return json",
        ]
        return any(signal in lowered for signal in signals)

    def _apply_autocheck_review(
        self,
        cv_markdown: str,
        review: Dict[str, Any],
        progress_callback=None,
    ) -> Optional[str]:
        if not self._llm_ready_for_autocheck():
            reason = self._autocheck_unavailable_reason()
            logger.warning("Auto-check revision skipped: %s", reason)
            return None

        if progress_callback:
            progress_callback("Auto-check: applying revisions...")

        revision_prompt = self._build_revision_prompt(cv_markdown, review, strict=True)
        revised = self.qwen_manager.generate_cv(
            revision_prompt,
            progress_callback,
            allow_fallback=False,
        )

        if not revised or not revised.strip():
            return None

        try:
            revised = revised.format(
                name=self.profile_data.name or "[Votre Prenom] [Votre Nom]",
                email=self.profile_data.email or "[Votre Email]",
                phone=self.profile_data.phone or "[Votre Telephone]",
                linkedin=self.profile_data.linkedin_url or "[Votre LinkedIn]",
            )
        except KeyError as e:
            logger.warning("Erreur formatage CV revision: %s", e)

        revised = self._force_profile_identity(revised).strip()

        if not revised.startswith("#") or self._contains_review_artifacts(revised):
            strict_prompt = self._build_revision_prompt(cv_markdown, review, strict=True)
            strict_output = self.qwen_manager.generate_cv(
                strict_prompt,
                progress_callback,
                allow_fallback=False,
            )
            if not strict_output or not strict_output.strip():
                return None
            try:
                strict_output = strict_output.format(
                    name=self.profile_data.name or "[Votre Prenom] [Votre Nom]",
                    email=self.profile_data.email or "[Votre Email]",
                    phone=self.profile_data.phone or "[Votre Telephone]",
                    linkedin=self.profile_data.linkedin_url or "[Votre LinkedIn]",
                )
            except KeyError as e:
                logger.warning("Erreur formatage CV revision strict: %s", e)
            strict_output = self._force_profile_identity(strict_output).strip()
            if not strict_output.startswith("#") or self._contains_review_artifacts(strict_output):
                return None
            return strict_output

        return revised

    def _auto_check_cv(self, cv_markdown: str, progress_callback=None) -> str:
        if not cv_markdown or not cv_markdown.strip():
            return cv_markdown

        if not self._llm_ready_for_autocheck():
            reason = self._autocheck_unavailable_reason()
            logger.warning("Auto-check skipped: %s", reason)
            return cv_markdown

        model_id = getattr(self.qwen_manager, "current_model_id", None) or getattr(
            self.qwen_manager, "model_name", "unknown"
        )
        logger.info("Auto-check uses model: %s", model_id)

        max_iterations = 5
        current_cv = cv_markdown

        for iteration in range(1, max_iterations + 1):
            if progress_callback:
                progress_callback(f"Auto-check LLM (iteration {iteration}/{max_iterations})...")

            prompts = self._build_autocheck_prompts(current_cv)
            review_raw = self.qwen_manager.generate_structured_json(
                prompts["system"],
                prompts["user"],
                progress_callback,
            )
            review = self._parse_json_response(review_raw)

            if not review:
                logger.warning("Auto-check LLM review failed: empty or invalid JSON")
                break

            actions = review.get("actions") if isinstance(review.get("actions"), list) else []
            missing_keywords = review.get("missing_keywords") if isinstance(review.get("missing_keywords"), list) else []
            issues = review.get("issues") if isinstance(review.get("issues"), list) else []
            should_improve = bool(review.get("should_improve"))

            if not should_improve and not actions and not missing_keywords and not issues:
                logger.info("Auto-check: no improvements detected")
                break

            revised = self._apply_autocheck_review(current_cv, review, progress_callback)
            if not revised:
                logger.warning("Auto-check stopped: revision step failed")
                break

            if self._normalize_for_compare(revised) == self._normalize_for_compare(current_cv):
                logger.info("Auto-check: no change after iteration %s", iteration)
                break

            current_cv = revised

        return current_cv

    def _ensure_job_title(self, cv_markdown: str) -> str:
        if not cv_markdown:
            return cv_markdown

        job_title = ""
        if isinstance(self.offer_data, dict):
            job_title = (self.offer_data.get("job_title") or "").strip()

        if not job_title:
            return cv_markdown

        lines = cv_markdown.splitlines()
        normalized_job = job_title.lower()

        for line in lines:
            if line.strip().startswith("## ") and normalized_job in line.strip().lower():
                return cv_markdown

        heading = f"## {job_title}"
        insert_idx = 0
        for idx, line in enumerate(lines):
            if line.strip().startswith("# "):
                insert_idx = idx + 1
                break

        scan_idx = insert_idx
        while scan_idx < len(lines) and not lines[scan_idx].strip():
            scan_idx += 1

        if scan_idx < len(lines) and lines[scan_idx].strip().startswith("## "):
            existing = lines[scan_idx].strip()[3:]
            existing_lower = existing.lower()
            if any(token in existing_lower for token in ["titre du poste", "poste cible", "target role", "<", ">"]):
                lines[scan_idx] = heading
                return "\n".join(lines).strip()
            if any(token in existing_lower for token in ["contact", "profil professionnel", "professional summary"]):
                lines.insert(scan_idx, heading)
                return "\n".join(lines).strip()

        lines.insert(insert_idx, heading)
        return "\n".join(lines).strip()

    def _force_profile_identity(self, cv_markdown: str) -> str:
        """Ensure the generated CV uses the profile identity (name/contact)."""
        if not cv_markdown:
            return cv_markdown

        lines = cv_markdown.splitlines()
        name = (self.profile_data.name or "[Votre Prenom] [Votre Nom]").strip()
        email = (self.profile_data.email or "[Votre Email]").strip()
        phone = (self.profile_data.phone or "[Votre Telephone]").strip()
        linkedin = (self.profile_data.linkedin_url or "[Votre LinkedIn]").strip()

        if name:
            replaced = False
            for idx, line in enumerate(lines):
                if line.strip().startswith("# "):
                    lines[idx] = f"# {name}"
                    replaced = True
                    break
            if not replaced:
                lines.insert(0, f"# {name}")

        if email:
            for idx, line in enumerate(lines):
                if "@" in line or "email" in line.lower():
                    updated = EMAIL_RE.sub(email, line)
                    if updated == line and "email" in line.lower():
                        updated = f"- Email: {email}"
                    lines[idx] = updated

        if phone:
            for idx, line in enumerate(lines):
                lowered = line.lower()
                if any(token in lowered for token in ["tel", "telephone", "phone", "mobile"]):
                    updated = PHONE_RE.sub(phone, line)
                    if updated == line:
                        updated = f"- Telephone: {phone}"
                    lines[idx] = updated

        if linkedin:
            for idx, line in enumerate(lines):
                if "linkedin" in line.lower():
                    updated = LINKEDIN_RE.sub(linkedin, line)
                    if updated == line:
                        updated = f"- LinkedIn: {linkedin}"
                    lines[idx] = updated

        return "\n".join(lines).strip()

    def build_cover_letter_prompt(self) -> str:
        """Construit le prompt optimisé pour générer la lettre de motivation."""
        analysis = self.offer_data.get("analysis", {}) if isinstance(self.offer_data, dict) else {}
        keywords: List[str] = []
        if isinstance(analysis, dict):
            for key in ("keywords", "skills", "tech_keywords", "soft_keywords", "tools"):
                value = analysis.get(key)
                if isinstance(value, list):
                    keywords.extend(str(item) for item in value)
                elif isinstance(value, str):
                    keywords.extend(part.strip() for part in value.split(",") if part.strip())
        keywords = _dedup_preserve([item for item in keywords if item])
        language = (
            (analysis.get("language") if isinstance(analysis, dict) else None)
            or getattr(self.profile_data, "preferred_language", None)
            or "fr"
        )
        language_code = _normalize_language(language)
        placeholder = "[TO COMPLETE]" if language_code == "en" else "[A COMPLETER]"

        template_key = _normalize_template_name(self.template)
        style_hint = {
            "modern": "Ton moderne et direct, phrases courtes, tres specifique.",
            "classic": "Ton formel et corporate, vocabulaire sobre.",
            "tech": "Ton technique/pro: concret, oriente realisations et stack verifiable.",
            "creative": "Ton dynamique, orientation projets/impact, mais professionnel.",
        }.get(template_key, "Ton professionnel et specifique.")

        job_title = self.offer_data.get("job_title") if isinstance(self.offer_data, dict) else None
        company = self.offer_data.get("company") if isinstance(self.offer_data, dict) else None
        offer_text = self.offer_data.get("text") if isinstance(self.offer_data, dict) else None
        offer_keywords = analysis.get("offer_keywords_llm") if isinstance(analysis, dict) else None

        profile_block = _format_profile_detailed_data(self.profile_data)

        keywords_text = ", ".join(str(k) for k in keywords[:15] if str(k).strip())
        if not keywords_text:
            keywords_text = "None" if language_code == "en" else "Aucun"

        if language_code == "en":
            letter_skeleton = f"""Subject: Application - {job_title} ({company})

Dear Hiring Manager,

<Paragraph 1: hook + why this role/company (specific)>

<Paragraph 2: 2-3 proof points (experience/projects) + verified skills + impact>

<Paragraph 3: motivation + projection + interview availability>

Sincerely,

{self.profile_data.name or placeholder}"""
        else:
            letter_skeleton = f"""Objet: Candidature - {job_title} ({company})

Madame, Monsieur,

<Paragraphe 1: accroche + pourquoi ce poste/entreprise (specifique)>

<Paragraphe 2: 2-3 preuves de fit (experiences/projets) + competences cles verifiables + impact>

<Paragraphe 3: motivation + projection + disponibilite pour entretien>

Je vous prie d'agreer, Madame, Monsieur, l'expression de mes salutations distinguees.

{self.profile_data.name or placeholder}"""
        return f"""
LANGUE: {language_code}
STYLE (template): {self.template} ({style_hint})

OFFRE CIBLE:
- Poste: {job_title}
- Entreprise: {company}
- Mots-cles detectes: {keywords_text}
- Description (brut, tronquee si besoin):
{_trim_text(offer_text, 2000 if isinstance(offer_keywords, dict) else 3000)}

OFFER_KEYWORDS_JSON (si disponible):
{_trim_text(json.dumps(offer_keywords, indent=2, ensure_ascii=True), 1200) if isinstance(offer_keywords, dict) else "N/A"}

DONNEES CANDIDAT (Profil detaille + CV de reference + lettre type si fournie):
{profile_block}

SORTIE OBLIGATOIRE (texte uniquement, pas de Markdown):
- Respecte STRICTEMENT la structure ci-dessous.
- Utilise uniquement les faits presents dans les donnees candidat (sinon {placeholder}).
- Mots-cles ATS: tu peux reprendre les termes de l'offre OU des synonymes/termes equivalents, tant que le fond reste vrai.
- Longueur: maximum 1 page.

STRUCTURE:
{letter_skeleton}
""".strip()

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
    ) -> JobApplication:
        """Sauvegarde la candidature en base."""
        application = JobApplication(
            profile_id=self.profile_data.id,
            job_title=self.offer_data['job_title'],
            company=self.offer_data['company'],
            offer_text=self.offer_data['text'],
            offer_analysis=self.offer_data.get('analysis', {}),
            template_used=self.template,
            model_version_used=self.profile_data.model_version,
            generated_cv_markdown=cv_markdown,
            generated_cv_html=cv_html,
            generated_cover_letter=cover_letter,
            profile_json=profile_json,
            critic_json=critic_json,
            cv_json_draft=cv_json_draft,
            cv_json_final=cv_json_final,
            status=ApplicationStatus.DRAFT
        )

        with get_session() as session:
            session.add(application)
            session.commit()
            session.refresh(application)

        # Mettre à jour les stats du profil via SQL direct (évite DetachedInstanceError)
        try:
            with get_session() as session:
                from sqlmodel import text
                session.execute(
                    text("UPDATE userprofile SET total_cvs_generated = total_cvs_generated + 1 WHERE id = :pid"),
                    {"pid": self.profile_data.id}
                )
                session.commit()
                logger.debug(f"Stats profil {self.profile_data.id} mises à jour")
        except Exception as e:
            logger.warning(f"Impossible de mettre à jour les stats du profil: {e}")

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
    ):
        super().__init__()
        self.profile_data = profile_data
        self.offer_data = offer_data
        self.template = template
        self.application_id = application_id
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
            progress_callback(f"🤖 Initialisation du modèle {model_name}...")
            self.qwen_manager.load_model(progress_callback, allow_fallback=False)

            # Étape 2: Construction du prompt
            progress_callback("📝 Construction du prompt pour la lettre...")
            prompt = self.build_letter_prompt()

            # Étape 3: Génération de la lettre
            progress_callback("💌 Génération de la lettre de motivation...")
            cover_letter = self.qwen_manager.generate_cover_letter(prompt, progress_callback)

            # Étape 4: Sauvegarde
            progress_callback("💾 Sauvegarde de la lettre...")
            application = self.save_cover_letter(cover_letter)

            # Étape 5: Nettoyage mémoire
            progress_callback("🧹 Nettoyage mémoire...")
            self.qwen_manager.cleanup_memory()

            # Résultat final
            result = {
                "application_id": application.id,
                "cover_letter": cover_letter,
                "template": self.template,
                "model_version": self.profile_data.model_version,
                "model_used": getattr(self.qwen_manager, 'current_model_id', 'unknown'),
                "gpu_used": gpu_manager.gpu_info["available"]
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
        """Construit le prompt optimisé pour la lettre de motivation."""
        analysis = self.offer_data.get("analysis", {}) if isinstance(self.offer_data, dict) else {}
        keywords: List[str] = []
        if isinstance(analysis, dict):
            for key in ("keywords", "skills", "tech_keywords", "soft_keywords", "tools"):
                value = analysis.get(key)
                if isinstance(value, list):
                    keywords.extend(str(item) for item in value)
                elif isinstance(value, str):
                    keywords.extend(part.strip() for part in value.split(",") if part.strip())
        keywords = _dedup_preserve([item for item in keywords if item])
        language = (
            (analysis.get("language") if isinstance(analysis, dict) else None)
            or getattr(self.profile_data, "preferred_language", None)
            or "fr"
        )
        language_code = _normalize_language(language)
        placeholder = "[TO COMPLETE]" if language_code == "en" else "[A COMPLETER]"

        template_key = _normalize_template_name(self.template)
        style_hint = {
            "modern": "Ton moderne et direct, phrases courtes, tres specifique.",
            "classic": "Ton formel et corporate, vocabulaire sobre.",
            "tech": "Ton technique/pro: concret, oriente realisations et stack verifiable.",
            "creative": "Ton dynamique, orientation projets/impact, mais professionnel.",
        }.get(template_key, "Ton professionnel et specifique.")

        job_title = self.offer_data.get("job_title") if isinstance(self.offer_data, dict) else None
        company = self.offer_data.get("company") if isinstance(self.offer_data, dict) else None
        offer_text = self.offer_data.get("text") if isinstance(self.offer_data, dict) else None
        offer_keywords = analysis.get("offer_keywords_llm") if isinstance(analysis, dict) else None

        profile_block = _format_profile_detailed_data(self.profile_data)

        keywords_text = ", ".join(str(k) for k in keywords[:15] if str(k).strip())
        if not keywords_text:
            keywords_text = "None" if language_code == "en" else "Aucun"

        if language_code == "en":
            letter_skeleton = f"""Subject: Application - {job_title} ({company})

Dear Hiring Manager,

<Paragraph 1: hook + why this role/company (specific)>

<Paragraph 2: 2-3 proof points (experience/projects) + verified skills + impact>

<Paragraph 3: motivation + projection + interview availability>

Sincerely,

{self.profile_data.name or placeholder}"""
        else:
            letter_skeleton = f"""Objet: Candidature - {job_title} ({company})

Madame, Monsieur,

<Paragraphe 1: accroche + pourquoi ce poste/entreprise (specifique)>

<Paragraphe 2: 2-3 preuves de fit (experiences/projets) + competences cles verifiables + impact>

<Paragraphe 3: motivation + projection + disponibilite pour entretien>

Je vous prie d'agreer, Madame, Monsieur, l'expression de mes salutations distinguees.

{self.profile_data.name or placeholder}"""
        return f"""
LANGUE: {language_code}
STYLE (template): {self.template} ({style_hint})

OFFRE CIBLE:
- Poste: {job_title}
- Entreprise: {company}
- Mots-cles detectes: {keywords_text}
- Description (brut, tronquee si besoin):
{_trim_text(offer_text, 2000 if isinstance(offer_keywords, dict) else 3000)}

OFFER_KEYWORDS_JSON (si disponible):
{_trim_text(json.dumps(offer_keywords, indent=2, ensure_ascii=True), 1200) if isinstance(offer_keywords, dict) else "N/A"}

DONNEES CANDIDAT (Profil detaille + CV de reference + lettre type si fournie):
{profile_block}

SORTIE OBLIGATOIRE (texte uniquement, pas de Markdown):
- Respecte STRICTEMENT la structure ci-dessous.
- Utilise uniquement les faits presents dans les donnees candidat (sinon {placeholder}).
- Mots-cles ATS: tu peux reprendre les termes de l'offre OU des synonymes/termes equivalents, tant que le fond reste vrai.
- Longueur: maximum 1 page.

STRUCTURE:
{letter_skeleton}
""".strip()

    def save_cover_letter(self, cover_letter: str) -> JobApplication:
        """Sauvegarde la lettre de motivation en base."""
        if self.application_id:
            try:
                from datetime import datetime

                with get_session() as session:
                    existing = session.get(JobApplication, self.application_id)
                    if existing is not None:
                        existing.generated_cover_letter = cover_letter
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
            offer_analysis=self.offer_data.get('analysis', {}),
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
            self.progress_updated.emit("🧠 Préparation des données d'entraînement...", 10)
            time.sleep(2)

            self.progress_updated.emit("⚙️ Configuration du modèle...", 30)
            time.sleep(3)

            self.progress_updated.emit("🔥 Fine-tuning en cours...", 50)
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

