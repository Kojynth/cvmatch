"""
Domain detection utility for identifying domain-like company names.
Prevents emails and URLs from being parsed as companies in experience extraction.
"""

import re
from typing import List, Set
from ..logging.safe_logger import get_safe_logger, DEFAULT_PII_CONFIG

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


class DomainDetector:
    """Detects domain-like strings that should not be treated as companies."""
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        self._init_tld_list()
        
    def _init_tld_list(self) -> None:
        """Initialize comprehensive TLD list."""
        # Common TLDs - prioritize most frequent ones for performance
        self.common_tlds = {
            'com', 'org', 'net', 'edu', 'gov', 'mil', 'int', 'biz', 'info', 'name',
            'fr', 'uk', 'de', 'es', 'it', 'nl', 'be', 'ca', 'us', 'au', 'jp', 'cn',
            'ru', 'br', 'mx', 'in', 'ch', 'se', 'no', 'dk', 'fi', 'pt', 'pl', 'ro',
            'bg', 'cz', 'sk', 'hu', 'gr', 'ar', 'cl', 'co', 'pe', 'uy', 've', 'ec',
            'nz', 'za', 'ng', 'ke', 'eg', 'ma', 'tn', 'dz', 'ly', 'sd', 'et', 'gh',
            'th', 'vn', 'my', 'sg', 'ph', 'id', 'kr', 'tw', 'hk', 'pk', 'bd', 'lk',
            'mm', 'kh', 'la', 'mn', 'kg', 'tj', 'tm', 'uz', 'kz', 'am', 'az', 'ge',
            'by', 'ua', 'md', 'lt', 'lv', 'ee', 'is', 'ie', 'mt', 'cy', 'lu', 'ad',
            'mc', 'sm', 'va', 'li', 'at', 'si', 'hr', 'ba', 'rs', 'me', 'mk', 'al',
            'tr', 'il', 'jo', 'lb', 'sy', 'iq', 'ir', 'af', 'kw', 'sa', 'ye', 'om',
            'ae', 'qa', 'bh', 'ps', 'io', 'ai', 'dev', 'app', 'tech', 'online',
            'website', 'store', 'shop', 'blog', 'news', 'media', 'tv', 'radio',
            'music', 'video', 'photo', 'art', 'design', 'studio', 'agency', 'group',
            'team', 'pro', 'expert', 'guru', 'ninja', 'geek', 'cloud', 'digital'
        }
        
        # Allow extension from config
        extra_tlds = self.config.get('extra_tlds', [])
        if extra_tlds:
            self.common_tlds.update(extra_tlds)
            logger.debug(f"DOMAIN_DETECT: added {len(extra_tlds)} extra TLDs")
    
    def is_domain_like(self, text: str) -> bool:
        """
        Check if text appears to be a domain name or contains domain elements.
        
        Args:
            text: Text to analyze
            
        Returns:
            True if text appears domain-like
        """
        if not text or not isinstance(text, str):
            return False
        
        text = text.strip().lower()
        
        # Quick checks first
        if '.' in text:
            return self._check_domain_with_dots(text)
        
        # Check for TLD-like endings without dots
        return self._check_tld_endings(text)
    
    def _check_domain_with_dots(self, text: str) -> bool:
        """Check text containing dots for domain patterns."""
        
        # Split by dots and check components
        parts = [p.strip() for p in text.split('.') if p.strip()]
        
        if len(parts) < 2:
            return False
        
        # Check if last part looks like a TLD
        last_part = parts[-1].lower()
        
        # Check against known TLDs
        if last_part in self.common_tlds:
            logger.debug(f"DOMAIN_DETECT: TLD_match | text='{text}' tld='{last_part}'")
            return True
        
        # Check for numeric TLDs (like .123, could be IP fragments)
        if last_part.isdigit():
            logger.debug(f"DOMAIN_DETECT: numeric_tld | text='{text}' tld='{last_part}'")
            return True
        
        # Check for typical domain structure (2+ chars in last part)
        if len(last_part) >= 2 and last_part.isalpha():
            # Heuristic: if first part looks like domain name (alphanumeric with possible hyphens)
            first_part = parts[0]
            if re.match(r'^[a-zA-Z0-9-]+$', first_part) and len(first_part) >= 2:
                logger.debug(f"DOMAIN_DETECT: domain_structure | text='{text}' first='{first_part}' last='{last_part}'")
                return True
        
        return False
    
    def _check_tld_endings(self, text: str) -> bool:
        """Check if text ends with a known TLD (without requiring dots)."""
        
        # Only check single words to avoid false positives
        if ' ' in text or len(text) < 2:
            return False
        
        # Check exact TLD match
        if text in self.common_tlds:
            logger.debug(f"DOMAIN_DETECT: exact_tld | text='{text}'")
            return True
        
        # Check for words ending in common TLDs
        for tld in self.common_tlds:
            if len(tld) >= 2 and text.endswith(tld) and len(text) > len(tld):
                # Additional check: make sure it's not just coincidence
                prefix = text[:-len(tld)]
                if len(prefix) >= 2 and re.match(r'^[a-zA-Z0-9-]+$', prefix):
                    logger.debug(f"DOMAIN_DETECT: tld_suffix | text='{text}' tld='{tld}' prefix='{prefix}'")
                    return True
        
        return False
    
    def extract_domain_parts(self, text: str) -> dict:
        """
        Extract domain components from text for analysis.
        
        Args:
            text: Text to analyze
            
        Returns:
            Dict with 'subdomain', 'domain', 'tld' keys
        """
        if not self.is_domain_like(text):
            return {}
        
        text = text.strip().lower()
        
        if '.' not in text:
            return {'domain': text, 'tld': None, 'subdomain': None}
        
        parts = [p.strip() for p in text.split('.') if p.strip()]
        
        if len(parts) == 2:
            return {
                'subdomain': None,
                'domain': parts[0],
                'tld': parts[1]
            }
        elif len(parts) > 2:
            return {
                'subdomain': '.'.join(parts[:-2]) if len(parts) > 2 else None,
                'domain': parts[-2],
                'tld': parts[-1]
            }
        
        return {}
    
    def is_email_domain(self, text: str) -> bool:
        """
        Specifically check if text looks like it came from an email address.
        More restrictive than general domain detection.
        """
        if not text:
            return False
        
        text = text.strip().lower()
        
        # Must contain at least one dot
        if '.' not in text:
            return False
        
        parts = text.split('.')
        if len(parts) < 2:
            return False
        
        # Last part should be a known TLD
        tld = parts[-1]
        if tld not in self.common_tlds:
            return False
        
        # Domain part should look reasonable (not too short, alphanumeric)
        domain = parts[-2] if len(parts) >= 2 else ''
        if len(domain) < 2 or not re.match(r'^[a-zA-Z0-9-]+$', domain):
            return False
        
        logger.debug(f"EMAIL_DOMAIN_DETECT: text='{text}' domain='{domain}' tld='{tld}'")
        return True


def is_domain_like(text: str) -> bool:
    """
    Convenience function for quick domain-like checking.
    
    Args:
        text: Text to check
        
    Returns:
        True if text appears domain-like
    """
    detector = DomainDetector()
    return detector.is_domain_like(text)


def is_email_domain(text: str) -> bool:
    """
    Convenience function for email domain checking.
    
    Args:
        text: Text to check
        
    Returns:
        True if text looks like an email domain
    """
    detector = DomainDetector()
    return detector.is_email_domain(text)