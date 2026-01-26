"""
Date Normalization Utilities
============================

Utilities for normalizing dates and ongoing status for the unified data model.
"""

from typing import Optional, Tuple


def normalize_ongoing_date(date_str: Optional[str]) -> Optional[str]:
    """
    Normalize date string to None if it represents an ongoing state.
    
    Args:
        date_str: Date string to normalize
        
    Returns:
        None if ongoing, normalized date string otherwise
    """
    if not date_str or not isinstance(date_str, str):
        return date_str
    
    date_lower = date_str.lower().strip()
    
    # Ongoing patterns - map to None
    ongoing_patterns = [
        'présent', 'present', 'en cours', 'current', 'currently',
        'à ce jour', 'ce jour', 'maintenant', 'now', 'today',
        'ongoing', 'actuel', 'actuellement', 'en_cours'
    ]
    
    if any(pattern in date_lower for pattern in ongoing_patterns):
        return None
    
    # Return normalized date string
    return date_str.strip()


def extract_ongoing_state(start_date: Optional[str], end_date: Optional[str]) -> Tuple[Optional[str], Optional[str], bool]:
    """
    Extract normalized start_date, end_date and ongoing state.
    
    Args:
        start_date: Raw start date string
        end_date: Raw end date string
        
    Returns:
        (normalized_start_date, normalized_end_date, is_ongoing)
    """
    normalized_start = normalize_ongoing_date(start_date)
    normalized_end = normalize_ongoing_date(end_date)
    
    # Determine ongoing state
    is_ongoing = normalized_end is None
    
    return normalized_start, normalized_end, is_ongoing


def format_date_for_ui(date_str: Optional[str], is_ongoing: bool = False) -> str:
    """
    Format date for UI display.
    
    Args:
        date_str: Date string to format
        is_ongoing: Whether this represents an ongoing state
        
    Returns:
        Formatted date string for UI
    """
    if is_ongoing or date_str is None:
        return ""  # Empty for ongoing - checkbox will handle display
    
    return str(date_str).strip()


def parse_ongoing_from_ui(end_date_input: str, ongoing_checked: bool) -> Optional[str]:
    """
    Parse end_date from UI inputs considering ongoing checkbox state.
    
    Args:
        end_date_input: End date from date input field
        ongoing_checked: State of ongoing checkbox
        
    Returns:
        Normalized end_date (None if ongoing)
    """
    if ongoing_checked:
        return None
    
    if not end_date_input or not end_date_input.strip():
        return None
    
    return end_date_input.strip()