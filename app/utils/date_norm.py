"""
Enhanced Date Normalization - Extension of date_normalize.py with strict validation.

Adds temporal validation, education-specific date handling, and enhanced
French format support for education extraction hardening.
"""

import re
import unicodedata
from typing import Tuple, Optional, Dict, Any, List
from datetime import datetime, date

# CRITICAL: Import dateutil avec fallback vers notre parser de secours
try:
    from dateutil import parser as date_parser
    DATEUTIL_AVAILABLE = True
except ImportError:
    # Fallback vers notre parser de secours si dateutil est manquant
    try:
        from .fallback_date_parser import get_fallback_date_parser
        date_parser = get_fallback_date_parser()
        DATEUTIL_AVAILABLE = False
    except ImportError:
        # Si même le fallback n'est pas disponible, utiliser None 
        date_parser = None
        DATEUTIL_AVAILABLE = False

from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG
from ..rules.date_normalize import (
    normalize_present_token, normalize_date_span, 
    _normalize_single_date, is_valid_date_range,
    PRESENT_TOKENS
)

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)

# Log du système de parsing utilisé
if DATEUTIL_AVAILABLE:
    logger.info("DATE_SYSTEM: Using python-dateutil for date parsing")
elif date_parser is not None:
    logger.info("DATE_SYSTEM: Using fallback date parser (dateutil unavailable)")
else:
    logger.warning("DATE_SYSTEM: No date parser available - limited date parsing functionality")


def normalize_date_range_with_validation(text: str, context_lines: Optional[List[str]] = None) -> Tuple[Optional[datetime], Optional[datetime], bool, Dict[str, Any]]:
    """
    Enhanced date range normalization with strict temporal validation.
    
    Args:
        text: Text containing date range
        context_lines: Optional context for better parsing
        
    Returns:
        Tuple (start_date, end_date, is_current, validation_flags)
    """
    validation_flags = {
        'temporal_valid': True,
        'format_valid': True,
        'range_reasonable': True,
        'present_detected': False,
        'date_warning': None
    }
    
    if not text:
        validation_flags['format_valid'] = False
        return None, None, False, validation_flags
    
    # Use existing normalization for basic parsing
    start_str, end_str, is_current = normalize_date_span(text)
    validation_flags['present_detected'] = is_current
    
    start_date = None
    end_date = None
    
    try:
        # Parse start date
        if start_str:
            start_date = _parse_date_string_enhanced(start_str)
            if not start_date:
                validation_flags['format_valid'] = False
                logger.debug(f"DATE_NORM: failed to parse start date '{start_str}'")
        
        # Parse end date
        if end_str and not is_current:
            end_date = _parse_date_string_enhanced(end_str)
            if not end_date:
                validation_flags['format_valid'] = False
                logger.debug(f"DATE_NORM: failed to parse end date '{end_str}'")
        
        # CRITICAL: Temporal consistency validation
        if start_date and end_date and end_date < start_date:
            validation_flags['temporal_valid'] = False
            validation_flags['date_warning'] = 'end_before_start'
            logger.warning(f"DATE_NORM: temporal inconsistency detected - end ({end_date}) < start ({start_date})")
        
        # Range reasonableness check
        if start_date and end_date:
            duration_years = (end_date - start_date).days / 365.25
            if duration_years < 0.08:  # Less than 1 month
                validation_flags['range_reasonable'] = False
                validation_flags['date_warning'] = 'duration_too_short'
            elif duration_years > 20:  # More than 20 years
                validation_flags['range_reasonable'] = False
                validation_flags['date_warning'] = 'duration_too_long'
        
        # Current date validation (if marked as current, end should be None/recent)
        if is_current and end_date:
            current_date = datetime.now()
            if end_date < current_date.replace(year=current_date.year-1):
                # End date is more than a year ago but marked as current
                validation_flags['date_warning'] = 'current_date_mismatch'
                logger.debug(f"DATE_NORM: current flag but end_date {end_date} is old")
        
    except Exception as e:
        logger.warning(f"DATE_NORM: parsing exception for '{text}': {e}")
        validation_flags['format_valid'] = False
        validation_flags['date_warning'] = 'parsing_exception'
    
    return start_date, end_date, is_current, validation_flags


