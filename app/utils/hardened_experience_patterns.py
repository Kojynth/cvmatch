"""
Hardened experience pattern matching system.
Replaces the vulnerable role@company fallback with strict domain-aware patterns.
"""

import re
from typing import List, Dict, Any, Optional, Tuple, Set
from ..logging.safe_logger import get_safe_logger, DEFAULT_PII_CONFIG
from .domain_detector import DomainDetector, is_domain_like
from .extraction_metrics import get_metrics_collector

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


class HardenedExperiencePatterns:
    """Hardened pattern matcher for experience extraction."""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.domain_detector = DomainDetector(self.config.get('domain_detector', {}))
        self.metrics = get_metrics_collector()
        
        # Configuration flags
        self.require_spaced_at = self.config.get('require_spaced_at_for_role_company', True)
        self.fallback_window_size = self.config.get('exp_fallback_window_size', 30)
        
        # Known role titles for validation
        self.valid_role_titles = {
            # English
            'intern', 'engineer', 'manager', 'consultant', 'developer', 'analyst',
            'director', 'lead', 'senior', 'junior', 'associate', 'specialist',
            'coordinator', 'supervisor', 'administrator', 'executive', 'officer',
            # French
            'stagiaire', 'ingénieur', 'gestionnaire', 'développeur', 'analyste',
            'directeur', 'responsable', 'senior', 'junior', 'associé', 'spécialiste',
            'coordinateur', 'superviseur', 'administrateur', 'cadre', 'chef'
        }
        
        # Initialize patterns
        self._init_patterns()
        
        logger.debug(f"HARDENED_PATTERNS: initialized | "
                    f"spaced_at={self.require_spaced_at} window={self.fallback_window_size}")
    
    def _init_patterns(self):
        """Initialize hardened regex patterns."""
        
        # Strict spaced @ pattern (require literal spaces around @)
        self.spaced_at_pattern = re.compile(r'(.+?)\s+@\s+(.+)', re.IGNORECASE)
        
        # Alternative safe separators (no @ symbol)
        self.safe_separator_patterns = [
            re.compile(r'(.+?)\s+(?:chez|at)\s+(.+)', re.IGNORECASE),
            re.compile(r'(.+?)\s*[-–—]\s*(.+)', re.IGNORECASE),
            re.compile(r'(.+?)\s*\|\s*(.+)', re.IGNORECASE),
        ]
        
        # Action verb patterns for supporting signals
        self.action_verb_patterns = [
            re.compile(r'\b(?:led|built|designed|developed|managed|created|implemented|delivered|achieved)\b', re.IGNORECASE),
            re.compile(r'\b(?:géré|développé|conçu|créé|mis en place|livré|réalisé|dirigé)\b', re.IGNORECASE),
        ]
        
        # Experience section headers
        self.exp_header_patterns = [
            re.compile(r'\b(?:experience|expérience|work|travail|employment|emploi)\b', re.IGNORECASE),
            re.compile(r'\b(?:professional|professionnel|career|carrière)\b', re.IGNORECASE),
        ]
    
    def extract_title_company_safe(self, line: str, line_idx: int, 
                                 text_lines: List[str], 
                                 section_bounds: Optional[Tuple[int, int]] = None) -> Optional[Dict[str, Any]]:
        """
        Safe extraction of title@company patterns with comprehensive validation.
        
        Args:
            line: Text line to analyze
            line_idx: Index of the line
            text_lines: All text lines for context analysis
            section_bounds: Optional (start, end) bounds for experience section
            
        Returns:
            Dictionary with title/company or None if validation fails
        """
        # Step 1: Try strict spaced @ pattern first
        title_company = self._try_spaced_at_pattern(line)
        
        # Step 2: If spaced @ fails, try safe separator patterns
        if not title_company:
            title_company = self._try_safe_separator_patterns(line)
        
        if not title_company:
            return None
        
        title, company = title_company
        
        # Step 3: Domain-aware company validation
        if not self._validate_company_not_domain(company):
            return None
        
        # Step 4: Title quality validation
        if not self._validate_title_quality(title):
            return None
        
        # Step 5: Context validation (require supporting signals)
        if not self._validate_supporting_context(line_idx, text_lines, section_bounds):
            return None
        
        # All validations passed
        logger.debug(f"HARDENED_EXTRACT: success | line={line_idx} "
                    f"title_len={len(title)} company_len={len(company)}")
        
        return {
            'title': title.strip(),
            'company': company.strip(),
            'source_line_idx': line_idx,
            'extraction_method': 'hardened_pattern',
            'confidence': self._calculate_confidence(title, company, line_idx, text_lines)
        }
    
    def _try_spaced_at_pattern(self, line: str) -> Optional[Tuple[str, str]]:
        """Try the strict spaced @ pattern."""
        if not self.require_spaced_at:
            return None
        
        match = self.spaced_at_pattern.match(line.strip())
        if match:
            title, company = match.groups()
            self.metrics.enforce_spaced_at_pattern("spaced_@")
            logger.debug(f"SPACED_AT_MATCH: title_len={len(title)} company_len={len(company)}")
            return title, company
        
        return None
    
    def _try_safe_separator_patterns(self, line: str) -> Optional[Tuple[str, str]]:
        """Try safe separator patterns (no @ symbol)."""
        for pattern in self.safe_separator_patterns:
            match = pattern.match(line.strip())
            if match:
                title, company = match.groups()
                logger.debug(f"SAFE_SEPARATOR_MATCH: pattern={pattern.pattern[:20]}... "
                           f"title_len={len(title)} company_len={len(company)}")
                return title, company
        
        return None
    
    def _validate_company_not_domain(self, company: str) -> bool:
        """Validate that company is not domain-like."""
        company = company.strip()
        
        if not company or len(company) < 2:
            self.metrics.reject_domain_like_company(company, "too_short")
            return False
        
        # Check for domain-like patterns
        if self.domain_detector.is_domain_like(company):
            self.metrics.reject_domain_like_company(company, "domain_like")
            logger.debug(f"DOMAIN_REJECT: company appears domain-like | company='[REDACTED]'")
            return False
        
        # Check for email domain patterns specifically
        if self.domain_detector.is_email_domain(company):
            self.metrics.reject_email_like_company(company, "email_domain")
            logger.debug(f"EMAIL_DOMAIN_REJECT: company appears to be email domain | company='[REDACTED]'")
            return False
        
        return True
    
    def _validate_title_quality(self, title: str) -> bool:
        """Validate that title meets quality requirements."""
        title = title.strip()
        
        if not title or len(title) < 2:
            self.metrics.reject_single_word_title(title)
            return False
        
        # Check for single word titles that are all lowercase
        words = title.split()
        if len(words) == 1 and words[0].islower():
            # Allow if it's a known role title
            if words[0].lower() not in self.valid_role_titles:
                self.metrics.reject_lowercase_title(title)
                logger.debug(f"TITLE_REJECT: single_lowercase_word | title='[REDACTED]'")
                return False
        
        # Check for completely lowercase multi-word titles (likely parsing errors)
        if len(words) > 1 and title.islower():
            self.metrics.reject_lowercase_title(title)
            logger.debug(f"TITLE_REJECT: all_lowercase | title='[REDACTED]'")
            return False
        
        return True
    
    def _validate_supporting_context(self, line_idx: int, text_lines: List[str], 
                                   section_bounds: Optional[Tuple[int, int]]) -> bool:
        """Validate that there are supporting signals for this extraction."""
        
        # Check 1: Are we within experience section bounds or near exp header?
        if section_bounds:
            start, end = section_bounds
            if not (start <= line_idx <= end):
                # Outside section bounds - check if within fallback window of a header
                if not self._within_exp_header_window(line_idx, text_lines):
                    self.metrics.reject_no_supporting_signals("", "")
                    logger.debug(f"CONTEXT_REJECT: outside_exp_bounds | line={line_idx} bounds={section_bounds}")
                    return False
        
        # Check 2: Look for action verbs in nearby lines (supporting signals)
        if self._has_action_verb_support(line_idx, text_lines):
            logger.debug(f"CONTEXT_SUPPORT: action_verbs_found | line={line_idx}")
            return True
        
        # Check 3: Look for experience-related keywords in nearby lines
        if self._has_experience_keyword_support(line_idx, text_lines):
            logger.debug(f"CONTEXT_SUPPORT: exp_keywords_found | line={line_idx}")
            return True
        
        # No supporting signals found
        self.metrics.reject_no_supporting_signals("", "")
        logger.debug(f"CONTEXT_REJECT: no_supporting_signals | line={line_idx}")
        return False
    
    def _within_exp_header_window(self, line_idx: int, text_lines: List[str]) -> bool:
        """Check if line is within fallback window of an experience header."""
        window_start = max(0, line_idx - self.fallback_window_size)
        window_end = min(len(text_lines), line_idx + 1)
        
        for i in range(window_start, window_end):
            if i < len(text_lines):
                line = text_lines[i]
                for pattern in self.exp_header_patterns:
                    if pattern.search(line):
                        logger.debug(f"EXP_HEADER_WINDOW: found_header | header_line={i} target_line={line_idx}")
                        return True
        
        return False
    
    def _has_action_verb_support(self, line_idx: int, text_lines: List[str]) -> bool:
        """Check for action verbs in nearby lines."""
        # Check line itself and 2 lines below
        check_range = range(line_idx, min(len(text_lines), line_idx + 3))
        
        for i in check_range:
            if i < len(text_lines):
                line = text_lines[i]
                for pattern in self.action_verb_patterns:
                    if pattern.search(line):
                        return True
        
        return False
    
    def _has_experience_keyword_support(self, line_idx: int, text_lines: List[str]) -> bool:
        """Check for experience-related keywords in nearby lines."""
        # Simple keyword check
        keywords = ['responsibilities', 'achievements', 'tasks', 'duties', 
                   'responsabilités', 'réalisations', 'tâches', 'missions']
        
        # Check current line and 3 lines below
        check_range = range(line_idx, min(len(text_lines), line_idx + 4))
        
        for i in check_range:
            if i < len(text_lines):
                line_lower = text_lines[i].lower()
                for keyword in keywords:
                    if keyword in line_lower:
                        return True
        
        return False
    
    def _calculate_confidence(self, title: str, company: str, line_idx: int, text_lines: List[str]) -> float:
        """Calculate confidence score for the extraction."""
        confidence = 0.5  # Base confidence
        
        # Boost for longer, more descriptive titles
        if len(title.split()) >= 2:
            confidence += 0.1
        
        # Boost for company names that look substantial
        if len(company.split()) >= 2 or len(company) >= 5:
            confidence += 0.1
        
        # Boost for action verb support
        if self._has_action_verb_support(line_idx, text_lines):
            confidence += 0.2
        
        # Boost for proper capitalization
        if title[0].isupper() and company[0].isupper():
            confidence += 0.1
        
        return min(1.0, confidence)
    
    def is_email_line(self, line: str) -> bool:
        """Quick check if line contains an email (should never match role@company)."""
        # Simple email detection
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        return bool(re.search(email_pattern, line))
    
    def batch_extract_safe_patterns(self, text_lines: List[str], 
                                  section_bounds: Optional[Tuple[int, int]] = None) -> List[Dict[str, Any]]:
        """
        Extract all safe title@company patterns from text lines.
        
        Args:
            text_lines: List of text lines
            section_bounds: Optional experience section bounds
            
        Returns:
            List of extracted experience dictionaries
        """
        extractions = []
        
        for i, line in enumerate(text_lines):
            # Skip empty lines
            if not line.strip():
                continue
            
            # Skip obvious email lines immediately
            if self.is_email_line(line):
                logger.debug(f"EMAIL_SKIP: skipping_email_line | line={i}")
                continue
            
            # Try extraction
            extraction = self.extract_title_company_safe(line, i, text_lines, section_bounds)
            if extraction:
                extractions.append(extraction)
        
        logger.info(f"BATCH_EXTRACT: processed={len(text_lines)} extracted={len(extractions)}")
        return extractions


# Module-level convenience functions
_global_patterns: Optional[HardenedExperiencePatterns] = None


def get_hardened_patterns(config: Dict[str, Any] = None) -> HardenedExperiencePatterns:
    """Get or create the global hardened patterns instance."""
    global _global_patterns
    
    if _global_patterns is None:
        _global_patterns = HardenedExperiencePatterns(config)
    
    return _global_patterns


def extract_safe_title_company(line: str, line_idx: int, text_lines: List[str],
                              section_bounds: Optional[Tuple[int, int]] = None) -> Optional[Dict[str, Any]]:
    """Convenience function for safe title@company extraction."""
    patterns = get_hardened_patterns()
    return patterns.extract_title_company_safe(line, line_idx, text_lines, section_bounds)


def is_line_email(line: str) -> bool:
    """Convenience function to check if line contains email."""
    patterns = get_hardened_patterns()
    return patterns.is_email_line(line)