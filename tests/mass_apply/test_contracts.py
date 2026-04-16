from __future__ import annotations

from app.domain.mass_apply import (
    ApplyExecutionResult,
    HumanReviewDecision,
    PreparedApplication,
    QualificationDecision,
)


def test_mass_apply_contract_defaults() -> None:
    qualification = QualificationDecision(decision="qualified", confidence_score=82)
    prepared = PreparedApplication(profile_id=1, offer_id="offer-7")
    review = HumanReviewDecision(approved=True)
    result = ApplyExecutionResult(status="queued")

    assert qualification.requires_human_review is False
    assert prepared.template == "modern"
    assert review.overrides == {}
    assert result.errors == []