def _parse_date_string_enhanced(date_str: str) -> Optional[datetime]:
    """
    Enhanced date parsing with French format support.
    
    Args:
        date_str: Date string to parse
        
    Returns:
        Parsed datetime or None
    """
    if not date_str or date_str.strip().upper() == 'PRESENT':
        return None
    
    date_str = date_str.strip()

    iso_month = re.match(r'^(\d{4})-(\d{1,2})$', date_str)
    if iso_month:
        try:
            return datetime(int(iso_month.group(1)), int(iso_month.group(2)), 1)
        except ValueError:
            pass
    
    # Try normalized single date first (from existing module)
    normalized = _normalize_single_date(date_str)
    if normalized and '-' in normalized:
        try:
            # Convert YYYY-MM to datetime
            year, month = normalized.split('-')
            return datetime(int(year), int(month), 1)
        except (ValueError, TypeError):
            pass
    
    # Enhanced French format patterns
    french_patterns = [
        # DD/MM/YYYY or DD/MM/YY
        (r'^(\d{1,2})/(\d{1,2})/(\d{2,4})$', lambda m: _parse_dmy(m.group(1), m.group(2), m.group(3))),
        
        # MM/YYYY
        (r'^(\d{1,2})/(\d{4})$', lambda m: datetime(int(m.group(2)), int(m.group(1)), 1)),
        
        # YYYY alone
        (r'^\d{4}$', lambda m: datetime(int(m.group(0)), 1, 1)),
        
        # French month names
        (r'^(\d{1,2})\s+(janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s+(\d{4})$', 
         lambda m: _parse_french_month(m.group(1), m.group(2), m.group(3))),
        
        # Abbreviated French months
        (r'^(\d{1,2})\s+(jan|fév|mar|avr|mai|jun|jul|aoû|sep|oct|nov|déc)\.?\s+(\d{4})$',
         lambda m: _parse_french_month_abbr(m.group(1), m.group(2), m.group(3)))
    ]
    
    for pattern, parser_func in french_patterns:
        match = re.match(pattern, date_str, re.IGNORECASE)
        if match:
            try:
                result = parser_func(match)
                if result:
                    logger.debug(f"DATE_PARSE: French format '{date_str}' -> {result}")
                    return result
            except (ValueError, TypeError) as e:
                logger.debug(f"DATE_PARSE: French pattern failed for '{date_str}': {e}")
                continue
    
    # Fallback to dateutil parser for international formats (if available)
    if date_parser is not None:
        try:
            if DATEUTIL_AVAILABLE:
                # Utiliser dateutil directement
                parsed = date_parser.parse(date_str, dayfirst=True, fuzzy=True)
                logger.debug(f"DATE_PARSE: dateutil fallback '{date_str}' -> {parsed}")
                return parsed
            else:
                # Utiliser notre fallback parser
                parsed, _ = date_parser.parse_single_date(date_str)
                if parsed:
                    logger.debug(f"DATE_PARSE: fallback parser '{date_str}' -> {parsed}")
                    return parsed
        except Exception as e:
            logger.debug(f"DATE_PARSE: parser failed for '{date_str}': {e}")
    
    # Si aucun parser disponible, retourner None
    logger.warning(f"DATE_PARSE: no parser available for '{date_str}' - install python-dateutil")
    return None


def _parse_dmy(day_str: str, month_str: str, year_str: str) -> Optional[datetime]:
    """Parse day/month/year format."""
    try:
        day = int(day_str)
        month = int(month_str)
        year = int(year_str)
        
        # Handle 2-digit years
        if year < 100:
            if year < 30:
                year += 2000  # 00-29 -> 2000-2029
            else:
                year += 1900  # 30-99 -> 1930-1999
        
        # Validate ranges
        if not (1 <= month <= 12):
            return None
        if not (1 <= day <= 31):
            return None
        if not (1970 <= year <= 2030):
            return None
        
        return datetime(year, month, day)
    except (ValueError, TypeError):
        return None


def _parse_french_month(day_str: str, month_name: str, year_str: str) -> Optional[datetime]:
    """Parse French month names."""
    french_months = {
        'janvier': 1, 'février': 2, 'mars': 3, 'avril': 4,
        'mai': 5, 'juin': 6, 'juillet': 7, 'août': 8,
        'septembre': 9, 'octobre': 10, 'novembre': 11, 'décembre': 12
    }
    
    try:
        day = int(day_str)
        month = french_months.get(month_name.lower())
        year = int(year_str)
        
        if month and 1 <= day <= 31 and 1970 <= year <= 2030:
            return datetime(year, month, day)
    except (ValueError, TypeError):
        pass
    return None


def _parse_french_month_abbr(day_str: str, month_abbr: str, year_str: str) -> Optional[datetime]:
    """Parse abbreviated French month names."""
    french_abbrevs = {
        'jan': 1, 'fév': 2, 'mar': 3, 'avr': 4, 'mai': 5, 'jun': 6,
        'jul': 7, 'aoû': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'déc': 12
    }
    
    try:
        day = int(day_str)
        month = french_abbrevs.get(month_abbr.lower())
        year = int(year_str)
        
        if month and 1 <= day <= 31 and 1970 <= year <= 2030:
            return datetime(year, month, day)
    except (ValueError, TypeError):
        pass
    return None


