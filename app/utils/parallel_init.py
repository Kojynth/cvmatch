"""
Parallel Initialization Manager
===============================

Gestionnaire pour paralléliser les initialisations non-critiques.
Réduit le temps de démarrage en lançant plusieurs tâches en parallèle.
"""

import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Callable, Dict, Any, Optional, Tuple
from dataclasses import dataclass

# Logger sécurisé
try:
    from ..logging.safe_logger import get_safe_logger
    from ..config import DEFAULT_PII_CONFIG
    logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


@dataclass
class InitTask:
    """Tâche d'initialisation."""
    name: str
    func: Callable
    args: tuple = ()
    kwargs: dict = None
    critical: bool = False
    timeout: float = 30.0
    
    def __post_init__(self):
        if self.kwargs is None:
            self.kwargs = {}


@dataclass
class InitResult:
    """Résultat d'une tâche d'initialisation."""
    task_name: str
    success: bool
    result: Any = None
    error: Optional[Exception] = None
    duration: float = 0.0


class ParallelInitializer:
    """Gestionnaire d'initialisation parallèle."""
    
    def __init__(self, max_workers: int = 3):
        self.max_workers = max_workers
        self.tasks: List[InitTask] = []
        self.results: Dict[str, InitResult] = {}
    
    def add_task(self, name: str, func: Callable, *args, critical: bool = False, 
                 timeout: float = 30.0, **kwargs):
        """Ajouter une tâche d'initialisation."""
        task = InitTask(
            name=name,
            func=func,
            args=args,
            kwargs=kwargs,
            critical=critical,
            timeout=timeout
        )
        self.tasks.append(task)
        logger.debug(f"📋 Added task: {name} (critical={critical})")
    
    def _execute_task(self, task: InitTask) -> InitResult:
        """Exécuter une tâche d'initialisation."""
        start_time = time.time()
        
        try:
            logger.debug(f"🔄 Starting: {task.name}")
            result = task.func(*task.args, **task.kwargs)
            duration = time.time() - start_time
            
            logger.info(f"✅ Completed: {task.name} ({duration:.2f}s)")
            return InitResult(
                task_name=task.name,
                success=True,
                result=result,
                duration=duration
            )
        
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"❌ Failed: {task.name} ({duration:.2f}s) - {e}")
            
            return InitResult(
                task_name=task.name,
                success=False,
                error=e,
                duration=duration
            )
    
    def run_sequential(self) -> Dict[str, InitResult]:
        """Exécuter les tâches de manière séquentielle (pour debug)."""
        logger.info(f"🔄 Running {len(self.tasks)} tasks sequentially...")
        
        for task in self.tasks:
            result = self._execute_task(task)
            self.results[task.name] = result
            
            # Arrêter si une tâche critique échoue
            if task.critical and not result.success:
                logger.error(f"💀 Critical task failed: {task.name}")
                break
        
        return self.results
    
    def run_parallel(self) -> Dict[str, InitResult]:
        """Exécuter les tâches en parallèle."""
        if not self.tasks:
            return {}
        
        logger.info(f"⚡ Running {len(self.tasks)} tasks in parallel (max_workers={self.max_workers})...")
        start_time = time.time()
        
        # Séparer les tâches critiques et non-critiques
        critical_tasks = [t for t in self.tasks if t.critical]
        non_critical_tasks = [t for t in self.tasks if not t.critical]
        
        # Exécuter les tâches critiques d'abord (séquentiellement)
        for task in critical_tasks:
            result = self._execute_task(task)
            self.results[task.name] = result
            
            if not result.success:
                logger.error(f"💀 Critical task failed: {task.name}")
                return self.results
        
        # Exécuter les tâches non-critiques en parallèle
        if non_critical_tasks:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                # Soumettre toutes les tâches
                future_to_task = {
                    executor.submit(self._execute_task, task): task
                    for task in non_critical_tasks
                }
                
                # Récupérer les résultats au fur et à mesure
                for future in as_completed(future_to_task, timeout=60):
                    task = future_to_task[future]
                    
                    try:
                        result = future.result(timeout=task.timeout)
                        self.results[task.name] = result
                    except Exception as e:
                        logger.error(f"❌ Task {task.name} failed with exception: {e}")
                        self.results[task.name] = InitResult(
                            task_name=task.name,
                            success=False,
                            error=e,
                            duration=0.0
                        )
        
        total_duration = time.time() - start_time
        success_count = sum(1 for r in self.results.values() if r.success)
        
        logger.info(f"⚡ Parallel init completed: {success_count}/{len(self.tasks)} tasks succeeded in {total_duration:.2f}s")
        
        return self.results
    
    def get_result(self, task_name: str) -> Optional[InitResult]:
        """Récupérer le résultat d'une tâche."""
        return self.results.get(task_name)
    
    def get_successful_results(self) -> Dict[str, Any]:
        """Récupérer tous les résultats réussis."""
        return {
            name: result.result 
            for name, result in self.results.items() 
            if result.success
        }
    
    def get_failed_tasks(self) -> List[str]:
        """Récupérer les noms des tâches qui ont échoué."""
        return [
            name for name, result in self.results.items() 
            if not result.success
        ]
    
    def print_summary(self):
        """Afficher un résumé des résultats."""
        if not self.results:
            logger.info("📋 No initialization tasks executed")
            return
        
        total_tasks = len(self.results)
        successful = sum(1 for r in self.results.values() if r.success)
        failed = total_tasks - successful
        total_time = sum(r.duration for r in self.results.values())
        
        logger.info("=" * 50)
        logger.info("📊 INITIALIZATION SUMMARY")
        logger.info("=" * 50)
        logger.info(f"✅ Successful: {successful}/{total_tasks}")
        logger.info(f"❌ Failed: {failed}/{total_tasks}")
        logger.info(f"⏱️ Total time: {total_time:.2f}s")
        
        if failed > 0:
            logger.info("\n❌ Failed tasks:")
            for name, result in self.results.items():
                if not result.success:
                    logger.error(f"  • {name}: {result.error}")
        
        logger.info("\n⏱️ Task durations:")
        for name, result in sorted(self.results.items(), key=lambda x: x[1].duration, reverse=True):
            status = "✅" if result.success else "❌"
            logger.info(f"  • {status} {name}: {result.duration:.2f}s")
        
        logger.info("=" * 50)


