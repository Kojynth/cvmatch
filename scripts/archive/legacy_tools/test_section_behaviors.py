"""
Specialized tests by section:
- Soft Skills V2: taxonomy-based parsing
- Languages V2: certification-to-language mapping
- Experience Gate: reject dates-only seeds
- Project Router: intelligent routing project vs experience

How to run:
  - python scripts/test_section_behaviors.py
"""

from typing import List

from app.parsers.soft_skills_parser import parse_soft_skills_from_lines
from app.utils.language_normalizer import LanguageNormalizer
from app.utils.experience_extractor_enhanced import enhanced_experience_extractor
from app.utils.project_router import ProjectRouter, ContentType


def test_soft_skills_v2_basic() -> tuple[bool, str]:
    lines = ["Leadership, communication"]
    parsed = parse_soft_skills_from_lines(lines, context="section")
    names = {item.get("name") for item in parsed if item.get("name")}
    # Expect canonicalized forms to include Communication/Leadership (case-insensitive acceptance)
    ok = any("communication" in (n or "").lower() for n in names) and any("leader" in (n or "").lower() for n in names)
    return ok, f"Parsed soft skills: {sorted(names)}"


def test_languages_v2_cert_mapping() -> tuple[bool, str]:
    normalizer = LanguageNormalizer()
    pairs = normalizer.extract_language_from_certification("TOEFL 950")
    langs = [lang for (lang, _cert) in pairs]
    ok = any(lang.lower() == "english" for lang in langs)
    return ok, f"Certification->language: {pairs}"


def test_experience_gate_reject_dates_only() -> tuple[bool, str]:
    lines: List[str] = [
        "Janvier 2020",
        "Netflix Inc",
        ""  # no role/action signals
    ]
    result = enhanced_experience_extractor.extract_experiences_with_gates(
        lines, section_bounds=None, entities=[], date_hits=None
    )
    exps = result.get("experiences", [])
    ok = len(exps) == 0
    return ok, f"Experiences extracted: {exps}"


def test_project_router_basic() -> tuple[bool, str]:
    router = ProjectRouter()
    # Clear project-like
    decision_proj = router.route_content(
        "Développement d'une application React avec API Node.js et Docker (projet personnel)",
        {"has_company": False}
    )
    # Clear experience-like
    decision_exp = router.route_content(
        "Chef de projet IT chez Capgemini – 2 ans – management d'équipe",
        {"has_company": True, "has_dates": True}
    )
    ok = (
        decision_proj.content_type == ContentType.PROJECT and
        decision_exp.content_type == ContentType.EXPERIENCE
    )
    return ok, f"proj=({decision_proj.content_type.value},{decision_proj.confidence:.2f}) exp=({decision_exp.content_type.value},{decision_exp.confidence:.2f})"


def main():
    tests = [
        ("Soft Skills V2", test_soft_skills_v2_basic),
        ("Languages V2 (TOEFL->English)", test_languages_v2_cert_mapping),
        ("Experience Gate (reject dates-only)", test_experience_gate_reject_dates_only),
        ("Project Router", test_project_router_basic),
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

