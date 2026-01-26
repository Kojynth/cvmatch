"""
Configuration pour CVExtractor
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
import os


@dataclass
class ExtractionConfig:
    """Configuration de l'extraction"""

    # Langues supportées
    supported_languages: List[str] = field(
        default_factory=lambda: [
            "fr",
            "en",
            "de",
            "es",
            "pt",
            "it",
            "nl",
            "pl",
            "ro",
            "tr",
            "ja",
            "ar",
        ]
    )

    # OCR
    enable_ocr: bool = True
    ocr_languages: List[str] = field(
        default_factory=lambda: ["eng", "fra", "deu", "spa"]
    )
    ocr_confidence_threshold: float = 0.6

    # Segmentation
    section_confidence_threshold: float = 0.5
    use_ml_classifier: bool = True

    # Extraction
    field_confidence_threshold: float = 0.3
    enable_fuzzy_matching: bool = True

    # Normalisation
    normalize_dates: bool = True
    normalize_phones: bool = True
    validate_emails: bool = True

    # Performance
    max_processing_time: float = 30.0  # secondes
    max_memory_mb: int = 512

    # Chemins
    models_dir: str = field(
        default_factory=lambda: os.path.join(os.path.dirname(__file__), "..", "models")
    )
    tesseract_cmd: Optional[str] = None  # Auto-détection

    # Mapping des sections (personnalisable)
    section_aliases: Dict[str, List[str]] = field(
        default_factory=lambda: {
            "personal_info": [
                "personal information",
                "informations personnelles",
                "persönliche daten",
                "datos personales",
                "informazioni personali",
            ],
            "experience": [
                "experience",
                "work experience",
                "professional experience",
                "expérience",
                "expérience professionnelle",
                "berufserfahrung",
                "experiencia laboral",
                "esperienza lavorativa",
            ],
            "education": [
                "education",
                "formation",
                "ausbildung",
                "educación",
                "istruzione",
                "academic background",
                "études",
                "formación académica",
            ],
            "skills": [
                "skills",
                "compétences",
                "fähigkeiten",
                "habilidades",
                "competenze",
                "technical skills",
                "core competencies",
            ],
            "languages": ["languages", "langues", "sprachen", "idiomas", "lingue"],
            "projects": ["projects", "projets", "projekte", "proyectos", "progetti"],
            "certifications": [
                "certifications",
                "certificates",
                "certifications",
                "zertifikate",
                "certificaciones",
                "certificati",
            ],
            "interests": [
                "interests",
                "hobbies",
                "centres d'intérêt",
                "loisirs",
                "interessen",
                "intereses",
                "interessi",
            ],
        }
    )

    # Patterns regex par langue
    date_patterns: Dict[str, List[str]] = field(
        default_factory=lambda: {
            "fr": [
                r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})\b",  # DD/MM/YYYY
                r"\b(\d{1,2})\s+(janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s+(\d{4})\b",
                r"\b(\d{4})\s*[-–—]\s*(\d{4})\b",  # 2019-2021
                r"\bdepuis\s+(\d{4})\b",
            ],
            "en": [
                r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})\b",  # MM/DD/YYYY
                r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})\b",
                r"\b(\d{4})\s*[-–—]\s*(\d{4})\b",
                r"\bsince\s+(\d{4})\b",
            ],
        }
    )

    email_pattern: str = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
    phone_patterns: List[str] = field(
        default_factory=lambda: [
            r"\+33[\s\d\.\-]{8,}",  # France
            r"\+1[\s\d\.\-]{10,}",  # US/Canada
            r"\+49[\s\d\.\-]{10,}",  # Allemagne
            r"\b0[1-9][\s\d\.\-]{8,}\b",  # Format local
        ]
    )

    def get_section_aliases(self, section_type: str) -> List[str]:
        """Retourne les alias d'une section"""
        return self.section_aliases.get(section_type, [section_type])

    def get_date_patterns(self, language: str) -> List[str]:
        """Retourne les patterns de date pour une langue"""
        return self.date_patterns.get(language, self.date_patterns.get("en", []))
