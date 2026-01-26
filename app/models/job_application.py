"""
Job Application Models
=====================

Modèles pour gérer les candidatures et leur suivi.
"""

from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum
from sqlmodel import SQLModel, Field, Relationship, Column, Text, JSON


class ApplicationStatus(str, Enum):
    """Statuts possibles d'une candidature."""
    DRAFT = "draft"
    SENT = "sent"
    INTERVIEW = "interview"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class JobApplication(SQLModel, table=True):
    """Candidature à un poste avec CV généré."""
    
    # ID et références
    id: Optional[int] = Field(default=None, primary_key=True)
    profile_id: int = Field(foreign_key="userprofile.id")
    
    # Informations sur l'offre
    job_title: str = Field(max_length=200)
    company: str = Field(max_length=100)
    offer_text: str = Field(sa_column=Column(Text))
    offer_url: Optional[str] = Field(default=None, max_length=1000)
    offer_file_path: Optional[str] = Field(default=None, max_length=1000)
    
    # Analyse automatique de l'offre (JSON)
    offer_analysis: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSON)
    )
    
    # Résultats de génération
    template_used: str = Field(max_length=50)
    model_version_used: str = Field(max_length=20)
    generated_cv_markdown: str = Field(sa_column=Column(Text))
    generated_cv_html: Optional[str] = Field(default=None, sa_column=Column(Text))
    generated_cover_letter: Optional[str] = Field(default=None, sa_column=Column(Text))
    profile_json: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    critic_json: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    cv_json_draft: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    cv_json_final: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    
    # Version finale (après édition utilisateur)
    final_cv_markdown: Optional[str] = Field(default=None, sa_column=Column(Text))
    final_cv_html: Optional[str] = Field(default=None, sa_column=Column(Text))
    final_cover_letter: Optional[str] = Field(default=None, sa_column=Column(Text))
    
    # Statut et feedback
    status: ApplicationStatus = Field(default=ApplicationStatus.DRAFT)
    user_rating: Optional[int] = Field(default=None, ge=1, le=5)
    user_edited: bool = Field(default=False)
    user_comments: Optional[str] = Field(default=None, sa_column=Column(Text))
    
    # Exports et envois
    exported_pdf_path: Optional[str] = Field(default=None, max_length=1000)
    exported_at: Optional[datetime] = Field(default=None)
    sent_at: Optional[datetime] = Field(default=None)
    
    # Suivi candidature
    interview_date: Optional[datetime] = Field(default=None)
    response_received_at: Optional[datetime] = Field(default=None)
    notes: Optional[str] = Field(default=None, sa_column=Column(Text))
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    
    # Relations
    profile: Optional["UserProfile"] = Relationship(back_populates="job_applications")

    def update_status(self, new_status: ApplicationStatus, notes: Optional[str] = None):
        """Met à jour le statut de la candidature."""
        self.status = new_status
        self.updated_at = datetime.now()
        
        if new_status == ApplicationStatus.SENT and not self.sent_at:
            self.sent_at = datetime.now()
        
        if notes:
            if self.notes:
                self.notes += f"\n\n[{datetime.now().strftime('%Y-%m-%d %H:%M')}] {notes}"
            else:
                self.notes = f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] {notes}"

    def mark_as_edited(self, final_cv: str, final_cover_letter: Optional[str] = None):
        """Marque la candidature comme éditée par l'utilisateur."""
        self.user_edited = True
        self.final_cv_markdown = final_cv
        self.final_cover_letter = final_cover_letter
        self.updated_at = datetime.now()

    def set_rating(self, rating: int, comments: Optional[str] = None):
        """Définit la note utilisateur pour cette génération."""
        if 1 <= rating <= 5:
            self.user_rating = rating
            self.user_comments = comments
            self.updated_at = datetime.now()

    def get_display_cv(self) -> str:
        """Retourne le CV à afficher (final si édité, sinon généré)."""
        return self.final_cv_markdown or self.generated_cv_markdown

    def has_positive_outcome(self) -> bool:
        """Return True when the candidate received a positive response."""
        return self.status in {ApplicationStatus.ACCEPTED, ApplicationStatus.INTERVIEW}

    def get_display_cover_letter(self) -> Optional[str]:
        """Retourne la lettre à afficher (finale si éditée, sinon générée)."""
        return self.final_cover_letter or self.generated_cover_letter

    def has_changes(self) -> bool:
        """Vérifie si l'utilisateur a modifié le CV généré."""
        if not self.final_cv_markdown:
            return False
        return self.final_cv_markdown != self.generated_cv_markdown

    def get_match_score(self) -> float:
        """Calcule un score de correspondance basé sur l'analyse."""
        if not self.offer_analysis:
            return 0.0
        
        # Score simplifié basé sur les éléments de l'analyse
        analysis = self.offer_analysis
        score = 0.0
        
        # Correspondance des compétences (exemple)
        if "skills_match" in analysis:
            score += analysis["skills_match"] * 0.4
        
        # Correspondance d'expérience
        if "experience_match" in analysis:
            score += analysis["experience_match"] * 0.3
        
        # Correspondance de secteur
        if "sector_match" in analysis:
            score += analysis["sector_match"] * 0.2
        
        # Langue
        if "language_match" in analysis:
            score += analysis["language_match"] * 0.1
        
        return min(score, 1.0)  # Max 1.0

    def get_summary(self) -> Dict[str, Any]:
        """Retourne un résumé de la candidature."""
        return {
            "id": self.id,
            "job_title": self.job_title,
            "company": self.company,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "user_rating": self.user_rating,
            "user_edited": self.user_edited,
            "match_score": self.get_match_score(),
            "template_used": self.template_used,
            "model_version": self.model_version_used
        }


class ApplicationStats:
    """Classe utilitaire pour calculer des statistiques sur les candidatures."""
    
    @staticmethod
    def get_profile_stats(profile_id: int) -> Dict[str, Any]:
        """Calcule les statistiques pour un profil."""
        from .database import get_session
        
        with get_session() as session:
            applications = session.query(JobApplication).filter(
                JobApplication.profile_id == profile_id
            ).all()
        
        if not applications:
            return {
                "total": 0,
                "by_status": {},
                "average_rating": 0.0,
                "templates_used": {},
                "recent_activity": []
            }
        
        # Statistiques par statut
        status_counts = {}
        for app in applications:
            status = app.status.value
            status_counts[status] = status_counts.get(status, 0) + 1
        
        # Note moyenne
        rated_apps = [app for app in applications if app.user_rating]
        avg_rating = sum(app.user_rating for app in rated_apps) / len(rated_apps) if rated_apps else 0.0
        
        # Templates utilisés
        template_counts = {}
        for app in applications:
            template = app.template_used
            template_counts[template] = template_counts.get(template, 0) + 1
        
        # Activité récente (10 dernières)
        recent = sorted(applications, key=lambda x: x.updated_at, reverse=True)[:10]
        recent_activity = [app.get_summary() for app in recent]
        
        return {
            "total": len(applications),
            "by_status": status_counts,
            "average_rating": round(avg_rating, 2),
            "templates_used": template_counts,
            "recent_activity": recent_activity,
            "success_rate": status_counts.get("accepted", 0) / len(applications) if applications else 0.0
        }
