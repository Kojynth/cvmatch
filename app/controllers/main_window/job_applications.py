"""Coordinator managing job application generation workflows."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from ...models.database import get_session
from ...models.job_application import ApplicationStatus, JobApplication
from ...models.user_profile import UserProfile
from ...workers.llm_worker import CVGenerationWorker, CoverLetterGenerationWorker
from ...workers.worker_data import ProfileWorkerData
from .base import Coordinator, SimpleCoordinator


class JobApplicationCoordinator(SimpleCoordinator, Coordinator):
    """Coordinates job application and cover letter generation flows."""

    __slots__ = ("profile", "_active_workers")

    def __init__(self, profile: Optional[UserProfile] = None) -> None:
        super().__init__()
        self.profile: Optional[UserProfile] = profile
        self._active_workers: List[Any] = []

    # ------------------------------------------------------------------
    # Profile management
    # ------------------------------------------------------------------
    def bind_profile(self, profile: UserProfile) -> None:
        """Associate the coordinator with the active user profile."""

        self.profile = profile

    def refresh_profile(self) -> Optional[UserProfile]:
        """Reload the bound profile from the database."""

        if not self.profile or getattr(self.profile, "id", None) is None:
            return self.profile

        with get_session() as session:
            refreshed = session.get(UserProfile, self.profile.id)
            if refreshed:
                session.expunge(refreshed)
                self.profile = refreshed
        return self.profile

    # ------------------------------------------------------------------
    # Worker lifecycle
    # ------------------------------------------------------------------
    def _ensure_profile(self) -> UserProfile:
        if not self.profile:
            raise RuntimeError("JobApplicationCoordinator requires a bound profile")
        return self.profile

    def create_cv_worker(self, *, offer_data: Dict[str, Any], template: str) -> CVGenerationWorker:
        """Instantiate a CV generation worker and track it.

        Note: Extrait les données du profil AVANT de passer au worker
        pour éviter les erreurs SQLAlchemy DetachedInstanceError.
        """
        profile = self._ensure_profile()
        # Extraire les données du profil dans le thread principal (session active)
        profile_data = ProfileWorkerData.from_profile(profile)

        worker = CVGenerationWorker(
            profile_data=profile_data,
            offer_data=offer_data,
            template=template
        )
        self._active_workers.append(worker)
        return worker

    def create_cover_letter_worker(
        self,
        *,
        offer_data: Dict[str, Any],
        template: str,
        application_id: Optional[int] = None,
    ) -> CoverLetterGenerationWorker:
        """Instantiate a cover letter worker and track it.

        Note: Extrait les données du profil AVANT de passer au worker
        pour éviter les erreurs SQLAlchemy DetachedInstanceError.
        """
        profile = self._ensure_profile()
        # Extraire les données du profil dans le thread principal (session active)
        profile_data = ProfileWorkerData.from_profile(profile)

        worker = CoverLetterGenerationWorker(
            profile_data=profile_data,
            offer_data=offer_data,
            template=template,
            application_id=application_id,
        )
        self._active_workers.append(worker)
        return worker

    def release_worker(self, worker: Any) -> None:
        """Stop tracking a worker once it has finished."""

        try:
            self._active_workers.remove(worker)
        except ValueError:
            return

    def iter_active_workers(self) -> Iterable[Any]:
        """Return a snapshot of active workers."""

        return tuple(self._active_workers)

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------
    def duplicate_application(self, source: JobApplication) -> JobApplication:
        """Persist a duplicated job application entry."""

        profile = self._ensure_profile()
        duplicate = JobApplication(
            profile_id=profile.id,
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
            final_cv_markdown=source.final_cv_markdown,
            final_cv_html=source.final_cv_html,
            final_cover_letter=source.final_cover_letter,
            status=ApplicationStatus.DRAFT,
            user_rating=None,
            user_edited=False,
            user_comments=None,
            exported_pdf_path=None,
            exported_at=None,
            sent_at=None,
            interview_date=None,
            response_received_at=None,
            notes=None,
        )

        with get_session() as session:
            session.add(duplicate)
            session.commit()
            session.refresh(duplicate)
        return duplicate

    def delete_application(self, application: JobApplication) -> bool:
        """Delete a job application entry if it exists."""

        if application.id is None:
            return False

        with get_session() as session:
            existing = session.get(JobApplication, application.id)
            if not existing:
                return False
            session.delete(existing)
            session.commit()
        return True

    def update_status(self, application: JobApplication, status: ApplicationStatus) -> JobApplication:
        """Persist a status change and return the refreshed entity."""

        if application.id is None:
            application.update_status(status)
            return application

        with get_session() as session:
            existing = session.get(JobApplication, application.id)
            if not existing:
                return application
            existing.update_status(status)
            session.add(existing)
            session.commit()
            session.refresh(existing)
        return existing
