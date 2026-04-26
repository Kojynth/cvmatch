from __future__ import annotations

from pathlib import Path

import pytest

from app.controllers.export_manager import ExportManager
from app.utils.cv_postprocessing import (
    clean_skill_item_residues,
    coerce_generated_cv_payload,
    enforce_cv_offer_adaptation,
)


def _fallback_generator(_profile_json, _reason):
    return {
        "schema_version": "cv.v1",
        "target_job_title": "",
        "target_company": "",
        "contact": {
            "full_name": "Alice Example",
            "email": "alice@example.com",
            "phone": "",
            "linkedin_url": "",
            "location": "",
        },
        "summary": "",
        "skills": [],
        "experience": [],
        "education": [],
        "projects": [],
        "languages": [],
        "certifications": [],
        "ats_keywords": [],
    }


def test_sparse_final_payload_recovers_profile_backed_experience_and_skills() -> None:
    profile_json = {
        "experiences": [
            {
                "title": "Software Quality Engineer",
                "company": "ACME",
                "start_date": "01/2022",
                "end_date": "09/2025",
                "location": "Paris",
                "description": "Designed and executed manual and automated test campaigns across web and API systems.",
            }
        ],
        "skills": [
            {"name": "Playwright"},
            {"name": "Selenium"},
            {"name": "API testing"},
        ],
        "soft_skills": [{"name": "Communication"}],
    }

    result = coerce_generated_cv_payload(
        payload={
            "summary": "Software Quality Engineer focused on test reliability.",
            "skills": [],
            "experience": [],
        },
        profile_json=profile_json,
        fallback_generator=_fallback_generator,
        language_code="en",
    )

    assert result["experience"]
    assert result["experience"][0]["title"] == "Software Quality Engineer"
    assert result["skills"]
    assert result["skills"][0]["category"] == "Technical Skills"
    technical_items = result["skills"][0]["items"]
    assert "Playwright" in technical_items
    assert "Selenium" in technical_items


def test_offer_adaptation_failure_keeps_deterministic_reconciliation() -> None:
    profile_json = {
        "experiences": [
            {
                "title": "QA Engineer",
                "company": "ACME",
                "start_date": "2023",
                "end_date": "09/2026",
                "location": "Paris",
                "description": "Validated releases, automated regression suites, and tracked defects.",
            }
        ],
        "skills": [
            {"name": "Playwright"},
            {"name": "CI/CD"},
        ],
    }

    result = coerce_generated_cv_payload(
        payload={
            "summary": "QA profile.",
            "skills": [],
            "experience": [],
        },
        profile_json=profile_json,
        fallback_generator=_fallback_generator,
        language_code="en",
        offer_adaptation_fn=lambda _candidate, _review: (_ for _ in ()).throw(
            NameError("missing_education_terms_postprocess")
        ),
    )

    assert result["experience"]
    assert result["skills"]
    assert result["skills"][0]["items"]


def test_coerce_generated_cv_payload_dedups_duplicate_experience_entries() -> None:
    profile_json = {
        "experiences": [
            {
                "title": "QA Engineer",
                "company": "ACME",
                "start_date": "09/2021",
                "end_date": "Present",
                "description": "Validated releases, automated regression suites, and tracked defects.",
            }
        ],
        "skills": [{"name": "Playwright"}],
    }

    result = coerce_generated_cv_payload(
        payload={
            "summary": "QA profile.",
            "experience": [
                {
                    "title": "QA Engineer",
                    "company": "ACME",
                    "start_date": "09/2021",
                    "end_date": "Present",
                    "summary": "Validated releases.",
                    "highlights": ["Validated releases."],
                },
                {
                    "title": "QA Engineer",
                    "company": "ACME",
                    "start_date": "2021-09",
                    "end_date": "Current",
                    "summary": "Validated releases and automated regression suites.",
                    "highlights": ["Automated regression suites."],
                },
            ],
        },
        profile_json=profile_json,
        fallback_generator=_fallback_generator,
        language_code="en",
    )

    assert len(result["experience"]) == 1
    merged = result["experience"][0]
    assert "automated regression suites" in merged["summary"].lower()
    highlight_blob = " ".join(str(item) for item in merged["highlights"]).lower()
    assert "validated releases" in highlight_blob
    assert "automated regression suites" in highlight_blob


