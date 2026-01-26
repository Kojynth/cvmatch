"""
Fallback Date Parser - Emergency date parsing when dateutil is unavailable.

Provides basic date parsing for French and English formats without external dependencies.
Used as a safety net to prevent total extraction failure when dateutil module is missing.
"""

import re
from typing import Tuple, Optional, Union, List
from datetime import date, datetime
from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)

# French month mappings with common variants and typos
# Enhanced for strict FR parsing with abbreviated forms
FR_MONTHS = {
    "janvier": 1, "jan": 1, "janv": 1, "janv.": 1,
    "février": 2, "fevrier": 2, "fév": 2, "fev": 2, "févr": 2, "févr.": 2, "feb": 2,
    "mars": 3, "mar": 3,
    "avril": 4, "avr": 4, "avr.": 4, "apr": 4, "avri": 4,
    "mai": 5, "may": 5,
    "juin": 6, "jun": 6,
    "juillet": 7, "juil": 7, "juil.": 7, "jul": 7,
    "août": 8, "aout": 8, "aoû": 8, "aoû.": 8, "aug": 8,
    "septembre": 9, "sept": 9, "sept.": 9, "sep": 9,
    "octobre": 10, "oct": 10, "oct.": 10,
    "novembre": 11, "nov": 11, "nov.": 11,
    "décembre": 12, "decembre": 12, "déc": 12, "déc.": 12, "dec": 12
}

# French postal code patterns (5 digits)
FR_POSTAL_PATTERNS = [
    r'^\d{5}$',  # 75001, 13001
    r'^\d{2}\s*\d{3}$',  # 75 001
]

# French month names for filtering as organizations
FR_MONTH_NAMES = set([
    "janvier", "février", "fevrier", "mars", "avril", "mai", "juin",
    "juillet", "août", "aout", "septembre", "octobre", "novembre", "décembre",
    "jan", "janv", "janv.", "fév", "févr", "févr.", "mar", "avr", "avr.",
    "juil", "juil.", "aoû", "aoû.", "sept", "sept.", "oct", "oct.", "nov", "nov.", "déc", "déc."
])

# English month mappings
EN_MONTHS = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12
}

# Present/current indicators in multiple languages
PRESENT_TOKENS = {
    "fr": [
        "à ce jour", "aujourd'hui", "actuel", "actuellement", "en cours", 
        "présent", "present", "maintenant", "jusqu'à présent", "à present"
    ],
    "en": [
        "present", "current", "currently", "now", "today", "ongoing",
        "to present", "to date", "until now"
    ],
    "es": [
        "presente", "actual", "actualmente", "hasta la fecha", "hoy"
    ],
    "de": [
        "heute", "aktuell", "gegenwärtig", "bis heute", "derzeit"
    ]
}

# All present tokens flattened for easy lookup
ALL_PRESENT_TOKENS = set()
for lang_tokens in PRESENT_TOKENS.values():
    ALL_PRESENT_TOKENS.update(token.lower() for token in lang_tokens)

# French-enhanced date patterns (ordered by specificity, day-first default)
DATE_PATTERNS = [
    # Full dates with strict FR format: DD/MM/YYYY (day-first default)
    (r'(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})', 'dmy_fr'),
    
    # Two-digit years with FR format: DD/MM/YY (day-first, 2-digit year handling)
    (r'(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{2})', 'dmy_yy_fr'),
    
    # Year-first format (ISO-like): YYYY/MM/DD, YYYY-MM-DD
    (r'(\d{4})[/\-\.](\d{1,2})[/\-\.](\d{1,2})', 'ymd'),
    
    # Month-Year with FR preference: MM/YYYY
    (r'(\d{1,2})[/\-\.](\d{4})', 'my_fr'),
    
    # Year-Month: YYYY/MM
    (r'(\d{4})[/\-\.](\d{1,2})', 'ym'),
    
    # Year ranges: YYYY-YYYY, YYYY–YYYY (em dash)
    (r'(\d{4})\s*[–—-]\s*(\d{4})', 'year_range'),
    
    # French month names with years: "janvier 2023", "janv. 2023", etc.
    (r'([a-zA-Zàâäçéèêëïîôùûüÿ\.]+)\s+(\d{4})', 'month_name_year'),
    
    # Years only: 2023, 2022, etc. (avoid postal codes)
    (r'\b(19\d{2}|20\d{2})\b', 'year_only'),
    
    # Present indicators
    (r'(' + '|'.join(re.escape(token) for token in ALL_PRESENT_TOKENS) + r')', 'present')
]

