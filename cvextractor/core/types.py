"""
Types et structures de données pour CVExtractor
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Union, Tuple
from datetime import datetime
from enum import Enum
import json


class ExtractionMethod(Enum):
    """Méthodes d'extraction utilisées"""

    REGEX = "regex"
    ML_CLASSIFIER = "ml_classifier"
    HEURISTIC = "heuristic"
    OCR = "ocr"
    LAYOUT_ANALYSIS = "layout_analysis"


class ConfidenceLevel(Enum):
    """Niveaux de confiance"""

    HIGH = "high"  # >0.8
    MEDIUM = "medium"  # 0.5-0.8
    LOW = "low"  # <0.5


@dataclass
class BoundingBox:
    """Rectangle de délimitation pour la provenance"""

    page: int
    x0: float
    y0: float
    x1: float
    y1: float

    def area(self) -> float:
        return (self.x1 - self.x0) * (self.y1 - self.y0)


@dataclass
class SourceProvenance:
    """Provenance d'un champ extrait"""

    page: int
    bbox: Optional[BoundingBox] = None
    method: ExtractionMethod = ExtractionMethod.HEURISTIC
    confidence: float = 0.5
    source_text: str = ""

    @property
    def confidence_level(self) -> ConfidenceLevel:
        if self.confidence >= 0.8:
            return ConfidenceLevel.HIGH
        elif self.confidence >= 0.5:
            return ConfidenceLevel.MEDIUM
        else:
            return ConfidenceLevel.LOW


@dataclass
class ExtractedField:
    """Champ extrait avec métadonnées"""

    value: Any
    provenance: SourceProvenance
    normalized_value: Any = None
    validation_status: str = "ok"
    warnings: List[str] = field(default_factory=list)


@dataclass
class ContactInfo:
    """Informations de contact"""

    email: Optional[ExtractedField] = None
    phone: Optional[ExtractedField] = None
    address: Optional[ExtractedField] = None
    city: Optional[ExtractedField] = None
    country: Optional[ExtractedField] = None
    linkedin: Optional[ExtractedField] = None
    github: Optional[ExtractedField] = None
    website: Optional[ExtractedField] = None


@dataclass
class PersonalInfo:
    """Informations personnelles"""

    first_name: Optional[ExtractedField] = None
    last_name: Optional[ExtractedField] = None
    full_name: Optional[ExtractedField] = None
    title: Optional[ExtractedField] = None
    summary: Optional[ExtractedField] = None


@dataclass
class Experience:
    """Expérience professionnelle"""

    title: Optional[ExtractedField] = None
    company: Optional[ExtractedField] = None
    location: Optional[ExtractedField] = None
    start_date: Optional[ExtractedField] = None
    end_date: Optional[ExtractedField] = None
    duration_months: Optional[ExtractedField] = None
    description: Optional[ExtractedField] = None
    technologies: List[ExtractedField] = field(default_factory=list)
    achievements: List[ExtractedField] = field(default_factory=list)


@dataclass
class Education:
    """Formation"""

    degree: Optional[ExtractedField] = None
    institution: Optional[ExtractedField] = None
    location: Optional[ExtractedField] = None
    start_date: Optional[ExtractedField] = None
    end_date: Optional[ExtractedField] = None
    grade: Optional[ExtractedField] = None
    field_of_study: Optional[ExtractedField] = None


@dataclass
class Skill:
    """Compétence"""

    name: ExtractedField
    category: Optional[ExtractedField] = None
    level: Optional[ExtractedField] = None
    years_experience: Optional[ExtractedField] = None


@dataclass
class Language:
    """Langue"""

    name: ExtractedField
    level: Optional[ExtractedField] = None
    proficiency_score: Optional[ExtractedField] = None


@dataclass
class Project:
    """Projet"""

    name: ExtractedField
    description: Optional[ExtractedField] = None
    url: Optional[ExtractedField] = None
    technologies: List[ExtractedField] = field(default_factory=list)
    start_date: Optional[ExtractedField] = None
    end_date: Optional[ExtractedField] = None


