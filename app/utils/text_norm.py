"""
Utilities for generic text normalization and tokenization.

This module provides locale-agnostic text processing functions
to handle accents, punctuation, and stopwords for CV extraction.

ENHANCED: Unicode NFKC normalization, PUA character stripping,
icon-to-word mapping, and ftfy-like UTF-8 error correction.
"""

import re
import unicodedata
from typing import List, Set, Optional
from functools import lru_cache

try:
    import ftfy
    HAS_FTFY = True
except ImportError:
    HAS_FTFY = False


# Generic stopwords (minimal set, locale-agnostic)
STOPWORDS = {
    # French
    'le', 'la', 'les', 'un', 'une', 'des', 'du', 'de', 'et', 'ou', 'à', 'au', 'aux',
    'dans', 'sur', 'avec', 'par', 'pour', 'sans', 'sous', 'vers', 'chez', 'depuis',
    'pendant', 'avant', 'après', 'entre', 'parmi', 'selon', 'contre', 'malgré',
    'ce', 'cette', 'ces', 'son', 'sa', 'ses', 'mon', 'ma', 'mes', 'ton', 'ta', 'tes',
    'notre', 'nos', 'votre', 'vos', 'leur', 'leurs', 'qui', 'que', 'dont', 'où',
    'il', 'elle', 'ils', 'elles', 'je', 'tu', 'nous', 'vous', 'se', 'me', 'te',
    'lui', 'leur', 'en', 'y', 'ne', 'pas', 'plus', 'moins', 'très', 'assez',
    'bien', 'mal', 'mieux', 'beaucoup', 'peu', 'trop', 'tout', 'tous', 'toute',
    'toutes', 'autre', 'autres', 'même', 'mêmes', 'tel', 'telle', 'tels', 'telles',
    # English
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with',
    'by', 'from', 'about', 'into', 'through', 'during', 'before', 'after', 'above',
    'below', 'up', 'down', 'out', 'off', 'over', 'under', 'again', 'further', 'then',
    'once', 'here', 'there', 'when', 'where', 'why', 'how', 'all', 'any', 'both',
    'each', 'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not',
    'only', 'own', 'same', 'so', 'than', 'too', 'very', 'can', 'will', 'just',
    'should', 'now', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'them', 'their',
    'what', 'which', 'who', 'whom', 'this', 'that', 'these', 'those', 'am', 'is',
    'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does',
    'did', 'doing', 'would', 'could', 'should', 'may', 'might', 'must', 'shall'
}


def normalize_text(text: str) -> str:
    """
    Normalize text by handling Unicode, punctuation and spacing.
    Conserve accents et casse utile pour l'affichage, garde sauts de ligne.
    
    Args:
        text: Raw text to normalize
        
    Returns:
        Normalized text with preserved accents and line breaks
    """
    if not text:
        return ""
    
    # Replace Unicode dashes and quotes
    text = text.replace('\u2013', '-').replace('\u2014', '-')  # en-dash, em-dash
    text = text.replace('\u2018', "'").replace('\u2019', "'")  # smart quotes
    text = text.replace('\u201c', '"').replace('\u201d', '"')  # smart double quotes
    text = text.replace('\u00a0', ' ')  # non-breaking space
    
    # Collapse multiple spaces but preserve line breaks
    text = re.sub(r'[ \t]+', ' ', text)  # Only horizontal spaces
    text = re.sub(r'\n\s*\n', '\n\n', text)  # Clean up multiple newlines
    
    return text.strip()


def normalize_text_for_ui(text: str, fix_mojibake: bool = True) -> str:
    """
    Enhanced text normalization for UI display with mojibake prevention.
    
    Args:
        text: Raw text to normalize
        fix_mojibake: Whether to apply mojibake fixes
        
    Returns:
        UI-ready normalized text
    """
    if not text:
        return ""
    
    # Step 1: NFKC normalization to handle composed characters
    normalized = unicodedata.normalize('NFKC', text)
    
    # Step 2: Remove Private Use Area characters (U+E000–U+F8FF) that cause mojibake
    if fix_mojibake:
        normalized = _strip_private_use_area(normalized)
        
        # Step 3: Map common icon glyphs to words
        normalized = _map_icon_glyphs(normalized)
        
        # Step 4: Fix common UTF-8 encoding errors
        normalized = _fix_utf8_errors(normalized)
    
    # Step 5: Apply standard text normalization
    normalized = normalize_text(normalized)
    
    return normalized


