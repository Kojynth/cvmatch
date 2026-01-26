"""Simplified date normalizer used for compatibility tests."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple


class DatePrecision(Enum):
    YEAR = "year"
    MONTH = "month"
    DAY = "day"


@dataclass
class NormalizedDate:
    iso_date: str
    precision: DatePrecision
    is_current: bool = False
    confidence: float = 0.0
    original_text: str = ""
    language_detected: Optional[str] = None


class DateNormalizer:
    """Multilingual date normalizer tailored for the test-suite."""

    MONTH_NAMES: Dict[str, Dict[str, int]] = {
        'en': {
            'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
            'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12,
            'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'jun': 6, 'jul': 7, 'aug': 8, 'sep': 9,
            'oct': 10, 'nov': 11, 'dec': 12,
        },
        'fr': {
            'janvier': 1, 'février': 2, 'fevrier': 2, 'mars': 3, 'avril': 4, 'mai': 5, 'juin': 6,
            'juillet': 7, 'août': 8, 'aout': 8, 'septembre': 9, 'octobre': 10, 'novembre': 11, 'décembre': 12,
            'janv': 1, 'févr': 2, 'fevr': 2, 'avr': 4, 'juill': 7, 'aoû': 8, 'sept': 9,
        },
        'es': {
            'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4, 'mayo': 5, 'junio': 6,
            'julio': 7, 'agosto': 8, 'septiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12,
        },
    }

    CURRENT_TOKENS: Dict[str, List[str]] = {
        'en': ['present', 'current', 'now', 'today'],
        'fr': ['ce jour', 'en cours', 'actuellement', 'présent', "aujourd'hui"],
        'es': ['presente', 'actual'],
    }

    ISO_DAY_RE = re.compile(r"^(?P<year>\d{4})-(?P<month>\d{1,2})-(?P<day>\d{1,2})$")
    ISO_MONTH_RE = re.compile(r"^(?P<year>\d{4})-(?P<month>\d{1,2})$")
    YEAR_ONLY_RE = re.compile(r"^(?P<year>\d{4})$")

    MONTH_DAY_YEAR_RE = re.compile(
        r"^(?P<month>\d{1,2})[\/\-.](?P<day>\d{1,2})[\/\-.](?P<year>\d{4})$"
    )

    def __init__(self, current_year: Optional[int] = None) -> None:
        self.current_year = current_year or datetime.now().year

    # ------------------------------------------------------------------
    # Language detection helpers
    # ------------------------------------------------------------------
    def detect_language(self, text: str) -> str:
        lower = text.lower()
        if any(token in lower for token in self.MONTH_NAMES['fr'].keys()) or 'é' in lower or 'à' in lower:
            return 'fr'
        if any(token in lower for token in self.MONTH_NAMES['es'].keys()):
            return 'es'
        return 'en'

    def parse_month_name(self, text: str, language: str) -> Optional[int]:
        month_map = self.MONTH_NAMES.get(language, {})
        key = text.lower().strip()
        if key in month_map:
            return month_map[key]
        # fallback across languages
        for months in self.MONTH_NAMES.values():
            if key in months:
                return months[key]
        return None

    def is_current_date(self, text: str, language: str) -> bool:
        tokens = self.CURRENT_TOKENS.get(language, [])
        lower = text.lower()
        return any(token in lower for token in tokens)

    # ------------------------------------------------------------------
    # Normalisation API
    # ------------------------------------------------------------------
    def normalize_date(self, text: str, language: Optional[str] = None) -> Optional[NormalizedDate]:
        if not text:
            return None
        stripped = text.strip()
        original = stripped

        language = language or self.detect_language(stripped)

        if self.is_current_date(stripped, language):
            return NormalizedDate(
                iso_date=str(self.current_year),
                precision=DatePrecision.YEAR,
                is_current=True,
                confidence=1.0,
                original_text=original,
                language_detected=language,
            )

        match = self.ISO_DAY_RE.match(stripped)
        if match:
            year = int(match.group('year'))
            month = int(match.group('month'))
            day = int(match.group('day'))
            if not self._validate_components(year, month, day):
                return None
            return NormalizedDate(
                iso_date=f"{year:04d}-{month:02d}-{day:02d}",
                precision=DatePrecision.DAY,
                confidence=0.95,
                original_text=original,
                language_detected=language,
            )

        match = self.ISO_MONTH_RE.match(stripped)
        if match:
            year = int(match.group('year'))
            month = int(match.group('month'))
            if not self._validate_components(year, month):
                return None
            return NormalizedDate(
                iso_date=f"{year:04d}-{month:02d}",
                precision=DatePrecision.MONTH,
                confidence=0.9,
                original_text=original,
                language_detected=language,
            )

        match = self.MONTH_DAY_YEAR_RE.match(stripped)
        if match:
            year = int(match.group('year'))
            month = int(match.group('month'))
            day = int(match.group('day'))
            if not self._validate_components(year, month, day):
                return None
            return NormalizedDate(
                iso_date=f"{year:04d}-{month:02d}-{day:02d}",
                precision=DatePrecision.DAY,
                confidence=0.85,
                original_text=original,
                language_detected=language,
            )

        tokens = stripped.replace(',', ' ').split()
        if len(tokens) == 2:
            month_candidate, year_candidate = tokens
            if self.YEAR_ONLY_RE.match(year_candidate):
                month_number = self.parse_month_name(month_candidate, language)
                if month_number is not None:
                    year = int(year_candidate)
                    if not self._validate_components(year, month_number):
                        return None
                    return NormalizedDate(
                        iso_date=f"{year:04d}-{month_number:02d}",
                        precision=DatePrecision.MONTH,
                        confidence=0.8,
                        original_text=original,
                        language_detected=language,
                    )

        match = self.YEAR_ONLY_RE.match(stripped)
        if match:
            year = int(match.group('year'))
            if not self._validate_components(year):
                return None
            return NormalizedDate(
                iso_date=f"{year:04d}",
                precision=DatePrecision.YEAR,
                confidence=0.7,
                original_text=original,
                language_detected=language,
            )

        return None

    def normalize_date_range(self, start_text: str, end_text: str, language: Optional[str] = None) -> Tuple[Optional[NormalizedDate], Optional[NormalizedDate]]:
        return (
            self.normalize_date(start_text, language=language),
            self.normalize_date(end_text, language=language),
        )

    def batch_normalize(self, items: List[str], language: Optional[str] = None) -> List[Optional[NormalizedDate]]:
        return [self.normalize_date(item, language=language) for item in items]

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------
    def _validate_components(self, year: int, month: Optional[int] = None, day: Optional[int] = None) -> bool:
        if year > self.current_year or year < self.current_year - 80:
            return False
        if month is not None and not (1 <= month <= 12):
            return False
        if day is not None and not (1 <= day <= 31):
            return False
        return True

    # ------------------------------------------------------------------
    # New utility methods for contact protection and validation
    # ------------------------------------------------------------------
    def meets_precision_requirement(self, date_obj, min_precision: str = 'year') -> bool:
        """
        Check if date meets minimum precision requirement.

        Args:
            date_obj: Either a dict with keys 'year', 'month', 'day' or a NormalizedDate object
            min_precision: Minimum required precision ('year', 'month', 'day')

        Returns:
            True if date meets precision requirement
        """
        precision_levels = {
            'year': 1,      # Only year required
            'month': 2,     # Year + month required
            'day': 3        # Year + month + day required
        }

        if min_precision not in precision_levels:
            raise ValueError(f"Invalid precision level: {min_precision}")

        required_level = precision_levels[min_precision]

        # Handle both dict and NormalizedDate objects
        if isinstance(date_obj, NormalizedDate):
            # Extract precision level from NormalizedDate
            precision_map = {
                DatePrecision.YEAR: 1,
                DatePrecision.MONTH: 2,
                DatePrecision.DAY: 3,
            }
            current_level = precision_map.get(date_obj.precision, 0)
        else:
            # Handle dict format
            has_year = date_obj.get('year') is not None
            has_month = date_obj.get('month') is not None
            has_day = date_obj.get('day') is not None

            current_level = 0
            if has_year:
                current_level = 1
            if has_year and has_month:
                current_level = 2
            if has_year and has_month and has_day:
                current_level = 3

        return current_level >= required_level

    def is_valid_experience_date(self, date_string: str, language: Optional[str] = None, max_age: int = 70) -> bool:
        """
        Validate if date range is reasonable for experience entry.

        Args:
            date_string: Date range as string (e.g., "2020-2022", "January 2020 - December 2022")
            max_age: Maximum reasonable duration in years

        Returns:
            True if date appears valid for experience
        """
        try:
            from app.utils.robust_date_parser import extract_date_range

            result = extract_date_range(date_string)
            if not result:
                return False

            start_year, end_year, is_current = result

            if start_year is None:
                return False

            if end_year is None and not is_current:
                return False

            # Validate ranges
            if start_year < 1950:
                return False

            if end_year and end_year > self.current_year + 1:
                return False

            if start_year > self.current_year:
                return False

            # Check duration
            if end_year:
                duration = end_year - start_year
                if duration > max_age:
                    return False
                if duration < 0:
                    return False

            return True

        except Exception:
            return False

    def has_nearby_date(self, all_lines: List[str], line_idx: int, window_size: int = 3) -> bool:
        """
        Check if a line has dates nearby (within window).

        Args:
            all_lines: All lines in context
            line_idx: Index of line to check
            window_size: How many lines before/after to search

        Returns:
            True if date found within window
        """
        if line_idx < 0 or line_idx >= len(all_lines):
            return False

        # Calculate window bounds
        half_window = window_size // 2
        start_idx = max(0, line_idx - half_window)
        end_idx = min(len(all_lines), line_idx + half_window + 1)

        for idx in range(start_idx, end_idx):
            if idx == line_idx:
                continue  # Skip the line itself

            # Try to parse dates from line
            from app.utils.robust_date_parser import parse_dates
            dates = parse_dates(all_lines[idx])

            if dates and len(dates) > 0:
                return True

        return False

    def find_dates_in_window(self, lines: List[str], line_idx: int, window_size: int = 3) -> List[dict]:
        """
        Find all dates in a window of lines.

        Args:
            lines: List of all lines
            line_idx: Center line index
            window_size: Number of lines to check (centered on line_idx)

        Returns:
            List of found dates with line indices
        """
        from app.utils.robust_date_parser import parse_dates

        found_dates = []

        if line_idx < 0 or line_idx >= len(lines):
            return found_dates

        # Calculate window bounds
        half_window = window_size // 2
        start = max(0, line_idx - half_window)
        end = min(len(lines), line_idx + half_window + 1)

        for idx in range(start, end):
            line = lines[idx]
            dates = parse_dates(line)

            for date_obj in dates:
                found_dates.append({
                    'date_obj': date_obj,
                    'line_idx': idx,
                    'text': line,
                    'distance': abs(idx - line_idx)
                })

        return found_dates


# Convenience wrapper to match legacy imports
_normalizer_singleton: Optional[DateNormalizer] = None


def get_date_normalizer() -> DateNormalizer:
    global _normalizer_singleton
    if _normalizer_singleton is None:
        _normalizer_singleton = DateNormalizer()
    return _normalizer_singleton


def normalize_date_text(text: str, language: Optional[str] = None) -> Optional[NormalizedDate]:
    return get_date_normalizer().normalize_date(text, language=language)


# ------------------------------------------------------------------
# Convenience functions for direct import
# ------------------------------------------------------------------
def is_valid_experience_date(date_string: str, language: Optional[str] = None, max_age: int = 70) -> bool:
    """
    Validate if date range is reasonable for experience entry.

    Wrapper for DateNormalizer.is_valid_experience_date()
    """
    return get_date_normalizer().is_valid_experience_date(date_string, language, max_age)


def has_nearby_date(all_lines: List[str], line_idx: int, window_size: int = 3) -> bool:
    """
    Check if a line has dates nearby (within window).

    Wrapper for DateNormalizer.has_nearby_date()
    """
    return get_date_normalizer().has_nearby_date(all_lines, line_idx, window_size)


def find_dates_in_window(lines: List[str], line_idx: int, window_size: int = 3) -> List[dict]:
    """
    Find all dates in a window of lines.

    Wrapper for DateNormalizer.find_dates_in_window()
    """
    return get_date_normalizer().find_dates_in_window(lines, line_idx, window_size)