def extract_education_dates(text: str) -> Dict[str, Any]:
    """
    Extract and validate dates specifically for education contexts.
    
    Args:
        text: Education text line
        
    Returns:
        Dict with date information and validation status
    """
    start_date, end_date, is_current, validation_flags = normalize_date_range_with_validation(text)
    
    result = {
        'start_date': start_date,
        'end_date': end_date,
        'is_current': is_current,
        'original_text': text,
        'validation_flags': validation_flags,
        'formatted_start': format_date_for_display(start_date) if start_date else None,
        'formatted_end': format_date_for_display(end_date) if end_date else None,
        'duration_months': None
    }
    
    # Calculate duration if both dates available
    if start_date and end_date:
        duration_days = (end_date - start_date).days
        result['duration_months'] = round(duration_days / 30.44, 1)
    elif start_date and is_current:
        current_date = datetime.now()
        duration_days = (current_date - start_date).days
        result['duration_months'] = round(duration_days / 30.44, 1)
    
    return result


def format_date_for_display(dt: Optional[datetime], format_type: str = 'short') -> Optional[str]:
    """
    Format datetime for display in various formats.
    
    Args:
        dt: Datetime to format
        format_type: 'short' (MM/YYYY), 'long' (Mois YYYY), 'iso' (YYYY-MM-DD)
        
    Returns:
        Formatted date string
    """
    if not dt:
        return None
    
    if format_type == 'short':
        return dt.strftime('%m/%Y')
    elif format_type == 'long':
        months_fr = [
            'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
            'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'
        ]
        month_name = months_fr[dt.month - 1]
        return f"{month_name} {dt.year}"
    elif format_type == 'iso':
        return dt.strftime('%Y-%m-%d')
    else:
        return dt.strftime('%m/%Y')  # Default to short


def validate_education_date_range(start_date: Optional[datetime], end_date: Optional[datetime], 
                                is_current: bool = False) -> Tuple[bool, Optional[str]]:
    """
    Validate date range specifically for education contexts.
    
    Args:
        start_date: Start date
        end_date: End date (None if current)
        is_current: Whether education is ongoing
        
    Returns:
        Tuple (is_valid, error_message)
    """
    if not start_date:
        return False, "Missing start date"
    
    # Check start date is reasonable for education
    if start_date.year < 1950 or start_date.year > datetime.now().year + 5:
        return False, f"Start year {start_date.year} out of reasonable range"
    
    # If not current, must have end date
    if not is_current and not end_date:
        return True, None  # Allow incomplete date ranges for some contexts
    
    # Temporal consistency  
    if end_date and end_date < start_date:
        return False, "End date before start date"
    
    # Duration checks
    if start_date and end_date:
        duration_years = (end_date - start_date).days / 365.25
        if duration_years < 0.05:  # Less than ~20 days
            return False, "Duration too short for education"
        if duration_years > 25:  # More than 25 years
            return False, "Duration too long for education"
    
    # Current date validation
    if is_current and end_date:
        current_date = datetime.now()
        if end_date < current_date.replace(year=current_date.year-2):
            return False, "End date too old for current education"
    
    return True, None


