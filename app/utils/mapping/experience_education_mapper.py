"""Experience and education mapping helpers."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Tuple

from ...config import DEFAULT_PII_CONFIG
from ...logging.safe_logger import get_safe_logger


class ExperienceEducationMapper:
    """Encapsulates normalization logic for experience and education sections."""

    def __init__(self) -> None:
        self.logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)

    def map_experiences(
        self, experiences: Iterable[Any]
    ) -> Tuple[List[Dict[str, Any]], int]:
        mapped: List[Dict[str, Any]] = []
        errors = 0
        for index, item in enumerate(experiences or []):
            try:
                if isinstance(item, dict):
                    mapped_item = self.map_single_experience(item)
                    mapped.append(mapped_item)
                    self.logger.debug(
                        "  OK Exp %s: %s",
                        index + 1,
                        mapped_item.get("title", "No title"),
                    )
                else:
                    self.logger.debug("  SKIP Exp %s: non-dict input", index + 1)
                    errors += 1
            except Exception as exc:
                self.logger.error("  ERR Exp %s: %s", index + 1, exc)
                errors += 1
                if isinstance(item, dict) and item.get("title"):
                    mapped.append(item)
        return mapped, errors

    def map_single_experience(self, exp_data: Dict[str, Any]) -> Dict[str, Any]:
        self.logger.debug(
            "EXPERIENCE_MAPPER: mapping %s", exp_data.get("title", "Sans titre")
        )

        mapped: Dict[str, Any] = {}

        title = (
            exp_data.get("title")
            or exp_data.get("position")
            or exp_data.get("job_title")
            or "Poste à définir"
        )
        mapped["title"] = str(title).strip()

        company = (
            exp_data.get("company")
            or exp_data.get("employer")
            or exp_data.get("organization")
            or exp_data.get("enterprise")
        )
        if company and str(company).strip():
            mapped["company"] = str(company).strip()

        location = (
            exp_data.get("location")
            or exp_data.get("city")
            or exp_data.get("place")
            or exp_data.get("address")
        )
        if location and str(location).strip():
            mapped["location"] = str(location).strip()

        start_date = (
            exp_data.get("start_date")
            or exp_data.get("date_start")
            or exp_data.get("begin_date")
            or exp_data.get("from_date")
        )
        if start_date:
            mapped["start_date"] = self._normalize_date(start_date)

        end_date = (
            exp_data.get("end_date")
            or exp_data.get("date_end")
            or exp_data.get("finish_date")
            or exp_data.get("to_date")
        )
        if end_date:
            mapped["end_date"] = self._normalize_date(end_date)

        exp_type = (
            exp_data.get("experience_type")
            or exp_data.get("type")
            or exp_data.get("employment_type")
        )
        if exp_type:
            mapped["experience_type"] = self._map_experience_type(exp_type)

        confidence = exp_data.get("confidence") or "medium"
        mapped["confidence"] = self._normalize_confidence(confidence)

        description = (
            exp_data.get("description")
            or exp_data.get("summary")
            or exp_data.get("details")
            or exp_data.get("responsibilities")
        )
        if description:
            mapped["description"] = str(description).strip()

        achievements = (
            exp_data.get("achievements") or exp_data.get("accomplishments") or []
        )
        if achievements:
            mapped["achievements"] = self._normalize_list_field(achievements)

        skills_used = (
            exp_data.get("skills_used")
            or exp_data.get("skills")
            or exp_data.get("technologies")
            or []
        )
        if skills_used:
            mapped["skills_used"] = self._normalize_list_field(skills_used)

        for meta_field in [
            "source_lines",
            "extraction_method",
            "span_start",
            "span_end",
            "flags",
            "raw_text",
        ]:
            if meta_field in exp_data and exp_data[meta_field] is not None:
                mapped[meta_field] = exp_data[meta_field]

        self.logger.debug(
            "EXPERIENCE_MAPPER: mapped %s @ %s",
            mapped.get("title"),
            mapped.get("company", "N/A"),
        )
        return mapped

    def map_education(
        self, education_items: Iterable[Any]
    ) -> Tuple[List[Dict[str, Any]], int]:
        mapped: List[Dict[str, Any]] = []
        errors = 0
        for index, item in enumerate(education_items or []):
            try:
                if isinstance(item, dict):
                    mapped_item = self.map_single_education(item)
                    mapped.append(mapped_item)
                    self.logger.debug(
                        "  OK Edu %s: %s",
                        index + 1,
                        mapped_item.get("degree", "No degree"),
                    )
                else:
                    self.logger.debug("  SKIP Edu %s: non-dict input", index + 1)
                    errors += 1
            except Exception as exc:
                self.logger.error("  ERR Edu %s: %s", index + 1, exc)
                errors += 1
                if isinstance(item, dict) and (
                    item.get("degree") or item.get("institution")
                ):
                    mapped.append(item)
        return mapped, errors

    def map_single_education(self, edu_data: Dict[str, Any]) -> Dict[str, Any]:
        self.logger.debug(
            "EDUCATION_MAPPER: mapping %s", edu_data.get("degree", "Sans diplôme")
        )

        mapped: Dict[str, Any] = {}

        degree = (
            edu_data.get("degree")
            or edu_data.get("diploma")
            or edu_data.get("qualification")
            or edu_data.get("title")
            or "Formation à définir"
        )
        mapped["degree"] = str(degree).strip()

        institution = (
            edu_data.get("institution")
            or edu_data.get("school")
            or edu_data.get("university")
            or edu_data.get("college")
            or edu_data.get("establishment")
            or "Institution à définir"
        )
        mapped["institution"] = str(institution).strip()

        field_of_study = (
            edu_data.get("field_of_study")
            or edu_data.get("major")
            or edu_data.get("specialization")
            or edu_data.get("domain")
        )
        if field_of_study and str(field_of_study).strip():
            mapped["field_of_study"] = str(field_of_study).strip()

        location = (
            edu_data.get("location") or edu_data.get("city") or edu_data.get("place")
        )
        if location and str(location).strip():
            mapped["location"] = str(location).strip()

        start_year = edu_data.get("start_year") or edu_data.get("year_start")
        if start_year and self._is_valid_year(start_year):
            mapped["start_year"] = int(start_year)

        end_year = edu_data.get("end_year") or edu_data.get("year_end")
        if end_year and self._is_valid_year(end_year):
            mapped["end_year"] = int(end_year)

        year = edu_data.get("year") or edu_data.get("period")
        if year and str(year).strip():
            mapped["year"] = str(year).strip()

        education_level = edu_data.get("education_level") or edu_data.get("level")
        if education_level:
            mapped["education_level"] = self._normalize_education_level(education_level)

        grade = edu_data.get("grade") or edu_data.get("mention") or edu_data.get("gpa")
        if grade and str(grade).strip():
            mapped["grade"] = str(grade).strip()

        confidence = edu_data.get("confidence") or "medium"
        mapped["confidence"] = self._normalize_confidence(confidence)

        description = (
            edu_data.get("description")
            or edu_data.get("summary")
            or edu_data.get("details")
        )
        if description:
            mapped["description"] = str(description).strip()

        courses = edu_data.get("courses") or edu_data.get("subjects") or []
        if courses:
            mapped["courses"] = self._normalize_list_field(courses)

        achievements = edu_data.get("achievements") or edu_data.get("honors") or []
        if achievements:
            mapped["achievements"] = self._normalize_list_field(achievements)

        for meta_field in ["source_lines", "extraction_method", "raw_text"]:
            if meta_field in edu_data and edu_data[meta_field] is not None:
                mapped[meta_field] = edu_data[meta_field]

        self.logger.debug(
            "EDUCATION_MAPPER: mapped %s @ %s",
            mapped.get("degree"),
            mapped.get("institution"),
        )
        return mapped

    def _normalize_date(self, date_value: Any) -> str | None:
        if not date_value:
            return None

        date_str = str(date_value).strip()
        present_words = [
            "present",
            "présent",
            "actuel",
            "current",
            "ongoing",
            "now",
            "en cours",
        ]
        if any(word in date_str.lower() for word in present_words):
            return "present"

        date_str = re.sub(r"[^\d/\-\s]", "", date_str).strip()
        if not date_str:
            return None

        date_patterns = [
            (r"^\d{4}$", lambda m: m.group(0)),
            (r"^(\d{1,2})/(\d{4})$", lambda m: f"{int(m.group(1)):02d}/{m.group(2)}"),
            (
                r"^(\d{1,2})/(\d{1,2})/(\d{4})$",
                lambda m: f"{int(m.group(1)):02d}/{int(m.group(2)):02d}/{m.group(3)}",
            ),
            (r"^(\d{4})-(\d{1,2})$", lambda m: f"{int(m.group(2)):02d}/{m.group(1)}"),
            (
                r"^(\d{4})-(\d{1,2})-(\d{1,2})$",
                lambda m: f"{int(m.group(3)):02d}/{int(m.group(2)):02d}/{m.group(1)}",
            ),
        ]

        for pattern, formatter in date_patterns:
            match = re.match(pattern, date_str)
            if match:
                try:
                    formatted_date = formatter(match)
                    if self._is_valid_date_format(formatted_date):
                        return formatted_date
                except (ValueError, IndexError):
                    continue

        self.logger.debug("EXPERIENCE_MAPPER: unrecognised date '%s'", date_value)
        return date_str

    def _is_valid_date_format(self, date_str: str) -> bool:
        try:
            year_match = re.search(r"\b(\d{4})\b", date_str)
            if year_match:
                year = int(year_match.group(1))
                return 1990 <= year <= 2030
            return True
        except (ValueError, AttributeError):
            return False

    def _map_experience_type(self, exp_type: str) -> str | None:
        if not exp_type:
            return None

        exp_type_lower = str(exp_type).lower()
        type_mappings = {
            "full_time": ["full time", "temps plein", "permanent", "cdi"],
            "part_time": ["part time", "temps partiel", "mi-temps", "partiel"],
            "internship": ["internship", "stage", "intern", "stagiaire"],
            "freelance": ["freelance", "freelancer", "indépendant", "consultant"],
            "contract": ["contract", "contrat", "contractuel", "cdd", "mission"],
            "volunteer": ["volunteer", "bénévole", "volontaire", "bénévolat"],
            "project": ["project", "projet", "mission courte"],
        }

        for standard_type, aliases in type_mappings.items():
            if any(alias in exp_type_lower for alias in aliases):
                return standard_type

        return None

    def _normalize_confidence(self, confidence: Any) -> str:
        if not confidence:
            return "medium"

        conf_str = str(confidence).lower()
        if conf_str in {"high", "élevé", "élevée", "fort", "forte", "3"}:
            return "high"
        if conf_str in {"low", "faible", "bas", "basse", "1"}:
            return "low"
        if conf_str in {"unknown", "inconnu", "incertain", "0"}:
            return "unknown"
        return "medium"

    def _normalize_list_field(self, field_value: Any) -> List[str]:
        if not field_value:
            return []

        if isinstance(field_value, str):
            items = re.split(r"[,;\n]", field_value)
            return [item.strip() for item in items if item.strip()]

        if isinstance(field_value, list):
            cleaned: List[str] = []
            for item in field_value:
                if isinstance(item, str) and item.strip():
                    cleaned.append(item.strip())
                elif item:
                    cleaned.append(str(item).strip())
            return cleaned

        text = str(field_value).strip()
        return [text] if text else []

    def _is_valid_year(self, year_value: Any) -> bool:
        try:
            year = int(year_value)
            return 1990 <= year <= 2030
        except (ValueError, TypeError):
            return False

    def _normalize_education_level(self, level: Any) -> str:
        if not level:
            return "other"

        level_lower = str(level).lower()
        level_mappings = {
            "bac": ["bac", "baccalauréat", "high school"],
            "bac+2": ["bac+2", "bac +2", "bts", "dut", "deug"],
            "bac+3": ["bac+3", "bac +3", "licence", "bachelor", "but"],
            "bac+5": ["bac+5", "bac +5", "master", "ingénieur", "mba"],
            "doctorate": ["doctorat", "phd", "thèse", "doctorate"],
            "other": ["autre", "other", "formation", "certificat"],
        }

        for standard_level, aliases in level_mappings.items():
            if any(alias in level_lower for alias in aliases):
                return standard_level

        return "other"


__all__ = ["ExperienceEducationMapper"]
