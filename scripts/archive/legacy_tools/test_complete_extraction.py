"""
Test End-to-End (E2E) for the enhanced extraction pipeline.

Validates that extracted information lands in the correct sections and that
date-only + company lines are not misrouted to education.

How to run:
  - python scripts/test_complete_extraction.py
"""

from pathlib import Path
import tempfile

from app.utils.enhanced_extraction_pipeline import EnhancedExtractionPipeline


def _write_temp_cv(lines: list[str]) -> str:
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w", encoding="utf-8")
    tmp.write("\n".join(lines))
    tmp.flush()
    tmp.close()
    return tmp.name


def test_e2e_basic_structure() -> tuple[bool, str]:
    """Smoke E2E: extraction returns structured sections and metrics."""
    # Arrange: Build a minimal CV aligned with the mock segmentation indices
    # indices in EnhancedExtractionPipeline._segment_sections_with_boundaries():
    # personal_info: 0..5, experience: 6..20, education: 21..30, skills: 31..35, languages: 36..40
    lines = []
    # 0..5 personal info (mock)
    lines += [
        "John Doe",
        "Software Engineer",
        "john.doe@example.com",
        "+33 6 12 34 56 78",
        "",
        "",
    ]
    # 6..20 experience: add a simple experience-like block with a date+role+company
    lines += [
        "Expériences",
        "2021 - 2023",
        "Développeur Full-Stack chez Capgemini",
        "Missions: API REST, React, PostgreSQL",
        "",
    ]
    while len(lines) < 21:
        lines.append("")
    # 21..30 education
    lines += [
        "Formation",
        "Master Informatique - Sorbonne Université 2018 - 2020",
        "",
    ]
    while len(lines) < 31:
        lines.append("")
    # 31..35 skills
    lines += [
        "Compétences",
        "Python, JavaScript, React, Docker, SQL",
        "",
    ]
    while len(lines) < 36:
        lines.append("")
    # 36..40 languages
    lines += [
        "Langues",
        "Français (C1), Anglais (B2)",
    ]

    cv_path = _write_temp_cv(lines)

    # Act
    pipeline = EnhancedExtractionPipeline()
    result = pipeline.extract_cv_enhanced(cv_path)

    # Assert minimal structure
    ok = (
        isinstance(result, dict)
        and 'experiences' in result
        and 'education' in result
        and 'metrics' in result
        and 'validation' in result
        and result.get('success') is True
    )
    msg = "Structured extraction present with success=true" if ok else f"Unexpected result keys: {list(result.keys())}"
    return ok, msg


def test_dates_only_not_routed_to_education() -> tuple[bool, str]:
    """Regression: lines with only date + company are NOT accepted as education."""
    lines = [
        "",
        "",
        "",
        "",
        "",
        "",
        # experience zone (6..20) left mostly empty for this test
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        # education zone (21..30): insert date-only + company-like content which should be rejected
        "Janvier 2020",
        "Netflix Inc",
        "",
    ]
    cv_path = _write_temp_cv(lines)

    pipeline = EnhancedExtractionPipeline()
    result = pipeline.extract_cv_enhanced(cv_path)

    education_items = result.get('education', [])

    # Expect zero items or, at minimum, no degree/institution-only items from date+company without degree
    ok = len(education_items) == 0
    msg = "Date-only + company correctly rejected from education" if ok else f"Education incorrectly contains: {education_items}"
    return ok, msg


def main():
    tests = [
        ("E2E basic structure", test_e2e_basic_structure),
        ("Reject dates-only to education", test_dates_only_not_routed_to_education),
    ]

    passed = 0
    for name, fn in tests:
        ok, msg = fn()
        status = "PASS" if ok else "FAIL"
        print(f"[ {status} ] {name}: {msg}")
        if ok:
            passed += 1
    print(f"Summary: {passed}/{len(tests)} passed")


if __name__ == "__main__":
    main()