# Enhanced negative patterns to avoid false positives (postal codes, phones, etc.)
NEGATIVE_PATTERNS = [
    r'^\d{5}$',  # 75001 (French postal)
    r'^\d{2}\s*\d{3}$',  # 75 001 (spaced French postal)
    r'^\d{4,5}\s*[A-Z]{2}$',  # 1000 AB (Dutch postal)
    r'^[A-Z]\d[A-Z]\s?\d[A-Z]\d$',  # K1A 0A6 (Canadian postal)
    r'^\+?\d{2,3}[\s.-]?\d{2,3}[\s.-]?\d{2,4}[\s.-]?\d{2,4}$',  # Phone numbers
    r'^\d{4,5}$',  # Generic 4-5 digit codes (likely postal)
    r'^\d{2}[\s.-]\d{2}[\s.-]\d{2}[\s.-]\d{2}[\s.-]\d{2}$',  # French phone format
    r'^0[1-9]\s*\d{2}\s*\d{2}\s*\d{2}\s*\d{2}$',  # French mobile format
]


class FallbackDateParser:
    """Emergency date parser for when dateutil is not available."""
    
    def __init__(self):
        self.logger = get_safe_logger(f"{__name__}.FallbackDateParser", cfg=DEFAULT_PII_CONFIG)
        self.all_months = {**FR_MONTHS, **EN_MONTHS}
        
        # Compile patterns for performance
        self.compiled_patterns = [
            (re.compile(pattern, re.IGNORECASE), pattern_type) 
            for pattern, pattern_type in DATE_PATTERNS
        ]
        
        # Compile negative patterns for filtering
        self.negative_patterns = [
            re.compile(pattern, re.IGNORECASE) for pattern in NEGATIVE_PATTERNS
        ]
        
        self.logger.debug(f"FALLBACK_DATE_PARSER: initialized with {len(self.compiled_patterns)} patterns and {len(self.negative_patterns)} negative patterns")
    
    def normalize_text(self, text: str) -> str:
        """Normalize text for better French date matching."""
        if not text:
            return ""
        
        # Convert to lowercase and strip
        normalized = text.lower().strip()
        
        # Remove extra whitespace
        normalized = re.sub(r'\s+', ' ', normalized)
        
        # Normalize common date separators
        normalized = re.sub(r'[–—]', '-', normalized)
        
        # Normalize French accents for month matching
        accent_replacements = {
            'à': 'a', 'â': 'a', 'ä': 'a', 'ç': 'c',
            'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
            'ï': 'i', 'î': 'i', 'ô': 'o', 'ù': 'u', 
            'û': 'u', 'ü': 'u', 'ÿ': 'y'
        }
        
        for accented, plain in accent_replacements.items():
            normalized = normalized.replace(accented, plain)
        
        return normalized
    
    def extract_month_number(self, month_text: str) -> Optional[int]:
        """Extract month number from month name or abbreviation."""
        month_text = self.normalize_text(month_text)
        return self.all_months.get(month_text)
    
    def convert_two_digit_year(self, year: int) -> int:
        """Convert 2-digit year to 4-digit using French conventions.
        
        Args:
            year: 2-digit year (0-99)
            
        Returns:
            4-digit year following French conventions:
            - 00-24 → 2000-2024 (current era)
            - 25-99 → 1925-1999 (previous era)
        """
        if year <= 24:
            return 2000 + year
        else:
            return 1900 + year
    
    def is_present_indicator(self, text: str) -> bool:
        """Check if text indicates present/current date."""
        normalized = self.normalize_text(text)
        return normalized in ALL_PRESENT_TOKENS
    
    def is_negative_match(self, text: str) -> bool:
        """Check if text matches negative patterns (postal codes, phones, etc.)."""
        if not text:
            return False
        
        clean_text = text.strip()
        
        # Check against negative patterns
        for pattern in self.negative_patterns:
            if pattern.match(clean_text):
                self.logger.debug(f"FALLBACK_DATE_PARSER: negative match '{clean_text}' against pattern")
                return True
        
        # Additional check for French month names (should not be treated as dates in org context)
        normalized = self.normalize_text(text)
        if normalized.lower() in FR_MONTH_NAMES:
            self.logger.debug(f"FALLBACK_DATE_PARSER: month name rejected as date '{clean_text}'")
            return True
        
        return False
    
    def parse_single_date(self, date_str: str) -> Tuple[Optional[date], bool]:
        """
        Parse a single date string.
        
        Returns:
            (parsed_date, is_present) where is_present=True for current/ongoing dates
        """
        if not date_str:
            return None, False
        
        normalized = self.normalize_text(date_str)
        
        # Check for negative patterns first (postal codes, phones, etc.)
        if self.is_negative_match(date_str):
            return None, False
        
        # Check for present indicators
        if self.is_present_indicator(normalized):
            return None, True
        
        # Try each pattern in order
        for pattern, pattern_type in self.compiled_patterns:
            match = pattern.search(normalized)
            if not match:
                continue
            
            try:
                if pattern_type == 'dmy_fr':
                    day, month, year = map(int, match.groups())
                    # French day-first format validation
                    if 1 <= month <= 12 and 1 <= day <= 31:
                        return date(year, month, day), False
                
                elif pattern_type == 'dmy_yy_fr':
                    day, month, yy = map(int, match.groups())
                    # Handle 2-digit years with French conventions
                    year = self.convert_two_digit_year(yy)
                    if 1 <= month <= 12 and 1 <= day <= 31:
                        return date(year, month, day), False
                
                elif pattern_type == 'ymd':
                    year, month, day = map(int, match.groups())
                    if 1 <= month <= 12 and 1 <= day <= 31:
                        return date(year, month, day), False
                
                elif pattern_type == 'my_fr':
                    month, year = map(int, match.groups())
                    # French month-first preference
                    if 1 <= month <= 12:
                        return date(year, month, 1), False
                
                elif pattern_type == 'ym':
                    year, month = map(int, match.groups())
                    if 1 <= month <= 12:
                        return date(year, month, 1), False
                
                elif pattern_type == 'month_name_year':
                    month_name, year = match.groups()
                    month_num = self.extract_month_number(month_name)
                    if month_num and 1900 <= int(year) <= 2100:
                        return date(int(year), month_num, 1), False
                
                elif pattern_type == 'year_only':
                    year = int(match.group(1))
                    if 1900 <= year <= 2100:
                        return date(year, 1, 1), False
                
                elif pattern_type == 'present':
                    return None, True
                    
            except (ValueError, TypeError) as e:
                self.logger.debug(f"FALLBACK_DATE_PARSER: invalid date values in '{date_str}' | error={e}")
                continue
        
        self.logger.debug(f"FALLBACK_DATE_PARSER: no patterns matched '{date_str}'")
        return None, False
    
    def parse_date_range(self, range_str: str) -> Tuple[Optional[date], Optional[date], bool]:
        """
        Parse a date range string like "2020-2023", "jan 2020 - dec 2022", etc.
        
        Returns:
            (start_date, end_date, has_present) where has_present=True if range is ongoing
        """
        if not range_str:
            return None, None, False
        
        normalized = self.normalize_text(range_str)
        
        # Split on common range separators
        range_parts = re.split(r'\s*[–—-]\s*|\s+(?:to|à|jusqu|until|bis)\s+', normalized, maxsplit=1)
        
        if len(range_parts) == 1:
            # Single date, not a range
            single_date, is_present = self.parse_single_date(range_parts[0])
            return single_date, None, is_present
        
        start_str, end_str = range_parts
        start_date, start_present = self.parse_single_date(start_str)
        end_date, end_present = self.parse_single_date(end_str)
        
        # Handle present end dates
        has_present = end_present
        if has_present:
            end_date = None
        
        return start_date, end_date, has_present
    
    def extract_dates_from_text(self, text: str) -> List[Tuple[str, Optional[date], bool]]:
        """
        Extract all potential dates from text.
        
        Returns:
            List of (original_text, parsed_date, is_present) tuples
        """
        if not text:
            return []
        
        results = []
        normalized = self.normalize_text(text)
        
        # Find all date-like patterns
        for pattern, pattern_type in self.compiled_patterns:
            for match in pattern.finditer(normalized):
                matched_text = match.group(0)
                parsed_date, is_present = self.parse_single_date(matched_text)
                results.append((matched_text, parsed_date, is_present))
        
        return results
    
    def format_date_for_cv(self, parsed_date: Optional[date], is_present: bool = False) -> str:
        """Format a parsed date for CV display."""
        if is_present:
            return "Présent"
        
        if not parsed_date:
            return "Date inconnue"
        
        # Format as MM/YYYY for CV display
        return f"{parsed_date.month:02d}/{parsed_date.year}"
    
    def format_date_iso(self, parsed_date: Optional[date], is_present: bool = False) -> str:
        """Format a parsed date in ISO format (YYYY-MM-DD)."""
        if is_present:
            return "present"
        
        if not parsed_date:
            return "unknown"
        
        # ISO format with day defaulted to 1 for month-only dates
        return parsed_date.isoformat()
    
    def validate_date_range(self, start_date: Optional[date], end_date: Optional[date]) -> bool:
        """Validate that a date range makes logical sense."""
        if not start_date:
            return False
        
        # End date can be None (ongoing/present)
        if end_date and start_date > end_date:
            return False
        
        # Check reasonable bounds (not too far in past/future)
        current_year = datetime.now().year
        if start_date.year < 1950 or start_date.year > current_year + 5:
            return False
        
        if end_date and (end_date.year < 1950 or end_date.year > current_year + 5):
            return False
        
        return True


