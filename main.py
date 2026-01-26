#!/usr/bin/env python3
"""
CVMatch - Point d'entrée pour la nouvelle interface
===================================================

Interface principale refactorisée avec sidebar navigation.
"""

# IMPORTANT: Bootstrap WeasyPrint AVANT tout autre import
try:
    from scripts import weasyprint_bootstrap
except ImportError:
    # Fallback si scripts n'est pas un package
    import sys
    from pathlib import Path
    scripts_path = Path(__file__).parent / "scripts"
    sys.path.insert(0, str(scripts_path))
    import weasyprint_bootstrap

import sys
import os
import warnings
from pathlib import Path
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
try:
    from app.logging.safe_logger import get_safe_logger
    from app.logging.emoji_sanitizer import create_windows_safe_console_handler, create_utf8_file_handler
    from app.config import DEFAULT_PII_CONFIG
    logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

# AJOUT: Logger résistant aux crashes (AVANT tout autre import)
sys.path.insert(0, str(Path(__file__).parent))
from app.utils.crash_resistant_logger import get_crash_logger, log_startup_event, log_critical_error, log_debug_info

# Initialiser le crash logger immédiatement
crash_logger = get_crash_logger()
log_startup_event("MAIN_IMPORT", "Début imports main.py")

# Supprimer TOUS les avertissements pour une sortie plus propre
warnings.filterwarnings("ignore")

# Capturer et supprimer les messages d'erreur WeasyPrint au niveau système
class WeasyPrintSuppressor:
    """Supprime les messages d'erreur WeasyPrint en capturant stderr temporairement."""
    
    def __init__(self):
        self.original_stderr = None
        
    def __enter__(self):
        import io
        self.original_stderr = sys.stderr
        sys.stderr = io.StringIO()  # Capturer stderr
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        # Récupérer les messages capturés
        captured = sys.stderr.getvalue()
        sys.stderr = self.original_stderr
        
        # Filtrer et n'afficher que les vrais messages d'erreur (pas WeasyPrint)
        # MAIS préserver les logs loguru (reconnaissables par leur format)
        if captured:
            lines = captured.strip().split('\n')
            for line in lines:
                # Garder les logs loguru et les vraies erreurs, filtrer WeasyPrint
                if (any(keyword in line.lower() for keyword in ['weasyprint', 'external libraries', 'courtbouillon', 'gtk']) 
                    and not any(marker in line for marker in ['INFO', 'WARNING', 'ERROR', 'DEBUG'])):
                    continue  # Filtrer cette ligne WeasyPrint
                else:
                    print(line, file=sys.stderr)  # Afficher les logs et vraies erreurs

# Gérer les erreurs d'import WeasyPrint silencieusement avec suppresseur
WEASYPRINT_AVAILABLE = False
try:
    with WeasyPrintSuppressor():
        import weasyprint
        WEASYPRINT_AVAILABLE = True
except (ImportError, OSError) as e:
    # N'afficher l'avertissement qu'une seule fois au démarrage
    print("[INFO] WeasyPrint non disponible - export PDF limite")
    if "OSError" in str(type(e)):
        print("       Erreur: Bibliotheques systeme manquantes pour WeasyPrint")
        print("       Voir: https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#windows")
    else:
        print("       Pour installer: pip install weasyprint")

# ENHANCED: Windows UTF-8 stream wrapping for emoji compatibility
def _wrap_windows_streams_utf8_if_possible():
    """
    Attempt to wrap Windows stdout/stderr with UTF-8 encoding to support emojis.
    This is a best-effort approach that falls back gracefully if it fails.
    """
    if os.name != "nt":
        return  # Only apply on Windows
    
    try:
        import io
        
        # Wrap stdout if it has a detach method and isn't already UTF-8
        if (hasattr(sys.stdout, "detach") and 
            getattr(sys.stdout, "encoding", "").lower() not in ("utf-8", "utf8")):
            try:
                sys.stdout = io.TextIOWrapper(
                    sys.stdout.detach(), 
                    encoding="utf-8", 
                    errors="replace"
                )
            except Exception:
                pass  # Keep original stdout if wrapping fails
        
        # Wrap stderr similarly
        if (hasattr(sys.stderr, "detach") and 
            getattr(sys.stderr, "encoding", "").lower() not in ("utf-8", "utf8")):
            try:
                sys.stderr = io.TextIOWrapper(
                    sys.stderr.detach(), 
                    encoding="utf-8", 
                    errors="replace"
                )
            except Exception:
                pass  # Keep original stderr if wrapping fails
                
    except Exception:
        # If anything goes wrong, continue with original streams
        pass


