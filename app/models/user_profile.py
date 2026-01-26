"""
User Profile Models
==================

Modèles pour gérer les profils utilisateur et l'apprentissage.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
from sqlmodel import SQLModel, Field, Relationship, Column, String, Text, JSON
from pydantic import EmailStr


class ModelVersion(str, Enum):
    """Versions de modèles IA disponibles."""
    BASE = "base"
    V1 = "v1"
    V2 = "v2"
    V3 = "v3"
    LATEST = "latest"


class UserProfile(SQLModel, table=True):
    """Profil utilisateur principal avec apprentissage."""
    
    # ID et infos de base
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(max_length=100)
    email: str = Field(max_length=255)
    phone: Optional[str] = Field(default=None, max_length=20)
    linkedin_url: Optional[str] = Field(default=None, max_length=500)
    linkedin_pdf_path: Optional[str] = Field(
        default=None, max_length=1024,
        description="Chemin sécurisé vers le PDF export LinkedIn"
    )
    linkedin_pdf_checksum: Optional[str] = Field(
        default=None, max_length=128,
        description="Empreinte SHA256 du PDF LinkedIn"
    )
    linkedin_pdf_uploaded_at: Optional[datetime] = Field(
        default=None,
        description="Horodatage de l'upload du PDF LinkedIn"
    )

    # Documents de référence
    master_cv_path: Optional[str] = Field(default=None, max_length=1000)
    master_cv_content: Optional[str] = Field(default=None, sa_column=Column(Text))
    default_cover_letter: Optional[str] = Field(default=None, sa_column=Column(Text))

    # Données extraites du CV (structurées)
    extracted_personal_info: Optional[Dict[str, Any]] = Field(
        default=None, sa_column=Column(JSON),
        description="Informations personnelles extraites (nom, contact, etc.)"
    )
    extracted_experiences: Optional[List[Dict[str, Any]]] = Field(
        default=None, sa_column=Column(JSON),
        description="Expériences professionnelles structurées"
    )
    extracted_education: Optional[List[Dict[str, Any]]] = Field(
        default=None, sa_column=Column(JSON),
        description="Formations et diplômes"
    )
    extracted_skills: Optional[List[Dict[str, Any]]] = Field(
        default=None, sa_column=Column(JSON),
        description="Compétences techniques"
    )
    extracted_soft_skills: Optional[List[Dict[str, Any]]] = Field(
        default=None, sa_column=Column(JSON),
        description="Soft skills et compétences comportementales"
    )
    extracted_languages: Optional[List[Dict[str, Any]]] = Field(
        default=None, sa_column=Column(JSON),
        description="Langues parlées avec niveaux"
    )
    extracted_projects: Optional[List[Dict[str, Any]]] = Field(
        default=None, sa_column=Column(JSON),
        description="Projets et réalisations"
    )
    extracted_certifications: Optional[List[Dict[str, Any]]] = Field(
        default=None, sa_column=Column(JSON),
        description="Certifications professionnelles"
    )
    extracted_publications: Optional[List[Dict[str, Any]]] = Field(
        default=None, sa_column=Column(JSON),
        description="Publications, articles, recherches"
    )
    extracted_volunteering: Optional[List[Dict[str, Any]]] = Field(
        default=None, sa_column=Column(JSON),
        description="Bénévolat et engagements associatifs"
    )
    extracted_interests: Optional[List[str]] = Field(
        default=None, sa_column=Column(JSON),
        description="Centres d'intérêt et hobbies"
    )
    extracted_awards: Optional[List[Dict[str, Any]]] = Field(
        default=None, sa_column=Column(JSON),
        description="Récompenses et distinctions"
    )
    extracted_references: Optional[List[Dict[str, Any]]] = Field(
        default=None, sa_column=Column(JSON),
        description="Références professionnelles"
    )
    
    # Données LinkedIn (si disponibles)
    linkedin_data: Optional[Dict[str, Any]] = Field(
        default=None, sa_column=Column(JSON),
        description="Données extraites de LinkedIn"
    )
    linkedin_last_sync: Optional[datetime] = Field(
        default=None,
        description="Dernière synchronisation LinkedIn"
    )
    linkedin_sync_status: Optional[str] = Field(
        default=None, max_length=50,
        description="Statut de la sync LinkedIn (success, error, private, etc.)"
    )
    
    # Préférences et configuration
    preferred_template: str = Field(default="modern", max_length=50)
    preferred_language: str = Field(default="fr", max_length=10)
    model_version: ModelVersion = Field(default=ModelVersion.BASE)
    learning_enabled: bool = Field(default=True)
    
    # Métadonnées d'apprentissage
    total_cvs_generated: int = Field(default=0)
    total_cvs_validated: int = Field(default=0)
    average_rating: float = Field(default=0.0)
    last_fine_tuning: Optional[datetime] = Field(default=None)
    
    # Préférences apprises (JSON)
    learned_preferences: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSON)
    )
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    
    # Relations
    job_applications: List["JobApplication"] = Relationship(back_populates="profile")
    learning_records: List["LearningRecord"] = Relationship(back_populates="profile")

    def update_learning_stats(self, rating: int):
        """Met à jour les statistiques d'apprentissage."""
        self.total_cvs_validated += 1
        total_points = (self.average_rating * (self.total_cvs_validated - 1)) + rating
        self.average_rating = total_points / self.total_cvs_validated
        self.updated_at = datetime.now()

    def should_trigger_fine_tuning(self, threshold: int = 10) -> bool:
        """Détermine s'il faut déclencher un fine-tuning."""
        if not self.learning_enabled:
            return False
        
        cvs_since_last_tuning = self.total_cvs_validated
        if self.last_fine_tuning:
            # Compter les CV depuis le dernier fine-tuning
            # (logique simplifiée pour le MVP)
            pass
        
        return cvs_since_last_tuning >= threshold

    def get_model_path(self) -> str:
        """Retourne le chemin vers le modèle personnalisé."""
        if self.model_version == ModelVersion.BASE:
            return "models/qwen2.5-32b-base/"
        return f"models/qwen2.5-32b-{self.name.lower().replace(' ', '_')}-{self.model_version.value}/"
    
    def get_extraction_completeness(self) -> Dict[str, bool]:
        """Retourne l'état de complétude des données extraites."""
        return {
            "personal_info": bool(self.extracted_personal_info),
            "experiences": bool(self.extracted_experiences),
            "education": bool(self.extracted_education),
            "skills": bool(self.extracted_skills),
            "languages": bool(self.extracted_languages),
            "projects": bool(self.extracted_projects),
            "certifications": bool(self.extracted_certifications),
            "publications": bool(self.extracted_publications),
            "volunteering": bool(self.extracted_volunteering),
            "interests": bool(self.extracted_interests),
            "awards": bool(self.extracted_awards),
            "references": bool(self.extracted_references),
            "linkedin_data": bool(self.linkedin_data)
        }
    
    def get_completion_percentage(self) -> int:
        """Calcule le pourcentage de complétude du profil."""
        completeness = self.get_extraction_completeness()
        # Pondération des sections (obligatoires vs optionnelles)
        weights = {
            "personal_info": 20,  # Obligatoire
            "experiences": 25,    # Obligatoire
            "education": 20,      # Obligatoire
            "skills": 15,         # Important
            "languages": 5,       # Optionnel
            "projects": 5,        # Optionnel
            "certifications": 3,  # Optionnel
            "publications": 2,    # Optionnel
            "volunteering": 2,    # Optionnel
            "interests": 1,       # Optionnel
            "awards": 1,          # Optionnel
            "references": 1,      # Optionnel
            "linkedin_data": 0    # Bonus (ne compte pas dans le pourcentage)
        }
        
        total_weight = sum(weights.values())
        achieved_weight = sum(
            weight for field, weight in weights.items() 
            if completeness.get(field, False)
        )
        
        return int((achieved_weight / total_weight) * 100)
    
    def has_linkedin_pdf(self) -> bool:
        """Indique si un PDF LinkedIn a été importé."""
        return bool(self.linkedin_pdf_path)

    def has_linkedin_data(self) -> bool:
        """Vérifie si des données LinkedIn sont disponibles."""
        return bool(self.linkedin_data and self.linkedin_sync_status == "success")

    def needs_linkedin_resync(self, days_threshold: int = 30) -> bool:
        """Détermine si une resynchronisation LinkedIn est recommandée."""
        reference_time = self.linkedin_pdf_uploaded_at or self.linkedin_last_sync
        if self.linkedin_pdf_path:
            return not reference_time or (datetime.now() - reference_time).days > days_threshold
        if self.linkedin_url:
            if not self.linkedin_last_sync:
                return True
            return (datetime.now() - self.linkedin_last_sync).days > days_threshold
        return False


