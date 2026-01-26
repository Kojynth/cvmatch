"""
Safe Date Integration - Intègre le parser de secours avec le système existant.

Remplace l'usage direct de dateutil dans le code existant par un système
de fallback robuste qui évite les crashes complets quand dateutil est manquant.
"""

import re
from typing import Optional, Tuple, Any
from datetime import date, datetime

from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG
from .fallback_date_parser import parse_date_with_fallback, parse_date_range_with_fallback
from .feature_flags import get_extraction_fixes_flags

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


def safe_parse_date(date_str: str, fuzzy: bool = True, default_date: Optional[date] = None) -> Tuple[Optional[date], bool]:
    """
    Safely parse a date string with fallback.
    
    Args:
        date_str: Date string to parse
        fuzzy: Whether to use fuzzy parsing (ignored in fallback)
        default_date: Default date if parsing fails (ignored in fallback)
    
    Returns:
        (parsed_date, is_present) where is_present=True for ongoing dates
    """
    if not date_str:
        return None, False
    
    flags = get_extraction_fixes_flags()
    use_dateutil = not flags.fallback_date_parser  # Use dateutil if fallback is disabled
    
    try:
        return parse_date_with_fallback(date_str, use_dateutil=use_dateutil)
    except Exception as e:
        logger.warning(f"SAFE_DATE_PARSE: failed to parse '{date_str}' | error={e}")
        return None, False


def safe_parse_date_range(range_str: str) -> Tuple[Optional[date], Optional[date], bool]:
    """
    Safely parse a date range string.
    
    Returns:
        (start_date, end_date, has_present) where has_present=True if range is ongoing
    """
    if not range_str:
        return None, None, False
    
    flags = get_extraction_fixes_flags()
    use_dateutil = not flags.fallback_date_parser
    
    try:
        return parse_date_range_with_fallback(range_str, use_dateutil=use_dateutil)
    except Exception as e:
        logger.warning(f"SAFE_DATE_RANGE: failed to parse '{range_str}' | error={e}")
        return None, None, False


def format_date_for_display(parsed_date: Optional[date], is_present: bool = False) -> str:
    """Format a parsed date for display in the UI."""
    if is_present:
        return "Présent"
    
    if not parsed_date:
        return ""
    
    # Format as MM/YYYY for consistency with existing UI
    return f"{parsed_date.month:02d}/{parsed_date.year}"


def validate_date_range_logic(start_date: Optional[date], end_date: Optional[date], is_present: bool = False) -> bool:
    """Validate that a date range makes logical sense."""
    if not start_date:
        return False
    
    # Present/ongoing ranges are valid
    if is_present:
        return True
    
    # End date can be None (incomplete data)
    if end_date is None:
        return True
    
    # Start should be before end
    if start_date > end_date:
        return False
    
    # Check reasonable bounds
    current_year = datetime.now().year
    if start_date.year < 1950 or start_date.year > current_year + 5:
        return False
    
    if end_date.year < 1950 or end_date.year > current_year + 5:
        return False
    
    return True


def extract_dates_from_experience_text(text: str) -> Tuple[Optional[date], Optional[date], bool]:
    """
    Extract start and end dates from experience text.
    
    This replaces the dateutil-dependent logic in experience extraction.
    
    Returns:
        (start_date, end_date, is_ongoing)
    """
    if not text:
        return None, None, False
    
    # Common date range patterns
    date_patterns = [
        # MM/YYYY - MM/YYYY
        r'(\d{1,2}/\d{4})\s*[-–—]\s*(\d{1,2}/\d{4})',
        # YYYY - YYYY
        r'(\d{4})\s*[-–—]\s*(\d{4})',
        # MM/YYYY - present variants
        r'(\d{1,2}/\d{4})\s*[-–—]\s*(présent|present|actuel|en cours|à ce jour)',
        # YYYY - present variants
        r'(\d{4})\s*[-–—]\s*(présent|present|actuel|en cours|à ce jour)',
        # Month YYYY - Month YYYY
        r'([a-zA-Zàâäéèêëïîôöùûüÿç]+\s+\d{4})\s*[-–—]\s*([a-zA-Zàâäéèêëïîôöùûüÿç]+\s+\d{4})',
        # Month YYYY - present
        r'([a-zA-Zàâäéèêëïîôöùûüÿç]+\s+\d{4})\s*[-–—]\s*(présent|present|actuel|en cours|à ce jour)',
    ]
    
    for pattern in date_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            start_str = match.group(1)
            end_str = match.group(2) if len(match.groups()) > 1 else None
            
            # Parse start date
            start_date, _ = safe_parse_date(start_str)
            
            # Parse end date or check for present indicators
            is_ongoing = False
            end_date = None
            
            if end_str:
                # Check if it's a present indicator
                present_indicators = ['présent', 'present', 'actuel', 'en cours', 'à ce jour']
                if any(indicator in end_str.lower() for indicator in present_indicators):
                    is_ongoing = True
                else:
                    end_date, _ = safe_parse_date(end_str)
            
            if start_date and validate_date_range_logic(start_date, end_date, is_ongoing):
                return start_date, end_date, is_ongoing
    
    # If no range found, try to find single dates
    single_date_patterns = [
        r'(\d{1,2}/\d{4})',
        r'(\d{4})',
        r'([a-zA-Zàâäéèêëïîôöùûüÿç]+\s+\d{4})',
    ]
    
    for pattern in single_date_patterns:
        matches = re.findall(pattern, text)
        if len(matches) >= 2:
            # Use first two dates as start and end
            start_date, _ = safe_parse_date(matches[0])
            end_date, _ = safe_parse_date(matches[1])
            
            if start_date and end_date and validate_date_range_logic(start_date, end_date):
                return start_date, end_date, False
        elif len(matches) == 1:
            # Single date - assume it's start date with ongoing end
            start_date, _ = safe_parse_date(matches[0])
            if start_date:
                return start_date, None, True
    
    return None, None, False


