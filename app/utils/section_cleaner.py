"""
Section Cleaner: Enhanced cleanup for interests, certifications, and languages extraction.

This module provides comprehensive cleanup and validation for secondary CV sections
to prevent false positives, empty sections, and low-quality extractions.
"""

import re
from typing import List, Dict, Any, Optional, Tuple
from ..config import DEFAULT_PII_CONFIG, CERT_CANON, CERT_TYPO
from ..logging.safe_logger import get_safe_logger

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


class SectionCleaner:
    """Enhanced cleanup for interests, certifications, and languages sections."""
    
    def __init__(self):
        self.logger = get_safe_logger(f"{__name__}.SectionCleaner", cfg=DEFAULT_PII_CONFIG)
        
        # Common false positive patterns
        self.false_positive_patterns = [
            r'^\s*$',  # Empty
            r'^\s*[\-•\*\.]+\s*$',  # Only formatting chars
            r'^\d+\s*$',  # Only numbers
            r'^[a-zA-Z]\s*$',  # Single letter
            r'^\s*[,;:\-]+\s*$',  # Only punctuation
        ]
        
        # Placeholder patterns
        self.placeholder_patterns = [
            'à définir', 'a definir', 'n/a', 'none', 'null', 'empty', 
            '...', 'xxx', 'tbd', 'todo', 'placeholder', 'exemple'
        ]
        
        # Compile regex patterns for performance
        self.false_positive_regex = [re.compile(pattern, re.IGNORECASE) 
                                   for pattern in self.false_positive_patterns]
    
    def clean_interests(self, interests: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Clean interests with enhanced validation and false positive removal.
        
        Args:
            interests: List of interest dictionaries
            
        Returns:
            Cleaned list of interests
        """
        if not interests:
            return []
        
        cleaned = []
        rejected_count = 0
        
        for interest in interests:
            if not interest or not isinstance(interest, dict):
                rejected_count += 1
                continue
            
            name = interest.get('name', '').strip()
            description = interest.get('description', '').strip()
            
            # Validation checks
            is_valid, rejection_reason = self._validate_interest(name, description)
            
            if is_valid:
                # Normalize the interest
                normalized_interest = self._normalize_interest(interest)
                if normalized_interest:
                    cleaned.append(normalized_interest)
                else:
                    rejected_count += 1
            else:
                rejected_count += 1
                self.logger.debug(f"INTEREST_REJECTED: {rejection_reason} | name='{name[:20]}...'")
        
        self.logger.info(f"INTERESTS_CLEANED: kept={len(cleaned)} rejected={rejected_count}")
        return cleaned
    
    def clean_certifications(self, certifications: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Clean certifications with canonical name normalization and validation.
        
        Args:
            certifications: List of certification dictionaries
            
        Returns:
            Cleaned list of certifications
        """
        if not certifications:
            return []
        
        cleaned = []
        rejected_count = 0
        
        for cert in certifications:
            if not cert or not isinstance(cert, dict):
                rejected_count += 1
                continue
                
            name = cert.get('name', '').strip()
            
            # Validation and normalization
            is_valid, normalized_name, confidence = self._validate_certification(name)
            
            if is_valid and normalized_name:
                # Create cleaned certification
                cleaned_cert = {
                    'name': normalized_name,
                    'date': cert.get('date', ''),
                    'authority': cert.get('authority', ''),
                    'confidence': confidence,
                    'original_name': name if name != normalized_name else None
                }
                
                # Remove None values
                cleaned_cert = {k: v for k, v in cleaned_cert.items() if v is not None}
                cleaned.append(cleaned_cert)
            else:
                rejected_count += 1
                self.logger.debug(f"CERT_REJECTED: invalid | name='{name[:30]}...'")
        
        # Remove duplicates
        deduplicated = self._deduplicate_certifications(cleaned)
        
        removed_dupes = len(cleaned) - len(deduplicated)
        if removed_dupes > 0:
            self.logger.info(f"CERT_DEDUPLICATION: removed={removed_dupes} duplicates")
        
        self.logger.info(f"CERTIFICATIONS_CLEANED: kept={len(deduplicated)} rejected={rejected_count}")
        return deduplicated
    
    def clean_languages(self, languages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Clean languages with nationality filtering and level validation.
        
        Args:
            languages: List of language dictionaries
            
        Returns:
            Cleaned list of languages
        """
        if not languages:
            return []
        
        cleaned = []
        rejected_count = 0
        
        for lang in languages:
            if not lang or not isinstance(lang, dict):
                rejected_count += 1
                continue
                
            language = lang.get('language', '').strip()
            level = lang.get('level', '').strip()
            
            # Validation
            is_valid, rejection_reason = self._validate_language(language, level, lang)
            
            if is_valid:
                # Normalize the language
                normalized_lang = self._normalize_language(lang)
                if normalized_lang:
                    cleaned.append(normalized_lang)
                else:
                    rejected_count += 1
            else:
                rejected_count += 1
                self.logger.debug(f"LANG_REJECTED: {rejection_reason} | lang='{language[:20]}...'")
        
        # Remove duplicates
        deduplicated = self._deduplicate_languages(cleaned)
        
        removed_dupes = len(cleaned) - len(deduplicated)
        if removed_dupes > 0:
            self.logger.info(f"LANG_DEDUPLICATION: removed={removed_dupes} duplicates")
        
        self.logger.info(f"LANGUAGES_CLEANED: kept={len(deduplicated)} rejected={rejected_count}")
        return deduplicated
    
    def _validate_interest(self, name: str, description: str) -> Tuple[bool, str]:
        """Validate interest name and description."""
        if not name:
            return False, "empty_name"
        
        if len(name) < 2:
            return False, "name_too_short"
        
        # Check false positive patterns
        for pattern in self.false_positive_regex:
            if pattern.match(name):
                return False, "false_positive_pattern"
        
        # Check placeholder patterns
        name_lower = name.lower()
        if any(placeholder in name_lower for placeholder in self.placeholder_patterns):
            return False, "placeholder_detected"
        
        # Check if it's just punctuation/formatting
        if re.match(r'^[\s\-•\*\.\,\;:]+$', name):
            return False, "only_formatting"
        
        # Must contain at least one alphanumeric character
        if not re.search(r'[a-zA-Z0-9]', name):
            return False, "no_alphanumeric"
        
        return True, ""
    
    def _validate_certification(self, name: str) -> Tuple[bool, Optional[str], float]:
        """Validate and normalize certification name."""
        if not name:
            return False, None, 0.0
        
        if len(name) < 2:
            return False, None, 0.0
        
        # Check false positive patterns
        for pattern in self.false_positive_regex:
            if pattern.match(name):
                return False, None, 0.0
        
        # Apply typo corrections
        corrected_name = name.lower()
        for typo, correct in CERT_TYPO.items():
            corrected_name = corrected_name.replace(typo, correct)
        
        # Check against canonical certifications
        for canon_cert in CERT_CANON:
            canon_lower = canon_cert.lower()
            if (canon_lower in corrected_name or 
                corrected_name in canon_lower or
                self._fuzzy_match(corrected_name, canon_lower)):
                return True, canon_cert, 0.9
        
        # If not canonical but looks like valid certification
        if self._looks_like_certification(name):
            return True, name.title(), 0.6
        
        return False, None, 0.0
    
    def _validate_language(self, language: str, level: str, lang_dict: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate language entry."""
        if not language:
            return False, "empty_language"
        
        if len(language) < 2:
            return False, "language_too_short"
        
        # Check if it's a nationality (common false positive)
        if self._is_nationality(language):
            return False, "nationality_detected"
        
        # Must be a recognized language
        if not self._is_recognized_language(language):
            return False, "unrecognized_language"
        
        return True, ""
    
    def _normalize_interest(self, interest: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Normalize interest entry."""
        name = interest.get('name', '').strip()
        description = interest.get('description', '').strip()
        
        # Clean up the name
        name = re.sub(r'\s+', ' ', name)  # Normalize whitespace
        name = name.strip('.,;:-')  # Remove trailing punctuation
        
        # Capitalize first letter of each word
        name = name.title()
        
        return {
            'name': name,
            'description': description if description else None
        }
    
    def _normalize_language(self, lang: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Normalize language entry."""
        language = lang.get('language', '').strip()
        level = lang.get('level', '').strip()
        
        # Normalize language name
        language = language.title()
        
        # Normalize level
        level_mapping = {
            'native': 'Native',
            'natif': 'Native', 
            'maternel': 'Native',
            'mothertongue': 'Native',
            'fluent': 'Fluent',
            'courant': 'Fluent',
            'intermediate': 'Intermediate',
            'intermediaire': 'Intermediate',
            'moyen': 'Intermediate',
            'basic': 'Basic',
            'basique': 'Basic',
            'débutant': 'Basic',
            'debutant': 'Basic'
        }
        
        normalized_level = level_mapping.get(level.lower(), level)
        
        return {
            'language': language,
            'level': normalized_level if normalized_level else None
        }
    
    def _deduplicate_certifications(self, certs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate certifications."""
        seen = set()
        deduplicated = []
        
        for cert in certs:
            # Create a key for deduplication
            key = cert.get('name', '').lower().strip()
            if key and key not in seen:
                seen.add(key)
                deduplicated.append(cert)
        
        return deduplicated
    
    def _deduplicate_languages(self, langs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate languages."""
        seen = set()
        deduplicated = []
        
        for lang in langs:
            # Create a key for deduplication
            key = lang.get('language', '').lower().strip()
            if key and key not in seen:
                seen.add(key)
                deduplicated.append(lang)
        
        return deduplicated
    
    def _fuzzy_match(self, text1: str, text2: str) -> bool:
        """Simple fuzzy matching for certification names."""
        # Basic similarity check
        if len(text1) < 3 or len(text2) < 3:
            return False
        
        # Check if one is contained in the other with some tolerance
        shorter, longer = (text1, text2) if len(text1) < len(text2) else (text2, text1)
        
        if len(shorter) / len(longer) > 0.8 and shorter in longer:
            return True
        
        return False
    
    def _looks_like_certification(self, name: str) -> bool:
        """Check if text looks like a valid certification."""
        cert_indicators = [
            'certification', 'certificate', 'certified', 'diploma', 'licence', 'license'
        ]
        
        name_lower = name.lower()
        return any(indicator in name_lower for indicator in cert_indicators)
    
    def _is_nationality(self, text: str) -> bool:
        """Check if text is a nationality rather than language."""
        # Common nationality suffixes
        nationality_suffixes = ['ais', 'ain', 'an', 'ien', 'ois', 'ese', 'ish']
        text_lower = text.lower()
        
        # Check suffixes
        if any(text_lower.endswith(suffix) for suffix in nationality_suffixes):
            return True
        
        # Known nationality patterns
        nationality_patterns = ['français', 'francais', 'american', 'german', 'italian']
        return any(pattern in text_lower for pattern in nationality_patterns)
    
    def _is_recognized_language(self, text: str) -> bool:
        """Check if text is a recognized language."""
        # Common languages (simplified list)
        languages = [
            'french', 'français', 'francais', 'english', 'anglais',
            'spanish', 'espagnol', 'german', 'allemand', 'italian', 'italien',
            'chinese', 'chinois', 'japanese', 'japonais', 'korean', 'coréen',
            'portuguese', 'portugais', 'dutch', 'néerlandais', 'russian', 'russe',
            'arabic', 'arabe'
        ]
        
        text_lower = text.lower()
        return any(lang in text_lower or text_lower in lang for lang in languages)


def get_section_cleaner() -> SectionCleaner:
    """Get a singleton instance of SectionCleaner."""
    if not hasattr(get_section_cleaner, '_instance'):
        get_section_cleaner._instance = SectionCleaner()
    return get_section_cleaner._instance