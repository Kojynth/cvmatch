"""
CVExtractor Normalization Module
===============================

Enhanced normalization capabilities for CV extraction including:
- Date normalization with present/ongoing detection
- CEFR language level mapping
- Field contamination cleaning
- Text normalization utilities
"""

from .data_normalizer import DataNormalizer
from .enhanced_normalizer import (
    # Core classes
    EnhancedNormalizer,
    DatePresence,
    CEFRLevel,
    # Result types
    NormalizedField,
    DateNormalizationResult,
    LanguageSkillResult,
    # Convenience functions
    normalize_date,
    normalize_language_skill,
    clean_field_contamination,
)

__all__ = [
    # Legacy normalizer
    "DataNormalizer",
    # Enhanced normalizer - core classes
    "EnhancedNormalizer",
    "DatePresence",
    "CEFRLevel",
    # Enhanced normalizer - result types
    "NormalizedField",
    "DateNormalizationResult",
    "LanguageSkillResult",
    # Enhanced normalizer - convenience functions
    "normalize_date",
    "normalize_language_skill",
    "clean_field_contamination",
]
