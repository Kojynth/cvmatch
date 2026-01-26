"""
Unified reporting system that consolidates metrics from all extraction components.
Ensures controller-level summaries derive from the same counters as the mapper.
"""

import json
import time
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from pathlib import Path

from ..logging.safe_logger import get_safe_logger, DEFAULT_PII_CONFIG

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


@dataclass
class ExtractionMetrics:
    """Unified extraction metrics structure."""
    
    # Document metadata
    doc_id: str
    extraction_timestamp: str
    processing_time_seconds: float
    
    # Section metrics
    sections_detected: int
    sections_mapped: int
    boundary_quality_score: float
    
    # Experience metrics
    experiences_attempted: int
    experiences_final: int
    assoc_rate: float  # Association rate
    exp_coverage: float  # Experience coverage
    tri_signal_passes: int
    tri_signal_failures: int
    
    # Organization rebinding
    org_rebind_attempts: int
    org_rebind_successes: int
    org_rebind_success_rate: float
    
    # Quality and demotions
    experiences_demoted: int
    demoted_to_education: int
    school_as_employer_flags: int
    missing_or_suspect_company_flags: int
    
    # Pattern diversity and overfitting
    pattern_diversity: float
    pattern_diversity_alerts: List[str]
    overfitting_warnings: List[str]
    
    # Education metrics
    education_items_pass1: int
    education_items_pass2: int
    education_keep_rate: float
    education_items_final: int
    
    # Certification metrics
    certifications_detected_pre_merge: int
    certifications_final: int
    certification_stop_tags: int
    
    # Other sections
    skills_extracted: int
    languages_extracted: int
    projects_extracted: int
    
    # Header conflicts and boundary guards
    header_conflicts_detected: int
    boundary_terminations: int
    timeline_blocks_excluded: int
    
    # Missing metrics from diagnostic requirements
    bornage_quality_score: float = 0.0
    foreign_density: float = 0.0
    boundary_overlap_count_before: int = 0
    boundary_overlap_count_after: int = 0
    edu_dedup_cross_window_count: int = 0
    exp_gate_pass_rate: float = 0.0
    
    # Success criteria flags
    meets_boundary_quality_threshold: bool = False
    meets_assoc_rate_threshold: bool = False  
    meets_exp_coverage_threshold: bool = False
    meets_pattern_diversity_threshold: bool = False


