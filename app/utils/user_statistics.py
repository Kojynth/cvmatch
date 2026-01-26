"""
User Statistics Calculator
==========================

Calcule les statistiques avancées pour l'affichage dans l'interface utilisateur.
Remplace l'ancien système basique de notes moyennes par des métriques motivantes.
"""

from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from sqlmodel import Session, select, func
from loguru import logger

from ..models.user_profile import UserProfile
from ..models.job_application import JobApplication, ApplicationStatus

# TODO: LearningRecord model à implémenter plus tard
# from ..models.learning_record import LearningRecord


@dataclass
class UserStatsData:
    """Structure de données pour toutes les statistiques utilisateur."""
    
    # Métriques de productivité
    success_rate: float  # Taux de succès des candidatures (%)
    cv_generated_count: int  # Nombre total de CV générés automatiquement
    positive_response_count: int  # Nombre d'offres avec réponse positive
    applications_in_progress: int  # Candidatures en cours
    avg_time_per_cv: Optional[int]  # Temps moyen par CV (secondes)
    monthly_progress: int  # Progression mensuelle (différence)
    
    # Métriques qualitatives
    edit_rate: float  # Taux d'édition (%)
    satisfaction_score: float  # Score de satisfaction moyen
    profile_completion: float  # Pourcentage de profil complété
    
    # Métriques motivantes
    current_streak: int  # Streak de jours consécutifs
    user_level: str  # Niveau utilisateur (Novice/Expert/Master)
    level_badge: str  # Emoji du badge
    next_milestone: Optional[str]  # Prochaine étape suggérée
    
    # Données brutes (pour tooltips/détails)
    raw_data: Dict[str, Any]


