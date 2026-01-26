#!/usr/bin/env python3
"""
Module de logging résistant aux crashes
======================================
S'assure que les logs critiques sont sauvés même en cas de crash de l'application.
"""

import os
import sys
import threading
import time
import atexit
from pathlib import Path
from typing import Optional
import datetime

class CrashResistantLogger:
    """Logger qui écrit immédiatement et force le flush pour résister aux crashes."""
    
    def __init__(self, log_dir: str = "logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        
        # Fichiers de log multiples pour redondance
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.main_log = self.log_dir / "crash_resistant.log"
        self.session_log = self.log_dir / f"session_{timestamp}.log"
        self.emergency_log = self.log_dir / "emergency_backup.log"
        
        # Verrou pour thread-safety
        self._lock = threading.Lock()
        
        # Flag pour éviter récursion lors du cleanup
        self._shutting_down = False
        
        # Auto-cleanup à la fermeture
        atexit.register(self.shutdown)
        
        # Log de démarrage
        self.log("CRASH_RESISTANT_LOGGER", "Initialisation du logger résistant aux crashes")
        self.log("CRASH_RESISTANT_LOGGER", f"Session: {timestamp}")
        self.log("CRASH_RESISTANT_LOGGER", f"PID: {os.getpid()}")
    
    def log(self, source: str, message: str, level: str = "INFO"):
        """Écrit un message dans tous les fichiers de log avec flush immédiat."""
        if self._shutting_down:
            return
            
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        log_line = f"[{timestamp}] {level:>5} | {source:>20} | {message}\n"
        
        with self._lock:
            # Écrire dans tous les fichiers avec gestion d'erreurs
            for log_file in [self.main_log, self.session_log, self.emergency_log]:
                try:
                    with open(log_file, "a", encoding="utf-8") as f:
                        f.write(log_line)
                        f.flush()
                        os.fsync(f.fileno())  # Force l'écriture sur disque
                except Exception as e:
                    # En cas d'erreur d'écriture, essayer au moins stderr
                    print(f"[ERREUR LOG] {log_file}: {e}", file=sys.stderr)
        
        # Aussi afficher sur la console
        print(f"[CRASH-LOG] {log_line.strip()}")
    
    def error(self, source: str, message: str):
        """Log une erreur."""
        self.log(source, message, "ERROR")
    
    def warning(self, source: str, message: str):
        """Log un avertissement."""
        self.log(source, message, "WARN")
    
    def debug(self, source: str, message: str):
        """Log debug."""
        self.log(source, message, "DEBUG")
    
    def critical(self, source: str, message: str):
        """Log critique - écrit aussi dans un fichier d'urgence séparé."""
        self.log(source, message, "CRITICAL")
        
        # Fichier critique séparé
        critical_file = self.log_dir / "critical_errors.log"
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        critical_line = f"[{timestamp}] CRITICAL | {source} | {message}\n"
        
        try:
            with open(critical_file, "a", encoding="utf-8") as f:
                f.write(critical_line)
                f.flush()
                os.fsync(f.fileno())
        except Exception:
            pass  # Si on ne peut pas écrire, tant pis
    
    def log_exception(self, source: str, exception: Exception):
        """Log une exception avec traceback."""
        import traceback
        tb = traceback.format_exc()
        self.error(source, f"Exception: {exception}")
        self.error(source, f"Traceback: {tb}")
    
    def shutdown(self):
        """Nettoyage à la fermeture."""
        if self._shutting_down:
            return
            
        self._shutting_down = True
        self.log("CRASH_RESISTANT_LOGGER", "Arrêt du logger résistant aux crashes")

# Instance globale
_global_crash_logger: Optional[CrashResistantLogger] = None

def get_crash_logger() -> CrashResistantLogger:
    """Retourne l'instance globale du crash logger."""
    global _global_crash_logger
    if _global_crash_logger is None:
        _global_crash_logger = CrashResistantLogger()
    return _global_crash_logger

def log_startup_event(event: str, details: str = ""):
    """Fonction de convenance pour logger les événements de démarrage."""
    logger = get_crash_logger()
    logger.log("STARTUP", f"{event} | {details}")

def log_critical_error(source: str, error: str):
    """Fonction de convenance pour logger les erreurs critiques."""
    logger = get_crash_logger()
    logger.critical(source, error)

def log_debug_info(source: str, info: str):
    """Fonction de convenance pour logger les infos de debug."""
    logger = get_crash_logger()
    logger.debug(source, info)

# Installation d'un handler d'exception global
def global_exception_handler(exc_type, exc_value, exc_traceback):
    """Handler global pour capturer toutes les exceptions non gérées."""
    if _global_crash_logger:
        _global_crash_logger.critical(
            "GLOBAL_EXCEPTION",
            f"Exception non gérée: {exc_type.__name__}: {exc_value}"
        )
        _global_crash_logger.log_exception("GLOBAL_EXCEPTION", exc_value)
    
    # Appeler le handler par défaut
    sys.__excepthook__(exc_type, exc_value, exc_traceback)

# Installer le handler global
sys.excepthook = global_exception_handler

if __name__ == "__main__":
    # Test du logger
    logger = get_crash_logger()
    logger.log("TEST", "Test du crash resistant logger")
    logger.error("TEST", "Test erreur")
    logger.critical("TEST", "Test critique")
    
    try:
        raise ValueError("Test exception")
    except Exception as e:
        logger.log_exception("TEST", e)
    
    print("Test terminé - vérifiez les fichiers de log")
