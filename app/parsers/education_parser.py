from .metrics_mixin import ParserMetricsMixin
"""
Education Parser - Enhanced education section parsing with degree classification.

This parser implements:
- Degree classification and validation
- Institution validation and enrichment
- French education system awareness
- Academic achievement scoring
- Educational timeline validation
"""

import re
from typing import List, Dict, Any, Optional, Tuple
from datetime import date, datetime
from dataclasses import dataclass

from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG
from ..utils.fallback_date_parser import get_fallback_date_parser
from ..utils.org_sieve import SchoolLexicon
from .education_detector import EducationDetector

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


@dataclass
class EducationMetrics:
    """Metrics for education parsing and classification."""
    entries_received: int = 0
    entries_processed: int = 0
    entries_validated: int = 0
    entries_rejected: int = 0
    degree_classifications: Dict[str, int] = None
    institution_validations: int = 0
    validation_failures: List[str] = None
    
    def __post_init__(self):
        if self.degree_classifications is None:
            self.degree_classifications = {}
        if self.validation_failures is None:
            self.validation_failures = []


class EducationParser(ParserMetricsMixin):
    """
    Enhanced education parser with degree classification and institution validation.
    
    Key features:
    - French education system classification
    - Institution validation using SchoolLexicon
    - Academic achievement scoring
    - Timeline validation and normalization
    """
    
    def __init__(self):
        self.logger = get_safe_logger(f"{__name__}.EducationParser", cfg=DEFAULT_PII_CONFIG)
        self.date_parser = get_fallback_date_parser()
        self.school_lexicon = SchoolLexicon()
        self.education_detector = EducationDetector()
        self.metrics = EducationMetrics()
        
        # French education levels (Bac+X system)
        self.french_degree_levels = {
            'bac': 0,
            'bts': 2, 'dut': 2, 'but': 3,
            'licence': 3, 'bachelor': 3,
            'master': 5, 'mastère': 5, 'msc': 5, 'ms': 5,
            'ingénieur': 5, 'engineer': 5,
            'doctorat': 8, 'phd': 8, 'doctorate': 8,
            'mba': 5
        }
        
        # Degree classification patterns
        self.degree_patterns = {
            'high_school': [
                r'\b(?:bac|baccalauréat|high\s+school|lycée)\b',
                r'\b(?:terminale|seconde|première)\b'
            ],
            'vocational': [
                r'\b(?:bts|dut|but|cap|bep|bac\s+pro)\b',
                r'\b(?:formation\s+professionnelle|apprentissage)\b'
            ],
            'undergraduate': [
                r'\b(?:licence|bachelor|l[123]|deug|deust)\b',
                r'\b(?:bac\+?3|niveau\s+bac\+?3)\b'
            ],
            'graduate': [
                r'\b(?:master|mastère|m[12]|msc|ms|maîtrise)\b',
                r'\b(?:bac\+?[45]|niveau\s+bac\+?[45])\b',
                r'\b(?:ingénieur|engineer|diplôme\s+ingénieur)\b'
            ],
            'postgraduate': [
                r'\b(?:doctorat|phd|doctorate|thèse)\b',
                r'\b(?:bac\+?8|niveau\s+bac\+?8)\b'
            ],
            'business': [
                r'\b(?:mba|executive\s+mba|emba)\b',
                r'\b(?:école\s+de\s+commerce|business\s+school)\b'
            ]
        }
        
        # Subject/field patterns
        self.field_patterns = {
            'computer_science': [
                r'\b(?:informatique|computer\s+science|cs|it)\b',
                r'\b(?:développement|programming|software)\b',
                r'\b(?:data\s+science|intelligence\s+artificielle|ai)\b'
            ],
            'engineering': [
                r'\b(?:ingénierie|engineering|génie)\b',
                r'\b(?:mécanique|mechanical|électrique|electrical)\b',
                r'\b(?:civil|chimie|chemistry|industriel)\b'
            ],
            'business': [
                r'\b(?:commerce|business|management|gestion)\b',
                r'\b(?:marketing|finance|comptabilité|accounting)\b',
                r'\b(?:économie|economics|administration)\b'
            ],
            'sciences': [
                r'\b(?:mathématiques|mathematics|physique|physics)\b',
                r'\b(?:biologie|biology|chimie|chemistry)\b',
                r'\b(?:sciences|science|recherche|research)\b'
            ],
            'humanities': [
                r'\b(?:lettres|literature|histoire|history)\b',
                r'\b(?:philosophie|philosophy|sociologie|sociology)\b',
                r'\b(?:langues|languages|communication)\b'
            ]
        }
        
        # Institution type patterns
        self.institution_patterns = {
            'university': [
                r'\b(?:université|university|fac|faculté)\b',
                r'\b(?:sorbonne|panthéon|sciences\s+po)\b'
            ],
            'engineering_school': [
                r'\b(?:école\s+d[\'e]\s*ingénieurs?|engineering\s+school)\b',
                r'\b(?:centrale|polytechnique|mines|ponts)\b',
                r'\b(?:insa|ensam|supelec|telecom)\b'
            ],
            'business_school': [
                r'\b(?:école\s+de\s+commerce|business\s+school)\b',
                r'\b(?:hec|essec|escp|edhec|emlyon|skema)\b'
            ],
            'technical_institute': [
                r'\b(?:iut|institut\s+universitaire)\b',
                r'\b(?:lycée\s+technique|centre\s+de\s+formation)\b'
            ]
        }
    
    def parse_education_section(self, lines: List[str], start_idx: int = 0, end_idx: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Parse education section with degree classification and validation.
        
        Args:
            lines: Lines of text to parse
            start_idx: Start index in original document
            end_idx: End index in original document
            
        Returns:
            List of classified and validated education entries
        """
        self.metrics = EducationMetrics()
        self.metrics.entries_received = len(lines)
        
        if end_idx is None:
            end_idx = start_idx + len(lines)
        
        logger.info(f"EDUCATION_PARSER: parse_start | lines={len(lines)} range=({start_idx}-{end_idx})")
        
        if not lines:
            logger.info("EDUCATION_PARSER: empty_lines | skipping parsing")
            return []
        
        # Extract raw education entries
        raw_entries = self._extract_raw_entries(lines)
        self.metrics.entries_processed = len(raw_entries)
        
        # Classify and validate entries
        classified_entries = []
        for entry in raw_entries:
            classified_entry = self._classify_and_validate_entry(entry)
            if classified_entry:
                classified_entries.append(classified_entry)
                self.metrics.entries_validated += 1
            else:
                self.metrics.entries_rejected += 1
        
        # Sort by educational level and timeline
        sorted_entries = self._sort_by_timeline_and_level(classified_entries)
        
        logger.info(f"EDUCATION_PARSER: parse_complete | "
                   f"processed={self.metrics.entries_processed} "
                   f"validated={self.metrics.entries_validated} "
                   f"rejected={self.metrics.entries_rejected} "
                   f"final={len(sorted_entries)}")
        
        return sorted_entries
    
    def _extract_raw_entries(self, lines: List[str]) -> List[Dict[str, Any]]:
        """
        Extract raw education entries from lines.
        
        Args:
            lines: Lines to extract from
            
        Returns:
            List of raw education entries
        """
        entries = []
        current_entry = None
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            
            # Detect new education entry
            if self._is_education_header(line):
                # Save previous entry
                if current_entry:
                    entries.append(current_entry)
                
                # Start new entry
                current_entry = {
                    'line_idx': i,
                    'raw_lines': [line],
                    'degree': self._extract_degree_from_line(line),
                    'institution': self._extract_institution_from_line(line),
                    'field': self._extract_field_from_line(line),
                    'dates': self._extract_dates_from_line(line),
                    'additional_info': []
                }
            elif current_entry:
                # Add content to current entry
                current_entry['raw_lines'].append(line)
                
                # Extract additional information
                if not current_entry['degree']:
                    degree = self._extract_degree_from_line(line)
                    if degree:
                        current_entry['degree'] = degree
                
                if not current_entry['institution']:
                    institution = self._extract_institution_from_line(line)
                    if institution:
                        current_entry['institution'] = institution
                
                if not current_entry['field']:
                    field = self._extract_field_from_line(line)
                    if field:
                        current_entry['field'] = field
                
                if not current_entry['dates']:
                    dates = self._extract_dates_from_line(line)
                    if dates:
                        current_entry['dates'] = dates
                
                # Check for additional info (grades, mentions, specializations)
                if self._is_additional_info(line):
                    current_entry['additional_info'].append(line)
        
        # Don't forget the last entry
        if current_entry:
            entries.append(current_entry)
        
        logger.debug(f"EDUCATION_PARSER: extracted {len(entries)} raw entries")
        return entries
    
    def _is_education_header(self, line: str) -> bool:
        """Check if line is an education entry header."""
        line_lower = line.lower()
        
        # Use existing education detector for initial filtering
        if not self.education_detector.is_education_line(line):
            return False
        
        # Check for degree patterns
        for category, patterns in self.degree_patterns.items():
            for pattern in patterns:
                if re.search(pattern, line_lower):
                    return True
        
        # Check for institution patterns
        for category, patterns in self.institution_patterns.items():
            for pattern in patterns:
                if re.search(pattern, line_lower):
                    return True
        
        return False
    
    def _is_additional_info(self, line: str) -> bool:
        """Check if line contains additional education information."""
        line_lower = line.lower()
        
        # Grade indicators
        grade_patterns = [
            r'\b(?:mention|grade|note|average)\b',
            r'\b(?:distinction|honors|cum\s+laude)\b',
            r'\b(?:\d+[.,]\d+/20|\d+/20|très\s+bien|bien|assez\s+bien)\b'
        ]
        
        for pattern in grade_patterns:
            if re.search(pattern, line_lower):
                return True
        
        # Specialization indicators
        specialization_patterns = [
            r'\b(?:spÃ©cialisation|specialization|major|minor)\b',
            r'\b(?:option|parcours|track|concentration)\b'
        ]
        
        for pattern in specialization_patterns:
            if re.search(pattern, line_lower):
                return True
        
        return False
    
    def _extract_degree_from_line(self, line: str) -> Optional[str]:
        """Extract degree information from line."""
        line_lower = line.lower()
        
        # Try to find degree patterns with context
        for category, patterns in self.degree_patterns.items():
            for pattern in patterns:
                match = re.search(f'({pattern}(?:[^,\\n]{{0,30}})?)', line_lower)
                if match:
                    return match.group(1).strip()
        
        return None
    
    def _extract_institution_from_line(self, line: str) -> Optional[str]:
        """Extract institution name from line."""
        # Look for institution patterns
        institution_patterns = [
            r'(?:Ã |at|universitÃ©|university|Ã©cole|school)\s+([^,\n]{5,50})',
            r'([A-Z][a-zA-ZÃ Ã¢Ã¤Ã§Ã©Ã¨ÃªÃ«Ã¯Ã®Ã´Ã¹Ã»Ã¼Ã¿\s]{5,50})(?:\s*[-,])',
            r'(?:^|\s)([A-Z][a-zA-ZÃ Ã¢Ã¤Ã§Ã©Ã¨ÃªÃ«Ã¯Ã®Ã´Ã¹Ã»Ã¼Ã¿\s]{10,50})(?:\s*$)'
        ]
        
        for pattern in institution_patterns:
            match = re.search(pattern, line)
            if match:
                institution = match.group(1).strip()
                
                # Validate with SchoolLexicon
                is_school, _ = self.school_lexicon.is_school_organization(institution)
                if is_school:
                    self.metrics.institution_validations += 1
                    return institution
                elif len(institution) > 10:  # Reasonable length even if not validated
                    return institution
        
        return None
    
    def _extract_field_from_line(self, line: str) -> Optional[str]:
        """Extract field of study from line."""
        line_lower = line.lower()
        
        # Try to find field patterns
        for field, patterns in self.field_patterns.items():
            for pattern in patterns:
                match = re.search(f'({pattern}(?:[^,\\n]{{0,30}})?)', line_lower)
                if match:
                    return match.group(1).strip()
        
        return None
    
    def _extract_dates_from_line(self, line: str) -> Optional[str]:
        """Extract date information from line."""
        # Reuse date patterns from fallback_date_parser
        date_patterns = [
            r'(\d{4})\s*[-–—]\s*(\d{4})',  # 2020-2023
            r'(\d{4})',  # Single year
            r'([a-zA-Zàâäçéèêëïîôùûüÿ]+\s+\d{4})\s*[-–—]\s*([a-zA-Zàâäçéèêëïîôùûüÿ]+\s+\d{4})',  # Month Year - Month Year
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, line)
            if match:
                return match.group(0)
        
        return None
    
    def _classify_and_validate_entry(self, entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Classify and validate a single education entry.
        
        Args:
            entry: Raw entry to classify and validate
            
        Returns:
            Classified and validated entry or None if invalid
        """
        classified_entry = entry.copy()
        validation_issues = []
        
        # Classify degree
        degree = entry.get('degree', '')
        if degree:
            degree_category, degree_level = self._classify_degree(degree)
            classified_entry['degree_category'] = degree_category
            classified_entry['degree_level'] = degree_level
            classified_entry['normalized_degree'] = self._normalize_degree(degree)
            
            # Update metrics
            if degree_category not in self.metrics.degree_classifications:
                self.metrics.degree_classifications[degree_category] = 0
            self.metrics.degree_classifications[degree_category] += 1
        else:
            validation_issues.append('missing_degree')
            classified_entry['degree_category'] = 'unknown'
            classified_entry['degree_level'] = 0
        
        # Validate and enrich institution
        institution = entry.get('institution', '')
        if institution:
            institution_type = self._classify_institution(institution)
            institution_confidence = self.school_lexicon.get_school_confidence(institution)
            
            classified_entry['institution_type'] = institution_type
            classified_entry['institution_confidence'] = institution_confidence
            classified_entry['normalized_institution'] = self._normalize_institution(institution)
            
            if institution_confidence < 0.3:
                validation_issues.append('low_confidence_institution')
        else:
            validation_issues.append('missing_institution')
            classified_entry['institution_type'] = 'unknown'
            classified_entry['institution_confidence'] = 0.0
        
        # Classify field of study
        field = entry.get('field', '')
        if field:
            field_category = self._classify_field(field)
            classified_entry['field_category'] = field_category
            classified_entry['normalized_field'] = self._normalize_field(field)
        else:
            classified_entry['field_category'] = 'general'
            classified_entry['normalized_field'] = ''
        
        # Validate and normalize dates
        dates = entry.get('dates', '')
        if dates:
            start_date, end_date, is_ongoing = self._parse_education_dates(dates)
            
            if start_date:
                classified_entry['start_date'] = start_date
                classified_entry['end_date'] = end_date
                classified_entry['is_ongoing'] = is_ongoing
                classified_entry['duration_years'] = self._calculate_duration_years(start_date, end_date, is_ongoing)
                
                # Validate timeline logic
                if not self.date_parser.validate_date_range(start_date, end_date):
                    validation_issues.append('invalid_date_range')
            else:
                validation_issues.append('unparseable_dates')
        else:
            validation_issues.append('missing_dates')
        
        # Process additional information
        additional_info = entry.get('additional_info', [])
        if additional_info:
            classified_entry['achievements'] = self._extract_achievements(additional_info)
            classified_entry['specializations'] = self._extract_specializations(additional_info)
        
        # Calculate academic quality score
        classified_entry['academic_score'] = self._calculate_academic_score(classified_entry)
        classified_entry['validation_issues'] = validation_issues
        
        # Validation: reject if too many critical issues
        critical_issues = ['missing_degree', 'missing_institution', 'missing_dates']
        critical_count = sum(1 for issue in validation_issues if issue in critical_issues)
        
        if critical_count >= 2:  # Max 1 critical issue allowed
            logger.debug(f"EDUCATION_PARSER: entry_rejected | "
                        f"degree='{classified_entry.get('normalized_degree', '')[:20]}...' "
                        f"critical_issues={critical_count}")
            self.metrics.validation_failures.extend(validation_issues)
            return None
        
        logger.debug(f"EDUCATION_PARSER: entry_classified | "
                    f"degree='{classified_entry.get('normalized_degree', '')[:20]}...' "
                    f"category={classified_entry.get('degree_category', 'unknown')} "
                    f"level={classified_entry.get('degree_level', 0)}")
        
        return classified_entry
    
    def _classify_degree(self, degree: str) -> Tuple[str, int]:
        """Classify degree into category and level."""
        degree_lower = degree.lower()
        
        for category, patterns in self.degree_patterns.items():
            for pattern in patterns:
                if re.search(pattern, degree_lower):
                    # Get level based on French system
                    level = self._get_degree_level(degree_lower)
                    return category, level
        
        return 'unknown', 0
    
    def _get_degree_level(self, degree: str) -> int:
        """Get degree level in French Bac+X system."""
        # Check for explicit Bac+X mentions
        bac_match = re.search(r'bac\s*\+?\s*(\d+)', degree)
        if bac_match:
            return int(bac_match.group(1))
        
        # Check predefined levels
        for degree_name, level in self.french_degree_levels.items():
            if degree_name in degree:
                return level
        
        return 0  # Unknown level
    
    def _classify_institution(self, institution: str) -> str:
        """Classify institution type."""
        institution_lower = institution.lower()
        
        for inst_type, patterns in self.institution_patterns.items():
            for pattern in patterns:
                if re.search(pattern, institution_lower):
                    return inst_type
        
        return 'unknown'
    
    def _classify_field(self, field: str) -> str:
        """Classify field of study."""
        field_lower = field.lower()
        
        for field_category, patterns in self.field_patterns.items():
            for pattern in patterns:
                if re.search(pattern, field_lower):
                    return field_category
        
        return 'general'
    
    def _normalize_degree(self, degree: str) -> str:
        """Normalize degree name."""
        if not degree:
            return ''
        
        normalized = degree.strip()
        normalized = re.sub(r'\\s+', ' ', normalized)
        return normalized[:100]  # Limit length
    
    def _normalize_institution(self, institution: str) -> str:
        """Normalize institution name."""
        if not institution:
            return ''
        
        normalized = institution.strip()
        normalized = re.sub(r'\\s+', ' ', normalized)
        return normalized[:100]  # Limit length
    
    def _normalize_field(self, field: str) -> str:
        """Normalize field of study."""
        if not field:
            return ''
        
        normalized = field.strip()
        normalized = re.sub(r'\\s+', ' ', normalized)
        return normalized[:100]  # Limit length
    
    def _parse_education_dates(self, date_string: str) -> Tuple[Optional[date], Optional[date], bool]:
        """Parse education dates."""
        return self.date_parser.parse_date_range(date_string)
    
    def _calculate_duration_years(self, start_date: Optional[date], end_date: Optional[date], is_ongoing: bool) -> Optional[float]:
        """Calculate education duration in years."""
        if not start_date:
            return None
        
        if is_ongoing:
            end_date = date.today()
        elif not end_date:
            return None
        
        years_diff = end_date.year - start_date.year
        months_diff = end_date.month - start_date.month
        
        return years_diff + (months_diff / 12.0)
    
    def _extract_achievements(self, additional_info: List[str]) -> List[str]:
        """Extract academic achievements from additional info."""
        achievements = []
        
        achievement_patterns = [
            r'\b(?:mention|grade|distinction|honors)\b[^\n]{0,50}',
            r'\b(?:trÃ¨s\s+bien|bien|assez\s+bien|cum\s+laude)\b[^\n]{0,30}',
            r'\b\d+[.,]\d+/20\b',
            r'\b(?:first\s+class|second\s+class|distinction)\b'
        ]
        
        for info in additional_info:
            for pattern in achievement_patterns:
                matches = re.findall(pattern, info, re.IGNORECASE)
                achievements.extend(matches)
        
        return achievements
    
    def _extract_specializations(self, additional_info: List[str]) -> List[str]:
        """Extract specializations from additional info."""
        specializations = []
        
        spec_patterns = [
            r'(?:spécialisation|specialization|major)\s*[:.]?\s*([^\n,]{5,50})',
            r'(?:option|parcours|track)\s*[:.]?\s*([^\n,]{5,50})'
        ]
        
        for info in additional_info:
            for pattern in spec_patterns:
                matches = re.findall(pattern, info, re.IGNORECASE)
                specializations.extend([m.strip() for m in matches])
        
        return specializations
    
    def _calculate_academic_score(self, entry: Dict[str, Any]) -> float:
        """Calculate academic quality score."""
        score = 0.0
        
        # Degree level bonus (0-0.4)
        degree_level = entry.get('degree_level', 0)
        if degree_level > 0:
            score += min(degree_level * 0.05, 0.4)  # Max 0.4 for level 8 (PhD)
        
        # Institution confidence (0-0.3)
        inst_confidence = entry.get('institution_confidence', 0.0)
        score += inst_confidence * 0.3
        
        # Duration appropriateness (0-0.15)
        duration = entry.get('duration_years', 0.0)
        degree_category = entry.get('degree_category', 'unknown')
        
        expected_durations = {
            'vocational': 2.0,
            'undergraduate': 3.0,
            'graduate': 2.0,  # Master's
            'postgraduate': 3.0,  # PhD
            'business': 1.5  # MBA
        }
        
        expected = expected_durations.get(degree_category, 2.0)
        if duration and abs(duration - expected) <= 1.0:  # Within 1 year of expected
            score += 0.15
        
        # Achievements bonus (0-0.1)
        achievements = entry.get('achievements', [])
        if achievements:
            score += min(len(achievements) * 0.02, 0.1)
        
        # Specializations bonus (0-0.05)
        specializations = entry.get('specializations', [])
        if specializations:
            score += min(len(specializations) * 0.025, 0.05)
        
        return min(1.0, score)
    
    def _sort_by_timeline_and_level(self, entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Sort education entries by timeline and academic level."""
        def sort_key(entry):
            # Primary: start date (most recent first)
            start_date = entry.get('start_date')
            date_key = start_date.year if start_date else 0
            
            # Secondary: degree level (highest first)
            level_key = entry.get('degree_level', 0)
            
            return (-date_key, -level_key)
        
        return sorted(entries, key=sort_key)
    
        # get_metrics provided by ParserMetricsMixin

