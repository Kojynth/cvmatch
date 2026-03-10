"""
Quality and consistency tests:
- Validate presence of pattern diversity metrics and enforcement output

How to run:
  - python scripts/test_quality_and_consistency.py
"""

import tempfile
from app.utils.enhanced_extraction_pipeline import EnhancedExtractionPipeline


def _make_low_diversity_cv(n: int = 20) -> str:
    """Create a temp CV with many similar date-only lines to stress diversity gate."""
    lines = []
    # pad to reach experience zone
    while len(lines) < 6:
        lines.append("")
    # add repetitive date-only patterns
    for i in range(n):
        lines.append(f"2020 - 2020")
        lines.append("Entreprise")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w", encoding="utf-8")
    tmp.write("\n".join(lines))
    tmp.flush()
    tmp.close()
    return tmp.name


def test_pattern_diversity_enforcement_present() -> tuple[bool, str]:
    cv_path = _make_low_diversity_cv()
    pipeline = EnhancedExtractionPipeline()
    result = pipeline.extract_cv_enhanced(cv_path)
    validation = result.get('validation', {})
    enforcement = validation.get('enforcement_result', {})

    ok = (
        isinstance(validation, dict)
        and 'pattern_diversity' in validation
        and isinstance(enforcement, dict)
        and 'action' in enforcement
    )
    return ok, f"validation={validation}"


def main():
    ok, msg = test_pattern_diversity_enforcement_present()
    print(f"[ {'PASS' if ok else 'FAIL'} ] Quality Guards (pattern diversity): {msg}")


if __name__ == "__main__":
    main()

