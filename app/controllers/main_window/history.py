"""History coordinator handling application summaries and persistence."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.models.database import get_session
from app.models.job_application import ApplicationStatus, JobApplication

from .base import Coordinator, SimpleCoordinator
from .view_models import HistoryRowViewModel, JobApplicationSummary

logger = logging.getLogger(__name__)


class HistoryCoordinator(SimpleCoordinator, Coordinator):
    """Manages recent applications and export actions."""

    __slots__ = ("_session_factory",)

    def __init__(self, session_factory=None) -> None:
        super().__init__()
        self._session_factory = session_factory or get_session

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    def list_applications(self, profile_id: int) -> List[JobApplicationSummary]:
        """Return summaries for the given profile ordered by recency."""

        with self._session_factory() as session:
            applications: List[JobApplication] = (
                session.query(JobApplication)
                .filter(JobApplication.profile_id == profile_id)
                .order_by(JobApplication.created_at.desc())
                .all()
            )

        return [self._to_summary(app) for app in applications]

    def list_application_rows(self, profile_id: int) -> List[HistoryRowViewModel]:
        """Return table-oriented view-models for UI consumption."""
        summaries = self.list_applications(profile_id)
        return [self.to_row_view_model(summary) for summary in summaries]

    def to_row_view_model(self, summary: JobApplicationSummary) -> HistoryRowViewModel:
        """Convert a summary into a table row view-model."""
        created_at = summary.created_at.strftime("%d/%m/%Y") if summary.created_at else "-"
        updated_at = summary.updated_at.strftime("%d/%m/%Y") if summary.updated_at else "-"
        template = summary.template_used or "-"
        status = summary.status.value.title()
        return HistoryRowViewModel(
            summary=summary,
            display_status=status,
            display_template=template,
            display_created_at=created_at,
            display_updated_at=updated_at,
        )

    def get_application(self, application_id: int) -> Optional[JobApplication]:
        """Return the persisted application entity."""

        with self._session_factory() as session:
            application = session.get(JobApplication, application_id)
            if application is None:
                return None
            session.expunge(application)
            return application

    def get_application_summary(
        self, application_id: int
    ) -> Optional[JobApplicationSummary]:
        """Return a summary for a specific application id."""
        application = self.get_application(application_id)
        if application is None:
            return None
        return self._to_summary(application)

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------
    def duplicate_application(self, application_id: int) -> Optional[JobApplicationSummary]:
        """Duplicate an application entry and return its summary."""

        with self._session_factory() as session:
            source = session.get(JobApplication, application_id)
            if source is None:
                return None

            duplicate = JobApplication(
                profile_id=source.profile_id,
                job_title=source.job_title,
                company=source.company,
                offer_text=source.offer_text,
                offer_url=source.offer_url,
                offer_file_path=source.offer_file_path,
                offer_analysis=source.offer_analysis,
                template_used=source.template_used,
                model_version_used=source.model_version_used,
                generated_cv_markdown=source.generated_cv_markdown,
                generated_cv_html=source.generated_cv_html,
                generated_cover_letter=source.generated_cover_letter,
                profile_json=source.profile_json,
                critic_json=source.critic_json,
                cv_json_draft=source.cv_json_draft,
                cv_json_final=source.cv_json_final,
                final_cv_markdown=source.final_cv_markdown,
                final_cv_html=source.final_cv_html,
                final_cover_letter=source.final_cover_letter,
                status=ApplicationStatus.DRAFT,
                user_rating=None,
                user_edited=False,
                user_comments=None,
                notes=None,
            )
            session.add(duplicate)
            session.commit()
            session.refresh(duplicate)
            session.expunge(duplicate)

        return self._to_summary(duplicate)

    def delete_application(self, application_id: int) -> bool:
        """Delete an application entry."""

        with self._session_factory() as session:
            application = session.get(JobApplication, application_id)
            if application is None:
                return False
            session.delete(application)
            session.commit()
        return True

    def update_status(
        self,
        application_id: int,
        new_status: ApplicationStatus,
        *,
        notes: Optional[str] = None,
    ) -> Optional[JobApplicationSummary]:
        """Update the application status and return the refreshed summary."""

        with self._session_factory() as session:
            application = session.get(JobApplication, application_id)
            if application is None:
                return None

            application.update_status(new_status, notes)
            session.add(application)
            session.commit()
            session.refresh(application)
            session.expunge(application)

        return self._to_summary(application)

    def save_user_edits(
        self,
        application_id: int,
        *,
        final_cv_html: Optional[str] = None,
        final_cv_markdown: Optional[str] = None,
        final_cover_letter: Optional[str] = None,
    ) -> Optional[JobApplicationSummary]:
        """Persist user edits for a generated application."""
        with self._session_factory() as session:
            application = session.get(JobApplication, application_id)
            if application is None:
                return None

            if final_cv_html is not None:
                application.final_cv_html = final_cv_html
            if final_cv_markdown is not None:
                application.final_cv_markdown = final_cv_markdown
            if final_cover_letter is not None:
                application.final_cover_letter = final_cover_letter

            application.user_edited = True
            application.updated_at = datetime.now()
            session.add(application)
            session.commit()
            session.refresh(application)
            session.expunge(application)

        return self._to_summary(application)

    def create_generic_application(
        self,
        *,
        profile_id: int,
        job_title: str,
        company: str,
        template_used: str,
        model_version_used: str,
        generated_cv_markdown: str,
        generated_cv_html: Optional[str] = None,
        profile_json: Optional[Dict[str, Any]] = None,
        cv_json_final: Optional[Dict[str, Any]] = None,
        offer_analysis: Optional[Dict[str, Any]] = None,
        notes: Optional[str] = None,
    ) -> Optional[JobApplicationSummary]:
        """Persist a standalone generic CV generation in history."""

        if not profile_id:
            return None

        with self._session_factory() as session:
            application = JobApplication(
                profile_id=int(profile_id),
                job_title=str(job_title or "CV Générique")[:200],
                company=str(company or "N/A")[:100],
                offer_text="",
                offer_analysis=(
                    dict(offer_analysis)
                    if isinstance(offer_analysis, dict)
                    else {"generation_mode": "generic"}
                ),
                template_used=str(template_used or "modern")[:50],
                model_version_used=str(model_version_used or "generic")[:20],
                generated_cv_markdown=str(generated_cv_markdown or ""),
                generated_cv_html=generated_cv_html,
                generated_cover_letter=None,
                profile_json=(
                    dict(profile_json) if isinstance(profile_json, dict) else None
                ),
                cv_json_final=(
                    dict(cv_json_final) if isinstance(cv_json_final, dict) else None
                ),
                status=ApplicationStatus.DRAFT,
                notes=str(notes or "").strip() or None,
            )
            session.add(application)
            session.commit()
            session.refresh(application)
            session.expunge(application)

        try:
            from sqlmodel import text

            with self._session_factory() as session:
                session.execute(
                    text(
                        "UPDATE userprofile SET total_cvs_generated = total_cvs_generated + 1 WHERE id = :pid"
                    ),
                    {"pid": int(profile_id)},
                )
                session.commit()
        except Exception as exc:
            logger.warning(
                "Impossible de mettre à jour les stats du profil %s: %s",
                profile_id,
                exc,
            )

        return self._to_summary(application)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _to_summary(application: JobApplication) -> JobApplicationSummary:
        """Convert the SQLModel instance into a UI-friendly snapshot."""

        return JobApplicationSummary(
            id=application.id or -1,
            profile_id=application.profile_id,
            job_title=application.job_title,
            company=application.company,
            status=application.status,
            user_rating=application.user_rating,
            template_used=application.template_used,
            created_at=application.created_at,
            updated_at=application.updated_at,
            generated_cv_markdown=application.generated_cv_markdown,
            generated_cv_html=application.generated_cv_html,
            generated_cover_letter=application.generated_cover_letter,
            final_cv_markdown=application.final_cv_markdown,
            final_cv_html=application.final_cv_html,
            final_cover_letter=application.final_cover_letter,
            cv_json_final=application.cv_json_final,
            offer_analysis=application.offer_analysis,
            offer_text=application.offer_text,
            notes=application.notes,
            match_score=application.get_match_score() if hasattr(application, "get_match_score") else None,
        )