# Global fallback parser instance
_fallback_parser = None


def get_fallback_date_parser() -> FallbackDateParser:
    """Get the global fallback date parser instance."""
    global _fallback_parser
    if _fallback_parser is None:
        _fallback_parser = FallbackDateParser()
    return _fallback_parser


def parse_date_with_fallback(date_str: str, use_dateutil: bool = True) -> Tuple[Optional[date], bool]:
    """
    Parse a date string with fallback to our parser if dateutil fails.
    
    Args:
        date_str: Date string to parse
        use_dateutil: Whether to try dateutil first
    
    Returns:
        (parsed_date, is_present)
    """
    if not date_str:
        return None, False
    
    # Try dateutil first if available and requested
    if use_dateutil:
        try:
            from dateutil import parser as date_parser
            
            # Check for present indicators first
            fallback = get_fallback_date_parser()
            if fallback.is_present_indicator(date_str):
                return None, True
            
            parsed = date_parser.parse(date_str, fuzzy=True)
            return parsed.date(), False
            
        except (ImportError, ValueError, TypeError) as e:
            logger.debug(f"DATEUTIL_FALLBACK: dateutil failed for '{date_str}' | error={e}")
    
    # Use fallback parser
    fallback = get_fallback_date_parser()
    return fallback.parse_single_date(date_str)


