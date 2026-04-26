from __future__ import annotations

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
    assert "Atouts pertinents pour Mistral AI" in summary
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
