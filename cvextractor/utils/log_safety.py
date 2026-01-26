"""
PII-Safe Logging Utilities for CV Extraction
============================================

Comprehensive PII masking for extraction pipeline logs and debug artifacts.
Ensures no personal information leaks in logs while maintaining debug utility.
"""

import re
import hashlib
from typing import Dict, Any, List, Union
import json


# Regex patterns for PII detection
EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", re.IGNORECASE
)
PHONE_PATTERN = re.compile(
    r"(?:\+33|0)[1-9](?:[.-]?\d{2}){4}|(?:\+1-?)?(?:\(\d{3}\)|\d{3})[.-]?\d{3}[.-]?\d{4}",
    re.IGNORECASE,
)
URL_PATTERN = re.compile(
    r"https?://(?:[-\w.])+(?:[:\d]+)?(?:/(?:[\w/_.])*(?:\?(?:[\w&=%.])*)?(?:#(?:[\w.])*)?)?",
    re.IGNORECASE,
)

# Common personal name patterns (French/English)
PERSON_NAME_PATTERN = re.compile(r"\b[A-Z][a-z]+ [A-Z][a-z]+\b")

# Address patterns (basic)
ADDRESS_PATTERN = re.compile(
    r"\d+\s+[A-Za-z\s]+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Rue|Avenue)\b",
    re.IGNORECASE,
)

# Social security and ID patterns
SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b|\b\d{9}\b")
FRENCH_SSN_PATTERN = re.compile(r"\b[12]\d{2}(0[1-9]|1[0-2])\d{2}\d{3}\d{3}\d{2}\b")


class PIIMasker:
    """Comprehensive PII masking utility with configurable sensitivity levels."""

    def __init__(self, mask_char: str = "█", preserve_structure: bool = True):
        self.mask_char = mask_char
        self.preserve_structure = preserve_structure
        self.hash_salt = "cvextractor_pii_salt_2024"

    def mask_email(self, text: str) -> str:
        """Mask email addresses while preserving domain structure for debugging."""

        def replace_email(match):
            email = match.group(0)
            if self.preserve_structure:
                local, domain = email.split("@", 1)
                masked_local = (
                    self.mask_char * min(len(local), 3) + local[-1:]
                    if len(local) > 1
                    else self.mask_char
                )
                return f"{masked_local}@{domain}"
            else:
                return f"EMAIL_{self._hash_token(email)[:8]}"

        return EMAIL_PATTERN.sub(replace_email, text)

    def mask_phone(self, text: str) -> str:
        """Mask phone numbers while preserving country/area codes."""

        def replace_phone(match):
            phone = match.group(0)
            if self.preserve_structure:
                # Keep first 2-3 digits and last digit, mask middle
                if len(phone) >= 6:
                    prefix = phone[:3]
                    suffix = phone[-1:]
                    middle_len = len(phone) - 4
                    return f"{prefix}{self.mask_char * middle_len}{suffix}"
                else:
                    return self.mask_char * len(phone)
            else:
                return f"PHONE_{self._hash_token(phone)[:8]}"

        return PHONE_PATTERN.sub(replace_phone, text)

    def mask_url(self, text: str) -> str:
        """Mask URLs while preserving domain structure."""

        def replace_url(match):
            url = match.group(0)
            if self.preserve_structure:
                # Keep protocol and domain, mask path
                parts = url.split("/", 3)
                if len(parts) >= 3:
                    protocol_domain = "/".join(parts[:3])
                    path = parts[3] if len(parts) > 3 else ""
                    masked_path = self.mask_char * min(len(path), 10) if path else ""
                    return (
                        f"{protocol_domain}/{masked_path}"
                        if masked_path
                        else protocol_domain
                    )
                return url[:20] + self.mask_char * max(0, len(url) - 20)
            else:
                return f"URL_{self._hash_token(url)[:8]}"

        return URL_PATTERN.sub(replace_url, text)

    def mask_person_names(self, text: str) -> str:
        """Mask person names with hashed placeholders."""

        def replace_name(match):
            name = match.group(0)
            return f"PERSON_{self._hash_token(name)[:8]}"

        return PERSON_NAME_PATTERN.sub(replace_name, text)

    def mask_addresses(self, text: str) -> str:
        """Mask physical addresses."""

        def replace_address(match):
            address = match.group(0)
            return f"ADDRESS_{self._hash_token(address)[:8]}"

        return ADDRESS_PATTERN.sub(replace_address, text)

    def mask_ssn(self, text: str) -> str:
        """Mask social security numbers and national IDs."""
        # US SSN
        text = SSN_PATTERN.sub(
            lambda m: f"SSN_{self._hash_token(m.group(0))[:8]}", text
        )
        # French Social Security
        text = FRENCH_SSN_PATTERN.sub(
            lambda m: f"INSEE_{self._hash_token(m.group(0))[:8]}", text
        )
        return text

    def _hash_token(self, token: str) -> str:
        """Create deterministic hash for consistent masking across runs."""
        return hashlib.sha256((token + self.hash_salt).encode()).hexdigest()


# Global masker instance
_global_masker = PIIMasker()


def mask_email(text: str) -> str:
    """Mask email addresses in text."""
    return _global_masker.mask_email(text)


