"""
Enhanced organization rebinding system (org_sieve) with school lexicon and employment scoring.
Implements the nearest valid org detection and school-based demotion logic.
"""

import re
from typing import List, Dict, Any, Optional, Tuple
from ..config import EXPERIENCE_CONF, SCHOOL_TOKENS, EMPLOYMENT_KEYWORDS, ACTION_VERBS_FR
from ..logging.safe_logger import get_safe_logger, DEFAULT_PII_CONFIG
from .experience_filters import normalize_text_for_matching

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


class EmploymentScorer:
    """Scores employment context for organization validation."""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or EXPERIENCE_CONF
        self.employment_keywords = set(normalize_text_for_matching(kw) for kw in EMPLOYMENT_KEYWORDS)
        self.action_verbs = set(normalize_text_for_matching(verb) for verb in ACTION_VERBS_FR)
        
    def score_employment_context(self, text_lines: List[str], 
                                target_line_idx: int,
                                window: Optional[int] = None) -> Dict[str, Any]:
        """
        Score employment context around a target line.
        
        Args:
            text_lines: List of text lines
            target_line_idx: Target line index
            window: Scoring window size (default from config)
            
        Returns:
            Dict with score, matched keywords, and scoring details
        """
        if window is None:
            window = self.config["employment_score_window"]
            
        start_idx = max(0, target_line_idx - window)
        end_idx = min(len(text_lines), target_line_idx + window + 1)
        
        matched_keywords = []
        matched_verbs = []
        total_words = 0
        
        for i in range(start_idx, end_idx):
            if i >= len(text_lines):
                continue
                
            line = text_lines[i]
            normalized_line = normalize_text_for_matching(line)
            words = normalized_line.split()
            total_words += len(words)
            
            # Check employment keywords
            for keyword in self.employment_keywords:
                if keyword in normalized_line:
                    matched_keywords.append({
                        'keyword': keyword,
                        'line_idx': i,
                        'original_line': line.strip()
                    })
                    
            # Check action verbs
            for verb in self.action_verbs:
                if verb in normalized_line:
                    matched_verbs.append({
                        'verb': verb,
                        'line_idx': i,
                        'original_line': line.strip()
                    })
        
        # Calculate weighted score
        keyword_score = len(matched_keywords) * 0.3  # Employment keywords weighted higher
        verb_score = len(matched_verbs) * 0.2       # Action verbs weighted lower
        
        # Normalize by total words to avoid bias toward longer texts
        raw_score = (keyword_score + verb_score) / max(total_words, 1) * 100
        
        # Convert to 0-1 scale
        employment_score = min(raw_score, 1.0)
        
        logger.debug(f"EMPLOYMENT_SCORE: calculated | target_line={target_line_idx} "
                    f"score={employment_score:.3f} keywords={len(matched_keywords)} "
                    f"verbs={len(matched_verbs)} total_words={total_words}")
        
        return {
            'score': employment_score,
            'matched_keywords': matched_keywords,
            'matched_verbs': matched_verbs,
            'total_words': total_words,
            'window_analyzed': [start_idx, end_idx]
        }


# Organization detection patterns for French-first detection
ORG_PREFIXES = {
    # French academic/public institutions
    'université', 'université de', 'école', 'école de', 'institut', 'centre',
    'laboratoire', 'hôpital', 'chu', 'mairie', 'ville de', 'région',
    
    # Corporate/business
    'groupe', 'société', 'compagnie', 'entreprise', 'cabinet', 'bureau',
    'studio', 'agence', 'conseil', 'consulting',
}

LEGAL_SUFFIXES = {
    # French legal entities
    'sarl', 'sas', 'sasu', 'sa', 's.a.', 'eurl', 'sci', 'snc',
    
    # International legal entities  
    'ltd', 'inc', 'corp', 'llc', 'gmbh', 'ag', 'bv', 'ab',
    'co', 'company', 'corporation', 'limited', 'incorporated'
}


