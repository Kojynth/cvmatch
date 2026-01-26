"""
Contact line detector for CV extraction pipeline.
Identifies and flags contact information lines to prevent misclassification.
"""

import re
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass
from ..logging.safe_logger import get_safe_logger, DEFAULT_PII_CONFIG

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


@dataclass
class ContactLineResult:
    """Result from contact line detection."""
    line_idx: int
    is_contact: bool
    header_block: bool
    contact_types: List[str]  # Types of contact info found: ['email', 'phone', 'url', 'address']
    confidence: float


class ContactLineDetector:
    """Detects contact information lines in CV text."""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self._init_patterns()
        
        # Configuration
        self.header_block_threshold = self.config.get('header_block_threshold', 0.7)
        self.header_block_max_lines = self.config.get('header_block_max_lines', 10)
        self.address_min_words = self.config.get('address_min_words', 3)
    
    def _init_patterns(self):
        """Initialize regex patterns for contact detection."""
        
        # Email patterns
        self.email_patterns = [
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            r'\b[A-Za-z0-9._%+-]+\s*[@]\s*[A-Za-z0-9.-]+\s*[.]\s*[A-Z|a-z]{2,}\b'
        ]
        
        # Phone patterns (comprehensive international formats)
        self.phone_patterns = [
            r'(?:\+33|0033|0)[1-9](?:[0-9]{8})',  # French
            r'(?:\+1[-.\s]?)?(?:\([2-9][0-9]{2}\)|[2-9][0-9]{2})[-.\s]?[2-9][0-9]{2}[-.\s]?[0-9]{4}',  # US
            r'(?:\+49|0049|0)[1-9][0-9]{1,14}',  # German
            r'(?:\+44|0044|0)[1-9][0-9]{8,10}',  # UK
            r'(?:\+|00)[1-9]\d{1,4}[-.\s]?\d{1,4}[-.\s]?\d{1,9}',  # International
            r'\b(?:\d{2}[-.\s]?){4}\d{2}\b',  # Generic 10-digit
            r'\b(?:\d{3}[-.\s]?){2}\d{4}\b',  # Generic with separators
            r'\b\d{10,15}\b'  # Simple numeric sequence
        ]
        
        # URL/Social media patterns
        self.url_patterns = [
            r'https?://[^\s<>"{}|\\^`\[\]]+',
            r'www\.[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
            r'linkedin\.com/in/[a-zA-Z0-9-]+',
            r'github\.com/[a-zA-Z0-9-]+',
            r'twitter\.com/[a-zA-Z0-9_]+',
            r'@[a-zA-Z0-9_]+',  # Social handles
        ]
        
        # Address patterns (partial postal addresses)
        self.address_patterns = [
            r'\b\d{5}\s+[A-Za-z\s]+\b',  # ZIP + City
            r'\b[A-Za-z\s]+,\s*\d{5}\b',  # City, ZIP
            r'\b\d{1,5}\s+[A-Za-z\s]+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr)\b',
            r'\b(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr)\s+\w+',
            r'\b\d{2,5}\s*,?\s*[A-Za-z\s]+\s*,\s*\d{5}',  # Address with ZIP
        ]
        
        # Compile patterns for efficiency
        self.compiled_email = [re.compile(p, re.IGNORECASE) for p in self.email_patterns]
        self.compiled_phone = [re.compile(p) for p in self.phone_patterns]
        self.compiled_url = [re.compile(p, re.IGNORECASE) for p in self.url_patterns]
        self.compiled_address = [re.compile(p, re.IGNORECASE) for p in self.address_patterns]
    
    def detect_contact_lines(self, text_lines: List[str]) -> List[ContactLineResult]:
        """
        Detect contact information in lines of text.
        
        Args:
            text_lines: List of text lines to analyze
            
        Returns:
            List of ContactLineResult objects
        """
        results = []
        
        for i, line in enumerate(text_lines):
            if not line.strip():
                continue
                
            contact_types, confidence = self._analyze_line(line)
            is_contact = len(contact_types) > 0
            
            results.append(ContactLineResult(
                line_idx=i,
                is_contact=is_contact,
                header_block=False,  # Will be set in post-processing
                contact_types=contact_types,
                confidence=confidence
            ))
        
        # Detect header blocks
        results = self._detect_header_blocks(results, text_lines)
        
        # Log summary
        contact_count = sum(1 for r in results if r.is_contact)
        header_block_count = sum(1 for r in results if r.header_block)
        
        logger.info(f"CONTACT_DETECT: analyzed={len(text_lines)} lines "
                   f"contact_lines={contact_count} header_block_lines={header_block_count}")
        
        return results
    
    def _analyze_line(self, line: str) -> Tuple[List[str], float]:
        """Analyze a single line for contact information."""
        contact_types = []
        confidences = []
        
        # Check email
        for pattern in self.compiled_email:
            if pattern.search(line):
                contact_types.append('email')
                confidences.append(0.95)
                logger.debug(f"CONTACT_EMAIL: detected in line '{line[:30]}...'")
                break
        
        # Check phone
        for pattern in self.compiled_phone:
            if pattern.search(line.replace(' ', '').replace('-', '').replace('.', '')):
                contact_types.append('phone')
                confidences.append(0.85)
                logger.debug(f"CONTACT_PHONE: detected in line '{line[:30]}...'")
                break
        
        # Check URL/Social
        for pattern in self.compiled_url:
            if pattern.search(line):
                contact_types.append('url')
                confidences.append(0.90)
                logger.debug(f"CONTACT_URL: detected in line '{line[:30]}...'")
                break
        
        # Check address (requires minimum word count)
        if len(line.split()) >= self.address_min_words:
            for pattern in self.compiled_address:
                if pattern.search(line):
                    contact_types.append('address')
                    confidences.append(0.70)
                    logger.debug(f"CONTACT_ADDRESS: detected in line '{line[:30]}...'")
                    break
        
        # Calculate overall confidence
        if confidences:
            confidence = max(confidences)
        else:
            confidence = 0.0
        
        return contact_types, confidence
    
    def _detect_header_blocks(self, results: List[ContactLineResult], 
                            text_lines: List[str]) -> List[ContactLineResult]:
        """Detect contiguous header blocks dominated by contact information."""
        
        # Only consider first N lines as potential header
        header_candidates = results[:self.header_block_max_lines]
        
        if not header_candidates:
            return results
        
        # Find contiguous blocks of contact lines from the top
        contact_block_end = 0
        for i, result in enumerate(header_candidates):
            if result.is_contact or not text_lines[result.line_idx].strip():
                # Contact line or empty line (common in headers)
                contact_block_end = i + 1
            else:
                break
        
        # Check if we have enough contact density
        if contact_block_end >= 2:  # Minimum block size
            contact_lines_in_block = sum(1 for r in header_candidates[:contact_block_end] if r.is_contact)
            non_empty_lines = sum(1 for i in range(contact_block_end) 
                                if text_lines[i].strip())
            
            if non_empty_lines > 0:
                contact_density = contact_lines_in_block / non_empty_lines
                
                if contact_density >= self.header_block_threshold:
                    # Mark as header block
                    for i in range(contact_block_end):
                        if i < len(results):
                            results[i].header_block = True
                    
                    logger.info(f"HEADER_BLOCK: detected lines=0-{contact_block_end-1} "
                              f"density={contact_density:.2f} contact_lines={contact_lines_in_block}")
        
        return results
    
    def is_email_line(self, line: str) -> bool:
        """Quick check if line contains an email address."""
        for pattern in self.compiled_email:
            if pattern.search(line):
                return True
        return False
    
    def is_phone_line(self, line: str) -> bool:
        """Quick check if line contains a phone number."""
        cleaned_line = line.replace(' ', '').replace('-', '').replace('.', '')
        for pattern in self.compiled_phone:
            if pattern.search(cleaned_line):
                return True
        return False
    
    def is_url_line(self, line: str) -> bool:
        """Quick check if line contains a URL or social handle."""
        for pattern in self.compiled_url:
            if pattern.search(line):
                return True
        return False