# Configuration du logging (console + fichier) - PERSISTANT + ENHANCED
# Note: SafeLoggerAdapter n'a pas de méthode remove() comme loguru
# Le logging est déjà configuré via get_safe_logger()

# ENHANCED: Apply UTF-8 stream wrapping before logging setup
_wrap_windows_streams_utf8_if_possible()

# Créer les dossiers logs s'ils n'existent pas
logs_dir = Path("logs")
logs_dir.mkdir(exist_ok=True)

# FORCER la création de logs persistants avec PLUSIEURS destinations
import datetime
timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

# SafeLoggerAdapter utilise le système logging standard, pas loguru
# Le logging est déjà configuré avec des handlers appropriés
try:
    # ENHANCED: Configuration des logs avec le système standard logging + Windows emoji safety
    import logging
    from logging.handlers import RotatingFileHandler
    
    # ENHANCED: UTF-8 rotatingfilehandler preserving emojis avec ID processus unique
    import os
    process_id = os.getpid()
    main_handler = RotatingFileHandler(
        f"logs/cvmatch_{process_id}.log",
        maxBytes=10*1024*1024,  # 10MB
        backupCount=7,
        encoding="utf-8"  # Ensure UTF-8 encoding for emojis
    )
    main_handler.setLevel(logging.DEBUG)
    main_handler.setFormatter(logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s'
    ))
    
    # ENHANCED: UTF-8 error handler avec ID processus unique
    error_log = f"logs/errors_{datetime.datetime.now().strftime('%Y%m%d')}_{process_id}.log"
    error_handler = RotatingFileHandler(error_log, maxBytes=5*1024*1024, backupCount=3, encoding="utf-8")
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s'
    ))
    
    # ENHANCED: Windows-safe console handler with emoji sanitization
    console_handler = create_windows_safe_console_handler(
        level=logging.INFO,
        fmt='%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s'
    )
    
    # Ajouter les handlers au logger racine (sera utilisé par tous les safe_loggers)
    root_logger = logging.getLogger()
    root_logger.addHandler(main_handler)
    root_logger.addHandler(error_handler)
    root_logger.addHandler(console_handler)
    root_logger.setLevel(logging.INFO)  # Set to INFO instead of DEBUG to reduce spam

    print(f"[LOGS] Log principal: logs/cvmatch_{process_id}.log")
    print(f"[LOGS] Erreurs du jour: {error_log}")
    print(f"[LOGS] Windows emoji-safe logging configured")
    
except Exception as e:
    # Fallback: logging vers la console seulement
    print(f"[WARNING] Logging partiel à cause de: {e}")
    # Pas de logger.add() car SafeLoggerAdapter n'a pas cette méthode

# Ajout du chemin racine au sys.path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

try:
    from app.models.database import create_db_and_tables, get_session
    from app.models.user_profile import UserProfile
    from app.lifecycle.app_initializer import bootstrap_main_window
    from app.views.main_window import MainWindowWithSidebar
    from app.widgets.dialog_manager import show_error, show_success
except ImportError as e:
    print(f"[ERREUR] Erreur d'import critique: {e}")
    sys.exit(1)