def is_org(text: str) -> bool:
    """
    Determine if text represents an organization name using French-first patterns.
    
    Combines:
    1. ORG lexicon/affixes (Université, École, Groupe, Ville de, Société, SARL/SAS/etc.)
    2. Casing heuristics (Title Case sequences)  
    3. Legal entity detection
    
    Args:
        text: Text to analyze for organization indicators
        
    Returns:
        True if text appears to be an organization name
    """
    if not text or len(text.strip()) < 3:
        return False
        
    text_lower = text.strip().lower()
    text_words = text_lower.split()
    
    # Check for explicit org prefixes
    for prefix in ORG_PREFIXES:
        if text_lower.startswith(prefix + ' ') or text_lower == prefix:
            return True
    
    # Check for legal suffixes
    for suffix in LEGAL_SUFFIXES:
        if text_lower.endswith(' ' + suffix) or text_lower == suffix:
            return True
        # Also check for suffixes with punctuation
        if text_lower.endswith('.' + suffix) or text_lower.endswith(',' + suffix):
            return True
    
    # Check for Title Case pattern (multiple capitalized words)
    words = text.split()
    if len(words) >= 2:
        capitalized_words = sum(1 for word in words if word and word[0].isupper())
        if capitalized_words >= 2 and capitalized_words / len(words) >= 0.6:
            return True
    
    # Check for organization keywords in text
    org_keywords = {'université', 'école', 'groupe', 'société', 'entreprise', 'cabinet', 
                   'compagnie', 'institut', 'centre', 'laboratoire', 'studio', 'agence'}
    
    if any(keyword in text_lower for keyword in org_keywords):
        return True
    
    return False


class SchoolLexicon:
    """Manages school/academic institution detection and validation."""
    
    def __init__(self):
        self.school_tokens = set(normalize_text_for_matching(token) for token in SCHOOL_TOKENS)
        
        # Additional patterns for school detection
        self.school_patterns = [
            r'\b(?:university|université)\b',
            r'\b(?:college|collège)\b', 
            r'\b(?:school|école|ecole)\b',
            r'\b(?:institute|institut)\b',
            r'\b(?:academy|académie|academie)\b',
            r'\b(?:faculty|faculté)\b'
        ]
        
    def is_school_organization(self, org_name: str) -> Tuple[bool, List[str]]:
        """
        Determine if organization name indicates a school/academic institution.
        
        Args:
            org_name: Organization name to check
            
        Returns:
            (is_school, matched_indicators)
        """
        if not org_name:
            return False, []
            
        normalized_org = normalize_text_for_matching(org_name)
        matched_indicators = []
        
        # Check token matches
        for token in self.school_tokens:
            if token in normalized_org:
                matched_indicators.append(f"token:{token}")
                
        # Check pattern matches
        for pattern in self.school_patterns:
            matches = re.findall(pattern, normalized_org, re.IGNORECASE)
            for match in matches:
                matched_indicators.append(f"pattern:{match}")
                
        is_school = len(matched_indicators) > 0
        
        if is_school:
            logger.debug(f"SCHOOL_LEXICON: school_detected | org='{org_name[:30]}...' "
                        f"indicators={matched_indicators}")
                        
        return is_school, matched_indicators
        
    def get_school_confidence(self, org_name: str) -> float:
        """Get confidence score that organization is a school (0-1)."""
        is_school, indicators = self.is_school_organization(org_name)
        if not is_school:
            return 0.0
            
        # Higher confidence for multiple indicators
        base_confidence = 0.7
        indicator_bonus = min(len(indicators) * 0.1, 0.25)
        
        return min(base_confidence + indicator_bonus, 1.0)


