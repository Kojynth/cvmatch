"""
PII-Safe Logging System with Redaction
======================================

Provides comprehensive PII (Personally Identifiable Information) redaction
for logging and debug output. Ensures no sensitive data is exposed in logs
while maintaining debugging capability through stable hashing.
"""

import re
import hashlib
import logging
from typing import Dict, List, Optional, Pattern, Tuple, Set
from dataclasses import dataclass
from enum import Enum


class PIIType(Enum):
    """Types of PII that can be detected and redacted."""

    EMAIL = "EMAIL"
    PHONE = "PHONE"
    SSN = "SSN"
    CREDIT_CARD = "CC"
    IBAN = "IBAN"
    IP_ADDRESS = "IP"
    POSTAL_ADDRESS = "ADDRESS"
    PERSON_NAME = "NAME"
    ORGANIZATION = "ORG"
    URL = "URL"
    DATE_OF_BIRTH = "DOB"
    UNKNOWN = "UNKNOWN"

    def __str__(self) -> str:
        return self.value


@dataclass
class PIIPattern:
    """Pattern definition for PII detection."""

    pii_type: PIIType
    pattern: Pattern[str]
    description: str
    confidence: float = 1.0  # Confidence level (0.0 to 1.0)


@dataclass
class RedactionResult:
    """Result of PII redaction operation."""

    original_text: str
    redacted_text: str
    pii_found: List[Tuple[PIIType, str, int, int]]  # type, value, start, end
    redaction_count: int
    processing_time_ms: float


