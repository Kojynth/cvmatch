"""
Database Configuration and Management
=====================================

Configuration SQLite avec SQLModel pour CVMatch.
"""

from pathlib import Path
from typing import Optional
from sqlmodel import SQLModel, create_engine, Session
# PATCH-PII: Remplacement par logger sécurisé
from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG
from ..utils.redactor import safe_database_path_for_log
logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)
import os

# Configuration des chemins
APP_DATA_DIR = Path.home() / ".cvmatch"
DATABASE_PATH = APP_DATA_DIR / "cvmatch.db"

# Créer le dossier de données s'il n'existe pas
APP_DATA_DIR.mkdir(exist_ok=True)

# Configuration de l'engine SQLite
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

engine = create_engine(
    DATABASE_URL,
    echo=False,  # Mettre à True pour debug SQL
    connect_args={"check_same_thread": False}
)


def create_db_and_tables():
    """Crée la base de données et toutes les tables."""
    try:
        SQLModel.metadata.create_all(engine)
        _ensure_job_application_columns()
        _ensure_user_profile_columns()
        # PATCH-PII: Chemin anonymisé
        logger.info("Base de données créée : %s", safe_database_path_for_log(str(DATABASE_PATH)))
    except Exception as e:
        logger.error(f"Erreur création base de données : {e}")
        raise




def _ensure_job_application_columns() -> None:
    """Lightweight migration for new job_application JSON columns."""
    try:
        from sqlmodel import text

        with engine.connect() as connection:
            rows = connection.execute(text("PRAGMA table_info(jobapplication)")).fetchall()
            existing = {row[1] for row in rows}

            for column in (
                "profile_json",
                "critic_json",
                "cv_json_draft",
                "cv_json_final",
            ):
                if column not in existing:
                    connection.execute(
                        text(f"ALTER TABLE jobapplication ADD COLUMN {column} TEXT")
                    )
    except Exception as exc:
        logger.warning(f"Schema migration skipped: {exc}")


def _ensure_user_profile_columns() -> None:
    """Lightweight migration for new userprofile columns."""
    try:
        from sqlmodel import text

        with engine.connect() as connection:
            rows = connection.execute(text("PRAGMA table_info(userprofile)")).fetchall()
            existing = {row[1] for row in rows}
            if "profile_photo_path" not in existing:
                connection.execute(
                    text("ALTER TABLE userprofile ADD COLUMN profile_photo_path TEXT")
                )
            if "location" not in existing:
                connection.execute(
                    text("ALTER TABLE userprofile ADD COLUMN location TEXT")
                )
    except Exception as exc:
        logger.warning(f"User profile schema migration skipped: {exc}")


def get_session() -> Session:
    """Retourne une session de base de données."""
    return Session(engine)


def reset_database():
    """
    Remet à zéro la base de données (ATTENTION : supprime toutes les données).

    Ferme tous les moteurs et sessions actives pour libérer les verrous de fichier.
    NOTE: La suppression réelle du fichier DB peut être différée jusqu'à la fermeture complète de l'app.
    """
    global engine
    try:
        # 1. Fermer ALL active connections - critical step
        logger.info("🔒 Fermeture de toutes les connexions de base de données...")

        # Dispose du moteur SQLAlchemy
        if engine:
            engine.dispose()
            logger.info("✅ Engine disposed et connexions SQLAlchemy fermées")

        # Force garbage collection to release connection handles
        import gc
        gc.collect()
        logger.info("✅ Garbage collection forcé")

        # 2. Wait for OS to release file locks
        import time
        time.sleep(1.0)  # Increased from 0.5s to 1.0s for Windows lock release
        logger.info("✅ Délai de libération des verrous: 1 seconde écoulée")

        # 3. Supprimer le fichier de base de données principale
        if DATABASE_PATH.exists():
            try:
                DATABASE_PATH.unlink()
                logger.info(f"🗑️ Base de données supprimée: {DATABASE_PATH}")
            except PermissionError as e:
                # Si on ne peut pas supprimer (verrou Windows), renommer pour préserver
                import os
                backup_name = f"{DATABASE_PATH}.backup_{os.urandom(4).hex()}"
                try:
                    DATABASE_PATH.rename(backup_name)
                    logger.warning(f"⚠️ Base de données verrouillée, renommée en: {backup_name}")
                except Exception as rename_err:
                    logger.warning(f"⚠️ Impossible de renommer DB ({rename_err}), sera supprimée à la fermeture de l'app")

        # 4. Recréer l'engine et les tables
        logger.info("🔄 Recréation du moteur de base de données...")
        engine = create_engine(
            DATABASE_URL,
            echo=False,
            connect_args={"check_same_thread": False}
        )
        create_db_and_tables()
        logger.info("✅ Base de données réinitialisée avec succès")

    except Exception as e:
        logger.error(f"❌ Erreur réinitialisation base de données: {e}")
        raise


def backup_database(backup_path: Optional[Path] = None) -> Path:
    """Sauvegarde la base de données."""
    if backup_path is None:
        backup_path = APP_DATA_DIR / f"cvmatch_backup_{os.urandom(4).hex()}.db"
    
    try:
        import shutil
        shutil.copy2(DATABASE_PATH, backup_path)
        logger.info(f"Sauvegarde créée : {backup_path}")
        return backup_path
    except Exception as e:
        logger.error(f"Erreur sauvegarde : {e}")
        raise


def get_database_info() -> dict:
    """Retourne des informations sur la base de données."""
    try:
        size_mb = DATABASE_PATH.stat().st_size / (1024 * 1024) if DATABASE_PATH.exists() else 0
        
        with get_session() as session:
            # Compter les enregistrements
            from .user_profile import UserProfile
            from .job_application import JobApplication
            
            profiles_count = session.query(UserProfile).count()
            applications_count = session.query(JobApplication).count()
        
        return {
            "path": str(DATABASE_PATH),
            "size_mb": round(size_mb, 2),
            "profiles_count": profiles_count,
            "applications_count": applications_count,
            "exists": DATABASE_PATH.exists()
        }
    except Exception as e:
        logger.error(f"Erreur info base de données : {e}")
        return {
            "path": str(DATABASE_PATH),
            "size_mb": 0,
            "profiles_count": 0,
            "applications_count": 0,
            "exists": False
        }