def mask_phone(text: str) -> str:
    """Mask phone numbers in text."""
    return _global_masker.mask_phone(text)


def mask_url(text: str) -> str:
    """Mask URLs in text."""
    return _global_masker.mask_url(text)


def mask_person_names(text: str) -> str:
    """Mask person names in text."""
    return _global_masker.mask_person_names(text)


def mask_addresses(text: str) -> str:
    """Mask addresses in text."""
    return _global_masker.mask_addresses(text)


def mask_ssn(text: str) -> str:
    """Mask social security numbers in text."""
    return _global_masker.mask_ssn(text)


def mask_all_pii(text: str) -> str:
    """Apply all PII masking functions to text."""
    if not isinstance(text, str):
        return text

    masked = text
    masked = mask_email(masked)
    masked = mask_phone(masked)
    masked = mask_url(masked)
    masked = mask_person_names(masked)
    masked = mask_addresses(masked)
    masked = mask_ssn(masked)

    return masked


def mask_dict_pii(data: Dict[str, Any], recursive: bool = True) -> Dict[str, Any]:
    """Recursively mask PII in dictionary values."""
    if not isinstance(data, dict):
        return data

    masked_data = {}

    for key, value in data.items():
        if isinstance(value, str):
            masked_data[key] = mask_all_pii(value)
        elif isinstance(value, dict) and recursive:
            masked_data[key] = mask_dict_pii(value, recursive=True)
        elif isinstance(value, list) and recursive:
            masked_data[key] = [
                (
                    mask_dict_pii(item, recursive=True)
                    if isinstance(item, dict)
                    else mask_all_pii(item) if isinstance(item, str) else item
                )
                for item in value
            ]
        else:
            masked_data[key] = value

    return masked_data


def mask_all(payload: Union[str, Dict, List, Any]) -> Union[str, Dict, List, Any]:
    """Universal PII masking for any payload type."""
    if isinstance(payload, str):
        return mask_all_pii(payload)
    elif isinstance(payload, dict):
        return mask_dict_pii(payload, recursive=True)
    elif isinstance(payload, list):
        return [mask_all(item) for item in payload]
    else:
        # For other types, try string conversion then mask
        try:
            if hasattr(payload, "__dict__"):
                # Handle dataclass or object
                return mask_dict_pii(vars(payload), recursive=True)
            else:
                return payload
        except Exception:
            return payload


def create_safe_logger_wrapper(logger):
    """Wrap a logger to automatically mask PII in all log messages."""

    class SafeLoggerWrapper:
        def __init__(self, wrapped_logger):
            self._logger = wrapped_logger

        def debug(self, msg, *args, **kwargs):
            safe_msg = mask_all_pii(str(msg))
            safe_args = [mask_all(arg) for arg in args] if args else args
            return self._logger.debug(safe_msg, *safe_args, **kwargs)

        def info(self, msg, *args, **kwargs):
            safe_msg = mask_all_pii(str(msg))
            safe_args = [mask_all(arg) for arg in args] if args else args
            return self._logger.info(safe_msg, *safe_args, **kwargs)

        def warning(self, msg, *args, **kwargs):
            safe_msg = mask_all_pii(str(msg))
            safe_args = [mask_all(arg) for arg in args] if args else args
            return self._logger.warning(safe_msg, *safe_args, **kwargs)

        def error(self, msg, *args, **kwargs):
            safe_msg = mask_all_pii(str(msg))
            safe_args = [mask_all(arg) for arg in args] if args else args
            return self._logger.error(safe_msg, *safe_args, **kwargs)

        def critical(self, msg, *args, **kwargs):
            safe_msg = mask_all_pii(str(msg))
            safe_args = [mask_all(arg) for arg in args] if args else args
            return self._logger.critical(safe_msg, *safe_args, **kwargs)

        def __getattr__(self, name):
            # Delegate other attributes to wrapped logger
            return getattr(self._logger, name)

    return SafeLoggerWrapper(logger)


def validate_no_pii_leakage(text: str, raise_on_found: bool = False) -> List[str]:
    """
    Validate that text contains no PII patterns.

    Returns:
        List of PII types found (empty if clean)
    """
    found_pii = []

    if EMAIL_PATTERN.search(text):
        found_pii.append("email")
    if PHONE_PATTERN.search(text):
        found_pii.append("phone")
    if URL_PATTERN.search(text):
        found_pii.append("url")
    if PERSON_NAME_PATTERN.search(text):
        found_pii.append("person_name")
    if ADDRESS_PATTERN.search(text):
        found_pii.append("address")
    if SSN_PATTERN.search(text) or FRENCH_SSN_PATTERN.search(text):
        found_pii.append("ssn")

    if found_pii and raise_on_found:
        raise ValueError(f"PII found in text: {found_pii}")

    return found_pii


# Export main functions
__all__ = [
    "mask_email",
    "mask_phone",
    "mask_url",
    "mask_person_names",
    "mask_addresses",
    "mask_ssn",
    "mask_all_pii",
    "mask_dict_pii",
    "mask_all",
    "create_safe_logger_wrapper",
    "validate_no_pii_leakage",
    "PIIMasker",
]
