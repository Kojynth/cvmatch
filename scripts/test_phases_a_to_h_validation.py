#!/usr/bin/env python3
"""
Validation script for Phases A through H implementations.

Performs comprehensive testing of all implemented enhancements including:
- Boundary guards and residual ledger
- 2-tier Phase-1 gating  
- Projects V2 extractor with no-progress guard
- French date normalization and org sieve
- Dedicated experience and education parsers
- Conservative soft skills V2 extractor
- Pattern quality analysis with fail-fast
- Unified reporting with post-mapping validation
- Feature flags system integration
- Reset logging system

Usage:
    python scripts/test_phases_a_to_h_validation.py
"""

import sys
import traceback
from pathlib import Path
import json
from typing import Dict, List, Any, Optional
import logging

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import all Phase A-H components
try:
    from app.utils.boundary_guards import ResidualLedger, assert_no_overlap, merge_overlapping_boundaries
    from app.utils.projects_extractor_v2 import ProjectsExtractorV2
    from app.utils.fallback_date_parser import FallbackDateParser
    from app.utils.org_sieve import SchoolLexicon
    from app.parsers.experience_parser import ExperienceParser
    from app.parsers.education_parser import EducationParser
    from app.utils.soft_skills_v2 import SoftSkillsV2
    from app.utils.experience_filters import PatternQualityAnalyzer
    from app.utils.unified_reporter import UnifiedReporter
    from app.utils.feature_flags import (
        get_phases_a_to_h_flags, is_boundary_guards_enabled,
        is_projects_v2_enabled, get_feature_flag_manager
    )
    from app.utils.reset_logger import ResetLogger
    from app.logging.safe_logger import get_safe_logger
    from app.config import DEFAULT_PII_CONFIG
    
    print("✅ All Phase A-H imports successful")
    
except ImportError as e:
    print(f"❌ Import error: {e}")
    traceback.print_exc()
    sys.exit(1)

# Initialize logger
logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


