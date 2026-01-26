"""
CVMatch Workers Package
======================

Package contenant tous les workers QThread pour les tâches asynchrones.
"""

from .llm_worker import CVGenerationWorker, QwenManager
from .profile_parser import ProfileParserWorker

__all__ = [
    "CVGenerationWorker",
    "QwenManager", 
    "ProfileParserWorker",
]
