"""
QA Guardrails - Anti-overdemption protection for extraction quality assurance.

Prevents aggressive demotions and misclassifications through intelligent quality gates
and composable filters that preserve legitimate content while filtering noise.
"""

import re
from typing import List, Dict, Any, Optional, Tuple, Set
from collections import defaultdict, Counter
from dataclasses import dataclass
from datetime import datetime

from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG
from ..utils.pii import validate_no_pii_leakage
from .experience_metrics import get_experience_metrics_tracker
from .org_classifier import classify_organization, OrgType

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


@dataclass
class QAMetrics:
    """Container for QA processing metrics."""
    items_reviewed: int = 0
    items_rescued: int = 0
    items_demoted: int = 0
    rescue_reasons: Dict[str, int] = None
    demotion_reasons: Dict[str, int] = None
    
    def __post_init__(self):
        if self.rescue_reasons is None:
            self.rescue_reasons = defaultdict(int)
        if self.demotion_reasons is None:
            self.demotion_reasons = defaultdict(int)


class QAGuardrail:
    """Intelligent QA guardrail to prevent over-demotions."""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.logger = get_safe_logger(f"{__name__}.QAGuardrail", cfg=DEFAULT_PII_CONFIG)
        self.metrics = QAMetrics()
        
        # Configuration thresholds
        self.min_rescue_confidence = self.config.get('min_rescue_confidence', 0.4)
        self.max_demotion_ratio = self.config.get('max_demotion_ratio', 0.3)  # Max 30% demotions
        self.diversity_protection_threshold = self.config.get('diversity_protection', 0.7)
        
        # Pattern allowlist for rescue operations
        self._init_rescue_patterns()
        
        # Track processing session
        self.session_id = f"qa_session_{int(datetime.now().timestamp())}"
        
    def _init_rescue_patterns(self):
        """Initialize patterns that should be rescued from demotion."""
        
        # Patterns that indicate legitimate professional experience
        self.professional_indicators = [
            r'\b(?:stage|stagiaire|intern|internship|apprenti|alternance)\b',
            r'\b(?:développeur|developer|engineer|ingénieur|analyst|consultant)\b', 
            r'\b(?:manager|chef|responsable|directeur|coordinator|lead|senior)\b',
            r'\b(?:assistant|technicien|specialist|designer|architect)\b',
            r'\b(?:project|projet|équipe|team|client|customer|mission)\b'
        ]
        
        # Companies/orgs that are clearly business (not education)
        self.business_indicators = [
            r'\b(?:startup|start-up|entreprise|company|corporation|inc|ltd)\b',
            r'\b(?:consulting|conseil|services|solutions|technologies)\b',
            r'\b(?:agency|agence|cabinet|bureau|laboratoire|research)\b',
            r'\b(?:group|groupe|holding|branch|filiale)\b'
        ]
        
        # Strong employment context indicators
        self.employment_context = [
            r'\b(?:contrat|contract|cdd|cdi|temps plein|full.time|part.time)\b',
            r'\b(?:salaire|salary|rémunération|benefits|avantages)\b',
            r'\b(?:équipe|team|collègues|colleagues|supervisor|manager)\b',
            r'\b(?:mission|project|objective|résultats|achievements)\b'
        ]
        
        # Compile patterns for performance
        self.professional_regex = [re.compile(p, re.IGNORECASE) for p in self.professional_indicators]
        self.business_regex = [re.compile(p, re.IGNORECASE) for p in self.business_indicators] 
        self.employment_regex = [re.compile(p, re.IGNORECASE) for p in self.employment_context]
    
    def should_rescue_experience(self, exp_item: Dict[str, Any], 
                               context_lines: List[str] = None, 
                               all_experiences: List[Dict[str, Any]] = None) -> Tuple[bool, str]:
        """
        Determine if an experience item should be rescued from demotion.
        
        Args:
            exp_item: Experience item to evaluate
            context_lines: Surrounding text lines for context analysis
            all_experiences: All experience items for diversity analysis
            
        Returns:
            (should_rescue, rescue_reason)
        """
        title = exp_item.get('title', '')
        company = exp_item.get('company', '')
        description = exp_item.get('description', '')
        confidence = exp_item.get('confidence', exp_item.get('_confidence_score', 0.0))
        
        # Combine text for analysis
        full_text = f"{title} {company} {description}".lower()
        
        # Rescue Rule 1: Confidence not too low (above rescue threshold)
        if confidence >= self.min_rescue_confidence:
            return True, f"confidence_above_threshold_{confidence:.3f}"
        
        # Rescue Rule 2: Strong professional indicators
        prof_matches = sum(1 for pattern in self.professional_regex if pattern.search(full_text))
        if prof_matches >= 2:
            return True, f"multiple_professional_indicators_{prof_matches}"
        
        # Rescue Rule 3: Business organization classification
        org_result = classify_organization(company, context_lines)
        if (org_result['type'] == OrgType.BUSINESS.value and 
            org_result['confidence'] >= 0.5):
            return True, f"business_organization_{org_result['confidence']:.3f}"
        
        # Rescue Rule 4: Strong employment context
        if context_lines:
            context_text = ' '.join(context_lines).lower()
            emp_matches = sum(1 for pattern in self.employment_regex if pattern.search(context_text))
            if emp_matches >= 2:
                return True, f"employment_context_indicators_{emp_matches}"
        
        # Rescue Rule 5: Duration indicates real experience (>3 months)
        start_date = exp_item.get('start_date')
        end_date = exp_item.get('end_date')
        if start_date and end_date:
            try:
                duration_days = (end_date - start_date).days
                if duration_days >= 90:  # >= 3 months
                    return True, f"meaningful_duration_{duration_days}days"
            except (TypeError, AttributeError):
                pass
        
        # Rescue Rule 6: Diversity protection (avoid mass demotions)
        if all_experiences and len(all_experiences) >= 3:
            # If this would be one of the last remaining items, be more lenient
            high_conf_count = sum(1 for exp in all_experiences 
                                if exp.get('confidence', exp.get('_confidence_score', 0)) >= 0.6)
            if high_conf_count <= 2:
                return True, f"diversity_protection_preserve_minimum"
        
        return False, "no_rescue_criteria_met"
    
    def should_demote_experience(self, exp_item: Dict[str, Any],
                               context_lines: List[str] = None) -> Tuple[bool, str]:
        """
        Determine if an experience should be demoted with protective checks.
        
        Args:
            exp_item: Experience item to evaluate
            context_lines: Surrounding context for analysis
            
        Returns:
            (should_demote, demotion_reason)
        """
        title = exp_item.get('title', '')
        company = exp_item.get('company', '')
        confidence = exp_item.get('confidence', exp_item.get('_confidence_score', 0.0))
        
        # Protective Rule 1: Never demote high-confidence items
        if confidence >= 0.8:
            return False, f"high_confidence_protected_{confidence:.3f}"
        
        # Protective Rule 2: Check for education misclassification
        org_result = classify_organization(company, context_lines)
        if org_result['type'] == OrgType.SCHOOL.value and org_result['confidence'] >= 0.6:
            # This should have been caught by education routing
            return True, f"education_misclassification_{org_result['confidence']:.3f}"
        
        # Protective Rule 3: Date-only or very short content
        combined_text = f"{title} {company}".strip()
        if len(combined_text) <= 8:  # Very short
            return True, f"content_too_short_{len(combined_text)}chars"
        
        # Protective Rule 4: No meaningful professional content
        full_text = f"{title} {company}".lower()
        has_professional = any(pattern.search(full_text) for pattern in self.professional_regex)
        has_business = any(pattern.search(full_text) for pattern in self.business_regex)
        
        if not has_professional and not has_business and confidence < 0.4:
            return True, f"lack_professional_business_context_{confidence:.3f}"
        
        return False, "demotion_criteria_not_met"
    
    def apply_qa_filtering(self, experiences: List[Dict[str, Any]], 
                         context_lines: List[str] = None) -> Tuple[List[Dict[str, Any]], QAMetrics]:
        """
        Apply QA guardrails to experience list.
        
        Args:
            experiences: List of experience items
            context_lines: Full text lines for context analysis
            
        Returns:
            (filtered_experiences, qa_metrics)
        """
        if not experiences:
            return experiences, self.metrics
        
        self.logger.info(f"QA_GUARDRAIL: starting | session={self.session_id} | input_count={len(experiences)}")
        
        filtered_experiences = []
        rescued_items = []
        demoted_items = []
        
        for i, exp_item in enumerate(experiences):
            self.metrics.items_reviewed += 1
            
            # Extract relevant context window if available
            item_context = context_lines
            line_idx = exp_item.get('line_idx', -1)
            if context_lines and line_idx >= 0:
                window_start = max(0, line_idx - 3)
                window_end = min(len(context_lines), line_idx + 4)
                item_context = context_lines[window_start:window_end]
            
            # Check for rescue eligibility
            should_rescue, rescue_reason = self.should_rescue_experience(
                exp_item, item_context, experiences
            )
            
            if should_rescue:
                # Item rescued - keep it
                filtered_experiences.append(exp_item)
                rescued_items.append(exp_item)
                self.metrics.items_rescued += 1
                self.metrics.rescue_reasons[rescue_reason] += 1
                
                self.logger.debug(f"QA_RESCUE: item_{i} | reason={rescue_reason} | "
                                f"title='{validate_no_pii_leakage(exp_item.get('title', '')[:20], DEFAULT_PII_CONFIG.HASH_SALT)}'")
                continue
            
            # Check for demotion with protective measures
            should_demote, demotion_reason = self.should_demote_experience(exp_item, item_context)
            
            if should_demote:
                # Item demoted - remove from experience list
                demoted_items.append(exp_item)
                self.metrics.items_demoted += 1
                self.metrics.demotion_reasons[demotion_reason] += 1
                
                self.logger.debug(f"QA_DEMOTE: item_{i} | reason={demotion_reason} | "
                                f"company='{validate_no_pii_leakage(exp_item.get('company', '')[:20], DEFAULT_PII_CONFIG.HASH_SALT)}'")
            else:
                # Item passes QA - keep it
                filtered_experiences.append(exp_item)
        
        # Safety check: prevent excessive demotions  
        demotion_ratio = self.metrics.items_demoted / max(self.metrics.items_reviewed, 1)
        if demotion_ratio > self.max_demotion_ratio and len(demoted_items) > 1:
            # Restore some demoted items with highest confidence
            demoted_items.sort(key=lambda x: x.get('confidence', x.get('_confidence_score', 0)), reverse=True)
            items_to_restore = int(len(demoted_items) * 0.5)  # Restore 50%
            
            for item in demoted_items[:items_to_restore]:
                filtered_experiences.append(item)
                self.metrics.items_rescued += 1
                self.metrics.rescue_reasons['mass_demotion_protection'] += 1
                
            self.logger.warning(f"QA_MASS_PROTECTION: restored_{items_to_restore} | demotion_ratio={demotion_ratio:.3f}")
        
        # Log final summary
        final_count = len(filtered_experiences)
        self.logger.info(f"QA_SUMMARY: session={self.session_id} | "
                        f"input={len(experiences)} output={final_count} | "
                        f"rescued={self.metrics.items_rescued} demoted={self.metrics.items_demoted} | "
                        f"rescue_rate={self.metrics.items_rescued/max(self.metrics.items_reviewed,1):.3f}")
        
        # Update experience metrics if available
        try:
            exp_tracker = get_experience_metrics_tracker()
            exp_tracker.record_context_match()  # QA processing as context enrichment
        except:
            pass
        
        return filtered_experiences, self.metrics
    
    def get_qa_summary(self) -> Dict[str, Any]:
        """Get comprehensive QA processing summary."""
        return {
            'session_id': self.session_id,
            'processing_stats': {
                'items_reviewed': self.metrics.items_reviewed,
                'items_rescued': self.metrics.items_rescued,
                'items_demoted': self.metrics.items_demoted,
                'rescue_rate': self.metrics.items_rescued / max(self.metrics.items_reviewed, 1),
                'demotion_rate': self.metrics.items_demoted / max(self.metrics.items_reviewed, 1)
            },
            'rescue_reasons': dict(self.metrics.rescue_reasons),
            'demotion_reasons': dict(self.metrics.demotion_reasons),
            'config': {
                'min_rescue_confidence': self.min_rescue_confidence,
                'max_demotion_ratio': self.max_demotion_ratio,
                'diversity_protection_threshold': self.diversity_protection_threshold
            }
        }


# Global guardrail instance
_qa_guardrail = None

def get_qa_guardrail(config: Dict[str, Any] = None) -> QAGuardrail:
    """Get singleton QA guardrail instance."""
    global _qa_guardrail
    if _qa_guardrail is None:
        _qa_guardrail = QAGuardrail(config)
    return _qa_guardrail


# Convenience functions
def apply_qa_protection(experiences: List[Dict[str, Any]], 
                       context_lines: List[str] = None) -> List[Dict[str, Any]]:
    """Apply QA guardrails to prevent over-demotions."""
    guardrail = get_qa_guardrail()
    filtered_exp, _ = guardrail.apply_qa_filtering(experiences, context_lines)
    return filtered_exp


def get_qa_processing_summary() -> Dict[str, Any]:
    """Get QA processing summary."""
    guardrail = get_qa_guardrail()
    return guardrail.get_qa_summary()


def should_rescue_from_demotion(exp_item: Dict[str, Any], 
                               context_lines: List[str] = None,
                               all_items: List[Dict[str, Any]] = None) -> bool:
    """Quick check if an experience should be rescued."""
    guardrail = get_qa_guardrail()
    should_rescue, _ = guardrail.should_rescue_experience(exp_item, context_lines, all_items)
    return should_rescue