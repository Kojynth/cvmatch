#!/usr/bin/env python3
"""
Simple Test Suite
=================

Basic validation tests for the enhanced pipeline components.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_imports():
    """Test that all modules can be imported successfully."""
    print("Testing imports...")

    try:
        from cvextractor.utils.log_safety import mask_all_pii
        print("[OK] PII safety module")
    except Exception as e:
        print(f"[FAIL] PII safety module: {e}")
        return False

    try:
        from cvextractor.metrics.instrumentation import MetricsCollector
        print("[OK] Metrics instrumentation")
    except Exception as e:
        print(f"[FAIL] Metrics instrumentation: {e}")
        return False

    try:
        from cvextractor.structure.structure_analyzer import SectionStructureAnalyzer
        print("[OK] Structure analyzer")
    except Exception as e:
        print(f"[FAIL] Structure analyzer: {e}")
        return False

    try:
        from cvextractor.extraction.parser_mapper import ParserMapper
        print("[OK] Parser mapper")
    except Exception as e:
        print(f"[FAIL] Parser mapper: {e}")
        return False

    try:
        from cvextractor.ai.ai_gate import EnhancedAIGate
        print("[OK] AI gate")
    except Exception as e:
        print(f"[FAIL] AI gate: {e}")
        return False

    try:
        from cvextractor.handlers.internship_handler import InternshipHandler
        print("[OK] Internship handler")
    except Exception as e:
        print(f"[FAIL] Internship handler: {e}")
        return False

    try:
        from cvextractor.normalization.enhanced_normalizer import EnhancedNormalizer
        print("[OK] Enhanced normalizer")
    except Exception as e:
        print(f"[FAIL] Enhanced normalizer: {e}")
        return False

    try:
        from cvextractor.i18n import detect_text_direction
        print("[OK] Internationalization")
    except Exception as e:
        print(f"[FAIL] Internationalization: {e}")
        return False

    return True


def test_basic_functionality():
    """Test basic functionality of key components."""
    print("\nTesting basic functionality...")

    # Test PII masking
    try:
        from cvextractor.utils.log_safety import mask_all_pii
        result = mask_all_pii("Contact me at john@example.com")
        assert "john@example.com" not in result
        print("[OK] PII masking works")
    except Exception as e:
        print(f"[FAIL] PII masking: {e}")
        return False

    # Test metrics collector
    try:
        from cvextractor.metrics.instrumentation import MetricsCollector
        collector = MetricsCollector("test_doc")
        assert collector.doc_id == "test_doc"
        print("[OK] Metrics collector creation")
    except Exception as e:
        print(f"[FAIL] Metrics collector: {e}")
        return False

    # Test structure analyzer
    try:
        from cvextractor.structure.structure_analyzer import SectionStructureAnalyzer
        analyzer = SectionStructureAnalyzer()
        assert analyzer.contact_density_threshold > 0
        print("[OK] Structure analyzer creation")
    except Exception as e:
        print(f"[FAIL] Structure analyzer: {e}")
        return False

    # Test normalization
    try:
        from cvextractor.normalization.enhanced_normalizer import EnhancedNormalizer
        normalizer = EnhancedNormalizer()
        result = normalizer.normalize_date("2020-present")
        assert "PRESENT" in result.normalized
        print("[OK] Date normalization")
    except Exception as e:
        print(f"[FAIL] Date normalization: {e}")
        return False

    # Test internationalization
    try:
        from cvextractor.i18n import detect_text_direction, TextDirection
        analysis = detect_text_direction("Hello World")
        assert analysis.primary_direction == TextDirection.LTR
        print("[OK] Text direction detection")
    except Exception as e:
        print(f"[FAIL] Text direction detection: {e}")
        return False

    return True


def main():
    """Run the simple test suite."""
    print("Enhanced Pipeline Simple Test Suite")
    print("=" * 40)

    # Test imports
    import_success = test_imports()

    if not import_success:
        print("\n[FAILURE] Import tests failed - cannot proceed with functionality tests")
        return 1

    # Test basic functionality
    functionality_success = test_basic_functionality()

    print("\n" + "=" * 40)
    print("SUMMARY")
    print("=" * 40)

    if import_success and functionality_success:
        print("[SUCCESS] All basic tests passed!")
        print("The enhanced pipeline components are working correctly.")
        return 0
    else:
        print("[FAILURE] Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())