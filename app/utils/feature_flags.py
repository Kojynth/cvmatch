"""
Feature Flags Configuration - Toggle system for experience extraction enhancements.

Allows runtime configuration of hardened experience extraction features
including Phase 1 early routing, 3-gate validation, and QA guardrails.
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
import json
from pathlib import Path

from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


@dataclass
class ExperienceExtractionFlags:
    """Feature flags for experience extraction system."""
    
    # Phase 1 Early Routing
    enable_early_education_routing: bool = True
    enable_early_certification_routing: bool = True
    early_routing_confidence_threshold: float = 0.6
    
    # 3-Gate Validation System
    enable_three_gate_validation: bool = True
    enable_pre_filtering: bool = True
    enable_context_validation: bool = True
    enable_temporal_validation: bool = True
    
    # Confidence Scoring
    enable_weighted_scoring: bool = True
    employment_keyword_weight: float = 0.4
    valid_date_span_weight: float = 0.3
    business_org_weight: float = 0.2
    not_short_acronym_weight: float = 0.1
    minimum_confidence_threshold: float = 0.6
    
    # Organization Classification  
    enable_org_classification: bool = True
    org_classification_confidence_threshold: float = 0.5
    
    # QA Guardrails
    enable_qa_guardrails: bool = True
    max_demotion_ratio: float = 0.3
    min_rescue_confidence: float = 0.4
    diversity_protection_enabled: bool = True
    
    # Metrics and Observability
    enable_experience_metrics: bool = True
    enable_pii_safe_logging: bool = True
    enable_debug_sampling: bool = True
    max_debug_samples: int = 3
    
    # Enhanced Date Processing
    enable_french_date_normalization: bool = True
    enable_automatic_date_swap: bool = True
    enable_temporal_consistency_checks: bool = True
    
    # Whitelist Integration
    use_acronym_whitelist: bool = True
    use_employment_keywords_whitelist: bool = True
    context_window_size: int = 2


@dataclass
class PerformanceFlags:
    """Performance-related feature flags."""
    
    # Processing optimizations
    enable_pattern_compilation_cache: bool = True
    enable_org_classifier_cache: bool = True
    enable_validation_stats_cache: bool = True
    
    # Limits and throttling
    max_lines_per_section: int = 1000
    max_patterns_per_line: int = 10
    validation_timeout_seconds: float = 5.0
    
    # Memory management
    enable_memory_cleanup: bool = True
    cleanup_interval_items: int = 100


@dataclass
class QualityGuardrailsFlags:
    """Quality Guardrails System feature flags."""
    
    # Master enable/disable
    enabled: bool = False
    rollout_percentage: float = 0.0
    fallback_on_errors: bool = True
    
    # Core monitoring features
    enable_pattern_diversity_monitoring: bool = True
    enable_overfitting_interventions: bool = True
    enable_demotion_budget_system: bool = True
    enable_section_balance_controls: bool = True
    enable_keep_rate_monitoring: bool = True
    enable_empty_section_recovery: bool = True
    enable_quality_alerts: bool = True
    enable_metrics_logging: bool = True
    
    # Integration phase controls
    phase_1_extraction: bool = True
    phase_2_cleanup: bool = True
    phase_5_mapping: bool = True
    rescue_flow: bool = True
    
    # Diversity thresholds
    global_minimum: float = 0.30
    exp_minimum: float = 0.30
    edu_minimum: float = 0.25
    certs_minimum: float = 0.20
    lang_minimum: float = 0.20
    soft_minimum: float = 0.25
    proj_minimum: float = 0.30
    
    # Demotion budget limits
    exp_to_edu_hard_cap: int = 8
    exp_to_edu_share_cap: float = 0.25
    exp_to_edu_per_school_cap: int = 2
    min_evidence_count: int = 2


@dataclass
class DebuggingFlags:
    """Debugging and development feature flags."""
    
    # Debug output
    enable_detailed_rejection_logging: bool = False
    enable_pattern_match_details: bool = False
    enable_confidence_breakdown_logging: bool = False
    enable_qa_decision_logging: bool = True
    
    # Test hooks
    enable_synthetic_test_data: bool = False
    force_validation_failure_rate: float = 0.0
    enable_metrics_export: bool = False
    
    # Development aids
    enable_live_config_reload: bool = False
    enable_feature_flag_override: bool = True


@dataclass
class ExtractionFixesFlags:
    """Feature flags for Phase 2 extraction fixes and enhancements."""
    
    # Core extraction fixes
    new_split_algorithm: bool = False
    stage_override_logic: bool = False 
    project_intelligent_router: bool = False
    cert_lang_router: bool = False
    enhanced_extraction_pipeline: bool = True
    fallback_date_parser: bool = True
    
    # Resilience and error handling
    disable_emergency_fallback: bool = False
    strict_validation_mode: bool = False
    regex_lint_validation: bool = True
    
    # Text processing improvements
    enhanced_normalization: bool = True
    apostrophe_accent_preprocessing: bool = True
    title_length_sanitization: bool = True
    max_title_length: int = 120
    
    # Classification improvements
    stage_priority_over_school: bool = False
    project_date_heuristics: bool = False
    cert_typo_correction: bool = True
    
    # UI guard rails
    anti_phantom_interests: bool = True
    strict_deduplication: bool = True
    sanity_title_cleanup: bool = True


@dataclass  
class PhasesAToHFlags:
    """Feature flags for Phases A through H enhancements."""
    
    # Phase A: Boundary Guards & Residual Ledger
    boundary_guards_enabled: bool = True
    use_residual_ledger: bool = True
    assert_no_overlap: bool = True
    merge_overlapping: bool = True
    
    # Phase B: 2-tier Phase-1 Gating
    phase1_gating_2tier_enabled: bool = True
    use_2tier_policy: bool = True
    soft_gate_min_chars: int = 80
    min_valid_blocks: int = 1
    fallback_enabled: bool = True
    
    # Phase C: Projects V2 with No-Progress Guard
    projects_v2_enabled: bool = True
    use_no_progress_guard: bool = True
    max_pass_limit: int = 3
    candidate_tracking: bool = True
    explicit_slice_acceptance: bool = True
    
    # Phase D: French Date Normalization & Org Sieve
    french_date_normalization_enabled: bool = True
    strict_fr_format: bool = True
    two_digit_year_cutoff: int = 25
    handle_textual_months: bool = True
    org_sieve_filtering_enabled: bool = True
    reject_postal_codes: bool = True
    reject_month_names: bool = True
    french_specific: bool = True
    
    # Phase E: Dedicated Section Parsers
    experience_parser_dedicated_enabled: bool = True
    experience_strict_validation: bool = True
    experience_role_classification: bool = True
    experience_org_rebinding: bool = True
    experience_quality_scoring: bool = True
    education_parser_dedicated_enabled: bool = True
    education_french_system: bool = True
    education_degree_classification: bool = True
    education_institution_validation: bool = True
    education_timeline_analysis: bool = True
    
    # Phase F: Conservative Soft Skills V2
    soft_skills_v2_conservative_enabled: bool = True
    conservative_mode: bool = True
    statistical_validation: bool = True
    false_positive_filtering: bool = True
    quality_threshold: float = 0.75
    min_confidence: float = 0.6
    
    # Phase G: Pattern Quality Analysis  
    pattern_quality_analysis_enabled: bool = True
    fail_fast_enabled: bool = True
    diversity_threshold: float = 0.7
    min_pattern_coverage: float = 0.5
    statistical_analysis: bool = True
    
    # Phase H: Unified Reporting Post-Mapping
    unified_reporting_postmapping_enabled: bool = True
    post_mapping_validation: bool = True
    cross_section_coherence: bool = True
    timeline_consistency: bool = True
    quality_assurance: bool = True
    consistency_threshold: float = 0.8


@dataclass
class ResetLoggingFlags:
    """Feature flags for reset logging system."""
    
    enabled: bool = True
    persist_across_resets: bool = True
    json_history: bool = True
    metrics_tracking: bool = True
    log_directory: str = "logs/reset"


@dataclass
class AllFeatureFlags:
    """Container for all feature flag categories."""
    
    experience_extraction: ExperienceExtractionFlags
    performance: PerformanceFlags  
    quality_guardrails: QualityGuardrailsFlags
    debugging: DebuggingFlags
    extraction_fixes: ExtractionFixesFlags
    phases_a_to_h: PhasesAToHFlags
    reset_logging: ResetLoggingFlags
    
    def __post_init__(self):
        if not isinstance(self.experience_extraction, ExperienceExtractionFlags):
            self.experience_extraction = ExperienceExtractionFlags(**self.experience_extraction)
        if not isinstance(self.performance, PerformanceFlags):
            self.performance = PerformanceFlags(**self.performance)
        if not isinstance(self.quality_guardrails, QualityGuardrailsFlags):
            self.quality_guardrails = QualityGuardrailsFlags(**self.quality_guardrails)
        if not isinstance(self.debugging, DebuggingFlags):
            self.debugging = DebuggingFlags(**self.debugging)
        if not isinstance(self.extraction_fixes, ExtractionFixesFlags):
            self.extraction_fixes = ExtractionFixesFlags(**self.extraction_fixes)
        if not isinstance(self.phases_a_to_h, PhasesAToHFlags):
            self.phases_a_to_h = PhasesAToHFlags(**self.phases_a_to_h)
        if not isinstance(self.reset_logging, ResetLoggingFlags):
            self.reset_logging = ResetLoggingFlags(**self.reset_logging)


class FeatureFlagManager:
    """Manages feature flags with runtime configuration support."""
    
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or Path("app/config/feature_flags.json")
        self.logger = get_safe_logger(f"{__name__}.FeatureFlagManager", cfg=DEFAULT_PII_CONFIG)
        
        # Initialize with defaults
        self.flags = AllFeatureFlags(
            experience_extraction=ExperienceExtractionFlags(),
            performance=PerformanceFlags(),
            quality_guardrails=QualityGuardrailsFlags(),
            debugging=DebuggingFlags(),
            extraction_fixes=ExtractionFixesFlags(),
            phases_a_to_h=PhasesAToHFlags(),
            reset_logging=ResetLoggingFlags()
        )
        
        # Load from file if exists
        self.load_from_file()
        
        self.logger.info(f"FEATURE_FLAGS: initialized | config_path={self.config_path}")
    
    def load_from_file(self) -> bool:
        """Load feature flags from JSON configuration file."""
        try:
            if not self.config_path.exists():
                self.logger.info("FEATURE_FLAGS: config file not found, using defaults")
                return False
            
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            # Reconstruct flags from loaded data
            self.flags = AllFeatureFlags(
                experience_extraction=config_data.get('experience_extraction', {}),
                performance=config_data.get('performance', {}),
                quality_guardrails=config_data.get('quality_guardrails', {}),
                debugging=config_data.get('debugging', {}),
                extraction_fixes=config_data.get('extraction_fixes', {}),
                phases_a_to_h=config_data.get('phases_a_to_h', {}),
                reset_logging=config_data.get('reset_logging', {})
            )
            
            self.logger.info(f"FEATURE_FLAGS: loaded from file | path={self.config_path}")
            return True
            
        except Exception as e:
            self.logger.warning(f"FEATURE_FLAGS: failed to load config | error={e}")
            return False
    
    def save_to_file(self) -> bool:
        """Save current feature flags to JSON configuration file."""
        try:
            # Ensure directory exists
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Convert to serializable dict
            config_data = asdict(self.flags)
            
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"FEATURE_FLAGS: saved to file | path={self.config_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"FEATURE_FLAGS: failed to save config | error={e}")
            return False
    
    def get_experience_flags(self) -> ExperienceExtractionFlags:
        """Get experience extraction feature flags."""
        return self.flags.experience_extraction
    
    def get_performance_flags(self) -> PerformanceFlags:
        """Get performance feature flags."""
        return self.flags.performance
    
    def get_quality_guardrails_flags(self) -> QualityGuardrailsFlags:
        """Get quality guardrails feature flags."""
        return self.flags.quality_guardrails
    
    def get_debugging_flags(self) -> DebuggingFlags:
        """Get debugging feature flags."""
        return self.flags.debugging
    
    def get_extraction_fixes_flags(self) -> ExtractionFixesFlags:
        """Get extraction fixes feature flags."""
        return self.flags.extraction_fixes
    
    def get_phases_a_to_h_flags(self) -> PhasesAToHFlags:
        """Get Phases A-H feature flags."""
        return self.flags.phases_a_to_h
    
    def get_reset_logging_flags(self) -> ResetLoggingFlags:
        """Get reset logging feature flags."""
        return self.flags.reset_logging
    
    def update_flag(self, category: str, flag_name: str, value: Any) -> bool:
        """Update a specific feature flag value."""
        try:
            if category == 'experience_extraction':
                if hasattr(self.flags.experience_extraction, flag_name):
                    setattr(self.flags.experience_extraction, flag_name, value)
                    self.logger.info(f"FEATURE_FLAGS: updated {category}.{flag_name} = {value}")
                    return True
            elif category == 'performance':
                if hasattr(self.flags.performance, flag_name):
                    setattr(self.flags.performance, flag_name, value)
                    self.logger.info(f"FEATURE_FLAGS: updated {category}.{flag_name} = {value}")
                    return True
            elif category == 'quality_guardrails':
                if hasattr(self.flags.quality_guardrails, flag_name):
                    setattr(self.flags.quality_guardrails, flag_name, value)
                    self.logger.info(f"FEATURE_FLAGS: updated {category}.{flag_name} = {value}")
                    return True
            elif category == 'debugging':
                if hasattr(self.flags.debugging, flag_name):
                    setattr(self.flags.debugging, flag_name, value)
                    self.logger.info(f"FEATURE_FLAGS: updated {category}.{flag_name} = {value}")
                    return True
            elif category == 'extraction_fixes':
                if hasattr(self.flags.extraction_fixes, flag_name):
                    setattr(self.flags.extraction_fixes, flag_name, value)
                    self.logger.info(f"FEATURE_FLAGS: updated {category}.{flag_name} = {value}")
                    return True
            elif category == 'phases_a_to_h':
                if hasattr(self.flags.phases_a_to_h, flag_name):
                    setattr(self.flags.phases_a_to_h, flag_name, value)
                    self.logger.info(f"FEATURE_FLAGS: updated {category}.{flag_name} = {value}")
                    return True
            elif category == 'reset_logging':
                if hasattr(self.flags.reset_logging, flag_name):
                    setattr(self.flags.reset_logging, flag_name, value)
                    self.logger.info(f"FEATURE_FLAGS: updated {category}.{flag_name} = {value}")
                    return True
            
            self.logger.warning(f"FEATURE_FLAGS: unknown flag {category}.{flag_name}")
            return False
            
        except Exception as e:
            self.logger.error(f"FEATURE_FLAGS: failed to update {category}.{flag_name} | error={e}")
            return False
    
    def is_enabled(self, category: str, flag_name: str) -> bool:
        """Check if a specific feature flag is enabled."""
        try:
            if category == 'experience_extraction':
                return getattr(self.flags.experience_extraction, flag_name, False)
            elif category == 'performance':
                return getattr(self.flags.performance, flag_name, False)
            elif category == 'quality_guardrails':
                return getattr(self.flags.quality_guardrails, flag_name, False)
            elif category == 'debugging':
                return getattr(self.flags.debugging, flag_name, False)
            elif category == 'extraction_fixes':
                return getattr(self.flags.extraction_fixes, flag_name, False)
            elif category == 'phases_a_to_h':
                return getattr(self.flags.phases_a_to_h, flag_name, False)
            elif category == 'reset_logging':
                return getattr(self.flags.reset_logging, flag_name, False)
            else:
                return False
        except:
            return False
    
    def get_config_summary(self) -> Dict[str, Any]:
        """Get summary of current configuration."""
        return {
            'config_path': str(self.config_path),
            'experience_extraction': asdict(self.flags.experience_extraction),
            'performance': asdict(self.flags.performance),
            'quality_guardrails': asdict(self.flags.quality_guardrails),
            'debugging': asdict(self.flags.debugging),
            'feature_counts': {
                'experience_flags': len([k for k, v in asdict(self.flags.experience_extraction).items() if isinstance(v, bool) and v]),
                'performance_flags': len([k for k, v in asdict(self.flags.performance).items() if isinstance(v, bool) and v]),
                'quality_guardrails_flags': len([k for k, v in asdict(self.flags.quality_guardrails).items() if isinstance(v, bool) and v]),
                'debugging_flags': len([k for k, v in asdict(self.flags.debugging).items() if isinstance(v, bool) and v]),
            }
        }


# Global feature flag manager instance
_feature_flag_manager = None

def get_feature_flag_manager(config_path: Optional[Path] = None) -> FeatureFlagManager:
    """Get singleton feature flag manager instance."""
    global _feature_flag_manager
    if _feature_flag_manager is None:
        _feature_flag_manager = FeatureFlagManager(config_path)
    return _feature_flag_manager


# Convenience functions for easy access
def get_experience_flags() -> ExperienceExtractionFlags:
    """Get experience extraction feature flags."""
    return get_feature_flag_manager().get_experience_flags()


def get_performance_flags() -> PerformanceFlags:
    """Get performance feature flags."""
    return get_feature_flag_manager().get_performance_flags()


def get_quality_guardrails_flags() -> QualityGuardrailsFlags:
    """Get quality guardrails feature flags."""
    return get_feature_flag_manager().get_quality_guardrails_flags()


def get_debugging_flags() -> DebuggingFlags:
    """Get debugging feature flags."""  
    return get_feature_flag_manager().get_debugging_flags()


def get_extraction_fixes_flags() -> ExtractionFixesFlags:
    """Get extraction fixes feature flags."""
    return get_feature_flag_manager().get_extraction_fixes_flags()


def get_phases_a_to_h_flags() -> PhasesAToHFlags:
    """Get Phases A-H feature flags."""
    return get_feature_flag_manager().get_phases_a_to_h_flags()


def get_reset_logging_flags() -> ResetLoggingFlags:
    """Get reset logging feature flags."""
    return get_feature_flag_manager().get_reset_logging_flags()


def is_feature_enabled(category: str, flag_name: str) -> bool:
    """Check if a specific feature is enabled."""
    return get_feature_flag_manager().is_enabled(category, flag_name)


def update_feature_flag(category: str, flag_name: str, value: Any) -> bool:
    """Update a feature flag value."""
    return get_feature_flag_manager().update_flag(category, flag_name, value)


def save_feature_flags() -> bool:
    """Save current feature flags to file."""
    return get_feature_flag_manager().save_to_file()


def reload_feature_flags() -> bool:
    """Reload feature flags from file."""
    return get_feature_flag_manager().load_from_file()


# Development helpers
def enable_debug_mode():
    """Enable comprehensive debugging features."""
    manager = get_feature_flag_manager()
    manager.update_flag('debugging', 'enable_detailed_rejection_logging', True)
    manager.update_flag('debugging', 'enable_pattern_match_details', True)
    manager.update_flag('debugging', 'enable_confidence_breakdown_logging', True)
    manager.update_flag('debugging', 'enable_qa_decision_logging', True)
    logger.info("FEATURE_FLAGS: debug mode enabled")


def disable_heavy_features():
    """Disable performance-heavy features for faster processing."""
    manager = get_feature_flag_manager()
    manager.update_flag('experience_extraction', 'enable_org_classification', False)
    manager.update_flag('experience_extraction', 'enable_temporal_validation', False)
    manager.update_flag('experience_extraction', 'enable_debug_sampling', False)
    manager.update_flag('performance', 'max_lines_per_section', 500)
    logger.info("FEATURE_FLAGS: heavy features disabled for performance")


# Phase A-H specific flag checkers
def is_boundary_guards_enabled() -> bool:
    """Check if boundary guards are enabled."""
    return is_feature_enabled('phases_a_to_h', 'boundary_guards_enabled')


def is_phase1_gating_2tier_enabled() -> bool:
    """Check if 2-tier Phase-1 gating is enabled."""
    return is_feature_enabled('phases_a_to_h', 'phase1_gating_2tier_enabled')


def is_projects_v2_enabled() -> bool:
    """Check if Projects V2 extractor is enabled."""
    return is_feature_enabled('phases_a_to_h', 'projects_v2_enabled')


def is_french_date_normalization_enabled() -> bool:
    """Check if French date normalization is enabled."""
    return is_feature_enabled('phases_a_to_h', 'french_date_normalization_enabled')


def is_org_sieve_filtering_enabled() -> bool:
    """Check if organization sieve filtering is enabled."""
    return is_feature_enabled('phases_a_to_h', 'org_sieve_filtering_enabled')


def is_experience_parser_dedicated_enabled() -> bool:
    """Check if dedicated experience parser is enabled."""
    return is_feature_enabled('phases_a_to_h', 'experience_parser_dedicated_enabled')


def is_education_parser_dedicated_enabled() -> bool:
    """Check if dedicated education parser is enabled."""
    return is_feature_enabled('phases_a_to_h', 'education_parser_dedicated_enabled')


def is_soft_skills_v2_conservative_enabled() -> bool:
    """Check if conservative soft skills V2 is enabled."""
    return is_feature_enabled('phases_a_to_h', 'soft_skills_v2_conservative_enabled')


def is_pattern_quality_analysis_enabled() -> bool:
    """Check if pattern quality analysis is enabled."""
    return is_feature_enabled('phases_a_to_h', 'pattern_quality_analysis_enabled')


def is_unified_reporting_postmapping_enabled() -> bool:
    """Check if post-mapping unified reporting is enabled."""
    return is_feature_enabled('phases_a_to_h', 'unified_reporting_postmapping_enabled')


def is_reset_logging_enabled() -> bool:
    """Check if reset logging is enabled."""
    return is_feature_enabled('reset_logging', 'enabled')