"""
Worker Data Classes
====================

Dataclasses pour passer des données aux workers sans dépendance ORM.
Évite les erreurs SQLAlchemy DetachedInstanceError dans les threads background.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any
from datetime import datetime


@dataclass
class ProfileWorkerData:
    """Données de profil extraites pour utilisation dans les workers.

    Cette classe copie les valeurs nécessaires d'un UserProfile SQLModel
    pour éviter les accès lazy-load dans les threads background.
    """

    # Identifiant
    id: int

    # Informations de base
    name: str
    email: str
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None

    # Version du modèle IA (valeur string, pas l'enum)
    model_version: str = "base"

    # Documents de référence
    master_cv_content: Optional[str] = None
    default_cover_letter: Optional[str] = None

    # Préférences
    preferred_template: str = "modern"
    preferred_language: str = "fr"

    # Données extraites (copies des JSON)
    extracted_personal_info: Optional[Dict[str, Any]] = None
    extracted_experiences: Optional[List[Dict[str, Any]]] = None
    extracted_education: Optional[List[Dict[str, Any]]] = None
    extracted_skills: Optional[List[Dict[str, Any]]] = None
    extracted_soft_skills: Optional[List[Dict[str, Any]]] = None
    extracted_languages: Optional[List[Dict[str, Any]]] = None
    extracted_projects: Optional[List[Dict[str, Any]]] = None
    extracted_certifications: Optional[List[Dict[str, Any]]] = None
    extracted_publications: Optional[List[Dict[str, Any]]] = None
    extracted_volunteering: Optional[List[Dict[str, Any]]] = None
    extracted_interests: Optional[List[str]] = None
    extracted_awards: Optional[List[Dict[str, Any]]] = None
    extracted_references: Optional[List[Dict[str, Any]]] = None

    # Données LinkedIn
    linkedin_data: Optional[Dict[str, Any]] = None

    # Statistiques (lecture seule - les modifications passent par signaux)
    total_cvs_generated: int = 0
    total_cvs_validated: int = 0
    average_rating: float = 0.0

    # Préférences apprises
    learned_preferences: Optional[Dict[str, Any]] = None

    @classmethod
    def from_profile(cls, profile: "UserProfile") -> "ProfileWorkerData":
        """Extrait les données d'un profil SQLModel.

        Args:
            profile: Instance UserProfile (peut être détachée après cet appel)

        Returns:
            ProfileWorkerData avec toutes les valeurs copiées
        """
        # Extraire model_version.value de manière sécurisée
        model_version_value = "base"
        try:
            if profile.model_version is not None:
                model_version_value = (
                    profile.model_version.value
                    if hasattr(profile.model_version, "value")
                    else str(profile.model_version)
                )
        except Exception:
            model_version_value = "base"

        return cls(
            id=profile.id or 0,
            name=profile.name or "",
            email=profile.email or "",
            phone=profile.phone,
            linkedin_url=profile.linkedin_url,
            model_version=model_version_value,
            master_cv_content=profile.master_cv_content,
            default_cover_letter=profile.default_cover_letter,
            preferred_template=profile.preferred_template or "modern",
            preferred_language=profile.preferred_language or "fr",
            extracted_personal_info=profile.extracted_personal_info,
            extracted_experiences=profile.extracted_experiences,
            extracted_education=profile.extracted_education,
            extracted_skills=profile.extracted_skills,
            extracted_soft_skills=profile.extracted_soft_skills,
            extracted_languages=profile.extracted_languages,
            extracted_projects=profile.extracted_projects,
            extracted_certifications=profile.extracted_certifications,
            extracted_publications=profile.extracted_publications,
            extracted_volunteering=profile.extracted_volunteering,
            extracted_interests=profile.extracted_interests,
            extracted_awards=profile.extracted_awards,
            extracted_references=profile.extracted_references,
            linkedin_data=profile.linkedin_data,
            total_cvs_generated=profile.total_cvs_generated or 0,
            total_cvs_validated=profile.total_cvs_validated or 0,
            average_rating=profile.average_rating or 0.0,
            learned_preferences=profile.learned_preferences,
        )
