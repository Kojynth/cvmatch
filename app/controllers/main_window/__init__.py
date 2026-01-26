"""
Coordinator skeletons for the main window refactor.

The real implementations will arrive incrementally as legacy logic is
split out of `app.views.main_window`. For now we expose lightweight
placeholders so downstream modules can depend on stable names.
"""

from .base import Coordinator, CoordinatorContext, SimpleCoordinator
from .extraction import ExtractionCoordinator
from .history import HistoryCoordinator
from .job_applications import JobApplicationCoordinator
from .linkedin import LinkedInCoordinator
from .ml_workflow import MlWorkflowCoordinator
from .navigation import NavigationCoordinator
from .profile_state import ProfileStateCoordinator
from .settings import SettingsCoordinator

__all__ = [
    "Coordinator",
    "CoordinatorContext",
    "ExtractionCoordinator",
    "HistoryCoordinator",
    "JobApplicationCoordinator",
    "LinkedInCoordinator",
    "MlWorkflowCoordinator",
    "NavigationCoordinator",
    "ProfileStateCoordinator",
    "SettingsCoordinator",
    "SimpleCoordinator",
]