def _strip_private_use_area(text: str) -> str:
    """
    Remove Private Use Area Unicode characters (U+E000–U+F8FF).
    
    Args:
        text: Text potentially containing PUA characters
        
    Returns:
        Text with PUA characters removed
    """
    # Remove PUA characters - these often appear as garbled symbols
    filtered_chars = []
    
    for char in text:
        code_point = ord(char)
        # Private Use Area: U+E000 to U+F8FF
        if not (0xE000 <= code_point <= 0xF8FF):
            filtered_chars.append(char)
    
    return ''.join(filtered_chars)


def _map_icon_glyphs(text: str) -> str:
    """
    Map common icon glyphs to readable words.
    
    Args:
        text: Text containing icon glyphs
        
    Returns:
        Text with icons mapped to words
    """
    icon_mapping = {
        # Phone/contact icons
        '📞': 'Tel',
        '📱': 'Mobile',
        '☎️': 'Phone',
        '☎': 'Phone',
        
        # Email icons
        '✉️': 'Email',
        '✉': 'Email',
        '📧': 'Email',
        '📨': 'Email',
        '📩': 'Email',
        
        # Location icons
        '📍': 'Location',
        '📌': 'Location',
        '🏠': 'Address',
        '🏡': 'Home',
        '🌍': 'Location',
        '🌎': 'Location',
        '🌏': 'Location',
        
        # Date/calendar icons
        '📅': 'Date',
        '📆': 'Calendar',
        '🗓️': 'Schedule',
        '🗓': 'Schedule',
        
        # Education/work icons
        '🎓': 'Education',
        '🏫': 'School',
        '🏢': 'Company',
        '💼': 'Work',
        '📚': 'Studies',
        '📖': 'Education',
        
        # Skills/tech icons
        '💻': 'Computer',
        '⌨️': 'Tech',
        '🖥️': 'Computer',
        '💡': 'Skills',
        '🔧': 'Tools',
        '⚙️': 'Technical',
        
        # Common symbols that get mangled
        '•': '•',  # Keep bullet points
        '→': '→',  # Keep arrows
        '▶': '▶',  # Keep play symbols
        '►': '►',  # Keep play symbols
        '★': '★',  # Keep stars
        '☆': '☆',  # Keep empty stars
    }
    
    for icon, word in icon_mapping.items():
        text = text.replace(icon, word)
    
    return text


def _fix_utf8_errors(text: str) -> str:
    """
    Fix common UTF-8 encoding errors (ftfy-like functionality).

    Uses ftfy library if available, otherwise applies manual fixes.

    Args:
        text: Text with potential UTF-8 errors

    Returns:
        Text with UTF-8 errors corrected
    """
    if not text:
        return text

    # Use ftfy if available for comprehensive fixing
    if HAS_FTFY:
        try:
            fixed = ftfy.fix_text(text)
            # Additional fixes that ftfy might miss
            fixed = _apply_additional_fixes(fixed)
            return fixed
        except Exception:
            # Fall back to manual fixes if ftfy fails
            pass

    # Manual UTF-8 mojibake fixes
    utf8_fixes = {
        # French characters commonly mangled
        'Ã©': 'é',  'Ã¨': 'è',  'Ã ': 'à',  'Ã¢': 'â',  'Ã´': 'ô',
        'Ã®': 'î',  'Ã§': 'ç',  'Ã¹': 'ù',  'Ã»': 'û',  'Ãª': 'ê',
        'Ã«': 'ë',  'Ã¯': 'ï',  'Ã¼': 'ü',  'Ã¶': 'ö',  'Ã¤': 'ä',

        # Uppercase variants
        'Ã‰': 'É',  'Ã€': 'À',  'Ã‡': 'Ç',  'Ãˆ': 'È',

        # Common quote/dash issues
        'â€™': "'",   'â€œ': '"',   'â€': '"',    'â€"': '—',
        'â€"': '–',   'â€¦': '…',

        # Other common issues
        'Â': '',      'â€‹': '',    'ï¿½': '',   # Replacement character
        'â€‹': '',    # Zero-width space

        # Windows-1252 to UTF-8 issues
        'Ã¢â‚¬â„¢': "'",  'Ã¢â‚¬Å"': '"',  'Ã¢â‚¬': '"',
        'Ã¢â‚¬â€œ': '—',   'Ã¢â‚¬â€œ': '–',
    }

    for mojibake, correct in utf8_fixes.items():
        text = text.replace(mojibake, correct)

    text = _apply_additional_fixes(text)
    return text