class PhasesValidationRunner:
    """Comprehensive validation runner for Phases A-H."""
    
    def __init__(self):
        """Initialize validation runner."""
        self.results = {
            "phase_a": {"name": "Boundary Guards & Residual Ledger", "tests": [], "passed": 0, "failed": 0},
            "phase_b": {"name": "2-tier Phase-1 Gating", "tests": [], "passed": 0, "failed": 0},
            "phase_c": {"name": "Projects V2 with No-Progress Guard", "tests": [], "passed": 0, "failed": 0},
            "phase_d": {"name": "French Date Normalization & Org Sieve", "tests": [], "passed": 0, "failed": 0},
            "phase_e": {"name": "Dedicated Section Parsers", "tests": [], "passed": 0, "failed": 0},
            "phase_f": {"name": "Conservative Soft Skills V2", "tests": [], "passed": 0, "failed": 0},
            "phase_g": {"name": "Pattern Quality Analysis", "tests": [], "passed": 0, "failed": 0},
            "phase_h": {"name": "Unified Reporting Post-Mapping", "tests": [], "passed": 0, "failed": 0},
            "integration": {"name": "Feature Flags & Integration", "tests": [], "passed": 0, "failed": 0},
            "reset_logging": {"name": "Reset Logging System", "tests": [], "passed": 0, "failed": 0}
        }
        self.total_tests = 0
        self.total_passed = 0
        
    def run_test(self, phase: str, test_name: str, test_func):
        """Run a single test and record results."""
        self.total_tests += 1
        
        try:
            test_func()
            self.results[phase]["tests"].append({"name": test_name, "status": "PASSED", "error": None})
            self.results[phase]["passed"] += 1
            self.total_passed += 1
            print(f"  ✅ {test_name}")
        except Exception as e:
            self.results[phase]["tests"].append({"name": test_name, "status": "FAILED", "error": str(e)})
            self.results[phase]["failed"] += 1
            print(f"  ❌ {test_name}: {e}")
            
    def validate_phase_a(self):
        """Validate Phase A: Boundary Guards & Residual Ledger."""
        print("\n🔍 Phase A: Boundary Guards & Residual Ledger")
        
        def test_residual_ledger_basic():
            ledger = ResidualLedger()
            ledger.consume_lines("test", [0, 1, 2])
            assert ledger.get_line_owner(0) == "test"
            assert ledger.get_line_owner(5) is None
            
        def test_overlap_detection():
            ledger = ResidualLedger()
            ledger.consume_lines("consumer1", [0, 1])
            try:
                ledger.consume_lines("consumer2", [1, 2])  # Should raise
                assert False, "Should have raised overlap error"
            except ValueError:
                pass  # Expected
                
        def test_assert_no_overlap():
            boundaries = [{'start': 0, 'end': 5}, {'start': 10, 'end': 15}]
            assert_no_overlap(boundaries)  # Should not raise
            
        def test_merge_overlapping():
            boundaries = [
                {'start': 0, 'end': 10, 'section': 'A'},
                {'start': 5, 'end': 15, 'section': 'B'}
            ]
            merged = merge_overlapping_boundaries(boundaries)
            assert len(merged) == 1
            assert merged[0]['end'] == 15
            
        self.run_test("phase_a", "Residual Ledger Basic Operations", test_residual_ledger_basic)
        self.run_test("phase_a", "Overlap Detection", test_overlap_detection)
        self.run_test("phase_a", "Boundary Overlap Assertion", test_assert_no_overlap)
        self.run_test("phase_a", "Overlapping Boundaries Merge", test_merge_overlapping)
        
    def validate_phase_b(self):
        """Validate Phase B: 2-tier Phase-1 Gating."""
        print("\n🔍 Phase B: 2-tier Phase-1 Gating")
        
        def test_2tier_policy_exists():
            # Test that the gating policy components exist
            from app.workers.cv_extractor import CVExtractorWorker
            # Just test instantiation for now
            assert CVExtractorWorker is not None
            
        def test_gating_flags():
            flags = get_phases_a_to_h_flags()
            assert hasattr(flags, 'phase1_gating_2tier_enabled')
            assert hasattr(flags, 'soft_gate_min_chars')
            assert flags.soft_gate_min_chars == 80
            
        self.run_test("phase_b", "2-tier Policy Class Exists", test_2tier_policy_exists)
        self.run_test("phase_b", "Gating Configuration Flags", test_gating_flags)
        
    def validate_phase_c(self):
        """Validate Phase C: Projects V2 with No-Progress Guard."""
        print("\n🔍 Phase C: Projects V2 with No-Progress Guard")
        
        def test_projects_v2_initialization():
            extractor = ProjectsExtractorV2()
            assert extractor is not None
            assert hasattr(extractor, '_extract_with_no_progress_guard')
            
        def test_no_progress_guard_mechanism():
            extractor = ProjectsExtractorV2()
            # Test empty lines scenario
            result = extractor._extract_with_no_progress_guard([], slice(0, 0))
            assert isinstance(result, list)
            
        def test_projects_flags():
            flags = get_phases_a_to_h_flags()
            assert flags.projects_v2_enabled is True
            assert flags.max_pass_limit == 3
            
        self.run_test("phase_c", "Projects V2 Initialization", test_projects_v2_initialization)
        self.run_test("phase_c", "No-Progress Guard Mechanism", test_no_progress_guard_mechanism)
        self.run_test("phase_c", "Projects V2 Configuration Flags", test_projects_flags)
        
    def validate_phase_d(self):
        """Validate Phase D: French Date Normalization & Org Sieve."""
        print("\n🔍 Phase D: French Date Normalization & Org Sieve")
        
        def test_french_date_parser():
            parser = FallbackDateParser()
            assert hasattr(parser, 'parse_date_french')
            assert hasattr(parser, 'convert_two_digit_year')
            
        def test_two_digit_year_conversion():
            parser = FallbackDateParser()
            # Test 2-digit year conversion rules
            assert parser.convert_two_digit_year(23) == 2023  # 00-24 -> 2000s
            assert parser.convert_two_digit_year(95) == 1995  # 25-99 -> 1900s
            
        def test_org_sieve_functionality():
            sieve = SchoolLexicon()
            assert hasattr(sieve, 'should_reject_as_organization')
            
        def test_postal_code_rejection():
            sieve = SchoolLexicon()
            assert sieve.should_reject_as_organization("75001") is True
            assert sieve.should_reject_as_organization("13000 Marseille") is True
            
        def test_month_name_rejection():
            sieve = SchoolLexicon()
            assert sieve.should_reject_as_organization("janvier") is True
            assert sieve.should_reject_as_organization("février") is True
            
        self.run_test("phase_d", "French Date Parser Initialization", test_french_date_parser)
        self.run_test("phase_d", "Two-Digit Year Conversion", test_two_digit_year_conversion)
        self.run_test("phase_d", "Organization Sieve Functionality", test_org_sieve_functionality)
        self.run_test("phase_d", "Postal Code Rejection", test_postal_code_rejection)
        self.run_test("phase_d", "Month Name Rejection", test_month_name_rejection)
        
    def validate_phase_e(self):
        """Validate Phase E: Dedicated Section Parsers."""
        print("\n🔍 Phase E: Dedicated Section Parsers")
        
        def test_experience_parser():
            parser = ExperienceParser()
            assert hasattr(parser, 'parse_experience_section')
            assert hasattr(parser, '_validate_and_enrich_entry')
            
        def test_education_parser():
            parser = EducationParser()
            assert hasattr(parser, 'parse_education_section')
            assert hasattr(parser, '_classify_degree')
            
        def test_french_education_classification():
            parser = EducationParser()
            result = parser._classify_degree("Master en Informatique")
            assert "level" in result
            assert "category" in result
            
        def test_experience_validation():
            parser = ExperienceParser()
            entry = {
                "role": "Developer",
                "organization": "TechCorp",
                "start_date": "2022",
                "end_date": "2024"
            }
            result = parser._validate_and_enrich_entry(entry)
            assert result is not None
            
        self.run_test("phase_e", "Experience Parser Initialization", test_experience_parser)
        self.run_test("phase_e", "Education Parser Initialization", test_education_parser)
        self.run_test("phase_e", "French Education Classification", test_french_education_classification)
        self.run_test("phase_e", "Experience Entry Validation", test_experience_validation)
        
    def validate_phase_f(self):
        """Validate Phase F: Conservative Soft Skills V2."""
        print("\n🔍 Phase F: Conservative Soft Skills V2")
        
        def test_soft_skills_v2_initialization():
            extractor = SoftSkillsV2()
            assert hasattr(extractor, 'extract_soft_skills')
            assert hasattr(extractor, '_validate_statistical')
            
        def test_conservative_thresholds():
            extractor = SoftSkillsV2()
            assert extractor.quality_threshold >= 0.7  # Conservative threshold
            assert extractor.min_confidence >= 0.6
            
        def test_extraction_basic():
            extractor = SoftSkillsV2()
            lines = ["Communication, Leadership, Teamwork"]
            result = extractor.extract_soft_skills(lines)
            assert isinstance(result, list)
            
        self.run_test("phase_f", "Soft Skills V2 Initialization", test_soft_skills_v2_initialization)
        self.run_test("phase_f", "Conservative Thresholds", test_conservative_thresholds)
        self.run_test("phase_f", "Basic Extraction", test_extraction_basic)
        
    def validate_phase_g(self):
        """Validate Phase G: Pattern Quality Analysis."""
        print("\n🔍 Phase G: Pattern Quality Analysis")
        
        def test_pattern_quality_analyzer():
            analyzer = PatternQualityAnalyzer()
            assert hasattr(analyzer, 'analyze_pattern_quality')
            assert hasattr(analyzer, '_calculate_pattern_diversity')
            
        def test_diversity_calculation():
            analyzer = PatternQualityAnalyzer()
            patterns = [
                {"pattern": "Pattern1", "weight": 0.4},
                {"pattern": "Pattern2", "weight": 0.3},
                {"pattern": "Pattern3", "weight": 0.3}
            ]
            diversity = analyzer._calculate_pattern_diversity(patterns)
            assert 0.0 <= diversity <= 1.0
            
        def test_fail_fast_mechanism():
            analyzer = PatternQualityAnalyzer()
            # Test with poor patterns
            poor_patterns = [{"pattern": "Same", "weight": 1.0}]
            result = analyzer.analyze_pattern_quality(poor_patterns)
            assert "quality_score" in result
            assert "fail_fast_triggered" in result
            
        self.run_test("phase_g", "Pattern Quality Analyzer Initialization", test_pattern_quality_analyzer)
        self.run_test("phase_g", "Diversity Calculation", test_diversity_calculation)
        self.run_test("phase_g", "Fail-Fast Mechanism", test_fail_fast_mechanism)
        
    def validate_phase_h(self):
        """Validate Phase H: Unified Reporting Post-Mapping."""
        print("\n🔍 Phase H: Unified Reporting Post-Mapping")
        
        def test_unified_reporter():
            reporter = UnifiedReporter()
            assert hasattr(reporter, 'perform_post_mapping_validation')
            assert hasattr(reporter, '_validate_extraction_to_mapping_consistency')
            
        def test_post_mapping_validation():
            reporter = UnifiedReporter()
            extraction = {"experience": [{"role": "Dev"}]}
            mapping = {"experience": [{"title": "Dev"}]}
            result = reporter.perform_post_mapping_validation(extraction, mapping)
            assert "validation_success" in result
            assert "consistency_score" in result
            
        def test_cross_section_coherence():
            reporter = UnifiedReporter()
            sections = {"exp": [{"senior": True}], "edu": [{"level": "bachelor"}]}
            result = reporter._analyze_cross_section_coherence(sections)
            assert "coherence_score" in result
            
        self.run_test("phase_h", "Unified Reporter Initialization", test_unified_reporter)
        self.run_test("phase_h", "Post-Mapping Validation", test_post_mapping_validation)
        self.run_test("phase_h", "Cross-Section Coherence", test_cross_section_coherence)
        
    def validate_integration(self):
        """Validate feature flags and integration."""
        print("\n🔍 Integration: Feature Flags & System Integration")
        
        def test_feature_flags_manager():
            manager = get_feature_flag_manager()
            assert manager is not None
            assert hasattr(manager, 'get_phases_a_to_h_flags')
            
        def test_all_phase_flags():
            flags = get_phases_a_to_h_flags()
            required_flags = [
                'boundary_guards_enabled', 'phase1_gating_2tier_enabled',
                'projects_v2_enabled', 'french_date_normalization_enabled',
                'experience_parser_dedicated_enabled', 'education_parser_dedicated_enabled',
                'soft_skills_v2_conservative_enabled', 'pattern_quality_analysis_enabled',
                'unified_reporting_postmapping_enabled'
            ]
            
            for flag in required_flags:
                assert hasattr(flags, flag), f"Missing flag: {flag}"
                
        def test_flag_accessibility():
            assert is_boundary_guards_enabled() in [True, False]
            assert is_projects_v2_enabled() in [True, False]
            
        self.run_test("integration", "Feature Flags Manager", test_feature_flags_manager)
        self.run_test("integration", "All Phase Flags Present", test_all_phase_flags)
        self.run_test("integration", "Flag Accessibility Functions", test_flag_accessibility)
        
    def validate_reset_logging(self):
        """Validate reset logging system."""
        print("\n🔍 Reset Logging System")
        
        def test_reset_logger_initialization():
            logger = ResetLogger()
            assert logger is not None
            assert hasattr(logger, 'start_reset_operation')
            
        def test_operation_lifecycle():
            logger = ResetLogger()
            op_id = logger.start_reset_operation("test", {})
            assert op_id is not None
            result = logger.complete_reset_operation(op_id, {"success": True})
            assert result is True
            
        self.run_test("reset_logging", "Reset Logger Initialization", test_reset_logger_initialization)
        self.run_test("reset_logging", "Operation Lifecycle", test_operation_lifecycle)
        
    def generate_report(self):
        """Generate comprehensive validation report."""
        print("\n" + "="*80)
        print("📊 PHASES A-H VALIDATION REPORT")
        print("="*80)
        
        for phase_id, phase_data in self.results.items():
            total = phase_data["passed"] + phase_data["failed"]
            if total == 0:
                continue
                
            success_rate = (phase_data["passed"] / total) * 100
            status_icon = "✅" if phase_data["failed"] == 0 else "❌"
            
            print(f"\n{status_icon} {phase_data['name']}")
            print(f"   Passed: {phase_data['passed']}/{total} ({success_rate:.1f}%)")
            
            if phase_data["failed"] > 0:
                print("   Failed tests:")
                for test in phase_data["tests"]:
                    if test["status"] == "FAILED":
                        print(f"     - {test['name']}: {test['error']}")
                        
        overall_success = (self.total_passed / self.total_tests) * 100
        print(f"\n{'='*80}")
        print(f"🎯 OVERALL RESULTS: {self.total_passed}/{self.total_tests} tests passed ({overall_success:.1f}%)")
        
        if self.total_passed == self.total_tests:
            print("🎉 ALL PHASES A-H IMPLEMENTATIONS VALIDATED SUCCESSFULLY!")
        else:
            print("⚠️  Some tests failed - review implementation details above")
            
        return {
            "total_tests": self.total_tests,
            "total_passed": self.total_passed,
            "success_rate": overall_success,
            "details": self.results
        }
        
    def save_report(self, filename: str):
        """Save validation report to file."""
        report_data = {
            "validation_timestamp": "2024-09-06",
            "total_tests": self.total_tests,
            "total_passed": self.total_passed,
            "success_rate": (self.total_passed / self.total_tests) * 100 if self.total_tests > 0 else 0,
            "phases": self.results
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)
            
        print(f"📄 Report saved to: {filename}")


def main():
    """Run comprehensive Phases A-H validation."""
    print("🚀 Starting Phases A-H Comprehensive Validation")
    print("="*80)
    
    runner = PhasesValidationRunner()
    
    try:
        # Run all phase validations
        runner.validate_phase_a()
        runner.validate_phase_b()
        runner.validate_phase_c()
        runner.validate_phase_d()
        runner.validate_phase_e()
        runner.validate_phase_f()
        runner.validate_phase_g()
        runner.validate_phase_h()
        runner.validate_integration()
        runner.validate_reset_logging()
        
        # Generate and save report
        runner.generate_report()
        
        report_file = project_root / "scripts" / "phases_a_to_h_validation_report.json"
        runner.save_report(report_file)
        
        # Return success code based on results
        if runner.total_passed == runner.total_tests:
            return 0
        else:
            return 1
            
    except Exception as e:
        print(f"❌ Validation failed with error: {e}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())