from __future__ import annotations

from app.domain.profile.experience_feedback import build_experience_editor_feedback


def test_experience_feedback_uses_present_for_future_end_date() -> None:
    feedback = build_experience_editor_feedback(
        {
            "title": "QA Engineer",
            "company": "ACME",
            "start_date": "09/2024",
            "end_date": "12/2999",
            "description": "Suit les plans de test et analyse les anomalies.",
        },
        language_code="fr",
    )

    assert "poste en cours" in feedback["tense_feedback"]
    assert "présent" in feedback["tense_feedback"]


def test_experience_feedback_guides_past_compose_for_ended_french_role() -> None:
    feedback = build_experience_editor_feedback(
        {
            "title": "QA Engineer",
            "company": "ACME",
            "start_date": "09/2023",
            "end_date": "08/2024",
            "description": "A analysé les anomalies et structuré les retours.",
        },
        language_code="fr",
    )

    assert "passé composé" in feedback["tense_feedback"]
    assert "A analysé" in feedback["tense_feedback"]


def test_experience_feedback_keeps_language_specific_tense_guidance() -> None:
    english = build_experience_editor_feedback(
        {
            "title": "QA Engineer",
            "company": "ACME",
            "start_date": "09/2024",
            "end_date": "Present",
            "description": "Analyzes defects and tracks release readiness.",
        },
        language_code="en",
    )
    japanese = build_experience_editor_feedback(
        {
            "title": "QA Engineer",
            "company": "ACME",
            "start_date": "09/2024",
            "end_date": "Present",
            "description": "品質改善とリリース確認を担当。",
        },
        language_code="ja",
    )

    assert "present tense" in english["tense_feedback"]
    assert "sortie japonaise" in japanese["tense_feedback"]
