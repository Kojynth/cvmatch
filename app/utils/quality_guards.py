"""
Quality Guards System for CV Extraction Guardrails.

Comprehensive quality control system implementing:
- Demotion budget system with evidence requirements (≥2 of 4 criteria for EXP→EDU)  
- Section balance heuristics with skew detection and borderline recovery
- Keep-rate floor monitoring and empty section recovery mechanisms
- PII-safe logging with metrics-only output
"""

import json
import yaml
from typing import Dict, List, Any, Optional, Tuple, Set, Union
from dataclasses import dataclass, asdict, field
from datetime import datetime
from collections import defaultdict, Counter
from pathlib import Path
import re
import math

from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG, SCHOOL_TOKENS, EMPLOYMENT_KEYWORDS


logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


@dataclass
class DemotionEvidence:
    """Evidence for potential EXP → EDU demotion."""
    company_is_school: bool = False
    missing_or_suspect_company: bool = False
    no_employment_keywords: bool = False
    education_signals_present: bool = False
    school_name: str = ""
    evidence_count: int = 0
    confidence_score: float = 0.0
    
    def __post_init__(self):
        """Calculate total evidence count."""
        self.evidence_count = sum([
            self.company_is_school,
            self.missing_or_suspect_company, 
            self.no_employment_keywords,
            self.education_signals_present
        ])


@dataclass
class DemotionCandidate:
    """Candidate for section demotion."""
    item_index: int
    original_section: str
    target_section: str
    evidence: DemotionEvidence
    item_data: Dict[str, Any]
    demotion_reason: str = ""
    approved_for_demotion: bool = False


@dataclass 
class SectionBalance:
    """Section balance metrics and status."""
    section: str
    item_count: int
    target_count: Optional[int] = None
    keep_rate: float = 0.0
    is_empty: bool = False
    has_headers: bool = False
    skew_ratio: float = 0.0
    needs_recovery: bool = False
    recovery_candidates: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class QualityGuardsReport:
    """Comprehensive quality guards execution report."""
    cv_id: str
    timestamp: datetime
    
    # Demotion budget usage
    demotions_attempted: Dict[str, int] = field(default_factory=dict)
    demotions_approved: Dict[str, int] = field(default_factory=dict)
    budget_utilization: Dict[str, float] = field(default_factory=dict)
    
    # Section balance status
    section_balances: Dict[str, SectionBalance] = field(default_factory=dict)
    skew_detected: bool = False
    recoveries_performed: int = 0
    
    # Quality metrics
    overall_keep_rates: Dict[str, float] = field(default_factory=dict)
    empty_sections_recovered: List[str] = field(default_factory=list)
    alerts_generated: List[str] = field(default_factory=list)


