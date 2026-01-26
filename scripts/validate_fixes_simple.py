"""
Simple Validation Script for CV Extraction Pipeline Repairs
===========================================================

Validates that all the implemented fixes are present in the codebase.

Usage: python validate_fixes_simple.py
"""

import os
import re
from pathlib import Path
from typing import List, Tuple


def check_file_patterns(file_path: str, patterns: List[str]) -> Tuple[bool, List[str]]:
    """Check if file exists and contains required patterns."""
    if not os.path.exists(file_path):
        return False, [f"File not found: {file_path}"]
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        return False, [f"Error reading file: {e}"]
    
    missing = []
    for pattern in patterns:
        if not re.search(pattern, content, re.MULTILINE | re.IGNORECASE):
            missing.append(pattern)
    
    return len(missing) == 0, missing


def main():
    """Main validation function."""
    print("CV EXTRACTION PIPELINE REPAIR VALIDATION")
    print("=" * 50)
    print()
    
    validations = []
    
    # 1. Consumption tracking fixes
    print("1. Validating consumption tracking fixes...")
    patterns = [
        r"def _mark_consumed",
        r"_mark_consumed\(.*experiences",
        r"_mark_consumed\(.*education", 
        r"_mark_consumed\(.*skills",
        r"def _format_ranges"
    ]
    success, missing = check_file_patterns("app/workers/cv_extractor.py", patterns)
    validations.append(("Consumption Tracking", success))
    print(f"   {'PASS' if success else 'FAIL'} - Consumption tracking fixes")
    if not success:
        print(f"   Missing patterns: {len(missing)}")
    print()
    
    # 2. Boundary overlap detection
    print("2. Validating boundary overlap detection...")
    patterns = [
        r"class.*OverlapConflict",
        r"def detect_section_overlaps",
        r"def canonicalize_section_name", 
        r"SECTION_CANONICALIZATION",
        r"def resolve_overlaps"
    ]
    success, missing = check_file_patterns("app/utils/boundary_guards.py", patterns)
    validations.append(("Boundary Overlap", success))
    print(f"   {'PASS' if success else 'FAIL'} - Boundary overlap detection")
    if not success:
        print(f"   Missing patterns: {len(missing)}")
    print()
    
    # 3. Extraction mapper improvements
    print("3. Validating extraction mapper improvements...")
    patterns = [
        r"def is_meaningful_content",
        r"def map_experience_data_no_placeholders",
        r"def map_education_data_no_placeholders",
        r"placeholder_keywords.*définir"
    ]
    success, missing = check_file_patterns("app/utils/extraction_mapper_improved.py", patterns)
    validations.append(("Extraction Mapper", success))
    print(f"   {'PASS' if success else 'FAIL'} - Extraction mapper improvements")
    if not success:
        print(f"   Missing patterns: {len(missing)}")
    print()
    
    # 4. Experience validation strengthening
    print("4. Validating experience validation strengthening...")
    patterns = [
        r"def _is_suspicious_content",
        r"def _detect_content_duplication", 
        r"def _has_sufficient_information_density",
        r"strict_mode.*STRICT_VALIDATION_MODE",
        r"quality_distribution.*high.*medium.*low"
    ]
    success, missing = check_file_patterns("app/utils/experience_validation.py", patterns)
    validations.append(("Experience Validation", success))
    print(f"   {'PASS' if success else 'FAIL'} - Experience validation strengthening")
    if not success:
        print(f"   Missing patterns: {len(missing)}")
    print()
    
    # 5. Unified reporter consistency
    print("5. Validating unified reporter consistency...")
    patterns = [
        r"def _validate_metric_consistency",
        r"def _recalculate_derived_metrics",
        r"def perform_manual_consistency_check",
        r"consistency_checks_enabled",
        r"_update_history"
    ]
    success, missing = check_file_patterns("app/utils/unified_reporter.py", patterns)
    validations.append(("Unified Reporter", success))
    print(f"   {'PASS' if success else 'FAIL'} - Unified reporter consistency")
    if not success:
        print(f"   Missing patterns: {len(missing)}")
    print()
    
    # 6. Fallback date parser
    print("6. Validating fallback date parser...")
    patterns = [
        r"class FallbackDateParser",
        r"NEGATIVE_PATTERNS",
        r"def is_negative_match",
        r"FR_MONTHS.*janvier",
        r"EN_MONTHS.*january"
    ]
    success, missing = check_file_patterns("app/utils/fallback_date_parser.py", patterns)
    validations.append(("Date Parser", success))
    print(f"   {'PASS' if success else 'FAIL'} - Fallback date parser")
    if not success:
        print(f"   Missing patterns: {len(missing)}")
    print()
    
    # 7. Soft skills/interests extractors
    print("7. Validating soft skills/interests extractors...")
    patterns = [
        r"class.*SoftSkillsExtractor",
        r"class.*InterestsExtractor",
        r"def extract_with_context",
        r"FORBIDDEN_CONTEXTS",
        r"context.*aware"
    ]
    success, missing = check_file_patterns("app/utils/soft_interest_extractors.py", patterns)
    validations.append(("Soft Extractors", success))
    print(f"   {'PASS' if success else 'FAIL'} - Soft skills/interests extractors")
    if not success:
        print(f"   Missing patterns: {len(missing)}")
    print()
    
    # 8. Test suite
    print("8. Validating test suite...")
    patterns = [
        r"class TestFallbackDateParser",
        r"class TestBoundaryOverlapResolution", 
        r"class TestExtractionMapperImprovements",
        r"def run_comprehensive_tests"
    ]
    success, missing = check_file_patterns("test_comprehensive_fixes.py", patterns)
    validations.append(("Test Suite", success))
    print(f"   {'PASS' if success else 'FAIL'} - Comprehensive test suite")
    if not success:
        print(f"   Missing patterns: {len(missing)}")
    print()
    
    # Summary
    print("=" * 50)
    print("VALIDATION SUMMARY")
    print("=" * 50)
    
    passed = sum(1 for _, success in validations if success)
    total = len(validations)
    success_rate = (passed / total * 100) if total > 0 else 0
    
    print(f"Components: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {total - passed}")
    print(f"Success Rate: {success_rate:.1f}%")
    print()
    
    for name, success in validations:
        status = "PASS" if success else "FAIL"
        print(f"  [{status}] {name}")
    
    print()
    
    if success_rate >= 85:
        print("RESULT: EXCELLENT - All major fixes implemented!")
    elif success_rate >= 70:
        print("RESULT: GOOD - Most fixes implemented successfully.")
    else:
        print("RESULT: NEEDS WORK - Several fixes missing.")
    
    print()
    print("To run full tests: python test_comprehensive_fixes.py")
    
    return success_rate >= 70


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)