def test_summary_focus_sentence_prefers_profile_backed_aligned_skills() -> None:
    profile_json = {
        "skills": [
            {"name": "SQL"},
            {"name": "Python"},
        ],
        "soft_skills": [
            {"name": "Communication"},
        ],
    }
    cv_json = {
        "summary": "",
        "experience": [],
        "skills": [],
        "projects": [],
        "education": [],
        "certifications": [],
        "languages": [],
    }

    result = enforce_cv_offer_adaptation(
        cv_json,
        job_title="QA Engineer",
        company="Mistral AI",
        aligned_terms=["SQL", "Python", "Communication"],
        missing_summary_terms=["LLM", "inference"],
        missing_experience_terms=[],
        profile_json=profile_json,
        language_code="fr",
    )

    summary = str(result.get("summary") or "")
    assert "Profil aligné avec Mistral AI" in summary
    lowered = summary.lower()
    assert "sql" in lowered
    assert "python" in lowered


def test_skill_residue_cleanup_preserves_non_skill_qualifier_heads() -> None:
    cleaned = clean_skill_item_residues(
        ["Senior Data Analysis", "Predictive Data Analysis", "Data Analysis"],
        other_items=[
            "Senior Data Analysis",
            "Predictive Data Analysis",
            "Data Analysis",
        ],
        category_label="Technical skills",
    )

    assert "Senior Data Analysis" in cleaned
    assert "Predictive Data Analysis" in cleaned
    assert "Senior" not in cleaned
    assert "Predictive" not in cleaned


def test_skill_residue_cleanup_keeps_generic_tool_context_repair() -> None:
    cleaned = clean_skill_item_residues(
        ["Python", "Playwright", "Agilitest Tests API"],
        other_items=["Python", "Playwright", "Tests API"],
        category_label="Automatisation & scripting",
    )

    assert "Agilitest" in cleaned
    assert "Agilitest Tests API" not in cleaned


def test_profile_skill_reconciliation_drops_unsupported_offer_only_skills() -> None:
    profile_json = {
        "skills": [
            {"name": "Postman"},
            {"name": "SQL"},
            {"name": "PostgreSQL"},
            {"name": "MongoDB"},
            {"name": "SQL Server"},
        ],
        "experiences": [
            {
                "title": "QA Engineer",
                "company": "ACME",
                "start_date": "09/2023",
                "end_date": "Present",
                "description": "Tests API avec Postman et vérifications SQL en base.",
            }
        ],
    }

    result = coerce_generated_cv_payload(
        payload={
            "summary": "QA profile.",
            "skills": [
                {
                    "category": "Compétences techniques",
                    "items": [
                        "ensuring end-to-end reliability",
                        "QA",
                        "api",
                        "Descriptif",
                        "UX Design",
                        "Cloud computing",
                        "Architecture cloud AWS",
                    ],
                }
            ],
            "experience": [],
        },
        profile_json=profile_json,
        fallback_generator=_fallback_generator,
        language_code="fr",
    )

    items = [
        item
        for block in result["skills"]
        for item in block.get("items", [])
        if isinstance(item, str)
    ]
    rendered = " ".join(items)
    assert "Postman" in rendered
    assert "SQL" in rendered
    assert "Descriptif" not in rendered
    assert "UX Design" not in rendered
    assert "Cloud computing" not in rendered
    assert "Architecture cloud AWS" not in rendered
    assert "ensuring end-to-end reliability" not in rendered


