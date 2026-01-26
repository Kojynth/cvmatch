"""
PII-safe logging sanitizer for CVMatch.

This module implements comprehensive PII redaction for logging systems,
ensuring no personal data leaks through logs while maintaining log usability.

Features:
- Optimized compiled regex patterns for common PII types
- Order-safe replacement passes to avoid overlapping matches  
- Configurable strictness levels (standard vs strict mode)
- Performance-oriented implementation with caching
- Defense-in-depth sanitization for both structured and free-text data
- Fail-closed error handling
"""

import re
import logging
import hashlib
import time
from typing import Dict, List, Tuple, Optional, Pattern, Any
from functools import lru_cache
from collections import defaultdict

# Import existing PII utilities - we'll enhance and optimize them
from .pii import (
    EMAIL, PHONE, ADDR, NAME, ORG, GEO, HANDLE, 
    redact_with_token, mask_email, mask_phone, mask_keep_shape,
    _is_technical_exclusion
)
from ..config import PIIConfig, DEFAULT_PII_CONFIG

# Performance metrics tracking
_sanitizer_metrics = defaultdict(int)
_sanitizer_timing = defaultdict(float)

class SanitizerError(Exception):
    """Exception raised when sanitization fails."""
    pass

# Optimized compiled patterns for logging-specific PII detection
# Order is critical: most specific patterns first to avoid conflicts

# Enhanced file path patterns (Windows + POSIX)
FILE_PATH_PATTERNS = [
    # Windows paths with usernames - more specific patterns first
    re.compile(r'C:\\Users\\([^\\]+)\\[^\\]*(?:\\[^\\]*)*', re.IGNORECASE),
    re.compile(r'\\Users\\([^\\]+)\\[^\\]*(?:\\[^\\]*)*', re.IGNORECASE),
    # POSIX paths with usernames  
    re.compile(r'/home/([^/]+)/[^/]*(?:/[^/]*)*', re.IGNORECASE),
    re.compile(r'/Users/([^/]+)/[^/]*(?:/[^/]*)*', re.IGNORECASE),
    # Generic paths that might contain usernames
    re.compile(r'[A-Za-z]:\\.*\\([A-Za-z][a-zA-Z0-9._-]+)\\.*', re.IGNORECASE),
]

# French postal codes (5 digits, not part of other numbers)
POSTAL_CODE = re.compile(r'\b\d{5}\b(?!\d)')

# Nationality patterns (French-specific)
NATIONALITY_PATTERNS = [
    re.compile(r'\bdouble nationalité\s+([^.]+?)(?:\s+et\s+([^.]+?))?(?=\s|$|[.,])', re.IGNORECASE | re.UNICODE),
    re.compile(r'\bnationalité\s+([^.]+?)(?=\s|$|[.,])', re.IGNORECASE | re.UNICODE),
    re.compile(r'\b(français|française|japonais|japonaise|américain|américaine|britannique|allemand|allemande|chinois|chinoise|italien|italienne)\s+(?:de naissance|d\'origine)?\b', re.IGNORECASE | re.UNICODE),
]

# UUID/ID patterns
UUID_PATTERN = re.compile(r'\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b')
GENERIC_ID_PATTERN = re.compile(r'\b[A-Z0-9]{8,}\b')

