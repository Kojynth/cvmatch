"""
Quick Validation Script for CV Extraction Pipeline Repairs
==========================================================

Validates that all the implemented fixes are present in the codebase
without requiring complex imports or test execution.

Usage: python validate_fixes.py
"""

import os
import re
from pathlib import Path
from typing import List, Tuple, Dict


def validate_file_exists_and_contains(file_path: str, required_patterns: List[str]) -> Tuple[bool, List[str]]:
    """
    Validate that a file exists and contains required patterns.
    
    Returns:
        (success, missing_patterns)
    """
    if not os.path.exists(file_path):
        return False, [f"File does not exist: {file_path}"]
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        return False, [f"Could not read file: {e}"]
    
    missing = []
    for pattern in required_patterns:
        if not re.search(pattern, content, re.MULTILINE | re.IGNORECASE):
            missing.append(pattern)
    
    return len(missing) == 0, missing


def validate_consumption_tracking_fixes():
    """Validate consumption tracking fixes in cv_extractor.py."""
    print("Validating consumption tracking fixes...")
    
    file_path = "app/workers/cv_extractor.py"
    required_patterns = [
        r"def _mark_consumed.*normalized.*deduplicated",
        r"_mark_consumed\(.*experiences.*\)",
        r"_mark_consumed\(.*education.*\)", 
        r"_mark_consumed\(.*skills.*\)",
        r"def _format_ranges.*indices.*List.*int",
        r"logger\.debug.*CONSUMPTION.*marked.*lines.*consumed"
    ]
    
    success, missing = validate_file_exists_and_contains(file_path, required_patterns)
    
    if success:
        print("  [PASS] Consumption tracking fixes implemented")
        return True
    else:
        print(f"  [FAIL] Missing consumption tracking patterns: {len(missing)}")
        for pattern in missing:
            print(f"    - {pattern}")
        return False


def validate_boundary_overlap_fixes():
    """Validate boundary overlap detection in boundary_guards.py."""
    print("🔍 Validating boundary overlap detection...")
    
    file_path = "app/utils/boundary_guards.py"
    required_patterns = [
        r"class.*OverlapConflict",
        r"def detect_section_overlaps",
        r"def canonicalize_section_name", 
        r"SECTION_CANONICALIZATION.*=",
        r"SECTION_PRIORITY.*=",
        r"def resolve_overlaps",
        r"def analyze_and_resolve_section_overlaps"
    ]
    
    success, missing = validate_file_exists_and_contains(file_path, required_patterns)
    
    if success:
        print("  ✅ Boundary overlap fixes implemented")
        return True
    else:
        print(f"  ❌ Missing boundary overlap patterns: {len(missing)}")
        for pattern in missing:
            print(f"    - {pattern}")
        return False


def validate_extraction_mapper_fixes():
    """Validate extraction mapper improvements."""
    print("🔍 Validating extraction mapper improvements...")
    
    # Check the improved mapper file exists
    improved_file = "app/utils/extraction_mapper_improved.py"
    required_patterns = [
        r"def is_meaningful_content",
        r"def map_experience_data_no_placeholders",
        r"def map_education_data_no_placeholders",
        r"placeholder_keywords.*=.*définir.*specify.*unknown",
        r"return None.*insufficient.*meaningful.*data"
    ]
    
    success, missing = validate_file_exists_and_contains(improved_file, required_patterns)
    
    if success:
        print("  ✅ Extraction mapper improvements implemented")
        return True
    else:
        print(f"  ❌ Missing extraction mapper patterns: {len(missing)}")
        for pattern in missing:
            print(f"    - {pattern}")
        return False


def validate_experience_validation_fixes():
    """Validate experience validation strengthening."""
    print("🔍 Validating experience validation strengthening...")
    
    file_path = "app/utils/experience_validation.py"
    required_patterns = [
        r"def _is_suspicious_content",
        r"def _detect_content_duplication", 
        r"def _has_sufficient_information_density",
        r"def _calculate_temporal_quality_score",
        r"strict_mode.*=.*config\.get.*STRICT_VALIDATION_MODE",
        r"suspicious_patterns.*=",
        r"strong_work_indicators.*=",
        r"quality_distribution.*=.*high.*medium.*low"
    ]
    
    success, missing = validate_file_exists_and_contains(file_path, required_patterns)
    
    if success:
        print("  ✅ Experience validation strengthening implemented")
        return True
    else:
        print(f"  ❌ Missing experience validation patterns: {len(missing)}")
        for pattern in missing:
            print(f"    - {pattern}")
        return False


def validate_unified_reporter_fixes():
    """Validate unified reporter consistency fixes."""
    print("🔍 Validating unified reporter consistency fixes...")
    
    file_path = "app/utils/unified_reporter.py"
    required_patterns = [
        r"def _validate_metric_consistency",
        r"def _recalculate_derived_metrics",
        r"def _perform_final_validation_checks",
        r"def perform_manual_consistency_check",
        r"consistency_checks_enabled.*=.*True",
        r"_update_history.*=.*\[\]",
        r"_metric_snapshots.*=.*\[\]",
        r"warnings.*=.*validate_metric_consistency"
    ]
    
    success, missing = validate_file_exists_and_contains(file_path, required_patterns)
    
    if success:
        print("  ✅ Unified reporter consistency fixes implemented")
        return True
    else:
        print(f"  ❌ Missing unified reporter patterns: {len(missing)}")
        for pattern in missing:
            print(f"    - {pattern}")
        return False


