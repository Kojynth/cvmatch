import re
from typing import Any


def is_valid_date_format(date_str: str) -> bool:
    """Validate a formatted date string is in a reasonable range (year 1990..2030)."""
    try:
        year_match = re.search(r"\b(\d{4})\b", date_str)
        if year_match:
            year = int(year_match.group(1))
            return 1990 <= year <= 2030
        return True  # Accept if no detectable year
    except (ValueError, AttributeError):
        return False


def is_valid_year(year_value: Any) -> bool:
    """Check if a year-like value is valid (1990..2030)."""
    try:
        year = int(year_value)
        return 1990 <= year <= 2030
    except (ValueError, TypeError):
        return False


def normalize_confidence(confidence: Any) -> str:
    """Normalize confidence to one of: high, medium, low, unknown."""
    if not confidence:
        return 'medium'

    conf_str = str(confidence).lower()

    if conf_str in ['high', 'élévé', 'élevée', 'fort', 'forte', '3', 'ǸlevǸ', 'ǸlevǸe']:
        return 'high'
    elif conf_str in ['low', 'faible', 'bas', 'basse', '1']:
        return 'low'
    elif conf_str in ['unknown', 'inconnu', 'incertain', '0']:
        return 'unknown'
    else:
        return 'medium'