def normalize_date(date_text: str, context_lines: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Enhanced single date normalization with validation and current detection.
    
    Args:
        date_text: Date text to normalize
        context_lines: Optional context for better parsing
        
    Returns:
        Dict with normalized date info and validation flags
    """
    result = {
        'original_text': date_text,
        'parsed_date': None,
        'is_current': False,
        'date_format': 'unknown',
        'validation_flags': {
            'format_valid': False,
            'range_reasonable': True,
            'current_detected': False
        }
    }
    
    if not date_text or len(date_text.strip()) < 3:
        return result
    
    # Check for current/present indicators
    present_indicators = ['présent', 'present', 'actuel', 'en cours', 'à ce jour', 'current', 'now']
    text_lower = date_text.lower().strip()
    
    for indicator in present_indicators:
        if indicator in text_lower:
            result['is_current'] = True
            result['validation_flags']['current_detected'] = True
            logger.debug(f"DATE_NORM: current detected with '{indicator}'")
            break
    
    # If marked as current, no need to parse specific date
    if result['is_current']:
        result['validation_flags']['format_valid'] = True
        return result
    
    # Parse specific date formats
    parsed_date = _parse_date_string_enhanced(date_text)
    if parsed_date:
        result['parsed_date'] = parsed_date
        result['validation_flags']['format_valid'] = True
        
        # Determine format type
        if re.match(r'^\d{4}$', date_text.strip()):
            result['date_format'] = 'year_only'
        elif re.match(r'^\d{1,2}/\d{4}$', date_text.strip()):
            result['date_format'] = 'month_year'
        elif re.match(r'^\d{1,2}/\d{1,2}/\d{2,4}$', date_text.strip()):
            result['date_format'] = 'full_date'
        else:
            result['date_format'] = 'parsed'
        
        # Validate reasonableness
        current_year = datetime.now().year
        if parsed_date.year < 1970 or parsed_date.year > current_year + 5:
            result['validation_flags']['range_reasonable'] = False
            logger.debug(f"DATE_NORM: unreasonable year {parsed_date.year}")
    
    return result


def normalize_date_range_with_swap(date_range_text: str, context_lines: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Enhanced date range normalization with automatic swap for inverted dates.
    
    Args:
        date_range_text: Text containing date range
        context_lines: Optional context lines
        
    Returns:
        Dict with normalized date range and swap information
    """
    result = {
          'original_text': date_range_text,
          'start_date': None,
          'end_date': None, 
          'is_current': False,
          'date_swap': False,
          'date_swapped': False,
          'validation_flags': {
              'temporal_valid': True,
              'format_valid': True,
              'range_reasonable': True,
              'swap_performed': False
          }
      }
    
    if not date_range_text:
        result['validation_flags']['format_valid'] = False
        return result
    
    # Use existing range normalization as base
    start_date, end_date, is_current, validation_flags = normalize_date_range_with_validation(
        date_range_text, context_lines
    )
    
    result['start_date'] = start_date
    result['end_date'] = end_date
    result['is_current'] = is_current
    result['validation_flags'].update(validation_flags)
    
    # Check for date swap needed (end_date < start_date)
    if start_date and end_date and end_date < start_date:
        # Perform swap
        result['start_date'] = end_date
        result['end_date'] = start_date
        result['date_swap'] = True
        result['date_swapped'] = True
        result['validation_flags']['swap_performed'] = True
        result['validation_flags']['temporal_valid'] = True  # Now valid after swap

        logger.info(
            f"DATE_SWAP: performed swap | original: {start_date} - {end_date} | swapped: {end_date} - {start_date}"
        )
    
    result['parsed_start_date'] = result['start_date']
    result['parsed_end_date'] = result['end_date']
    return result


def validate_dates_for_experience(start_date: Optional[datetime], end_date: Optional[datetime], 
                                is_current: bool, employment_keywords_present: bool) -> Dict[str, Any]:
    """
    Validate date information specifically for experience extraction.
    
    Args:
        start_date: Start date
        end_date: End date
        is_current: Whether marked as current
        employment_keywords_present: Whether employment keywords found in context
        
    Returns:
        Dict with validation results and recommendations
    """
    validation = {
        'is_valid': True,
        'should_keep': True,
        'issues': [],
        'confidence_penalty': 0.0
    }
    
    # Rule: If both dates missing AND no employment keywords, discard
    if not start_date and not end_date and not is_current:
        if not employment_keywords_present:
            validation['is_valid'] = False
            validation['should_keep'] = False
            validation['issues'].append('no_dates_no_employment_context')
            return validation
        else:
            # Missing dates but has employment context - penalize but don't discard
            validation['confidence_penalty'] += 0.2
            validation['issues'].append('missing_dates_but_has_context')
    
    # Validate date reasonableness
    current_year = datetime.now().year
    
    if start_date:
        if start_date.year < 1970 or start_date.year > current_year + 1:
            validation['confidence_penalty'] += 0.3
            validation['issues'].append('unreasonable_start_date')
        
        # Future start dates should be rare
        if start_date.year > current_year:
            validation['confidence_penalty'] += 0.1
            validation['issues'].append('future_start_date')
    
    if end_date:
        if end_date.year < 1970 or end_date.year > current_year + 1:
            validation['confidence_penalty'] += 0.3
            validation['issues'].append('unreasonable_end_date')
        
        # Very long experiences (>15 years) are suspicious
        if start_date and (end_date.year - start_date.year) > 15:
            validation['confidence_penalty'] += 0.2
            validation['issues'].append('very_long_duration')
        
        # Very short experiences (<1 month) without current flag
        if start_date and not is_current:
            duration_days = (end_date - start_date).days
            if duration_days < 30:
                validation['confidence_penalty'] += 0.1
                validation['issues'].append('very_short_duration')
    
    # Current experiences should not have end dates
    if is_current and end_date:
        validation['confidence_penalty'] += 0.1
        validation['issues'].append('current_with_end_date')
    
    # Apply confidence penalty to determine final validity
    if validation['confidence_penalty'] >= 0.5:
        validation['should_keep'] = False
        validation['issues'].append('high_confidence_penalty')
    
    return validation


# Convenience functions for backward compatibility
def normalize_date_range(text: str) -> Tuple[Optional[datetime], Optional[datetime], bool]:
    """
    Backward compatible function that returns basic date range.
    
    Args:
        text: Text with date range
        
    Returns:
        Tuple (start_date, end_date, is_current)
    """
    start_date, end_date, is_current, _ = normalize_date_range_with_validation(text)
    return start_date, end_date, is_current