def _apply_additional_fixes(text: str) -> str:
    """Apply additional character fixes that might be missed."""
    additional_fixes = {
        # Zero-width characters
        '\u200b': '',  # Zero-width space
        '\u200c': '',  # Zero-width non-joiner
        '\u200d': '',  # Zero-width joiner
        '\ufeff': '',  # Byte order mark

        # Control characters
        '\x00': '',  # Null
        '\x01': '',  # Start of heading
        '\x02': '',  # Start of text
        '\x03': '',  # End of text
        '\x04': '',  # End of transmission
        '\x05': '',  # Enquiry
        '\x06': '',  # Acknowledge
        '\x07': '',  # Bell
        '\x08': '',  # Backspace
        '\x0b': '',  # Vertical tab
        '\x0c': '',  # Form feed
        '\x0e': '',  # Shift out
        '\x0f': '',  # Shift in

        # Additional replacement patterns
        '…': '...',  # Convert ellipsis to three dots for compatibility
    }

    for wrong, correct in additional_fixes.items():
        text = text.replace(wrong, correct)

    return text


def normalize_text_for_matching(text: str) -> str:
    """
    Normalize text for matching by lowercasing and stripping accents.
    Matches the behavior previously duplicated in multiple modules.

    Args:
        text: Text to normalize for matching

    Returns:
        Lowercased, accent-stripped, trimmed text
    """
    if not text:
        return ""

    # Strip accents using NFD and remove combining marks
    normalized = unicodedata.normalize('NFD', text.lower())
    normalized = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')

    return normalized.strip()


def normalize_for_comparison(text: str) -> str:
    """
    Normalize text for fuzzy comparison.
    unicodedata.normalize("NFKD"), suppression accents, lower(), 
    remplace tout non alphanum par espace, collapse espaces.
    
    Args:
        text: Text to normalize
        
    Returns:
        Text normalized for comparison (no accents, only alphanum)
    """
    if not text:
        return ""
    
    # Unicode normalization NFKD
    text = unicodedata.normalize('NFKD', text)
    
    # Remove accents (combining characters)
    text = ''.join(c for c in text if not unicodedata.combining(c))
    
    # Lower case
    text = text.lower()
    
    # Replace all non-alphanumeric with space
    text = re.sub(r'[^a-zA-Z0-9]', ' ', text)
    
    # Collapse multiple spaces
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()


def tokenize(text: str) -> List[str]:
    """
    Tokenize text into list of normalized words.
    Utilise normalize_for_comparison, split sur espaces, enlève stopwords FR/EN,
    filtre tokens < 2 caractères et purement numériques.
    
    Args:
        text: Text to tokenize
        
    Returns:
        List of normalized tokens
    """
    if not text:
        return []
    
    # Use normalize_for_comparison for consistency
    normalized = normalize_for_comparison(text)
    
    # Split on spaces
    tokens = normalized.split()
    
    # Filter tokens: >= 2 chars and not purely numeric
    filtered_tokens = [
        token for token in tokens 
        if len(token) >= 2 and not token.isdigit()
    ]
    
    # Remove stopwords
    filtered_tokens = [token for token in filtered_tokens if token not in STOPWORDS]
    
    return filtered_tokens


