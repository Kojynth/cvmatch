"""View-model dataclasses used by main window panels."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from app.models.job_application import ApplicationStatus


@dataclass(slots=True)
class ProfileSummary:
    """Lightweight descriptor for a saved profile."""

    id: int
    name: str
    email: str
    updated_at: Optional[datetime]


@dataclass(slots=True)
class ProfileSnapshot:
    """Normalized profile payload consumed by UI panels."""

    id: Optional[int]
    name: str
    email: str
    phone: Optional[str]
    linkedin_url: Optional[str]
    preferred_template: Optional[str]
    preferred_language: Optional[str]
    learning_enabled: Optional[bool]
    model_version: Optional[str]
    extracted_sections: Dict[str, Any]
    metadata: Dict[str, Any]


@dataclass(slots=True)
class JobOfferViewModel:
    """Structured payload describing a job offer."""

    job_title: str
    company: str
    text: str
    analysis: Dict[str, Any]


@dataclass(slots=True)
class JobApplicationSummary:
    """Snapshot of a generated job application for UI display."""

    id: int
    profile_id: int
    job_title: str
    company: str
    status: ApplicationStatus
    user_rating: Optional[int]
    template_used: str
    created_at: datetime
    updated_at: datetime
    generated_cv_markdown: str
    generated_cover_letter: Optional[str]
    offer_text: str
    notes: Optional[str]
    generated_cv_html: Optional[str] = None
    final_cv_markdown: Optional[str] = None
    final_cv_html: Optional[str] = None
    final_cover_letter: Optional[str] = None
    cv_json_final: Optional[Dict[str, Any]] = None
    match_score: Optional[float] = None


@dataclass(slots=True)
class HistoryRowViewModel:
    """Representation of a table row for the history panel."""

    summary: JobApplicationSummary
    display_status: str
    display_template: str
    display_created_at: str
    display_updated_at: str
