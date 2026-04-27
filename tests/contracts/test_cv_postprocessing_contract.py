from __future__ import annotations

from pathlib import Path

import pytest

from app.controllers.export_manager import ExportManager
from app.utils.cv_json_renderer import cv_json_to_cv_data
from app.utils.cv_postprocessing import (
    clean_skill_item_residues,
    coerce_generated_cv_payload,
    enforce_cv_offer_adaptation,
    sanitize_cv_json_output,
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
    categories = [block["category"] for block in result["skills"]]
    assert "Automation" in categories
    technical_items = [
        item
        for block in result["skills"]
        for item in block.get("items", [])
    ]
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

    skills = prepared["featured_skills"]
    rendered = "\n".join(skills)
    assert "Compétences techniques :" not in rendered
    assert "QA & tests :" not in rendered
    assert "API & data :" not in rendered
    assert "Automatisation :" not in rendered
    assert "Delivery QA :" not in rendered
    assert "Benchmark Playwright / Cypress / Selenium / Agilitest" in skills
    assert "Playwright" not in skills
    assert "Cypress" not in skills
    assert "Selenium" not in skills
    assert "Microsoft SQL Server" in skills
    assert "Postman" in skills
    assert "PostgreSQL" in skills
    assert "MongoDB" in skills
    assert "Jira" in skills
    assert "Python" in skills
    assert "UX Design" not in rendered
    assert "Cloud computing" not in rendered
    assert "Architecture cloud AWS" not in rendered
    assert "Tableau" not in rendered


def test_render_featured_skills_stays_flat_without_generated_categories() -> None:
    manager = ExportManager()
    cv_data = {
        "name": "Alice Example",
        "language": "fr",
        "job_title": "Software Engineer, QA",
        "profile_summary": "Profil QA.",
        "skills": [
            {
                "category": "Compétences techniques",
                "skills_list": [
                    {"name": "Cypress"},
                    {"name": "Selenium"},
                    {"name": "Playwright"},
                    {"name": "Benchmark d'outils d'automatisation"},
                    {"name": "Postman"},
                    {"name": "SQL"},
                    {"name": "PostgreSQL"},
                    {"name": "MongoDB"},
                    {"name": "Microsoft SQL Server"},
                    {"name": "Engineer SQL"},
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
                    "Réalise des tests API avec Postman et des vérifications SQL "
                    "sur PostgreSQL, MongoDB et Microsoft SQL Server. "
                    "Explore et benchmarke Playwright, Cypress, Selenium et Agilitest."
                ),
            }
        ],
    }

    prepared = manager.prepare_template_data(cv_data)
    skills = prepared["featured_skills"]
    rendered = "\n".join(skills)

    assert "API & data :" not in rendered
    assert "Automatisation :" not in rendered
    assert "Benchmark Playwright / Cypress / Selenium / Agilitest" in skills
    assert "Playwright" not in skills
    assert "Cypress" not in skills
    assert "Selenium" not in skills
    assert "Engineer SQL" not in rendered
    assert "Benchmark Cypress / Selenium" not in rendered


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

    assert len(bullets) >= 4
    assert len(bullets) <= 4
    assert "cas limites" in rendered
    assert "Postman" in rendered
    assert "PostgreSQL, MongoDB et SQL Server" in rendered
    assert "conformité RGPD" in rendered
    assert "agents IA" in rendered
    assert "génération de données de test" in rendered
    assert "benchmark d'outils d'automatisation" in rendered


def test_featured_project_filters_noisy_generated_technologies() -> None:
    manager = ExportManager()
    project = manager._build_featured_project(
        [
            {
                "name": "CVMatch",
                "technologies": "Python, api, seeking, skilled, proactive, summary, are",
                "description": (
                    "CVMatch est une application développée en Python permettant "
                    "d'analyser une offre d'emploi, d'adapter un profil candidat "
                    "et de générer un CV ciblé. Le projet repose sur des LLM, "
                    "une validation des sorties et des tests unitaires avec pytest."
                ),
            }
        ]
    )

    assert project is not None
    assert project["technologies"] == ["Python", "LLM", "pytest"]
    rendered = " ".join(project["description_lines"])
    assert "Application Python/LLM" in rendered
    assert "analyse d'offres d'emploi" in rendered
    assert "tests unitaires avec pytest" in rendered
    assert "summary" not in rendered
    assert "are" not in rendered


def test_featured_project_prefers_offer_aligned_project_and_keeps_rich_details() -> None:
    manager = ExportManager()
    project = manager._build_featured_project(
        [
            {
                "name": "Reporting commercial",
                "technologies": "Tableau, Power BI, Excel, SQL",
                "url": "https://example.com/reporting",
                "duration": "2023",
                "description": (
                    "Construit des tableaux de bord commerciaux et suit les KPI "
                    "pour une équipe opérationnelle."
                ),
            },
            {
                "name": "CVMatch",
                "technologies": "Python",
                "description": (
                    "CVMatch est une application développée en Python permettant "
                    "d'analyser une offre d'emploi, d'adapter un profil candidat "
                    "et de générer un CV ciblé. Le projet repose sur des LLM, "
                    "une validation des sorties et des tests unitaires avec pytest."
                ),
            },
        ],
        job_title="Software Engineer",
        offer_terms=[
            "Python",
            "LLM",
            "validation des sorties",
            "tests unitaires",
            "génération de CV ciblés",
        ],
    )

    assert project is not None
    assert project["name"] == "CVMatch"
    assert project["technologies"] == ["Python", "LLM", "pytest"]
    assert project["render_detail_budget"] == 2
    rendered = " ".join(project["description_lines"])
    assert "Application Python/LLM" in rendered
    assert "génération de CV ciblés" in rendered
    assert "validation des sorties" in rendered
    assert "tests unitaires avec pytest" in rendered


def test_featured_project_can_keep_two_project_detail_lines_when_source_is_rich() -> None:
    manager = ExportManager()
    project = manager._build_featured_project(
        [
            {
                "name": "Data Quality Toolkit",
                "technologies": "Python, SQL",
                "description": (
                    "Développé un outil Python pour analyser la qualité des données "
                    "et détecter les incohérences avant exploitation. Validé les "
                    "résultats avec des requêtes SQL et des tests de non-régression."
                ),
            }
        ],
        job_title="Data Analyst",
        offer_terms=["Python", "SQL", "qualité des données"],
    )

    assert project is not None
    assert project["name"] == "Data Quality Toolkit"
    assert project["render_detail_budget"] == 2
    assert len(project["description_lines"]) == 2
    rendered = " ".join(project["description_lines"])
    assert "outil Python" in rendered
    assert "requêtes SQL" in rendered


def test_targeted_one_page_render_drops_interests_under_space_pressure() -> None:
    manager = ExportManager()
    prepared = manager.prepare_template_data(
        {
            "name": "Alice Example",
            "language": "fr",
            "job_title": "Software Engineer, QA",
            "ats_keywords": ["API testing", "automation"],
            "profile_summary": "Profil QA.",
            "experience": [
                {
                    "title": "QA Engineer",
                    "company": "ACME",
                    "start_date": "09/2023",
                    "end_date": "Présent",
                    "description": ["Réalise des tests API avec Postman."],
                }
            ],
            "projects": [
                {
                    "name": "CVMatch",
                    "technologies": "Python",
                    "description": "Application Python de génération de CV ciblés.",
                }
            ],
            "education": [{"degree": "Master", "institution": "School", "year": "2024"}],
            "languages": [{"name": "Anglais", "level": "B2"}],
            "interests": ["Histoire", "Natation en compétition", "Fitness"],
        }
    )

    assert prepared["featured_project"]
    assert prepared["interests"] == []


def test_past_french_bullets_drop_auxiliary_a_prefix() -> None:
    result = coerce_generated_cv_payload(
        payload={
            "summary": "Profil QA.",
            "experience": [
                {
                    "title": "Stage Sales Support",
                    "company": "ACME",
                    "start_date": "06/2023",
                    "end_date": "08/2023",
                    "highlights": [
                        "A automatisé les calculs pour limiter les erreurs.",
                        "A structuré les retours utilisateurs.",
                    ],
                }
            ],
        },
        profile_json={},
        fallback_generator=_fallback_generator,
        language_code="fr",
    )

    highlights = result["experience"][0]["highlights"]
    assert highlights[0].startswith("Automatisé")
    assert highlights[1].startswith("Structuré")


def test_experience_reconciliation_supplements_short_generated_current_role() -> None:
    profile_json = {
        "experiences": [
            {
                "title": "Alternant Ingénieur QA",
                "company": "Careside",
                "start_date": "09/2023",
                "end_date": "Présent",
                "description": (
                    "Conçois, exécute et suit des plans de test sur 3 applications critiques. "
                    "Réalise des tests API avec Postman ainsi que des vérifications en base "
                    "de données sur MongoDB, PostgreSQL et Microsoft SQL Server. "
                    "Crée 3 agents IA pour assister les activités QA : génération de données "
                    "de test, aide à la conception de plans de test et benchmark d'outils "
                    "d'automatisation comme Playwright, Cypress, Selenium et Agilitest."
                ),
            }
        ],
    }

    result = coerce_generated_cv_payload(
        payload={
            "summary": "Profil QA.",
            "experience": [
                {
                    "title": "Alternant Ingénieur QA",
                    "company": "Careside",
                    "start_date": "09/2023",
                    "end_date": "Présent",
                    "highlights": [
                        "Exécute et suit des plans de test sur 3 applications critiques.",
                        "Réalise des tests API avec Postman.",
                    ],
                }
            ],
        },
        profile_json=profile_json,
        fallback_generator=_fallback_generator,
        language_code="fr",
    )

    highlights = result["experience"][0]["highlights"]
    rendered = " ".join(highlights)

    assert len(highlights) >= 3
    assert "Postman" in rendered
    assert "agents IA" in rendered
    assert "génération de données de test" in rendered


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


def test_project_reconciliation_enriches_poor_generated_project_from_profile() -> None:
    profile_json = {
        "projects": [
            {
                "name": "CVMatch",
                "technologies": "Python",
                "description": (
                    "CVMatch est une application développée en Python permettant "
                    "d'analyser une offre d'emploi, d'adapter un profil candidat "
                    "et de générer un CV ciblé. Le projet repose sur des LLM, "
                    "une validation des sorties et des tests unitaires avec pytest."
                ),
            }
        ],
    }

    result = coerce_generated_cv_payload(
        payload={
            "summary": "Profil QA.",
            "projects": [
                {
                    "name": "CVMatch",
                    "technologies": "Python, seeking, skilled, proactive",
                    "description": (
                        "Application Python : analyse d'offres d'emploi, "
                        "adaptation de profil candidat."
                    ),
                }
            ],
        },
        profile_json=profile_json,
        fallback_generator=_fallback_generator,
        language_code="fr",
    )

    project = ExportManager()._build_featured_project(result["projects"])

    assert project is not None
    assert project["technologies"] == ["Python", "LLM", "pytest"]
    rendered = " ".join(project["description_lines"])
    assert "Application Python/LLM" in rendered
    assert "génération de CV ciblés" in rendered
    assert "validation des sorties" in rendered
    assert "tests unitaires avec pytest" in rendered
    assert "seeking" not in rendered
    assert "skilled" not in rendered
    assert "proactive" not in rendered


def test_noisy_flat_skills_rebuild_as_source_backed_themed_rows() -> None:
    profile_json = {
        "experiences": [
            {
                "title": "Alternant Ingénieur QA",
                "company": "Careside",
                "start_date": "09/2023",
                "end_date": "Présent",
                "description": (
                    "Conçoit, exécute et suit des plans de test sur 3 applications "
                    "critiques avec analyse des risques fonctionnels, cas limites "
                    "et qualification d'anomalies. Réalise des tests API avec "
                    "Postman et vérifie les données SQL sur PostgreSQL, MongoDB "
                    "et Microsoft SQL Server. Explore et benchmarke Playwright, "
                    "Cypress, Selenium et Agilitest pour les activités "
                    "d'automatisation."
                ),
            }
        ],
        "skills": [
            {"name": "SQL"},
            {"name": "Python"},
            {"name": "Postman"},
        ],
        "projects": [
            {
                "name": "CVMatch",
                "technologies": "Python, LLM, pytest, JSON",
                "description": (
                    "Application Python/LLM de prompt engineering pour analyser "
                    "des offres d'emploi, adapter un profil candidat, générer des "
                    "CV ciblés et valider les sorties avec des tests unitaires "
                    "pytest et des payloads JSON."
                ),
            }
        ],
    }

    result = coerce_generated_cv_payload(
        payload={
            "summary": "Profil QA.",
            "skills": [
                {
                    "category": "Compétences techniques",
                    "items": [
                        (
                            "Benchmark Cypress / Selenium / Agilitest / "
                            "Playwright Microsoft SQL Server Postman AI-powered "
                            "PostgreSQL MongoDB implicites du recruteur du "
                            "prompt engineering including functional SQL"
                        )
                    ],
                }
            ],
        },
        profile_json=profile_json,
        fallback_generator=_fallback_generator,
        language_code="fr",
        job_title="Software Engineer, QA",
        offer_terms=[
            "functional testing",
            "API testing",
            "edge cases",
            "test automation",
            "AI products",
            "Python",
        ],
    )
    prepared = ExportManager().prepare_template_data(
        cv_json_to_cv_data(result, language="fr")
    )

    rows = prepared["featured_skills"]
    rendered = "\n".join(rows)

    assert any(row.startswith("QA & tests :") for row in rows)
    assert "Plans de test" in rendered
    assert "Tests fonctionnels" in rendered
    assert "Tests API" in rendered
    assert "Analyse des risques" in rendered
    assert "Cas limites" in rendered
    assert "Qualification d'anomalies" in rendered
    assert any(row.startswith("API & data :") for row in rows)
    assert "Postman" in rendered
    assert "PostgreSQL" in rendered
    assert "MongoDB" in rendered
    assert "Microsoft SQL Server" in rendered
    assert any(row.startswith("Automatisation :") for row in rows)
    assert "Python" in rendered
    assert "Playwright" in rendered
    assert "Cypress" in rendered
    assert "Selenium" in rendered
    assert "Agilitest" in rendered
    assert "Benchmark d'outils" in rendered
    assert any(row.startswith("IA & qualité logicielle :") for row in rows)
    assert "LLM" in rendered
    assert "Prompt engineering" in rendered
    assert "Validation de sorties" in rendered
    assert "pytest" in rendered
    assert "JSON" in rendered
    assert " · " in rendered
    assert "AI-powered" not in rendered
    assert "including functional" not in rendered
    assert "recruteur" not in rendered


def test_project_technologies_preserve_slash_delimited_tool_names() -> None:
    cv = {
        "projects": [
            {
                "name": "Tooling",
                "technologies": "CI/CD, C/C++, Node.js/TypeScript, Python / Django",
            }
        ]
    }

    sanitize_cv_json_output(cv, language_code="en")

    assert (
        cv["projects"][0]["technologies"]
        == "CI/CD, C/C++, Node.js/TypeScript, Python, Django"
    )


def test_project_reconciliation_deduplicates_technologies_across_passes() -> None:
    result = coerce_generated_cv_payload(
        payload={
            "summary": "Profile.",
            "projects": [
                {
                    "name": "CVMatch",
                    "technologies": "Python, LLM",
                    "description": "Application Python.",
                }
            ],
        },
        profile_json={
            "projects": [
                {
                    "name": "CVMatch",
                    "technologies": "Python, LLM",
                    "description": "Application Python with LLM and pytest validation.",
                }
            ]
        },
        fallback_generator=_fallback_generator,
        language_code="en",
    )

    assert result["projects"][0]["technologies"] == "Python, LLM"


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


def test_renderer_preserves_english_colon_positioning_sentence() -> None:
    cv_json = {
        "target_job_title": "QA Engineer",
        "target_company": "Mistral AI",
        "contact": {"full_name": "Alice Example", "email": "alice@example.com"},
        "summary": (
            "QA engineer focused on release quality. "
            "Profile aligned with Mistral AI: foundation in API testing."
        ),
        "experience": [],
        "skills": [],
    }

    data = cv_json_to_cv_data(cv_json, language="en")

    assert data["profile_summary"] == "QA engineer focused on release quality."
    assert (
        data["profile_positioning_sentence"]
        == "Profile aligned with Mistral AI: foundation in API testing."
    )


def test_non_french_locale_does_not_force_french_render_fallbacks() -> None:
    manager = ExportManager()
    cv_json = {
        "contact": {"full_name": "Alice Example", "email": "alice@example.com"},
        "summary": "Perfil QA.",
        "experience": [],
        "skills": [],
    }
    data = cv_json_to_cv_data(cv_json, language="es")

    assert data["language"] == "es"
    assert data["labels"]["skills"] == "Habilidades"

    source_lines = [
        "API testing with Postman and database checks on PostgreSQL.",
    ]
    evidence_lines = manager._source_backed_experience_evidence_lines(
        source_lines,
        offer_terms=["API testing", "database"],
        language_code="es",
    )
    assert evidence_lines == source_lines

    grouped = manager._group_featured_skills_for_display(
        ["Postman", "SQL"],
        {
            "skills": [
                {
                    "category": "Habilidades",
                    "skills_list": [{"name": "Postman"}, {"name": "SQL"}],
                }
            ],
            "experience": [
                {
                    "title": "QA",
                    "company": "ACME",
                    "description": ["Plans de test, Postman, SQL, Jira, Xray"],
                }
            ],
            "experience_all": [
                {
                    "title": "QA",
                    "company": "ACME",
                    "description": ["Plans de test, Postman, SQL, Jira, Xray"],
                }
            ],
        },
        offer_terms=["QA", "testing", "API", "release"],
        job_title="QA Engineer",
        language_code="es",
    )
    assert grouped == ["Postman", "SQL"]


def test_contextual_positioning_does_not_claim_offer_only_experience() -> None:
    manager = ExportManager()
    formatted = {
        "language": "en",
        "company": "Mistral AI",
        "job_title": "QA Engineer",
        "ats_keywords": [
            "API testing",
            "SQL",
            "defect analysis",
            "test automation",
        ],
        "skills": [{"category": "Skills", "skills_list": [{"name": "Manual testing"}]}],
        "featured_skills": ["Manual testing"],
        "experience": [
            {
                "title": "QA tester",
                "company": "ACME",
                "description": ["Executed manual test plans and wrote release notes."],
            }
        ],
        "experience_all": [
            {
                "title": "QA tester",
                "company": "ACME",
                "description": ["Executed manual test plans and wrote release notes."],
            }
        ],
    }

    sentence = manager._build_targeted_summary_sentence(
        formatted,
        rendered_signatures=[],
        used_keys=set(),
    )

    assert "experience in API testing" not in sentence
    assert "SQL checks" not in sentence
    assert "defect analysis" not in sentence


def test_intro_line_filter_keeps_action_evidence_starting_with_platform_or_group() -> None:
    manager = ExportManager()

    assert (
        manager._score_experience_render_line(
            "Platform migration reduced release risk across three products.",
            company="ACME",
            job_title="QA Engineer",
            offer_terms=["release", "risk"],
            language_code="en",
        )
        > -50
    )
    assert (
        manager._score_experience_render_line(
            "Group test cases by risk before release.",
            company="ACME",
            job_title="QA Engineer",
            offer_terms=["release", "risk"],
            language_code="en",
        )
        > -50
    )
    assert (
        manager._score_experience_render_line(
            "Company: platform for patient workflow.",
            company="ACME",
            job_title="QA Engineer",
            offer_terms=["release", "risk"],
            language_code="en",
        )
        <= -50
    )
