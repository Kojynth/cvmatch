#!/usr/bin/env python3
"""
Simple Enhanced Normalizer Test
===============================

Minimal test for enhanced normalization.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    print("Importing enhanced normalizer...")
    from cvextractor.normalization.enhanced_normalizer import EnhancedNormalizer
    print("[OK] Import successful")

    print("Creating normalizer instance...")
    normalizer = EnhancedNormalizer()
    print("[OK] Instance created")

    print("Testing simple date normalization...")
    result = normalizer.normalize_date("2020-2023", "test")
    print(f"[OK] Date test: '2020-2023' -> '{result.normalized}'")

    print("Testing simple language normalization...")
    lang_result = normalizer.normalize_language_skill("English B2", "test")
    print(f"[OK] Language test: 'English B2' -> '{lang_result.cefr_level.value}'")

    print("[SUCCESS] All basic tests passed!")

except Exception as e:
    print(f"[ERROR] {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)