# Fonctions utilitaires pour les tâches communes
def init_database():
    """Initialiser la base de données."""
    try:
        from ..models.database import create_db_and_tables
        create_db_and_tables()
        return True
    except Exception as e:
        logger.error(f"Database init failed: {e}")
        return False


def init_logging_handlers():
    """Initialiser les handlers de logging."""
    try:
        import logging
        from logging.handlers import RotatingFileHandler
        from pathlib import Path
        
        # Créer les dossiers logs
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)
        
        return True
    except Exception as e:
        logger.error(f"Logging init failed: {e}")
        return False


def init_user_directories():
    """Créer les dossiers utilisateur."""
    try:
        import os
        user_dirs = [
            "logs", "CV", "CV/importés", "CV/générés",
            "runtime", "runtime/cache", "runtime/exports"
        ]
        
        for dir_path in user_dirs:
            os.makedirs(dir_path, exist_ok=True)
        
        return len(user_dirs)
    except Exception as e:
        logger.error(f"User directories init failed: {e}")
        return False


def preload_gpu_detection():
    """Pré-charger la détection GPU."""
    try:
        from .gpu_utils_optimized import get_gpu_manager
        gpu_manager = get_gpu_manager(use_cache=True)
        return gpu_manager.gpu_info
    except Exception as e:
        logger.error(f"GPU detection failed: {e}")
        return False


def preload_ml_components():
    """Pré-charger les composants ML essentiels."""
    try:
        from .lazy_imports import preload_background
        preload_background()
        return True
    except Exception as e:
        logger.error(f"ML preload failed: {e}")
        return False


# Instance globale pour réutilisation
_global_initializer = None

def get_global_initializer() -> ParallelInitializer:
    """Obtenir l'instance globale du gestionnaire d'initialisation."""
    global _global_initializer
    if _global_initializer is None:
        _global_initializer = ParallelInitializer()
    return _global_initializer