def parse_date_range_with_fallback(range_str: str, use_dateutil: bool = True) -> Tuple[Optional[date], Optional[date], bool]:
    """
    Parse a date range with fallback parsing.
    
    Returns:
        (start_date, end_date, has_present)
    """
    if not range_str:
        return None, None, False
    
    fallback = get_fallback_date_parser()
    
    # For ranges, use our fallback parser directly as dateutil doesn't handle ranges well
    return fallback.parse_date_range(range_str)


if __name__ == "__main__":
    # Test the fallback parser
    parser = get_fallback_date_parser()
    
    test_dates = [
        "janvier 2023",
        "janv. 2023",
        "févr. 2021",
        "sept. 2020",
        "01/2022",
        "15/03/2020",  # French DD/MM/YYYY
        "15/03/20",    # French DD/MM/YY
        "03/2021",     # MM/YYYY
        "2020-2023", 
        "à ce jour",
        "present",
        "Dec 2021",
        "2019 - présent",
        "75001",       # Should be rejected (postal code)
        "invalid date"
    ]
    
    print("Enhanced Fallback Date Parser Test Results:")
    print("=" * 50)
    
    for test_date in test_dates:
        parsed, is_present = parser.parse_single_date(test_date)
        formatted = parser.format_date_for_cv(parsed, is_present)
        iso_formatted = parser.format_date_iso(parsed, is_present)
        print(f"'{test_date}' -> {formatted} | ISO: {iso_formatted} (present: {is_present})")
    
    print("\nDate Range Tests:")
    print("=" * 30)
    
    range_tests = [
        "2020-2023",
        "jan 2021 - dec 2022", 
        "2019 - présent",
        "septembre 2020 - à ce jour"
    ]
    
    for test_range in range_tests:
        start, end, has_present = parser.parse_date_range(test_range)
        start_fmt = parser.format_date_for_cv(start)
        end_fmt = parser.format_date_for_cv(end, has_present)
        start_iso = parser.format_date_iso(start)
        end_iso = parser.format_date_iso(end, has_present)
        print(f"'{test_range}' -> {start_fmt} - {end_fmt} | ISO: {start_iso} - {end_iso}")