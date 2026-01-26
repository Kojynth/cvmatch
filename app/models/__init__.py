"""
CVMatch Models Package
=====================

Ce package contient tous les modèles de données pour l'application CVMatch.
"""

# Éviter l'import automatique de database pour prévenir les cycles
# from .database import engine, create_db_and_tables
from .user_profile import UserProfile, LearningRecord, ModelVersion
from .job_application import JobApplication, ApplicationStatus

# Nouveaux modèles d'extraction avec validation Pydantic (Task 9)
from .extraction_schemas import (
    ExperienceItem,
    EducationItem,
    ExtractionResult,
    ConfidenceLevel,
    ExperienceType,
    EducationLevel,
    migrate_legacy_experiences,
    migrate_legacy_education
)

__all__ = [
    # "engine",
    # "create_db_and_tables", 
    "UserProfile",
    "LearningRecord",
    "ModelVersion",
    "JobApplication",
    "ApplicationStatus",
    # Modèles d'extraction
    "ExperienceItem",
    "EducationItem", 
    "ExtractionResult",
    "ConfidenceLevel",
    "ExperienceType",
    "EducationLevel",
    "migrate_legacy_experiences",
    "migrate_legacy_education"
]
