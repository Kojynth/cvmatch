#!/usr/bin/env python3
"""
Test Enhanced Normalizer
========================

Simple validation test for the enhanced normalization functionality.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from cvextractor.normalization import (
    EnhancedNormalizer,
    normalize_date,
    normalize_language_skill,
    clean_field_contamination,
    CEFRLevel
)


def test_date_normalization():
    """Test date normalization functionality."""
    print("=== Testing Date Normalization ===")

    normalizer = EnhancedNormalizer()

    test_cases = [
        "2020 - présent",
        "janvier 2019 - mars 2023",
        "01/2020 - 12/2023",
        "2019-2023",
        "à ce jour",
        "present",
        "2020-03-15",
        "2020-03",
        "depuis 2019 et se poursuit"
    ]

    for test_case in test_cases:
        result = normalizer.normalize_date(test_case, "test_doc")
        print(f"'{test_case}' -> '{result.normalized}' (format: {result.format_type}, conf: {result.confidence:.2f})")

    print()


def test_language_normalization():
    """Test language skill normalization."""
    print("=== Testing Language Normalization ===")

    normalizer = EnhancedNormalizer()

    test_cases = [
        "English B2",
        "Français natif",
        "Spanish fluent",
        "German intermediate",
        "Chinese A1",
        "Italian professional working proficiency",
        "Portuguese mother tongue",
        "Japanese basic"
    ]

    for test_case in test_cases:
        result = normalizer.normalize_language_skill(test_case, "test_doc")
        print(f"'{test_case}' -> {result.cefr_level.value} (conf: {result.confidence:.2f})")

    print()


def test_field_contamination_cleaning():
    """Test field contamination cleaning."""
    print("=== Testing Field Contamination Cleaning ===")

    normalizer = EnhancedNormalizer()

    test_cases = [
        ("Software Engineer 2020-2023", "title"),
        ("TechCorp Inc depuis janvier 2019", "company"),
        ("Senior Developer - 2019 to present", "role"),
        ("Clean title without dates", "title"),
        ("Project Manager, 01/2020 - 03/2023, leading team", "description")
    ]

    for field_value, field_type in test_cases:
        result = normalizer.clean_field_contamination(field_value, field_type)
        if result.original_value != result.normalized_value:
            print(f"{field_type}: '{result.original_value}' -> '{result.normalized_value}' (notes: {result.notes})")
        else:
            print(f"{field_type}: '{result.original_value}' (unchanged)")

    print()


def test_convenience_functions():
    """Test convenience functions."""
    print("=== Testing Convenience Functions ===")

    # Test date normalization convenience function
    date_result = normalize_date("mars 2020 - présent", "test_doc")
    print(f"normalize_date() -> {date_result.normalized}")

    # Test language normalization convenience function
    lang_result = normalize_language_skill("English C1", "test_doc")
    print(f"normalize_language_skill() -> {lang_result.cefr_level.value}")

    # Test field cleaning convenience function
    clean_result = clean_field_contamination("Manager 2019-2023", "title")
    print(f"clean_field_contamination() -> '{clean_result.normalized_value}'")

    print()


def main():
    """Run all tests."""
    print("Enhanced Normalizer Validation Test")
    print("=" * 40)
    print()

    try:
        test_date_normalization()
        test_language_normalization()
        test_field_contamination_cleaning()
        test_convenience_functions()

        print("✅ All tests completed successfully!")

    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())