class LearningRecord(SQLModel, table=True):
    """Enregistrement d'apprentissage pour fine-tuning."""
    
    id: Optional[int] = Field(default=None, primary_key=True)
    profile_id: int = Field(foreign_key="userprofile.id")
    
    # Données d'apprentissage
    job_offer_text: str = Field(sa_column=Column(Text))
    ai_generated_cv: str = Field(sa_column=Column(Text))
    user_final_cv: str = Field(sa_column=Column(Text))
    user_rating: int = Field(ge=1, le=5)  # 1-5 étoiles
    
    # Améliorations détectées (JSON)
    improvements_detected: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSON)
    )
    
    # Contexte de génération
    template_used: str = Field(max_length=50)
    language_used: str = Field(max_length=10)
    model_version_used: ModelVersion
    
    # Feedback utilisateur
    user_comments: Optional[str] = Field(default=None, sa_column=Column(Text))
    time_spent_editing: Optional[int] = Field(default=None)  # secondes
    
    # Métadonnées
    created_at: datetime = Field(default_factory=datetime.now)
    
    # Relations
    profile: Optional[UserProfile] = Relationship(back_populates="learning_records")

    def analyze_improvements(self) -> Dict[str, Any]:
        """Analyse les améliorations apportées par l'utilisateur."""
        if not self.ai_generated_cv or not self.user_final_cv:
            return {}
        
        # Analyse simplifiée pour le MVP
        ai_lines = self.ai_generated_cv.split('\n')
        user_lines = self.user_final_cv.split('\n')
        
        return {
            "length_change": len(self.user_final_cv) - len(self.ai_generated_cv),
            "lines_added": len(user_lines) - len(ai_lines),
            "substantial_changes": abs(len(self.user_final_cv) - len(self.ai_generated_cv)) > 100,
            "rating": self.user_rating,
            "timestamp": self.created_at.isoformat()
        }


class LearningDataset:
    """Classe utilitaire pour gérer les datasets d'apprentissage."""
    
    @staticmethod
    def prepare_training_data(profile: UserProfile) -> List[Dict[str, Any]]:
        """Prépare les données d'entraînement pour un profil."""
        training_examples = []
        
        for record in profile.learning_records:
            if record.user_rating >= 4:  # Seulement les bons exemples
                training_examples.append({
                    "input": {
                        "profile": profile.master_cv_content,
                        "job_offer": record.job_offer_text,
                        "template": record.template_used,
                        "language": record.language_used
                    },
                    "output": record.user_final_cv,
                    "metadata": {
                        "rating": record.user_rating,
                        "improvements": record.improvements_detected,
                        "created_at": record.created_at.isoformat()
                    }
                })
        
        return training_examples

    @staticmethod
    def export_for_fine_tuning(profile: UserProfile, output_path: str):
        """Exporte les données au format JSONL pour fine-tuning."""
        import json
        from pathlib import Path
        
        training_data = LearningDataset.prepare_training_data(profile)
        
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            for example in training_data:
                f.write(json.dumps(example, ensure_ascii=False) + '\n')
        
        return len(training_data)