class UnifiedReporter:
    """Unified reporting system for all extraction metrics."""
    
    def __init__(self):
        self.current_metrics: Optional[ExtractionMetrics] = None
        self.session_start_time = time.time()
        
        # Success criteria thresholds (from prompt requirements)
        self.success_thresholds = {
            'boundary_quality_score': 0.70,
            'assoc_rate': 0.70,
            'exp_coverage': 0.25,
            'org_rebind_success_rate': 0.60,
            'pattern_diversity': 0.30
        }
        
    def start_extraction_session(self, doc_id: str) -> str:
        """Start a new extraction session and initialize metrics."""
        extraction_id = f"{doc_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        self.current_metrics = ExtractionMetrics(
            doc_id=doc_id,
            extraction_timestamp=datetime.now().isoformat(),
            processing_time_seconds=0.0,
            sections_detected=0,
            sections_mapped=0,
            boundary_quality_score=0.0,
            experiences_attempted=0,
            experiences_final=0,
            assoc_rate=0.0,
            exp_coverage=0.0,
            tri_signal_passes=0,
            tri_signal_failures=0,
            org_rebind_attempts=0,
            org_rebind_successes=0,
            org_rebind_success_rate=0.0,
            experiences_demoted=0,
            demoted_to_education=0,
            school_as_employer_flags=0,
            missing_or_suspect_company_flags=0,
            pattern_diversity=0.0,
            pattern_diversity_alerts=[],
            overfitting_warnings=[],
            education_items_pass1=0,
            education_items_pass2=0,
            education_keep_rate=0.0,
            education_items_final=0,
            certifications_detected_pre_merge=0,
            certifications_final=0,
            certification_stop_tags=0,
            skills_extracted=0,
            languages_extracted=0,
            projects_extracted=0,
            header_conflicts_detected=0,
            boundary_terminations=0,
            timeline_blocks_excluded=0,
            # Initialize new metrics from diagnostic requirements
            bornage_quality_score=0.0,
            foreign_density=0.0,
            boundary_overlap_count_before=0,
            boundary_overlap_count_after=0,
            edu_dedup_cross_window_count=0,
            exp_gate_pass_rate=0.0
        )
        
        logger.info(f"UNIFIED_REPORTER: session_started | extraction_id={extraction_id}")
        return extraction_id
        
    def update_section_metrics(self, sections_detected: int, sections_mapped: int,
                             boundary_quality_score: float):
        """Update section-level metrics."""
        if not self.current_metrics:
            return
            
        self.current_metrics.sections_detected = sections_detected
        self.current_metrics.sections_mapped = sections_mapped
        self.current_metrics.boundary_quality_score = boundary_quality_score
        
        # Check success criteria
        self.current_metrics.meets_boundary_quality_threshold = (
            boundary_quality_score >= self.success_thresholds['boundary_quality_score']
        )
        
        logger.debug(f"UNIFIED_REPORTER: section_metrics_updated | "
                    f"detected={sections_detected} mapped={sections_mapped} "
                    f"boundary_quality={boundary_quality_score:.3f}")
        
    def update_experience_metrics(self, extraction_stats: Dict[str, Any],
                                pattern_diversity: float,
                                demotions: List[Dict[str, Any]] = None):
        """Update experience extraction metrics."""
        if not self.current_metrics:
            return
            
        stats = extraction_stats
        
        self.current_metrics.experiences_attempted = stats.get('total_attempts', 0)
        self.current_metrics.experiences_final = stats.get('final_experiences', 0)
        self.current_metrics.tri_signal_passes = stats.get('tri_signal_passes', 0)
        self.current_metrics.tri_signal_failures = stats.get('tri_signal_failures', 0)
        self.current_metrics.org_rebind_attempts = stats.get('org_rebind_attempts', 0)
        self.current_metrics.org_rebind_successes = stats.get('org_rebind_successes', 0)
        self.current_metrics.school_as_employer_flags = stats.get('school_org_demotions', 0)
        self.current_metrics.header_conflicts_detected = stats.get('header_conflicts', 0)
        self.current_metrics.pattern_diversity = pattern_diversity
        
        # Calculate derived metrics
        if self.current_metrics.experiences_attempted > 0:
            self.current_metrics.assoc_rate = (
                self.current_metrics.tri_signal_passes / self.current_metrics.experiences_attempted
            )
        
        if self.current_metrics.org_rebind_attempts > 0:
            self.current_metrics.org_rebind_success_rate = (
                self.current_metrics.org_rebind_successes / self.current_metrics.org_rebind_attempts
            )
            
        # Process demotions
        if demotions:
            self.current_metrics.experiences_demoted = len(demotions)
            for demotion in demotions:
                if demotion.get('target_section') == 'education':
                    self.current_metrics.demoted_to_education += 1
                    
                reasons = demotion.get('reasons', [])
                if 'missing_or_suspect_company' in reasons:
                    self.current_metrics.missing_or_suspect_company_flags += 1
                    
        # Check success criteria
        self.current_metrics.meets_assoc_rate_threshold = (
            self.current_metrics.assoc_rate >= self.success_thresholds['assoc_rate']
        )
        self.current_metrics.meets_pattern_diversity_threshold = (
            pattern_diversity >= self.success_thresholds['pattern_diversity']
        )
        
        logger.debug(f"UNIFIED_REPORTER: experience_metrics_updated | "
                    f"final={self.current_metrics.experiences_final} "
                    f"assoc_rate={self.current_metrics.assoc_rate:.3f} "
                    f"pattern_diversity={pattern_diversity:.3f}")
        
    def update_education_metrics(self, education_metrics: Dict[str, Any]):
        """Update education extraction metrics."""
        if not self.current_metrics:
            return
            
        metrics = education_metrics.get('metrics', {})
        
        self.current_metrics.education_items_pass1 = len(education_metrics.get('items', []))
        self.current_metrics.education_keep_rate = metrics.get('keep_rate_pass1', 0.0)
        self.current_metrics.education_items_pass2 = metrics.get('pass2_items_added', 0)
        self.current_metrics.education_items_final = metrics.get('final_item_count', 0)
        
        # Calculate experience coverage approximation
        total_sections = max(self.current_metrics.sections_detected, 1)
        self.current_metrics.exp_coverage = (
            self.current_metrics.experiences_final / total_sections
        )
        
        # Check exp_coverage success criteria
        self.current_metrics.meets_exp_coverage_threshold = (
            self.current_metrics.exp_coverage >= self.success_thresholds['exp_coverage']
        )
        
        logger.debug(f"UNIFIED_REPORTER: education_metrics_updated | "
                    f"pass1={self.current_metrics.education_items_pass1} "
                    f"pass2={self.current_metrics.education_items_pass2} "
                    f"keep_rate={self.current_metrics.education_keep_rate:.3f}")
        
    def update_certification_metrics(self, cert_result: Dict[str, Any]):
        """Update certification metrics."""
        if not self.current_metrics:
            return
            
        self.current_metrics.certifications_detected_pre_merge = cert_result.get('pre_merge_count', 0)
        self.current_metrics.certification_stop_tags = len(cert_result.get('stop_tags', set()))
        self.current_metrics.certifications_final = len(cert_result.get('detected_certifications', []))
        
        logger.debug(f"UNIFIED_REPORTER: certification_metrics_updated | "
                    f"pre_merge={self.current_metrics.certifications_detected_pre_merge} "
                    f"stop_tags={self.current_metrics.certification_stop_tags}")
        
    def update_other_section_metrics(self, skills_count: int = 0, languages_count: int = 0,
                                   projects_count: int = 0):
        """Update metrics for other sections (skills, languages, projects)."""
        if not self.current_metrics:
            return
            
        self.current_metrics.skills_extracted = skills_count
        self.current_metrics.languages_extracted = languages_count
        self.current_metrics.projects_extracted = projects_count
        
    def add_pattern_diversity_alert(self, alert_message: str):
        """Add a pattern diversity alert."""
        if not self.current_metrics:
            return
            
        self.current_metrics.pattern_diversity_alerts.append(alert_message)
        logger.warning(f"PATTERN_DIVERSITY_ALERT: {alert_message}")
        
    def add_overfitting_warning(self, warning_message: str):
        """Add an overfitting warning."""
        if not self.current_metrics:
            return
            
        self.current_metrics.overfitting_warnings.append(warning_message)
        logger.warning(f"OVERFITTING_WARNING: {warning_message}")
    
    def update_bornage_quality_score(self, score: float):
        """Update boundary quality score (bornage)."""
        if not self.current_metrics:
            return
        self.current_metrics.bornage_quality_score = score
        logger.debug(f"BORNAGE_QUALITY: updated_score={score:.3f}")
    
    def update_foreign_density(self, density: float):
        """Update foreign language/character density."""
        if not self.current_metrics:
            return
        self.current_metrics.foreign_density = density
        logger.debug(f"FOREIGN_DENSITY: updated_density={density:.3f}")
    
    def update_boundary_overlap_counts(self, before: int, after: int):
        """Update boundary overlap counts before and after normalization."""
        if not self.current_metrics:
            return
        self.current_metrics.boundary_overlap_count_before = before
        self.current_metrics.boundary_overlap_count_after = after
        logger.info(f"BOUNDARY_OVERLAPS: before={before} after={after}")
    
    def increment_edu_dedup_cross_window(self):
        """Increment education deduplication cross-window counter."""
        if not self.current_metrics:
            return
        self.current_metrics.edu_dedup_cross_window_count += 1
        logger.debug(f"EDU_DEDUP: cross_window_count={self.current_metrics.edu_dedup_cross_window_count}")
    
    def update_exp_gate_pass_rate(self, passed: int, total: int):
        """Update experience gate pass rate."""
        if not self.current_metrics:
            return
        self.current_metrics.exp_gate_pass_rate = passed / total if total > 0 else 0.0
        logger.debug(f"EXP_GATE: pass_rate={self.current_metrics.exp_gate_pass_rate:.3f} ({passed}/{total})")
        
    def finalize_extraction_session(self) -> ExtractionMetrics:
        """Finalize the extraction session and calculate final metrics."""
        if not self.current_metrics:
            raise ValueError("No active extraction session to finalize")
            
        # Calculate final processing time
        self.current_metrics.processing_time_seconds = time.time() - self.session_start_time
        
        # Final validation of success criteria
        success_criteria = [
            self.current_metrics.meets_boundary_quality_threshold,
            self.current_metrics.meets_assoc_rate_threshold,
            self.current_metrics.meets_exp_coverage_threshold,
            self.current_metrics.meets_pattern_diversity_threshold
        ]
        
        overall_success = sum(success_criteria) >= 3  # At least 3 of 4 criteria
        
        logger.info(f"UNIFIED_REPORTER: session_finalized | "
                   f"doc_id={self.current_metrics.doc_id} "
                   f"processing_time={self.current_metrics.processing_time_seconds:.2f}s "
                   f"overall_success={overall_success} "
                   f"success_criteria={sum(success_criteria)}/4")
        
        return self.current_metrics
        
    def generate_counts_snapshot(self) -> Dict[str, Any]:
        """Generate final counts snapshot (unified counters)."""
        if not self.current_metrics:
            return {}
            
        snapshot = {
            'extraction_timestamp': self.current_metrics.extraction_timestamp,
            'sections': {
                'detected': self.current_metrics.sections_detected,
                'mapped': self.current_metrics.sections_mapped,
                'boundary_quality': self.current_metrics.boundary_quality_score
            },
            'experiences': {
                'attempted': self.current_metrics.experiences_attempted,
                'final': self.current_metrics.experiences_final,
                'assoc_rate': self.current_metrics.assoc_rate,
                'exp_coverage': self.current_metrics.exp_coverage,
                'demoted': self.current_metrics.experiences_demoted
            },
            'education': {
                'pass1_items': self.current_metrics.education_items_pass1,
                'pass2_items': self.current_metrics.education_items_pass2,
                'final_items': self.current_metrics.education_items_final,
                'keep_rate': self.current_metrics.education_keep_rate
            },
            'certifications': {
                'pre_merge_detected': self.current_metrics.certifications_detected_pre_merge,
                'final': self.current_metrics.certifications_final
            },
            'other_sections': {
                'skills': self.current_metrics.skills_extracted,
                'languages': self.current_metrics.languages_extracted,
                'projects': self.current_metrics.projects_extracted
            },
            'quality_metrics': {
                'pattern_diversity': self.current_metrics.pattern_diversity,
                'org_rebind_success_rate': self.current_metrics.org_rebind_success_rate,
                'processing_time_seconds': self.current_metrics.processing_time_seconds
            },
            'success_criteria': {
                'boundary_quality_met': self.current_metrics.meets_boundary_quality_threshold,
                'assoc_rate_met': self.current_metrics.meets_assoc_rate_threshold,
                'exp_coverage_met': self.current_metrics.meets_exp_coverage_threshold,
                'pattern_diversity_met': self.current_metrics.meets_pattern_diversity_threshold
            }
        }
        
        return snapshot
        
    def export_detailed_report(self, output_path: str):
        """Export detailed extraction report to file."""
        if not self.current_metrics:
            logger.warning("UNIFIED_REPORTER: no_metrics_to_export")
            return
            
        report_data = {
            'metadata': {
                'report_version': '1.0.0',
                'generated_at': datetime.now().isoformat(),
                'doc_id': self.current_metrics.doc_id
            },
            'metrics': asdict(self.current_metrics),
            'counts_snapshot': self.generate_counts_snapshot(),
            'success_analysis': self._generate_success_analysis()
        }
        
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False, default=str)
            
        logger.info(f"UNIFIED_REPORTER: detailed_report_exported | path={output_path}")
        
    def _generate_success_analysis(self) -> Dict[str, Any]:
        """Generate detailed success criteria analysis."""
        if not self.current_metrics:
            return {}
            
        analysis = {
            'overall_assessment': 'success' if sum([
                self.current_metrics.meets_boundary_quality_threshold,
                self.current_metrics.meets_assoc_rate_threshold,
                self.current_metrics.meets_exp_coverage_threshold,
                self.current_metrics.meets_pattern_diversity_threshold
            ]) >= 3 else 'needs_improvement',
            
            'criteria_details': {
                'boundary_quality': {
                    'current': self.current_metrics.boundary_quality_score,
                    'threshold': self.success_thresholds['boundary_quality_score'],
                    'met': self.current_metrics.meets_boundary_quality_threshold
                },
                'assoc_rate': {
                    'current': self.current_metrics.assoc_rate,
                    'threshold': self.success_thresholds['assoc_rate'],
                    'met': self.current_metrics.meets_assoc_rate_threshold
                },
                'exp_coverage': {
                    'current': self.current_metrics.exp_coverage,
                    'threshold': self.success_thresholds['exp_coverage'],
                    'met': self.current_metrics.meets_exp_coverage_threshold
                },
                'pattern_diversity': {
                    'current': self.current_metrics.pattern_diversity,
                    'threshold': self.success_thresholds['pattern_diversity'],
                    'met': self.current_metrics.meets_pattern_diversity_threshold
                }
            },
            
            'improvement_recommendations': self._generate_improvement_recommendations()
        }
        
        return analysis
        
    def _generate_improvement_recommendations(self) -> List[str]:
        """Generate recommendations for improvement based on current metrics."""
        recommendations = []
        
        if not self.current_metrics:
            return recommendations
            
        if not self.current_metrics.meets_boundary_quality_threshold:
            recommendations.append(
                "Improve boundary detection quality by tuning section segmentation algorithms"
            )
            
        if not self.current_metrics.meets_assoc_rate_threshold:
            recommendations.append(
                f"Improve tri-signal validation (current: {self.current_metrics.assoc_rate:.2f}, "
                f"target: {self.success_thresholds['assoc_rate']:.2f})"
            )
            
        if not self.current_metrics.meets_exp_coverage_threshold:
            recommendations.append(
                "Increase experience coverage by improving date-first fallback or section detection"
            )
            
        if not self.current_metrics.meets_pattern_diversity_threshold:
            recommendations.append(
                f"Increase pattern diversity (current: {self.current_metrics.pattern_diversity:.2f}, "
                f"target: {self.success_thresholds['pattern_diversity']:.2f}) by using more varied extraction patterns"
            )
            
        if self.current_metrics.experiences_demoted > self.current_metrics.experiences_final * 0.5:
            recommendations.append(
                "High demotion rate detected - review organization rebinding and quality assessment thresholds"
            )
            
        if self.current_metrics.org_rebind_success_rate < self.success_thresholds['org_rebind_success_rate']:
            recommendations.append(
                "Improve organization rebinding success rate by expanding school lexicon or employment keyword detection"
            )
            
        return recommendations


# Global unified reporter instance
unified_reporter = UnifiedReporter()


def get_unified_reporter() -> UnifiedReporter:
    """Get global unified reporter instance."""
    return unified_reporter
