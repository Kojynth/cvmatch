"""
Logger spécialisé pour les opérations d'extraction CV
====================================================

Crée un fichier log dédié uniquement aux opérations d'extraction
pour faciliter l'analyse et le debug des problèmes d'extraction.
"""

import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any


class ExtractionLogger:
    """Logger spécialisé pour l'extraction CV."""
    
    def __init__(self):
        self.extraction_log_path: Optional[str] = None
        self.extraction_started = False
        self.extraction_logger = None
        self.handler = None
        # Pour capturer les logs du logger principal
        self.main_logger_handler = None
        self.original_main_logger_level = None
        # Pour capturer les logs de plusieurs loggers
        self.additional_handlers = []  # Liste des (logger, handler) configurés
        # Pour la double écriture permanente (extraction + logs principaux)
        self.permanent_handlers = []  # Liste des (logger, extraction_handler, main_handler) configurés
        self.main_log_path = "logs/app.log"  # Fichier de logs principal
    
    def start_extraction_session(self, profile_id: str, cv_path: str) -> str:
        """Démarre une session d'extraction et crée le fichier log dédié."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Créer le dossier logs/extraction s'il n'existe pas
        extraction_logs_dir = Path("logs/extraction")
        extraction_logs_dir.mkdir(parents=True, exist_ok=True)
        
        # Nom du fichier log spécialisé
        self.extraction_log_path = f"logs/extraction/cv_extraction_{timestamp}.log"
        
        # Créer un logger standard Python complètement isolé
        logger_name = f"extraction_{timestamp}"
        self.extraction_logger = logging.getLogger(logger_name)
        self.extraction_logger.setLevel(logging.DEBUG)
        
        # S'assurer qu'il n'y a pas d'handlers existants
        self.extraction_logger.handlers.clear()
        
        # Créer le handler pour le fichier
        self.handler = logging.FileHandler(self.extraction_log_path, encoding='utf-8')
        self.handler.setLevel(logging.DEBUG)
        
        # Format proche de loguru
        formatter = logging.Formatter(
            '%(asctime)s.%(msecs)03d | %(levelname)-8s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        self.handler.setFormatter(formatter)
        
        # Ajouter le handler au logger
        self.extraction_logger.addHandler(self.handler)
        
        # Empêcher la propagation vers les loggers parents
        self.extraction_logger.propagate = False
        
        self.extraction_started = True
        
        # Log d'en-tête de session
        self.log_info("="*60)
        self.log_info("NOUVELLE SESSION D'EXTRACTION CV")
        self.log_info("="*60)
        self.log_info(f"Profile ID: {profile_id}")
        self.log_info(f"CV Path: {cv_path}")
        self.log_info(f"Timestamp: {timestamp}")
        self.log_info(f"Log file: {self.extraction_log_path}")
        self.log_info("-"*60)
        
        return self.extraction_log_path
    
    def setup_main_logger_redirection(self, main_logger_name: str = "app.workers.cv_extractor"):
        """Configure le logger principal pour écrire aussi dans le fichier d'extraction."""
        if not self.extraction_started or not self.extraction_log_path:
            return
        
        try:
            # Obtenir le logger principal
            main_logger = logging.getLogger(main_logger_name)
            
            # Sauvegarder le niveau original
            self.original_main_logger_level = main_logger.level
            
            # Créer un handler dédié pour rediriger vers le fichier d'extraction
            self.main_logger_handler = logging.FileHandler(self.extraction_log_path, encoding='utf-8')
            self.main_logger_handler.setLevel(logging.DEBUG)
            
            # Format similaire pour cohérence
            formatter = logging.Formatter(
                '%(asctime)s.%(msecs)03d | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            self.main_logger_handler.setFormatter(formatter)
            
            # Ajouter le handler au logger principal
            main_logger.addHandler(self.main_logger_handler)
            
            # S'assurer que le niveau permet de capturer tous les logs importants
            if main_logger.level > logging.DEBUG:
                main_logger.setLevel(logging.DEBUG)
            
            self.log_info("📝 REDIRECTION ACTIVÉE: Logs détaillés du worker principal capturés")
            self.log_debug(f"   Logger configuré: {main_logger_name}")
            self.log_debug(f"   Niveau: {logging.getLevelName(main_logger.level)}")
            
        except Exception as e:
            self.log_warning(f"⚠️ Erreur configuration redirection logger: {e}")
    
    def cleanup_main_logger_redirection(self, main_logger_name: str = "app.workers.cv_extractor"):
        """Nettoie la redirection du logger principal."""
        if not self.main_logger_handler:
            return
        
        try:
            # Obtenir le logger principal
            main_logger = logging.getLogger(main_logger_name)
            
            # Retirer le handler d'extraction
            main_logger.removeHandler(self.main_logger_handler)
            self.main_logger_handler.close()
            
            # Restaurer le niveau original si on l'a modifié
            if self.original_main_logger_level is not None:
                main_logger.setLevel(self.original_main_logger_level)
            
            self.log_debug("✅ Redirection logger principale nettoyée")
            
        except Exception as e:
            self.log_warning(f"⚠️ Erreur nettoyage redirection: {e}")
        finally:
            self.main_logger_handler = None
            self.original_main_logger_level = None
    
    def setup_multiple_loggers_redirection(self, logger_names: list[str]):
        """Configure plusieurs loggers pour écrire simultanément dans extraction ET logs principaux."""
        if not self.extraction_started or not self.extraction_log_path:
            return
        
        # Créer le dossier logs principal s'il n'existe pas
        Path("logs").mkdir(parents=True, exist_ok=True)
        
        for logger_name in logger_names:
            try:
                logger_obj = logging.getLogger(logger_name)

                # Handler pour le fichier d'extraction SEULEMENT
                # Main logging is handled by root logger configured in main.py
                extraction_handler = logging.FileHandler(self.extraction_log_path, encoding='utf-8')
                extraction_handler.setLevel(logging.DEBUG)

                # Format for extraction log
                formatter = logging.Formatter(
                    '%(asctime)s.%(msecs)03d | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S'
                )
                extraction_handler.setFormatter(formatter)

                # Ajouter SEULEMENT le handler d'extraction
                # Root logger handlers will handle main logging
                logger_obj.addHandler(extraction_handler)

                # FORCER le niveau DEBUG pour capturer tous les logs détaillés
                logger_obj.setLevel(logging.DEBUG)

                # Sauvegarder pour nettoyage ultérieur (only extraction handler)
                self.permanent_handlers.append((logger_obj, extraction_handler, None))

                self.log_debug(f"   Logger configuré (extraction seulement): {logger_name}")
                
            except Exception as e:
                self.log_warning(f"⚠️ Erreur configuration logger {logger_name}: {e}")
        
        if self.permanent_handlers:
            self.log_info(f"📝 DOUBLE-ÉCRITURE MULTI-LOGGERS: {len(self.permanent_handlers)} loggers configurés")
    
    def cleanup_extraction_only_handlers(self):
        """Nettoie SEULEMENT les handlers d'extraction, garde les handlers principaux actifs."""
        # Nettoyer le logger principal (temporaire)
        self.cleanup_main_logger_redirection()
        
        # Pour les loggers permanents, supprimer seulement le handler d'extraction
        for logger_obj, extraction_handler, main_handler in self.permanent_handlers:
            try:
                # Supprimer seulement le handler d'extraction
                logger_obj.removeHandler(extraction_handler)
                extraction_handler.close()
                # Garder le main_handler actif pour continuer à loguer
                self.log_debug(f"   Handler extraction supprimé pour: {logger_obj.name}")
            except Exception as e:
                self.log_warning(f"⚠️ Erreur nettoyage extraction handler: {e}")
        
        # Nettoyer les loggers additionnels (ancienne méthode)
        for logger_obj, handler in self.additional_handlers:
            try:
                logger_obj.removeHandler(handler)
                handler.close()
            except Exception as e:
                self.log_warning(f"⚠️ Erreur nettoyage handler: {e}")
        
        self.additional_handlers.clear()
        self.log_debug("✅ Handlers d'extraction nettoyés (handlers principaux conservés)")
    
    def cleanup_all_handlers_completely(self):
        """Nettoie TOUS les handlers (à utiliser seulement à l'arrêt de l'application)."""
        # Nettoyer complètement tous les handlers
        for logger_obj, extraction_handler, main_handler in self.permanent_handlers:
            try:
                logger_obj.removeHandler(extraction_handler)
                extraction_handler.close()
                if main_handler:
                    main_handler.close()
            except Exception as e:
                print(f"⚠️ Erreur nettoyage complet: {e}")
        
        self.permanent_handlers.clear()
        print("✅ TOUS les handlers nettoyés")
    
    def log_info(self, message: str):
        """Log une information d'extraction."""
        if self.extraction_started and self.extraction_logger:
            self.extraction_logger.info(message)
    
    def log_debug(self, message: str):
        """Log un debug d'extraction."""
        if self.extraction_started and self.extraction_logger:
            self.extraction_logger.debug(message)
    
    def log_warning(self, message: str):
        """Log un warning d'extraction."""
        if self.extraction_started and self.extraction_logger:
            self.extraction_logger.warning(message)
    
    def log_error(self, message: str):
        """Log une erreur d'extraction."""
        if self.extraction_started and self.extraction_logger:
            self.extraction_logger.error(message)
    
    def log_section_start(self, section_name: str):
        """Log le début d'extraction d'une section."""
        self.log_info(f"📋 SECTION: {section_name.upper()}")
        self.log_debug(f"   Début extraction section: {section_name}")
    
    def log_section_result(self, section_name: str, data: Dict[str, Any], confidence: float = None):
        """Log le résultat d'extraction d'une section."""
        if data:
            items_count = len(data) if isinstance(data, (list, dict)) else 1
            self.log_info(f"   ✅ {section_name}: {items_count} élément(s) extraits")
            if confidence:
                self.log_debug(f"   Confiance: {confidence:.2f}")
            
            # Log un résumé des données sans PII
            if isinstance(data, dict):
                keys = list(data.keys())[:3]  # Première 3 clés
                self.log_debug(f"   Clés trouvées: {keys}{'...' if len(data) > 3 else ''}")
            elif isinstance(data, list) and len(data) > 0:
                self.log_debug(f"   Premier élément type: {type(data[0]).__name__}")
        else:
            self.log_warning(f"   ⚠️  {section_name}: Aucune donnée extraite")
    
    def log_section_error(self, section_name: str, error: str):
        """Log une erreur d'extraction de section."""
        self.log_error(f"   ❌ {section_name}: ERREUR - {error}")
    
    def log_progress(self, percentage: int, current_step: str):
        """Log la progression de l'extraction."""
        self.log_info(f"🔄 Progression: {percentage:3d}% - {current_step}")
    
    def log_ml_operation(self, operation: str, model_name: str = None, duration: float = None):
        """Log une opération ML/IA."""
        msg = f"🤖 ML: {operation}"
        if model_name:
            msg += f" (modèle: {model_name})"
        if duration:
            msg += f" (durée: {duration:.2f}s)"
        self.log_debug(msg)
    
    def log_document_analysis(self, doc_type: str, pages: int, text_length: int):
        """Log l'analyse du document."""
        self.log_info(f"📄 Document: type={doc_type}, pages={pages}, longueur={text_length} chars")
    
    def end_extraction_session(self, success: bool, total_duration: float = None):
        """Termine la session d'extraction."""
        if not self.extraction_started:
            return
        
        self.log_info("-"*60)
        if success:
            self.log_info("✅ EXTRACTION TERMINÉE AVEC SUCCÈS")
        else:
            self.log_error("❌ EXTRACTION ÉCHOUÉE")
        
        if total_duration:
            self.log_info(f"⏱️  Durée totale: {total_duration:.2f}s")
        
        self.log_info("="*60)
        self.log_info(f"Log détaillé disponible: {self.extraction_log_path}")
        self.log_info("="*60)
        
        # Nettoyage automatique des anciens logs d'extraction (garder les 15 plus récents)
        self._cleanup_old_extraction_logs()
        
        # Nettoyer seulement les handlers d'extraction (garder les logs principaux)
        self.cleanup_extraction_only_handlers()
        
        # Nettoyer le logger d'extraction
        if self.extraction_logger and self.handler:
            self.extraction_logger.removeHandler(self.handler)
            self.handler.close()
            self.extraction_logger = None
            self.handler = None
        
        self.extraction_started = False
    
    def _cleanup_old_extraction_logs(self):
        """Nettoie les anciens logs d'extraction."""
        try:
            extraction_logs_dir = Path("logs/extraction")
            if extraction_logs_dir.exists():
                log_files = list(extraction_logs_dir.glob("cv_extraction_*.log"))
                if len(log_files) > 15:
                    # Trier par date de modification et supprimer les plus anciens
                    log_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                    for old_log in log_files[15:]:
                        try:
                            old_log.unlink()
                            self.log_debug(f"Ancien log supprimé: {old_log.name}")
                        except Exception:
                            pass  # Ignore les erreurs de suppression
        except Exception as e:
            self.log_warning(f"Erreur nettoyage logs: {e}")


# Instance globale du logger d'extraction
extraction_logger_instance = ExtractionLogger()


def get_extraction_logger() -> ExtractionLogger:
    """Récupère l'instance du logger d'extraction."""
    return extraction_logger_instance
