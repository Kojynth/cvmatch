#!/usr/bin/env python3
"""
Migration LinkedIn Columns
==========================

Ajoute les colonnes LinkedIn manquantes à la table userprofile.
Cette migration est nécessaire pour corriger l'erreur:
"sqlite3.OperationalError: no such column: userprofile.linkedin_pdf_path"

Usage:
    python scripts/migrate_linkedin_columns.py [--dry-run]
"""

import sqlite3
import sys
from pathlib import Path
from typing import Optional
import argparse
import shutil
from datetime import datetime

# Ajouter le répertoire parent au path pour les imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.logging.safe_logger import get_safe_logger
from app.config import DEFAULT_PII_CONFIG
from app.models.database import DATABASE_PATH

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


def check_database_exists() -> bool:
    """Vérifie si la base de données existe."""
    return DATABASE_PATH.exists()


def backup_database() -> Path:
    """Crée une sauvegarde de la base de données."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = DATABASE_PATH.parent / f"cvmatch_backup_{timestamp}.db"
    shutil.copy2(DATABASE_PATH, backup_path)
    logger.info(f"Sauvegarde créée : {backup_path}")
    return backup_path


def check_columns_exist(conn: sqlite3.Connection) -> dict:
    """Vérifie quelles colonnes LinkedIn existent déjà."""
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(userprofile)")
    columns = [row[1] for row in cursor.fetchall()]

    linkedin_columns = {
        'linkedin_pdf_path': 'linkedin_pdf_path' in columns,
        'linkedin_pdf_checksum': 'linkedin_pdf_checksum' in columns,
        'linkedin_pdf_uploaded_at': 'linkedin_pdf_uploaded_at' in columns
    }

    return linkedin_columns


def add_linkedin_columns(conn: sqlite3.Connection, dry_run: bool = False) -> bool:
    """Ajoute les colonnes LinkedIn manquantes."""
    cursor = conn.cursor()

    # Vérifier l'état actuel
    existing_columns = check_columns_exist(conn)
    missing_columns = [col for col, exists in existing_columns.items() if not exists]

    if not missing_columns:
        logger.info("✅ Toutes les colonnes LinkedIn existent déjà")
        return True

    logger.info(f"📋 Colonnes à ajouter : {missing_columns}")

    # Définir les commandes SQL pour chaque colonne
    sql_commands = {
        'linkedin_pdf_path': """
            ALTER TABLE userprofile
            ADD COLUMN linkedin_pdf_path VARCHAR(1024)
        """,
        'linkedin_pdf_checksum': """
            ALTER TABLE userprofile
            ADD COLUMN linkedin_pdf_checksum VARCHAR(128)
        """,
        'linkedin_pdf_uploaded_at': """
            ALTER TABLE userprofile
            ADD COLUMN linkedin_pdf_uploaded_at DATETIME
        """
    }

    if dry_run:
        logger.info("🧪 MODE DRY-RUN - Aucune modification appliquée")
        for col in missing_columns:
            logger.info(f"SERAIT EXÉCUTÉ : {sql_commands[col].strip()}")
        return True

    # Exécuter les migrations
    try:
        for col in missing_columns:
            logger.info(f"➕ Ajout de la colonne : {col}")
            cursor.execute(sql_commands[col])

        conn.commit()
        logger.info("✅ Migration réussie")
        return True

    except Exception as e:
        conn.rollback()
        logger.error(f"❌ Erreur lors de la migration : {e}")
        return False


def verify_migration(conn: sqlite3.Connection) -> bool:
    """Vérifie que la migration s'est bien déroulée."""
    try:
        cursor = conn.cursor()

        # Test d'une requête SELECT avec les nouvelles colonnes
        cursor.execute("""
            SELECT id, name, linkedin_pdf_path, linkedin_pdf_checksum, linkedin_pdf_uploaded_at
            FROM userprofile
            LIMIT 1
        """)

        result = cursor.fetchone()
        logger.info("✅ Vérification réussie - les colonnes sont accessibles")
        return True

    except Exception as e:
        logger.error(f"❌ Échec de la vérification : {e}")
        return False


def main():
    """Point d'entrée principal."""
    parser = argparse.ArgumentParser(description="Migration des colonnes LinkedIn")
    parser.add_argument("--dry-run", action="store_true",
                       help="Affiche les changements sans les appliquer")
    parser.add_argument("--no-backup", action="store_true",
                       help="Ne crée pas de sauvegarde (non recommandé)")

    args = parser.parse_args()

    # Vérifications préliminaires
    if not check_database_exists():
        logger.error(f"❌ Base de données non trouvée : {DATABASE_PATH}")
        sys.exit(1)

    logger.info(f"🔍 Migration des colonnes LinkedIn")
    logger.info(f"📍 Base de données : {DATABASE_PATH}")

    # Sauvegarde (sauf si désactivée ou dry-run)
    if not args.no_backup and not args.dry_run:
        backup_path = backup_database()
        logger.info(f"💾 Sauvegarde : {backup_path}")

    # Connexion à la base de données
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        logger.info("🔌 Connexion à la base de données établie")

        # Vérifier l'état initial
        existing_columns = check_columns_exist(conn)
        logger.info(f"📊 État actuel des colonnes : {existing_columns}")

        # Exécuter la migration
        success = add_linkedin_columns(conn, dry_run=args.dry_run)

        if success and not args.dry_run:
            # Vérifier la migration
            if verify_migration(conn):
                logger.info("🎉 Migration complète avec succès")
            else:
                logger.error("⚠️ Migration appliquée mais vérification échouée")
                sys.exit(1)
        elif success and args.dry_run:
            logger.info("✅ Dry-run terminé - prêt pour la migration")
        else:
            logger.error("❌ Échec de la migration")
            sys.exit(1)

    except Exception as e:
        logger.error(f"💥 Erreur critique : {e}")
        sys.exit(1)
    finally:
        if 'conn' in locals():
            conn.close()
            logger.info("🔌 Connexion fermée")


if __name__ == "__main__":
    main()