class CVMatchApp(QApplication):
    """Application principale CVMatch avec la nouvelle interface."""
    
    def __init__(self, args):
        super().__init__(args)
        self.setApplicationName("CVMatch")
        self.setApplicationVersion("2.0")
        self.setOrganizationName("CVMatch")
        
        # Style sombre par défaut
        self.setStyleSheet("""
            QApplication {
                background-color: #2d2d2d;
                color: #ffffff;
            }
        """)
        
        logger.info("Demarrage CVMatch")
    
    def initialize_database(self):
        """Initialise la base de données."""
        try:
            create_db_and_tables()
            logger.info("Base de donnees initialisee")
            return True
        except Exception as e:
            logger.error(f"Erreur initialisation BDD: {e}")
            show_error("Erreur Base de Données", 
                      f"Impossible d'initialiser la base de données:\n{str(e)}")
            return False
    
    def get_or_setup_profile(self) -> UserProfile:
        """Récupère un profil existant ou lance le setup de premier lancement."""
        try:
            with get_session() as session:
                # Chercher un profil existant (utilisation de la syntaxe SQLModel moderne)
                from sqlmodel import select
                statement = select(UserProfile)
                profile = session.exec(statement).first()
                
                if profile:
                    # PATCH-PII: Éviter exposition nom utilisateur
                    completion = getattr(profile, 'completion_percentage', 0)
                    completion_pct = completion if isinstance(completion, (int, float)) else 0
                    logger.info("📁 Profil existant trouvé: profile_id=%s completion=%d%%", profile.id, completion_pct)
                    return profile
                
                # Aucun profil trouvé = premier lancement
                logger.info("🎯 Premier lancement détecté - ouverture du setup initial")
                
                # DÉBOGAGE: Mode bypass ProfileSetupDialog si variable d'environnement définie
                if os.getenv('CVMATCH_BYPASS_SETUP') == '1':
                    logger.warning("⚠️ MODE DEBUG: Bypass ProfileSetupDialog activé")
                    return self._create_debug_profile()
                
                return self._run_first_time_setup()
                
        except Exception as e:
            logger.error(f"Erreur gestion profil: {e}")
            # En cas d'erreur, lancer aussi le setup
            logger.info("🔧 Erreur profil - lancement du setup de récupération")
            return self._run_first_time_setup()
    
    def _create_debug_profile(self) -> UserProfile:
        """Crée un profil de debug temporaire pour bypass le setup."""
        try:
            logger.info("🛠️ Création profil de debug temporaire...")
            
            # Créer un profil minimal pour debug
            debug_profile = UserProfile(
                first_name="Debug",
                last_name="User",
                email="debug@cvmatch.local",
                phone="",
                completion_percentage=50
            )
            
            # Sauvegarder en base de données
            with get_session() as session:
                session.add(debug_profile)
                session.commit()
                session.refresh(debug_profile)
                
                logger.info(f"✅ Profil debug créé avec ID: {debug_profile.id}")
                return debug_profile
                
        except Exception as e:
            logger.error(f"Erreur création profil debug: {e}")
            # Fallback - continuer quand même avec setup normal
            return self._run_first_time_setup()
    
    def _run_first_time_setup(self) -> UserProfile:
        """Lance le setup de premier lancement et retourne le profil créé."""
        try:
            # CRASH RESISTANT LOG: Point d'entrée critique
            log_startup_event("SETUP_START", "Début _run_first_time_setup")
            
            logger.debug("🚀 DÉBUT DÉTAILLÉ DU SETUP...")
            logger.debug(f"   QApplication active: {QApplication.instance() is not None}")
            logger.debug(f"   Thread principal: {QApplication.instance().thread()}")
            
            log_debug_info("SETUP", f"QApp active: {QApplication.instance() is not None}")
            
            logger.info("📦 Import ProfileSetupDialog...")
            log_startup_event("SETUP_IMPORT", "Import ProfileSetupDialog...")
            from app.views.profile_setup import ProfileSetupDialog
            from PySide6.QtWidgets import QMessageBox
            logger.debug("   ✅ Import ProfileSetupDialog réussi")
            log_startup_event("SETUP_IMPORT", "Import ProfileSetupDialog réussi")
            
            # Créer et afficher le dialog de setup avec debugging étendu
            logger.info("📱 Création du dialog de setup...")
            log_startup_event("SETUP_DIALOG", "Création ProfileSetupDialog")
            setup_dialog = ProfileSetupDialog()
            logger.debug("   ✅ Dialog créé")
            log_startup_event("SETUP_DIALOG", "ProfileSetupDialog créé avec succès")
            
            logger.debug("🎨 Configuration dialog...")
            setup_dialog.setWindowTitle("CVMatch - Configuration initiale")
            setup_dialog.resize(900, 700)  # Taille plus grande pour debug
            setup_dialog.setModal(True)
            logger.debug("   ✅ Dialog configuré")
            log_startup_event("SETUP_DIALOG", "Dialog configuré (title, size, modal)")
            
            # Tests de visibilité pré-affichage
            logger.debug("🔍 Tests pré-affichage:")
            logger.debug(f"   Dialog valid: {setup_dialog is not None}")
            logger.debug(f"   Dialog width/height: {setup_dialog.width()}x{setup_dialog.height()}")
            
            # Test show() rapide pour vérifier la création
            logger.debug("🎭 Test show() rapide...")
            setup_dialog.show()
            self.processEvents()  # Traiter les événements
            is_visible_after_show = setup_dialog.isVisible()
            logger.debug(f"   Visible après show(): {is_visible_after_show}")
            
            if not is_visible_after_show:
                logger.error("❌ PROBLÈME: Dialog non visible après show()")
                logger.debug("   Tentative raise() et activateWindow()...")
                setup_dialog.raise_()
                setup_dialog.activateWindow()
                self.processEvents()
                
                # Vérification après tentative de correction
                is_visible_after_raise = setup_dialog.isVisible()
                logger.debug(f"   Visible après raise(): {is_visible_after_raise}")
                
                if not is_visible_after_raise:
                    logger.error("💀 ÉCHEC CRITIQUE: Impossible d'afficher le dialog")
                    # Essai avec QMessageBox simple pour tester l'affichage Qt
                    logger.debug("🔧 Test avec QMessageBox simple...")
                    from PySide6.QtWidgets import QMessageBox
                    test_box = QMessageBox(QMessageBox.Information, "Test CVMatch", "CVMatch peut afficher des dialogs")
                    test_box.show()
                    self.processEvents()
                    test_visible = test_box.isVisible()
                    logger.debug(f"   QMessageBox visible: {test_visible}")
                    test_box.close()
                    
                    if test_visible:
                        logger.error("   ⚠️ QMessageBox fonctionne mais pas ProfileSetupDialog")
                    else:
                        logger.error("   💀 Problème global d'affichage Qt")
            
            logger.info("🎯 Lancement exec() du dialog de setup...")
            logger.debug("   exec() va bloquer jusqu'à fermeture du dialog...")
            
            # CRASH RESISTANT LOG: Point critique - exec()
            log_startup_event("SETUP_EXEC", "AVANT exec() - Point critique")
            
            # POINT CRITIQUE: exec() - c'est ici que ça peut se bloquer/échouer
            result = setup_dialog.exec()
            
            # CRASH RESISTANT LOG: Retour d'exec()
            log_startup_event("SETUP_EXEC", f"APRÈS exec() - Résultat: {result}")
            
            logger.info(f"🎭 Résultat du dialog: {result}")
            logger.debug(f"   DialogCode.Accepted = {setup_dialog.DialogCode.Accepted}")
            logger.debug(f"   DialogCode.Rejected = {setup_dialog.DialogCode.Rejected}")
            
            if result == setup_dialog.DialogCode.Accepted:
                logger.debug("✅ Dialog accepté, récupération profile_id...")
                # Le profil a déjà été créé par le wizard dans ProcessingPage
                profile_id = setup_dialog.get_profile_id()
                logger.debug(f"   Profile ID retourné: {profile_id}")
                
                if profile_id:
                    logger.debug("🔍 Recherche profil en base...")
                    # Récupérer le profil depuis la base de données
                    with get_session() as session:
                        from sqlmodel import select
                        statement = select(UserProfile).where(UserProfile.id == profile_id)
                        created_profile = session.exec(statement).first()
                        
                        if created_profile:
                            # PATCH-PII: Éviter exposition du nom utilisateur
                            logger.info("✅ Profil récupéré via setup: profile_id=%s", created_profile.id)
                            logger.debug("🎉 SETUP RÉUSSI - retour profil")
                            return created_profile
                        else:
                            logger.error("❌ Profil créé mais non trouvé en base")
                            raise Exception("Profil créé mais non trouvé en base")
                else:
                    logger.error("❌ ID de profil manquant après le setup")
                    raise Exception("ID de profil manquant après le setup")
            else:
                # L'utilisateur a annulé le setup - fermeture directe
                logger.info("👋 Setup annulé par l'utilisateur - fermeture de l'application")
                logger.info("🔚 Fin de session CVMatch suite à annulation setup")
                logger.debug("   Appel self.quit() et sys.exit(0)")
                self.quit()
                sys.exit(0)
                    
        except ImportError:
            # Si ProfileSetupDialog n'est pas disponible, fermer l'app
            logger.error("❌ Interface de setup non disponible - fermeture de l'application")
            self.quit()
            sys.exit(1)
        except Exception as e:
            logger.error(f"❌ Erreur durant le setup: {e}")
            # En cas d'erreur, fermer l'app aussi
            self.quit()
            sys.exit(1)
    
    
    def run(self):
        """Lance l'application principale."""
        try:
            # Initialiser la base de données
            if not self.initialize_database():
                return 1
            
            # Récupérer le profil utilisateur
            profile = self.get_or_setup_profile()
            
            # Créer et afficher la fenêtre principale
            main_window = bootstrap_main_window(profile)
            main_window.show()
            
            logger.info("Interface principale affichee")
            
            # Lancer la boucle d'événements
            return self.exec()
            
        except Exception as e:
            logger.error(f"Erreur critique dans l'application: {e}")
            show_error("Erreur Critique", 
                      f"Une erreur critique s'est produite:\n{str(e)}\n\nL'application va se fermer.")
            return 1


