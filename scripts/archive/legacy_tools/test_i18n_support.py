#!/usr/bin/env python3
"""
Test Internationalization Support
=================================

Validation test for RTL/CJK and multilingual header recognition.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from cvextractor.i18n import (
        detect_text_direction, is_rtl_text, is_cjk_text,
        recognize_header, get_section_type,
        TextDirection, ScriptType, SectionType
    )
    print("[OK] I18n imports successful")

    # Test text direction detection
    print("\n=== Testing Text Direction Detection ===")

    test_texts = [
        ("Hello World", "English LTR"),
        ("مرحبا بالعالم", "Arabic RTL"),
        ("שלום עולם", "Hebrew RTL"),
        ("こんにちは世界", "Japanese CJK"),
        ("你好世界", "Chinese CJK"),
        ("안녕하세요 세계", "Korean CJK"),
        ("Привет мир", "Russian Cyrillic"),
        ("Hello مرحبا", "Mixed Arabic-English")
    ]

    for text, description in test_texts:
        try:
            analysis = detect_text_direction(text)
            print(f"{description}: {analysis.primary_direction.value} / {analysis.primary_script.value} (conf: {analysis.confidence:.2f})")
        except Exception as e:
            print(f"{description}: ERROR - {e}")

    # Test convenience functions
    print("\n=== Testing Convenience Functions ===")
    print(f"Arabic is RTL: {is_rtl_text('مرحبا بالعالم')}")
    print(f"Chinese is CJK: {is_cjk_text('你好世界')}")
    print(f"English is RTL: {is_rtl_text('Hello World')}")
    print(f"English is CJK: {is_cjk_text('Hello World')}")

    # Test multilingual header recognition
    print("\n=== Testing Multilingual Header Recognition ===")

    header_tests = [
        ("Experience", "English"),
        ("Education", "English"),
        ("Skills", "English"),
        ("الخبرة", "Arabic Experience"),
        ("التعليم", "Arabic Education"),
        ("המשכלה", "Hebrew Education"),
        ("经验", "Chinese Experience"),
        ("教育", "Chinese Education"),
        ("опыт работы", "Russian Experience"),
        ("компетенции", "Russian Skills"),
        ("expérience", "French Experience"),
        ("competências", "Portuguese Skills")
    ]

    for header, description in header_tests:
        try:
            match = recognize_header(header)
            print(f"{description}: {match.section_type.value} (conf: {match.confidence:.2f}, method: {match.match_method})")
        except Exception as e:
            print(f"{description}: ERROR - {e}")

    print("\n[SUCCESS] All I18n tests completed!")

except Exception as e:
    print(f"[ERROR] Test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)