@dataclass
class Certification:
    """Certification"""

    name: ExtractedField
    issuer: Optional[ExtractedField] = None
    date: Optional[ExtractedField] = None
    expiry_date: Optional[ExtractedField] = None
    credential_id: Optional[ExtractedField] = None


@dataclass
class TextLine:
    """Individual text line with contact/header protection flags."""

    text: str
    line_idx: int
    is_contact: bool = False
    header_block: bool = False
    contact_types: List[str] = field(default_factory=list)
    confidence: float = 0.0
    bbox: Optional[BoundingBox] = None

    def is_protected(self) -> bool:
        """Check if line is protected from EXP/EDU extraction."""
        return self.is_contact or self.header_block


@dataclass
class CVSection:
    """Section générique du CV"""

    section_type: str
    title: str
    content: List[Dict[str, Any]]
    bbox: Optional[BoundingBox] = None
    confidence: float = 0.5
    # Add support for line-level contact protection
    text_lines: List[TextLine] = field(default_factory=list)


@dataclass
class ExtractionMetrics:
    """Métriques d'extraction"""

    total_pages: int
    ocr_pages: int = 0
    processing_time: float = 0.0
    sections_detected: int = 0
    fields_extracted: int = 0
    fields_with_high_confidence: int = 0
    completion_rate: float = 0.0
    warnings: List[str] = field(default_factory=list)


@dataclass
class ExtractionResult:
    """Résultat complet de l'extraction"""

    # Sections principales
    personal_info: PersonalInfo = field(default_factory=PersonalInfo)
    contact_info: ContactInfo = field(default_factory=ContactInfo)
    experiences: List[Experience] = field(default_factory=list)
    education: List[Education] = field(default_factory=list)
    skills: List[Skill] = field(default_factory=list)
    languages: List[Language] = field(default_factory=list)
    projects: List[Project] = field(default_factory=list)
    certifications: List[Certification] = field(default_factory=list)

    # Sections génériques pour extensions
    other_sections: List[CVSection] = field(default_factory=list)

    # Métadonnées
    source_file: str = ""
    detected_language: str = "unknown"
    extraction_date: datetime = field(default_factory=datetime.now)
    metrics: ExtractionMetrics = field(
        default_factory=lambda: ExtractionMetrics(total_pages=0)
    )

    def to_dict(self, include_provenance: bool = True) -> Dict[str, Any]:
        """Convertit en dictionnaire pour sérialisation"""
        result = {}

        for section_name in ["personal_info", "contact_info"]:
            section = getattr(self, section_name)
            result[section_name] = self._serialize_object(section, include_provenance)

        for section_name in [
            "experiences",
            "education",
            "skills",
            "languages",
            "projects",
            "certifications",
        ]:
            section_list = getattr(self, section_name)
            result[section_name] = [
                self._serialize_object(item, include_provenance)
                for item in section_list
            ]

        result["metrics"] = {
            "total_pages": self.metrics.total_pages,
            "ocr_pages": self.metrics.ocr_pages,
            "processing_time": self.metrics.processing_time,
            "completion_rate": self.metrics.completion_rate,
            "fields_extracted": self.metrics.fields_extracted,
        }

        return result

    def _serialize_object(self, obj, include_provenance: bool) -> Dict[str, Any]:
        """Sérialise un objet dataclass"""
        if obj is None:
            return None

        result = {}
        for field_name, field_value in obj.__dict__.items():
            if isinstance(field_value, ExtractedField):
                if include_provenance:
                    result[field_name] = {
                        "value": field_value.value,
                        "confidence": field_value.provenance.confidence,
                        "method": field_value.provenance.method.value,
                        "normalized_value": field_value.normalized_value,
                    }
                else:
                    result[field_name] = (
                        field_value.normalized_value or field_value.value
                    )
            elif isinstance(field_value, list):
                result[field_name] = [
                    self._serialize_object(item, include_provenance)
                    for item in field_value
                ]
            else:
                result[field_name] = field_value

        return result

    def to_json(self, include_provenance: bool = True) -> str:
        """Exporte en JSON"""
        return json.dumps(
            self.to_dict(include_provenance), indent=2, ensure_ascii=False, default=str
        )