def jaccard_similarity(tokens1: List[str], tokens2: List[str]) -> float:
    """
    Calculate Jaccard similarity between two token lists.
    
    Args:
        tokens1: First set of tokens
        tokens2: Second set of tokens
        
    Returns:
        Jaccard similarity (0.0 to 1.0)
    """
    if not tokens1 and not tokens2:
        return 1.0
    
    if not tokens1 or not tokens2:
        return 0.0
    
    set1, set2 = set(tokens1), set(tokens2)
    intersection = len(set1.intersection(set2))
    union = len(set1.union(set2))
    
    return intersection / union if union > 0 else 0.0


# =============================================================================
# UI SANITIZATION FUNCTIONS
# =============================================================================

def sanitize_widget_tree(widget) -> int:
    """
    Sanitize text in a widget tree to prevent mojibake display issues.

    Recursively walks through a QWidget tree and applies text normalization
    to all text-containing widgets (QLabel, QPushButton, QLineEdit, etc.).

    Args:
        widget: Root QWidget to sanitize

    Returns:
        Number of widgets sanitized
    """
    sanitized_count = 0

    try:
        # Import PySide6 components here to avoid dependency issues
        from PySide6.QtWidgets import (
            QLabel, QPushButton, QLineEdit, QTextEdit, QPlainTextEdit,
            QGroupBox, QCheckBox, QRadioButton, QTabWidget, QAction
        )

        # Sanitize current widget if it has text
        if hasattr(widget, 'text') and callable(getattr(widget, 'text')):
            original_text = widget.text()
            if original_text:
                sanitized_text = normalize_text_for_ui(original_text, fix_mojibake=True)
                if sanitized_text != original_text:
                    widget.setText(sanitized_text)
                    sanitized_count += 1

        # Special handling for different widget types
        if isinstance(widget, (QTextEdit, QPlainTextEdit)):
            original_html = widget.toHtml() if hasattr(widget, 'toHtml') else widget.toPlainText()
            if original_html:
                sanitized_html = normalize_text_for_ui(original_html, fix_mojibake=True)
                if sanitized_html != original_html:
                    if hasattr(widget, 'setHtml'):
                        widget.setHtml(sanitized_html)
                    else:
                        widget.setPlainText(sanitized_html)
                    sanitized_count += 1

        elif hasattr(widget, 'title') and callable(getattr(widget, 'title')):
            # For QGroupBox, QTabWidget, etc.
            original_title = widget.title()
            if original_title:
                sanitized_title = normalize_text_for_ui(original_title, fix_mojibake=True)
                if sanitized_title != original_title:
                    widget.setTitle(sanitized_title)
                    sanitized_count += 1

        elif isinstance(widget, QTabWidget):
            # Sanitize tab titles
            for i in range(widget.count()):
                original_tab_text = widget.tabText(i)
                if original_tab_text:
                    sanitized_tab_text = normalize_text_for_ui(original_tab_text, fix_mojibake=True)
                    if sanitized_tab_text != original_tab_text:
                        widget.setTabText(i, sanitized_tab_text)
                        sanitized_count += 1

        # Recursively sanitize child widgets
        if hasattr(widget, 'children'):
            for child in widget.children():
                sanitized_count += sanitize_widget_tree(child)

    except Exception as e:
        # Log error but don't break the application
        import logging
        logging.warning(f"Widget sanitization error: {e}")

    return sanitized_count


def safe_emoji(text: str, fallback_mode: bool = False) -> str:
    """
    Ensure emoji/icon text is safe for display across different systems.

    Args:
        text: Text that may contain emoji or icons
        fallback_mode: If True, replace all emoji with text equivalents

    Returns:
        Text safe for display
    """
    if not text:
        return text

    # Apply comprehensive text normalization
    normalized = normalize_text_for_ui(text, fix_mojibake=True)

    if fallback_mode:
        # Additional emoji-to-text replacements for problematic systems
        emoji_fallbacks = {
            '👤': '[Person]',
            '⚙️': '[Settings]',
            '📋': '[Notes]',
            '📙': '[History]',
            '🏠': '[Home]',
            '📁': '[Folder]',
            '📂': '[Open Folder]',
            '🔧': '[Tools]',
            '💼': '[Work]',
            '🎓': '[Education]',
            '📞': '[Phone]',
            '📧': '[Email]',
            '🔗': '[Link]',
            '💡': '[Ideas]',
            '⭐': '[Star]',
            '★': '[Star]',
            '☆': '[Star]',
            '✓': '[Check]',
            '✗': '[X]',
            '❌': '[X]',
            '✅': '[Check]',
        }

        for emoji, fallback in emoji_fallbacks.items():
            normalized = normalized.replace(emoji, fallback)

    return normalized