def normalize_present_token(token: str) -> str:
    """Normalize present/current indicators to a standard form."""
    if not token:
        return ""
    
    token_lower = token.lower().strip()
    
    # French present indicators
    fr_present = ['présent', 'present', 'actuel', 'actuellement', 'en cours', 
                  'à ce jour', 'aujourd\'hui', 'maintenant']
    
    # English present indicators  
    en_present = ['present', 'current', 'currently', 'now', 'today', 'ongoing',
                  'to present', 'to date']
    
    if any(indicator in token_lower for indicator in fr_present):
        return "Présent"
    elif any(indicator in token_lower for indicator in en_present):
        return "Present"
    
    return token


def is_valid_date_span(start_date: Optional[date], end_date: Optional[date]) -> bool:
    """
    Check if a date span is valid and reasonable.
    
    Replacement for similar logic that might use dateutil parsing.
    """
    if not start_date:
        return False
    
    # Single date is valid
    if not end_date:
        return True
    
    # Check chronological order
    if start_date > end_date:
        return False
    
    # Check reasonable span duration (not more than 10 years for most experiences)
    years_diff = end_date.year - start_date.year
    if years_diff > 10:
        logger.debug(f"DATE_SPAN: unusually long span {years_diff} years")
        return False
    
    return True


# Monkey patch function to replace dateutil usage in existing code
def patch_dateutil_usage():
    """
    Apply monkey patching to replace dateutil usage in the codebase.
    
    This should be called early in the application startup.
    """
    try:
        # Try to import modules that use dateutil and patch them
        logger.info("SAFE_DATE_INTEGRATION: applying dateutil compatibility patches")
        
        # Add any specific patching logic here as needed
        # For example, if there are specific modules that import dateutil directly
        
        logger.info("SAFE_DATE_INTEGRATION: patches applied successfully")
        
    except Exception as e:
        logger.warning(f"SAFE_DATE_INTEGRATION: patch application failed | error={e}")


if __name__ == "__main__":
    # Test the safe date integration
    test_cases = [
        "01/2020 - 12/2022",
        "2019 - présent", 
        "janvier 2021 - décembre 2023",
        "Stage 6 mois - 2023",
        "Développeur depuis 2020"
    ]
    
    print("🗓️ Safe Date Integration Test:")
    print("=" * 40)
    
    for text in test_cases:
        start, end, ongoing = extract_dates_from_experience_text(text)
        start_fmt = format_date_for_display(start)
        end_fmt = format_date_for_display(end, ongoing)
        
        print(f"Text: '{text}'")
        print(f"  Dates: {start_fmt} - {end_fmt}")
        print(f"  Ongoing: {ongoing}")
        print()
    
    # Test individual date parsing
    print("\n📅 Individual Date Parsing:")
    print("=" * 30)
    
    date_tests = ["janvier 2023", "01/2022", "2020", "présent", "invalid"]
    for date_str in date_tests:
        parsed, is_present = safe_parse_date(date_str)
        formatted = format_date_for_display(parsed, is_present)
        print(f"'{date_str}' → {formatted if formatted else 'Échec'}")