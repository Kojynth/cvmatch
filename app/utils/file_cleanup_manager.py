"""
File Cleanup Manager - Gestionnaire de nettoyage robuste pour Windows
====================================================================

Gère la suppression sécurisée de fichiers verrouillés sous Windows avec
retry et fermeture propre des handles.
"""

import os
import time
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Dict, Optional, Callable
from contextlib import contextmanager
from loguru import logger
import threading
import gc

# Windows-specific imports
try:
    import psutil
    import win32api
    import win32con
    import win32file
    WINDOWS_AVAILABLE = True
except ImportError:
    WINDOWS_AVAILABLE = False


class FileCleanupManager:
    """Gestionnaire de nettoyage de fichiers robuste."""
    
    def __init__(self, max_retries: int = 5, retry_delay: float = 0.5):
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.locked_files = []
        
    def safe_delete_file(self, file_path: Path, force: bool = False) -> bool:
        """
        Supprime un fichier de manière sécurisée avec retry.
        
        Args:
            file_path: Chemin vers le fichier à supprimer
            force: Forcer la suppression même si verrouillé
            
        Returns:
            bool: True si suppression réussie
        """
        if not file_path.exists():
            return True
        
        file_path = Path(file_path)
        
        # Tentative suppression normale
        for attempt in range(self.max_retries):
            try:
                file_path.unlink()
                logger.info("🗑️ Fichier supprimé: %s", "[FILENAME]")
                return True
                
            except PermissionError as e:
                logger.warning(f"⚠️ Tentative {attempt + 1}/{self.max_retries} - "
                             f"Fichier verrouillé: {file_path.name}")
                
                if attempt < self.max_retries - 1:
                    # Attendre et forcer garbage collection
                    time.sleep(self.retry_delay * (attempt + 1))
                    gc.collect()
                    
                    # Essayer de libérer les handles si Windows
                    if force and WINDOWS_AVAILABLE:
                        self._force_close_handles(file_path)
                else:
                    # Dernier recours : renommer et marquer pour suppression
                    if force:
                        return self._mark_for_deletion(file_path)
                    else:
                        logger.error(f"❌ Impossible de supprimer {file_path}: {e}")
                        self.locked_files.append(str(file_path))
                        return False
                        
            except Exception as e:
                logger.error(f"❌ Erreur suppression {file_path}: {e}")
                return False
        
        return False
    
    def safe_delete_directory(self, dir_path: Path, 
                            keep_structure: bool = False,
                            keep_files: List[str] = None) -> bool:
        """
        Supprime un répertoire de manière sécurisée.
        
        Args:
            dir_path: Chemin vers le répertoire
            keep_structure: Garder la structure (juste vider)
            keep_files: Liste des fichiers à préserver (ex: .gitkeep)
            
        Returns:
            bool: True si suppression réussie
        """
        if not dir_path.exists() or not dir_path.is_dir():
            return True
        
        keep_files = keep_files or ['.gitkeep', 'README.md']
        success = True
        
        try:
            for item in dir_path.iterdir():
                # Préserver certains fichiers
                if item.name in keep_files:
                    logger.debug("📌 Préservé: [FILENAME]")
                    continue
                
                try:
                    if item.is_file():
                        if not self.safe_delete_file(item, force=True):
                            success = False
                    elif item.is_dir():
                        if not self.safe_delete_directory(item, keep_structure=False):
                            success = False
                        else:
                            logger.info("🗂️ Dossier supprimé: [FILENAME]/")
                            
                except Exception as e:
                    logger.warning("⚠️ Erreur [FILENAME]: {e}")
                    success = False
            
            # Supprimer le répertoire lui-même si pas keep_structure
            if not keep_structure:
                try:
                    dir_path.rmdir()
                    logger.info("🗂️ Répertoire supprimé: [FILENAME]")
                except OSError:
                    # Répertoire pas vide ou verrouillé
                    logger.warning(f"⚠️ Répertoire non vide ou verrouillé: {dir_path}")
                    success = False
                    
        except Exception as e:
            logger.error(f"❌ Erreur suppression répertoire {dir_path}: {e}")
            success = False
        
        return success
    
    def _force_close_handles(self, file_path: Path) -> bool:
        """Force la fermeture des handles sur un fichier (Windows)."""
        if not WINDOWS_AVAILABLE:
            return False
        
        try:
            # Trouver les processus qui utilisent le fichier
            processes_using_file = []
            
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    for file_obj in proc.open_files():
                        if Path(file_obj.path) == file_path:
                            processes_using_file.append(proc)
                            break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            # Si c'est notre propre processus, essayer de fermer proprement
            current_pid = os.getpid()
            for proc in processes_using_file:
                if proc.pid == current_pid:
                    logger.warning("⚠️ Notre processus utilise encore %s", "[FILENAME]")
                    # Forcer garbage collection et attendre
                    gc.collect()
                    time.sleep(0.5)
                    return True
                else:
                    logger.warning(f"⚠️ Processus {proc.name} (PID: {proc.pid}) "
                                 f"utilise {file_path.name}")
            
            return len(processes_using_file) == 0
            
        except Exception as e:
            logger.debug(f"Erreur force_close_handles: {e}")
            return False
    
    def _mark_for_deletion(self, file_path: Path) -> bool:
        """Marque un fichier pour suppression au redémarrage (Windows)."""
        try:
            # Renommer vers fichier temporaire
            temp_name = f"{file_path.stem}_{int(time.time())}_DELETE{file_path.suffix}"
            temp_path = file_path.parent / temp_name
            
            try:
                file_path.rename(temp_path)
                logger.info(f"🔄 Renommé pour suppression: {temp_name}")
                
                # Marquer pour suppression au redémarrage (Windows)
                if WINDOWS_AVAILABLE:
                    try:
                        win32file.MoveFileEx(
                            str(temp_path), 
                            None, 
                            win32file.MOVEFILE_DELAY_UNTIL_REBOOT
                        )
                        logger.info(f"⏰ Suppression programmée au redémarrage: {temp_name}")
                        return True
                    except Exception as e:
                        logger.warning(f"⚠️ Impossible de programmer suppression: {e}")
                
                # Fallback: tenter suppression directe du fichier renommé
                time.sleep(1.0)
                temp_path.unlink()
                logger.info(f"🗑️ Fichier renommé supprimé: {temp_name}")
                return True
                
            except Exception as e:
                logger.warning("⚠️ Échec renommage %s: {e}", "[FILENAME]")
                return False
                
        except Exception as e:
            logger.error(f"❌ Erreur mark_for_deletion: {e}")
            return False
    
    @contextmanager
    def database_cleanup_context(self, db_paths: List[Path]):
        """Context manager pour nettoyage base de données."""
        try:
            # Avant : fermer toutes les connexions
            logger.info("🔒 Fermeture connexions base de données...")
            self._close_database_connections()
            
            # Attendre que les verrous se libèrent
            time.sleep(1.0)
            
            yield
            
        finally:
            # Après : nettoyage des fichiers DB verrouillés
            for db_path in db_paths:
                if db_path.exists():
                    self.safe_delete_file(db_path, force=True)
    
    def _close_database_connections(self):
        """Force la fermeture des connexions SQLite."""
        try:
            # Import ici pour éviter les dépendances circulaires
            from sqlmodel import Session
            from ..models.database import engine
            
            # Fermer toutes les sessions actives
            if hasattr(engine, 'dispose'):
                engine.dispose()
                logger.debug("🔒 Connexions SQLite fermées")
            
            # Garbage collection pour libérer les références
            gc.collect()
            
        except Exception as e:
            logger.debug(f"Erreur fermeture DB: {e}")
    
    @contextmanager  
    def logging_cleanup_context(self, log_files: List[Path]):
        """Context manager pour nettoyage des logs."""
        original_handlers = []
        
        try:
            # Sauvegarder et supprimer handlers actuels
            from loguru import logger as loguru_logger
            
            # Récupérer handlers actuels
            original_handlers = list(loguru_logger._core.handlers.keys())
            
            # Supprimer tous les handlers vers fichiers
            for handler_id in original_handlers:
                try:
                    loguru_logger.remove(handler_id)
                except ValueError:
                    pass  # Handler déjà supprimé
            
            # Ajouter handler temporaire vers console seulement
            temp_handler_id = loguru_logger.add(
                lambda msg: print(msg, end=""),
                level="INFO",
                format="{time:HH:mm:ss} | {level} | {message}"
            )
            
            logger.info("📝 Handlers de logs temporairement fermés")
            
            # Attendre que les handles se libèrent
            time.sleep(0.5)
            
            yield
            
        except Exception as e:
            logger.error(f"❌ Erreur logging cleanup: {e}")
            
        finally:
            try:
                # Nettoyer les fichiers de logs
                for log_file in log_files:
                    self.safe_delete_file(log_file, force=True)
                
                # Note: Ne pas restaurer les handlers car on reset tout
                logger.debug("📝 Nettoyage logs terminé")
                
            except Exception as e:
                logger.debug(f"Erreur restauration logs: {e}")
    
    def get_cleanup_summary(self) -> Dict[str, any]:
        """Retourne un résumé du nettoyage."""
        return {
            'locked_files_count': len(self.locked_files),
            'locked_files': self.locked_files.copy(),
            'retry_count': self.max_retries,
            'windows_features': WINDOWS_AVAILABLE
        }
