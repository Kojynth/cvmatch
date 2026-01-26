"""
Enhanced education extractor with two-pass system and strict deduplication.
Implements keep_rate monitoring and strong signal requirements.

ENHANCED: Late merge pass with Levenshtein distance for education deduplication.
"""

import re
import hashlib
from typing import List, Dict, Any, Optional, Tuple, Set
from collections import defaultdict
from ..config import EXPERIENCE_CONF, SCHOOL_TOKENS
from ..logging.safe_logger import get_safe_logger, DEFAULT_PII_CONFIG
from .experience_filters import normalize_text_for_matching
from .certification_router import CertificationRouter

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)

def levenshtein_distance(s1: str, s2: str) -> int:
    """
    Calculate Levenshtein distance between two strings.

    Args:
        s1: First string
        s2: Second string

    Returns:
        Levenshtein distance
    """
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


def normalize_education_field(field: str) -> str:
    """
    Normalize education field for comparison (school or degree).

    Args:
        field: Field to normalize

    Returns:
        Normalized field
    """
    if not field:
        return ""

    # Apply text normalization
    normalized = normalize_text_for_matching(field)

    # Remove common noise words
    noise_words = [
        'de', 'du', 'des', 'la', 'le', 'les', 'university', 'école', 'ecole',
        'institut', 'université', 'universite', 'college', 'school'
    ]

    words = normalized.split()
    filtered_words = [word for word in words if word not in noise_words]

    return ' '.join(filtered_words) if filtered_words else normalized


