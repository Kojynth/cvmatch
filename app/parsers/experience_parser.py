from .metrics_mixin import ParserMetricsMixin
"""
Experience Parser - Enhanced experience section parsing with strict validation.

This parser implements:
- Strict validation and enriched entity linking  
- Role-responsibility pattern matching
- Date range validation and normalization
- Organization validation and enrichment
- Experience quality scoring and filtering
"""

import re
from typing import List, Dict, Any, Optional, Tuple
from datetime import date, datetime
from dataclasses import dataclass

from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG
from ..utils.fallback_date_parser import get_fallback_date_parser
from ..utils.org_sieve import OrgSieve

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


@dataclass
class ExperienceMetrics:
    """Metrics for experience parsing and validation."""
    entries_received: int = 0
    entries_processed: int = 0
    entries_validated: int = 0
    entries_rejected: int = 0
    validation_failures: List[str] = None
    org_rebind_attempts: int = 0
    org_rebind_successes: int = 0
    
    def __post_init__(self):
        if self.validation_failures is None:
            self.validation_failures = []


class ExperienceParser(ParserMetricsMixin):
    """
    Enhanced experience parser with strict validation and entity linking.
    
    Key features:
    - Role-responsibility pattern matching
    - Date validation and normalization
    - Organization validation and enrichment
    - Quality scoring and filtering
    """
    
    def __init__(self):
        self.logger = get_safe_logger(f"{__name__}.ExperienceParser", cfg=DEFAULT_PII_CONFIG)
        self.date_parser = get_fallback_date_parser()
        self.org_sieve = OrgSieve()
        self.metrics = ExperienceMetrics()
        
        # French role patterns with hierarchical levels
        self.role_patterns = {
            'executive': [
                r'\b(?:directeur|directrice|ceo|cto|cfo|coo|president|présidente?)\b',
                r'\b(?:responsable|manager|chef|head|lead)\b',
                r'\b(?:directeur\s+général|dg|directeur\s+régional)\b'
            ],
            'senior': [
                r'\b(?:senior|sr|principal|expert|spécialiste)\b',
                r'\b(?:architecte|architect|consultant|conseiller)\b',
                r'\b(?:chef\s+de\s+projet|project\s+manager|pm)\b'
            ],
            'intermediate': [
                r'\b(?:développeur|developer|dev|ingénieur|engineer)\b',
                r'\b(?:analyste|analyst|technicien|technician)\b',
                r'\b(?:coordinateur|coordinator|assistant)\b'
            ],
            'junior': [
                r'\b(?:junior|jr|stagiaire|intern|apprenti)\b',
                r'\b(?:assistant|aide|support|débutant)\b'
            ]
        }
        
        # Responsibility action verbs (French)
        self.action_verbs_fr = [
            'développé', 'créé', 'conçu', 'géré', 'dirigé', 'coordonné',
            'implémenté', 'réalisé', 'maintenu', 'optimisé', 'superviser',
            'analyser', 'planifier', 'organiser', 'former', 'encadrer',
            'collaborer', 'participer', 'contribuer', 'améliorer'
        ]
        
        # Responsibility indicators
        self.responsibility_patterns = [
            r'(?:responsabilités?|missions?|tâches?|activités?)\s*[:.-]',
            r'(?:en\s+charge\s+de|chargée?\s+de|responsable\s+de)',
            r'(?:missions?\s+principales?|principales?\s+missions?)',
            r'(?:' + '|'.join(self.action_verbs_fr) + r')\s+\w+'
        ]
        
        # Date range patterns
        self.date_range_patterns = [
            r'(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})\s*[-–—]\s*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})',
            r'(\d{1,2}[/\-\.]\d{4})\s*[-–—]\s*(\d{1,2}[/\-\.]\d{4})',
            r'([a-zA-Zàâäçéèêëïîôùûüÿ\.]+\s+\d{4})\s*[-–—]\s*([a-zA-Zàâäçéèêëïîôùûüÿ\.]+\s+\d{4})',
            r'(\d{4})\s*[-–—]\s*(\d{4})',
            r'(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})\s*[-–—]\s*(présent|actuel|à ce jour)',
            r'(\d{1,2}[/\-\.]\d{4})\s*[-–—]\s*(présent|actuel|à ce jour)'
        ]
        
    def parse_experience_section(self, lines: List[str], start_idx: int = 0, end_idx: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Parse experience section with strict validation.
        
        Args:
            lines: Lines of text to parse
            start_idx: Start index in original document
            end_idx: End index in original document
            
        Returns:
            List of validated experience entries
        """
        self.metrics = ExperienceMetrics()
        self.metrics.entries_received = len(lines)
        
        if end_idx is None:
            end_idx = start_idx + len(lines)
        
        logger.info(f"EXPERIENCE_PARSER: parse_start | lines={len(lines)} range=({start_idx}-{end_idx})")
        
        if not lines:
            logger.info("EXPERIENCE_PARSER: empty_lines | skipping parsing")
            return []
        
        # Extract raw experience entries
        raw_entries = self._extract_raw_entries(lines)
        self.metrics.entries_processed = len(raw_entries)
        
        # Validate and enrich entries
        validated_entries = []
        for entry in raw_entries:
            validated_entry = self._validate_and_enrich_entry(entry, lines, start_idx)
            if validated_entry:
                validated_entries.append(validated_entry)
                self.metrics.entries_validated += 1
            else:
                self.metrics.entries_rejected += 1
        
        # Final quality filtering
        final_entries = self._filter_by_quality(validated_entries)
        
        logger.info(f"EXPERIENCE_PARSER: parse_complete | "
                   f"processed={self.metrics.entries_processed} "
                   f"validated={self.metrics.entries_validated} "
                   f"rejected={self.metrics.entries_rejected} "
                   f"final={len(final_entries)}")
        
        return final_entries
    
    def _extract_raw_entries(self, lines: List[str]) -> List[Dict[str, Any]]:
        """
        Extract raw experience entries from lines.
        
        Args:
            lines: Lines to extract from
            
        Returns:
            List of raw experience entries
        """
        entries = []
        current_entry = None
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            
            # Detect new experience entry
            if self._is_experience_header(line):
                # Save previous entry
                if current_entry:
                    entries.append(current_entry)
                
                # Start new entry
                current_entry = {
                    'line_idx': i,
                    'raw_lines': [line],
                    'title': self._extract_title_from_header(line),
                    'company': self._extract_company_from_header(line),
                    'date_range': self._extract_dates_from_header(line),
                    'responsibilities': []
                }
            elif current_entry:
                # Add content to current entry
                current_entry['raw_lines'].append(line)
                
                # Check for responsibilities
                if self._is_responsibility_line(line):
                    current_entry['responsibilities'].append(line)
                
                # Check for additional dates/company info
                if not current_entry['date_range']:
                    date_match = self._extract_dates_from_line(line)
                    if date_match:
                        current_entry['date_range'] = date_match
                
                if not current_entry['company']:
                    company_match = self._extract_company_from_line(line)
                    if company_match:
                        current_entry['company'] = company_match
        
        # Don't forget the last entry
        if current_entry:
            entries.append(current_entry)
        
        logger.debug(f"EXPERIENCE_PARSER: extracted {len(entries)} raw entries")
        return entries
    
    def _is_experience_header(self, line: str) -> bool:
        """Check if line is an experience entry header."""
        line_lower = line.lower()
        
        # Check for role patterns
        for level, patterns in self.role_patterns.items():
            for pattern in patterns:
                if re.search(pattern, line_lower, re.IGNORECASE):
                    return True
        
        # Check for date patterns indicating experience
        for pattern in self.date_range_patterns:
            if re.search(pattern, line):
                return True
        
        # Check for company indicators
        company_indicators = [r'\bchez\b', r'\bat\b', r'-\s*[A-Z][a-z]+', r'\b(?:société|company|corp|inc|ltd|sarl|sas)\b']
        for indicator in company_indicators:
            if re.search(indicator, line, re.IGNORECASE):
                return True
        
        return False
    
    def _is_responsibility_line(self, line: str) -> bool:
        """Check if line contains responsibility information."""
        line_lower = line.lower()
        
        # Check responsibility patterns
        for pattern in self.responsibility_patterns:
            if re.search(pattern, line_lower):
                return True
        
        # Check for bullet points or list indicators
        if re.match(r'^\s*[-•*▪◦]\s+', line):
            return True
        
        # Check for action verbs
        for verb in self.action_verbs_fr:
            if verb in line_lower:
                return True
        
        return False
    
    def _extract_title_from_header(self, line: str) -> Optional[str]:
        """Extract job title from header line."""
        # Try to extract title before company/date information
        title_patterns = [
            r'^([^–—-]+)(?:\s*[-–—]\s*)',  # Title before dash
            r'^([^,]+)(?:\s*,\s*)',        # Title before comma
            r'^([^\(]+)(?:\s*\()',         # Title before parentheses
        ]
        
        for pattern in title_patterns:
            match = re.search(pattern, line)
            if match:
                title = match.group(1).strip()
                if len(title) > 3:  # Reasonable length
                    return title
        
        # Fallback: use first part of line
        words = line.split()
        if len(words) >= 2:
            return ' '.join(words[:min(5, len(words))])  # Max 5 words
        
        return None
    
    def _extract_company_from_header(self, line: str) -> Optional[str]:
        """Extract company name from header line."""
        company_patterns = [
            r'chez\s+([^,\-–—\(]+)',       # "chez Company"
            r'at\s+([^,\-–—\(]+)',         # "at Company" 
            r'[-–—]\s*([^,\(]+?)(?:\s*[-–—,\(]|$)',  # After dash
            r',\s*([^,\(]+?)(?:\s*[,\(]|$)',         # After comma
        ]
        
        for pattern in company_patterns:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                company = match.group(1).strip()
                if len(company) > 2:  # Reasonable length
                    return company
        
        return None
    
    def _extract_company_from_line(self, line: str) -> Optional[str]:
        """Extract company name from any line."""
        return self._extract_company_from_header(line)
    
    def _extract_dates_from_header(self, line: str) -> Optional[str]:
        """Extract date range from header line."""
        return self._extract_dates_from_line(line)
    
    def _extract_dates_from_line(self, line: str) -> Optional[str]:
        """Extract date range from any line."""
        for pattern in self.date_range_patterns:
            match = re.search(pattern, line)
            if match:
                return match.group(0)
        
        return None
    
    def _validate_and_enrich_entry(self, entry: Dict[str, Any], all_lines: List[str], start_idx: int) -> Optional[Dict[str, Any]]:
        """
        Validate and enrich a single experience entry.
        
        Args:
            entry: Raw entry to validate
            all_lines: All lines from the section
            start_idx: Start index offset
            
        Returns:
            Enriched and validated entry or None if invalid
        """
        enriched_entry = entry.copy()
        validation_issues = []
        
        # Validate and enrich title
        title = entry.get('title')
        if not title or len(title.strip()) < 3:
            validation_issues.append("invalid_title")
            enriched_entry['title'] = 'Position non spécifiée'
        else:
            enriched_entry['title'] = self._normalize_title(title)
            enriched_entry['title_level'] = self._classify_title_level(title)
        
        # Validate and enrich company
        company = entry.get('company')
        if not company or len(company.strip()) < 2:
            # Try organization rebinding
            line_idx = entry.get('line_idx', 0)
            target_line_idx = start_idx + line_idx
            
            rebind_result = self.org_sieve.rebind_organization(
                enriched_entry, all_lines, target_line_idx
            )
            
            self.metrics.org_rebind_attempts += 1
            if rebind_result.get('success'):
                self.metrics.org_rebind_successes += 1
                enriched_entry['company'] = rebind_result['new_org']
                enriched_entry['org_rebind_info'] = rebind_result
            else:
                validation_issues.append("missing_company")
                enriched_entry['company'] = 'Organisation non spécifiée'
        else:
            # Validate existing company
            should_reject, reason = self.org_sieve.school_lexicon.should_reject_as_organization(company)
            if should_reject:
                validation_issues.append(f"invalid_org_{reason}")
                # Try rebinding
                line_idx = entry.get('line_idx', 0)
                target_line_idx = start_idx + line_idx
                
                rebind_result = self.org_sieve.rebind_organization(
                    enriched_entry, all_lines, target_line_idx
                )
                
                self.metrics.org_rebind_attempts += 1
                if rebind_result.get('success'):
                    self.metrics.org_rebind_successes += 1
                    enriched_entry['company'] = rebind_result['new_org']
                    enriched_entry['org_rebind_info'] = rebind_result
            else:
                enriched_entry['company'] = self._normalize_company(company)
        
        # Validate and enrich dates
        date_range = entry.get('date_range')
        if date_range:
            start_date, end_date, has_present = self.date_parser.parse_date_range(date_range)
            
            if start_date or has_present:
                enriched_entry['start_date'] = start_date
                enriched_entry['end_date'] = end_date
                enriched_entry['is_current'] = has_present
                enriched_entry['duration_months'] = self._calculate_duration_months(start_date, end_date, has_present)
                
                # Validate date logic
                if not self.date_parser.validate_date_range(start_date, end_date):
                    validation_issues.append("invalid_date_range")
            else:
                validation_issues.append("unparseable_dates")
        else:
            validation_issues.append("missing_dates")
        
        # Enrich responsibilities
        responsibilities = entry.get('responsibilities', [])
        if responsibilities:
            enriched_entry['responsibilities'] = self._normalize_responsibilities(responsibilities)
            enriched_entry['responsibility_count'] = len(responsibilities)
        else:
            enriched_entry['responsibilities'] = []
            enriched_entry['responsibility_count'] = 0
            validation_issues.append("no_responsibilities")
        
        # Calculate quality score
        enriched_entry['quality_score'] = self._calculate_quality_score(enriched_entry)
        enriched_entry['validation_issues'] = validation_issues
        
        # Strict validation: reject if too many critical issues
        critical_issues = ['invalid_title', 'missing_company', 'missing_dates', 'invalid_date_range']
        critical_count = sum(1 for issue in validation_issues if any(critical in issue for critical in critical_issues))
        
        if critical_count >= 2:  # Max 1 critical issue allowed
            logger.debug(f"EXPERIENCE_PARSER: entry_rejected | title='{enriched_entry.get('title', '')[:20]}...' "
                        f"critical_issues={critical_count} issues={validation_issues[:3]}")
            self.metrics.validation_failures.extend(validation_issues)
            return None
        
        logger.debug(f"EXPERIENCE_PARSER: entry_validated | title='{enriched_entry.get('title', '')[:20]}...' "
                    f"company='{enriched_entry.get('company', '')[:20]}...' "
                    f"quality={enriched_entry['quality_score']:.2f}")
        
        return enriched_entry
    
    def _normalize_title(self, title: str) -> str:
        """Normalize job title."""
        if not title:
            return ''
        
        # Clean up title
        normalized = title.strip()
        normalized = re.sub(r'\s+', ' ', normalized)
        normalized = re.sub(r'[^\w\s\-\.]', '', normalized)
        
        # Capitalize appropriately
        if normalized.islower():
            normalized = normalized.title()
        
        return normalized[:100]  # Limit length
    
    def _classify_title_level(self, title: str) -> str:
        """Classify job title into level categories."""
        title_lower = title.lower()
        
        for level, patterns in self.role_patterns.items():
            for pattern in patterns:
                if re.search(pattern, title_lower):
                    return level
        
        return 'intermediate'  # Default
    
    def _normalize_company(self, company: str) -> str:
        """Normalize company name."""
        if not company:
            return ''
        
        # Clean up company name
        normalized = company.strip()
        normalized = re.sub(r'\s+', ' ', normalized)
        
        return normalized[:100]  # Limit length
    
    def _normalize_responsibilities(self, responsibilities: List[str]) -> List[str]:
        """Normalize responsibility entries."""
        normalized = []
        
        for resp in responsibilities:
            if not resp or len(resp.strip()) < 5:
                continue
            
            clean_resp = resp.strip()
            # Remove bullet points
            clean_resp = re.sub(r'^\s*[-•*▪◦]\s*', '', clean_resp)
            # Normalize whitespace
            clean_resp = re.sub(r'\s+', ' ', clean_resp)
            
            if len(clean_resp) >= 10:  # Min meaningful length
                normalized.append(clean_resp[:500])  # Limit length
        
        return normalized
    
    def _calculate_duration_months(self, start_date: Optional[date], end_date: Optional[date], is_current: bool) -> Optional[int]:
        """Calculate experience duration in months."""
        if not start_date:
            return None
        
        if is_current:
            end_date = date.today()
        elif not end_date:
            return None
        
        # Calculate months difference
        years_diff = end_date.year - start_date.year
        months_diff = end_date.month - start_date.month
        
        total_months = years_diff * 12 + months_diff
        
        return max(1, total_months)  # At least 1 month
    
    def _calculate_quality_score(self, entry: Dict[str, Any]) -> float:
        """Calculate quality score for experience entry."""
        score = 0.0
        
        # Title quality (0-0.3)
        title = entry.get('title', '')
        if title and len(title) > 5:
            score += 0.15
            if entry.get('title_level') in ['executive', 'senior']:
                score += 0.15
        
        # Company quality (0-0.3)
        company = entry.get('company', '')
        if company and len(company) > 3:
            score += 0.15
            if not entry.get('org_rebind_info'):  # Original company was valid
                score += 0.15
        
        # Date quality (0-0.2)
        if entry.get('start_date'):
            score += 0.1
            if entry.get('end_date') or entry.get('is_current'):
                score += 0.1
        
        # Duration bonus (0-0.1)
        duration = entry.get('duration_months', 0)
        if duration >= 6:  # At least 6 months
            score += 0.05
            if duration >= 24:  # At least 2 years
                score += 0.05
        
        # Responsibilities quality (0-0.1)
        resp_count = entry.get('responsibility_count', 0)
        if resp_count > 0:
            score += 0.05
            if resp_count >= 3:
                score += 0.05
        
        return min(1.0, score)
    
    def _filter_by_quality(self, entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter entries by quality threshold."""
        quality_threshold = 0.4  # Minimum quality score
        
        filtered = []
        for entry in entries:
            quality_score = entry.get('quality_score', 0.0)
            if quality_score >= quality_threshold:
                filtered.append(entry)
            else:
                logger.debug(f"EXPERIENCE_PARSER: entry_filtered_quality | "
                           f"title='{entry.get('title', '')[:20]}...' "
                           f"quality={quality_score:.2f} threshold={quality_threshold}")
        
        return filtered
    
        # get_metrics provided by ParserMetricsMixin

