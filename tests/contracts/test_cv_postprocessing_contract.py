from __future__ import annotations

from app.utils.cv_postprocessing import coerce_generated_cv_payload


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
