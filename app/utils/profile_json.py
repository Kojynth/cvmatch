from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from ..config import DEFAULT_PII_CONFIG
from ..logging.safe_logger import get_safe_logger
from .text_norm import normalize_text_for_ui

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)

MODEL_PATH = Path.cwd() / "schemas" / "profile_details_model.json"
SCHEMA_VERSION = "profile.v1"
PROFILE_CACHE_DIR = Path.cwd() / "logs" / "profile_json"

SECTION_FIELDS: Dict[str, List[str]] = {
    "personal_info": ["full_name", "email", "phone", "linkedin_url", "location"],
    "experiences": [
        "title",
        "company",
        "start_date",
        "end_date",
        "location",
        "description",
        "source",
    ],
    "education": [
        "school",
        "degree",
        "field_of_study",
        "start_date",
        "end_date",
        "grade",
        "source",
    ],
    "skills": ["name", "level"],
    "soft_skills": ["name", "level"],
    "languages": ["language", "proficiency"],
    "projects": ["name", "url", "technologies", "description"],
    "certifications": ["name", "organization", "date", "url"],
    "publications": ["title", "authors", "journal", "date", "url"],
    "volunteering": ["organization", "role", "period", "description"],
    "awards": ["name", "organization", "date", "description"],
    "references": ["name", "title", "company", "email", "phone"],
    "interests": [],
}

PROFILE_SECTIONS = [
    "personal_info",
    "experiences",
    "education",
    "skills",
    "soft_skills",
    "languages",
    "projects",
    "certifications",
    "publications",
    "volunteering",
    "awards",
    "references",
    "interests",
]

LIST_SECTIONS = [section for section in PROFILE_SECTIONS if section != "personal_info"]

DATE_RANGE_SPLIT = re.compile(r"\s*(?:-|\\u2013|\\u2014|to|au)\s*", re.IGNORECASE)
CEFR_RE = re.compile(r"\b(A1|A2|B1|B2|C1|C2)\b", re.IGNORECASE)
NATIVE_RE = re.compile(r"\b(native|natif)\b", re.IGNORECASE)
HEADER_TOKENS = {
    "experience",
    "experiences",
    "education",
    "formation",
    "formations",
    "competence",
    "competences",
    "skill",
    "skills",
    "project",
    "projects",
    "projet",
    "projets",
    "certification",
    "certifications",
    "language",
    "languages",
    "langue",
    "langues",
    "profil",
    "profile",
    "resume",
    "summary",
    "contact",
    "interet",
    "interets",
    "interest",
    "interests",
    "hobby",
    "hobbies",
    "award",
    "awards",
    "reference",
    "references",
    "volunteer",
    "volunteering",
    "publication",
    "publications",
}
CERT_KEYWORDS = {
    "certif",
    "certification",
    "certificate",
    "scrum master",
    "professional scrum",
    "tosa",
    "pix",
    "toeic",
    "toefl",
    "ielts",
    "pmp",
    "itil",
    "csm",
    "psm",
    "aws",
    "azure",
    "gcp",
    "google",
    "microsoft",
    "cisco",
    "oracle",
    "sap",
    "permis",
    "license",
    "licence",
}
INTEREST_HINTS = {
    "passion",
    "hobby",
    "loisir",
    "interest",
    "interet",
    "interets",
}
SKILL_SPLIT_RE = re.compile(r"\s*(?:,|;|\||•|·)\s*")
LINE_BREAK_RE = re.compile(r"[\r\n]+")
PAGE_HINT_RE = re.compile(r"^page\s*\d+", re.IGNORECASE)