class UserStatsCalculator:
    """Calculateur de statistiques utilisateur avancées."""
    
    # Configuration des niveaux
    LEVEL_THRESHOLDS = {
        0: ("Novice", "🌱"),
        5: ("Apprenti", "📚"), 
        15: ("Confirmé", "⚡"),
        30: ("Expert", "✨"),
        50: ("Master", "🏆"),
        100: ("Légende", "👑")
    }
    
    def __init__(self, session: Session, profile: UserProfile):
        self.session = session
        self.profile = profile
        
    def calculate_all_stats(self) -> UserStatsData:
        """Calcule toutes les statistiques pour un profil utilisateur."""
        try:
            logger.info(f"🧮 Calcul des statistiques pour le profil {self.profile.id}")
            
            # Récupérer toutes les candidatures
            applications = self._get_user_applications()
            learning_records = []  # TODO: Implémenter _get_learning_records() plus tard
            
            # Calculer chaque groupe de métriques
            productivity_stats = self._calculate_productivity_metrics(applications)
            quality_stats = self._calculate_quality_metrics(applications, learning_records)
            motivational_stats = self._calculate_motivational_metrics(applications)
            
            # Données brutes pour les tooltips
            raw_data = {
                "total_applications": len(applications),
                "applications_by_status": self._count_by_status(applications),
                "last_activity": self._get_last_activity_date(applications),
                "profile_sections": self._count_completed_sections()
            }
            
            stats = UserStatsData(
                # Productivité
                success_rate=productivity_stats["success_rate"],
                applications_in_progress=productivity_stats["in_progress"],
                avg_time_per_cv=productivity_stats["avg_time"],
                monthly_progress=productivity_stats["monthly_progress"],
                cv_generated_count=productivity_stats["cv_generated"],
                positive_response_count=productivity_stats["positive_responses"],
                
                # Qualité
                edit_rate=quality_stats["edit_rate"],
                satisfaction_score=quality_stats["satisfaction"],
                profile_completion=quality_stats["completion"],
                
                # Motivation
                current_streak=motivational_stats["streak"],
                user_level=motivational_stats["level"],
                level_badge=motivational_stats["badge"],
                next_milestone=motivational_stats["next_milestone"],
                
                raw_data=raw_data
            )
            
            logger.info(f"✅ Statistiques calculées: niveau={stats.user_level}, "
                       f"taux_succès={stats.success_rate:.1f}%, "
                       f"streak={stats.current_streak}j")
            
            return stats
            
        except Exception as e:
            logger.error(f"❌ Erreur lors du calcul des statistiques: {e}")
            return self._get_fallback_stats()
    
    def _get_user_applications(self) -> List[JobApplication]:
        """Récupère toutes les candidatures de l'utilisateur."""
        stmt = select(JobApplication).where(JobApplication.profile_id == self.profile.id)
        return list(self.session.exec(stmt))
    
    def _get_learning_records(self) -> List:
        """Récupère les enregistrements d'apprentissage."""
        # TODO: Implémenter quand LearningRecord sera disponible
        return []
    
    def _calculate_productivity_metrics(self, applications: List[JobApplication]) -> Dict[str, Any]:
        """Calcule les métriques de productivité."""
        if not applications:
            return {"success_rate": 0.0, "in_progress": 0, "avg_time": None, "monthly_progress": 0, "positive_responses": 0, "cv_generated": self.profile.total_cvs_generated}
        
        # Taux de succès
        completed_apps = [app for app in applications 
                         if app.status in [ApplicationStatus.ACCEPTED, ApplicationStatus.REJECTED, 
                                         ApplicationStatus.INTERVIEW]]
        success_count = len([app for app in completed_apps if app.has_positive_outcome()])
        success_rate = (success_count / len(completed_apps) * 100) if completed_apps else 0.0
        
        # Candidatures en cours
        in_progress = len([app for app in applications 
                          if app.status in [ApplicationStatus.SENT, ApplicationStatus.INTERVIEW]])
        
        # Temps moyen par CV (TODO: implémenter avec les learning records plus tard)
        avg_time = None  # Sera calculé quand LearningRecord sera disponible
        
        # Progression mensuelle
        now = datetime.now()
        this_month = len([app for app in applications 
                         if app.created_at.month == now.month and app.created_at.year == now.year])
        last_month = len([app for app in applications 
                         if app.created_at.month == (now.month - 1) and app.created_at.year == now.year])
        monthly_progress = this_month - last_month
        
        return {
            "success_rate": success_rate,
            "in_progress": in_progress,
            "avg_time": avg_time,
            "monthly_progress": monthly_progress,
            "positive_responses": success_count,
            "cv_generated": self.profile.total_cvs_generated
        }
    
    def _calculate_quality_metrics(self, applications: List[JobApplication], 
                                 learning_records: List) -> Dict[str, Any]:
        """Calcule les métriques qualitatives."""
        if not applications:
            return {"edit_rate": 0.0, "satisfaction": 0.0, "completion": 0.0}
        
        # Taux d'édition
        edited_count = len([app for app in applications if app.user_edited])
        edit_rate = (edited_count / len(applications) * 100) if applications else 0.0
        
        # Score de satisfaction
        rated_apps = [app for app in applications if app.user_rating is not None]
        satisfaction = (sum(app.user_rating for app in rated_apps) / len(rated_apps)) if rated_apps else 0.0
        
        # Completion du profil
        completion = self._calculate_profile_completion()
        
        return {
            "edit_rate": edit_rate,
            "satisfaction": satisfaction,
            "completion": completion
        }
    
    def _calculate_motivational_metrics(self, applications: List[JobApplication]) -> Dict[str, Any]:
        """Calcule les métriques motivantes."""
        # Streak de jours consécutifs
        streak = self._calculate_activity_streak(applications)
        
        # Niveau utilisateur
        total_cvs = self.profile.total_cvs_generated
        level, badge = self._get_user_level(total_cvs)
        
        # Prochaine étape
        next_milestone = self._get_next_milestone(total_cvs, applications)
        
        return {
            "streak": streak,
            "level": level,
            "badge": badge,
            "next_milestone": next_milestone
        }
    
    def _calculate_activity_streak(self, applications: List[JobApplication]) -> int:
        """Calcule le streak de jours consécutifs avec activité."""
        if not applications:
            return 0
        
        # Trier les candidatures par date décroissante
        sorted_apps = sorted(applications, key=lambda x: x.created_at, reverse=True)
        
        # Calculer le streak depuis aujourd'hui
        today = datetime.now().date()
        current_date = today
        streak = 0
        
        for app in sorted_apps:
            app_date = app.created_at.date()
            
            if app_date == current_date:
                streak += 1
                current_date -= timedelta(days=1)
            elif app_date < current_date:
                # Jour manquant, fin du streak
                break
        
        return streak
    
    def _get_user_level(self, total_cvs: int) -> tuple[str, str]:
        """Détermine le niveau et le badge de l'utilisateur."""
        for threshold in sorted(self.LEVEL_THRESHOLDS.keys(), reverse=True):
            if total_cvs >= threshold:
                return self.LEVEL_THRESHOLDS[threshold]
        
        return self.LEVEL_THRESHOLDS[0]  # Par défaut: Novice
    
    def _get_next_milestone(self, total_cvs: int, applications: List[JobApplication]) -> Optional[str]:
        """Suggère la prochaine étape pour l'utilisateur."""
        # Prochaine étape de niveau
        for threshold in sorted(self.LEVEL_THRESHOLDS.keys()):
            if total_cvs < threshold:
                remaining = threshold - total_cvs
                level_name = self.LEVEL_THRESHOLDS[threshold][0]
                return f"{remaining} CV pour atteindre {level_name}"
        
        # Si déjà au niveau max, suggestions alternatives
        if not applications:
            return "Créer votre première candidature"
        
        in_progress = len([app for app in applications 
                          if app.status in [ApplicationStatus.SENT, ApplicationStatus.INTERVIEW]])
        if in_progress == 0:
            return "Postuler à une nouvelle offre"
        
        return "Continuer le suivi de vos candidatures"
    
    def _calculate_profile_completion(self) -> float:
        """Calcule le pourcentage de completion du profil."""
        sections = [
            self.profile.extracted_personal_info,
            self.profile.extracted_experiences,
            self.profile.extracted_education,
            self.profile.extracted_skills,
            self.profile.extracted_languages
        ]
        
        completed = sum(1 for section in sections if section and len(section) > 0)
        return (completed / len(sections)) * 100
    
    def _count_completed_sections(self) -> Dict[str, bool]:
        """Compte les sections complétées du profil."""
        return {
            "personal_info": bool(self.profile.extracted_personal_info),
            "experiences": bool(self.profile.extracted_experiences and len(self.profile.extracted_experiences) > 0),
            "education": bool(self.profile.extracted_education and len(self.profile.extracted_education) > 0),
            "skills": bool(self.profile.extracted_skills and len(self.profile.extracted_skills) > 0),
            "languages": bool(self.profile.extracted_languages and len(self.profile.extracted_languages) > 0),
        }
    
    def _count_by_status(self, applications: List[JobApplication]) -> Dict[str, int]:
        """Compte les candidatures par statut."""
        counts = {}
        for status in ApplicationStatus:
            counts[status.value] = len([app for app in applications if app.status == status])
        return counts
    
    def _get_last_activity_date(self, applications: List[JobApplication]) -> Optional[datetime]:
        """Récupère la date de dernière activité."""
        if not applications:
            return None
        return max(app.created_at for app in applications)
    
    def _get_fallback_stats(self) -> UserStatsData:
        """Retourne des statistiques par défaut en cas d'erreur."""
        logger.warning("Utilisation des statistiques par défaut")
        
        return UserStatsData(
            success_rate=0.0,
            applications_in_progress=0,
            avg_time_per_cv=None,
            monthly_progress=0,
            cv_generated_count=getattr(self.profile, "total_cvs_generated", 0),
            positive_response_count=0,
            edit_rate=0.0,
            satisfaction_score=0.0,
            profile_completion=50.0,  # Valeur par défaut raisonnable
            current_streak=0,
            user_level="Novice",
            level_badge="🌱",
            next_milestone="Créer votre première candidature",
            raw_data={}
        )


def get_user_stats(session: Session, profile: UserProfile) -> UserStatsData:
    """Fonction utilitaire pour obtenir les statistiques d'un utilisateur."""
    calculator = UserStatsCalculator(session, profile)
    return calculator.calculate_all_stats()
