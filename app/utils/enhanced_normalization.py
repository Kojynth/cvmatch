"""
Enhanced Text Normalization - Improved pre-processing for CV extraction.

Provides robust text normalization with apostrophe/accent handling,
Unicode normalization, and special character cleanup to improve
extraction accuracy and reduce parsing errors.
"""

import re
import unicodedata
from typing import Dict, List, Optional, Tuple
from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG
from .feature_flags import get_extraction_fixes_flags

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


class EnhancedNormalizer:
    """Enhanced text normalizer with configurable preprocessing options."""
    
    def __init__(self):
        self.logger = get_safe_logger(f"{__name__}.EnhancedNormalizer", cfg=DEFAULT_PII_CONFIG)
        self.flags = get_extraction_fixes_flags()
        
        # Apostrophe normalization mapping
        self.apostrophe_map = {
            ''': "'",  # Right single quotation mark
            ''': "'",  # Left single quotation mark  
            '`': "'",  # Grave accent
            '´': "'",  # Acute accent
            '′': "'",  # Prime symbol
            '‛': "'",  # Single high-reversed-9 quotation mark
        }
        
        # Common accent mappings for better matching
        self.accent_map = {
            'à': 'a', 'á': 'a', 'â': 'a', 'ä': 'a', 'ã': 'a', 'å': 'a', 'æ': 'ae',
            'è': 'e', 'é': 'e', 'ê': 'e', 'ë': 'e',
            'ì': 'i', 'í': 'i', 'î': 'i', 'ï': 'i',
            'ò': 'o', 'ó': 'o', 'ô': 'o', 'ö': 'o', 'õ': 'o', 'ø': 'o', 'œ': 'oe',
            'ù': 'u', 'ú': 'u', 'û': 'u', 'ü': 'u',
            'ÿ': 'y', 'ý': 'y',
            'ç': 'c',
            'ñ': 'n',
            'ß': 'ss'
        }
        
        # Organization name normalization patterns
        self.org_normalization_patterns = [
            # Remove legal suffixes for matching
            (r'\b(SA|SAS|SASU|SARL|EURL|Inc|Corp|Ltd|LLC|GmbH|AG)\b', ''),
            # Normalize spacing around &
            (r'\s*&\s*', ' & '),
            # Normalize common abbreviations
            (r'\bSt\b', 'Saint'),
            (r'\bCie\b', 'Compagnie'),
            (r'\bEts\b', 'Etablissements'),
        ]
        
        # Title cleanup patterns
        self.title_cleanup_patterns = [
            # Remove residual date patterns from titles
            (r'\s*[-–—]\s*\d{4}\s*$', ''),
            (r'\s*[-–—]\s*\d{1,2}/\d{4}\s*$', ''),
            (r'\s*\(\d{4}[-–—]\d{4}?\)\s*$', ''),
            # Remove location info that got mixed into titles
            (r'\s*,\s*[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s*$', ''),
            # Clean up extra punctuation
            (r'\s*[,;]\s*$', ''),
            (r'^\s*[-–—]\s*', ''),
        ]
        
        # Special character normalization
        self.special_char_map = {
            # Dashes and hyphens
            '–': '-',  # En dash
            '—': '-',  # Em dash
            '−': '-',  # Minus sign
            '‒': '-',  # Figure dash
            '‐': '-',  # Hyphen
            # Quotes
            '"': '"',  # Left double quotation mark
            '"': '"',  # Right double quotation mark
            '„': '"',  # Double low-9 quotation mark
            '‚': "'",  # Single low-9 quotation mark
            # Spaces
            '\xa0': ' ',  # Non-breaking space
            '\u2009': ' ',  # Thin space
            '\u200b': '',  # Zero width space
            # Ellipsis
            '…': '...',
        }
    
    def normalize_apostrophes(self, text: str) -> str:
        """Normalize various apostrophe characters to standard single quote."""
        if not text or not self.flags.apostrophe_accent_preprocessing:
            return text
        
        normalized = text
        for old_char, new_char in self.apostrophe_map.items():
            normalized = normalized.replace(old_char, new_char)
        
        return normalized
    
    def normalize_accents(self, text: str, remove_accents: bool = False) -> str:
        """
        Normalize accented characters.
        
        Args:
            text: Input text
            remove_accents: If True, remove accents completely. If False, normalize Unicode.
        """
        if not text:
            return text
        
        if remove_accents:
            # Remove accents using our mapping
            normalized = text.lower()
            for accented, plain in self.accent_map.items():
                normalized = normalized.replace(accented, plain)
            return normalized
        else:
            # Unicode normalization (NFD = decomposed form)
            return unicodedata.normalize('NFD', text)
    
    def normalize_special_characters(self, text: str) -> str:
        """Normalize special characters to standard equivalents."""
        if not text or not self.flags.enhanced_normalization:
            return text
        
        normalized = text
        for special_char, standard_char in self.special_char_map.items():
            normalized = normalized.replace(special_char, standard_char)
        
        return normalized
    
    def clean_whitespace(self, text: str) -> str:
        """Clean and normalize whitespace."""
        if not text:
            return text
        
        # Replace multiple whitespace with single space
        cleaned = re.sub(r'\s+', ' ', text)
        
        # Remove leading/trailing whitespace
        cleaned = cleaned.strip()
        
        return cleaned
    
    def normalize_organization_name(self, org_name: str) -> str:
        """Normalize organization names for better matching."""
        if not org_name:
            return org_name
        
        normalized = org_name
        
        # Apply organization-specific patterns
        for pattern, replacement in self.org_normalization_patterns:
            normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
        
        # Basic normalization
        normalized = self.normalize_apostrophes(normalized)
        normalized = self.normalize_special_characters(normalized)
        normalized = self.clean_whitespace(normalized)
        
        return normalized
    
    def sanitize_title(self, title: str) -> str:
        """Sanitize job titles by removing residual dates and location info."""
        if not title or not self.flags.sanity_title_cleanup:
            return title
        
        sanitized = title
        
        # Apply title cleanup patterns
        for pattern, replacement in self.title_cleanup_patterns:
            sanitized = re.sub(pattern, replacement, sanitized)
        
        # Truncate if too long
        max_length = self.flags.max_title_length
        if max_length > 0 and len(sanitized) > max_length:
            sanitized = sanitized[:max_length].rstrip()
            self.logger.debug(f"TITLE_SANITIZE: truncated title from {len(title)} to {len(sanitized)} chars")
        
        # Clean whitespace
        sanitized = self.clean_whitespace(sanitized)
        
        return sanitized
    
    def normalize_for_matching(self, text: str, aggressive: bool = False) -> str:
        """
        Normalize text for matching purposes.
        
        Args:
            text: Input text
            aggressive: If True, apply aggressive normalization (remove accents, etc.)
        """
        if not text:
            return text
        
        normalized = text
        
        # Basic normalization
        normalized = self.normalize_apostrophes(normalized)
        normalized = self.normalize_special_characters(normalized)
        
        if aggressive:
            # Remove accents for better matching
            normalized = self.normalize_accents(normalized, remove_accents=True)
            
            # Convert to lowercase
            normalized = normalized.lower()
            
            # Remove extra punctuation
            normalized = re.sub(r'[^\w\s\-]', ' ', normalized)
        
        # Clean whitespace
        normalized = self.clean_whitespace(normalized)
        
        return normalized
    
    def preprocess_cv_text(self, text: str) -> str:
        """
        Complete preprocessing of CV text before extraction.
        
        This is the main entry point for text preprocessing.
        """
        if not text:
            return text
        
        processed = text
        
        # Apply preprocessing steps in order
        processed = self.normalize_apostrophes(processed)
        processed = self.normalize_special_characters(processed)
        processed = self.clean_whitespace(processed)
        
        self.logger.debug(f"PREPROCESS: normalized {len(text)} -> {len(processed)} chars")
        
        return processed
    
    def normalize_phone_number(self, phone: str) -> str:
        """Normalize phone number format."""
        if not phone:
            return phone
        
        # Remove common formatting
        normalized = re.sub(r'[\s\-\.\(\)]+', '', phone)
        
        # Add international prefix if missing
        if normalized.startswith('0') and len(normalized) == 10:
            # French phone number
            normalized = '+33' + normalized[1:]
        elif normalized.startswith('06') or normalized.startswith('07'):
            # French mobile
            normalized = '+33' + normalized[1:]
        
        return normalized
    
    def normalize_email(self, email: str) -> str:
        """Normalize email address."""
        if not email:
            return email
        
        # Basic normalization
        normalized = email.lower().strip()
        
        # Remove extra dots before @
        parts = normalized.split('@')
        if len(parts) == 2:
            local_part = parts[0].replace('..', '.')
            normalized = f"{local_part}@{parts[1]}"
        
        return normalized
    
    def extract_clean_text_blocks(self, text: str) -> List[str]:
        """
        Extract clean text blocks from preprocessed text.
        
        Returns list of clean text blocks suitable for parsing.
        """
        if not text:
            return []
        
        # Preprocess the entire text
        preprocessed = self.preprocess_cv_text(text)
        
        # Split into meaningful blocks (paragraphs)
        blocks = []
        for line in preprocessed.split('\n'):
            line = line.strip()
            if line and len(line) > 10:  # Skip very short lines
                blocks.append(line)
        
        # Merge related blocks if they seem connected
        merged_blocks = []
        current_block = ""
        
        for block in blocks:
            # If block starts with lowercase or continues previous sentence
            if (current_block and 
                (block[0].islower() or 
                 current_block.endswith(',') or 
                 current_block.endswith(';'))):
                current_block += " " + block
            else:
                if current_block:
                    merged_blocks.append(current_block)
                current_block = block
        
        if current_block:
            merged_blocks.append(current_block)
        
        return merged_blocks


