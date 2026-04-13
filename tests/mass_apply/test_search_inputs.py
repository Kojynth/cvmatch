from __future__ import annotations

from types import SimpleNamespace

from app.utils.mass_apply.search_inputs import prepare_search_input


def test_prepare_search_input_keeps_explicit_keywords_and_locations() -> None:
    profile = SimpleNamespace(
        learned_preferences={"preferred_countries": ["France", "Singapore"]},
        extracted_personal_info={"preferred_locations": ["Paris"]},
        extracted_skills=[{"skill": "Python"}],
        extracted_experiences=[{"title": "Data Engineer"}],
    )

    prepared = prepare_search_input(
        profile,
        "ml engineer, python, ml engineer",
        "Singapore, Hong Kong; Switzerland",
    )

    assert prepared.keywords == "ml engineer, python"
    assert prepared.keyword_queries[:2] == ["ml engineer", "python"]
    assert prepared.locations == ["Singapore", "Hong Kong", "Switzerland"]
    assert "Suisse" in prepared.location_queries
    assert prepared.derived_keywords is False
    assert prepared.derived_locations is False


def test_prepare_search_input_derives_profile_context_when_empty() -> None:
    profile = SimpleNamespace(
        learned_preferences={
            "focus_keywords": ["cloud", "devops"],
            "preferred_countries": ["Switzerland", "Singapore"],
        },
        extracted_personal_info={},
        extracted_skills=[{"skill": "Kubernetes"}, {"skill": "Terraform"}],
        extracted_experiences=[{"title": "Cloud Engineer"}],
    )

    prepared = prepare_search_input(profile, "", "")

    assert "cloud" in prepared.keywords.lower()
    assert "cloud engineer" in prepared.keywords.lower()
    assert "Zurich" in prepared.location_queries
    assert prepared.derived_keywords is True
    assert prepared.derived_locations is True