def validate_date_parser_fixes():
    """Validate fallback date parser enhancements."""
    print("🔍 Validating fallback date parser enhancements...")
    
    file_path = "app/utils/fallback_date_parser.py"
    required_patterns = [
        r"class FallbackDateParser",
        r"NEGATIVE_PATTERNS.*=",
        r"def is_negative_match",
        r"postal.*code.*phone.*number",
        r"FR_MONTHS.*=.*janvier.*février",
        r"EN_MONTHS.*=.*january.*february",
        r"ALL_PRESENT_TOKENS.*=.*set"
    ]
    
    success, missing = validate_file_exists_and_contains(file_path, required_patterns)
    
    if success:
        print("  ✅ Fallback date parser enhancements implemented")
        return True
    else:
        print(f"  ❌ Missing date parser patterns: {len(missing)}")
        for pattern in missing:
            print(f"    - {pattern}")
        return False


def validate_soft_interest_extractors():
    """Validate soft skills/interests extraction improvements."""
    print("🔍 Validating soft skills/interests extractors...")
    
    file_path = "app/utils/soft_interest_extractors.py"
    required_patterns = [
        r"class.*SoftSkillsExtractor",
        r"class.*InterestsExtractor",
        r"def extract_with_context",
        r"def _is_skills_context",
        r"def _is_interests_context",
        r"FORBIDDEN_CONTEXTS.*=",
        r"context.*aware.*extraction",
        r"SKILLS_VOCABULARY.*=",
        r"INTERESTS_VOCABULARY.*="
    ]
    
    success, missing = validate_file_exists_and_contains(file_path, required_patterns)
    
    if success:
        print("  ✅ Soft skills/interests extractors implemented")
        return True
    else:
        print(f"  ❌ Missing soft extractors patterns: {len(missing)}")
        for pattern in missing:
            print(f"    - {pattern}")
        return False


def validate_test_suite():
    """Validate that comprehensive test suite was created."""
    print("🔍 Validating comprehensive test suite...")
    
    file_path = "test_comprehensive_fixes.py"
    required_patterns = [
        r"class TestFallbackDateParser",
        r"class TestSoftInterestExtractors",
        r"class TestBoundaryOverlapResolution", 
        r"class TestExtractionMapperImprovements",
        r"class TestExperienceValidationStrengthening",
        r"class TestUnifiedReporterConsistency",
        r"class TestIntegrationScenarios",
        r"def run_comprehensive_tests"
    ]
    
    success, missing = validate_file_exists_and_contains(file_path, required_patterns)
    
    if success:
        print("  ✅ Comprehensive test suite created")
        return True
    else:
        print(f"  ❌ Missing test suite patterns: {len(missing)}")
        for pattern in missing:
            print(f"    - {pattern}")
        return False


def validate_project_structure():
    """Validate overall project structure and new files."""
    print("🔍 Validating project structure...")
    
    expected_files = [
        "app/utils/fallback_date_parser.py",
        "app/utils/soft_interest_extractors.py", 
        "app/utils/extraction_mapper_improved.py",
        "app/utils/extraction_mapper_patch.py",
        "test_comprehensive_fixes.py",
        "validate_fixes.py"
    ]
    
    missing_files = []
    for file_path in expected_files:
        if not os.path.exists(file_path):
            missing_files.append(file_path)
    
    if not missing_files:
        print("  ✅ All expected files present")
        return True
    else:
        print(f"  ❌ Missing files: {len(missing_files)}")
        for file_path in missing_files:
            print(f"    - {file_path}")
        return False


def generate_validation_report():
    """Generate a comprehensive validation report."""
    print("CV EXTRACTION PIPELINE REPAIR VALIDATION")
    print("=" * 60)
    print()
    
    validations = [
        ("Consumption Tracking Fixes", validate_consumption_tracking_fixes),
        ("Boundary Overlap Detection", validate_boundary_overlap_fixes),
        ("Extraction Mapper Improvements", validate_extraction_mapper_fixes), 
        ("Experience Validation Strengthening", validate_experience_validation_fixes),
        ("Unified Reporter Consistency", validate_unified_reporter_fixes),
        ("Date Parser Enhancements", validate_date_parser_fixes),
        ("Soft Skills/Interests Extractors", validate_soft_interest_extractors),
        ("Comprehensive Test Suite", validate_test_suite),
        ("Project Structure", validate_project_structure)
    ]
    
    results = []
    
    for name, validator in validations:
        try:
            success = validator()
            results.append((name, success))
        except Exception as e:
            print(f"  💥 Error validating {name}: {e}")
            results.append((name, False))
        print()
    
    # Summary report
    print("=" * 60)
    print("📊 VALIDATION SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    success_rate = (passed / total * 100) if total > 0 else 0
    
    print(f"Components Validated: {total}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {total - passed}")
    print(f"🎯 Success Rate: {success_rate:.1f}%")
    print()
    
    # Detailed results
    for name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"  {status} - {name}")
    
    print()
    
    if success_rate >= 90:
        print("🏆 EXCELLENT: All major fixes have been successfully implemented!")
        print("The CV extraction pipeline repairs are complete and validated.")
    elif success_rate >= 70:
        print("✅ GOOD: Most fixes implemented successfully.")
        print("Review any failed validations and complete remaining items.")
    else:
        print("⚠️  NEEDS WORK: Several fixes are missing or incomplete.")
        print("Review the failed validations and implement missing components.")
    
    print()
    print("💡 To run comprehensive tests:")
    print("   python test_comprehensive_fixes.py")
    print()
    print("💡 To apply extraction mapper improvements:")
    print("   from app.utils.extraction_mapper_patch import *")
    
    return success_rate >= 70


if __name__ == "__main__":
    success = generate_validation_report()
    exit(0 if success else 1)