# Global normalizer instance
_normalizer = None


def get_enhanced_normalizer() -> EnhancedNormalizer:
    """Get the global enhanced normalizer instance."""
    global _normalizer
    if _normalizer is None:
        _normalizer = EnhancedNormalizer()
    return _normalizer


def normalize_text(text: str, aggressive: bool = False) -> str:
    """Convenience function for text normalization."""
    return get_enhanced_normalizer().normalize_for_matching(text, aggressive=aggressive)


def preprocess_cv_content(text: str) -> str:
    """Convenience function for CV content preprocessing."""
    return get_enhanced_normalizer().preprocess_cv_text(text)


def sanitize_extracted_title(title: str) -> str:
    """Convenience function for title sanitization."""
    return get_enhanced_normalizer().sanitize_title(title)


def normalize_organization_name(org_name: str) -> str:
    """Convenience function for organization name normalization."""
    return get_enhanced_normalizer().normalize_organization_name(org_name)


if __name__ == "__main__":
    # Test the enhanced normalizer
    normalizer = EnhancedNormalizer()
    
    test_cases = [
        # Apostrophe normalization
        ("École d'ingénieur", "Ecole d'ingenieur"),
        ("L'université de Paris", "L'universite de Paris"),
        
        # Title sanitization
        ("Développeur Web – 2023", "Développeur Web"),
        ("Chef de projet (2020-2022)", "Chef de projet"),
        
        # Organization normalization
        ("ACME Corp & Co", "ACME & Co"),
        ("Établissements Martin SA", "Etablissements Martin"),
        
        # Special character normalization
        ("Stage—6 mois", "Stage-6 mois"),
        ("Formation…Python", "Formation...Python"),
    ]
    
    print("🔧 Enhanced Normalization Test Results:")
    print("=" * 50)
    
    for original, expected in test_cases:
        if "titre" in original.lower() or "chef" in original.lower():
            result = normalizer.sanitize_title(original)
        elif "corp" in original.lower() or "etabl" in original.lower():
            result = normalizer.normalize_organization_name(original)
        else:
            result = normalizer.preprocess_cv_text(original)
        
        status = "✅" if result.lower() == expected.lower() else "❌"
        print(f"{status} '{original}' → '{result}'")
        if result.lower() != expected.lower():
            print(f"   Expected: '{expected}'")
    
    print(f"\n📝 Preprocessing test:")
    test_text = """École  d'ingénieur—Formation  en…développement
    
    Stage chez ACME Corp & Cie – 2023
    Développeur  Web (6 mois)"""
    
    preprocessed = normalizer.preprocess_cv_text(test_text)
    print(f"Original: {test_text!r}")
    print(f"Result: {preprocessed!r}")