"""Application bootstrap helpers for the main window refactor."""

from __future__ import annotations

from dataclasses import dataclass

from app.controllers.main_window import (
    ExtractionCoordinator,
    HistoryCoordinator,
    JobApplicationCoordinator,
    LinkedInCoordinator,
    MlWorkflowCoordinator,
    NavigationCoordinator,
    ProfileStateCoordinator,
    SettingsCoordinator,
)
from app.controllers.main_window.base import CoordinatorContext
from app.services import DialogService, NavigationService, ProgressService, TelemetryService


@dataclass(slots=True)
class BootstrapArtifacts:
    """Container for the coordinators/services created at startup."""

    context: CoordinatorContext
    extraction: ExtractionCoordinator
    profile_state: ProfileStateCoordinator
    linkedin: LinkedInCoordinator
    ml_workflow: MlWorkflowCoordinator
    job_applications: JobApplicationCoordinator
    history: HistoryCoordinator
    navigation: NavigationCoordinator
    settings: SettingsCoordinator


def create_main_window_environment() -> BootstrapArtifacts:
    """
    Create coordinator instances and bind the shared context.

    The implementation is intentionally lightweight for now; it wires
    default service placeholders so tests can begin targeting the new
    module layout before real behaviour is ported.
    """

    context = CoordinatorContext(
        telemetry=TelemetryService(),
        dialog_service=DialogService(),
        progress_service=ProgressService(),
    )

    extraction = ExtractionCoordinator()
    profile_state = ProfileStateCoordinator()
    linkedin = LinkedInCoordinator()
    ml_workflow = MlWorkflowCoordinator()
    job_applications = JobApplicationCoordinator()
    history = HistoryCoordinator()
    navigation = NavigationCoordinator()
    settings = SettingsCoordinator()

    for coordinator in (
        extraction,
        profile_state,
        linkedin,
        ml_workflow,
        job_applications,
        history,
        navigation,
        settings,
    ):
        coordinator.bind(context)

    return BootstrapArtifacts(
        context=context,
        extraction=extraction,
        profile_state=profile_state,
        linkedin=linkedin,
        ml_workflow=ml_workflow,
        job_applications=job_applications,
        history=history,
        navigation=navigation,
        settings=settings,
    )
