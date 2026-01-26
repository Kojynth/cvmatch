"""
Panel placeholders introduced for the main window refactor.

The refactor will replace the current monolithic widgets with these
focused panels. For now they are lightweight classes so imports and
tests can target stable entry points.
"""

from .history_panel import HistoryPanel
from .job_application_panel import JobApplicationPanel
from .linkedin_panel import LinkedInPanel
from .profile import ProfilePanel
from .settings_panel import SettingsPanel
from .sidebar_panel import SidebarPanel

__all__ = [
    "HistoryPanel",
    "JobApplicationPanel",
    "LinkedInPanel",
    "ProfilePanel",
    "SettingsPanel",
    "SidebarPanel",
]