class QualityGuardsSystem:
    """
    Comprehensive Quality Guards System for CV Extraction.
    
    Implements systematic quality control through:
    - Evidence-based demotion budgets with hard caps and school limits
    - Section balance enforcement with automatic skew detection
    - Keep-rate floor monitoring and recovery mechanisms  
    - PII-safe logging with detailed quality metrics
    """
    
    def __init__(self, config_path: Optional[str] = None, quality_config: Optional[Dict] = None):
        """Initialize quality guards system with configuration."""
        # Initialize logger first so it's available in _load_quality_config
        self.logger = get_safe_logger(f"{__name__}.QualityGuardsSystem", cfg=DEFAULT_PII_CONFIG)
        self.quality_config = quality_config or self._load_quality_config(config_path)
        
        # Tracking structures
        self.current_session_demotions: Dict[str, int] = defaultdict(int)
        self.per_school_demotions: Dict[str, int] = defaultdict(int)
        self.section_recoveries: Dict[str, int] = defaultdict(int)
        
        # School lexicon for organization classification
        self.school_lexicon = set(SCHOOL_TOKENS)
        self.employment_keywords = set(EMPLOYMENT_KEYWORDS)
        
        self.logger.info("QUALITY_GUARDS: initialized | "
                        f"config_loaded={self.quality_config is not None} | "
                        f"exp_edu_hard_cap={self.quality_config.get('demotion_budget', {}).get('exp_to_edu', {}).get('hard_cap', 8)}")
    
    def _load_quality_config(self, config_path: Optional[str] = None) -> Dict[str, Any]:
        """Load quality configuration from YAML file."""
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "quality.yaml"
        
        try:
            if Path(config_path).exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                self.logger.info(f"QUALITY_GUARDS: config loaded | path={config_path}")
                return config
            else:
                self.logger.warning(f"QUALITY_GUARDS: config file not found | path={config_path} | using defaults")
        except Exception as e:
            self.logger.error(f"QUALITY_GUARDS: config load failed | path={config_path} | error={e}")
        
        # Return minimal default config
        return {
            "demotion_budget": {
                "exp_to_edu": {
                    "hard_cap": 8,
                    "share_cap": 0.25, 
                    "per_school_cap": 2,
                    "min_evidence_count": 2
                }
            },
            "balance": {
                "skew_detection": {
                    "edu_to_exp_ratio_trigger": 3.0,
                    "exp_minimum_threshold": 5
                }
            }
        }
    
    def apply_quality_guardrails(self, sections_data: Dict[str, List[Dict[str, Any]]], 
                                cv_id: str = "unknown") -> Tuple[Dict[str, List[Dict[str, Any]]], QualityGuardsReport]:
        """
        Apply comprehensive quality guardrails to extracted sections.
        
        Args:
            sections_data: Dictionary mapping section names to lists of extracted items
            cv_id: CV identifier for logging
            
        Returns:
            Tuple of (updated_sections_data, quality_guards_report)
        """
        updated_sections = sections_data.copy()
        report = QualityGuardsReport(cv_id=cv_id, timestamp=datetime.now())
        
        # Reset session tracking
        self.current_session_demotions.clear()
        self.per_school_demotions.clear()
        self.section_recoveries.clear()
        
        # Phase 1: Apply Demotion Budget System
        updated_sections, demotion_results = self._apply_demotion_budgets(updated_sections)
        report.demotions_attempted = demotion_results.get("attempted", {})
        report.demotions_approved = demotion_results.get("approved", {})
        report.budget_utilization = demotion_results.get("budget_utilization", {})
        
        # Phase 2: Section Balance Analysis and Recovery
        balance_results = self._apply_section_balance_controls(updated_sections)
        report.section_balances = balance_results.get("balances", {})
        report.skew_detected = balance_results.get("skew_detected", False)
        report.recoveries_performed = balance_results.get("recoveries_performed", 0)
        
        # Update sections with balance recovery results
        if "recovered_items" in balance_results:
            for section, recovered_items in balance_results["recovered_items"].items():
                if recovered_items:
                    updated_sections[section] = updated_sections.get(section, []) + recovered_items
        
        # Phase 3: Keep-Rate Floor Monitoring and Empty Section Recovery
        keep_rate_results = self._apply_keep_rate_monitoring(updated_sections)
        report.overall_keep_rates = keep_rate_results.get("keep_rates", {})
        report.empty_sections_recovered = keep_rate_results.get("recovered_sections", [])
        
        # Update sections with empty section recovery results
        if "recovered_items" in keep_rate_results:
            for section, recovered_items in keep_rate_results["recovered_items"].items():
                if recovered_items:
                    updated_sections[section] = updated_sections.get(section, []) + recovered_items
        
        # Generate quality alerts
        report.alerts_generated = self._generate_quality_alerts(report)
        
        # Log final summary
        self.logger.info(f"QUALITY_GUARDS: completed | cv={cv_id} | "
                        f"demotions_approved={sum(report.demotions_approved.values())} | "
                        f"recoveries_performed={report.recoveries_performed} | "
                        f"alerts={len(report.alerts_generated)}")
        
        return updated_sections, report
    
    def _apply_demotion_budgets(self, sections_data: Dict[str, List[Dict[str, Any]]]) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, Any]]:
        """Apply evidence-based demotion budget system."""
        updated_sections = sections_data.copy()
        results = {
            "attempted": defaultdict(int),
            "approved": defaultdict(int), 
            "budget_utilization": {}
        }
        
        # Focus on EXP → EDU demotion (main problematic route)
        exp_items = updated_sections.get("exp", [])
        if not exp_items:
            return updated_sections, results
        
        # Get demotion configuration
        exp_edu_config = self.quality_config.get("demotion_budget", {}).get("exp_to_edu", {})
        hard_cap = exp_edu_config.get("hard_cap", 8)
        share_cap = exp_edu_config.get("share_cap", 0.25)
        per_school_cap = exp_edu_config.get("per_school_cap", 2)
        min_evidence_count = exp_edu_config.get("min_evidence_count", 2)
        
        # Maximum demotions allowed
        max_by_share = int(len(exp_items) * share_cap)
        max_demotions = min(hard_cap, max_by_share)
        
        # Evaluate each experience item for demotion evidence
        demotion_candidates = []
        for idx, item in enumerate(exp_items):
            evidence = self._evaluate_exp_edu_demotion_evidence(item)
            
            if evidence.evidence_count >= min_evidence_count:
                candidate = DemotionCandidate(
                    item_index=idx,
                    original_section="exp",
                    target_section="edu",
                    evidence=evidence,
                    item_data=item,
                    demotion_reason=f"evidence_count={evidence.evidence_count}"
                )
                demotion_candidates.append(candidate)
                results["attempted"]["exp_to_edu"] += 1
        
        # Sort candidates by evidence strength (more evidence = higher priority)
        demotion_candidates.sort(key=lambda c: (c.evidence.evidence_count, c.evidence.confidence_score), reverse=True)
        
        # Apply budget constraints and approve demotions
        demotions_approved = 0
        demoted_indices = []
        school_counts = defaultdict(int)
        
        for candidate in demotion_candidates:
            # Check hard cap
            if demotions_approved >= max_demotions:
                break
            
            # Check per-school cap
            school_name = candidate.evidence.school_name or "unknown"
            if school_name != "unknown" and school_counts[school_name] >= per_school_cap:
                continue
            
            # Check for strong education signals override
            strong_edu_config = exp_edu_config.get("strong_edu_signals_override", {})
            if (candidate.evidence.education_signals_present and 
                strong_edu_config.get("bypass_evidence_count", False) and
                candidate.evidence.evidence_count >= strong_edu_config.get("min_signals", 2)):
                # Allow demotion even with less evidence
                pass
            elif candidate.evidence.evidence_count < min_evidence_count:
                continue
            
            # Approve demotion
            candidate.approved_for_demotion = True
            demotions_approved += 1
            demoted_indices.append(candidate.item_index)
            if school_name != "unknown":
                school_counts[school_name] += 1
            
            self.logger.debug(f"DEMOTION_APPROVED: exp_to_edu | idx={candidate.item_index} | "
                             f"evidence={candidate.evidence.evidence_count} | "
                             f"school={school_name} | reason={candidate.demotion_reason}")
        
        # Apply demotions to sections
        if demoted_indices:
            # Move items from EXP to EDU
            demoted_items = []
            remaining_exp_items = []
            
            for idx, item in enumerate(exp_items):
                if idx in demoted_indices:
                    # Mark as demoted and add to EDU section
                    item_copy = item.copy()
                    item_copy['_demoted_from'] = 'exp'
                    item_copy['_demotion_reason'] = 'quality_guards_evidence_based'
                    demoted_items.append(item_copy)
                else:
                    remaining_exp_items.append(item)
            
            # Update sections
            updated_sections["exp"] = remaining_exp_items
            updated_sections["edu"] = updated_sections.get("edu", []) + demoted_items
            
            results["approved"]["exp_to_edu"] = demotions_approved
        
        # Calculate budget utilization
        results["budget_utilization"]["exp_to_edu"] = demotions_approved / max_demotions if max_demotions > 0 else 0.0
        
        self.logger.info(f"DEMOTION_BUDGET: exp_to_edu | "
                        f"candidates={len(demotion_candidates)} "
                        f"approved={demotions_approved}/{max_demotions} "
                        f"utilization={results['budget_utilization']['exp_to_edu']:.2f}")
        
        return updated_sections, results
    
    def _evaluate_exp_edu_demotion_evidence(self, item: Dict[str, Any]) -> DemotionEvidence:
        """Evaluate evidence for EXP → EDU demotion."""
        evidence = DemotionEvidence()
        
        # Extract text fields for analysis
        company = item.get('company', '').strip()
        title = item.get('title', '').strip()
        description = item.get('description', '').strip()
        raw_text = item.get('raw_text', item.get('source_text', '')).strip()
        
        all_text = f"{company} {title} {description} {raw_text}".lower()
        
        # Evidence 1: Company is school
        if company:
            company_lower = company.lower()
            for school_token in self.school_lexicon:
                if school_token.lower() in company_lower:
                    evidence.company_is_school = True
                    evidence.school_name = company
                    break
        
        # Evidence 2: Missing or suspect company
        if not company or len(company.strip()) < 2:
            evidence.missing_or_suspect_company = True
        elif company.lower() in ['stage', 'internship', 'projet', 'project', 'thesis', 'mémoire']:
            evidence.missing_or_suspect_company = True
        
        # Evidence 3: No employment keywords
        employment_found = False
        for keyword in self.employment_keywords:
            if keyword.lower() in all_text:
                employment_found = True
                break
        evidence.no_employment_keywords = not employment_found
        
        # Evidence 4: Education signals present
        education_signals = [
            'degree', 'diplôme', 'master', 'bachelor', 'licence', 'bts', 'dut',
            'université', 'university', 'école', 'school', 'college', 'institut',
            'campus', 'faculté', 'faculty', 'département', 'department',
            'thesis', 'mémoire', 'dissertation', 'soutenance', 'projet fin étude'
        ]
        
        for signal in education_signals:
            if signal.lower() in all_text:
                evidence.education_signals_present = True
                break
        
        # Calculate confidence score
        base_confidence = item.get('confidence', item.get('raw_confidence', 0.5))
        evidence.confidence_score = base_confidence
        
        return evidence
    
    def _apply_section_balance_controls(self, sections_data: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
        """Apply section balance heuristics with skew detection and recovery."""
        results = {
            "balances": {},
            "skew_detected": False,
            "recoveries_performed": 0,
            "recovered_items": {}
        }
        
        # Get balance configuration
        balance_config = self.quality_config.get("balance", {})
        skew_config = balance_config.get("skew_detection", {})
        recovery_config = balance_config.get("borderline_recovery", {})
        
        exp_count = len(sections_data.get("exp", []))
        edu_count = len(sections_data.get("edu", []))
        
        # Calculate section balances
        for section in ["exp", "edu", "certs", "lang", "soft", "proj"]:
            items = sections_data.get(section, [])
            balance = SectionBalance(
                section=section,
                item_count=len(items),
                is_empty=(len(items) == 0),
                # TODO: Add header detection logic
                has_headers=False
            )
            results["balances"][section] = balance
        
        # Skew Detection: EDU > 3 × EXP AND EXP < 5
        edu_exp_ratio = edu_count / max(exp_count, 1)
        ratio_trigger = skew_config.get("edu_to_exp_ratio_trigger", 3.0)
        exp_threshold = skew_config.get("exp_minimum_threshold", 5)
        
        if edu_exp_ratio > float(ratio_trigger) and exp_count < int(exp_threshold):
            results["skew_detected"] = True
            
            self.logger.warning(f"SECTION_BALANCE: skew detected | "
                               f"edu={edu_count} exp={exp_count} "
                               f"ratio={edu_exp_ratio:.1f} > {ratio_trigger}")
            
            # Attempt borderline recovery for EXP
            recovered_exp = self._attempt_borderline_recovery("exp", sections_data, recovery_config)
            if recovered_exp:
                results["recovered_items"]["exp"] = recovered_exp
                results["recoveries_performed"] += len(recovered_exp)
                
                self.logger.info(f"BORDERLINE_RECOVERY: exp | "
                                f"recovered={len(recovered_exp)} items")
        
        return results
    
    def _attempt_borderline_recovery(self, target_section: str, sections_data: Dict[str, List[Dict[str, Any]]],
                                    recovery_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Attempt to recover borderline items for section balance."""
        recovered_items = []
        max_recoveries = recovery_config.get("max_recoveries", 3)
        confidence_range = recovery_config.get("confidence_range", [0.45, 0.60])
        confidence_boost = recovery_config.get("confidence_boost", 0.05)
        
        # Look for borderline items in other sections (especially EDU for EXP recovery)
        source_sections = ["edu", "proj", "soft"] if target_section == "exp" else ["exp"]
        
        recovery_candidates = []
        
        for source_section in source_sections:
            source_items = sections_data.get(source_section, [])
            
            for idx, item in enumerate(source_items):
                confidence = item.get('confidence', item.get('raw_confidence', 0.5))
                
                # Check if item is in borderline confidence range
                if float(confidence_range[0]) <= float(confidence) <= float(confidence_range[1]):
                    # Additional checks for EXP recovery
                    if target_section == "exp":
                        if self._could_be_experience(item):
                            recovery_candidates.append((source_section, idx, item, confidence))
                    else:
                        recovery_candidates.append((source_section, idx, item, confidence))
        
        # Sort by confidence (highest first for better candidates)
        recovery_candidates.sort(key=lambda x: x[3], reverse=True)
        
        # Recover up to max_recoveries items
        for source_section, idx, item, confidence in recovery_candidates[:max_recoveries]:
            # Create recovered item copy with boosted confidence
            recovered_item = item.copy()
            recovered_item['confidence'] = min(0.95, confidence + confidence_boost)
            recovered_item['_recovered_from'] = source_section
            recovered_item['_recovery_reason'] = 'borderline_balance_recovery'
            recovered_item[recovery_config.get('recovery_flag', 'recovered_borderline_exp')] = True
            
            recovered_items.append(recovered_item)
        
        return recovered_items
    
    def _could_be_experience(self, item: Dict[str, Any]) -> bool:
        """Check if an item could potentially be an experience."""
        # Basic heuristics for experience classification
        text_fields = [
            item.get('title', ''),
            item.get('company', ''),  
            item.get('description', ''),
            item.get('raw_text', item.get('source_text', ''))
        ]
        
        all_text = ' '.join(text_fields).lower()
        
        # Look for experience indicators
        exp_indicators = [
            'stage', 'internship', 'job', 'work', 'employ', 'mission', 'projet',
            'developed', 'managed', 'led', 'created', 'implemented', 'analyzed'
        ]
        
        # Look for anti-experience indicators  
        edu_indicators = [
            'course', 'cours', 'module', 'semester', 'grade', 'exam', 'student'
        ]
        
        exp_score = sum(1 for indicator in exp_indicators if indicator in all_text)
        edu_score = sum(1 for indicator in edu_indicators if indicator in all_text)
        
        return exp_score > edu_score
    
    def _apply_keep_rate_monitoring(self, sections_data: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
        """Apply keep-rate floor monitoring and empty section recovery."""
        results = {
            "keep_rates": {},
            "recovered_sections": [],
            "recovered_items": {}
        }
        
        # Get keep-rate configuration
        keep_rate_config = self.quality_config.get("balance", {}).get("keep_rate_floors", {})
        empty_recovery_config = self.quality_config.get("balance", {}).get("empty_section_recovery", {})
        
        # Monitor keep rates for key sections
        for section in ["exp", "edu"]:
            items = sections_data.get(section, [])
            if items:
                # TODO: Calculate actual keep rate based on original candidates
                # For now, use item count as proxy
                keep_rate = min(1.0, len(items) / 10.0)  # Placeholder calculation
                results["keep_rates"][section] = keep_rate
                
                try:
                    min_keep_rate = float(keep_rate_config.get(f"{section}_keep_rate_min", 0.10))
                except Exception:
                    min_keep_rate = 0.10
                if keep_rate < float(min_keep_rate):
                    self.logger.warning(f"KEEP_RATE: {section} | "
                                       f"rate={keep_rate:.2f} < {min_keep_rate}")
        
        # Empty section recovery
        for section in ["soft", "proj"]:
            items = sections_data.get(section, [])
            if not items:  # Empty section
                section_config = empty_recovery_config.get(section, {})
                if section_config.get("enable_fallback_parse", False):
                    # TODO: Implement fallback parsing recovery
                    self.logger.info(f"EMPTY_SECTION_RECOVERY: {section} | fallback parsing enabled")
                    results["recovered_sections"].append(section)
        
        return results
    
    def _generate_quality_alerts(self, report: QualityGuardsReport) -> List[str]:
        """Generate quality alerts based on guardrails report."""
        alerts = []
        
        # Alert configuration
        alert_config = self.quality_config.get("alerts", {})
        
        # Demotion budget alerts
        try:
            demotion_warning = float(alert_config.get("demotion_budget_warning", 0.75))
        except Exception:
            demotion_warning = 0.75
        try:
            demotion_critical = float(alert_config.get("demotion_budget_critical", 0.90))
        except Exception:
            demotion_critical = 0.90
        
        for route, utilization in report.budget_utilization.items():
            if utilization >= demotion_critical:
                alerts.append(f"CRITICAL: {route} demotion budget {utilization:.0%} utilized")
            elif utilization >= demotion_warning:
                alerts.append(f"WARNING: {route} demotion budget {utilization:.0%} utilized")
        
        # Section balance alerts
        try:
            severe_ratio = float(alert_config.get("severe_imbalance_ratio", 5.0))
        except Exception:
            severe_ratio = 5.0
        
        if report.skew_detected:
            alerts.append("WARNING: Severe section imbalance detected (EDU >> EXP)")
        
        # Empty section alerts
        if alert_config.get("empty_section_with_headers", True):
            for section, balance in report.section_balances.items():
                if balance.is_empty and balance.has_headers:
                    alerts.append(f"WARNING: {section} section empty despite headers detected")
        
        return alerts
    
    def get_demotion_budget_status(self) -> Dict[str, Any]:
        """Get current demotion budget utilization status."""
        exp_edu_config = self.quality_config.get("demotion_budget", {}).get("exp_to_edu", {})
        hard_cap = exp_edu_config.get("hard_cap", 8)
        
        return {
            "exp_to_edu": {
                "used": self.current_session_demotions.get("exp_to_edu", 0),
                "limit": hard_cap,
                "utilization": self.current_session_demotions.get("exp_to_edu", 0) / hard_cap,
                "remaining": hard_cap - self.current_session_demotions.get("exp_to_edu", 0)
            }
        }
    
    def reset_session(self):
        """Reset session tracking for new CV processing."""
        self.current_session_demotions.clear()
        self.per_school_demotions.clear()
        self.section_recoveries.clear()
        self.logger.debug("QUALITY_GUARDS: session reset")


# Global instance management
_global_quality_guards: Optional[QualityGuardsSystem] = None


def get_quality_guards(config_path: Optional[str] = None) -> QualityGuardsSystem:
    """Get the global quality guards system instance."""
    global _global_quality_guards
    
    if _global_quality_guards is None:
        _global_quality_guards = QualityGuardsSystem(config_path)
    
    return _global_quality_guards


def reset_quality_guards():
    """Reset the global quality guards system (primarily for testing)."""
    global _global_quality_guards
    _global_quality_guards = None