def get_pua_character_count(text: str) -> int:
    """
    Count Private Use Area characters in text for diagnostics.

    Args:
        text: Text to analyze

    Returns:
        Number of PUA characters found
    """
    if not text:
        return 0

    pua_count = 0
    for char in text:
        code_point = ord(char)
        if 0xE000 <= code_point <= 0xF8FF:
            pua_count += 1

    return pua_count


def apply_safe_text_to_widget(widget, text: str) -> bool:
    """
    Apply safely normalized text to a widget.

    Args:
        widget: QWidget to update
        text: Text to apply

    Returns:
        True if text was successfully applied
    """
    if not text:
        return False

    try:
        # Normalize text before applying
        safe_text = safe_emoji(normalize_text_for_ui(text), fallback_mode=False)

        # Apply to widget based on type
        if hasattr(widget, 'setText') and callable(getattr(widget, 'setText')):
            widget.setText(safe_text)
            return True
        elif hasattr(widget, 'setTitle') and callable(getattr(widget, 'setTitle')):
            widget.setTitle(safe_text)
            return True
        elif hasattr(widget, 'setPlainText') and callable(getattr(widget, 'setPlainText')):
            widget.setPlainText(safe_text)
            return True

    except Exception:
        # Fallback: try with aggressive emoji replacement
        try:
            fallback_text = safe_emoji(normalize_text_for_ui(text), fallback_mode=True)
            if hasattr(widget, 'setText'):
                widget.setText(fallback_text)
                return True
        except Exception:
            pass

    return False


def extract_merge_key(text: str, top_k: int = 5) -> List[str]:
    """
    Extract top-K most significant tokens for merge comparison.
    
    Args:
        text: Text to extract merge key from
        top_k: Number of top tokens to keep
        
    Returns:
        List of normalized tokens (sorted by length desc, then alpha)
    """
    if not text:
        return []
    
    tokens = tokenize(text)
    
    # Filter out pure numbers and very short tokens
    tokens = [t for t in tokens if not t.isdigit() and len(t) >= 3]
    
    # Sort by length (longer first) then alphabetically for consistency
    tokens = sorted(set(tokens), key=lambda x: (-len(x), x))
    
    return tokens[:top_k]


def should_merge_by_similarity(text1: str, text2: str, threshold: float = 0.6) -> bool:
    """
    Determine if two texts should be merged based on Jaccard similarity.
    Jaccard sur tokenize(a) vs tokenize(b) ; len(A∩B)/len(A∪B) >= threshold.
    
    Args:
        text1: First text
        text2: Second text  
        threshold: Minimum Jaccard similarity to merge (default 0.6)
        
    Returns:
        True if texts should be merged based on similarity
    """
    if not text1 or not text2:
        return False
    
    tokens1 = set(tokenize(text1))
    tokens2 = set(tokenize(text2))
    
    if not tokens1 or not tokens2:
        return False
    
    # Calculate Jaccard: len(A∩B)/len(A∪B)
    intersection = len(tokens1.intersection(tokens2))
    union = len(tokens1.union(tokens2))
    
    if union == 0:
        return False
    
    jaccard = intersection / union
    return jaccard >= threshold


def clean_name_for_display(name: str) -> str:
    """
    Clean a name/title for display (capitalize properly).
    
    Args:
        name: Raw name to clean
        
    Returns:
        Properly capitalized name
    """
    if not name:
        return ""
    
    # Basic normalization but keep case info
    name = name.strip()
    
    # Handle common cases
    if name.islower():
        # If all lowercase, title case it
        return name.title()
    elif name.isupper():
        # If all uppercase, title case it  
        return name.title()
    else:
        # Mixed case, assume it's correct
        return name


