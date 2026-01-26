"""
Organization Classifier - Lightweight classification for school vs business vs exam entities.

Provides organization type detection to prevent misclassification of educational 
institutions as business employers and route certifications properly.
"""

import re
import unicodedata
from typing import Dict, Any, Optional, List, Tuple
from enum import Enum

from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


class OrgType(Enum):
    """Organization types for classification."""
    SCHOOL = "school"
    BUSINESS = "business"
    EXAM = "exam"
    GOVERNMENT = "government"
    UNKNOWN = "unknown"


class OrganizationClassifier:
    """Lightweight classifier for organization types."""
    
    def __init__(self):
        self.logger = get_safe_logger(f"{__name__}.OrganizationClassifier", cfg=DEFAULT_PII_CONFIG)
        
        # School patterns (French + English)
        self.school_patterns = [
            # French educational institutions
            r'\b(?:lyc[ée]e|lycee)\b',
            r'\b(?:[ée]cole|ecole)\b',
            r'\b(?:universit[ée]|universite)\b',
            r'\b(?:institut|centre de formation)\b',
            r'\b(?:facult[ée]|faculte)\b',
            r'\b(?:iut|insa|ut|ens|ensi)\b',
            r'\b(?:grande?\s+[ée]cole|business\s+school)\b',
            r'\b(?:coll[èe]ge|campus)\b',
            
            # English educational institutions  
            r'\b(?:university|college|school|institute|academy)\b',
            r'\b(?:polytechnic|tech|technological)\b',
            r'\b(?:faculty|department|campus)\b',
            
            # Educational degree contexts
            r'\b(?:bachelor|master|phd|doctorate|degree|diploma)\b',
            r'\b(?:licence|bts|dut|but|mba|cap|bac)\b',
        ]
        
        # Exam/certification patterns
        self.exam_patterns = [
            # Language exams
            r'\b(?:toefl|toeic|ielts|bulats)\b',
            r'\b(?:cambridge\s+english)\b',
            r'\b(?:cambridge)\s+(?:b[12]|c[12]|first|advanced|proficiency)\b',
            r'\b(?:delf|dalf|tcf|tef)\b',
            r'\b(?:dele|siele|ccse)\b',
            r'\b(?:goethe|testdaf|dsh|telc)\b',
            r'\b(?:hsk|jlpt)\b',
            
            # IT certifications
            r'\b(?:aws|amazon\s+web\s+services)\s+certified\b',
            r'\b(?:azure|microsoft)\s+certified\b',
            r'\b(?:google\s+cloud|gcp)\s+certified\b',
            r'\b(?:cisco|ccna|ccnp|ccie)\b',
            r'\b(?:comptia|security\+|network\+|a\+)\b',
            r'\b(?:pmp|prince2|itil)\b',
            r'\b(?:six\s+sigma|lean)\b',
        ]
        
        # Business indicators
        self.business_patterns = [
            # Company types
            r'\b(?:sa|sas|sarl|eurl|sci)\b',
            r'\b(?:inc|corp|llc|ltd|plc)\b',
            r'\b(?:gmbh|ag|kg|ug)\b',
            r'\b(?:société|company|enterprise|corporation)\b',
            r'\b(?:consulting|conseil|services)\b',
            r'\b(?:tech|technologies|systems|solutions)\b',
            r'\b(?:group|groupe|holding)\b',
            
            # Business contexts
            r'\b(?:startup|start-up)\b',
            r'\b(?:cabinet|bureau|agence)\b',
            r'\b(?:laboratoire|research|r&d)\b',
        ]
        
        # Government/public sector
        self.government_patterns = [
            r'\b(?:mairie|pr[ée]fecture|conseil\s+(?:général|régional))\b',
            r'\b(?:minist[èe]re|administration|service\s+public)\b',
            r'\b(?:chu|h[ôo]pital|clinique)\b',
            r'\b(?:cnrs|inra|inserm|cea)\b',
            r'\b(?:government|ministry|department|agency)\b',
        ]
        
        # Compile patterns for performance
        self._compile_patterns()
    
    def _compile_patterns(self):
        """Compile regex patterns for better performance."""
        self.school_regex = [re.compile(p, re.IGNORECASE) for p in self.school_patterns]
        self.exam_regex = [re.compile(p, re.IGNORECASE) for p in self.exam_patterns] 
        self.business_regex = [re.compile(p, re.IGNORECASE) for p in self.business_patterns]
        self.government_regex = [re.compile(p, re.IGNORECASE) for p in self.government_patterns]

    def _normalize_text(self, value: str) -> str:
        """Lowercase string and strip diacritics for robust regex matching."""
        if not value:
            return ""
        lowered = unicodedata.normalize("NFKD", value.lower().strip())
        return "".join(ch for ch in lowered if not unicodedata.combining(ch))
    
    def classify_organization(self, text: str, context_lines: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Classify organization type from text.
        
        Args:
            text: Text containing organization name/context
            context_lines: Optional surrounding lines for better context
            
        Returns:
            Dict with type, confidence, and reasoning
        """
        if not text or len(text.strip()) < 2:
            return {
                'type': OrgType.UNKNOWN.value,
                'confidence': 0.0,
                'reasoning': 'empty_text'
            }
        
        # Normalize text for matching
        normalized = self._normalize_text(text)
        
        # Include context if available
        full_text = normalized
        if context_lines:
            context_text = self._normalize_text(' '.join(context_lines))
            full_text = f"{context_text} {normalized}"
        
        # Score each category
        scores = {
            OrgType.EXAM: self._score_patterns(full_text, self.exam_regex),
            OrgType.SCHOOL: self._score_patterns(full_text, self.school_regex),
            OrgType.GOVERNMENT: self._score_patterns(full_text, self.government_regex),
            OrgType.BUSINESS: self._score_patterns(full_text, self.business_regex),
        }
        
        # Special handling for Cambridge disambiguation
        if 'cambridge' in normalized:
            scores = self._disambiguate_cambridge(full_text, scores)
        
        # Find best match
        best_type = max(scores.keys(), key=lambda k: scores[k])
        best_score = scores[best_type]
        
        # Apply minimum confidence threshold
        if best_score < 0.3:
            best_type = OrgType.UNKNOWN
            best_score = 0.0
        
        # Generate reasoning
        reasoning = self._generate_reasoning(normalized, best_type, scores)
        
        result = {
            'type': best_type.value,
            'confidence': min(1.0, best_score),
            'reasoning': reasoning,
            'all_scores': {k.value: v for k, v in scores.items()}
        }
        
        self.logger.debug(f"ORG_CLASSIFY: '{text[:30]}...' -> {best_type.value} (conf={best_score:.2f})")
        return result
    
    def _score_patterns(self, text: str, patterns: List[re.Pattern]) -> float:
        """Score text against a list of compiled patterns."""
        matches = 0
        total_weight = 0.0
        
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                matches += 1
                # Weight by pattern specificity (longer patterns = higher weight)
                pattern_weight = min(2.0, len(match.group(0)) / 10.0)
                total_weight += pattern_weight
        
        if matches == 0:
            return 0.0
        
        # Base confidence bonus for any match plus weight-based boost
        base_confidence = 0.4
        weighted_boost = total_weight / 2.0
        return min(1.0, base_confidence + weighted_boost)
    
    def _disambiguate_cambridge(self, text: str, scores: Dict[OrgType, float]) -> Dict[OrgType, float]:
        """Disambiguate Cambridge University vs Cambridge English exams."""
        
        # University indicators
        university_indicators = ['university', 'college', 'degree', 'bachelor', 'master', 'phd', 'campus']
        has_university_context = any(indicator in text for indicator in university_indicators)
        
        # Exam level indicators  
        exam_indicators = ['english', 'b1', 'b2', 'c1', 'c2', 'first', 'advanced', 'proficiency']
        has_exam_context = any(indicator in text for indicator in exam_indicators)
        
        if has_exam_context and not has_university_context:
            # Boost exam score, reduce school score
            scores[OrgType.EXAM] = min(1.0, scores[OrgType.EXAM] + 0.4)
            scores[OrgType.SCHOOL] = max(0.0, scores[OrgType.SCHOOL] - 0.3)
            self.logger.debug("CAMBRIDGE_DISAMBIG: exam context detected")
        
        elif has_university_context and not has_exam_context:
            # Boost school score, reduce exam score  
            scores[OrgType.SCHOOL] = min(1.0, scores[OrgType.SCHOOL] + 0.4)
            scores[OrgType.EXAM] = max(0.0, scores[OrgType.EXAM] - 0.3)
            self.logger.debug("CAMBRIDGE_DISAMBIG: university context detected")
        
        return scores
    
    def _generate_reasoning(self, text: str, org_type: OrgType, scores: Dict[OrgType, float]) -> str:
        """Generate human-readable reasoning for classification."""
        if org_type == OrgType.UNKNOWN:
            return "no_clear_indicators"
        
        # Find what triggered the classification
        triggers = []
        
        if org_type == OrgType.SCHOOL:
            if any(pattern.search(text) for pattern in self.school_regex[:5]):  # First 5 are most specific
                triggers.append("educational_institution")
            if any(word in text for word in ['université', 'école', 'lycée', 'college']):
                triggers.append("institution_name")
        
        elif org_type == OrgType.EXAM:
            if any(pattern.search(text) for pattern in self.exam_regex[:10]):  # Language exams
                triggers.append("certification_exam")
            if 'cambridge' in text and any(level in text for level in ['b1', 'b2', 'c1', 'c2']):
                triggers.append("cambridge_english_level")
        
        elif org_type == OrgType.BUSINESS:
            if any(pattern.search(text) for pattern in self.business_regex[:5]):
                triggers.append("company_indicator")
            if any(word in text for word in ['tech', 'consulting', 'services']):
                triggers.append("business_sector")
        
        return '+'.join(triggers) if triggers else f"{org_type.value}_generic"
    
    def is_school_organization(self, text: str, context_lines: Optional[List[str]] = None) -> bool:
        """Quick check if text represents a school organization."""
        result = self.classify_organization(text, context_lines)
        return result['type'] == OrgType.SCHOOL.value and result['confidence'] >= 0.5
    
    def is_exam_certification(self, text: str, context_lines: Optional[List[str]] = None) -> bool:
        """Quick check if text represents an exam/certification."""
        result = self.classify_organization(text, context_lines)
        return result['type'] == OrgType.EXAM.value and result['confidence'] >= 0.5
    
    def is_business_organization(self, text: str, context_lines: Optional[List[str]] = None) -> bool:
        """Quick check if text represents a business organization."""
        result = self.classify_organization(text, context_lines)
        return result['type'] == OrgType.BUSINESS.value and result['confidence'] >= 0.4


# Global classifier instance
_classifier_instance = None

def get_org_classifier() -> OrganizationClassifier:
    """Get singleton organization classifier instance."""
    global _classifier_instance
    if _classifier_instance is None:
        _classifier_instance = OrganizationClassifier()
    return _classifier_instance


# Convenience functions
def classify_organization(text: str, context_lines: Optional[List[str]] = None) -> Dict[str, Any]:
    """Classify organization type."""
    return get_org_classifier().classify_organization(text, context_lines)


def is_school_organization(text: str, context_lines: Optional[List[str]] = None) -> bool:
    """Check if text represents a school."""
    return get_org_classifier().is_school_organization(text, context_lines)


def is_exam_certification(text: str, context_lines: Optional[List[str]] = None) -> bool:
    """Check if text represents an exam/certification."""
    return get_org_classifier().is_exam_certification(text, context_lines)


def is_business_organization(text: str, context_lines: Optional[List[str]] = None) -> bool:
    """Check if text represents a business."""
    return get_org_classifier().is_business_organization(text, context_lines)
