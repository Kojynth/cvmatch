"""Stable domain contracts for the mass-apply workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(slots=True)
class QualificationDecision:
    decision: str
    confidence_score: int = 0
    reasons: List[str] = field(default_factory=list)
    requires_human_review: bool = False


@dataclass(slots=True)
class PreparedApplication:
    profile_id: int
    offer_id: str
    template: str = "modern"
    selected_model_id: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class HumanReviewDecision:
    approved: bool
    reviewer_note: str = ""
    overrides: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ApplyExecutionResult:
    status: str
    provider: str = ""
    application_id: Optional[int] = None
    external_reference: str = ""
    errors: List[str] = field(default_factory=list)
