"""
Enhanced Normalization with CEFR Mapping
========================================

Comprehensive normalization for dates, languages, and text fields with
CEFR language level mapping and field contamination cleaning.
"""

import re
import logging
from typing import Dict, List, Any, Optional, Union, Tuple
from datetime import datetime, date
from dataclasses import dataclass
from enum import Enum

from ..utils.log_safety import create_safe_logger_wrapper
from ..metrics.instrumentation import get_metrics_collector


class DatePresence(Enum):
    """Date presence indicators."""

    PRESENT = "PRESENT"
    ONGOING = "ONGOING"
    CURRENT = "CURRENT"


class CEFRLevel(Enum):
    """Common European Framework of Reference language levels."""

    A1 = "A1"  # Beginner
    A2 = "A2"  # Elementary
    B1 = "B1"  # Intermediate
    B2 = "B2"  # Upper-Intermediate
    C1 = "C1"  # Advanced
    C2 = "C2"  # Proficient
    NATIVE = "NATIVE"  # Native speaker


@dataclass
class NormalizedField:
    """Normalized field result."""

    original_value: str
    normalized_value: str
    confidence: float = 1.0
    notes: List[str] = None

    def __post_init__(self):
        if self.notes is None:
            self.notes = []


@dataclass
class DateNormalizationResult:
    """Result of date normalization."""

    original: str
    normalized: str
    format_type: str  # iso_month, iso_date, present, range
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    is_present: bool = False
    confidence: float = 1.0


@dataclass
class LanguageSkillResult:
    """Result of language skill normalization."""

    language: str
    cefr_level: CEFRLevel
    proficiency_description: str
    confidence: float
    original_text: str


