"""
Text Direction Detector for RTL/CJK Support
==========================================

Detects text direction and script types for proper reading order handling
in CV extraction. Supports RTL (Arabic, Hebrew), CJK (Chinese, Japanese, Korean),
and complex mixed-script documents.
"""

import re
import logging
import unicodedata
from typing import Dict, List, Any, Optional, Tuple, NamedTuple
from dataclasses import dataclass
from enum import Enum

from ..utils.log_safety import create_safe_logger_wrapper
from ..metrics.instrumentation import get_metrics_collector


class TextDirection(Enum):
    """Text direction types."""

    LTR = "LTR"  # Left-to-right (Latin, Cyrillic, etc.)
    RTL = "RTL"  # Right-to-left (Arabic, Hebrew)
    TTB = "TTB"  # Top-to-bottom (Traditional Chinese, Japanese vertical)
    MIXED = "MIXED"  # Mixed directions


class ScriptType(Enum):
    """Unicode script types."""

    LATIN = "LATIN"
    ARABIC = "ARABIC"
    HEBREW = "HEBREW"
    CJK = "CJK"  # Chinese, Japanese, Korean
    CYRILLIC = "CYRILLIC"
    DEVANAGARI = "DEVANAGARI"
    THAI = "THAI"
    MIXED = "MIXED"
    UNKNOWN = "UNKNOWN"


@dataclass
class DirectionAnalysis:
    """Text direction analysis result."""

    primary_direction: TextDirection
    primary_script: ScriptType
    confidence: float
    script_ratios: Dict[ScriptType, float]
    direction_indicators: Dict[str, int]
    reading_order_hint: str  # "natural", "reverse", "vertical"