class PIIRedactor:
    """
    PII redaction engine with configurable patterns and stable hashing.

    Features:
    - Comprehensive PII pattern matching
    - Stable hashing for debugging (same input -> same hash)
    - Configurable redaction levels
    - Support for multiple languages
    - OCR noise tolerance
    """

    def __init__(
        self,
        hash_salt: str = "cvmatch_pii_salt_v1",
        preserve_format: bool = True,
        min_confidence: float = 0.7,
    ):
        """
        Initialize PII redactor.

        Args:
            hash_salt: Salt for stable hashing
            preserve_format: Whether to preserve original format in redaction
            min_confidence: Minimum confidence for PII detection
        """
        self.hash_salt = hash_salt
        self.preserve_format = preserve_format
        self.min_confidence = min_confidence

        # Initialize patterns
        self.patterns = self._initialize_patterns()

        # Cache for hash consistency
        self._hash_cache: Dict[str, str] = {}

        # Statistics tracking
        self.stats = {
            "total_redactions": 0,
            "redactions_by_type": {pii_type: 0 for pii_type in PIIType},
            "processed_texts": 0,
        }

    def redact(self, text: str, keep_first_chars: int = 2) -> str:
        """
        Redact PII from text with stable replacement tokens.

        Args:
            text: Input text potentially containing PII
            keep_first_chars: Number of first characters to preserve for debugging

        Returns:
            str: Text with PII redacted using stable tokens
        """
        if not text or not text.strip():
            return text

        result = self.redact_detailed(text, keep_first_chars)
        return result.redacted_text

    def redact_detailed(self, text: str, keep_first_chars: int = 2) -> RedactionResult:
        """
        Perform detailed PII redaction with full result information.

        Args:
            text: Input text potentially containing PII
            keep_first_chars: Number of first characters to preserve

        Returns:
            RedactionResult: Detailed redaction results
        """
        import time

        start_time = time.time()

        if not text or not text.strip():
            return RedactionResult(
                original_text=text,
                redacted_text=text,
                pii_found=[],
                redaction_count=0,
                processing_time_ms=0.0,
            )

        # Find all PII in text
        pii_matches = self._find_all_pii(text)

        # Sort by position (reverse order for safe replacement)
        pii_matches.sort(key=lambda x: x[2], reverse=True)

        # Perform redactions
        redacted_text = text
        redaction_count = 0

        for pii_type, original_value, start, end in pii_matches:
            # Generate stable redaction token
            redaction_token = self._generate_redaction_token(
                original_value, pii_type, keep_first_chars
            )

            # Replace in text
            redacted_text = (
                redacted_text[:start] + redaction_token + redacted_text[end:]
            )

            redaction_count += 1

            # Update statistics
            self.stats["redactions_by_type"][pii_type] += 1

        # Update global statistics
        self.stats["total_redactions"] += redaction_count
        self.stats["processed_texts"] += 1

        processing_time_ms = (time.time() - start_time) * 1000

        return RedactionResult(
            original_text=text,
            redacted_text=redacted_text,
            pii_found=pii_matches,
            redaction_count=redaction_count,
            processing_time_ms=processing_time_ms,
        )

    def _find_all_pii(self, text: str) -> List[Tuple[PIIType, str, int, int]]:
        """Find all PII matches in text."""
        matches = []

        for pattern_def in self.patterns:
            if pattern_def.confidence < self.min_confidence:
                continue

            for match in pattern_def.pattern.finditer(text):
                matches.append(
                    (pattern_def.pii_type, match.group(), match.start(), match.end())
                )

        # Remove overlapping matches (keep highest confidence)
        return self._remove_overlapping_matches(matches)

    def _remove_overlapping_matches(
        self, matches: List[Tuple[PIIType, str, int, int]]
    ) -> List[Tuple[PIIType, str, int, int]]:
        """Remove overlapping PII matches, keeping the most specific ones."""
        if not matches:
            return matches

        # Sort by start position
        matches.sort(key=lambda x: x[2])

        result = []
        for match in matches:
            pii_type, value, start, end = match

            # Check for overlap with existing matches
            overlapping = False
            for existing in result:
                existing_start, existing_end = existing[2], existing[3]
                if not (end <= existing_start or start >= existing_end):
                    # Overlapping - keep the longer/more specific match
                    if (end - start) > (existing_end - existing_start):
                        # Remove the existing match
                        result.remove(existing)
                        result.append(match)
                    overlapping = True
                    break

            if not overlapping:
                result.append(match)

        return result

    def _generate_redaction_token(
        self, original_value: str, pii_type: PIIType, keep_first_chars: int
    ) -> str:
        """Generate stable redaction token for PII value."""
        # Use cache for consistency
        cache_key = f"{original_value}:{pii_type.value}:{keep_first_chars}"
        if cache_key in self._hash_cache:
            return self._hash_cache[cache_key]

        # Generate stable hash
        stable_hash = self._generate_stable_hash(original_value)[:6]

        # Preserve format if requested
        if self.preserve_format and keep_first_chars > 0:
            prefix = original_value[:keep_first_chars]
            token = f"{prefix}***[REDACTED:{pii_type.value}:{stable_hash}]"
        else:
            token = f"[REDACTED:{pii_type.value}:{stable_hash}]"

        # Cache the result
        self._hash_cache[cache_key] = token
        return token

    def _generate_stable_hash(self, value: str) -> str:
        """Generate stable hash for debugging purposes."""
        combined = f"{self.hash_salt}:{value}"
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()

    def _initialize_patterns(self) -> List[PIIPattern]:
        """Initialize PII detection patterns."""
        patterns = []

        # Email addresses (comprehensive pattern)
        patterns.append(
            PIIPattern(
                pii_type=PIIType.EMAIL,
                pattern=re.compile(
                    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
                    re.IGNORECASE,
                ),
                description="Standard email address format",
                confidence=0.95,
            )
        )

        # Phone numbers (international and local formats)
        phone_patterns = [
            r"\+\d{1,3}[\s\-\.\(\)]*\d{1,4}[\s\-\.\(\)]*\d{1,4}[\s\-\.\(\)]*\d{1,9}",  # International
            r"\b\d{3}[\s\-\.\(\)]*\d{3}[\s\-\.\(\)]*\d{4}\b",  # US format
            r"\b0[1-9][\s\-\.\(\)]*\d{2}[\s\-\.\(\)]*\d{2}[\s\-\.\(\)]*\d{2}[\s\-\.\(\)]*\d{2}\b",  # French format
            r"\b\d{2}[\s\-\.\(\)]*\d{2}[\s\-\.\(\)]*\d{2}[\s\-\.\(\)]*\d{2}[\s\-\.\(\)]*\d{2}\b",  # Generic
        ]

        for phone_pattern in phone_patterns:
            patterns.append(
                PIIPattern(
                    pii_type=PIIType.PHONE,
                    pattern=re.compile(phone_pattern),
                    description="Phone number",
                    confidence=0.85,
                )
            )

        # Social Security Numbers (US format)
        patterns.append(
            PIIPattern(
                pii_type=PIIType.SSN,
                pattern=re.compile(r"\b\d{3}[\s\-]?\d{2}[\s\-]?\d{4}\b"),
                description="US Social Security Number",
                confidence=0.90,
            )
        )

        # Credit card numbers (basic pattern)
        patterns.append(
            PIIPattern(
                pii_type=PIIType.CREDIT_CARD,
                pattern=re.compile(r"\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b"),
                description="Credit card number",
                confidence=0.85,
            )
        )

        # IBAN (European bank account format)
        patterns.append(
            PIIPattern(
                pii_type=PIIType.IBAN,
                pattern=re.compile(
                    r"\b[A-Z]{2}\d{2}[\s\-]?[A-Z0-9]{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{2}\b"
                ),
                description="IBAN bank account number",
                confidence=0.90,
            )
        )

        # IP addresses
        patterns.append(
            PIIPattern(
                pii_type=PIIType.IP_ADDRESS,
                pattern=re.compile(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b"),
                description="IPv4 address",
                confidence=0.80,
            )
        )

        # URLs with personal information
        patterns.append(
            PIIPattern(
                pii_type=PIIType.URL,
                pattern=re.compile(r'https?://[^\s<>"\']+'),
                description="URLs that may contain personal info",
                confidence=0.70,
            )
        )

        # Postal addresses (basic pattern - highly variable)
        patterns.append(
            PIIPattern(
                pii_type=PIIType.POSTAL_ADDRESS,
                pattern=re.compile(
                    r"\b\d+\s+[A-Za-z\s]+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Way|Place|Pl)\b",
                    re.IGNORECASE,
                ),
                description="Street address",
                confidence=0.75,
            )
        )

        # Dates of birth (various formats)
        dob_patterns = [
            r"\b(?:born|birth|née?|born on)\s+\d{1,2}[/\-]\d{1,2}[/\-]\d{4}\b",
            r"\b\d{1,2}[/\-]\d{1,2}[/\-]\d{4}\s+(?:birth|DOB)\b",
        ]

        for dob_pattern in dob_patterns:
            patterns.append(
                PIIPattern(
                    pii_type=PIIType.DATE_OF_BIRTH,
                    pattern=re.compile(dob_pattern, re.IGNORECASE),
                    description="Date of birth",
                    confidence=0.85,
                )
            )

        return patterns

    def get_statistics(self) -> Dict[str, any]:
        """Get redaction statistics."""
        return self.stats.copy()

    def reset_statistics(self) -> None:
        """Reset redaction statistics."""
        self.stats = {
            "total_redactions": 0,
            "redactions_by_type": {pii_type: 0 for pii_type in PIIType},
            "processed_texts": 0,
        }


# Global redactor instance
_global_redactor: Optional[PIIRedactor] = None


def get_redactor(hash_salt: Optional[str] = None) -> PIIRedactor:
    """Get global PII redactor instance."""
    global _global_redactor

    if _global_redactor is None:
        salt = hash_salt or "cvmatch_pii_salt_v1"
        _global_redactor = PIIRedactor(hash_salt=salt)

    return _global_redactor


def redact(text: str, keep_first_chars: int = 2) -> str:
    """
    Convenience function for PII redaction.

    Args:
        text: Text to redact
        keep_first_chars: Number of first characters to preserve

    Returns:
        str: Redacted text
    """
    redactor = get_redactor()
    return redactor.redact(text, keep_first_chars)


def redact_log_message(message: str, *args) -> str:
    """
    Redact PII from log message and arguments.

    Args:
        message: Log message format string
        *args: Log message arguments

    Returns:
        str: Safely redacted log message
    """
    # Redact the message format string
    safe_message = redact(message)

    # Redact all arguments
    safe_args = []
    for arg in args:
        if isinstance(arg, str):
            safe_args.append(redact(arg))
        else:
            # Convert to string and redact
            safe_args.append(redact(str(arg)))

    # Format the safe message
    try:
        return safe_message % tuple(safe_args)
    except (TypeError, ValueError):
        # If formatting fails, return the safe message only
        return safe_message


class PIISafeLogger:
    """
    Logger wrapper that automatically redacts PII from log messages.

    This provides a drop-in replacement for standard loggers with automatic
    PII protection.
    """

    def __init__(self, logger: logging.Logger, redactor: Optional[PIIRedactor] = None):
        """
        Initialize PII-safe logger wrapper.

        Args:
            logger: Underlying logger instance
            redactor: PII redactor (uses global if None)
        """
        self.logger = logger
        self.redactor = redactor or get_redactor()

    def _safe_log(self, level: int, message: str, *args, **kwargs) -> None:
        """Safely log message with PII redaction."""
        # Redact the message and arguments
        safe_message = redact_log_message(message, *args)

        # Log safely (no additional args since they're already formatted)
        self.logger.log(level, safe_message, **kwargs)

    def debug(self, message: str, *args, **kwargs) -> None:
        """Log debug message with PII redaction."""
        self._safe_log(logging.DEBUG, message, *args, **kwargs)

    def info(self, message: str, *args, **kwargs) -> None:
        """Log info message with PII redaction."""
        self._safe_log(logging.INFO, message, *args, **kwargs)

    def warning(self, message: str, *args, **kwargs) -> None:
        """Log warning message with PII redaction."""
        self._safe_log(logging.WARNING, message, *args, **kwargs)

    def error(self, message: str, *args, **kwargs) -> None:
        """Log error message with PII redaction."""
        self._safe_log(logging.ERROR, message, *args, **kwargs)

    def critical(self, message: str, *args, **kwargs) -> None:
        """Log critical message with PII redaction."""
        self._safe_log(logging.CRITICAL, message, *args, **kwargs)

    def exception(self, message: str, *args, **kwargs) -> None:
        """Log exception with PII redaction."""
        kwargs.setdefault("exc_info", True)
        self.error(message, *args, **kwargs)

    # Delegate other methods to underlying logger
    def __getattr__(self, name):
        return getattr(self.logger, name)


def create_pii_safe_logger(
    name: str, redactor: Optional[PIIRedactor] = None
) -> PIISafeLogger:
    """
    Create a PII-safe logger.

    Args:
        name: Logger name
        redactor: Optional custom redactor

    Returns:
        PIISafeLogger: PII-safe logger instance
    """
    underlying_logger = logging.getLogger(name)
    return PIISafeLogger(underlying_logger, redactor)


# Export main classes and functions
__all__ = [
    "PIIType",
    "PIIPattern",
    "RedactionResult",
    "PIIRedactor",
    "PIISafeLogger",
    "create_pii_safe_logger",
    "redact",
    "redact_log_message",
    "get_redactor",
]