def create_user_directories():
    """Crée tous les dossiers nécessaires pour les données utilisateur."""
    user_dirs = [
        # Dossiers principaux de données utilisateur
        "logs",
        "exports",
        "reports",
        "reports/generated",
        "reports/linkedin",
        "cache",
        "models",
        "data",
        "datasets",
        "datasets/user_learning",
        "datasets/training_ready",
        "datasets/base_pretrained",
        "archive",
        "output",
        "CV",                       # Dossier racine CV
        "CV/importés",              # CV uploadés par l'utilisateur
        "CV/générés",               # CV générés par l'application
        # Dossiers runtime (nouvellement organisés)
        "runtime",
        "runtime/cache", 
        "runtime/exports",
        "runtime/output",
        "runtime/data",
        "runtime/models",
        # Dossiers datasets IA/ML
        "runtime/datasets",
        "runtime/datasets/user_learning",
        "runtime/datasets/training_ready", 
        "runtime/datasets/base_pretrained",
        # Dossiers dynamiques créés à l'usage
        "runtime/processing",
        "runtime/temp_uploads",
        "runtime/parsed_documents",
        "runtime/extracted_text",
        "runtime/checkpoints",
        "runtime/training_logs",
        "runtime/model_outputs",
        # Dossiers de développement
        "development/tests/fixtures",           # Structure tests
        "dev_tools/debug",
    ]
    
    for dir_path in user_dirs:
        os.makedirs(dir_path, exist_ok=True)
        
        # Créer un fichier .gitkeep pour maintenir la structure du dossier dans git
        # mais le contenu sera ignoré
        gitkeep_file = os.path.join(dir_path, ".gitkeep")
        if not os.path.exists(gitkeep_file):
            with open(gitkeep_file, 'w', encoding='utf-8') as f:
                f.write("# Ce fichier maintient la structure du dossier dans git\n")
                f.write("# Le contenu du dossier est ignoré par .gitignore\n")
                # Messages spécifiques pour les dossiers CV
                if dir_path == "CV":
                    f.write("# Dossier racine pour l'organisation des CV\n")
                elif dir_path == "CV/importés":
                    f.write("# CV importés/uploadés par l'utilisateur\n")
                elif dir_path == "CV/générés":
                    f.write("# CV générés par l'application CVMatch\n")
    
    print(f"[INFO] Dossiers utilisateur créés: {len(user_dirs)} dossiers")