def load_profile_json_model() -> Dict[str, Any]:
    if not MODEL_PATH.exists():
        return build_empty_profile_json()
    try:
        return json.loads(MODEL_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Unable to load profile JSON model: %s", exc)
        return build_empty_profile_json()


def build_empty_profile_json() -> Dict[str, Any]:
    data: Dict[str, Any] = {"schema_version": SCHEMA_VERSION}
    data["personal_info"] = {field: "" for field in SECTION_FIELDS["personal_info"]}
    for section in LIST_SECTIONS:
        data[section] = []
    return data


def normalize_profile_json(data: Dict[str, Any]) -> Dict[str, Any]:
    normalized = build_empty_profile_json()
    if not isinstance(data, dict):
        return normalized

    normalized["schema_version"] = str(data.get("schema_version") or SCHEMA_VERSION)

    personal = data.get("personal_info")
    if isinstance(personal, dict):
        for field in SECTION_FIELDS["personal_info"]:
            value = _clean_text(personal.get(field))
            if value:
                normalized["personal_info"][field] = value

    for section in LIST_SECTIONS:
        raw_items = data.get(section)
        if section == "interests":
            normalized["interests"] = _normalize_interests(raw_items)
            continue

        items = []
        for item in _as_list(raw_items):
            if not isinstance(item, dict):
                continue
            cleaned = {}
            for field in SECTION_FIELDS[section]:
                value = _clean_text(item.get(field))
                if value:
                    cleaned[field] = value
            if cleaned:
                items.append(cleaned)
        normalized[section] = items

    return normalized


def merge_profile_json(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    base_norm = normalize_profile_json(base)
    overlay_norm = normalize_profile_json(overlay)

    merged = build_empty_profile_json()
    merged["schema_version"] = overlay_norm.get("schema_version") or base_norm.get("schema_version")

    for field in SECTION_FIELDS["personal_info"]:
        merged["personal_info"][field] = overlay_norm["personal_info"].get(field) or base_norm["personal_info"].get(field) or ""

    for section in LIST_SECTIONS:
        overlay_list = overlay_norm.get(section, [])
        base_list = base_norm.get(section, [])
        merged[section] = _merge_section_items(section, base_list, overlay_list)

    return merged


def _merge_section_items(section: str, base_list: List[Any], overlay_list: List[Any]) -> List[Any]:
    if not overlay_list:
        return base_list
    if not base_list:
        return overlay_list
    if section == "interests":
        return _dedup_list(base_list + overlay_list)

    if section in {"experiences", "education"}:
        filtered_overlay = [item for item in overlay_list if _is_reasonable_section_item(section, item)]
        if not filtered_overlay:
            return base_list
        combined = base_list + filtered_overlay
        return _dedup_complex_section(section, combined)

    key = "name"
    if section == "languages":
        key = "language"
    elif section == "projects":
        key = "name"
    elif section == "certifications":
        key = "name"
    elif section == "publications":
        key = "title"
    elif section == "volunteering":
        key = "organization"
    elif section == "awards":
        key = "name"
    elif section == "references":
        key = "name"
    elif section == "skills":
        key = "name"
    elif section == "soft_skills":
        key = "name"
    return _dedup_items(base_list + overlay_list, key=key)


def _dedup_complex_section(section: str, items: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen = set()
    output: List[Dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if section == "experiences":
            key = "|".join(
                _normalize_for_match(item.get(field))
                for field in ("title", "company", "start_date", "end_date")
            )
        else:
            key = "|".join(
                _normalize_for_match(item.get(field))
                for field in ("school", "degree", "start_date", "end_date")
            )
        if not key.strip("|"):
            continue
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def _is_reasonable_section_item(section: str, item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    if section == "experiences":
        title = _clean_text(item.get("title"))
        company = _clean_text(item.get("company"))
        if not any([title, company, _clean_text(item.get("description"))]):
            return False
        if _looks_like_header(title) or _looks_like_header(company):
            return False
        if _too_long_inline(title, 140) or _too_long_inline(company, 140):
            return False
        return True
    if section == "education":
        school = _clean_text(item.get("school"))
        degree = _clean_text(item.get("degree"))
        if not any([school, degree, _clean_text(item.get("field_of_study"))]):
            return False
        if _looks_like_header(school) or _looks_like_header(degree):
            return False
        if _too_long_inline(school, 140) or _too_long_inline(degree, 140):
            return False
        return True
    return True


def has_profile_json_content(data: Dict[str, Any]) -> bool:
    if not isinstance(data, dict):
        return False
    personal = data.get("personal_info", {})
    if isinstance(personal, dict) and any(_clean_text(v) for v in personal.values()):
        return True
    for section in LIST_SECTIONS:
        items = data.get(section)
        if section == "interests":
            if _normalize_interests(items):
                return True
            continue
        if isinstance(items, list) and any(isinstance(item, dict) and item for item in items):
            return True
    return False


def apply_profile_json_to_profile(profile: Any, data: Dict[str, Any]) -> None:
    normalized = normalize_profile_json(data)
    if not hasattr(profile, "extracted_personal_info"):
        return

    existing_personal = getattr(profile, "extracted_personal_info", None) or {}
    merged_personal = dict(existing_personal)
    for field in SECTION_FIELDS["personal_info"]:
        value = _clean_text(normalized["personal_info"].get(field))
        if value:
            merged_personal[field] = value
    profile.extracted_personal_info = merged_personal

    attr_map = {
        "experiences": "extracted_experiences",
        "education": "extracted_education",
        "skills": "extracted_skills",
        "soft_skills": "extracted_soft_skills",
        "languages": "extracted_languages",
        "projects": "extracted_projects",
        "certifications": "extracted_certifications",
        "publications": "extracted_publications",
        "volunteering": "extracted_volunteering",
        "interests": "extracted_interests",
        "awards": "extracted_awards",
        "references": "extracted_references",
    }

    for section, attr in attr_map.items():
        value = normalized.get(section, [])
        if value:
            setattr(profile, attr, value)


def map_payload_to_profile_json(payload: Dict[str, Any], source: str = "") -> Dict[str, Any]:
    data = build_empty_profile_json()
    if not isinstance(payload, dict):
        return data

    data["personal_info"] = _extract_personal_info(payload)
    data["experiences"] = _map_experiences(_pick_payload_list(payload, ["experiences", "experience"]), source)
    data["education"] = _map_education(_pick_payload_list(payload, ["education", "educations"]), source)
    data["skills"] = _map_skills(payload.get("skills"))
    data["soft_skills"] = _map_soft_skills(payload.get("soft_skills"))
    data["languages"] = _map_languages(payload.get("languages"))
    data["projects"] = _map_projects(_pick_payload_list(payload, ["projects", "project"]))
    data["certifications"] = _map_certifications(_pick_payload_list(payload, ["certifications", "certification"]))
    data["publications"] = _map_publications(_pick_payload_list(payload, ["publications", "publication"]))
    data["volunteering"] = _map_volunteering(_pick_payload_list(payload, ["volunteering", "volunteer", "volunteers"]))
    data["awards"] = _map_awards(_pick_payload_list(payload, ["awards", "honors", "distinctions"]))
    data["references"] = _map_references(_pick_payload_list(payload, ["references", "recommendations"]))
    data["interests"] = _normalize_interests(_pick_payload_list(payload, ["interests", "hobbies"]))

    return normalize_profile_json(data)


def save_profile_json(data: Dict[str, Any], source: str) -> str:
    folder = Path.cwd() / "logs" / "profile_json"
    folder.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    safe_source = (source or "unknown").replace(" ", "_").lower()
    path = folder / f"profile_json_{safe_source}_{timestamp}.json"
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
    logger.info("Profile JSON saved: %s", path)
    return str(path)


def get_profile_json_cache_path(profile_id: int) -> Path:
    PROFILE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    safe_id = int(profile_id or 0)
    return PROFILE_CACHE_DIR / f"profile_json_profile_{safe_id}.json"


def save_profile_json_cache(profile_id: int, data: Dict[str, Any]) -> str:
    path = get_profile_json_cache_path(profile_id)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=True)
    logger.info("Profile JSON cache saved: %s", path)
    return str(path)


def load_profile_json_cache(profile_id: int) -> Dict[str, Any] | None:
    path = get_profile_json_cache_path(profile_id)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Unable to read profile JSON cache: %s", exc)
        return None
    normalized = normalize_profile_json(payload)
    if has_profile_json_content(normalized):
        return normalized
    return None


def build_profile_json_from_extracted_profile(profile: Any) -> Dict[str, Any]:
    personal_info = dict(getattr(profile, "extracted_personal_info", None) or {})
    if not personal_info.get("full_name"):
        personal_info["full_name"] = _clean_text(getattr(profile, "name", None))
    if not personal_info.get("email"):
        personal_info["email"] = _clean_text(getattr(profile, "email", None))
    if not personal_info.get("phone"):
        personal_info["phone"] = _clean_text(getattr(profile, "phone", None))
    if not personal_info.get("linkedin_url"):
        personal_info["linkedin_url"] = _clean_text(
            getattr(profile, "linkedin_url", None)
        )

    payload = {
        "personal_info": personal_info,
        "experiences": getattr(profile, "extracted_experiences", None) or [],
        "education": getattr(profile, "extracted_education", None) or [],
        "skills": getattr(profile, "extracted_skills", None) or [],
        "soft_skills": getattr(profile, "extracted_soft_skills", None) or [],
        "languages": getattr(profile, "extracted_languages", None) or [],
        "projects": getattr(profile, "extracted_projects", None) or [],
        "certifications": getattr(profile, "extracted_certifications", None) or [],
        "publications": getattr(profile, "extracted_publications", None) or [],
        "volunteering": getattr(profile, "extracted_volunteering", None) or [],
        "awards": getattr(profile, "extracted_awards", None) or [],
        "references": getattr(profile, "extracted_references", None) or [],
        "interests": getattr(profile, "extracted_interests", None) or [],
    }
    return normalize_profile_json(map_payload_to_profile_json(payload, source="profile"))


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    try:
        return normalize_text_for_ui(text)
    except Exception:
        return text


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _normalize_for_match(text: Any) -> str:
    value = _clean_text(text)
    if not value:
        return ""
    lowered = value.lower()
    normalized = unicodedata.normalize("NFKD", lowered)
    stripped = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    stripped = re.sub(r"[^a-z0-9+./ ]+", " ", stripped)
    return " ".join(stripped.split())


def _looks_like_header(text: Any) -> bool:
    normalized = _normalize_for_match(text)
    if not normalized:
        return False
    if normalized in HEADER_TOKENS:
        return True
    raw = _clean_text(text)
    if raw and raw.isupper() and len(raw) <= 24:
        return True
    return False


def _looks_like_noise(text: Any) -> bool:
    normalized = _normalize_for_match(text)
    if not normalized:
        return False
    if PAGE_HINT_RE.match(normalized):
        return True
    if normalized in {"curriculum vitae", "cv"}:
        return True
    return False


def _split_delimited_text(text: str) -> List[str]:
    if not text:
        return []
    if LINE_BREAK_RE.search(text):
        parts = []
        for line in LINE_BREAK_RE.split(text):
            line = line.strip()
            if not line:
                continue
            parts.extend(SKILL_SPLIT_RE.split(line))
    else:
        parts = SKILL_SPLIT_RE.split(text)
    return [part.strip() for part in parts if part.strip()]


@lru_cache(maxsize=1)
def _load_soft_skill_terms() -> List[str]:
    rules_path = Path(__file__).resolve().parents[1] / "rules" / "soft_skills.json"
    if not rules_path.exists():
        return []
    try:
        payload = json.loads(rules_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    terms = payload.get("soft_skills", [])
    if not isinstance(terms, list):
        return []
    normalized = {_normalize_for_match(term) for term in terms if term}
    return [term for term in normalized if term]


@lru_cache(maxsize=1)
def _load_soft_skill_set() -> set[str]:
    return set(_load_soft_skill_terms())


def _looks_like_soft_skill(text: Any) -> bool:
    normalized = _normalize_for_match(text)
    if not normalized:
        return False
    for term in _load_soft_skill_terms():
        if term and term in normalized:
            return True
    return False


def _is_soft_skill_exact(text: Any) -> bool:
    normalized = _normalize_for_match(text)
    if not normalized:
        return False
    return normalized in _load_soft_skill_set()


def _looks_like_certification(text: Any) -> bool:
    normalized = _normalize_for_match(text)
    if not normalized:
        return False
    return any(keyword in normalized for keyword in CERT_KEYWORDS)


def _is_certification_strong(text: Any) -> bool:
    normalized = _normalize_for_match(text)
    if not normalized:
        return False
    if _too_long_inline(text, 120) or _is_sentence_like(text, max_words=12):
        return False
    return any(keyword in normalized for keyword in CERT_KEYWORDS)


def _looks_like_interest(text: Any) -> bool:
    normalized = _normalize_for_match(text)
    if not normalized:
        return False
    return any(keyword in normalized for keyword in INTEREST_HINTS)


def _too_long_inline(text: Any, max_len: int) -> bool:
    value = _clean_text(text)
    if not value:
        return False
    return len(value) > max_len or "\n" in value or "\r" in value


def _is_sentence_like(text: Any, max_words: int = 14) -> bool:
    value = _clean_text(text)
    if not value:
        return False
    if value.count(".") >= 1:
        return True
    if len(value.split()) > max_words:
        return True
    return False


def _pick_payload_list(payload: Dict[str, Any], keys: Iterable[str]) -> List[Any]:
    for key in keys:
        if key in payload:
            return _as_list(payload.get(key))
    return []


def _pick_first(data: Dict[str, Any], keys: Iterable[str]) -> str:
    for key in keys:
        value = _clean_text(data.get(key))
        if value:
            return value
    return ""


def _split_date_range(value: Any, *, single_date_is_end: bool = False) -> Tuple[str, str]:
    text = _clean_text(value)
    if not text:
        return "", ""
    parts = DATE_RANGE_SPLIT.split(text, maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    # Single date fallback: choose start or end based on section expectations.
    if single_date_is_end:
        return "", text
    return text, ""


def _extract_personal_info(payload: Dict[str, Any]) -> Dict[str, str]:
    candidates = [
        payload.get("personal_info"),
        payload.get("contact_info"),
        payload.get("contact"),
        payload.get("basic_info"),
        payload.get("profile"),
    ]
    personal: Dict[str, Any] = {}
    for item in candidates:
        if isinstance(item, dict):
            personal = item
            break

    data = {field: "" for field in SECTION_FIELDS["personal_info"]}
    if not personal:
        return data

    data["full_name"] = _pick_first(personal, ["full_name", "name", "fullname"])
    data["email"] = _pick_first(personal, ["email", "mail"])
    data["phone"] = _pick_first(personal, ["phone", "telephone", "tel"])
    data["linkedin_url"] = _pick_first(personal, ["linkedin_url", "linkedin", "url", "profile_url"])
    data["location"] = _pick_first(personal, ["location", "city", "address", "city_country"])
    return data


def _map_experiences(raw_items: List[Any], source: str) -> List[Dict[str, str]]:
    items = []
    for item in raw_items:
        if isinstance(item, dict):
            title = _pick_first(item, ["title", "position", "role", "job_title"])
            company = _pick_first(item, ["company", "employer", "organization", "institution", "enterprise"])
            location = _pick_first(item, ["location", "city", "place"])
            description = _pick_first(item, ["description", "summary", "details", "responsibilities"])
            if not description:
                achievements = item.get("achievements") or item.get("accomplishments")
                if isinstance(achievements, list):
                    description = "\n".join(_clean_text(a) for a in achievements if _clean_text(a))
                elif achievements:
                    description = _clean_text(achievements)

            start_date = _pick_first(item, ["start_date", "date_start", "begin_date", "from_date"])
            end_date = _pick_first(item, ["end_date", "date_end", "finish_date", "to_date"])
            if not start_date and not end_date:
                # If a single date is provided for experience, treat it as the start date by default.
                start_date, end_date = _split_date_range(
                    _pick_first(item, ["dates", "date_range", "period"]),
                    single_date_is_end=False,
                )

            if not any([title, company, description]):
                continue

            mapped = {
                "title": title,
                "company": company,
                "start_date": start_date,
                "end_date": end_date,
                "location": location,
                "description": description,
            }
            src_value = _clean_text(item.get("source") or source)
            if src_value:
                mapped["source"] = src_value
            items.append(mapped)
            continue

        text = _clean_text(item)
        if text:
            mapped = {"title": text}
            if source:
                mapped["source"] = source
            items.append(mapped)

    return items


def _map_education(raw_items: List[Any], source: str) -> List[Dict[str, str]]:
    items = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        degree = _pick_first(item, ["degree", "diploma", "qualification", "title"])
        school = _pick_first(item, ["school", "institution", "university", "college"])
        field_of_study = _pick_first(item, ["field_of_study", "major", "specialization", "domain"])
        grade = _pick_first(item, ["grade", "gpa", "mention"])
        start_date = _pick_first(item, ["start_date", "start_year", "date_start", "begin_date"])
        end_date = _pick_first(item, ["end_date", "end_year", "date_end", "finish_date", "year"])
        if not start_date and not end_date:
            # Education entries often expose a single graduation year; treat it as the end date.
            start_date, end_date = _split_date_range(
                _pick_first(item, ["dates", "date_range", "period"]),
                single_date_is_end=True,
            )

        if not any([degree, school, field_of_study]):
            continue

        mapped = {
            "school": school,
            "degree": degree,
            "field_of_study": field_of_study,
            "start_date": start_date,
            "end_date": end_date,
            "grade": grade,
        }
        src_value = _clean_text(item.get("source") or source)
        if src_value:
            mapped["source"] = src_value
        items.append(mapped)
    return items


def _map_skills(raw_skills: Any) -> List[Dict[str, str]]:
    flattened: List[Any] = []
    if isinstance(raw_skills, dict):
        for value in raw_skills.values():
            flattened.extend(_as_list(value))
    else:
        flattened = _as_list(raw_skills)

    items: List[Dict[str, str]] = []
    for entry in flattened:
        if isinstance(entry, dict):
            nested = entry.get("items") or entry.get("skills") or entry.get("skills_list")
            if nested:
                flattened.extend(_as_list(nested))
                continue
            name = _pick_first(entry, ["name", "skill"])
            level = _pick_first(entry, ["level", "proficiency", "skill_level"])
        else:
            name = _clean_text(entry)
            level = ""

        if not name:
            continue
        items.append({"name": name, "level": level})

    return _dedup_items(items, key="name")


def _map_soft_skills(raw_soft_skills: Any) -> List[Dict[str, str]]:
    flattened: List[Any] = []
    if isinstance(raw_soft_skills, dict):
        for value in raw_soft_skills.values():
            flattened.extend(_as_list(value))
    else:
        flattened = _as_list(raw_soft_skills)

    items: List[Dict[str, str]] = []
    for entry in flattened:
        if isinstance(entry, dict):
            nested = entry.get("items") or entry.get("skills") or entry.get("skills_list")
            if nested:
                flattened.extend(_as_list(nested))
                continue
            name = _pick_first(entry, ["name", "skill"])
            level = _pick_first(entry, ["level", "proficiency", "skill_level"])
        else:
            name = _clean_text(entry)
            level = ""

        if not name:
            continue
        items.append({"name": name, "level": level})

    return _dedup_items(items, key="name")


def _map_languages(raw_languages: Any) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    for entry in _as_list(raw_languages):
        if isinstance(entry, dict):
            language = _pick_first(entry, ["language", "name"])
            proficiency = _pick_first(entry, ["proficiency", "level"])
        else:
            language, proficiency = _parse_language_string(_clean_text(entry))

        if not language:
            continue
        items.append({"language": language, "proficiency": proficiency})

    return _dedup_items(items, key="language")


def _parse_language_string(text: str) -> Tuple[str, str]:
    if not text:
        return "", ""
    level = ""
    level_match = CEFR_RE.search(text)
    if level_match:
        level = level_match.group(1).upper()
        text = CEFR_RE.sub("", text)
    elif NATIVE_RE.search(text):
        level = "Natif"
        text = NATIVE_RE.sub("", text)
    language = text.strip(" -:;|")
    return language, level


def _map_projects(raw_items: List[Any]) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        name = _pick_first(item, ["name", "title"])
        url = _pick_first(item, ["url", "link"])
        technologies = item.get("technologies") or item.get("tech_stack") or item.get("skills")
        if isinstance(technologies, list):
            technologies = ", ".join(_clean_text(t) for t in technologies if _clean_text(t))
        description = _pick_first(item, ["description", "summary", "details"])
        if not any([name, description, url]):
            continue
        items.append(
            {
                "name": name,
                "url": _clean_text(url),
                "technologies": _clean_text(technologies),
                "description": description,
            }
        )
    return items


def _map_certifications(raw_items: List[Any]) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            text = _clean_text(item)
            if text:
                items.append({"name": text})
            continue
        name = _pick_first(item, ["name", "title"])
        organization = _pick_first(item, ["organization", "issuer", "company"])
        date = _pick_first(item, ["date", "issued_date", "year"])
        url = _pick_first(item, ["url", "link"])
        if not name:
            continue
        items.append(
            {
                "name": name,
                "organization": organization,
                "date": date,
                "url": url,
            }
        )
    return items


def _map_publications(raw_items: List[Any]) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            text = _clean_text(item)
            if text:
                items.append({"title": text})
            continue
        title = _pick_first(item, ["title", "name"])
        authors = _pick_first(item, ["authors", "author"])
        journal = _pick_first(item, ["journal", "conference", "publisher"])
        date = _pick_first(item, ["date", "year"])
        url = _pick_first(item, ["url", "link"])
        if not title:
            continue
        items.append(
            {
                "title": title,
                "authors": authors,
                "journal": journal,
                "date": date,
                "url": url,
            }
        )
    return items


def _map_volunteering(raw_items: List[Any]) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        organization = _pick_first(item, ["organization", "company", "institution"])
        role = _pick_first(item, ["role", "title", "position"])
        period = _pick_first(item, ["period", "dates", "date_range"])
        if not period:
            start_date = _pick_first(item, ["start_date", "date_start"])
            end_date = _pick_first(item, ["end_date", "date_end"])
            if start_date or end_date:
                period = " - ".join(p for p in [start_date, end_date] if p)
        description = _pick_first(item, ["description", "summary", "details"])
        if not any([organization, role, description]):
            continue
        items.append(
            {
                "organization": organization,
                "role": role,
                "period": period,
                "description": description,
            }
        )
    return items


def _map_awards(raw_items: List[Any]) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            text = _clean_text(item)
            if text:
                items.append({"name": text})
            continue
        name = _pick_first(item, ["name", "title"])
        organization = _pick_first(item, ["organization", "issuer", "company"])
        date = _pick_first(item, ["date", "year"])
        description = _pick_first(item, ["description", "summary"])
        if not name:
            continue
        items.append(
            {
                "name": name,
                "organization": organization,
                "date": date,
                "description": description,
            }
        )
    return items


def _map_references(raw_items: List[Any]) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        name = _pick_first(item, ["name", "author"])
        title = _pick_first(item, ["title", "role", "relationship"])
        company = _pick_first(item, ["company", "organization", "employer"])
        email = _pick_first(item, ["email", "mail"])
        phone = _pick_first(item, ["phone", "telephone", "tel"])
        if not name and not title and not company:
            continue
        items.append(
            {
                "name": name,
                "title": title,
                "company": company,
                "email": email,
                "phone": phone,
            }
        )
    return items


def _normalize_interests(raw_items: Any) -> List[str]:
    interests: List[str] = []
    for item in _as_list(raw_items):
        if isinstance(item, dict):
            label = _pick_first(item, ["name", "label"])
            if label:
                interests.append(label)
            continue
        text = _clean_text(item)
        if text:
            interests.extend(part.strip() for part in text.split(",") if part.strip())
    return _dedup_list(interests)


def _dedup_items(items: List[Dict[str, str]], key: str) -> List[Dict[str, str]]:
    seen = set()
    output: List[Dict[str, str]] = []
    for item in items:
        value = _clean_text(item.get(key))
        if not value:
            continue
        norm = value.lower()
        if norm in seen:
            continue
        seen.add(norm)
        output.append(item)
    return output


def _dedup_list(items: List[str]) -> List[str]:
    seen = set()
    output = []
    for item in items:
        text = _clean_text(item)
        if not text:
            continue
        norm = text.lower()
        if norm in seen:
            continue
        seen.add(norm)
        output.append(text)
    return output


def _sanitize_llm_profile_json(data: Dict[str, Any]) -> Dict[str, Any]:
    cleaned = normalize_profile_json(data)
    for _ in range(3):
        snapshot = json.dumps(cleaned, sort_keys=True)
        cleaned = _sanitize_llm_profile_json_pass(cleaned)
        if json.dumps(cleaned, sort_keys=True) == snapshot:
            break
    return cleaned


def _sanitize_llm_profile_json_pass(cleaned: Dict[str, Any]) -> Dict[str, Any]:
    skills_out: List[Dict[str, str]] = []
    soft_out: List[Dict[str, str]] = []
    certs_out: List[Dict[str, str]] = []
    projects_out: List[Dict[str, str]] = []
    interests_out: List[str] = []

    for item in cleaned.get("skills", []):
        if not isinstance(item, dict):
            continue
        name = _clean_text(item.get("name"))
        level = _clean_text(item.get("level"))
        for part in _split_delimited_text(name) or [name]:
            if not part or _looks_like_header(part) or _looks_like_noise(part):
                continue
            if _looks_like_interest(part):
                interests_out.append(part)
                continue
            if _is_soft_skill_exact(part):
                soft_item = {"name": part}
                if level:
                    soft_item["level"] = level
                soft_out.append(soft_item)
                continue
            if _is_certification_strong(part):
                certs_out.append({"name": part})
                continue
            if _too_long_inline(part, 80) or _is_sentence_like(part, max_words=8):
                continue
            skills_out.append({"name": part, "level": level} if level else {"name": part})

    for item in cleaned.get("soft_skills", []):
        if not isinstance(item, dict):
            continue
        name = _clean_text(item.get("name"))
        level = _clean_text(item.get("level"))
        for part in _split_delimited_text(name) or [name]:
            if not part or _looks_like_header(part) or _looks_like_noise(part):
                continue
            if _looks_like_interest(part):
                interests_out.append(part)
                continue
            if _is_certification_strong(part):
                certs_out.append({"name": part})
                continue
            if _too_long_inline(part, 80) or _is_sentence_like(part, max_words=10):
                continue
            soft_out.append({"name": part, "level": level} if level else {"name": part})

    for item in cleaned.get("certifications", []):
        if not isinstance(item, dict):
            text = _clean_text(item)
            if text and _is_certification_strong(text):
                certs_out.append({"name": text})
            continue
        name = _clean_text(item.get("name"))
        if not name:
            continue
        if _looks_like_header(name) or _looks_like_noise(name):
            continue
        if _too_long_inline(name, 160) or _is_sentence_like(name, max_words=14):
            for part in _split_delimited_text(name):
                if not part or _looks_like_header(part):
                    continue
                if _is_certification_strong(part):
                    certs_out.append({"name": part})
            continue
        if not _is_certification_strong(name):
            if _looks_like_interest(name):
                interests_out.append(name)
            continue
        certs_out.append(
            {
                "name": name,
                "organization": _clean_text(item.get("organization")),
                "date": _clean_text(item.get("date")),
                "url": _clean_text(item.get("url")),
            }
        )

    for item in cleaned.get("projects", []):
        if not isinstance(item, dict):
            continue
        name = _clean_text(item.get("name"))
        if not name:
            continue
        parts = _split_delimited_text(name)
        if len(parts) > 1:
            for part in parts:
                if not part or _looks_like_header(part) or _looks_like_noise(part):
                    continue
                if _looks_like_interest(part):
                    interests_out.append(part)
                    continue
                if _is_soft_skill_exact(part):
                    soft_out.append({"name": part})
                    continue
                if _is_certification_strong(part):
                    certs_out.append({"name": part})
                    continue
                if _too_long_inline(part, 80) or _is_sentence_like(part, max_words=8):
                    continue
                projects_out.append({"name": part})
            continue
        if _looks_like_header(name) or _looks_like_noise(name):
            continue
        if _looks_like_interest(name):
            interests_out.append(name)
            continue
        if _is_soft_skill_exact(name):
            soft_out.append({"name": name})
            continue
        if _is_certification_strong(name):
            certs_out.append({"name": name})
            continue
        if _too_long_inline(name, 140) or _is_sentence_like(name, max_words=16):
            continue
        projects_out.append(
            {
                "name": name,
                "url": _clean_text(item.get("url")),
                "technologies": _clean_text(item.get("technologies")),
                "description": _clean_text(item.get("description")),
            }
        )

    for entry in cleaned.get("interests", []):
        if _looks_like_header(entry) or _looks_like_noise(entry):
            continue
        interests_out.append(_clean_text(entry))

    cleaned["skills"] = _dedup_items(skills_out, key="name")
    cleaned["soft_skills"] = _dedup_items(soft_out, key="name")
    cleaned["certifications"] = _dedup_items(certs_out, key="name")
    cleaned["projects"] = _dedup_items(projects_out, key="name")
    cleaned["interests"] = _dedup_list(interests_out)
    return cleaned


def build_profile_json_from_source(
    payload: Dict[str, Any] | None = None,
    raw_text: str | None = None,
    source: str = "",
    max_chars: int = 8000,
) -> Dict[str, Any]:
    base = map_payload_to_profile_json(payload or {}, source)
    text = _clean_text(raw_text) or _payload_to_text(payload, max_chars=max_chars)
    llm_data = extract_profile_json_with_llm(text, source, max_chars=max_chars)
    if has_profile_json_content(llm_data):
        llm_data = _sanitize_llm_profile_json(llm_data)
        return normalize_profile_json(merge_profile_json(base, llm_data))
    return base


def _prepare_profile_chunks(
    source_text: str,
    *,
    max_chars: int = 8000,
    max_block_chars: int = 2200,
    max_blocks: int = 6,
) -> List[str]:
    from .text_chunking import split_text_blocks

    text = _clean_text(source_text)
    if not text:
        return []
    if max_chars and len(text) > max_chars:
        head_size = max_chars // 2
        tail_size = max_chars - head_size
        head = text[:head_size].strip()
        tail = text[-tail_size:].strip()
        text = "\n\n".join(part for part in (head, tail) if part)

    return split_text_blocks(
        text, max_block_chars=max_block_chars, max_blocks=max_blocks
    )


def _extract_profile_json_with_llm_single(
    source_text: str,
    source: str,
) -> Dict[str, Any]:
    text = _clean_text(source_text)
    if not text:
        return {}
    system_prompt, user_prompt = _build_llm_prompts(text, source)
    from ..schemas.profile_schema import ProfileJSON
    from ..utils.json_strict import generate_json_with_schema
    from ..workers.llm_worker import QwenManager

    qwen = QwenManager()
    parsed = generate_json_with_schema(
        role="extractor",
        schema_model=ProfileJSON,
        messages={"system": system_prompt, "user": user_prompt},
        qwen_manager=qwen,
        retries=3,
    )
    return normalize_profile_json(parsed)


def extract_profile_json_with_llm(
    source_text: str,
    source: str,
    max_chars: int = 8000,
) -> Dict[str, Any]:
    chunks = _prepare_profile_chunks(source_text, max_chars=max_chars)
    if not chunks:
        return {}

    merged = build_empty_profile_json()
    for chunk in chunks:
        partial = _extract_profile_json_with_llm_single(chunk, source)
        if has_profile_json_content(partial):
            merged = merge_profile_json(merged, partial)
    return normalize_profile_json(merged)


def _payload_to_text(payload: Dict[str, Any] | None, max_chars: int) -> str:
    if not payload:
        return ""
    try:
        text = json.dumps(payload, indent=2, ensure_ascii=True)
    except Exception:
        text = str(payload)
    return text[:max_chars]


def _build_llm_prompts(source_text: str, source: str) -> Tuple[str, str]:
    source_label = (source or "source").lower()
    model = load_profile_json_model()
    model_text = json.dumps(model, indent=2, ensure_ascii=True)

    system_prompt = (
        "You are a data extraction engine. Return JSON only. "
        "Follow the exact keys and structure from the JSON model."
    )
    user_prompt = (
        "Extract profile data from the SOURCE_TEXT (may be a partial chunk) and return JSON matching the model. "
        "Rules: do not invent data, use empty strings for unknown scalar fields, "
        "use empty arrays when no items exist, and set 'source' to 'cv' or 'linkedin' "
        "for experiences and education when possible. "
        "Do not include section headers (e.g., Experience, Skills) as items. "
        "Each list item must be atomic and short (no full paragraphs). "
        "Use 'soft_skills' only for interpersonal traits; keep technical skills in 'skills'. "
        "Use 'certifications' only for certificates/licenses (short names). "
        "Use 'projects' only for actual projects; do not put skills or certifications there.\n\n"
        f"JSON_MODEL:\n{model_text}\n\n"
        f"SOURCE: {source_label}\n"
        f"SOURCE_TEXT:\n{source_text}\n\n"
        "Return JSON only."
    )
    return system_prompt, user_prompt


def _parse_json_response(text: str) -> Dict[str, Any]:
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
        return {}
    candidate = cleaned[start : end + 1]
    try:
        return json.loads(candidate)
    except Exception:
        return {}