def test_render_featured_skills_ranks_profile_evidence_against_offer() -> None:
    manager = ExportManager()
    cv_data = {
        "name": "Alice Example",
        "language": "fr",
        "job_title": "Software Engineer, QA",
        "company": "Mistral AI",
        "ats_keywords": [
            "API testing",
            "test automation",
            "edge cases",
            "release readiness",
            "Python",
        ],
        "profile_summary": "Profil QA.",
        "skills": [
            {
                "category": "Compétences techniques",
                "skills_list": [
                    {"name": "UX Design"},
                    {"name": "Cloud computing"},
                    {"name": "Architecture cloud AWS"},
                    {"name": "Tableau, Power BI et Looker"},
                    {"name": "Rédiger des plans de tests"},
                    {"name": "Maintenir la bibliothèque de tests de non-régression avec Xray Jira"},
                    {"name": "Concevoir et exécuter des tests d'acceptance et exploratoires (Gherkin)"},
                    {"name": "Gherkin"},
                    {"name": "Suivre les anomalies"},
                    {"name": "Benchmark d'outils d'automatisations"},
                    {"name": "SQL"},
                    {"name": "Python"},
                    {"name": "Bases de données relationnelles"},
                    {"name": "Jira"},
                    {"name": "Postman"},
                ],
            }
        ],
        "experience": [
            {
                "title": "Alternant Ingénieur QA",
                "company": "Careside",
                "start_date": "09/2023",
                "end_date": "Présent",
                "description": (
                    "Réalise des tests API avec Postman ainsi que des vérifications "
                    "en base de données sur MongoDB, PostgreSQL et Microsoft SQL Server. "
                    "Exécute et suit des plans de test sur 3 applications critiques "
                    "et analyse les risques fonctionnels. "
                    "Maintient la bibliothèque de tests de non-régression avec Xray et Jira. "
                    "Explore et benchmarke Playwright, Cypress, Selenium et Agilitest "
                    "pour industrialiser les tests."
                ),
            }
        ],
    }

    prepared = manager.prepare_template_data(cv_data)

    rendered = "\n".join(prepared["featured_skills"])
    assert "Compétences techniques :" not in rendered
    assert "QA & tests :" in rendered
    assert "Plans de test" in rendered
    assert "Non-régression" in rendered
    assert "API & data : Postman · Tests API · SQL · PostgreSQL · MongoDB · SQL Server" in rendered
    assert "Automatisation :" in rendered
    assert "Python" in rendered
    assert "Playwright" in rendered
    assert "Cypress" in rendered
    assert "Selenium" in rendered
    assert "Agilitest" in rendered
    assert "Delivery QA :" in rendered
    assert "Jira" in rendered
    assert "Xray" in rendered
    assert "Gherkin" in rendered
    assert "UX Design" not in rendered
    assert "Cloud computing" not in rendered
    assert "Architecture cloud AWS" not in rendered
    assert "Tableau" not in rendered