def run_development_syntax_validation():
    """
    Run syntax validation in development mode to catch issues early.
    Only runs if CVMATCH_DEV_MODE environment variable is set.
    """
    if not os.getenv('CVMATCH_DEV_MODE'):
        return True  # Skip validation in production

    try:
        print("[DEV] Running pre-launch syntax validation...")

        # Import and run syntax validator
        from pathlib import Path
        from scripts.validate_syntax import SyntaxValidator

        project_root = Path(__file__).parent
        validator = SyntaxValidator(project_root)

        # Validate only critical modules for faster startup
        results = validator.validate_all(critical_only=True)

        if results['critical_failures']:
            print(f"[DEV] ❌ Critical syntax issues found - app will likely crash!")
            for failure in results['critical_failures']:
                print(f"[DEV]    • {failure}")

            # In dev mode, show warning but continue (allow debugging)
            print("[DEV] ⚠️  Continuing in development mode despite issues...")
            return True
        else:
            print(f"[DEV] ✅ All critical modules validated successfully ({results['validated_count']} files)")
            return True

    except ImportError:
        print("[DEV] ⚠️  Syntax validator not available - continuing...")
        return True
    except Exception as e:
        print(f"[DEV] ⚠️  Syntax validation error: {e} - continuing...")
        return True


def main():
    """Point d'entrée principal."""
    try:
        # Créer tous les dossiers nécessaires pour les données utilisateur
        create_user_directories()

        # Development mode: Pre-launch syntax validation
        run_development_syntax_validation()

        # Vérification simple du démarrage
        print(f"[INFO] Demarrage CVMatch (PID: {os.getpid()})")

        # Créer l'application
        app = CVMatchApp(sys.argv)

        # Configuration: fermer l'app quand la dernière fenêtre se ferme
        app.setQuitOnLastWindowClosed(True)

        # Lancer l'application
        exit_code = app.run()

        logger.info(f"Application fermee avec le code: {exit_code}")
        print(f"[INFO] CVMatch ferme (code: {exit_code})")
        return exit_code
        
    except KeyboardInterrupt:
        logger.info("Application interrompue par l'utilisateur")
        return 0
    except Exception as e:
        logger.error(f"Erreur fatale: {e}")
        print(f"[ERREUR] Erreur fatale: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
