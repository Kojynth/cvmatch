"""
Service abstractions used by the refactored main window.

Each service hides side-effectful behaviour behind a simple interface so
coordinators can remain pure-Python and test-friendly.
"""

from .dialog_service import DialogService
from .navigation_service import NavigationService
from .progress_service import ProgressService
from .telemetry import TelemetryService

__all__ = ["DialogService", "NavigationService", "ProgressService", "TelemetryService"]