class EducationExtractor:
    """Enhanced education extractor with two-pass system and deduplication."""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or EXPERIENCE_CONF
        self.certification_router = CertificationRouter()
        
        # Education-specific patterns
        self.degree_patterns = [
            r'\b(licence|bachelor|bac\+3)\b',
            r'\b(master|maîtrise|bac\+5|m[12])\b',
            r'\b(doctorat|phd|doctorate|bac\+8)\b',
            r'\b(dut|bts|iut)\b',
            r'\b(ingénieur|engineer|diplôme d\'ingénieur)\b',
            r'\b(mba|executive)\b',
            r'\b(cap|bep|bac|baccalauréat)\b'
        ]
        
        self.school_indicators = set(normalize_text_for_matching(token) for token in SCHOOL_TOKENS)
        
    def extract_education_two_pass(self, text_lines: List[str], 
                                  section_bounds: Tuple[int, int] = None,
                                  entities: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Extract education using two-pass system with keep_rate monitoring.
        
        Args:
            text_lines: List of text lines
            section_bounds: Optional (start_line, end_line) bounds 
            entities: Optional NER entities
            
        Returns:
            Dict with extraction results and metrics
        """
        if section_bounds:
            start_line, end_line = section_bounds
            section_lines = text_lines[start_line:end_line]
            line_offset = start_line
        else:
            section_lines = text_lines
            line_offset = 0
            
        # First pass - regular extraction
        first_pass_results = self._extract_education_pass1(section_lines, line_offset, entities)
        
        # Calculate keep rate
        total_lines_analyzed = len([line for line in section_lines if line.strip()])
        items_kept_pass1 = len(first_pass_results['items'])
        keep_rate = items_kept_pass1 / total_lines_analyzed if total_lines_analyzed > 0 else 0.0
        
        logger.info(f"EDUCATION_PASS1: completed | items_kept={items_kept_pass1} "
                   f"lines_analyzed={total_lines_analyzed} keep_rate={keep_rate:.3f}")
        
        # Determine if second pass is needed
        threshold = self.config["edu_keep_rate_threshold"]
        needs_second_pass = keep_rate < threshold
        
        if needs_second_pass:
            logger.info(f"EDUCATION_PASS2: triggered | keep_rate={keep_rate:.3f} < threshold={threshold}")
            second_pass_results = self._extract_education_pass2(section_lines, line_offset, entities)
            
            # Combine results
            combined_items = first_pass_results['items'] + second_pass_results['items']
            # First apply similarity-based merging, then regular deduplication
            merged_items = self._merge_education_items_by_similarity(combined_items)
            final_items = self._deduplicate_education_items(merged_items)
            
            pass2_metrics = {
                'second_pass_triggered': True,
                'pass2_items_added': len(second_pass_results['items']),
                'items_before_dedup': len(combined_items),
                'items_after_dedup': len(final_items)
            }
        else:
            # Apply similarity-based merging even for single pass
            merged_items = self._merge_education_items_by_similarity(first_pass_results['items'])
            final_items = self._deduplicate_education_items(merged_items)
            pass2_metrics = {
                'second_pass_triggered': False,
                'pass2_items_added': 0,
                'items_before_dedup': len(first_pass_results['items']),
                'items_after_dedup': len(final_items)
            }
        
        # Apply item count cap
        final_items = self._apply_education_cap(final_items, total_lines_analyzed)
        
        return {
            'items': final_items,
            'metrics': {
                'keep_rate_pass1': keep_rate,
                'total_lines_analyzed': total_lines_analyzed,
                **pass2_metrics,
                'final_item_count': len(final_items)
            }
        }
        
    def _extract_education_pass1(self, section_lines: List[str], 
                                line_offset: int,
                                entities: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """First pass - regular education extraction with basic filtering."""
        items = []
        
        for i, line in enumerate(section_lines):
            if not line.strip():
                continue
                
            # Skip certification lines
            if self.certification_router.should_exclude_from_experience_seeds(line, i, section_lines):
                continue
                
            education_item = self._extract_education_from_line(line, i + line_offset, section_lines, entities)
            
            if education_item:
                items.append(education_item)
                
        return {'items': items}
        
    def _extract_education_pass2(self, section_lines: List[str],
                                line_offset: int, 
                                entities: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Second pass - strict extraction requiring strong signals (date+org+degree)."""
        items = []
        strong_signal_threshold = self.config["edu_strong_signals_org_conf_min"]
        
        for i, line in enumerate(section_lines):
            if not line.strip():
                continue
                
            # Require strong signals: date + org + degree
            has_date = self._line_contains_date(line)
            has_org = self._line_contains_org(line, entities, i + line_offset)
            has_degree = self._line_contains_degree(line)
            
            strong_signals = sum([has_date, has_org, has_degree])
            
            if strong_signals >= 2:  # At least 2 of the 3 strong signals
                education_item = self._extract_education_from_line(line, i + line_offset, section_lines, entities)
                
                if education_item:
                    # Additional validation for pass2
                    org_confidence = education_item.get('org_confidence', 0.0)
                    
                    # Apply strict org confidence threshold for fallback acceptance
                    if org_confidence >= strong_signal_threshold or has_degree:
                        education_item['extraction_pass'] = 2
                        education_item['strong_signals'] = strong_signals
                        items.append(education_item)
                        
                        logger.debug(f"EDUCATION_PASS2: strong_signal_accept | line={i + line_offset} "
                                   f"signals={strong_signals} org_conf={org_confidence:.2f}")
                        
        return {'items': items}
        
    def _extract_education_from_line(self, line: str, line_idx: int, 
                                   context_lines: List[str] = None,
                                   entities: List[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Extract education item from a single line with context."""
        
        # Validate inputs and initialize safely
        if not line or not line.strip():
            return None
        
        if context_lines is None:
            context_lines = []
        
        if entities is None:
            entities = []
        
        # Basic education patterns (more specific)
        education_patterns = [
            # Degree - Institution pattern
            r'(?P<degree>[^-–—]{3,50})\s*[-–—]\s*(?P<institution>[^,\n]{3,100})',
            # Institution: Degree pattern  
            r'(?P<institution>[^:]{3,100}):\s*(?P<degree>[^,\n]{3,50})',
            # Degree, Institution pattern
            r'(?P<degree>[^,]{3,50}),\s*(?P<institution>[^,\n]{3,100})'
        ]
        
        # Initialize education item with safe defaults
        education_item = {
            'degree': '',
            'institution': '',
            'start_date': '',
            'end_date': '',
            'location': '',
            'line_idx': line_idx,
            'original_line': line.strip(),
            'extraction_method': 'pattern',
            'confidence': 0.3,  # Lower initial confidence
            'org_confidence': 0.0,  # Ensure this is initialized
            'validation_flags': []  # Track validation issues
        }
        
        # Try pattern matching
        for pattern in education_patterns:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                groups = match.groupdict()
                education_item['degree'] = groups.get('degree', '').strip()
                education_item['institution'] = groups.get('institution', '').strip()
                education_item['confidence'] = 0.7
                break
                
        # If no pattern match, try heuristic extraction with stricter validation
        if not education_item['degree'] and not education_item['institution']:
            words = line.split()
            
            # Require minimum word count for heuristic extraction
            if len(words) < 2:
                education_item['validation_flags'].append('insufficient_words_for_heuristic')
                # Only allow if it's a clear degree indicator
                if self._line_contains_degree(line.strip()):
                    education_item['degree'] = line.strip()
                    education_item['extraction_method'] = 'single_word_degree'
                    education_item['confidence'] = 0.2  # Very low confidence
                else:
                    return None  # Reject single words that aren't clear degrees
            
            elif len(words) >= 2:
                # Split into halves for analysis
                mid_point = len(words) // 2
                first_half = ' '.join(words[:mid_point]).strip()
                second_half = ' '.join(words[mid_point:]).strip()
                
                # Validate minimum length for each part
                if len(first_half) < 3 or len(second_half) < 3:
                    education_item['validation_flags'].append('parts_too_short')
                    # Fallback: treat entire line as degree if it has degree indicators
                    if self._line_contains_degree(line.strip()):
                        education_item['degree'] = line.strip()
                        education_item['extraction_method'] = 'full_line_degree'
                        education_item['confidence'] = 0.25
                    else:
                        return None
                else:
                    # Improved heuristic logic
                    first_has_degree = self._line_contains_degree(first_half)
                    second_has_org = self._line_contains_org(second_half, entities, line_idx)
                    first_has_org = self._line_contains_org(first_half, entities, line_idx)
                    second_has_degree = self._line_contains_degree(second_half)
                    
                    # Prioritize configurations
                    if first_has_degree and second_has_org:
                        education_item['degree'] = first_half
                        education_item['institution'] = second_half
                        education_item['extraction_method'] = 'heuristic_degree_org'
                        education_item['confidence'] = 0.6
                    elif first_has_org and second_has_degree:
                        education_item['degree'] = second_half
                        education_item['institution'] = first_half
                        education_item['extraction_method'] = 'heuristic_org_degree'
                        education_item['confidence'] = 0.6
                    elif first_has_degree:
                        education_item['degree'] = first_half
                        education_item['institution'] = second_half
                        education_item['extraction_method'] = 'heuristic_degree_fallback'
                        education_item['confidence'] = 0.4
                        education_item['validation_flags'].append('institution_not_validated')
                    elif second_has_org:
                        education_item['degree'] = first_half
                        education_item['institution'] = second_half
                        education_item['extraction_method'] = 'heuristic_org_fallback'
                        education_item['confidence'] = 0.4
                        education_item['validation_flags'].append('degree_not_validated')
                    else:
                        # No clear indicators - stricter rejection
                        education_item['validation_flags'].append('no_clear_indicators')
                        return None
                    
        # Extract dates from context
        dates = self._extract_dates_from_context(line, context_lines, line_idx)
        if dates:
            education_item['start_date'] = dates.get('start_date', '')
            education_item['end_date'] = dates.get('end_date', '')
            
        # Calculate organization confidence
        org_confidence = self._calculate_org_confidence(education_item['institution'], entities, line_idx)
        education_item['org_confidence'] = org_confidence
        
        # Apply tightened acceptance rules
        if not self._passes_acceptance_criteria(education_item):
            return None
            
        return education_item
    
    def _passes_acceptance_criteria(self, education_item: Dict[str, Any]) -> bool:
        """Apply tightened acceptance criteria for education items."""
        
        # Rule 1: Must have at least degree or institution
        if not education_item['degree'] and not education_item['institution']:
            logger.debug(f"EDUCATION_REJECT: no_degree_or_institution | line={education_item['line_idx']}")
            return False
        
        # Rule 2: Minimum content length requirements
        degree_len = len(education_item['degree'].strip())
        institution_len = len(education_item['institution'].strip())
        
        if degree_len > 0 and degree_len < 3:
            logger.debug(f"EDUCATION_REJECT: degree_too_short | degree='{education_item['degree']}' len={degree_len}")
            return False
            
        if institution_len > 0 and institution_len < 3:
            logger.debug(f"EDUCATION_REJECT: institution_too_short | institution='{education_item['institution']}' len={institution_len}")
            return False
        
        # Rule 3: Content quality checks
        degree = education_item['degree'].lower()
        institution = education_item['institution'].lower()
        
        # Reject pure garbage/non-educational content
        garbage_indicators = [
            'xxxx', '????', '----', '...', 'test', 'exemple', 'sample',
            'lorem', 'ipsum', 'placeholder', 'todo', 'fixme'
        ]
        
        for garbage in garbage_indicators:
            if garbage in degree or garbage in institution:
                logger.debug(f"EDUCATION_REJECT: garbage_content | content='{garbage}'")
                return False
        
        # Rule 4: Confidence threshold (stricter)
        min_confidence = 0.25
        if education_item['confidence'] < min_confidence:
            logger.debug(f"EDUCATION_REJECT: confidence_too_low | confidence={education_item['confidence']} min={min_confidence}")
            return False
        
        # Rule 5: Organization confidence for institution-heavy extractions
        if education_item['institution'] and len(education_item['institution']) > 10:
            min_org_confidence = 0.1  # Minimum organization confidence
            if education_item['org_confidence'] < min_org_confidence:
                # Only reject if degree is also weak
                if not education_item['degree'] or not self._line_contains_degree(education_item['degree']):
                    logger.debug(f"EDUCATION_REJECT: weak_org_confidence | org_conf={education_item['org_confidence']} min={min_org_confidence}")
                    return False
        
        # Rule 6: Check validation flags for critical issues
        critical_flags = ['no_clear_indicators']
        if any(flag in education_item.get('validation_flags', []) for flag in critical_flags):
            logger.debug(f"EDUCATION_REJECT: critical_validation_flags | flags={education_item['validation_flags']}")
            return False
        
        return True
        
    def _line_contains_date(self, line: str) -> bool:
        """Check if line contains date information."""
        date_patterns = [
            r'\b\d{4}\b',
            r'\b\d{1,2}/\d{4}\b',
            r'\b\d{1,2}/\d{1,2}/\d{4}\b',
            r'\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b',
            r'\b(?:janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\b'
        ]
        
        for pattern in date_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                return True
        return False
        
    def _line_contains_org(self, line: str, entities: List[Dict[str, Any]] = None, 
                          line_idx: int = -1) -> bool:
        """Check if line contains organization information."""
        # Check for school indicators
        normalized_line = normalize_text_for_matching(line)
        for indicator in self.school_indicators:
            if indicator in normalized_line:
                return True
                
        # Check NER entities
        if entities and line_idx >= 0:
            for entity in entities:
                if (entity.get('label') == 'ORG' and 
                    entity.get('line_idx') == line_idx):
                    return True
                    
        # Check for organization patterns
        org_patterns = [
            r'\b(?:university|université|college|school|institute|academy)\b',
            r'\b[A-Z][a-z]+\s+[A-Z][a-z]+\b'  # Capitalized names
        ]
        
        for pattern in org_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                return True
                
        return False
        
    def _line_contains_degree(self, line: str) -> bool:
        """Check if line contains degree information."""
        for pattern in self.degree_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                return True
        return False
        
    def _extract_dates_from_context(self, line: str, context_lines: List[str] = None,
                                   line_idx: int = -1) -> Dict[str, str]:
        """Extract date information from line and context."""
        dates = {'start_date': '', 'end_date': ''}
        
        # Date patterns for education
        date_range_patterns = [
            r'(\d{4})\s*[-–—]\s*(\d{4})',
            r'(\d{4})\s*[-–—]\s*(?:present|current|aujourd\'hui)',
            r'(\d{1,2}/\d{4})\s*[-–—]\s*(\d{1,2}/\d{4})'
        ]
        
        search_text = line
        if context_lines and line_idx >= 0:
            # Include adjacent lines for date search
            start_idx = max(0, line_idx - 1)
            end_idx = min(len(context_lines), line_idx + 2)
            search_text = ' '.join(context_lines[start_idx:end_idx])
            
        for pattern in date_range_patterns:
            match = re.search(pattern, search_text)
            if match:
                dates['start_date'] = match.group(1)
                if len(match.groups()) > 1:
                    dates['end_date'] = match.group(2)
                break
                
        return dates
        
    def _calculate_org_confidence(self, institution: str, entities: List[Dict[str, Any]] = None,
                                line_idx: int = -1) -> float:
        """Calculate confidence that institution is valid (enhanced with safety checks)."""
        if not institution or not institution.strip():
            return 0.0
        
        # Validate entities parameter safely
        if entities is None:
            entities = []
            
        institution_stripped = institution.strip()
        
        # Start with lower base confidence for stricter validation
        confidence = 0.3
        
        # Boost for school indicators
        normalized_institution = normalize_text_for_matching(institution_stripped)
        school_indicator_found = False
        
        for indicator in self.school_indicators:
            if indicator in normalized_institution:
                confidence += 0.3  # Stronger boost for school indicators
                school_indicator_found = True
                break
                
        # Boost for NER validation
        ner_validation_found = False
        if entities and line_idx >= 0:
            for entity in entities:
                entity_label = entity.get('label', '')
                entity_line_idx = entity.get('line_idx', -1)
                entity_text = entity.get('text', '')
                
                if (entity_label == 'ORG' and 
                    entity_line_idx == line_idx and
                    entity_text and  # Ensure entity text exists
                    normalize_text_for_matching(entity_text) in normalized_institution):
                    confidence += 0.4  # Strong boost for NER validation
                    ner_validation_found = True
                    break
        
        # Additional validation checks
        # Proper capitalization pattern (educational institutions often have proper names)
        if institution_stripped and len(institution_stripped) > 1:
            words = institution_stripped.split()
            capitalized_words = sum(1 for word in words if word and word[0].isupper())
            
            if len(words) > 0:
                cap_ratio = capitalized_words / len(words)
                if cap_ratio >= 0.5:  # At least half the words are capitalized
                    confidence += 0.2
        
        # Length-based validation (very short institutions are suspicious)
        if len(institution_stripped) < 5:
            confidence -= 0.2
        elif len(institution_stripped) > 100:  # Suspiciously long
            confidence -= 0.1
        
        # Check for common educational institution patterns
        edu_patterns = [
            r'\b(?:université|university|college|école|school|institute|institut|academy|académie)\b',
            r'\b(?:iut|but|dut|bts|master|licence|bachelor)\b'  # French educational terms
        ]
        
        for pattern in edu_patterns:
            if re.search(pattern, institution_stripped, re.IGNORECASE):
                confidence += 0.2
                break
        
        # Penalize if no validation method worked
        if not school_indicator_found and not ner_validation_found:
            confidence -= 0.1
        
        return max(0.0, min(confidence, 1.0))  # Ensure bounds [0, 1]
        
    def _merge_education_items_by_similarity(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        ENHANCED: Merge education items using Levenshtein distance ≤ 2 for normalization.

        Uses merge key: (school_norm, degree_norm, year_span) with edit distance tolerance.
        Prefers updating existing items over creating new ones.

        Args:
            items: List of education items to merge

        Returns:
            List of merged education items
        """
        if len(items) <= 1:
            return items

        merged_items = []
        processed_indices = set()

        for i, item in enumerate(items):
            if i in processed_indices:
                continue

            # Normalize current item for comparison
            current_school_norm = normalize_education_field(item.get('school', '') or item.get('institution', ''))
            current_degree_norm = normalize_education_field(item.get('degree', ''))
            current_year = self._extract_year_span(item)

            # Create merge key
            merge_key = (current_school_norm, current_degree_norm, current_year)

            # Find similar items to merge using Levenshtein distance
            candidates_to_merge = [i]

            for j, other_item in enumerate(items[i+1:], start=i+1):
                if j in processed_indices:
                    continue

                other_school_norm = normalize_education_field(other_item.get('school', '') or other_item.get('institution', ''))
                other_degree_norm = normalize_education_field(other_item.get('degree', ''))
                other_year = self._extract_year_span(other_item)

                # Calculate Levenshtein distances
                school_distance = levenshtein_distance(current_school_norm, other_school_norm)
                degree_distance = levenshtein_distance(current_degree_norm, other_degree_norm)
                year_match = (current_year == other_year) or (abs(current_year - other_year) <= 1)

                # Merge criteria: both school and degree distance ≤ 2, and year match
                if school_distance <= 2 and degree_distance <= 2 and year_match:
                    candidates_to_merge.append(j)
                    logger.debug(f"EDUCATION_MERGE: candidate_found | "
                               f"school_dist={school_distance} degree_dist={degree_distance} "
                               f"current_school='{current_school_norm[:20]}...' "
                               f"other_school='{other_school_norm[:20]}...' "
                               f"current_degree='{current_degree_norm[:20]}...' "
                               f"other_degree='{other_degree_norm[:20]}...'")

            # Mark all candidates as processed
            for idx in candidates_to_merge:
                processed_indices.add(idx)

            # Merge candidates (prefer the most complete item as base)
            if len(candidates_to_merge) > 1:
                merged_item = self._merge_education_candidates([items[idx] for idx in candidates_to_merge])
                logger.info(f"EDUCATION_MERGE: merged_items | count={len(candidates_to_merge)} "
                           f"school='{merged_item.get('school', '')[:20]}...' "
                           f"degree='{merged_item.get('degree', '')[:20]}...' "
                           f"year={self._extract_year_span(merged_item)}")
            else:
                merged_item = item

            merged_items.append(merged_item)

        logger.info(f"EDUCATION_MERGE: completed | original={len(items)} merged={len(merged_items)}")
        return merged_items

    def _extract_year_span(self, item: Dict[str, Any]) -> int:
        """Extract year span from education item."""
        year = item.get('graduation_year', 0) or item.get('end_date', '') or item.get('year', 0)

        if isinstance(year, str):
            year_match = re.search(r'(\d{4})', year)
            return int(year_match.group(1)) if year_match else 0

        return int(year) if year else 0

    def _merge_education_candidates(self, candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Merge multiple education candidates into one item.

        Prefers the most complete item and merges additional information.

        Args:
            candidates: List of candidate items to merge

        Returns:
            Merged education item
        """
        if not candidates:
            return {}

        if len(candidates) == 1:
            return candidates[0]

        # Score candidates by completeness
        scored_candidates = []
        for candidate in candidates:
            score = 0
            score += 2 if candidate.get('school') or candidate.get('institution') else 0
            score += 2 if candidate.get('degree') else 0
            score += 1 if candidate.get('graduation_year') or candidate.get('end_date') else 0
            score += 1 if candidate.get('start_date') else 0
            score += 1 if candidate.get('location') else 0
            score += len(candidate.get('description', '')) / 50  # Description length bonus

            scored_candidates.append((score, candidate))

        # Sort by score (highest first)
        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        base_item = scored_candidates[0][1].copy()

        # Merge additional information from other candidates
        for score, candidate in scored_candidates[1:]:
            for field in ['school', 'institution', 'degree', 'location', 'start_date', 'end_date', 'graduation_year']:
                if not base_item.get(field) and candidate.get(field):
                    base_item[field] = candidate[field]

            # Merge descriptions
            if candidate.get('description') and candidate['description'] not in base_item.get('description', ''):
                base_desc = base_item.get('description', '')
                additional_desc = candidate['description']
                base_item['description'] = f"{base_desc} {additional_desc}".strip()

        return base_item
    
    def _are_texts_similar(self, text1: str, text2: str, max_distance: int = 2) -> bool:
        """
        Check if two texts are similar using simple Levenshtein-like distance.
        
        Args:
            text1, text2: Texts to compare
            max_distance: Maximum allowed character distance
            
        Returns:
            True if texts are similar
        """
        if not text1 or not text2:
            return False
        
        # Exact match
        if text1 == text2:
            return True
        
        # Simple character distance approximation
        if len(text1) < 3 or len(text2) < 3:
            return text1 == text2
        
        # Check if one is substring of other (common case)
        if text1 in text2 or text2 in text1:
            return True
        
        # Simple character difference count
        min_len = min(len(text1), len(text2))
        max_len = max(len(text1), len(text2))
        
        if max_len - min_len > max_distance:
            return False
        
        # Count character differences in common prefix
        differences = 0
        for i in range(min_len):
            if text1[i] != text2[i]:
                differences += 1
                if differences > max_distance:
                    return False
        
        # Add remaining character difference
        differences += max_len - min_len
        
        return differences <= max_distance
    
    def _merge_similar_education_items(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Merge multiple similar education items into one consolidated item.
        
        Args:
            items: List of similar education items
            
        Returns:
            Consolidated education item
        """
        if not items:
            return {}
        
        if len(items) == 1:
            return items[0]
        
        # Use first item as base
        merged = items[0].copy()
        
        # Consolidate fields from all items
        all_schools = [item.get('school', '') for item in items if item.get('school')]
        all_degrees = [item.get('degree', '') for item in items if item.get('degree')]
        all_descriptions = [item.get('description', '') for item in items if item.get('description')]
        
        # Choose the most complete/longest values
        if all_schools:
            merged['school'] = max(all_schools, key=len)
        
        if all_degrees:
            merged['degree'] = max(all_degrees, key=len)
        
        # Merge descriptions
        if all_descriptions:
            unique_descriptions = list(dict.fromkeys(all_descriptions))  # Remove duplicates while preserving order
            merged['description'] = ' | '.join(unique_descriptions)
        
        # Take the most recent year
        years = []
        for item in items:
            year = item.get('graduation_year') or item.get('end_date', '')
            if isinstance(year, str):
                year_match = re.search(r'(\d{4})', year)
                if year_match:
                    years.append(int(year_match.group(1)))
            elif isinstance(year, int) and year > 0:
                years.append(year)
        
        if years:
            merged['graduation_year'] = max(years)
        
        # Add merge metadata
        merged['_merged_from'] = len(items)
        merged['_merge_source'] = 'education_similarity_dedup'
        
        return merged
    
    def _deduplicate_education_items(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Deduplicate education items by (school, degree, normalized dates)."""
        seen_hashes = set()
        deduplicated = []
        
        for item in items:
            # Create dedup key
            school = normalize_text_for_matching(item.get('institution', ''))
            degree = normalize_text_for_matching(item.get('degree', ''))
            start_date = self._normalize_date(item.get('start_date', ''))
            end_date = self._normalize_date(item.get('end_date', ''))
            
            # Create hash for deduplication
            dedup_key = f"{school}|{degree}|{start_date}|{end_date}"
            dedup_hash = hashlib.md5(dedup_key.encode()).hexdigest()
            
            if dedup_hash not in seen_hashes:
                seen_hashes.add(dedup_hash)
                item['dedup_key'] = dedup_key
                deduplicated.append(item)
            else:
                logger.debug(f"EDUCATION_DEDUP: duplicate_removed | dedup_key='{dedup_key[:50]}...'")
                
        logger.info(f"EDUCATION_DEDUP: summary | original={len(items)} deduplicated={len(deduplicated)}")
        
        return deduplicated
        
    def _normalize_date(self, date_str: str) -> str:
        """Normalize date string for deduplication."""
        if not date_str:
            return ''
            
        # Extract year for normalization
        year_match = re.search(r'\b(\d{4})\b', date_str)
        if year_match:
            return year_match.group(1)
            
        return date_str.strip().lower()
        
    def _apply_education_cap(self, items: List[Dict[str, Any]], 
                           total_lines: int) -> List[Dict[str, Any]]:
        """Apply cap on education items per 100 lines."""
        max_items_per_100_lines = self.config["edu_items_per_100_lines_max"]
        max_items = max(1, (total_lines * max_items_per_100_lines) // 100)
        
        if len(items) <= max_items:
            return items
            
        # Sort by confidence and keep top items
        items_sorted = sorted(items, key=lambda x: x.get('confidence', 0.0), reverse=True)
        capped_items = items_sorted[:max_items]
        
        logger.info(f"EDUCATION_CAP: applied | total_lines={total_lines} "
                   f"original_items={len(items)} max_allowed={max_items} "
                   f"final_items={len(capped_items)}")
        
        return capped_items
        
    def filter_credential_duplicates(self, education_items: List[Dict[str, Any]],
                                   certification_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter out education items that duplicate certifications."""
        if not certification_items:
            return education_items
            
        # Create set of canonical certification names
        cert_names = set()
        for cert in certification_items:
            canonical_name = normalize_text_for_matching(cert.get('name', ''))
            if canonical_name:
                cert_names.add(canonical_name)
                
        # Filter education items
        filtered_education = []
        
        for edu_item in education_items:
            degree = normalize_text_for_matching(edu_item.get('degree', ''))
            
            # Check if degree matches any certification
            is_duplicate_cert = False
            for cert_name in cert_names:
                if cert_name in degree or degree in cert_name:
                    is_duplicate_cert = True
                    logger.debug(f"EDUCATION_CERT_FILTER: duplicate_removed | degree='{degree}' "
                               f"matches_cert='{cert_name}'")
                    break
                    
            if not is_duplicate_cert:
                filtered_education.append(edu_item)
                
        logger.info(f"EDUCATION_CERT_FILTER: summary | original={len(education_items)} "
                   f"filtered={len(filtered_education)} cert_duplicates_removed={len(education_items) - len(filtered_education)}")
                   
        return filtered_education


# Global instance
education_extractor = EducationExtractor()