def test_render_experience_keeps_role_critical_evidence_lines() -> None:
    manager = ExportManager()
    cv_data = {
        "name": "Alice Example",
        "language": "fr",
        "job_title": "Software Engineer, QA",
        "company": "Mistral AI",
        "ats_keywords": [
            "API testing",
            "edge cases",
            "test automation",
            "release readiness",
        ],
        "skills": [
            {"category": "Compétences techniques", "skills_list": [{"name": "Postman"}]}
        ],
        "experience": [
            {
                "title": "Alternant Ingénieur QA",
                "company": "Careside",
                "start_date": "09/2023",
                "end_date": "Présent",
                "description": (
                    "Conçois, exécute et suit des plans de test sur 3 applications critiques. "
                    "Analyse les spécifications fonctionnelles afin d'identifier ambiguïtés, incohérences et risques de conception. "
                    "Qualifie les évolutions applicatives et techniques, notamment dans le cadre de migrations front-end et de paramétrages back-end. "
                    "Réalise des tests API avec Postman ainsi que des vérifications en base de données sur MongoDB, PostgreSQL et Microsoft SQL Server. "
                    "Contrôle la conformité RGPD, incluant la vérification de scripts de purge de données en base. "
                    "Crée 3 agents IA pour réduire les temps de conception des plans de test et accélérer la préparation des activités QA. "
                    "Contribue à l'automatisation de la génération de données de test. "
                    "Explore et benchmarke des solutions d'automatisation, notamment Playwright, Cypress, Selenium et Agilitest."
                ),
            }
        ],
    }

    prepared = manager.prepare_template_data(cv_data)
    bullets = prepared["experience"][0]["description"]
    rendered = "\n".join(bullets)

    assert len(bullets) <= 4
    assert "cas limites" in rendered
    assert "Postman" in rendered
    assert "PostgreSQL, MongoDB et SQL Server" in rendered
    assert "conformité RGPD" in rendered
    assert "agents IA" in rendered
    assert "génération de données de test" in rendered
    assert "benchmark d'outils d'automatisation" in rendered


def test_coerce_generated_payload_recovers_profile_projects_and_interests() -> None:
    profile_json = {
        "projects": [
            {
                "name": "CVmatch",
                "technologies": "Python",
                "description": "Application Python de génération contrôlée de CV ciblés.",
            }
        ],
        "interests": ["Natation\nHistoire"],
    }

    result = coerce_generated_cv_payload(
        payload={"summary": "Profil QA.", "projects": [], "interests": []},
        profile_json=profile_json,
        fallback_generator=_fallback_generator,
        language_code="fr",
    )

    assert result["projects"]
    assert result["projects"][0]["name"] == "CVmatch"
    assert result["interests"] == ["Natation", "Histoire"]


def test_rendered_interests_section_is_not_ultra_hidden() -> None:
    template = Path("templates/cv_templates/minimal.html").read_text(encoding="utf-8")

    assert 'class="cv-section interests-section"' in template
    assert "interests-section fit-ultra-hide" not in template


def test_pdf_text_order_keeps_experience_bullets_before_education() -> None:
    pypdf = pytest.importorskip("pypdf")
    from app.controllers.export_manager import _check_weasyprint

    if not _check_weasyprint():
        pytest.skip("WeasyPrint unavailable")

    manager = ExportManager()
    output_path = Path("runtime") / "test_pdf_text_order_contract.pdf"
    output_path.parent.mkdir(exist_ok=True)
    cv_data = {
        "name": "Alice Example",
        "language": "fr",
        "job_title": "QA Engineer",
        "company": "ACME",
        "profile_summary": "Profil QA.",
        "experience": [
            {
                "title": "Role Alpha",
                "company": "Company A",
                "start_date": "01/2024",
                "end_date": "Présent",
                "description": [
                    "Alpha bullet verifies API behaviour.",
                    "Alpha bullet tracks production defects.",
                ],
            },
            {
                "title": "Role Beta",
                "company": "Company B",
                "start_date": "01/2023",
                "end_date": "12/2023",
                "description": ["Beta bullet automates reporting checks."],
            },
        ],
        "education": [
            {
                "degree": "Formation Gamma",
                "institution": "School C",
                "year": "2024",
            }
        ],
    }

    try:
        manager.export_cv(
            cv_data,
            template="minimal",
            output_format="pdf",
            output_path=str(output_path),
        )
        with output_path.open("rb") as handle:
            reader = pypdf.PdfReader(handle)
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        assert text.index("Role Alpha") < text.index("Alpha bullet verifies API behaviour")
        assert text.index("Alpha bullet tracks production defects") < text.index("Role Beta")
        assert text.index("Beta bullet automates reporting checks") < text.index(
            "F O R M A T I O N"
        )
        assert text.index("F O R M A T I O N") < text.index("Formation Gamma")
    finally:
        try:
            output_path.unlink()
        except OSError:
            pass
