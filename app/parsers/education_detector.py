"""
Education Detector - Advanced education content detection and field extraction.

Implements composable education detection with scoring, field extraction,
and noise filtering to achieve target edu_keep_rate ≥ 0.20.
"""

import re
import unicodedata
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, date
import json
from pathlib import Path

from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG
from ..utils.pii import validate_no_pii_leakage

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)

# Configuration constants
EDU_SCORE_THRESHOLD = 0.6
EDU_MIN_KEEP_RATE_TARGET = 0.20
ACRONYM_MAX_LENGTH = 4
DEGREE_SCORE_WEIGHT = 0.40
SCHOOL_SCORE_WEIGHT = 0.25
DATE_SCORE_WEIGHT = 0.15
PROGRAM_SCORE_WEIGHT = 0.10
SIGLE_PENALTY = -0.30

class EducationDetector:
    """Advanced education content detector with composable scoring."""
    
    def __init__(self):
        self.logger = get_safe_logger(f"{__name__}.EducationDetector", cfg=DEFAULT_PII_CONFIG)
        
        # Degree patterns (French + English)
        self.degree_patterns = [
            # French degrees
            r'\b(?:licence|bachelor|bac\+?3)\b',
            r'\b(?:master|ma[îi]trise|bac\+?5|m[12]|msc|ms)\b', 
            r'\b(?:doctorat|phd|doctorate|bac\+?8)\b',
            r'\b(?:dut|bts|but|iut|iup)\b',
            r'\b(?:ingenieur|engineer|diplome)\b',
            r'\b(?:mba|executive|emba)\b',
            r'\b(?:cap|bep|bac|baccalaur[ée]at)\b',
            r'\b(?:deug|deust|dess|dea)\b',
            r'\b(?:prépa?|cpge|classe?\s+pr[ée]paratoire)\b',
            
            # English degrees  
            r'\b(?:bachelor|ba|bs|bsc|be|beng)\b',
            r'\b(?:master|ma|ms|msc|meng|mba)\b',
            r'\b(?:doctorate|phd|dphil|edd|dsn|dba)\b',
            r'\b(?:associate|diploma|certificate)\b',
            r'\b(?:foundation|access|btec|hnc|hnd)\b'
        ]
        
        # School indicators
        self.school_patterns = [
            # French institutions
            r'\b(?:universit[ée]|univ|fac|facult[ée])\b',
            r'\b(?:[ée]cole|lyc[ée]e|lyc|coll[èe]ge)\b', 
            r'\b(?:iut|insa|ut|ens|ensi|epsi|esiee|epitech|supinfo)\b',
            r'\b(?:grande?\s+[ée]cole|business\s+school)\b',
            r'\b(?:institut|center|centre|campus)\b',
            
            # English institutions
            r'\b(?:university|college|school|institute|academy)\b',
            r'\b(?:polytechnic|tech|technological)\b',
            r'\b(?:faculty|department|dept)\b'
        ]
        
        # Program/specialization phrases
        self.program_patterns = [
            r'\b(?:option|sp[ée]cialit[ée]|parcours|mention)\b',
            r'\b(?:apprentissage|alternance|contrat\s+pro)\b',
            r'\b(?:formation|cursus|programme?)\b',
            r'\b(?:major|minor|concentration|track|stream)\b',
            r'\b(?:honors?|avec\s+f[ée]licitations)\b'
        ]
        
        # Date patterns for education context
        self.date_patterns = [
            r'\b\d{4}\s*[-–—]\s*\d{4}\b',           # 2019-2022
            r'\b\d{1,2}/\d{4}\s*[-–—]\s*\d{1,2}/\d{4}\b',  # 09/2019-06/2022
            r'\b\d{4}\s*[-–—]\s*(?:présent|present|actuel|en\s+cours)\b',
            r'\b(?:de|from)\s+\d{4}\s+(?:[àa]|to)\s+\d{4}\b'
        ]
        
        # Compile all patterns for efficiency
        self._compile_patterns()
        
        # Load education lexicon if available
        self._load_education_lexicon()
    
    def _compile_patterns(self):
        """Compile regex patterns for performance."""
        self.degree_regex = [re.compile(pattern, re.IGNORECASE) for pattern in self.degree_patterns]
        self.school_regex = [re.compile(pattern, re.IGNORECASE) for pattern in self.school_patterns]
        self.program_regex = [re.compile(pattern, re.IGNORECASE) for pattern in self.program_patterns]
        self.date_regex = [re.compile(pattern, re.IGNORECASE) for pattern in self.date_patterns]
        
        # Short uppercase sigle pattern (for penalty)
        self.sigle_pattern = re.compile(r'^\s*[A-Z]{2,4}\s*$')
        
        # Education context pattern
        self.edu_context_pattern = re.compile(
            r'\b(?:dipl[ôo]me?|certificat|formation|[ée]tudes?|academic|study|studies|graduation?)\b',
            re.IGNORECASE
        )
    
    def _load_education_lexicon(self):
        """Load education organization lexicon for enhanced detection."""
        try:
            lexicon_path = Path("app/data/edu_org_lexicon.txt")
            if lexicon_path.exists():
                with open(lexicon_path, 'r', encoding='utf-8') as f:
                    self.edu_lexicon = set(line.strip().lower() for line in f if line.strip())
                self.logger.debug(f"Loaded {len(self.edu_lexicon)} education terms from lexicon")
            else:
                self.edu_lexicon = set()
                self.logger.debug("Education lexicon not found, using patterns only")
        except Exception as e:
            self.logger.warning(f"Failed to load education lexicon: {e}")
            self.edu_lexicon = set()
    
    def is_education_line(self, text: str) -> bool:
        """
        Determine if a line represents education content.
        
        Args:
            text: Text line to analyze
            
        Returns:
            True if line is education-related
        """
        if not text or len(text.strip()) < 3:
            return False
        
        score = self.score_education_candidate(text)
        return score >= EDU_SCORE_THRESHOLD
    
    def score_education_candidate(self, text: str) -> float:
        """
        Score education content on scale 0-1.
        
        Args:
            text: Text to score
            
        Returns:
            Education score (0.0 to 1.0)
        """
        if not text:
            return 0.0
        
        # Normalize text for matching
        normalized = unicodedata.normalize('NFKC', text.lower().strip())
        score = 0.0
        
        # Degree keyword detection (+0.40)
        degree_found = any(pattern.search(normalized) for pattern in self.degree_regex)
        if degree_found:
            score += DEGREE_SCORE_WEIGHT
            self.logger.debug(f"EDU_SCORE: degree keyword found (+{DEGREE_SCORE_WEIGHT})")
        
        # School cue detection (+0.25)  
        school_found = any(pattern.search(normalized) for pattern in self.school_regex)
        if school_found:
            score += SCHOOL_SCORE_WEIGHT
            self.logger.debug(f"EDU_SCORE: school cue found (+{SCHOOL_SCORE_WEIGHT})")
        
        # Education lexicon check (enhance school score)
        if self.edu_lexicon:
            words = set(normalized.split())
            if words & self.edu_lexicon:
                score += 0.15  # Bonus for lexicon match
                self.logger.debug("EDU_SCORE: education lexicon match (+0.15)")
        
        # Valid date pattern (+0.15)
        date_found = any(pattern.search(text) for pattern in self.date_regex)
        if date_found:
            score += DATE_SCORE_WEIGHT
            self.logger.debug(f"EDU_SCORE: date pattern found (+{DATE_SCORE_WEIGHT})")
        
        # Program phrase detection (+0.10)
        program_found = any(pattern.search(normalized) for pattern in self.program_regex)
        if program_found:
            score += PROGRAM_SCORE_WEIGHT
            self.logger.debug(f"EDU_SCORE: program phrase found (+{PROGRAM_SCORE_WEIGHT})")
        
        # Education context bonus
        if self.edu_context_pattern.search(normalized):
            score += 0.05
            self.logger.debug("EDU_SCORE: education context (+0.05)")
        
        # Short sigle penalty (-0.30)
        if self.sigle_pattern.match(text.strip()):
            score += SIGLE_PENALTY  # Negative value
            self.logger.debug(f"EDU_SCORE: short sigle penalty ({SIGLE_PENALTY})")
        
        # Ensure score bounds
        score = max(0.0, min(1.0, score))
        
        return score
    
    def extract_education_fields(self, text: str) -> Dict[str, Any]:
        """
        Extract structured education fields from text.
        
        Args:
            text: Education text line
            
        Returns:
            Dictionary with education fields
        """
        if not text:
            return {}
        
        fields = {
            'original_text': text,
            'degree': None,
            'field': None, 
            'institution': None,
            'city': None,
            'country': None,
            'start_date': None,
            'end_date': None,
            'current': False,
            'notes': None,
            'confidence_score': self.score_education_candidate(text),
            'date_warning': None
        }
        
        # Extract degree
        fields['degree'] = self._extract_degree(text)
        
        # Extract institution
        fields['institution'] = self._extract_institution(text)
        
        # Extract field of study
        fields['field'] = self._extract_field_of_study(text)
        
        # Extract dates with validation
        start_date, end_date, is_current, date_warning = self._extract_and_validate_dates(text)
        fields['start_date'] = start_date
        fields['end_date'] = end_date
        fields['current'] = is_current
        fields['date_warning'] = date_warning
        
        # Extract location if present
        location = self._extract_location(text)
        if location:
            fields['city'] = location.get('city')
            fields['country'] = location.get('country')
        
        # Extract additional notes
        fields['notes'] = self._extract_notes(text)
        
        return fields
    
    def _extract_degree(self, text: str) -> Optional[str]:
        """Extract degree type from text."""
        for pattern in self.degree_regex:
            match = pattern.search(text)
            if match:
                degree = match.group(0).strip()
                self.logger.debug(f"EDU_EXTRACT: degree found '{degree}'")
                return degree.title()
        return None
    
    def _extract_institution(self, text: str) -> Optional[str]:
        """Extract institution name from text."""
        # Look for institution patterns with context
        patterns = [
            r'(?:à|at|@|—|–|-)\s*([^0-9\n]*(?:universit[ée]|[ée]cole|lyc[ée]e|college|university|institute)[^0-9\n]*)',
            r'([^0-9\n]*(?:universit[ée]|[ée]cole|lyc[ée]e|college|university|institute)[^0-9\n]*?)(?:\s*[0-9]|\s*$)',
            r'(?:dans|in)\s*([^0-9\n]*(?:universit[ée]|[ée]cole|lyc[ée]e|college|university|institute)[^0-9\n]*)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                institution = match.group(1).strip()
                # Clean up common noise
                institution = re.sub(r'^[—–-]+\s*', '', institution)
                institution = re.sub(r'\s*[—–-]+$', '', institution)
                if len(institution) > 3:
                    self.logger.debug(f"EDU_EXTRACT: institution found '{institution[:30]}...'")
                    return institution
        return None
    
    def _extract_field_of_study(self, text: str) -> Optional[str]:
        """Extract field of study from text."""
        # Common field patterns
        patterns = [
            r'\b(?:en|in)\s+([^0-9\n,]{3,40}?)(?:\s*[—–-]|\s*à|\s*$)',
            r'\b(?:option|spécialité|major)\s+([^0-9\n,]{3,40}?)(?:\s*[—–-]|\s*à|\s*$)',
            r'(?:bachelor|master|licence)\s+(?:of|en|de)?\s*([^0-9\n—–-]{3,40}?)(?:\s*[—–-]|\s*à)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                field = match.group(1).strip()
                if len(field) >= 3:
                    self.logger.debug(f"EDU_EXTRACT: field found '{field}'")
                    return field.title()
        return None
    
    def _extract_location(self, text: str) -> Optional[Dict[str, str]]:
        """Extract location information."""
        # Simple city pattern (extend as needed)
        city_pattern = r',\s*([A-Za-zÀ-ÿ\s-]{3,25}?)(?:\s*[0-9]|\s*$)'
        match = re.search(city_pattern, text)
        if match:
            city = match.group(1).strip()
            return {'city': city, 'country': None}
        return None
    
    def _extract_notes(self, text: str) -> Optional[str]:
        """Extract additional notes/context."""
        # Look for parenthetical or additional context
        notes_patterns = [
            r'\(([^)]{5,50})\)',
            r'—\s*([^0-9\n]{5,50}?)$'
        ]
        
        for pattern in notes_patterns:
            match = re.search(pattern, text)
            if match:
                notes = match.group(1).strip()
                if len(notes) >= 5:
                    return notes
        return None
    
    def _extract_and_validate_dates(self, text: str) -> Tuple[Optional[datetime], Optional[datetime], bool, Optional[str]]:
        """
        Extract and validate date ranges with temporal consistency.
        
        Returns:
            Tuple (start_date, end_date, is_current, date_warning)
        """
        from ..rules.date_normalize import normalize_date_span, is_valid_date_range
        from ..utils.robust_date_parser import parse_dates_with_validation
        
        try:
            # Use existing date parsing with validation
            start_date, end_date, is_current, validation_flags = parse_dates_with_validation(
                text, context_lines=[text]
            )
            
            date_warning = None
            
            # Check for temporal inconsistency
            if not validation_flags.get('temporal_valid', True):
                date_warning = 'end_before_start'
                end_date = None  # Drop invalid end date
                self.logger.debug("EDU_DATE: temporal inconsistency detected, end_date dropped")
            
            # Additional validation for education context
            if start_date and end_date:
                # Education periods should generally be reasonable (not too short/long)
                years_diff = (end_date.year - start_date.year) + (end_date.month - start_date.month) / 12
                if years_diff < 0.25:  # Less than 3 months seems suspicious for education
                    date_warning = 'duration_too_short'
                elif years_diff > 15:  # More than 15 years seems suspicious  
                    date_warning = 'duration_too_long'
            
            return start_date, end_date, is_current, date_warning
            
        except Exception as e:
            self.logger.warning(f"EDU_DATE: extraction failed for '{text[:50]}...': {e}")
            return None, None, False, 'extraction_failed'


def is_education_line(text: str) -> bool:
    """
    Global function for education line detection.
    
    Args:
        text: Text line to analyze
        
    Returns:
        True if line contains education content
    """
    detector = EducationDetector()
    return detector.is_education_line(text)


def score_education_candidate(text: str) -> float:
    """
    Global function for education scoring.
    
    Args:
        text: Text to score
        
    Returns:
        Education score (0.0 to 1.0)
    """
    detector = EducationDetector()
    return detector.score_education_candidate(text)


def extract_education_fields(text: str) -> Dict[str, Any]:
    """
    Global function for education field extraction.
    
    Args:
        text: Education text line
        
    Returns:
        Dictionary with extracted education fields
    """
    detector = EducationDetector()
    return detector.extract_education_fields(text)


# Singleton detector instance for performance
_detector_instance = None

def get_education_detector() -> EducationDetector:
    """Get singleton education detector instance."""
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = EducationDetector()
    return _detector_instance