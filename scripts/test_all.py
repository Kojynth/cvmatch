"""
Aggregate runner for all extraction validation tests.

Usage:
  - python scripts/test_all.py
"""

import importlib


def run_module(mod_name: str) -> int:
    print(f"\n=== Running {mod_name} ===")
    try:
        import subprocess
        import sys
        result = subprocess.run([sys.executable, '-m', mod_name], 
                              capture_output=True, text=True, encoding='cp1252')
        print(result.stdout)
        if result.stderr:
            print(result.stderr)
        return result.returncode
    except Exception as e:
        print(f"[ ERROR ] {mod_name}: {e}")
        return 1


def main():
    modules = [
        'scripts.test_complete_extraction',
        'scripts.test_section_behaviors',
        'scripts.test_quality_and_consistency',
    ]
    failures = 0
    for m in modules:
        failures += run_module(m)
    print(f"\nDone. Failures: {failures}")


if __name__ == "__main__":
    main()

