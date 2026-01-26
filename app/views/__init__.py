"""
CVMatch Views Package
====================

Package contenant toutes les interfaces graphiques de l'application.
"""

from .main_window import MainWindowWithSidebar
from .profile_setup import ProfileSetupDialog

try:
    from .settings_dialog import SettingsDialog
    __all__ = [
        "MainWindowWithSidebar",
        "ProfileSetupDialog", 
        "SettingsDialog",
    ]
except (ImportError, SyntaxError, IndentationError):
    __all__ = [
        "MainWindowWithSidebar",
        "ProfileSetupDialog",
    ]
