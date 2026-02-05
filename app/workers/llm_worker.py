"""
LLM Worker
==========

Worker pour la génération de CV avec le modèle Qwen2.5-32B-Instruct.
"""

import json
import re
import time
import unicodedata
import inspect
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
from ..utils.model_registry import model_registry
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


class QwenManager:
    """Gestionnaire pour les modèles IA avec support multi-modèles."""
    
    _instance = None
    _model = None
    _tokenizer = None
    _device = None
    _current_model_path = None
    DEFAULT_ROLE_PARAMS = {
        "extractor": {
            "temperature": 0.0,
            "top_p": 0.9,
            "top_k": 50,
            "max_input_tokens": 3000,
            "max_new_tokens": 700,
            "max_total_tokens": 3700,
        },
        "critic": {
            "temperature": 0.2,
            "top_p": 0.9,
            "top_k": 50,
            "max_input_tokens": 2800,
            "max_new_tokens": 900,
            "max_total_tokens": 3700,
        },
        "offer_critic": {
            "temperature": 0.1,
            "top_p": 0.9,
            "top_k": 50,
            "max_input_tokens": 2200,
            "max_new_tokens": 600,
            "max_total_tokens": 2800,
        },
        "generator": {
            "temperature": 0.3,
            "top_p": 0.9,
            "top_k": 50,
            "max_input_tokens": 2400,
            "max_new_tokens": 2200,
            "max_total_tokens": 5200,
        },
    }
    
    def __new__(cls, model_version: str = "base"):
        """Singleton pour éviter de recharger le modèle."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, model_version: str = "base"):
        if hasattr(self, '_initialized'):
            return
        
        self.model_version = model_version
        self.model_loaded = False
        self.model_name = "Qwen/Qwen2.5-7B-Instruct"  # Par défaut
        self.current_loader = "transformers"
        self.custom_parameters: Dict[str, Any] = {}
        self.role_params: Dict[str, Any] = {}
        self._llama_cpp_server = None
        self._optimization_config = None
        self._current_model_path = None
        self.last_model_resolution_note: Optional[str] = None
        self._initialized = True
        
        # Charger la configuration du modèle sélectionné
        self._load_selected_model_config()
    
    def _load_selected_model_config(self):
        """Charge la configuration du modèle sélectionné par l'utilisateur."""
        try:
            from ..utils.model_config_manager import model_config_manager
            from ..utils.model_manager import model_manager
            
            self.last_model_resolution_note = None

            # Récupérer le modèle sélectionné
            config = model_config_manager.get_current_config()
            self.custom_parameters = getattr(config, "custom_parameters", None) or {}

            # Toujours tenter le modele choisi par l'utilisateur, meme si incompatible
            if config.model_id not in getattr(model_manager, 'available_models', []):
                self.last_model_resolution_note = (
                    f"Warning: modele '{config.model_id}' incompatible selon le garde-fou. "
                    "Tentative de chargement quand meme."
                )
                logger.warning(self.last_model_resolution_note)

            model_info = model_manager.get_model_info(config.model_id)
             
            if model_info:
                self.model_name = model_info.model_path
                self.current_model_id = config.model_id
                self.current_loader = getattr(model_info, "loader", "transformers") or "transformers"
                self.role_params = (getattr(model_info, "metadata", None) or {}).get(
                    "role_params", {}
                )
                if getattr(model_info, "quantization", "") == "nf4":
                    self.custom_parameters.setdefault("force_4bit_nf4", True)
                logger.info(f"Configuration modèle: {config.model_id} -> {self.model_name}")
            else:
                logger.warning(f"Modele {config.model_id} non trouve, utilisation du registre dynamique")
                fallback = model_registry.select_profile({
                    "available": model_manager.gpu_info.get("available", False),
                    "vram_gb": model_manager.gpu_info.get("vram_gb", 0),
                    "ram_gb": getattr(model_manager, 'system_ram_gb', 0),
                })
                if fallback:
                    self.model_name = fallback.model_id
                    self.current_model_id = fallback.key
                    self.current_loader = getattr(fallback, "loader", None) or "transformers"
                    self.role_params = (getattr(fallback, "extra", None) or {}).get(
                        "role_params", {}
                    )
                    if getattr(fallback, "quantization", "") == "nf4":
                        self.custom_parameters.setdefault("force_4bit_nf4", True)
                    logger.info(f"Fallback registre -> {fallback.key} ({self.model_name})")
                else:
                    logger.warning("Aucun profil registre disponible, conservation du modèle par défaut")
                
        except ImportError:
            logger.warning("Configuration centralisée non disponible, modèle par défaut")
        except Exception as e:
            logger.error(f"Erreur chargement config modèle: {e}")
    
    def _resolve_role_params(
        self, role: str, overrides: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        defaults = dict(self.DEFAULT_ROLE_PARAMS.get(role, {}))
        model_overrides = self.role_params.get(role, {}) if self.role_params else {}
        merged = {**defaults, **model_overrides}
        if overrides:
            merged.update(overrides)
        return merged

    def generate_structured_json_lmfe(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: Dict[str, Any],
        role: str,
        progress_callback=None,
        role_params: Optional[Dict[str, Any]] = None,
    ) -> str:
        from ..utils.json_strict import build_lmfe_generation_kwargs, JsonStrictError

        if getattr(self, "current_loader", "transformers") != "transformers":
            raise JsonStrictError("Strict JSON requires transformers (in-process) loader.")

        if not self.model_loaded:
            self.load_model(progress_callback, allow_fallback=False)

        if not TRANSFORMERS_AVAILABLE or self._model is None or self._tokenizer is None:
            raise JsonStrictError("Transformers model not available for strict JSON.")

        params = self._resolve_role_params(role, role_params)
        max_input_tokens = int(params.get("max_input_tokens") or 2048)
        max_new_tokens = int(params.get("max_new_tokens") or 512)
        max_total_tokens = int(params.get("max_total_tokens") or 0) or None
        temperature = float(params.get("temperature") or 0.2)
        top_p = float(params.get("top_p") or 0.9)
        top_k = int(params.get("top_k") or 50)

        formatted_prompt = self._build_generic_prompt(system_prompt, user_prompt)

        inputs = self._tokenizer(
            formatted_prompt,
            return_tensors="pt",
            truncation=True,
            max_length=max_input_tokens,
        ).to(self._device)

        input_len = int(inputs.input_ids.shape[1])
        if max_total_tokens:
            max_new_tokens = max(1, min(max_new_tokens, max_total_tokens - input_len))

        slow_device = False
        try:
            if getattr(self._device, "type", None) == "cpu":
                slow_device = True
        except Exception:
            pass
        try:
            device_map = getattr(self._model, "hf_device_map", None)
            if isinstance(device_map, dict) and device_map:
                for value in device_map.values():
                    resolved = self._normalize_device_target(value)
                    if resolved is None:
                        continue
                    if resolved.type != "cuda":
                        slow_device = True
                        break
        except Exception:
            pass

        max_time_s = 120.0
        if slow_device:
            max_time_s = 240.0
            max_new_tokens = min(max_new_tokens, 800)
            logger.info(
                "Strict JSON slow mode: cap max_new_tokens=%s max_time=%.0fs",
                max_new_tokens,
                max_time_s,
            )

        lmfe_kwargs = build_lmfe_generation_kwargs(self._tokenizer, schema)

        with torch.no_grad():
            generate_kwargs = {
                "max_new_tokens": max_new_tokens,
                "temperature": max(temperature, 0.0),
                "top_p": top_p,
                "top_k": top_k,
                "do_sample": temperature > 0.0,
                "repetition_penalty": 1.05,
                "pad_token_id": self._tokenizer.eos_token_id,
                "eos_token_id": self._tokenizer.eos_token_id,
                "max_time": max_time_s,
                **lmfe_kwargs,
            }
            outputs = self._model.generate(**inputs, **generate_kwargs)

        generated_text = self._tokenizer.decode(
            outputs[0][inputs.input_ids.shape[1] :],
            skip_special_tokens=True,
        )

        return self._extract_structured_content(generated_text)

    def _check_first_download(self, progress_callback=None):
        """Vérifie si c'est le premier téléchargement du modèle."""
        try:
            from transformers import AutoTokenizer
            from pathlib import Path
            import os
            
            # Chemins de cache possibles
            cache_paths = [
                Path.home() / ".cache" / "huggingface" / "transformers",
                Path.home() / ".cache" / "huggingface" / "hub"
            ]
            
            model_cached = False
            for cache_path in cache_paths:
                if cache_path.exists():
                    # Chercher des traces du modèle dans le cache
                    for item in cache_path.iterdir():
                        if self.model_name.split('/')[-1].lower() in item.name.lower():
                            model_cached = True
                            break
                if model_cached:
                    break
            
            if not model_cached and progress_callback:
                model_display_name = getattr(self, 'current_model_id', self.model_name.split('/')[-1])
                progress_callback(f"⏳ Premier téléchargement de {model_display_name}")
                progress_callback("📥 Le téléchargement peut prendre plusieurs minutes selon votre connexion...")
                progress_callback("💾 Le modèle sera mis en cache pour les prochaines utilisations")
                
        except Exception as e:
            logger.warning(f"Impossible de vérifier le cache: {e}")

    def _estimate_required_ram_gb(
        self,
        *,
        model_name: Optional[str] = None,
        model_id: Optional[str] = None,
        optimization: Optional[Dict[str, Any]] = None,
    ) -> float:
        """Heuristique: estime la RAM (GB) requise pour charger le modèle."""
        opt = optimization or (self._optimization_config or {})
        dtype = opt.get("dtype")
        params_b = _estimate_model_size_gb(
            model_name or self.model_name,
            model_id or getattr(self, "current_model_id", None),
        )

        if opt.get("load_in_4bit"):
            gb_per_b = 0.5
        elif opt.get("load_in_8bit"):
            gb_per_b = 1.0
        else:
            dtype_str = str(dtype).lower() if dtype is not None else ""
            is_fp16_family = dtype in (
                getattr(torch, "float16", None),
                getattr(torch, "bfloat16", None),
            )
            if is_fp16_family or "float16" in dtype_str or "bfloat16" in dtype_str:
                gb_per_b = 2.0
            else:
                gb_per_b = 4.0

        overhead_factor = 1.10
        overhead_constant = 0.8
        return max(1.5, params_b * gb_per_b * overhead_factor + overhead_constant)

    def _pick_fallback_model_for_memory(self, available_ram_gb: float) -> Optional[Dict[str, str]]:
        """Choisit un modèle de fallback qui a le plus de chances de charger avec la RAM actuelle."""
        try:
            from ..utils.model_manager import model_manager
        except Exception:
            return None

        current_id = getattr(self, "current_model_id", None)
        candidates = [
            mid
            for mid in getattr(model_manager, "available_models", [])
            if mid and mid != current_id
        ]
        if not candidates:
            return None

        fitting: List[tuple] = []
        all_candidates: List[tuple] = []
        for model_id in candidates:
            info = model_manager.get_model_info(model_id)
            if not info:
                continue
            required = self._estimate_required_ram_gb(model_name=info.model_path, model_id=model_id)
            all_candidates.append((required, model_id, info.model_path))
            if available_ram_gb <= 0 or required <= available_ram_gb * 0.92:
                fitting.append(
                    (
                        -info.quality_stars,
                        -info.speed_rating,
                        required,
                        model_id,
                        info.model_path,
                    )
                )

        if fitting:
            fitting.sort()
            _, _, _, model_id, model_path = fitting[0]
            return {"model_id": model_id, "model_path": model_path}

        if not all_candidates:
            return None

        all_candidates.sort(key=lambda item: item[0])
        _, model_id, model_path = all_candidates[0]
        return {"model_id": model_id, "model_path": model_path}

    def _check_memory_before_load(self) -> tuple:
        """Vérifie si assez de mémoire est disponible avant chargement.

        Returns:
            tuple: (can_proceed: bool, error_message: str or None)
        """
        try:
            import psutil
            mem = psutil.virtual_memory()
            # Utiliser la RAM "available" (inclut le cache libérable) pour éviter de lancer
            # un chargement qui va swapper/crasher.
            available_ram = mem.available / (1024**3)
            total_ram = mem.total / (1024**3)

            device = (self._optimization_config or {}).get("device") or "cpu"

            # Pour GPU, la contrainte principale est la VRAM (déjà gérée par gpu_manager).
            # On garde ici une vérification minimale de RAM pour éviter les crashs au chargement.
            if device != "cpu":
                if available_ram < 2.0:
                    error_msg = (
                        f"Mémoire système insuffisante pour charger {self.model_name}: "
                        f"{available_ram:.1f}GB disponibles (sur {total_ram:.1f}GB). "
                        "Fermez des applications puis réessayez."
                    )
                    return False, error_msg
                return True, None

            required = float(self._estimate_required_ram_gb())

            # Vérification avec marge de sécurité de 20%
            if available_ram < required * 0.8:
                error_msg = (
                    f"Mémoire insuffisante pour charger {self.model_name}: "
                    f"{available_ram:.1f}GB disponibles (sur {total_ram:.1f}GB), ~{required:.1f}GB requis. "
                    "Fermez des applications ou choisissez un modèle plus petit (Qwen2.5-0.5B, TinyLlama)."
                )
                return False, error_msg

            # Avertissement si mémoire serrée
            if available_ram < required * 1.2:
                logger.warning(
                    f"Mémoire disponible limitée ({available_ram:.1f}GB) pour {self.model_name} "
                    f"(recommandé: {required:.1f}GB). Le chargement pourrait être lent."
                )

            return True, None

        except ImportError:
            logger.warning("psutil non disponible - vérification mémoire ignorée")
            return True, None
        except Exception as e:
            logger.warning(f"Erreur vérification mémoire: {e}")
            return True, None

    def _build_max_memory_map(self) -> Optional[Dict[Union[int, str], str]]:
        """Build a max_memory map for auto device placement."""
        if not TORCH_AVAILABLE or not torch.cuda.is_available():
            return None

        def _get_percent(key: str, default_value: int) -> int:
            raw = (self.custom_parameters or {}).get(key)
            try:
                value = int(raw)
            except Exception:
                return default_value
            if value < 10 or value > 99:
                return default_value
            return value

        free_vram_gb = 0.0
        try:
            if hasattr(torch.cuda, "mem_get_info"):
                free_bytes, _ = torch.cuda.mem_get_info()
                free_vram_gb = free_bytes / (1024**3)
        except Exception:
            free_vram_gb = 0.0

        if not free_vram_gb:
            try:
                total_vram = float(gpu_manager.gpu_info.get("total_memory_gb", 0) or 0)
            except Exception:
                total_vram = 0.0
            free_vram_gb = total_vram

        if free_vram_gb <= 0:
            return None

        gpu_percent = _get_percent("max_memory_gpu_percent", 90)
        vram_budget_mib = max(512, int(free_vram_gb * 1024 * (gpu_percent / 100.0)))
        memory_map: Dict[Union[int, str], str] = {0: f"{vram_budget_mib}MiB"}

        try:
            import psutil

            available_ram_gb = psutil.virtual_memory().available / (1024**3)
            if available_ram_gb >= 1.0:
                cpu_percent = _get_percent("max_memory_cpu_percent", 80)
                ram_budget_mib = max(
                    1024,
                    int(available_ram_gb * 1024 * (cpu_percent / 100.0)),
                )
                memory_map["cpu"] = f"{ram_budget_mib}MiB"
        except Exception:
            pass

        return memory_map

    def _patch_bitsandbytes_params4bit(self) -> None:
        try:
            import bitsandbytes as bnb
        except Exception:
            return

        params_cls = getattr(getattr(bnb, "nn", None), "Params4bit", None)
        if params_cls is None:
            return

        if getattr(params_cls, "_cvmatch_patched", False):
            return

        has_arg = False
        try:
            sig = inspect.signature(params_cls.__new__)
            has_arg = "_is_hf_initialized" in sig.parameters
        except Exception:
            code = getattr(params_cls.__new__, "__code__", None)
            if code and "_is_hf_initialized" in code.co_varnames:
                has_arg = True

        if has_arg:
            return

        original_new = params_cls.__new__

        def _patched_new(cls, *args, **kwargs):
            kwargs.pop("_is_hf_initialized", None)
            return original_new(cls, *args, **kwargs)

        params_cls.__new__ = staticmethod(_patched_new)
        params_cls._cvmatch_patched = True
        logger.warning("Patched bitsandbytes Params4bit for _is_hf_initialized compat.")

    def _normalize_device_target(self, target: Any) -> Optional["torch.device"]:
        if not TORCH_AVAILABLE:
            return None
        if isinstance(target, torch.device):
            return target
        if isinstance(target, int):
            return torch.device(f"cuda:{target}")
        if isinstance(target, str):
            if target in ("cpu", "mps", "meta"):
                return torch.device("cpu")
            if target.startswith("cuda"):
                return torch.device(target)
            if target == "disk":
                return torch.device("cpu")
        return None

    def _resolve_input_device(self) -> Optional["torch.device"]:
        """Pick the input device matching the model's device map."""
        if not TORCH_AVAILABLE or self._model is None:
            return None

        try:
            embeddings = self._model.get_input_embeddings()
            if embeddings is not None and hasattr(embeddings, "weight"):
                weight = embeddings.weight
                if weight is not None and hasattr(weight, "device"):
                    device = weight.device
                    if hasattr(device, "type") and device.type != "meta":
                        return device
        except Exception:
            pass

        device_map = getattr(self._model, "hf_device_map", None)
        if isinstance(device_map, dict) and device_map:
            preferred_keys = (
                "model.embed_tokens",
                "model.decoder.embed_tokens",
                "transformer.wte",
                "model.wte",
                "gpt_neox.embed_in",
                "embed_tokens",
                "wte",
            )
            target = None
            for key in preferred_keys:
                if key in device_map:
                    target = device_map[key]
                    break
            if target is None:
                for key, value in device_map.items():
                    if "embed" in key.lower():
                        target = value
                        break
            if target is None:
                for value in device_map.values():
                    if value not in ("disk", "meta"):
                        target = value
                        break
            resolved = self._normalize_device_target(target)
            if resolved is not None:
                return resolved

        try:
            return torch.device("cuda" if torch.cuda.is_available() else "cpu")
        except Exception:
            return None

    def _summarize_device_map(self) -> Dict[str, int]:
        """Return a compact device map summary for logging."""
        summary: Dict[str, int] = {}
        device_map = getattr(self._model, "hf_device_map", None)
        if not isinstance(device_map, dict) or not device_map:
            return summary
        for value in device_map.values():
            resolved = self._normalize_device_target(value)
            if resolved is None:
                key = str(value)
            else:
                key = str(resolved) if resolved.type == "cuda" else resolved.type
            summary[key] = summary.get(key, 0) + 1
        return summary

    def _load_llama_cpp_model(self, progress_callback=None) -> None:
        """Démarre (si besoin) un serveur llama.cpp local pour un modèle GGUF."""
        try:
            from ..utils.llama_cpp_server import LlamaCppServer, LlamaCppServerConfig
            import os
        except Exception as exc:
            raise RuntimeError(
                "Support llama.cpp indisponible (dépendances manquantes)."
            ) from exc

        model_path_value = (
            (self.custom_parameters or {}).get("llama_cpp_model_path")
            or os.getenv("CVMATCH_LLAMA_CPP_MODEL_PATH")
            or self.model_name
        )
        model_path = Path(str(model_path_value)).expanduser()
        if not model_path.is_absolute():
            repo_root = Path(__file__).resolve().parents[2]
            model_path = repo_root / model_path

        binary_override = (
            (self.custom_parameters or {}).get("llama_cpp_binary_path")
            or (self.custom_parameters or {}).get("llama_cpp_binary")
            or os.getenv("CVMATCH_LLAMA_CPP_BINARY")
            or os.getenv("CVMATCH_LLAMA_CPP_BIN")
        )
        binary_path = Path(str(binary_override)).expanduser() if binary_override else None

        try:
            port = int((self.custom_parameters or {}).get("llama_cpp_port") or os.getenv("CVMATCH_LLAMA_CPP_PORT") or 8080)
        except Exception:
            port = 8080
        try:
            ctx_size = int((self.custom_parameters or {}).get("llama_cpp_ctx_size") or os.getenv("CVMATCH_LLAMA_CPP_CTX") or 4096)
        except Exception:
            ctx_size = 4096
        try:
            threads = int((self.custom_parameters or {}).get("llama_cpp_threads") or os.getenv("CVMATCH_LLAMA_CPP_THREADS") or (os.cpu_count() or 4))
        except Exception:
            threads = os.cpu_count() or 4

        cfg = LlamaCppServerConfig(
            model_path=model_path,
            port=port,
            ctx_size=ctx_size,
            threads=threads,
            binary_path=binary_path,
        )

        existing = getattr(self, "_llama_cpp_server", None)
        if existing and getattr(existing, "config", None) == cfg and (
            existing.is_alive() or existing.is_ready()
        ):
            self.model_loaded = True
            self._current_model_path = self.model_name
            return

        if existing:
            try:
                existing.stop()
            except Exception:
                pass

        server = LlamaCppServer(cfg)
        if progress_callback:
            progress_callback("🦙 Démarrage du serveur llama.cpp...")
        server.start(timeout_s=45.0)
        self._llama_cpp_server = server

        self.model_loaded = True
        self._current_model_path = self.model_name
        self._model = None
        self._tokenizer = None
        try:
            self._device = torch.device("cpu") if TORCH_AVAILABLE else None
        except Exception:
            self._device = None

        if progress_callback:
            progress_callback("✅ llama.cpp prêt !")

    def _llama_cpp_chat(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ) -> str:
        server = getattr(self, "_llama_cpp_server", None)
        if server is None:
            raise RuntimeError("llama.cpp server non initialisé")
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return server.chat(
            messages=messages,
            max_tokens=int(max_tokens),
            temperature=float(temperature),
            top_p=float(top_p),
        )

    def load_model(self, progress_callback=None, allow_fallback: bool = True):
        """Charge le modèle sélectionné avec optimisations automatiques."""
        # Backend llama.cpp (GGUF): ne dépend pas de Transformers et gère son propre chargement.
        if getattr(self, "current_loader", "transformers") == "llama_cpp":
            self._load_llama_cpp_model(progress_callback)
            return

        # Vérifier si le modèle actuel est différent de celui demandé
        if self.model_loaded and self._model is not None and self._current_model_path == self.model_name:
            logger.info(f"Modèle {self.model_name} déjà chargé en mémoire")
            return
        
        # Si on change de modèle, nettoyer l'ancien
        if self.model_loaded and self._current_model_path != self.model_name:
            logger.info(f"Changement de modèle: {self._current_model_path} -> {self.model_name}")
            self.cleanup_memory()
            self.model_loaded = False
            self._model = None
            self._tokenizer = None
        
        if not TRANSFORMERS_AVAILABLE:
            logger.warning("Transformers non disponible - Mode simulation")
            time.sleep(2)
            self.model_loaded = True
            self._current_model_path = self.model_name
            return
        
        try:
            # Vérifier si c'est le premier téléchargement
            self._check_first_download(progress_callback)
            
            if progress_callback:
                progress_callback("🔍 Détection du matériel disponible...")
            
            # Vérifier les optimisations hf_xet
            xet_status = model_optimizer.check_hf_xet_status()
            if xet_status["optimizations_active"]:
                logger.info("✅ Optimisations hf_xet actives pour téléchargements rapides")
            
            # Optimisation matérielle automatique
            model_size_gb = _estimate_model_size_gb(
                getattr(self, "model_name", None),
                getattr(self, "current_model_id", None),
            )
            try:
                self._optimization_config = gpu_manager.recommend_quantization(model_size_gb=model_size_gb)
            except TypeError:
                # Compat/mode mock
                self._optimization_config = gpu_manager.recommend_quantization()
            gpu_manager.optimize_for_inference()
            if TORCH_AVAILABLE and torch.cuda.is_available():
                try:
                    free_bytes, total_bytes = torch.cuda.mem_get_info()
                    logger.info(
                        "GPU memory before load: free=%.2fGB total=%.2fGB",
                        free_bytes / (1024**3),
                        total_bytes / (1024**3),
                    )
                except Exception:
                    pass
            if self.custom_parameters.get("force_4bit_nf4"):
                self._optimization_config["load_in_4bit"] = True
                self._optimization_config["load_in_8bit"] = False
                self._optimization_config["dtype"] = torch.float16
                self._optimization_config["quantization"] = "nf4"
                self._optimization_config["reason"] = "Forced 4-bit NF4"

            logger.info(f"Configuration optimale: {self._optimization_config['reason']}")

            # Vérification mémoire avant chargement (évite les crashs Access Violation)
            can_proceed, memory_error = self._check_memory_before_load()
            if not can_proceed:
                logger.error(memory_error)
                if progress_callback:
                    progress_callback(f"❌ {memory_error}")

                if allow_fallback:
                    try:
                        import psutil  # type: ignore

                        mem = psutil.virtual_memory()
                        available_ram_gb = mem.available / (1024**3)
                    except Exception:
                        available_ram_gb = 0.0

                    fallback = self._pick_fallback_model_for_memory(available_ram_gb)
                    if fallback and fallback.get("model_id") and fallback.get("model_path"):
                        previous_id = getattr(self, "current_model_id", None)
                        previous_model = self.model_name
                        self.model_name = fallback["model_path"]
                        self.current_model_id = fallback["model_id"]
                        self.model_loaded = False
                        self._model = None
                        self._tokenizer = None
                        self._current_model_path = None
                        self._optimization_config = None
                        note = (
                            f"[WARN] RAM insuffisante pour '{previous_id or previous_model}'. "
                            f"Fallback vers '{self.current_model_id}'."
                        )
                        self.last_model_resolution_note = note
                        logger.warning(note)
                        if progress_callback:
                            progress_callback(note)
                        return self.load_model(progress_callback, allow_fallback=False)

                raise MemoryError(memory_error)

            # Telechargement optimise du modele si necessaire
            model_display_name = getattr(
                self, "current_model_id", self.model_name.split("/")[-1]
            )
            model_path = self.model_name
            if progress_callback:
                progress_callback(
                    f"[DL] Verification/telechargement du modele {model_display_name}..."
                )

            try:
                model_path = model_optimizer.optimize_model_download(
                    self.model_name,
                    progress_callback=progress_callback,
                )
            except Exception as e:
                logger.warning(f"Telechargement optimise echoue, fallback standard: {e}")
                model_path = self.model_name

            if progress_callback:
                progress_callback(f"[TOK] Chargement du tokenizer {model_display_name}...")

            # Chargement du tokenizer
            # Prefer the resolved snapshot path to avoid partial-cache mismatches.
            model_ref = model_path or self.model_name
            try:
                self._tokenizer = AutoTokenizer.from_pretrained(
                    model_ref,
                    trust_remote_code=True,
                    use_fast=True,
                )
            except ImportError as e:
                # Certains tokenizers (ex: SentencePiece -> conversion fast) requierent protobuf.
                msg = str(e).lower()
                if "protobuf" in msg or "protob" in msg:
                    if progress_callback:
                        progress_callback(
                            "[WARN] Dependances manquantes (protobuf). Fallback: tokenizer lent (use_fast=False)..."
                        )
                    try:
                        self._tokenizer = AutoTokenizer.from_pretrained(
                            model_ref,
                            trust_remote_code=True,
                            use_fast=False,
                        )
                    except ImportError as e2:
                        msg2 = str(e2).lower()
                        if "sentencepiece" in msg2:
                            raise RuntimeError(
                                "Le tokenizer necessite 'sentencepiece'. Installez: pip install sentencepiece protobuf"
                            ) from e2
                        raise
                elif "sentencepiece" in msg:
                    raise RuntimeError(
                        "Le tokenizer necessite 'sentencepiece'. Installez: pip install sentencepiece"
                    ) from e
                else:
                    raise
            except Exception as e:
                msg = str(e).lower()
                if any(token in msg for token in ("vocabulary", "sentencepiece", "tokenizer")):
                    logger.warning(
                        "Tokenizer load failed, retrying with use_fast=False: %s", e
                    )
                    try:
                        self._tokenizer = AutoTokenizer.from_pretrained(
                            model_ref,
                            trust_remote_code=True,
                            use_fast=False,
                        )
                    except Exception as e2:
                        forced_path = None
                        try:
                            forced_path = model_optimizer.optimize_model_download(
                                self.model_name,
                                progress_callback=progress_callback,
                                force_download=True,
                            )
                        except Exception as force_exc:
                            logger.warning(
                                "Force download failed after tokenizer error: %s",
                                force_exc,
                            )
                        if forced_path:
                            model_ref = forced_path
                            self._tokenizer = AutoTokenizer.from_pretrained(
                                model_ref,
                                trust_remote_code=True,
                                use_fast=False,
                            )
                        else:
                            raise e2
                else:
                    raise

            if progress_callback:
                progress_callback(
                    f"[MODEL] Chargement du modele {model_display_name} ({self._optimization_config['reason']})..."
                )

            # Configuration de quantisation
            model_kwargs = {
                "trust_remote_code": True,
                "torch_dtype": self._optimization_config["dtype"],
            }
            force_gpu = False
            auto_kwargs: Optional[Dict[str, Any]] = None
            if self._optimization_config["device"] == "cuda":
                model_kwargs["device_map"] = "auto"
                max_memory = self._build_max_memory_map()
                if max_memory:
                    model_kwargs["max_memory"] = max_memory
                    model_kwargs["low_cpu_mem_usage"] = True

                force_gpu_env = os.getenv("CVMATCH_FORCE_GPU")
                if force_gpu_env is not None:
                    force_gpu = force_gpu_env.strip() == "1"
                else:
                    force_gpu = bool(self.custom_parameters.get("force_cuda"))
            else:
                model_kwargs["device_map"] = None

            # Ajout de la quantisation si necessaire
            if self._optimization_config.get("load_in_8bit") or self._optimization_config.get("load_in_4bit"):
                try:
                    import bitsandbytes  # noqa: F401
                    self._patch_bitsandbytes_params4bit()
                except Exception as e:
                    raise RuntimeError(
                        "Quantisation 4-bit/8-bit demandee mais 'bitsandbytes' n'est pas utilisable sur cette machine. "
                        "Installez une version compatible (CUDA) ou choisissez un modele/quantification plus leger."
                    ) from e

            if self._optimization_config.get("load_in_8bit"):
                model_kwargs["load_in_8bit"] = True
            elif self._optimization_config.get("load_in_4bit"):
                quantization_config = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_compute_dtype=torch.float16,
                    bnb_4bit_use_double_quant=True,
                    bnb_4bit_quant_type="nf4",
                    llm_int8_enable_fp32_cpu_offload=True,
                )
                model_kwargs["quantization_config"] = quantization_config

            if force_gpu and model_kwargs.get("device_map") == "auto":
                auto_kwargs = dict(model_kwargs)
                model_kwargs["device_map"] = {"": 0}
                model_kwargs.pop("max_memory", None)
                model_kwargs.pop("low_cpu_mem_usage", None)
                logger.info(
                    "Force GPU strict: device_map=cuda:0 (set CVMATCH_FORCE_GPU=0 to allow CPU offload)."
                )
            elif model_kwargs.get("device_map") == "auto" and model_kwargs.get("max_memory"):
                logger.info("Hybrid load: device_map=auto with CPU offload enabled.")

            def _load_with_kwargs(kwargs: Dict[str, Any]):
                try:
                    return AutoModelForCausalLM.from_pretrained(model_ref, **kwargs)
                except Exception as exc:
                    msg = str(exc)
                    if "Device cuda:0 is not recognized" in msg or "Device 0 is not recognized" in msg:
                        logger.warning(
                            "Retry model load with alternate max_memory keys: %s",
                            msg,
                        )
                        alt_kwargs = dict(kwargs)
                        max_memory = alt_kwargs.get("max_memory")
                        if max_memory:
                            alt_memory: Dict[Union[int, str], str] = {}
                            for key, value in max_memory.items():
                                if isinstance(key, int):
                                    alt_memory[f"cuda:{key}"] = value
                                elif isinstance(key, str) and key.startswith("cuda:"):
                                    suffix = key.split(":", 1)[1]
                                    try:
                                        alt_memory[int(suffix)] = value
                                    except Exception:
                                        alt_memory[key] = value
                                else:
                                    alt_memory[key] = value
                            alt_kwargs["max_memory"] = alt_memory
                            try:
                                return AutoModelForCausalLM.from_pretrained(
                                    model_ref,
                                    **alt_kwargs
                                )
                            except Exception:
                                alt_kwargs.pop("max_memory", None)
                                alt_kwargs.pop("low_cpu_mem_usage", None)
                                return AutoModelForCausalLM.from_pretrained(
                                    model_ref,
                                    **alt_kwargs
                                )
                        raise
                    if "meta tensors" in msg:
                        logger.warning(
                            "Retry model load without max_memory after meta tensor error: %s",
                            msg,
                        )
                        alt_kwargs = dict(kwargs)
                        alt_kwargs.pop("max_memory", None)
                        alt_kwargs.pop("low_cpu_mem_usage", None)
                        try:
                            return AutoModelForCausalLM.from_pretrained(
                                model_ref,
                                **alt_kwargs
                            )
                        except Exception:
                            if self._optimization_config["device"] == "cuda":
                                alt_kwargs["device_map"] = {"": 0}
                            return AutoModelForCausalLM.from_pretrained(
                                model_ref,
                                **alt_kwargs
                            )
                    raise

            # Chargement du modele
            try:
                self._model = _load_with_kwargs(model_kwargs)
            except Exception as exc:
                lowered = str(exc).lower()
                if auto_kwargs and ("cuda out of memory" in lowered or "out of memory" in lowered):
                    logger.warning(
                        "Forced GPU load failed (OOM). Retrying with device_map=auto."
                    )
                    try:
                        self.cleanup_memory()
                    except Exception:
                        pass
                    self._model = _load_with_kwargs(auto_kwargs)
                else:
                    raise
            # Configuration pour CPU si nécessaire
            if self._optimization_config["device"] == "cpu":
                self._model = self._model.to("cpu")
                self._device = torch.device("cpu")
            else:
                resolved_device = self._resolve_input_device()
                self._device = resolved_device or torch.device("cuda")
                logger.info("Device map resolved input device: %s", self._device)

            device_summary = self._summarize_device_map()
            if device_summary:
                logger.info("Device map summary: %s", device_summary)
                if self._optimization_config["device"] == "cuda":
                    has_cuda = any(str(key).startswith("cuda") for key in device_summary.keys())
                    if not has_cuda:
                        free_vram = 0.0
                        try:
                            free_vram = float(gpu_manager.get_available_vram())
                        except Exception:
                            free_vram = 0.0
                        logger.warning(
                            "GPU available but model loaded on CPU (free VRAM %.2fGB).",
                            free_vram,
                        )
                        if progress_callback:
                            progress_callback(
                                "[WARN] GPU VRAM low; model loaded on CPU."
                            )
            
            # Mode évaluation pour l'inférence
            self._model.eval()
            
            # Optimisations post-chargement
            if hasattr(torch, 'compile') and self._device.type == "cuda":
                should_compile = True
                device_map = getattr(self._model, "hf_device_map", None)
                if isinstance(device_map, dict) and device_map:
                    for value in device_map.values():
                        resolved = self._normalize_device_target(value)
                        if resolved is None:
                            continue
                        if resolved.type != "cuda":
                            should_compile = False
                            break
                if not should_compile:
                    logger.info("Skip torch.compile: device_map includes CPU/disk.")
                else:
                    try:
                        self._model = torch.compile(self._model, mode="reduce-overhead")
                        logger.info("Modèle compilé avec torch.compile")
                    except Exception as e:
                        logger.warning(f"Compilation échouée: {e}")
            
            self.model_loaded = True
            self._current_model_path = self.model_name
            
            # Stats mémoire finales
            memory_stats = gpu_manager.get_memory_stats()
            logger.info(f"Modèle {model_display_name} chargé - Mémoire utilisée: {memory_stats}")
            
            if progress_callback:
                progress_callback(f"✅ Modèle {model_display_name} chargé avec succès !")
            
        except Exception as e:
            error_msg = str(e)
            error_code = getattr(e, 'winerror', None) or ""
            lowered = error_msg.lower()

            # Si le chargement a échoué en OOM, tenter un fallback automatique (une seule fois).
            if allow_fallback and (
                isinstance(e, MemoryError)
                or "out of memory" in lowered
                or "cuda out of memory" in lowered
            ):
                try:
                    import psutil  # type: ignore

                    mem = psutil.virtual_memory()
                    available_ram_gb = mem.available / (1024**3)
                except Exception:
                    available_ram_gb = 0.0

                fallback = self._pick_fallback_model_for_memory(available_ram_gb)
                if fallback and fallback.get("model_id") and fallback.get("model_path"):
                    previous_id = getattr(self, "current_model_id", None)
                    previous_model = self.model_name
                    self.model_name = fallback["model_path"]
                    self.current_model_id = fallback["model_id"]
                    self.model_loaded = False
                    self._model = None
                    self._tokenizer = None
                    self._current_model_path = None
                    self._optimization_config = None
                    note = (
                        f"[WARN] OOM lors du chargement de '{previous_id or previous_model}'. "
                        f"Fallback vers '{self.current_model_id}'."
                    )
                    self.last_model_resolution_note = note
                    logger.warning(note)
                    if progress_callback:
                        progress_callback(note)
                    return self.load_model(progress_callback, allow_fallback=False)

            # Détecter ACCESS_VIOLATION ou cache corrompu (Windows)
            is_access_violation = (
                "-1073741819" in error_msg or
                "0xC0000005" in error_msg or
                "Access" in error_msg and "Violation" in error_msg or
                error_code == 1314  # WinError 1314 - symlink permission
            )

            if is_access_violation:
                logger.error(
                    "Cache modèle probablement corrompu (ACCESS_VIOLATION). "
                    "Exécutez: python scripts/fix_model_cache.py"
                )
                if progress_callback:
                    progress_callback("❌ Cache modèle corrompu détecté")
                    progress_callback("💡 Exécutez: python scripts/fix_model_cache.py")

            diagnostic_lines: List[str] = []
            diagnostic_lines.append(f"- model_id: {getattr(self, 'current_model_id', None)}")
            diagnostic_lines.append(f"- model_name: {getattr(self, 'model_name', None)}")
            try:
                opt = dict(self._optimization_config or {})
                dtype = opt.get("dtype")
                if dtype is not None:
                    opt["dtype"] = str(dtype)
                diagnostic_lines.append(f"- optimization: {opt}")
            except Exception:
                pass

            try:
                import psutil  # type: ignore

                mem = psutil.virtual_memory()
                diagnostic_lines.append(f"- ram_total_gb: {mem.total / (1024**3):.1f}")
                diagnostic_lines.append(f"- ram_available_gb: {mem.available / (1024**3):.1f}")
            except Exception:
                pass

            try:
                diagnostic_lines.append(f"- torch_available: {TORCH_AVAILABLE}")
                if TORCH_AVAILABLE:
                    diagnostic_lines.append(f"- torch_cuda_available: {torch.cuda.is_available()}")
            except Exception:
                pass

            try:
                diagnostic_lines.append(f"- gpu_info: {getattr(gpu_manager, 'gpu_info', None)}")
                if hasattr(gpu_manager, "get_available_vram"):
                    diagnostic_lines.append(
                        f"- vram_available_gb: {gpu_manager.get_available_vram():.1f}"
                    )
            except Exception:
                pass

            hint = ""
            lowered = error_msg.lower()
            if "cuda out of memory" in lowered or "out of memory" in lowered:
                hint = (
                    "Piste: mémoire GPU/RAM insuffisante. Fermez les applis qui utilisent le GPU, "
                    "ou choisissez un modèle plus léger / une quantisation 4-bit."
                )
            elif "protobuf" in lowered or "protob" in lowered:
                hint = (
                    "Piste: dépendance manquante 'protobuf'. Installez: pip install protobuf "
                    "(et souvent aussi: pip install sentencepiece), puis redémarrez l'application."
                )
            elif "sentencepiece" in lowered:
                hint = (
                    "Piste: dépendance manquante 'sentencepiece'. Installez: pip install sentencepiece "
                    "(et parfois aussi: pip install protobuf), puis redémarrez l'application."
                )
            elif "_is_hf_initialized" in lowered or "params4bit" in lowered:
                hint = (
                    "Piste: bitsandbytes trop ancien/incompatible pour la quantisation 4-bit. "
                    "Mettez a jour bitsandbytes (CUDA) ou changez de quantification."
                )
            elif "bitsandbytes" in lowered:
                hint = (
                    "Piste: 'bitsandbytes' manquant/incompatible. Réinstallez bitsandbytes (CUDA) "
                    "ou choisissez un modèle CPU plus petit."
                )

            logger.error(f"Erreur chargement modèle: {e}")
            if progress_callback:
                progress_callback("❌ Erreur chargement modèle (voir diagnostic)")
                if hint:
                    progress_callback(f"💡 {hint}")
            diagnostic_text = "\n".join(diagnostic_lines) if diagnostic_lines else "N/A"
            raise RuntimeError(
                f"Erreur chargement modèle: {e}\n\nDiagnostic:\n{diagnostic_text}"
                + (f"\n\n{hint}" if hint else "")
            ) from e
    
    def generate_cv(self, prompt: str, progress_callback=None, allow_fallback: bool = True) -> str:
        """Génère un CV basé sur le prompt avec Qwen2.5-32B."""
        if not self.model_loaded:
            self.load_model(progress_callback, allow_fallback=allow_fallback)

        if getattr(self, "current_loader", "transformers") == "llama_cpp":
            try:
                if progress_callback:
                    progress_callback("🦙 Génération du CV via llama.cpp...")

                system_prompt = self._cv_system_prompt()
                user_prompt = self._cv_user_prompt(prompt)

                model_hint = str(self.model_name or "").lower()
                max_tokens = 1024
                if any(x in model_hint for x in ["0.6", "0.5", "tiny", "1.1b"]):
                    max_tokens = 512
                elif any(x in model_hint for x in ["1.7", "1.5"]):
                    max_tokens = 768

                try:
                    ctx_size = int(getattr(getattr(self._llama_cpp_server, "config", None), "ctx_size", 4096))
                except Exception:
                    ctx_size = 4096
                max_tokens = min(int(max_tokens), max(256, int(ctx_size // 2)))

                generated_text = self._llama_cpp_chat(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=max_tokens,
                    temperature=0.7,
                    top_p=0.9,
                )
                cv_content = self._extract_cv_content(generated_text)
                if progress_callback:
                    progress_callback("✨ CV généré !")
                return cv_content
            except Exception as e:
                logger.error(f"Erreur generation CV (llama.cpp): {e}")
                if allow_fallback:
                    if progress_callback:
                        progress_callback("Warning: llama.cpp error - fallback enabled")
                    return self._generate_fallback_cv()
                return ""

        if not TRANSFORMERS_AVAILABLE or self._model is None:
            # Mode simulation si modèle indisponible
            return self._generate_fallback_cv() if allow_fallback else ""
        
        try:
            if progress_callback:
                progress_callback("📝 Préparation du prompt optimisé...")
            
            # Template de prompt optimisé pour Qwen2.5
            formatted_prompt = self._build_cv_prompt(prompt)
            
            # ═══════════════════════════════════════════════════════════════════
            # Configuration max_new_tokens par modèle et device
            # ═══════════════════════════════════════════════════════════════════
            # Règle : Les petits modèles CPU génèrent moins de tokens pour éviter
            # les blocages mémoire et accélérer la génération.
            #
            # MODÈLE                    | CPU tokens | GPU tokens | RAM requise
            # ─────────────────────────────────────────────────────────────────
            # Qwen2.5-0.5B / TinyLlama  |    512     |   1024     |   1.5 GB
            # Qwen3-1.7B                |    768     |   1536     |   4.0 GB
            # Phi-3-Mini (3.8B)         |    768     |   1536     |   8.0 GB
            # Qwen3-4B                  |   1024     |   2048     |   8.0 GB
            # Mistral-7B / Qwen3-8B     |   1024     |   2048     |  16.0 GB
            # Qwen3-14B                 |   1536     |   2048     |  32.0 GB
            # Qwen3-32B                 |   2048     |   2048     |  64.0 GB
            # ═══════════════════════════════════════════════════════════════════

            model_name_lower = self.model_name.lower()
            is_cpu = self._optimization_config.get("device") == "cpu"

            # Déterminer max_tokens selon le modèle
            if any(x in model_name_lower for x in ["0.6", "0.5", "tiny", "1.1b"]):
                # Qwen3-0.6B, Qwen2.5-0.5B, TinyLlama (1.1B)
                max_tokens = 512 if is_cpu else 1024
            elif any(x in model_name_lower for x in ["1.7", "1.5"]):
                # Qwen3-1.7B, Qwen2.5-1.5B
                max_tokens = 768 if is_cpu else 1536
            elif any(x in model_name_lower for x in ["phi-3", "phi3", "mini"]):
                # Phi-3-Mini (3.8B)
                max_tokens = 768 if is_cpu else 1536
            elif any(x in model_name_lower for x in ["3b", "4b"]):
                # Qwen3-4B, Qwen2.5-3B
                max_tokens = 1024 if is_cpu else 2048
            elif any(x in model_name_lower for x in ["7b", "8b", "mistral"]):
                # Mistral-7B, Qwen3-8B
                max_tokens = 1024 if is_cpu else 2048
            elif "14b" in model_name_lower:
                # Qwen3-14B
                max_tokens = 1536 if is_cpu else 2048
            elif "32b" in model_name_lower:
                # Qwen3-32B
                max_tokens = 2048  # Même en CPU (machine puissante requise)
            else:
                # Modèle inconnu - valeurs par défaut sécurisées
                max_tokens = 1024 if is_cpu else 2048

            # Budget tokens: adapter le prompt et la génération selon la limite réelle du modèle.
            # Récupérer max_position_embeddings depuis la config du modèle chargé.
            model_max_positions = 4096  # Valeur par défaut sécurisée
            try:
                if hasattr(self._model, "config") and hasattr(self._model.config, "max_position_embeddings"):
                    model_max_positions = int(self._model.config.max_position_embeddings)
                    logger.debug(f"Capacité modèle détectée: max_position_embeddings={model_max_positions}")
            except Exception as cfg_err:
                logger.warning(f"Impossible de lire max_position_embeddings: {cfg_err}")

            try:
                opt_max_len = int((self._optimization_config or {}).get("max_model_len") or 0)
            except Exception:
                opt_max_len = 0

            # Utiliser le minimum entre la config utilisateur et les capacités réelles du modèle
            max_total_len = min(opt_max_len or model_max_positions, model_max_positions)
            max_new_tokens_cap = min(max_tokens, max_total_len // 2)
            prompt_max_len = max(256, max_total_len - max_new_tokens_cap - 64)

            inputs = self._tokenizer(
                formatted_prompt,
                return_tensors="pt",
                truncation=True,
                max_length=prompt_max_len,
            ).to(self._device)

            input_len = int(inputs.input_ids.shape[1])
            allowed_new_tokens = max_total_len - input_len - 32
            if allowed_new_tokens > 0:
                max_tokens = min(max_tokens, max_new_tokens_cap, allowed_new_tokens)
            else:
                max_tokens = min(max_tokens, max_new_tokens_cap)

            device_label = "CPU" if is_cpu else "GPU"
            logger.info(f"Mode {device_label}: génération avec max_tokens={max_tokens} pour {self.model_name}")

            if progress_callback:
                progress_callback(f"🤖 Génération du CV (~{max_tokens} tokens max)...")

            # Génération avec paramètres optimisés
            with torch.no_grad():
                outputs = self._model.generate(
                    **inputs,
                    max_new_tokens=max_tokens,
                    temperature=0.7,
                    top_p=0.9,
                    top_k=50,
                    do_sample=True,
                    repetition_penalty=1.1,
                    pad_token_id=self._tokenizer.eos_token_id,
                    eos_token_id=self._tokenizer.eos_token_id,
                    use_cache=True
                )
            
            # Décodage de la réponse avec protection contre les débordements
            output_len = outputs[0].shape[0]
            input_slice_end = min(inputs.input_ids.shape[1], output_len)

            if output_len <= input_slice_end:
                # Aucun nouveau token généré - fallback
                logger.warning(f"Aucun nouveau token généré (output_len={output_len}, input_len={input_slice_end})")
                generated_text = ""
            else:
                generated_text = self._tokenizer.decode(
                    outputs[0][input_slice_end:],
                    skip_special_tokens=True
                )
            
            # Nettoyage et extraction du CV
            cv_content = self._extract_cv_content(generated_text)
            
            if progress_callback:
                progress_callback("✨ CV généré avec succès !")
            
            logger.info(f"CV généré - Longueur: {len(cv_content)} caractères")
            return cv_content
            
        except Exception as e:
            logger.error(f"Erreur generation CV: {e}")
            if allow_fallback:
                if progress_callback:
                    progress_callback("Warning: generation error - fallback enabled")
                return self._generate_fallback_cv()
            return ""
    
    def generate_structured_json(self, system_prompt: str, user_prompt: str, progress_callback=None) -> str:
        """Generate a structured JSON payload using the active LLM."""
        if not self.model_loaded:
            self.load_model(progress_callback)

        if getattr(self, "current_loader", "transformers") == "llama_cpp":
            try:
                if progress_callback:
                    progress_callback("[LLM] Structured JSON via llama.cpp...")

                try:
                    ctx_size = int(getattr(getattr(self._llama_cpp_server, "config", None), "ctx_size", 4096))
                except Exception:
                    ctx_size = 4096
                max_tokens = max(256, int(min(768, ctx_size // 2)))

                generated_text = self._llama_cpp_chat(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=max_tokens,
                    temperature=0.2,
                    top_p=0.9,
                )
                return self._extract_structured_content(generated_text)
            except Exception as e:
                logger.error(f"Erreur gÇ¸nÇ¸ration JSON (llama.cpp): {e}")
                return ""

        if not TRANSFORMERS_AVAILABLE or self._model is None:
            return ""

        try:
            if progress_callback:
                progress_callback("[LLM] Generating structured JSON...")

            formatted_prompt = self._build_generic_prompt(system_prompt, user_prompt)

            desired_new_tokens = 768
            try:
                opt_max_len = int((self._optimization_config or {}).get("max_model_len") or 0)
            except Exception:
                opt_max_len = 0
            max_total_len = min(opt_max_len or 4096, 4096)
            max_new_tokens_cap = min(desired_new_tokens, max_total_len // 2)
            prompt_max_len = max(256, max_total_len - max_new_tokens_cap - 64)
            prompt_max_len = min(prompt_max_len, 3072)

            inputs = self._tokenizer(
                formatted_prompt,
                return_tensors="pt",
                truncation=True,
                max_length=prompt_max_len,
            ).to(self._device)

            input_len = int(inputs.input_ids.shape[1])
            allowed_new_tokens = max_total_len - input_len - 32
            if allowed_new_tokens > 0:
                max_new_tokens = min(desired_new_tokens, max_new_tokens_cap, allowed_new_tokens)
            else:
                max_new_tokens = max_new_tokens_cap

            with torch.no_grad():
                outputs = self._model.generate(
                    **inputs,
                    max_new_tokens=max_new_tokens,
                    temperature=0.2,
                    top_p=0.9,
                    do_sample=False,
                    repetition_penalty=1.05,
                    pad_token_id=self._tokenizer.eos_token_id,
                    eos_token_id=self._tokenizer.eos_token_id,
                )

            generated_text = self._tokenizer.decode(
                outputs[0][inputs.input_ids.shape[1]:],
                skip_special_tokens=True,
            )

            return self._extract_structured_content(generated_text)
        except Exception as e:
            logger.error(f"Erreur gÇ¸nÇ¸ration JSON: {e}")
            return ""

    def _cv_system_prompt(self) -> str:
        return """Tu es un recruteur senior (HR) et expert ATS + redaction de CV.
Ta mission: produire un CV pre-rempli, parfaitement adapte a l'offre cible, que le candidat pourra relire et corriger.

Contraintes absolues:
- N'invente jamais de faits (dates, entreprises, diplomes, competences, outils, certifications, niveaux, liens).
- Utilise uniquement les informations presentes dans les DONNEES CANDIDAT fournies.
- Si une information manque, laisse le champ vide (pas de placeholder, pas d'hypothese).
- Pour l'identite et les contacts, utilise les donnees du candidat quand disponibles, sinon laisse vide.
- Adapte le contenu a l'offre (mots-cles, priorisation) sans inventer: tu peux reformuler et utiliser des synonymes si le sens reste vrai et verifiable.
- N'ajoute pas de competences non presentes dans les donnees (tu peux changer la formulation, pas le fond).
- L'offre cible est prioritaire pour la structure et les mots-cles (si valides).
- Format de sortie: uniquement du Markdown, sans explications, en respectant strictement la structure demandee.
- Style: concis, orienté impact, resultats mesurables quand disponibles."""

    def _cv_user_prompt(self, base_prompt: str) -> str:
        return f"""{base_prompt}

Genere le CV final en Markdown uniquement, conforme a la structure imposee."""

    def _build_cv_prompt(self, base_prompt: str) -> str:
        """Construit un prompt optimisé selon le type de modèle.

        Les modèles Qwen/Mistral/Phi supportent les tags <|im_start|>/<|im_end|>
        tandis que TinyLlama et autres modèles simples utilisent un format basique.
        """
        system_prompt = self._cv_system_prompt()
        user_prompt = self._cv_user_prompt(base_prompt)

        # Détecter le type de modèle pour adapter le format du prompt
        model_lower = self.model_name.lower() if hasattr(self, 'model_name') else ""

        # Modèles supportant les tags ChatML (<|im_start|>/<|im_end|>)
        supports_chatml = any(x in model_lower for x in ["qwen", "mistral", "phi"])

        if supports_chatml:
            # Format ChatML pour Qwen/Mistral/Phi
            formatted_prompt = f"<|im_start|>system\n{system_prompt}<|im_end|>\n<|im_start|>user\n{user_prompt}<|im_end|>\n<|im_start|>assistant\n"
        else:
            # Format simple pour TinyLlama et autres modèles basiques
            # Ces modèles ne comprennent pas les tags ChatML
            formatted_prompt = f"""Instructions: {system_prompt}

{user_prompt}

CV en Markdown:
"""

        return formatted_prompt

    def _build_generic_prompt(self, system_prompt: str, user_prompt: str) -> str:
        """Build a generic prompt with ChatML when supported."""
        model_lower = self.model_name.lower() if hasattr(self, "model_name") else ""
        supports_chatml = any(x in model_lower for x in ["qwen", "mistral", "phi"])

        if supports_chatml:
            return (
                f"<|im_start|>system\n{system_prompt}<|im_end|>\n"
                f"<|im_start|>user\n{user_prompt}<|im_end|>\n"
                f"<|im_start|>assistant\n"
            )

        return f"Instructions: {system_prompt}\n\n{user_prompt}\n\nAnswer:\n"

    def _extract_cv_content(self, generated_text: str) -> str:
        """Extrait et nettoie le contenu du CV généré."""
        # Nettoyage basique
        content = generated_text.strip()
        
        # Supprimer les balises de fin si présentes
        if "<|im_end|>" in content:
            content = content.split("<|im_end|>")[0]
        
        # S'assurer que le contenu commence par un titre
        if not content.startswith("#"):
            lines = content.split("\n")
            for i, line in enumerate(lines):
                if line.strip().startswith("#"):
                    content = "\n".join(lines[i:])
                    break
        
        return content.strip()
    
    def _generate_fallback_cv(self) -> str:
        """Génère un CV de fallback si le modèle principal échoue."""
        logger.info("Génération CV fallback...")
        time.sleep(2)  # Simulation
        
        return """# {name}

## Informations de contact
- Email: {email}
- Téléphone: {phone}
- LinkedIn: {linkedin}

## Profil professionnel
Professionnel expérimenté avec une solide expertise dans le domaine. Passionné par l'innovation et l'excellence, je recherche activement de nouveaux défis pour mettre à profit mes compétences et contribuer au succès de votre organisation.

## Expérience professionnelle

### Poste récent
**Entreprise** | Période
- Responsabilité principale adaptée au poste visé
- Accomplissement significatif avec résultats mesurables
- Collaboration inter-équipes et gestion de projets

### Expérience antérieure
**Entreprise précédente** | Période
- Mission clé en lien avec les exigences du poste
- Innovation ou amélioration apportée
- Formation et encadrement d'équipe

## Compétences techniques
- Compétence 1 en rapport avec l'offre
- Compétence 2 demandée dans l'annonce
- Compétence 3 différenciante
- Outils et technologies maîtrisés

## Formation
**Diplôme principal** | Institution | Année
**Formation complémentaire** | Organisme | Année

## Langues
- Français: Natif
- Anglais: Professionnel
- Autre langue selon le contexte

## Centres d'intérêt
Activités en lien avec le poste ou démontrant des soft skills pertinentes.
"""
    
    def generate_cover_letter(self, prompt: str, progress_callback=None) -> str:
        """Génère une lettre de motivation avec Qwen2.5-32B."""
        if not self.model_loaded:
            self.load_model(progress_callback)

        if getattr(self, "current_loader", "transformers") == "llama_cpp":
            try:
                if progress_callback:
                    progress_callback("🦙 Génération de la lettre via llama.cpp...")

                system_prompt = self._letter_system_prompt()
                user_prompt = self._letter_user_prompt(prompt)

                try:
                    ctx_size = int(getattr(getattr(self._llama_cpp_server, "config", None), "ctx_size", 4096))
                except Exception:
                    ctx_size = 4096
                max_tokens = max(256, int(min(768, ctx_size // 2)))

                generated_text = self._llama_cpp_chat(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=max_tokens,
                    temperature=0.8,
                    top_p=0.9,
                )
                letter_content = self._extract_letter_content(generated_text)
                if progress_callback:
                    progress_callback("✨ Lettre de motivation générée !")
                return letter_content
            except Exception as e:
                logger.error(f"Erreur génération lettre (llama.cpp): {e}")
                return self._generate_fallback_letter()
        
        if not TRANSFORMERS_AVAILABLE or self._model is None:
            return self._generate_fallback_letter()
        
        try:
            if progress_callback:
                progress_callback("💌 Génération de la lettre de motivation...")
            
            # Prompt spécifique pour la lettre
            letter_prompt = self._build_letter_prompt(prompt)

            # Budget tokens: adapter le prompt et la génération selon la limite recommandée.
            desired_new_tokens = 1024
            try:
                opt_max_len = int((self._optimization_config or {}).get("max_model_len") or 0)
            except Exception:
                opt_max_len = 0
            max_total_len = min(opt_max_len or 4096, 4096)
            max_new_tokens_cap = min(desired_new_tokens, max_total_len // 2)
            prompt_max_len = max(256, max_total_len - max_new_tokens_cap - 64)
            prompt_max_len = min(prompt_max_len, 3072)
             
            inputs = self._tokenizer(
                letter_prompt,
                return_tensors="pt",
                truncation=True,
                max_length=prompt_max_len
            ).to(self._device)

            input_len = int(inputs.input_ids.shape[1])
            allowed_new_tokens = max_total_len - input_len - 32
            if allowed_new_tokens > 0:
                max_new_tokens = min(desired_new_tokens, max_new_tokens_cap, allowed_new_tokens)
            else:
                max_new_tokens = max_new_tokens_cap
             
            with torch.no_grad():
                outputs = self._model.generate(
                    **inputs,
                    max_new_tokens=max_new_tokens,
                    temperature=0.8,
                    top_p=0.9,
                    do_sample=True,
                    repetition_penalty=1.1,
                    pad_token_id=self._tokenizer.eos_token_id,
                    eos_token_id=self._tokenizer.eos_token_id
                )
            
            generated_text = self._tokenizer.decode(
                outputs[0][inputs.input_ids.shape[1]:],
                skip_special_tokens=True
            )
            
            letter_content = self._extract_letter_content(generated_text)
            
            if progress_callback:
                progress_callback("✨ Lettre de motivation générée !")
            
            return letter_content
            
        except Exception as e:
            logger.error(f"Erreur génération lettre: {e}")
            return self._generate_fallback_letter()
    
    def _letter_system_prompt(self) -> str:
        return """Tu es un recruteur senior (HR) et expert en redaction de lettres de motivation.
Ta mission: produire une lettre 100% personnalisee pour l'offre cible, que le candidat pourra relire et corriger.

Contraintes absolues:
- N'invente jamais de faits (experiences, dates, entreprises, diplomes, competences, projets, chiffres, contacts).
- Utilise uniquement les informations presentes dans les DONNEES CANDIDAT fournies.
- Si une information necessaire manque, laisse le champ vide (pas de placeholder, pas d'hypothese).
- Tu peux reformuler et utiliser des synonymes/termes equivalents pour coller a l'offre, tant que le fond reste vrai et verifiable.
- Structure obligatoire: Objet, formule d'appel, 2-3 paragraphes, conclusion + formule de politesse.
- Longueur: maximum 1 page (court, dense, sans blabla).
- Style: professionnel, specifique a l'offre (mots-cles) sans phrases generiques.
- Sortie: texte uniquement (pas de Markdown, pas d'explications)."""

    def _letter_user_prompt(self, base_prompt: str) -> str:
        return f"""{base_prompt}

Genere la lettre finale (texte uniquement), en respectant la structure demandee."""

    def _build_letter_prompt(self, base_prompt: str) -> str:
        """Construit un prompt pour lettre de motivation."""
        system_prompt = self._letter_system_prompt()
        user_prompt = self._letter_user_prompt(base_prompt)
        return f"<|im_start|>system\n{system_prompt}<|im_end|>\n<|im_start|>user\n{user_prompt}<|im_end|>\n<|im_start|>assistant\n"
    
    def _extract_letter_content(self, generated_text: str) -> str:
        """Extrait le contenu de la lettre générée."""
        content = generated_text.strip()
        if "<|im_end|>" in content:
            content = content.split("<|im_end|>")[0]
        return content.strip()
    
    def _extract_structured_content(self, generated_text: str) -> str:
        content = generated_text.strip()
        if "<|im_end|>" in content:
            content = content.split("<|im_end|>")[0]
        return content.strip()

    def _generate_fallback_letter(self) -> str:
        """Génère une lettre de fallback."""
        return """Objet: Candidature pour le poste de [Titre du poste]

Madame, Monsieur,

Votre annonce pour le poste de [Titre du poste] a retenu toute mon attention. Fort(e) de mon expérience en [domaine], je suis convaincu(e) de pouvoir apporter une contribution significative à votre équipe.

Mon parcours m'a permis de développer des compétences solides en [compétences clés], particulièrement recherchées pour ce poste. Mon expérience chez [entreprise] où j'ai [réalisation], m'a préparé(e) aux défis que représente ce nouveau poste.

Ce qui m'attire particulièrement chez [Entreprise], c'est [élément spécifique à l'entreprise]. Je suis motivé(e) à l'idée de [contribution spécifique] et de participer au développement de vos projets innovants.

Je serais ravi(e) de vous rencontrer pour discuter de ma candidature et vous présenter plus en détail mon parcours et mes motivations.

Dans l'attente de votre retour, je vous prie d'agréer, Madame, Monsieur, mes salutations distinguées.

[Nom]"""
    
    def cleanup_memory(self):
        """Nettoie la mémoire GPU/CPU."""
        # Si un serveur llama.cpp tourne et qu'on change de modèle, arrêter l'ancien serveur.
        server = getattr(self, "_llama_cpp_server", None)
        if server is not None and getattr(self, "_current_model_path", None) != getattr(self, "model_name", None):
            try:
                server.stop()
            except Exception:
                pass
            self._llama_cpp_server = None
        try:
            import gc

            gc.collect()
        except Exception:
            pass
        if TORCH_AVAILABLE and torch.cuda.is_available():
            try:
                torch.cuda.empty_cache()
                if hasattr(torch.cuda, "ipc_collect"):
                    torch.cuda.ipc_collect()
            except Exception:
                pass
        logger.info("Mémoire nettoyée")


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
        from ..schemas.offer_keywords_schema import OfferKeywordsJSON
        from ..utils.json_strict import generate_json_with_schema

        messages = self._build_offer_keywords_messages()
        return generate_json_with_schema(
            role="offer_critic",
            schema_model=OfferKeywordsJSON,
            messages=messages,
            qwen_manager=self.qwen_manager,
            retries=3,
            progress_callback=progress_callback,
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

    def run(self):
        """Run the Extractor/Critic/Generator pipeline."""
        from ..utils.json_strict import JsonStrictError
        from ..utils.cv_json_renderer import cv_json_to_html, cv_json_to_markdown

        try:
            def progress_callback(message):
                self.progress_updated.emit(message)

            start_ts = time.time()
            logger.info(
                "Generation start: profile_id=%s template=%s",
                getattr(self.profile_data, "id", "unknown"),
                self.template,
            )

            self.qwen_manager._load_selected_model_config()
            note = getattr(self.qwen_manager, "last_model_resolution_note", None)
            if note:
                progress_callback(note)
                self.qwen_manager.last_model_resolution_note = None

            model_name = getattr(self.qwen_manager, "current_model_id", "IA")
            progress_callback(f"[MODEL] Initialisation {model_name}...")
            self.qwen_manager.load_model(progress_callback, allow_fallback=False)

            progress_callback("[EXTRACTOR] Building ProfileJSON...")
            logger.info("ProfileJSON build start")
            profile_json = self._build_profile_json()
            logger.info(
                "ProfileJSON build done: experiences=%s education=%s skills=%s projects=%s languages=%s",
                len(profile_json.get("experiences") or []),
                len(profile_json.get("education") or []),
                len(profile_json.get("skills") or []),
                len(profile_json.get("projects") or []),
                len(profile_json.get("languages") or []),
            )
            language_code = self._resolve_language_code()
            if isinstance(self.offer_data, dict):
                analysis = self.offer_data.get("analysis")
                if isinstance(analysis, dict) and analysis.get("language") != language_code:
                    updated = dict(analysis)
                    updated["language"] = language_code
                    self.offer_data["analysis"] = updated
                    logger.info("Offer language set to %s", language_code)

            offer_text = (
                self.offer_data.get("text") if isinstance(self.offer_data, dict) else ""
            )
            if offer_text and len(str(offer_text).strip()) >= 50:
                progress_callback("[OFFER] Extracting keywords...")
                logger.info("Offer keyword extraction start")
                try:
                    offer_keywords = self.generate_offer_keywords_json(
                        progress_callback=progress_callback,
                    )
                    self._merge_offer_keywords(offer_keywords)
                    logger.info(
                        "Offer keyword extraction done: keywords=%s skills=%s tools=%s",
                        len((offer_keywords or {}).get("keywords") or []),
                        len((offer_keywords or {}).get("skills") or []),
                        len((offer_keywords or {}).get("tools") or []),
                    )
                except JsonStrictError as exc:
                    logger.warning("Offer keyword extraction failed: %s", exc)
                except Exception as exc:
                    logger.warning("Offer keyword extraction error: %s", exc)

            progress_callback("[GENERATOR] Draft CVJSON...")
            logger.info("Draft CVJSON generation start")
            cv_json_draft = self.generate_cv_json_draft(
                profile_json=profile_json,
                progress_callback=progress_callback,
            )
            self._apply_contact_fallback(cv_json_draft, profile_json)
            self._apply_target_fallback(cv_json_draft)
            logger.info("Draft CVJSON generation done")

            try:
                from ..utils.cv_json_storage import save_cv_json_draft

                draft_path = save_cv_json_draft(
                    cv_json_draft,
                    profile_id=self.profile_data.id,
                    job_title=self.offer_data.get("job_title"),
                    company=self.offer_data.get("company"),
                )
                logger.info("Draft CVJSON saved: %s", draft_path)
            except Exception as exc:
                logger.warning("Draft CVJSON save failed: %s", exc)

            progress_callback("[RENDER] Draft HTML...")
            logger.info("Draft HTML render start")
            draft_html = cv_json_to_html(
                cv_json_draft, template=self.template, language=language_code
            )
            logger.info("Draft HTML render done: html_len=%s", len(draft_html or ""))

            progress_callback("[CRITIC] Reviewing draft...")
            logger.info("Critic JSON generation start")
            critic_json = self.generate_critic_json(
                cv_html=draft_html,
                progress_callback=progress_callback,
            )
            logger.info("Critic JSON generation done")

            progress_callback("[GENERATOR] Rewrite CVJSON...")
            logger.info("Final CVJSON generation start")
            cv_json_final = self.generate_cv_json_final(
                profile_json=profile_json,
                critic_json=critic_json,
                progress_callback=progress_callback,
            )
            self._apply_contact_fallback(cv_json_final, profile_json)
            self._apply_target_fallback(cv_json_final)
            self._merge_cv_json_missing_sections(cv_json_final, cv_json_draft)
            self._sanitize_cv_json_output(cv_json_final)
            self._repair_summary_if_needed(cv_json_final, cv_json_draft)
            progress_callback("[POST] Aligning keywords...")
            logger.info("Keyword alignment start")
            self._apply_keyword_alignment(cv_json_final, critic_json=critic_json)
            logger.info("Keyword alignment done")
            logger.info("Final CVJSON generation done")

            progress_callback("[RENDER] Final output...")
            logger.info("Final render start")
            cv_markdown = cv_json_to_markdown(cv_json_final, language=language_code)
            cv_html = cv_json_to_html(
                cv_json_final, template=self.template, language=language_code
            )
            logger.info(
                "Final render done: markdown_len=%s html_len=%s",
                len(cv_markdown or ""),
                len(cv_html or ""),
            )

            progress_callback("[LETTER] Generating cover letter...")
            logger.info("Cover letter generation start")
            letter_prompt = self.build_cover_letter_prompt()
            cover_letter = self.qwen_manager.generate_cover_letter(
                letter_prompt, progress_callback
            )
            logger.info("Cover letter generation done: length=%s", len(cover_letter or ""))

            progress_callback("[SAVE] Persisting application...")
            logger.info("Save application start")
            application = self.save_application(
                cv_markdown,
                cover_letter,
                profile_json=profile_json,
                critic_json=critic_json,
                cv_json_draft=cv_json_draft,
                cv_json_final=cv_json_final,
                cv_html=cv_html,
            )
            logger.info("Save application done: id=%s", getattr(application, "id", "unknown"))

            progress_callback("[CLEANUP] Releasing memory...")
            self.qwen_manager.cleanup_memory()

            result = {
                "application_id": application.id,
                "cv_markdown": cv_markdown,
                "cv_html": cv_html,
                "cover_letter": cover_letter,
                "cv_json_draft": cv_json_draft,
                "cv_json_final": cv_json_final,
                "critic_json": critic_json,
                "profile_json": profile_json,
                "template": self.template,
                "model_version": self.profile_data.model_version,
                "model_used": getattr(self.qwen_manager, "current_model_id", "unknown"),
                "gpu_used": gpu_manager.gpu_info["available"],
            }

            progress_callback("[OK] Generation complete.")
            self.generation_finished.emit(result)
            logger.info("Generation complete: elapsed=%.2fs", time.time() - start_ts)

        except JsonStrictError as exc:
            logger.error("Strict JSON pipeline failed: %s", exc)
            try:
                self.qwen_manager.cleanup_memory()
            except Exception:
                pass
            self.error_occurred.emit(str(exc))
        except Exception as e:
            logger.error(f"Erreur génération CV : {e}")
            try:
                self.qwen_manager.cleanup_memory()
            except Exception:
                pass
            self.error_occurred.emit(f"Erreur génération: {str(e)}")

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
