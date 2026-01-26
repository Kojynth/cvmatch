"""
CVExtractor Internationalization Module
======================================

Comprehensive internationalization support for CV extraction including:
- Text direction detection (LTR, RTL, TTB, Mixed)
- Script recognition (Latin, Arabic, Hebrew, CJK, Cyrillic, etc.)
- Multilingual header recognition across multiple languages
- Reading order hints for proper layout processing
"""

from .text_direction_detector import (
    # Core classes
    TextDirection,
    ScriptType,
    DirectionAnalysis,
    DirectionDetector,
    # Convenience functions
    detect_text_direction,
    is_rtl_text,
    is_cjk_text,
    get_reading_order_hint,
)

from .multilingual_headers import (
    # Core classes
    SectionType,
    HeaderMatch,
    MultilingualHeaderRecognizer,
    # Convenience functions
    recognize_header,
    get_section_type,
    is_header_text,
)

__all__ = [
    # Text direction detection
    "TextDirection",
    "ScriptType",
    "DirectionAnalysis",
    "DirectionDetector",
    "detect_text_direction",
    "is_rtl_text",
    "is_cjk_text",
    "get_reading_order_hint",
    # Multilingual header recognition
    "SectionType",
    "HeaderMatch",
    "MultilingualHeaderRecognizer",
    "recognize_header",
    "get_section_type",
    "is_header_text",
]
