"""Bootstrap helpers for the main window lifecycle orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, cast

from app.controllers.main_window import (
    ExtractionCoordinator,
    HistoryCoordinator,
    JobApplicationCoordinator,
    LinkedInCoordinator,
    MlWorkflowCoordinator,
    NavigationCoordinator,
    ProfileStateCoordinator,
    SettingsCoordinator,
    Coordinator,
)
from app.controllers.main_window.base import CoordinatorContext
from app.lifecycle.bootstrap import BootstrapArtifacts, create_main_window_environment
from app.models.user_profile import UserProfile
from app.services import DialogService, ProgressService, TelemetryService
from app.views.main_window import MainWindowWithSidebar

__all__ = ["LifecycleServices", "bootstrap_main_window"]


@dataclass(slots=True)
class LifecycleServices:
    """
    Container exposing the coordinators and services required by the main window.

    The dataclass centralises the shared coordinator context so that both GUI and CLI
    entry points can bootstrap the application shell without touching PySide6 internals.
    """

    context: CoordinatorContext
    extraction: ExtractionCoordinator
    profile_state: ProfileStateCoordinator
    linkedin: LinkedInCoordinator
    ml_workflow: MlWorkflowCoordinator
    job_applications: JobApplicationCoordinator
    history: HistoryCoordinator
    navigation: NavigationCoordinator
    settings: SettingsCoordinator
    progress_service: ProgressService
    dialog_service: DialogService
    telemetry_service: TelemetryService

    @classmethod
    def from_artifacts(
        cls,
        artifacts: BootstrapArtifacts,
        *,
        progress_service: Optional[ProgressService] = None,
        dialog_service: Optional[DialogService] = None,
        telemetry_service: Optional[TelemetryService] = None,
    ) -> "LifecycleServices":
        """Promote bootstrap artifacts to a LifecycleServices container."""

        context = artifacts.context

        telemetry = telemetry_service or cast(TelemetryService, context.telemetry or TelemetryService())
        dialog = dialog_service or cast(DialogService, context.dialog_service or DialogService())
        progress = progress_service or cast(ProgressService, context.progress_service or ProgressService())

        context.telemetry = telemetry
        context.dialog_service = dialog
        context.progress_service = progress

        return cls(
            context=context,
            extraction=artifacts.extraction,
            profile_state=artifacts.profile_state,
            linkedin=artifacts.linkedin,
            ml_workflow=artifacts.ml_workflow,
            job_applications=artifacts.job_applications,
            history=artifacts.history,
            navigation=artifacts.navigation,
            settings=artifacts.settings,
            progress_service=progress,
            dialog_service=dialog,
            telemetry_service=telemetry,
        )

    @classmethod
    def create_default(cls) -> "LifecycleServices":
        """Instantiate the default coordinators/services for the application."""

        artifacts = create_main_window_environment()
        return cls.from_artifacts(artifacts)

    def iter_coordinators(self) -> tuple[Coordinator, ...]:
        """Return all coordinators managed by the lifecycle container."""

        return (
            self.extraction,
            self.profile_state,
            self.linkedin,
            self.ml_workflow,
            self.job_applications,
            self.history,
            self.navigation,
            self.settings,
        )


def bootstrap_main_window(
    profile: UserProfile,
    *,
    services: Optional[LifecycleServices] = None,
    parent=None,
) -> MainWindowWithSidebar:
    """
    Construct the main window shell with the supplied lifecycle services.

    When ``services`` is omitted the default coordinator/service bundle is created.
    The job application coordinator is rebound to the requested profile so worker
    flows keep receiving the active user context.
    """

    lifecycle = services or LifecycleServices.create_default()

    try:
        lifecycle.job_applications.bind_profile(profile)
    except Exception:
        lifecycle.job_applications.profile = profile  # type: ignore[attr-defined]

    window = MainWindowWithSidebar(profile, lifecycle=lifecycle, parent=parent)

    try:
        lifecycle.progress_service.set_parent(window)
    except Exception:
        pass

    return window