class PiiSanitizer:
    """
    High-performance PII sanitizer optimized for logging systems.
    
    Implements order-safe replacement, caching, and comprehensive PII detection
    while maintaining excellent performance for high-volume logging scenarios.
    """
    
    def __init__(self, config: PIIConfig = None, strict_mode: bool = False):
        """
        Initialize the sanitizer.
        
        Args:
            config: PII configuration (uses default if None)
            strict_mode: Enable strict mode for org/school name redaction
        """
        self.config = config or DEFAULT_PII_CONFIG
        self.strict_mode = strict_mode
        self._replacement_cache = {}  # Cache for expensive replacements
        self._detection_cache = {}    # Cache for PII detection results
        
        # Performance tracking
        self._call_count = 0
        self._total_time = 0.0
        
        # Ordered replacement patterns - critical order for non-overlapping replacements
        self._ordered_patterns = self._compile_ordered_patterns()
    
    def _compile_ordered_patterns(self) -> List[Tuple[Pattern, str, callable]]:
        """
        Compile patterns in order from most specific to least specific.
        This prevents overlapping matches and ensures consistent results.
        """
        patterns = [
            # 1. File paths (most specific - contains structured data)
            (re.compile(r'C:\\Users\\[^\\]+\\.*?(?=[\s\]]|$)', re.IGNORECASE), "PATH", self._mask_file_path),
            (re.compile(r'/home/[^/]+/.*?(?=[\s\]]|$)', re.IGNORECASE), "PATH", self._mask_file_path),
            (re.compile(r'/Users/[^/]+/.*?(?=[\s\]]|$)', re.IGNORECASE), "PATH", self._mask_file_path),
            
            # 2. Email addresses (structured format)
            (EMAIL, "EMAIL", mask_email),
            
            # 3. Phone numbers (structured format)  
            (PHONE, "PHONE", mask_phone),
            
            # 4. Social media handles (structured)
            (HANDLE, "HANDLE", mask_keep_shape),
            
            # 5. UUIDs and IDs (before names to avoid partial matches)
            (UUID_PATTERN, "ID", lambda x: "[ID]"),
            
            # 6. Street addresses (semi-structured)
            (ADDR, "ADDR", mask_keep_shape),
            
            # 7. Postal codes (numeric)
            (POSTAL_CODE, "POSTCODE", lambda x: "[PII-POSTCODE]"),
            
            # 8. Nationality mentions (context-dependent)
            *[(pattern, "NATIONALITY", self._mask_nationality) for pattern in NATIONALITY_PATTERNS],
            
            # 9. Organizations (in strict mode only)
            *([ORG, "ORG", mask_keep_shape] if self.strict_mode else []),
            
            # 10. Geographic locations (semi-structured)
            (GEO, "GEO", mask_keep_shape),
            
            # 11. Personal names (least specific - must be last)
            (NAME, "NAME", mask_keep_shape),
        ]
        
        return [(pattern, kind, masker) for pattern, kind, masker in patterns if pattern is not None]
    
    def _mask_file_path(self, path: str) -> str:
        """Mask file paths while preserving structure."""
        for pattern in FILE_PATH_PATTERNS:
            match = pattern.search(path)
            if match:
                # Extract username if found and replace
                if len(match.groups()) > 0:
                    username = match.group(1)
                    # Replace username in the full path
                    masked_path = path.replace(username, "[PII-USER]")
                    # Get the relative part after the user directory
                    user_dir_end = match.end()
                    if user_dir_end < len(path):
                        relative_part = path[user_dir_end:]
                        return f"[PII-PATH]{relative_part}"
                    else:
                        return "[PII-PATH]"
        return "[PII-PATH]"
    
    def _mask_nationality(self, text: str) -> str:
        """Mask nationality while preserving non-PII context."""
        # Keep the structure but mask specific nationalities
        text = re.sub(r'\b(français|française|japonais|japonaise|américain|américaine|britannique|allemand|allemande|chinois|chinoise|italien|italienne)\b', 
                     '[PII-NATIONALITY]', text, flags=re.IGNORECASE)
        return text
    
    @lru_cache(maxsize=1000)
    def _is_cached_exclusion(self, text: str, kind: str) -> bool:
        """Cached version of technical exclusion check."""
        return _is_technical_exclusion(text, kind)
    
    def sanitize_text(self, text: str) -> str:
        """
        Sanitize text by replacing all detected PII with safe tokens.
        
        Args:
            text: Input text to sanitize
            
        Returns:
            Sanitized text with PII replaced by tokens
            
        Raises:
            SanitizerError: If sanitization fails critically
        """
        if not text or not isinstance(text, str):
            return str(text) if text is not None else ""
        
        # Performance tracking
        start_time = time.time()
        self._call_count += 1
        
        try:
            # Check cache first
            cache_key = hash(text) if len(text) < 500 else None
            if cache_key and cache_key in self._replacement_cache:
                _sanitizer_metrics["cache_hits"] += 1
                return self._replacement_cache[cache_key]
            
            result = text
            
            # Apply patterns in order (critical for non-overlapping replacements)
            for pattern, kind, masker in self._ordered_patterns:
                result = self._apply_pattern_safe(pattern, result, kind, masker)
            
            # Additional safety pass for any remaining obvious PII
            result = self._final_safety_pass(result)
            
            # Cache result if reasonable size
            if cache_key and len(result) < 1000:
                self._replacement_cache[cache_key] = result
                _sanitizer_metrics["cache_stores"] += 1
            
            _sanitizer_metrics["successful_sanitizations"] += 1
            
        except Exception as e:
            # Fail-closed: return safe error message instead of original text
            _sanitizer_metrics["sanitization_errors"] += 1
            error_id = hashlib.md5(str(e).encode()).hexdigest()[:8]
            return f"[REDACTION-ERROR:{error_id}:{type(e).__name__}]"
        
        finally:
            elapsed = time.time() - start_time
            self._total_time += elapsed
            _sanitizer_timing["sanitize_text"] += elapsed
        
        return result
    
    def _apply_pattern_safe(self, pattern: Pattern, text: str, kind: str, masker: callable) -> str:
        """Apply a pattern safely with exclusion filtering."""
        def replace_match(match):
            matched_text = match.group(0)
            
            # Apply technical exclusions
            if self._is_cached_exclusion(matched_text, kind):
                return matched_text
            
            # Apply the masker
            try:
                return redact_with_token(matched_text, self.config.HASH_SALT, kind, masker)
            except Exception:
                # Fallback to generic masking
                return f"[PII-{kind}]"
        
        return pattern.sub(replace_match, text)
    
    def _final_safety_pass(self, text: str) -> str:
        """
        Final safety pass to catch any remaining obvious PII.
        This is a fail-safe for edge cases not covered by main patterns.
        """
        # Catch any remaining obvious email patterns
        email_safety = re.compile(r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b')
        text = email_safety.sub('[PII-EMAIL]', text)
        
        # Catch any remaining obvious phone patterns
        phone_safety = re.compile(r'\b(?:\+33|0)[1-9][\s.-]?\d{2}[\s.-]?\d{2}[\s.-]?\d{2}[\s.-]?\d{2}\b')
        text = phone_safety.sub('[PII-PHONE]', text)
        
        return text
    
    def sanitize_mapping(self, text: str) -> Tuple[str, Dict[str, int]]:
        """
        Sanitize text and return metrics about what was found.
        
        Args:
            text: Input text to sanitize
            
        Returns:
            Tuple of (sanitized_text, pii_type_counts)
        """
        if not text or not isinstance(text, str):
            return str(text) if text is not None else "", {}
        
        hits = defaultdict(int)
        result = text
        
        # Track what we find during sanitization
        for pattern, kind, masker in self._ordered_patterns:
            matches = list(pattern.finditer(result))
            for match in matches:
                if not self._is_cached_exclusion(match.group(0), kind):
                    hits[kind.lower()] += 1
            
            result = self._apply_pattern_safe(pattern, result, kind, masker)
        
        result = self._final_safety_pass(result)
        
        _sanitizer_metrics["sanitize_mapping_calls"] += 1
        
        return result, dict(hits)
    
    def has_pii(self, text: str) -> bool:
        """
        Quick check if text contains PII without sanitizing.
        Optimized for performance in logging filters.
        """
        if not text or not isinstance(text, str) or len(text.strip()) < 3:
            return False
        
        # Use fast cache check first
        cache_key = hash(text) if len(text) < 200 else None
        if cache_key and cache_key in self._detection_cache:
            _sanitizer_metrics["detection_cache_hits"] += 1
            return self._detection_cache[cache_key]
        
        # Quick pattern checks (only most obvious patterns for performance)
        has_obvious_pii = (
            EMAIL.search(text) is not None or
            PHONE.search(text) is not None or
            any(fp.search(text) for fp in FILE_PATH_PATTERNS[:2])  # Only check main path patterns
        )
        
        # Cache result
        if cache_key:
            self._detection_cache[cache_key] = has_obvious_pii
            _sanitizer_metrics["detection_cache_stores"] += 1
        
        return has_obvious_pii
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics for monitoring."""
        return {
            "call_count": self._call_count,
            "total_time_seconds": self._total_time,
            "avg_time_ms": (self._total_time / max(self._call_count, 1)) * 1000,
            "cache_hit_rate": _sanitizer_metrics["cache_hits"] / max(_sanitizer_metrics["cache_stores"], 1),
            "metrics": dict(_sanitizer_metrics),
            "timing": dict(_sanitizer_timing)
        }
    
    def clear_caches(self):
        """Clear internal caches (useful for testing or memory management)."""
        self._replacement_cache.clear()
        self._detection_cache.clear()
        _sanitizer_metrics.clear()
        _sanitizer_timing.clear()

# Global sanitizer instances (configured based on settings)
_default_sanitizer = None
_strict_sanitizer = None

def get_sanitizer(strict: bool = False) -> PiiSanitizer:
    """Get a configured sanitizer instance."""
    global _default_sanitizer, _strict_sanitizer
    
    if strict:
        if _strict_sanitizer is None:
            _strict_sanitizer = PiiSanitizer(DEFAULT_PII_CONFIG, strict_mode=True)
        return _strict_sanitizer
    else:
        if _default_sanitizer is None:
            _default_sanitizer = PiiSanitizer(DEFAULT_PII_CONFIG, strict_mode=False)
        return _default_sanitizer

def sanitize_text(text: str) -> str:
    """
    Convenience function for sanitizing text with default settings.
    
    Args:
        text: Text to sanitize
        
    Returns:
        Sanitized text
    """
    return get_sanitizer().sanitize_text(text)

def sanitize_mapping(text: str) -> Tuple[str, Dict[str, int]]:
    """
    Convenience function for sanitizing text and getting PII metrics.
    
    Args:
        text: Text to sanitize
        
    Returns:
        Tuple of (sanitized_text, pii_counts)
    """
    return get_sanitizer().sanitize_mapping(text)

def has_pii(text: str) -> bool:
    """
    Convenience function for checking if text has PII.
    
    Args:
        text: Text to check
        
    Returns:
        True if PII detected
    """
    return get_sanitizer().has_pii(text)

# Test strings for validation (as specified in requirements)
TEST_STRINGS = [
    "Loaded rules from C:\\Users\\username\\Documents\\cvmatch\\app\\rules\\soft_skills.json",
    "Test User", 
    "123 Example St 00000",
    "EPSAA - École Professionnelle Supérieure d'Arts Graphiques",
    "ANGLAIS bilingue / JAPONAIS bilingue",
    "double nationalité française et japonaise", 
    "user@example.com",
    "+33 6 12 34 56 78",
    "/home/user/documents/sensitive.pdf",
    "UUID: 123e4567-e89b-12d3-a456-426614174000"
]

def run_sanitizer_tests():
    """Run basic sanitizer tests with the predefined test strings."""
    sanitizer = get_sanitizer()
    strict_sanitizer = get_sanitizer(strict=True)
    
    print("=== PII Sanitizer Test Results ===")
    
    for i, test_string in enumerate(TEST_STRINGS, 1):
        normal_result = sanitizer.sanitize_text(test_string)
        strict_result = strict_sanitizer.sanitize_text(test_string)
        
        print(f"\nTest {i}:")
        print(f"Original: {test_string}")
        print(f"Normal:   {normal_result}")
        print(f"Strict:   {strict_result}")
    
    # Performance test
    import time
    start = time.time()
    for _ in range(1000):
        sanitizer.sanitize_text("Test with Test User and user@example.com")
    elapsed = time.time() - start
    print(f"\nPerformance: 1000 sanitizations in {elapsed:.3f}s ({elapsed*1000:.1f}ms avg)")

if __name__ == "__main__":
    run_sanitizer_tests()