def extract_numbers(text: str) -> List[str]:
    """
    Extract number sequences from text.
    Retourne toutes les séquences de chiffres.
    
    Args:
        text: Text to extract numbers from
        
    Returns:
        List of number strings found
    """
    if not text:
        return []
    
    return re.findall(r'\d+', text)


def contains_address_indicators(text: str) -> bool:
    """
    Check if text contains address-like patterns.
    Utilise des regex pour détecter adresses, téléphones, codes postaux.
    
    Args:
        text: Text to check
        
    Returns:
        True if text looks like an address
    """
    if not text:
        return False
    
    # French address pattern as specified - fixed tel pattern to avoid "ateliers" false positive
    fr_address_pattern = r'(t(e|é)l(é|e)phone|\bt(é|e)l[\s:]|rue|avenue|bd|boulevard|cedex|\b\d{5}\b|\b\d{2}\s?\d{2}\s?\d{2}\s?\d{2}\s?\d{2}\b)'
    
    # Additional simple patterns
    additional_patterns = [
        r'\bcp\s*\d+\b',  # Case Postale
        r'\b(zip|postal|phone|fax)\b',
        r'\b\d{2,5}\s+\w+\s+(street|road|way|drive)\b',
    ]
    
    # Check French pattern first
    if re.search(fr_address_pattern, text, re.IGNORECASE):
        return True
    
    # Check additional patterns
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in additional_patterns)


def extract_urls(text: str) -> List[str]:
    """
    Extract URLs from text.
    
    Args:
        text: Text containing potential URLs
        
    Returns:
        List of URLs found
    """
    if not text:
        return []
    
    url_pattern = r'https?://(?:[-\w.])+(?:[:\d]+)?(?:/(?:[\w/_.])*(?:\?(?:[\w&=%.])*)?(?:#(?:[\w.])*)?)?'
    return re.findall(url_pattern, text, re.IGNORECASE)


def norm(s: str) -> str:
    """
    API publique pour normalisation simple avec backward-compatibility.
    Normalise un texte pour la comparaison et l'extraction (NFKC + espaces).
    
    Args:
        s: Texte à normaliser (peut être None)
        
    Returns:
        Texte normalisé (Unicode NFKC, espaces consolidés, stripped)
    """
    if s is None:
        return ""
    
    # Normalisation Unicode NFKC (compatible + canonical)
    s = unicodedata.normalize("NFKC", s)
    
    # Strip et consolidation des espaces
    s = s.strip()
    s = re.sub(r"\s+", " ", s)
    
    return s


def is_all_caps_with_punctuation(s: str) -> bool:
    """
    Détecte si une chaîne est en majuscules avec ponctuation (headers potentiels).
    
    Args:
        s: Texte à analyser
        
    Returns:
        True si format header (MAJUSCULES + ponctuation)
    """
    if not s:
        return False
    
    s = s.strip()
    
    # Au moins 3 caractères
    if len(s) < 3:
        return False
    
    # Se termine par : ou autres ponctuations de header
    if not re.search(r'[:\-=_•]$', s):
        return False
    
    # Majoritairement en majuscules (au moins 70% des lettres)
    letters = [c for c in s if c.isalpha()]
    if not letters:
        return False
    
    uppercase_count = sum(1 for c in letters if c.isupper())
    uppercase_ratio = uppercase_count / len(letters)
    
    return uppercase_ratio >= 0.7


# Backward-compatibility shim pour le code existant qui importe _norm
_norm = norm


if __name__ == "__main__":
    # Simple tests
    test_text = "Développement d'applications avec Python – Formation intensive (3 semaines)"
    print(f"Original: {test_text}")
    print(f"Normalized: {normalize_text(test_text)}")
    print(f"For comparison: {normalize_for_comparison(test_text)}")
    print(f"Tokens: {tokenize(test_text)}")
    print(f"Merge key: {extract_merge_key(test_text)}")
    print(f"Contains address: {contains_address_indicators(test_text)}")
    
    # Test de la nouvelle API norm
    print(f"Norm API: {norm(test_text)}")
    print(f"_norm alias: {_norm(test_text)}")
    print(f"Header detection: {is_all_caps_with_punctuation('COMPÉTENCES:')}")
