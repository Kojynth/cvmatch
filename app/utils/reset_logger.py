"""
Reset Logger - Logger dédié pour les opérations de réinitialisation.

Ce logger crée des fichiers de log qui survivent aux opérations de reset,
permettant de tracer l'historique complet des réinitialisations effectuées.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
import shutil

from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG
from ..utils.log_sanitizer import sanitize_text

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


@dataclass
class ResetOperationMetrics:
    """Métriques pour une opération de reset."""
    operation_id: str
    start_time: str
    end_time: Optional[str] = None
    duration_seconds: Optional[float] = None
    
    # Base de données
    database_reset: bool = False
    database_errors: List[str] = None
    
    # Fichiers temporaires
    temp_files_targeted: int = 0
    temp_files_deleted: int = 0
    temp_files_failed: int = 0
    temp_files_errors: List[str] = None
    
    # Dossiers de données
    folders_processed: int = 0
    folders_protected: int = 0
    folders_cleaned: int = 0
    items_deleted: int = 0
    items_protected: int = 0
    folder_errors: List[str] = None
    
    # Fichiers de lancement
    launch_files_verified: List[str] = None
    launch_files_recreated: List[str] = None
    
    # Cache spécialisé
    hf_cache_removed: bool = False
    hf_cache_error: Optional[str] = None
    
    # Résultat global
    success: bool = False
    global_error: Optional[str] = None
    restart_attempted: bool = False

    def __post_init__(self):
        """Initialize mutable default values."""
        if self.database_errors is None:
            self.database_errors = []
        if self.temp_files_errors is None:
            self.temp_files_errors = []
        if self.folder_errors is None:
            self.folder_errors = []
        if self.launch_files_verified is None:
            self.launch_files_verified = []
        if self.launch_files_recreated is None:
            self.launch_files_recreated = []


class ResetLogger:
    """
    Logger spécialisé pour les opérations de réinitialisation.
    
    Crée des logs qui survivent au reset pour maintenir l'historique
    des opérations de réinitialisation.
    """
    
    def __init__(self, project_root: Optional[Path] = None):
        """Initialize reset logger."""
        if project_root is None:
            # Default to project root (survit au reset car pas dans les dossiers purgés)
            project_root = Path(__file__).parent.parent.parent
        
        self.project_root = project_root
        self.reset_log_file = project_root / "reset_operations.log"
        self.reset_history_file = project_root / "reset_history.json"
        
        # Métriques de l'opération courante
        self.current_operation: Optional[ResetOperationMetrics] = None
        
    def start_reset_operation(self) -> str:
        """
        Démarre une nouvelle opération de reset.
        
        Returns:
            ID unique de l'opération
        """
        operation_id = datetime.now().strftime("reset_%Y%m%d_%H%M%S")
        start_time = datetime.now().isoformat()
        
        self.current_operation = ResetOperationMetrics(
            operation_id=operation_id,
            start_time=start_time
        )
        
        # Log de début
        self._write_log_entry(f"🚀 RESET START [{operation_id}] - {start_time}")
        self._write_log_entry(f"📍 Project root: {sanitize_text(str(self.project_root))}")
        
        return operation_id
    
    def log_database_reset(self, success: bool, error: Optional[str] = None):
        """Log du reset de la base de données."""
        if not self.current_operation:
            return
            
        self.current_operation.database_reset = success
        if error:
            self.current_operation.database_errors.append(error)
            self._write_log_entry(f"❌ DATABASE RESET FAILED: {error}")
        else:
            self._write_log_entry("✅ DATABASE RESET SUCCESS")
    
    def log_temp_files_cleanup(self, targeted: int, deleted: int, failed: int, errors: List[str] = None):
        """Log du nettoyage des fichiers temporaires."""
        if not self.current_operation:
            return
            
        self.current_operation.temp_files_targeted = targeted
        self.current_operation.temp_files_deleted = deleted
        self.current_operation.temp_files_failed = failed
        
        if errors:
            self.current_operation.temp_files_errors.extend(errors)
        
        self._write_log_entry(f"📂 TEMP FILES: {deleted}/{targeted} deleted, {failed} failed")
        if errors:
            for error in errors:
                self._write_log_entry(f"   ⚠️ {error}")
    
    def log_folders_cleanup(self, processed: int, protected: int, cleaned: int, 
                          items_deleted: int, items_protected: int, errors: List[str] = None):
        """Log du nettoyage des dossiers."""
        if not self.current_operation:
            return
            
        self.current_operation.folders_processed = processed
        self.current_operation.folders_protected = protected
        self.current_operation.folders_cleaned = cleaned
        self.current_operation.items_deleted = items_deleted
        self.current_operation.items_protected = items_protected
        
        if errors:
            self.current_operation.folder_errors.extend(errors)
        
        self._write_log_entry(f"📁 FOLDERS: {cleaned}/{processed} cleaned, {protected} protected")
        self._write_log_entry(f"📄 ITEMS: {items_deleted} deleted, {items_protected} protected")
        if errors:
            for error in errors:
                self._write_log_entry(f"   ⚠️ {error}")
    
    def log_launch_files_verification(self, verified: List[str], recreated: List[str]):
        """Log de la vérification des fichiers de lancement."""
        if not self.current_operation:
            return
            
        self.current_operation.launch_files_verified = verified
        self.current_operation.launch_files_recreated = recreated
        
        self._write_log_entry(f"🚀 LAUNCH FILES: {len(verified)} verified, {len(recreated)} recreated")
        for recreated_file in recreated:
            self._write_log_entry(f"   🔧 Recreated: {sanitize_text(recreated_file)}")
    
    def log_hf_cache_cleanup(self, success: bool, error: Optional[str] = None):
        """Log du nettoyage du cache HuggingFace."""
        if not self.current_operation:
            return
            
        self.current_operation.hf_cache_removed = success
        if error:
            self.current_operation.hf_cache_error = error
            self._write_log_entry(f"⚠️ HF CACHE CLEANUP FAILED: {error}")
        else:
            self._write_log_entry("🗑️ HF CACHE CLEANED")
    
    def finish_reset_operation(self, success: bool, restart_attempted: bool = False, 
                              global_error: Optional[str] = None) -> Dict[str, Any]:
        """
        Termine l'opération de reset et sauvegarde les métriques.
        
        Args:
            success: True si le reset a réussi globalement
            restart_attempted: True si un redémarrage a été tenté
            global_error: Erreur globale si échec
            
        Returns:
            Métriques finales de l'opération
        """
        if not self.current_operation:
            return {}
        
        # Finaliser les métriques
        end_time = datetime.now()
        start_dt = datetime.fromisoformat(self.current_operation.start_time)
        
        self.current_operation.end_time = end_time.isoformat()
        self.current_operation.duration_seconds = (end_time - start_dt).total_seconds()
        self.current_operation.success = success
        self.current_operation.restart_attempted = restart_attempted
        
        if global_error:
            self.current_operation.global_error = global_error
        
        # Log de fin
        duration_str = f"{self.current_operation.duration_seconds:.1f}s"
        status_icon = "✅" if success else "❌"
        
        self._write_log_entry(f"{status_icon} RESET END [{self.current_operation.operation_id}] - Duration: {duration_str}")
        
        if global_error:
            self._write_log_entry(f"💥 GLOBAL ERROR: {global_error}")
        
        if restart_attempted:
            self._write_log_entry("🔄 APPLICATION RESTART ATTEMPTED")
        
        # Sauvegarder en historique JSON
        self._save_to_history()
        
        # Log final de séparation
        self._write_log_entry("=" * 80)
        
        # Retourner les métriques
        metrics = asdict(self.current_operation)
        self.current_operation = None  # Reset pour prochaine opération
        
        return metrics
    
    def _write_log_entry(self, message: str):
        """Écrit une entrée dans le fichier de log."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] {message}\n"
        
        try:
            # Append to log file (survit au reset)
            with open(self.reset_log_file, 'a', encoding='utf-8') as f:
                f.write(log_line)
                
            # Also log to standard logger pour debug
            logger.info(f"RESET_LOG: {message}")
            
        except Exception as e:
            # Fallback si problème d'écriture
            logger.error(f"Failed to write reset log: {e}")
    
    def _save_to_history(self):
        """Sauvegarde l'opération dans l'historique JSON."""
        if not self.current_operation:
            return
            
        try:
            # Charger l'historique existant
            history_data = {"operations": []}
            if self.reset_history_file.exists():
                try:
                    with open(self.reset_history_file, 'r', encoding='utf-8') as f:
                        loaded_data = json.load(f)
                        # Support ancien format (liste directe) et nouveau format (avec clé "operations")
                        if isinstance(loaded_data, list):
                            history_data["operations"] = loaded_data
                        elif isinstance(loaded_data, dict) and "operations" in loaded_data:
                            history_data = loaded_data
                        else:
                            history_data = {"operations": []}
                except (json.JSONDecodeError, OSError):
                    # Fichier corrompu, on repart à zéro
                    history_data = {"operations": []}
            
            # Ajouter l'opération courante
            history_data["operations"].append(asdict(self.current_operation))
            
            # Garder seulement les 50 dernières opérations pour éviter que le fichier grossisse trop
            if len(history_data["operations"]) > 50:
                history_data["operations"] = history_data["operations"][-50:]
            
            # Sauvegarder avec structure correcte
            with open(self.reset_history_file, 'w', encoding='utf-8') as f:
                json.dump(history_data, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            self._write_log_entry(f"⚠️ Failed to save to history: {e}")
    
    def get_reset_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Récupère l'historique des resets.
        
        Args:
            limit: Nombre maximum d'entrées à retourner
            
        Returns:
            Liste des opérations de reset (plus récentes en premier)
        """
        try:
            if not self.reset_history_file.exists():
                return []
                
            with open(self.reset_history_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
            
            # Retourner les plus récentes en premier
            return history[-limit:][::-1] if history else []
            
        except Exception as e:
            logger.error(f"Failed to read reset history: {e}")
            return []
    
    def cleanup_old_logs(self, days_to_keep: int = 30):
        """
        Nettoie les anciens logs de reset.
        
        Args:
            days_to_keep: Nombre de jours à conserver
        """
        try:
            if not self.reset_log_file.exists():
                return
                
            # Pour les logs texte, on garde tout (ils ne prennent pas beaucoup de place)
            # Mais on peut nettoyer l'historique JSON
            history = self.get_reset_history(limit=100)  # Garder max 100 entrées
            
            if len(history) > days_to_keep:  # Si plus de X entrées, garder les plus récentes
                recent_history = history[:days_to_keep]
                
                with open(self.reset_history_file, 'w', encoding='utf-8') as f:
                    json.dump(recent_history, f, indent=2, ensure_ascii=False)
                    
                logger.info(f"Reset history cleaned: kept {len(recent_history)} recent entries")
                
        except Exception as e:
            logger.error(f"Failed to cleanup reset logs: {e}")


# Instance globale pour faciliter l'utilisation
reset_logger = ResetLogger()
