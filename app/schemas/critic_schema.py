"""Strict Critic JSON schema."""

from __future__ import annotations

from enum import Enum
from typing import List

from pydantic import BaseModel, Field, model_validator


class IssueSeverity(str, Enum):
    blocker = "blocker"
    high = "high"
    medium = "medium"
    low = "low"


class IssueCategory(str, Enum):
    ats = "ATS"
    structure = "structure"
    evidence = "evidence"
    relevance = "relevance"
    style = "style"
    consistency = "consistency"
    formatting = "formatting"
    language = "language"


class ScorecardWeights(BaseModel):
    ats_keyword_coverage: float = 0.30
    clarity: float = 0.20
    evidence_metrics: float = 0.30
    consistency: float = 0.20


class Scorecard(BaseModel):
    ats_keyword_coverage: int = Field(ge=0, le=100)
    clarity: int = Field(ge=0, le=100)
    evidence_metrics: int = Field(ge=0, le=100)
    consistency: int = Field(ge=0, le=100)
    overall: int = Field(ge=0, le=100, default=0)
    weights: ScorecardWeights = Field(default_factory=ScorecardWeights)

    @model_validator(mode="after")
    def compute_overall(self) -> "Scorecard":
        weights = ScorecardWeights()
        ats = min(max(int(self.ats_keyword_coverage), 0), 100)
        clarity = min(max(int(self.clarity), 0), 100)
        evidence = min(max(int(self.evidence_metrics), 0), 100)
        consistency = min(max(int(self.consistency), 0), 100)
        overall = round(
            ats * weights.ats_keyword_coverage
            + clarity * weights.clarity
            + evidence * weights.evidence_metrics
            + consistency * weights.consistency
        )
        self.weights = weights
        self.overall = min(max(int(overall), 0), 100)
        return self


class CriticIssue(BaseModel):
    severity: IssueSeverity
    category: IssueCategory
    problem: str
    evidence: str
    fix: str


class CriticJSON(BaseModel):
    schema_version: str = Field(default="critic.v1")
    scorecard: Scorecard
    issues: List[CriticIssue] = Field(default_factory=list)
    missing_keywords: List[str] = Field(default_factory=list)
    rewrite_plan: List[str] = Field(default_factory=list)
    rewrite_prompt: str
    must_keep_facts: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def clamp_for_blockers(self) -> "CriticJSON":
        if any(issue.severity == IssueSeverity.blocker for issue in self.issues):
            self.scorecard.overall = min(self.scorecard.overall, 39)
        return self
