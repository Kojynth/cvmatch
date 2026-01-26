"""
Database Manager
===============

Gestionnaire de base de données avec utilitaires.
"""

from pathlib import Path
from typing import List, Optional, Dict, Any
from sqlmodel import Session, select
# PATCH-PII: Remplacement par logger sécurisé
from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG
logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)

from ..models.database import get_session, engine, backup_database
from ..models.user_profile import UserProfile, LearningRecord
from ..models.job_application import JobApplication, ApplicationStatus


class DatabaseManager:
    """Gestionnaire principal de la base de données."""
    
    def __init__(self):
        self.session_factory = get_session
    
    def get_or_create_profile(self, email: str) -> Optional[UserProfile]:
        """Récupère ou crée un profil utilisateur."""
        with self.session_factory() as session:
            statement = select(UserProfile).where(UserProfile.email == email)
            profile = session.exec(statement).first()
            return profile
    
    def get_default_profile(self) -> Optional[UserProfile]:
        """Récupère le profil par défaut (premier profil créé)."""
        with self.session_factory() as session:
            statement = select(UserProfile).order_by(UserProfile.created_at)
            profile = session.exec(statement).first()
            return profile
    
    def create_profile(self, profile_data: Dict[str, Any]) -> UserProfile:
        """Crée un nouveau profil."""
        profile = UserProfile(**profile_data)
        
        with self.session_factory() as session:
            session.add(profile)
            session.commit()
            session.refresh(profile)
            
        # PATCH-PII: Éviter exposition nom
        logger.info("Profil créé pour profile_id=%s created_at=%s", profile.id, profile.created_at.strftime('%Y-%m-%d') if hasattr(profile, 'created_at') and profile.created_at else 'unknown')
        return profile
    
    def update_profile(self, profile: UserProfile) -> UserProfile:
        """Met à jour un profil."""
        with self.session_factory() as session:
            session.add(profile)
            session.commit()
            session.refresh(profile)
            
        # PATCH-PII: Éviter exposition nom
        logger.info("Profil mis à jour pour profile_id=%s updated_at=%s", profile.id, 'now')
        return profile
    
    def get_profile_applications(self, profile_id: int, limit: int = 50) -> List[JobApplication]:
        """Récupère les candidatures d'un profil."""
        with self.session_factory() as session:
            statement = select(JobApplication).where(
                JobApplication.profile_id == profile_id
            ).order_by(JobApplication.created_at.desc()).limit(limit)
            
            applications = session.exec(statement).all()
            return list(applications)
    
    def get_application_by_id(self, application_id: int) -> Optional[JobApplication]:
        """Récupère une candidature par son ID."""
        with self.session_factory() as session:
            statement = select(JobApplication).where(JobApplication.id == application_id)
            return session.exec(statement).first()
    
    def update_application_status(self, application_id: int, status: ApplicationStatus, notes: Optional[str] = None):
        """Met à jour le statut d'une candidature."""
        with self.session_factory() as session:
            application = session.get(JobApplication, application_id)
            if application:
                application.update_status(status, notes)
                session.add(application)
                session.commit()
                logger.info(f"Statut candidature {application_id} mis à jour : {status.value}")
    
    def rate_application(self, application_id: int, rating: int, comments: Optional[str] = None):
        """Note une candidature."""
        with self.session_factory() as session:
            application = session.get(JobApplication, application_id)
            if application:
                application.set_rating(rating, comments)
                session.add(application)
                session.commit()
                
                # Mettre à jour les stats du profil
                profile = session.get(UserProfile, application.profile_id)
                if profile:
                    profile.update_learning_stats(rating)
                    session.add(profile)
                    session.commit()
                
                logger.info(f"Candidature {application_id} notée : {rating}/5")
    
    def create_learning_record(self, application: JobApplication) -> LearningRecord:
        """Crée un enregistrement d'apprentissage."""
        if not application.user_rating or not application.final_cv_markdown:
            raise ValueError("Candidature incomplète pour l'apprentissage")
        
        record = LearningRecord(
            profile_id=application.profile_id,
            job_offer_text=application.offer_text,
            ai_generated_cv=application.generated_cv_markdown,
            user_final_cv=application.final_cv_markdown,
            user_rating=application.user_rating,
            template_used=application.template_used,
            language_used="fr",  # TODO: détecter automatiquement
            model_version_used=application.model_version_used,
            user_comments=application.user_comments
        )
        
        # Analyser les améliorations
        record.improvements_detected = record.analyze_improvements()
        
        with self.session_factory() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
        
        logger.info(f"Enregistrement d'apprentissage créé pour candidature {application.id}")
        return record
    
    def get_learning_records(self, profile_id: int, limit: int = 100) -> List[LearningRecord]:
        """Récupère les enregistrements d'apprentissage."""
        with self.session_factory() as session:
            statement = select(LearningRecord).where(
                LearningRecord.profile_id == profile_id
            ).order_by(LearningRecord.created_at.desc()).limit(limit)
            
            records = session.exec(statement).all()
            return list(records)
    
    def get_profile_stats(self, profile_id: int) -> Dict[str, Any]:
        """Calcule les statistiques d'un profil."""
        with self.session_factory() as session:
            # Applications
            apps_statement = select(JobApplication).where(JobApplication.profile_id == profile_id)
            applications = session.exec(apps_statement).all()
            
            # Learning records
            learning_statement = select(LearningRecord).where(LearningRecord.profile_id == profile_id)
            learning_records = session.exec(learning_statement).all()
            
            # Calculs
            total_applications = len(applications)
            
            status_counts = {}
            for app in applications:
                status = app.status.value
                status_counts[status] = status_counts.get(status, 0) + 1
            
            # Notes
            rated_apps = [app for app in applications if app.user_rating]
            avg_rating = sum(app.user_rating for app in rated_apps) / len(rated_apps) if rated_apps else 0.0
            
            # Templates
            template_usage = {}
            for app in applications:
                template = app.template_used
                template_usage[template] = template_usage.get(template, 0) + 1
            
            # Apprentissage
            learning_stats = {
                "total_records": len(learning_records),
                "avg_rating": sum(r.user_rating for r in learning_records) / len(learning_records) if learning_records else 0.0,
                "improvement_trends": self._analyze_improvement_trends(learning_records)
            }
            
            return {
                "total_applications": total_applications,
                "status_breakdown": status_counts,
                "average_rating": round(avg_rating, 2),
                "template_usage": template_usage,
                "learning_stats": learning_stats,
                "success_rate": status_counts.get("accepted", 0) / total_applications if total_applications > 0 else 0.0
            }
    
    def _analyze_improvement_trends(self, learning_records: List[LearningRecord]) -> Dict[str, Any]:
        """Analyse les tendances d'amélioration."""
        if not learning_records:
            return {}
        
        # Trier par date
        sorted_records = sorted(learning_records, key=lambda x: x.created_at)
        
        # Analyser les notes dans le temps
        ratings_over_time = [r.user_rating for r in sorted_records]
        
        trends = {
            "rating_trend": "stable",
            "recent_improvement": False,
            "consistency": 0.0
        }
        
        if len(ratings_over_time) >= 3:
            # Tendance simple (comparaison première moitié vs seconde moitié)
            mid_point = len(ratings_over_time) // 2
            first_half_avg = sum(ratings_over_time[:mid_point]) / mid_point
            second_half_avg = sum(ratings_over_time[mid_point:]) / (len(ratings_over_time) - mid_point)
            
            if second_half_avg > first_half_avg + 0.5:
                trends["rating_trend"] = "improving"
            elif second_half_avg < first_half_avg - 0.5:
                trends["rating_trend"] = "declining"
            
            # Amélioration récente (3 derniers)
            if len(ratings_over_time) >= 3:
                recent_avg = sum(ratings_over_time[-3:]) / 3
                trends["recent_improvement"] = recent_avg >= 4.0
            
            # Consistance (écart-type inverse)
            import statistics
            std_dev = statistics.stdev(ratings_over_time) if len(ratings_over_time) > 1 else 0
            trends["consistency"] = max(0, 1 - std_dev / 2)  # Normalisé 0-1
        
        return trends
    
    def backup_data(self, backup_path: Optional[Path] = None) -> Path:
        """Sauvegarde la base de données."""
        return backup_database(backup_path)
    
    def export_profile_data(self, profile_id: int, export_path: Path) -> Dict[str, str]:
        """Exporte toutes les données d'un profil."""
        import json
        
        with self.session_factory() as session:
            # Profil
            profile = session.get(UserProfile, profile_id)
            if not profile:
                raise ValueError(f"Profil {profile_id} non trouvé")
            
            # Applications
            apps_statement = select(JobApplication).where(JobApplication.profile_id == profile_id)
            applications = session.exec(apps_statement).all()
            
            # Learning records
            learning_statement = select(LearningRecord).where(LearningRecord.profile_id == profile_id)
            learning_records = session.exec(learning_statement).all()
        
        # Préparer les données pour export
        export_data = {
            "profile": {
                "name": profile.name,
                "email": profile.email,
                "phone": profile.phone,
                "linkedin_url": profile.linkedin_url,
                "preferred_template": profile.preferred_template,
                "preferred_language": profile.preferred_language,
                "total_cvs_generated": profile.total_cvs_generated,
                "total_cvs_validated": profile.total_cvs_validated,
                "average_rating": profile.average_rating,
                "created_at": profile.created_at.isoformat(),
                "updated_at": profile.updated_at.isoformat()
            },
            "applications": [app.get_summary() for app in applications],
            "learning_records": [
                {
                    "job_title": apps_dict.get(lr.profile_id, "Unknown"),
                    "user_rating": lr.user_rating,
                    "template_used": lr.template_used,
                    "improvements": lr.improvements_detected,
                    "created_at": lr.created_at.isoformat()
                }
                for lr in learning_records
            ]
        }
        
        # Sauvegarder en JSON
        json_path = export_path / f"cvmatch_export_{profile.name.lower().replace(' ', '_')}.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Données exportées vers {json_path}")
        
        return {
            "json_export": str(json_path),
            "total_applications": len(applications),
            "total_learning_records": len(learning_records)
        }