class DirectionDetector:
    """Detects text direction and script types for internationalization."""

    def __init__(self, debug_mode: bool = False):
        self.debug_mode = debug_mode

        # Logger
        base_logger = logging.getLogger(__name__)
        self.logger = create_safe_logger_wrapper(base_logger)

        # Unicode ranges for script detection
        self._setup_unicode_ranges()

        # Direction markers and indicators
        self._setup_direction_markers()

    def _setup_unicode_ranges(self):
        """Setup Unicode ranges for script detection."""

        # Script detection ranges (simplified)
        self.script_ranges = {
            ScriptType.LATIN: [
                (0x0041, 0x005A),  # Basic Latin uppercase
                (0x0061, 0x007A),  # Basic Latin lowercase
                (0x00C0, 0x00FF),  # Latin-1 Supplement
                (0x0100, 0x017F),  # Latin Extended-A
                (0x0180, 0x024F),  # Latin Extended-B
            ],
            ScriptType.ARABIC: [
                (0x0600, 0x06FF),  # Arabic
                (0x0750, 0x077F),  # Arabic Supplement
                (0x08A0, 0x08FF),  # Arabic Extended-A
                (0xFB50, 0xFDFF),  # Arabic Presentation Forms-A
                (0xFE70, 0xFEFF),  # Arabic Presentation Forms-B
            ],
            ScriptType.HEBREW: [
                (0x0590, 0x05FF),  # Hebrew
                (0xFB1D, 0xFB4F),  # Hebrew Presentation Forms
            ],
            ScriptType.CJK: [
                (0x4E00, 0x9FFF),  # CJK Unified Ideographs
                (0x3400, 0x4DBF),  # CJK Extension A
                (0x20000, 0x2A6DF),  # CJK Extension B
                (0x3040, 0x309F),  # Hiragana
                (0x30A0, 0x30FF),  # Katakana
                (0x3100, 0x312F),  # Bopomofo
                (0xAC00, 0xD7AF),  # Hangul Syllables
                (0x1100, 0x11FF),  # Hangul Jamo
            ],
            ScriptType.CYRILLIC: [
                (0x0400, 0x04FF),  # Cyrillic
                (0x0500, 0x052F),  # Cyrillic Supplement
            ],
            ScriptType.DEVANAGARI: [
                (0x0900, 0x097F),  # Devanagari
            ],
            ScriptType.THAI: [
                (0x0E00, 0x0E7F),  # Thai
            ],
        }

    def _setup_direction_markers(self):
        """Setup direction markers and indicators."""

        # RTL direction markers
        self.rtl_markers = [
            "\u202e",  # Right-to-Left Override
            "\u202d",  # Left-to-Right Override
            "\u061c",  # Arabic Letter Mark
            "\u200f",  # Right-to-Left Mark
        ]

        # LTR direction markers
        self.ltr_markers = [
            "\u202d",  # Left-to-Right Override
            "\u200e",  # Left-to-Right Mark
        ]

        # Strong RTL characters (Arabic, Hebrew letters)
        self.rtl_strong_pattern = re.compile(
            r"[\u0590-\u05FF\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]"
        )

        # Strong LTR characters (Latin letters)
        self.ltr_strong_pattern = re.compile(r"[A-Za-z\u00C0-\u017F]")

        # CJK pattern for vertical text detection
        self.cjk_pattern = re.compile(r"[\u4E00-\u9FFF\u3040-\u309F\u30A0-\u30FF]")

        # Vertical text indicators (CJK punctuation patterns)
        self.vertical_indicators = [
            "︙",
            "︰",
            "︱",
            "︲",
            "︳",
            "︴",  # Vertical punctuation
            "｜",
            "—",
            "―",  # Vertical lines
        ]

    def detect_direction(self, text: str, doc_id: str = "unknown") -> DirectionAnalysis:
        """
        Detect text direction and script type.

        Args:
            text: Text to analyze
            doc_id: Document ID for metrics

        Returns:
            DirectionAnalysis with detected direction and script info
        """
        metrics = get_metrics_collector(doc_id)

        self.logger.debug(f"DIRECTION_DETECT: analyzing text length={len(text)}")

        if not text or not text.strip():
            return DirectionAnalysis(
                primary_direction=TextDirection.LTR,
                primary_script=ScriptType.LATIN,
                confidence=0.5,
                script_ratios={},
                direction_indicators={},
                reading_order_hint="natural",
            )

        # Step 1: Analyze script composition
        script_counts = self._analyze_script_composition(text)
        script_ratios = self._calculate_script_ratios(script_counts, len(text))

        # Step 2: Determine primary script
        primary_script = self._determine_primary_script(script_ratios)

        # Step 3: Detect direction based on script and markers
        direction_indicators = self._analyze_direction_indicators(text)
        primary_direction = self._determine_primary_direction(
            primary_script, direction_indicators, text
        )

        # Step 4: Determine reading order hint
        reading_order_hint = self._determine_reading_order(
            primary_script, primary_direction, text
        )

        # Step 5: Calculate confidence
        confidence = self._calculate_confidence(
            script_ratios, direction_indicators, primary_script
        )

        result = DirectionAnalysis(
            primary_direction=primary_direction,
            primary_script=primary_script,
            confidence=confidence,
            script_ratios=script_ratios,
            direction_indicators=direction_indicators,
            reading_order_hint=reading_order_hint,
        )

        self.logger.info(
            f"DIRECTION_DETECT: result | "
            f"direction={primary_direction.value} script={primary_script.value} "
            f"confidence={confidence:.3f} reading_order={reading_order_hint}"
        )

        return result

    def _analyze_script_composition(self, text: str) -> Dict[ScriptType, int]:
        """Analyze character composition by script."""
        script_counts = {script: 0 for script in ScriptType}

        for char in text:
            if char.isspace() or char.isdigit() or not char.isalpha():
                continue

            code_point = ord(char)
            script_detected = False

            # Check each script range
            for script_type, ranges in self.script_ranges.items():
                for start, end in ranges:
                    if start <= code_point <= end:
                        script_counts[script_type] += 1
                        script_detected = True
                        break
                if script_detected:
                    break

            if not script_detected:
                script_counts[ScriptType.UNKNOWN] += 1

        return script_counts

    def _calculate_script_ratios(
        self, script_counts: Dict[ScriptType, int], total_chars: int
    ) -> Dict[ScriptType, float]:
        """Calculate script ratios."""
        if total_chars == 0:
            return {script: 0.0 for script in ScriptType}

        return {
            script: count / total_chars
            for script, count in script_counts.items()
            if count > 0
        }

    def _determine_primary_script(
        self, script_ratios: Dict[ScriptType, float]
    ) -> ScriptType:
        """Determine primary script from ratios."""
        if not script_ratios:
            return ScriptType.LATIN

        # Find script with highest ratio
        primary_script = max(script_ratios.items(), key=lambda x: x[1])[0]

        # Handle mixed script scenarios
        significant_scripts = [
            script for script, ratio in script_ratios.items() if ratio > 0.1
        ]

        if len(significant_scripts) > 1:
            # Check for common mixed scenarios
            if (
                ScriptType.LATIN in significant_scripts
                and ScriptType.CJK in significant_scripts
            ):
                # CJK with Latin (common in modern documents)
                return (
                    ScriptType.CJK
                    if script_ratios[ScriptType.CJK] > 0.3
                    else ScriptType.MIXED
                )
            elif (
                ScriptType.LATIN in significant_scripts
                and ScriptType.ARABIC in significant_scripts
            ):
                # Arabic with Latin
                return (
                    ScriptType.ARABIC
                    if script_ratios[ScriptType.ARABIC] > 0.3
                    else ScriptType.MIXED
                )
            else:
                return ScriptType.MIXED

        return primary_script

    def _analyze_direction_indicators(self, text: str) -> Dict[str, int]:
        """Analyze direction indicators in text."""
        indicators = {
            "rtl_markers": 0,
            "ltr_markers": 0,
            "rtl_strong_chars": 0,
            "ltr_strong_chars": 0,
            "vertical_indicators": 0,
            "punctuation_patterns": 0,
        }

        # Count direction markers
        for marker in self.rtl_markers:
            indicators["rtl_markers"] += text.count(marker)

        for marker in self.ltr_markers:
            indicators["ltr_markers"] += text.count(marker)

        # Count strong directional characters
        indicators["rtl_strong_chars"] = len(self.rtl_strong_pattern.findall(text))
        indicators["ltr_strong_chars"] = len(self.ltr_strong_pattern.findall(text))

        # Count vertical indicators
        for indicator in self.vertical_indicators:
            indicators["vertical_indicators"] += text.count(indicator)

        # Analyze punctuation patterns (simplified)
        if re.search(r"[.!?]\s*$", text):  # Sentence-ending at the end
            indicators["punctuation_patterns"] += 1

        return indicators

    def _determine_primary_direction(
        self, primary_script: ScriptType, indicators: Dict[str, int], text: str
    ) -> TextDirection:
        """Determine primary text direction."""

        # Script-based direction defaults
        if primary_script in [ScriptType.ARABIC, ScriptType.HEBREW]:
            base_direction = TextDirection.RTL
        elif primary_script == ScriptType.CJK:
            # CJK can be LTR (modern) or TTB (traditional)
            if indicators["vertical_indicators"] > 0:
                base_direction = TextDirection.TTB
            else:
                base_direction = TextDirection.LTR
        else:
            base_direction = TextDirection.LTR

        # Override based on explicit markers
        if indicators["rtl_markers"] > indicators["ltr_markers"]:
            return TextDirection.RTL
        elif indicators["ltr_markers"] > indicators["rtl_markers"]:
            return TextDirection.LTR

        # Override based on character analysis
        rtl_score = indicators["rtl_strong_chars"]
        ltr_score = indicators["ltr_strong_chars"]

        if rtl_score > ltr_score * 2:  # Strongly RTL
            return TextDirection.RTL
        elif ltr_score > rtl_score * 2:  # Strongly LTR
            return TextDirection.LTR

        # Check for mixed content
        if (
            abs(rtl_score - ltr_score) < min(rtl_score, ltr_score) * 0.5
            and min(rtl_score, ltr_score) > 5
        ):
            return TextDirection.MIXED

        return base_direction

    def _determine_reading_order(
        self, primary_script: ScriptType, primary_direction: TextDirection, text: str
    ) -> str:
        """Determine reading order hint for layout processing."""

        if primary_direction == TextDirection.RTL:
            return "reverse"
        elif primary_direction == TextDirection.TTB:
            return "vertical"
        elif primary_direction == TextDirection.MIXED:
            # Analyze text structure for mixed content
            lines = text.split("\n")
            if len(lines) > 1:
                # Check if different lines have different directions
                line_directions = []
                for line in lines[:5]:  # Check first 5 lines
                    line_analysis = self._analyze_direction_indicators(line.strip())
                    if (
                        line_analysis["rtl_strong_chars"]
                        > line_analysis["ltr_strong_chars"]
                    ):
                        line_directions.append("rtl")
                    else:
                        line_directions.append("ltr")

                if "rtl" in line_directions and "ltr" in line_directions:
                    return "mixed_lines"

            return "natural"
        else:
            return "natural"

    def _calculate_confidence(
        self,
        script_ratios: Dict[ScriptType, float],
        indicators: Dict[str, int],
        primary_script: ScriptType,
    ) -> float:
        """Calculate confidence in direction detection."""

        if not script_ratios:
            return 0.5

        # Base confidence from primary script dominance
        primary_ratio = script_ratios.get(primary_script, 0.0)
        base_confidence = min(0.9, primary_ratio * 2)  # Cap at 0.9

        # Boost confidence with explicit markers
        marker_boost = 0.0
        total_markers = sum(
            [
                indicators["rtl_markers"],
                indicators["ltr_markers"],
                indicators["vertical_indicators"],
            ]
        )

        if total_markers > 0:
            marker_boost = min(0.2, total_markers * 0.05)

        # Reduce confidence for mixed scripts
        significant_scripts = len(
            [ratio for ratio in script_ratios.values() if ratio > 0.1]
        )
        if significant_scripts > 2:
            base_confidence *= 0.7

        final_confidence = min(0.95, base_confidence + marker_boost)
        return max(0.1, final_confidence)  # Minimum confidence of 0.1


# Convenience functions
def detect_text_direction(text: str, doc_id: str = "unknown") -> DirectionAnalysis:
    """Convenience function for direction detection."""
    detector = DirectionDetector()
    return detector.detect_direction(text, doc_id)


def is_rtl_text(text: str) -> bool:
    """Quick check if text is primarily RTL."""
    analysis = detect_text_direction(text)
    return analysis.primary_direction == TextDirection.RTL


def is_cjk_text(text: str) -> bool:
    """Quick check if text is primarily CJK."""
    analysis = detect_text_direction(text)
    return analysis.primary_script == ScriptType.CJK


def get_reading_order_hint(text: str) -> str:
    """Get reading order hint for layout processing."""
    analysis = detect_text_direction(text)
    return analysis.reading_order_hint


# Export main classes and functions
__all__ = [
    "TextDirection",
    "ScriptType",
    "DirectionAnalysis",
    "DirectionDetector",
    "detect_text_direction",
    "is_rtl_text",
    "is_cjk_text",
    "get_reading_order_hint",
]