class EnhancedNormalizer:
    """Enhanced normalizer with date and CEFR language mapping."""

    def __init__(self, debug_mode: bool = False):
        self.debug_mode = debug_mode

        # Logger
        base_logger = logging.getLogger(__name__)
        self.logger = create_safe_logger_wrapper(base_logger)

        # Compile patterns
        self._compile_patterns()

        # CEFR mappings
        self._setup_cefr_mappings()

    def _compile_patterns(self):
        """Compile regex patterns for normalization."""

        # French present indicators
        self.french_present_patterns = [
            r"\b(?:a\s+ce\s+jour|actuellement|en\s+cours|present|actuel|maintenant)\b",
            r"\b(?:jusqu[\'\']?a\s+(?:present|aujourd[\'\']?hui|maintenant))\b",
            r"\b(?:depuis.*?(?:et\s+se\s+poursuit|continue|en\s+cours))\b",
        ]

        # English present indicators
        self.english_present_patterns = [
            r"\b(?:present|current|ongoing|now|today|currently)\b",
            r"\b(?:to\s+(?:present|date|now)|until\s+(?:present|now))\b",
            r"\b(?:since.*?(?:and\s+ongoing|continuing|current))\b",
        ]

        # Date range patterns
        self.date_range_patterns = [
            # French patterns
            r"(?P<start>\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})\s*(?:au|a|–|-|jusqu[\'\']?a)\s*(?P<end>\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}|present|actuellement)",
            r"(?P<start>\d{4})\s*(?:au|a|–|-|jusqu[\'\']?a)\s*(?P<end>\d{4}|present|actuellement)",
            r"(?P<start>(?:janvier|fevrier|mars|avril|mai|juin|juillet|aout|septembre|octobre|novembre|decembre)\s+\d{4})\s*(?:au|a|–|-|jusqu[\'\']?a)\s*(?P<end>(?:janvier|fevrier|mars|avril|mai|juin|juillet|aout|septembre|octobre|novembre|decembre)\s+\d{4}|present)",
            # English patterns
            r"(?P<start>\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})\s*(?:to|–|-|until)\s*(?P<end>\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}|present|current)",
            r"(?P<start>\d{4})\s*(?:to|–|-|until)\s*(?P<end>\d{4}|present|current)",
            r"(?P<start>(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{4})\s*(?:to|–|-|until)\s*(?P<end>(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{4}|present)",
        ]

        # ISO date patterns (YYYY-MM, YYYY-MM-DD)
        self.iso_date_patterns = [
            r"\b(?P<year>\d{4})-(?P<month>\d{1,2})-(?P<day>\d{1,2})\b",
            r"\b(?P<year>\d{4})-(?P<month>\d{1,2})\b",
        ]

        # Date tokens that contaminate other fields
        self.date_contamination_patterns = [
            r"\b\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}\b",
            r"\b\d{4}\b",
            r"\b(?:depuis|from|since|until|to|au|a|jusqu[\'\']?a)\b",
            r"\b(?:janvier|fevrier|mars|avril|mai|juin|juillet|aout|septembre|octobre|novembre|decembre)\b",
            r"\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\b",
            r"\b(?:present|present|current|actuellement|en\s+cours)\b",
        ]

        # Compile all patterns
        self.french_present_regex = [
            re.compile(p, re.IGNORECASE) for p in self.french_present_patterns
        ]
        self.english_present_regex = [
            re.compile(p, re.IGNORECASE) for p in self.english_present_patterns
        ]
        self.date_range_regex = [
            re.compile(p, re.IGNORECASE) for p in self.date_range_patterns
        ]
        self.iso_date_regex = [
            re.compile(p, re.IGNORECASE) for p in self.iso_date_patterns
        ]
        self.date_contamination_regex = [
            re.compile(p, re.IGNORECASE) for p in self.date_contamination_patterns
        ]

    def _setup_cefr_mappings(self):
        """Setup CEFR level mappings."""

        # Direct CEFR level patterns
        self.cefr_level_patterns = {
            CEFRLevel.A1: [r"\bA1\b", r"\bbeginner\b", r"\bdebutant\b", r"\bbasic\b"],
            CEFRLevel.A2: [r"\bA2\b", r"\belementary\b", r"\belementaire\b"],
            CEFRLevel.B1: [r"\bB1\b", r"\bintermediate\b", r"\bintermediaire\b"],
            CEFRLevel.B2: [
                r"\bB2\b",
                r"\bupper[\s\-]?intermediate\b",
                r"\bintermediaire\s+superieur\b",
            ],
            CEFRLevel.C1: [r"\bC1\b", r"\badvanced\b", r"\bavance\b"],
            CEFRLevel.C2: [r"\bC2\b", r"\bproficient\b", r"\bmaitrise\b"],
            CEFRLevel.NATIVE: [
                r"\bnative\b",
                r"\bnatif\b",
                r"\bmaternel\b",
                r"\bmother\s+tongue\b",
                r"\blangue\s+maternelle\b",
            ],
        }

        # Heuristic proficiency mappings
        self.heuristic_cefr_mappings = {
            # High proficiency indicators
            CEFRLevel.C2: [
                r"\b(?:fluent|fluency|couramment)\b",
                r"\b(?:excellent|outstanding|exceptional)\b",
                r"\b(?:perfect|parfait)\b",
            ],
            CEFRLevel.C1: [
                r"\b(?:professional|professionnel|working)\b",
                r"\b(?:very\s+good|tres\s+bon|high)\b",
                r"\b(?:strong|solid|solide)\b",
            ],
            CEFRLevel.B2: [
                r"\b(?:good|bon|decent)\b",
                r"\b(?:conversational|conversation)\b",
                r"\b(?:independent\s+user)\b",
            ],
            CEFRLevel.B1: [
                r"\b(?:fair|moyen|moyenne)\b",
                r"\b(?:limited\s+working|usage\s+limite)\b",
            ],
            CEFRLevel.A2: [
                r"\b(?:basic|basique|waystage)\b",
                r"\b(?:survival|survie)\b",
            ],
            CEFRLevel.A1: [
                r"\b(?:beginner|debutant|breakthrough)\b",
                r"\b(?:minimal|minime)\b",
            ],
        }

        # Compile CEFR patterns
        self.compiled_cefr_patterns = {}
        for level, patterns in self.cefr_level_patterns.items():
            self.compiled_cefr_patterns[level] = [
                re.compile(p, re.IGNORECASE) for p in patterns
            ]

        self.compiled_heuristic_patterns = {}
        for level, patterns in self.heuristic_cefr_mappings.items():
            self.compiled_heuristic_patterns[level] = [
                re.compile(p, re.IGNORECASE) for p in patterns
            ]

    def normalize_date(
        self, date_text: str, doc_id: str = "unknown"
    ) -> DateNormalizationResult:
        """
        Normalize date strings to ISO format.

        Args:
            date_text: Raw date text
            doc_id: Document ID for metrics

        Returns:
            DateNormalizationResult with normalized date
        """
        metrics = get_metrics_collector(doc_id)
        original_text = date_text.strip()

        self.logger.debug(f"NORMALIZE_DATE: input='{original_text}'")

        # Step 1: Check for present indicators
        for pattern in self.french_present_regex + self.english_present_regex:
            if pattern.search(original_text):
                result = DateNormalizationResult(
                    original=original_text,
                    normalized="PRESENT",
                    format_type="present",
                    is_present=True,
                    confidence=0.95,
                )
                self.logger.info(
                    f"NORMALIZE_DATE: present detected | result={result.normalized}"
                )
                return result

        # Step 2: Check for date ranges
        for pattern in self.date_range_regex:
            match = pattern.search(original_text)
            if match:
                start_raw = match.group("start")
                end_raw = match.group("end")

                # Normalize start date
                start_normalized = self._normalize_single_date(start_raw)

                # Normalize end date (check for present indicators)
                if any(
                    present_word in end_raw.lower()
                    for present_word in [
                        "present",
                        "present",
                        "actuellement",
                        "current",
                    ]
                ):
                    end_normalized = "PRESENT"
                    is_present = True
                else:
                    end_normalized = self._normalize_single_date(end_raw)
                    is_present = False

                result = DateNormalizationResult(
                    original=original_text,
                    normalized=f"{start_normalized} - {end_normalized}",
                    format_type="range",
                    start_date=start_normalized,
                    end_date=end_normalized,
                    is_present=is_present,
                    confidence=0.90,
                )

                self.logger.info(
                    f"NORMALIZE_DATE: range detected | start={start_normalized} end={end_normalized}"
                )
                return result

        # Step 3: Check for single ISO dates
        for pattern in self.iso_date_regex:
            match = pattern.search(original_text)
            if match:
                year = match.group("year")
                month = (
                    match.group("month").zfill(2)
                    if "month" in match.groupdict()
                    else None
                )
                day = (
                    match.group("day").zfill(2)
                    if "day" in match.groupdict() and match.group("day")
                    else None
                )

                if day:
                    normalized = f"{year}-{month}-{day}"
                    format_type = "iso_date"
                elif month:
                    normalized = f"{year}-{month}"
                    format_type = "iso_month"
                else:
                    normalized = year
                    format_type = "year"

                result = DateNormalizationResult(
                    original=original_text,
                    normalized=normalized,
                    format_type=format_type,
                    confidence=0.85,
                )

                self.logger.info(
                    f"NORMALIZE_DATE: iso format | normalized={normalized}"
                )
                return result

        # Step 4: Try to extract and normalize any date-like patterns
        normalized_attempt = self._normalize_single_date(original_text)
        if normalized_attempt != original_text:
            result = DateNormalizationResult(
                original=original_text,
                normalized=normalized_attempt,
                format_type="heuristic",
                confidence=0.70,
            )
            self.logger.info(
                f"NORMALIZE_DATE: heuristic | normalized={normalized_attempt}"
            )
            return result

        # Step 5: No normalization possible
        result = DateNormalizationResult(
            original=original_text,
            normalized=original_text,
            format_type="unchanged",
            confidence=0.50,
        )

        self.logger.debug(f"NORMALIZE_DATE: unchanged | text='{original_text}'")
        return result

    def _normalize_single_date(self, date_str: str) -> str:
        """Normalize a single date string to ISO format."""
        date_str = date_str.strip()

        # French month names
        french_months = {
            "janvier": "01",
            "fevrier": "02",
            "mars": "03",
            "avril": "04",
            "mai": "05",
            "juin": "06",
            "juillet": "07",
            "aout": "08",
            "septembre": "09",
            "octobre": "10",
            "novembre": "11",
            "decembre": "12",
        }

        # English month names
        english_months = {
            "january": "01",
            "february": "02",
            "march": "03",
            "april": "04",
            "may": "05",
            "june": "06",
            "july": "07",
            "august": "08",
            "september": "09",
            "october": "10",
            "november": "11",
            "december": "12",
        }

        # Try various date formats
        formats_to_try = [
            # DD/MM/YYYY, DD-MM-YYYY, DD.MM.YYYY
            (
                r"(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})",
                lambda m: f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}",
            ),
            # MM/YYYY, MM-YYYY
            (
                r"(\d{1,2})[/\-\.](\d{4})",
                lambda m: f"{m.group(2)}-{m.group(1).zfill(2)}",
            ),
            # YYYY only
            (r"^(\d{4})$", lambda m: m.group(1)),
            # Month YYYY (English)
            (
                r"(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{4})",
                lambda m: f"{m.group(2)}-{english_months[m.group(1).lower()]}",
            ),
            # Month YYYY (French)
            (
                r"(janvier|fevrier|mars|avril|mai|juin|juillet|aout|septembre|octobre|novembre|decembre)\s+(\d{4})",
                lambda m: f"{m.group(2)}-{french_months[m.group(1).lower()]}",
            ),
        ]

        for pattern, formatter in formats_to_try:
            match = re.search(pattern, date_str, re.IGNORECASE)
            if match:
                try:
                    return formatter(match)
                except (ValueError, KeyError):
                    continue

        return date_str  # Return unchanged if no pattern matches

    def normalize_language_skill(
        self, language_text: str, doc_id: str = "unknown"
    ) -> LanguageSkillResult:
        """
        Normalize language skill to CEFR level.

        Args:
            language_text: Raw language skill text
            doc_id: Document ID for metrics

        Returns:
            LanguageSkillResult with CEFR mapping
        """
        metrics = get_metrics_collector(doc_id)
        original_text = language_text.strip()

        self.logger.debug(f"NORMALIZE_LANGUAGE: input='{original_text}'")

        # Extract language name (assume first word or phrase)
        language_parts = original_text.split()
        if language_parts:
            language = language_parts[0]
        else:
            language = "unknown"

        # Step 1: Check for explicit CEFR levels
        for level, patterns in self.compiled_cefr_patterns.items():
            for pattern in patterns:
                if pattern.search(original_text):
                    result = LanguageSkillResult(
                        language=language,
                        cefr_level=level,
                        proficiency_description=level.value,
                        confidence=0.95,
                        original_text=original_text,
                    )
                    self.logger.info(
                        f"NORMALIZE_LANGUAGE: explicit CEFR | level={level.value}"
                    )
                    return result

        # Step 2: Heuristic mapping based on proficiency indicators
        for level, patterns in self.compiled_heuristic_patterns.items():
            for pattern in patterns:
                if pattern.search(original_text):
                    result = LanguageSkillResult(
                        language=language,
                        cefr_level=level,
                        proficiency_description=level.value,
                        confidence=0.75,
                        original_text=original_text,
                    )
                    self.logger.info(
                        f"NORMALIZE_LANGUAGE: heuristic mapping | level={level.value}"
                    )
                    return result

        # Step 3: Default to B1 (intermediate) if no clear indicator
        result = LanguageSkillResult(
            language=language,
            cefr_level=CEFRLevel.B1,
            proficiency_description="B1 (estimated)",
            confidence=0.50,
            original_text=original_text,
        )

        self.logger.debug(f"NORMALIZE_LANGUAGE: default B1 | text='{original_text}'")
        return result

    def clean_field_contamination(
        self, field_value: str, field_type: str
    ) -> NormalizedField:
        """
        Clean field contamination by removing date tokens from title/company fields.

        Args:
            field_value: Original field value
            field_type: Field type (title, company, description, etc.)

        Returns:
            NormalizedField with cleaned value
        """
        original_value = field_value.strip()
        cleaned_value = original_value
        notes = []

        # Only clean title and company fields
        if field_type.lower() in ["title", "role", "company", "organization"]:
            # Remove date contamination patterns
            for pattern in self.date_contamination_regex:
                if pattern.search(cleaned_value):
                    old_value = cleaned_value
                    cleaned_value = pattern.sub("", cleaned_value).strip()
                    cleaned_value = re.sub(
                        r"\s+", " ", cleaned_value
                    )  # Normalize whitespace

                    if old_value != cleaned_value:
                        notes.append(f"removed_date_tokens_from_{field_type}")

            # Clean up extra whitespace and punctuation
            cleaned_value = re.sub(
                r"\s*[,\-–]\s*$", "", cleaned_value
            )  # Remove trailing punctuation
            cleaned_value = re.sub(
                r"^\s*[,\-–]\s*", "", cleaned_value
            )  # Remove leading punctuation
            cleaned_value = cleaned_value.strip()

        confidence = 1.0 if cleaned_value == original_value else 0.85

        result = NormalizedField(
            original_value=original_value,
            normalized_value=cleaned_value,
            confidence=confidence,
            notes=notes,
        )

        if notes:
            self.logger.info(
                f"CLEAN_CONTAMINATION: {field_type} | cleaned | notes={notes}"
            )

        return result

    def normalize_text_field(
        self, text: str, field_type: str = "general"
    ) -> NormalizedField:
        """
        General text field normalization.

        Args:
            text: Text to normalize
            field_type: Type of field being normalized

        Returns:
            NormalizedField with normalization result
        """
        original_text = text.strip() if text else ""

        if not original_text:
            return NormalizedField(
                original_value="",
                normalized_value="",
                confidence=1.0,
                notes=["empty_field"],
            )

        # Apply contamination cleaning
        cleaned = self.clean_field_contamination(original_text, field_type)

        # Additional normalizations can be added here
        normalized_text = cleaned.normalized_value
        notes = cleaned.notes.copy()

        # Normalize whitespace
        if re.search(r"\s{2,}", normalized_text):
            normalized_text = re.sub(r"\s+", " ", normalized_text)
            notes.append("normalized_whitespace")

        # Remove excessive punctuation
        if re.search(r"[.!?]{2,}", normalized_text):
            normalized_text = re.sub(r"([.!?])\1+", r"\1", normalized_text)
            notes.append("normalized_punctuation")

        confidence = 1.0 if len(notes) == 0 else 0.90

        return NormalizedField(
            original_value=original_text,
            normalized_value=normalized_text,
            confidence=confidence,
            notes=notes,
        )


# Convenience functions for backward compatibility
def normalize_date(date_text: str, doc_id: str = "unknown") -> DateNormalizationResult:
    """Convenience function for date normalization."""
    normalizer = EnhancedNormalizer()
    return normalizer.normalize_date(date_text, doc_id)


def normalize_language_skill(
    language_text: str, doc_id: str = "unknown"
) -> LanguageSkillResult:
    """Convenience function for language skill normalization."""
    normalizer = EnhancedNormalizer()
    return normalizer.normalize_language_skill(language_text, doc_id)


def clean_field_contamination(field_value: str, field_type: str) -> NormalizedField:
    """Convenience function for field contamination cleaning."""
    normalizer = EnhancedNormalizer()
    return normalizer.clean_field_contamination(field_value, field_type)


# Export main classes and functions
__all__ = [
    "DatePresence",
    "CEFRLevel",
    "NormalizedField",
    "DateNormalizationResult",
    "LanguageSkillResult",
    "EnhancedNormalizer",
    "normalize_date",
    "normalize_language_skill",
    "clean_field_contamination",
]