class OrgSieve:
    """Enhanced organization rebinding system with school detection and employment scoring."""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or EXPERIENCE_CONF
        self.employment_scorer = EmploymentScorer(config)
        self.school_lexicon = SchoolLexicon()
        
        self.rebind_attempts = 0
        self.rebind_successes = 0
        
    def find_nearest_valid_org(self, text_lines: List[str], 
                              target_line_idx: int,
                              entities: List[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """
        Find nearest valid organization that isn't flagged as a school.
        
        Args:
            text_lines: List of text lines
            target_line_idx: Target line index
            entities: Optional NER entities with line_idx
            
        Returns:
            Dict with organization details or None
        """
        max_distance = self.config["nearest_valid_org_max_distance"]
        
        candidates = []
        
        # Search in text lines using simple patterns
        for i in range(max(0, target_line_idx - max_distance), 
                      min(len(text_lines), target_line_idx + max_distance + 1)):
            if i >= len(text_lines):
                continue
                
            line = text_lines[i]
            
            # Simple organization indicators
            org_patterns = [
                r'(?:chez|at)\s+([^,\n]{3,50})',
                r'([^,\n]{3,50})\s+(?:company|corp|inc|ltd|sarl|sas)',
                r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*[-–]\s*(?:company|corp)'
            ]
            
            for pattern in org_patterns:
                matches = re.findall(pattern, line, re.IGNORECASE)
                for match in matches:
                    org_name = match.strip()
                    if len(org_name) >= 3:
                        distance = abs(i - target_line_idx)
                        candidates.append({
                            'org_name': org_name,
                            'line_idx': i,
                            'distance': distance,
                            'source': 'pattern',
                            'original_line': line.strip()
                        })
        
        # Add NER entities if available
        if entities:
            for entity in entities:
                if entity.get('label') != 'ORG':
                    continue
                    
                entity_line = entity.get('line_idx', -1)
                distance = abs(entity_line - target_line_idx)
                
                if distance <= max_distance:
                    candidates.append({
                        'org_name': entity.get('text', ''),
                        'line_idx': entity_line,
                        'distance': distance,
                        'source': 'ner',
                        'confidence': entity.get('confidence', 0.5)
                    })
        
        # Filter out school organizations and select best candidate
        valid_candidates = []
        
        for candidate in candidates:
            org_name = candidate['org_name']
            is_school, school_indicators = self.school_lexicon.is_school_organization(org_name)
            
            if not is_school:
                candidate['is_school'] = False
                candidate['school_confidence'] = 0.0
                valid_candidates.append(candidate)
            else:
                # Check employment context before completely discarding
                employment_result = self.employment_scorer.score_employment_context(
                    text_lines, candidate['line_idx']
                )
                
                employment_score = employment_result['score']
                threshold = self.config["employment_keyword_score_threshold"]
                
                if employment_score >= threshold:
                    # Keep despite school lexicon due to strong employment context
                    candidate['is_school'] = True
                    candidate['school_confidence'] = self.school_lexicon.get_school_confidence(org_name)
                    candidate['employment_override'] = True
                    candidate['employment_score'] = employment_score
                    valid_candidates.append(candidate)
                    
                    logger.info(f"ORG_SIEVE: employment_override | org='{org_name[:20]}...' "
                               f"employment_score={employment_score:.3f} threshold={threshold}")
                else:
                    logger.debug(f"ORG_SIEVE: school_filtered | org='{org_name[:20]}...' "
                                f"employment_score={employment_score:.3f} threshold={threshold}")
        
        if not valid_candidates:
            return None
            
        # Select closest valid organization
        valid_candidates.sort(key=lambda x: (x['distance'], -x.get('confidence', 0.5)))
        best_candidate = valid_candidates[0]
        
        logger.info(f"ORG_SIEVE: nearest_valid_found | org='{best_candidate['org_name'][:20]}...' "
                   f"distance={best_candidate['distance']} source={best_candidate['source']}")
                   
        return best_candidate
        
    def rebind_organization(self, experience: Dict[str, Any],
                           text_lines: List[str],
                           target_line_idx: int,
                           entities: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Attempt to rebind organization for experience with validation.
        
        Args:
            experience: Experience dictionary to rebind
            text_lines: List of text lines  
            target_line_idx: Target line index
            entities: Optional NER entities
            
        Returns:
            Dict with rebinding results and updated experience
        """
        self.rebind_attempts += 1
        
        original_org = experience.get('company', '')
        
        # Find alternative organization
        alt_org_result = self.find_nearest_valid_org(text_lines, target_line_idx, entities)
        
        if not alt_org_result:
            logger.debug(f"ORG_REBIND: no_alternative_found | original_org='{original_org[:20]}...' "
                        f"target_line={target_line_idx}")
            return {
                'success': False,
                'reason': 'no_alternative_found',
                'original_org': original_org,
                'new_org': None
            }
        
        new_org = alt_org_result['org_name']
        
        # Validate employment context for new organization
        employment_result = self.employment_scorer.score_employment_context(
            text_lines, alt_org_result['line_idx']
        )
        
        employment_score = employment_result['score']
        threshold = self.config["employment_keyword_score_threshold"]
        
        if employment_score < threshold and alt_org_result.get('is_school', False):
            logger.debug(f"ORG_REBIND: failed_employment_validation | "
                        f"new_org='{new_org[:20]}...' score={employment_score:.3f} "
                        f"threshold={threshold}")
            return {
                'success': False,
                'reason': 'failed_employment_validation',
                'original_org': original_org,
                'new_org': new_org,
                'employment_score': employment_score
            }
        
        # Successful rebind
        experience['company'] = new_org
        experience['org_rebind'] = {
            'original_org': original_org,
            'new_org': new_org,
            'distance': alt_org_result['distance'],
            'source': alt_org_result['source'],
            'employment_score': employment_score
        }
        
        self.rebind_successes += 1
        
        logger.info(f"ORG_REBIND: success | original='{original_org[:15]}...' "
                   f"new='{new_org[:15]}...' distance={alt_org_result['distance']} "
                   f"employment_score={employment_score:.3f}")
        
        return {
            'success': True,
            'reason': 'rebind_successful',
            'original_org': original_org,
            'new_org': new_org,
            'distance': alt_org_result['distance'],
            'employment_score': employment_score
        }
        
    def should_demote_for_school_org(self, experience: Dict[str, Any],
                                   text_lines: List[str],
                                   target_line_idx: int) -> Dict[str, Any]:
        """
        Determine if experience should be demoted due to school organization.
        
        Args:
            experience: Experience to evaluate
            text_lines: List of text lines
            target_line_idx: Target line index
            
        Returns:
            Dict with demotion decision and reasoning
        """
        company = experience.get('company', '')
        if not company:
            return {'should_demote': False, 'reason': 'no_company'}
            
        is_school, school_indicators = self.school_lexicon.is_school_organization(company)
        
        if not is_school:
            return {'should_demote': False, 'reason': 'not_school_org'}
            
        # Check employment context
        employment_result = self.employment_scorer.score_employment_context(
            text_lines, target_line_idx
        )
        
        employment_score = employment_result['score']
        threshold = self.config["employment_keyword_score_threshold"]
        
        should_demote = employment_score < threshold
        
        logger.info(f"SCHOOL_DEMOTE: evaluation | company='{company[:20]}...' "
                   f"is_school={is_school} employment_score={employment_score:.3f} "
                   f"threshold={threshold} should_demote={should_demote}")
        
        return {
            'should_demote': should_demote,
            'reason': 'school_org_low_employment_score' if should_demote else 'school_org_high_employment_score',
            'is_school': is_school,
            'school_indicators': school_indicators,
            'employment_score': employment_score,
            'employment_details': employment_result
        }
        
    def get_rebind_stats(self) -> Dict[str, Any]:
        """Get rebinding statistics."""
        success_rate = self.rebind_successes / self.rebind_attempts if self.rebind_attempts > 0 else 0.0
        
        return {
            'rebind_attempts': self.rebind_attempts,
            'rebind_successes': self.rebind_successes,
            'success_rate': success_rate
        }


# Global instance
org_sieve = OrgSieve()
