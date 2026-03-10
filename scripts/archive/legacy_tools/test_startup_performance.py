#!/usr/bin/env python3
"""
Test de performance de démarrage CVMatch
========================================

Script pour mesurer l'impact des optimisations de démarrage.
Compare les temps de démarrage avec et sans optimisations.
"""

import os
import sys
import time
import subprocess
import json
from pathlib import Path
from typing import Dict, List, Any
from dataclasses import dataclass, asdict

# Ajouter le répertoire parent au path pour les imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@dataclass
class StartupMetrics:
    """Métriques de démarrage."""
    total_time: float
    bootstrap_time: float = 0.0
    imports_time: float = 0.0
    gpu_detection_time: float = 0.0
    database_init_time: float = 0.0
    profile_setup_time: float = 0.0
    optimizations_used: List[str] = None
    
    def __post_init__(self):
        if self.optimizations_used is None:
            self.optimizations_used = []


class StartupBenchmark:
    """Benchmark de démarrage CVMatch."""
    
    def __init__(self):
        self.results: List[StartupMetrics] = []
        self.project_root = Path(__file__).parent.parent
    
    def cleanup_cache_files(self):
        """Nettoyer les fichiers de cache pour un test propre."""
        cache_files = [
            self.project_root / "cache" / ".cvmatch_deps_cache",
            self.project_root / "cache" / ".cvmatch_gpu_cache"
        ]
        
        for cache_file in cache_files:
            if cache_file.exists():
                cache_file.unlink()
                print(f"[CLEAN] Removed cache: {cache_file.name}")
    
    def measure_import_time(self) -> Dict[str, float]:
        """Mesurer le temps d'import des modules principaux."""
        import_times = {}
        
        # Test import lazy_imports
        start = time.time()
        try:
            from app.utils.lazy_imports import get_torch, get_transformers
            import_times['lazy_imports'] = time.time() - start
        except ImportError as e:
            import_times['lazy_imports'] = -1
            print(f"[ERROR] lazy_imports failed: {e}")
        
        # Test import bootstrap
        start = time.time()
        try:
            from app.bootstrap import fail_fast_boot_check
            import_times['bootstrap'] = time.time() - start
        except ImportError as e:
            import_times['bootstrap'] = -1
            print(f"[ERROR] bootstrap failed: {e}")
        
        # Test import GPU utils
        start = time.time()
        try:
            from app.utils.gpu_utils_optimized import get_gpu_manager
            import_times['gpu_utils'] = time.time() - start
        except ImportError as e:
            import_times['gpu_utils'] = -1
            print(f"[ERROR] gpu_utils failed: {e}")
        
        # Test import WeasyPrint lazy
        start = time.time()
        try:
            from app.utils.lazy_weasyprint import is_weasyprint_available
            import_times['lazy_weasyprint'] = time.time() - start
        except ImportError as e:
            import_times['lazy_weasyprint'] = -1
            print(f"[ERROR] lazy_weasyprint failed: {e}")
        
        return import_times
    
    def test_dependency_cache(self) -> Dict[str, float]:
        """Tester l'efficacité du cache des dépendances."""
        try:
            from app.bootstrap import fail_fast_boot_check
            
            # Premier appel (sans cache)
            self.cleanup_cache_files()
            start = time.time()
            fail_fast_boot_check(verbose=False, exit_on_failure=False, use_cache=False)
            no_cache_time = time.time() - start
            
            # Deuxième appel (avec cache)
            start = time.time()
            fail_fast_boot_check(verbose=False, exit_on_failure=False, use_cache=True)
            with_cache_time = time.time() - start
            
            return {
                'no_cache': no_cache_time,
                'with_cache': with_cache_time,
                'cache_speedup': (no_cache_time - with_cache_time) / no_cache_time * 100
            }
        except ImportError:
            return {'no_cache': -1, 'with_cache': -1, 'cache_speedup': 0}
    
    def test_gpu_detection_cache(self) -> Dict[str, float]:
        """Tester l'efficacité du cache GPU."""
        try:
            from app.utils.gpu_utils_optimized import get_gpu_manager
            
            # Premier appel (sans cache)
            gpu_cache = Path(".cvmatch_gpu_cache")
            if gpu_cache.exists():
                gpu_cache.unlink()
            
            start = time.time()
            gpu_manager = get_gpu_manager(use_cache=False)
            no_cache_time = time.time() - start
            
            # Deuxième appel (avec cache)
            start = time.time()
            gpu_manager_cached = get_gpu_manager(use_cache=True)
            with_cache_time = time.time() - start
            
            return {
                'no_cache': no_cache_time,
                'with_cache': with_cache_time,
                'cache_speedup': (no_cache_time - with_cache_time) / no_cache_time * 100 if no_cache_time > 0 else 0
            }
        except ImportError:
            return {'no_cache': -1, 'with_cache': -1, 'cache_speedup': 0}
    
    def test_lazy_loading(self) -> Dict[str, float]:
        """Tester l'efficacité du lazy loading."""
        try:
            from app.utils.lazy_imports import get_torch, get_transformers, get_lazy_stats
            
            # Mesurer le temps de premier accès (chargement réel)
            start = time.time()
            torch_module = get_torch()
            torch_load_time = time.time() - start
            
            # Mesurer le temps de second accès (déjà chargé)
            start = time.time()
            torch_module_cached = get_torch()
            torch_cached_time = time.time() - start
            
            # Stats lazy loading
            stats = get_lazy_stats()
            
            return {
                'torch_first_load': torch_load_time,
                'torch_cached': torch_cached_time,
                'lazy_stats': stats
            }
        except ImportError:
            return {'torch_first_load': -1, 'torch_cached': -1, 'lazy_stats': {}}
    
    def test_parallel_init(self) -> Dict[str, float]:
        """Tester l'efficacité de l'initialisation parallèle."""
        try:
            from app.utils.parallel_init import ParallelInitializer
            from app.utils.parallel_init import init_user_directories, init_logging_handlers, preload_gpu_detection
            
            # Test séquentiel
            init_seq = ParallelInitializer(max_workers=1)
            init_seq.add_task("user_dirs", init_user_directories)
            init_seq.add_task("logging", init_logging_handlers)
            init_seq.add_task("gpu", preload_gpu_detection)
            
            start = time.time()
            results_seq = init_seq.run_sequential()
            sequential_time = time.time() - start
            
            # Test parallèle
            init_par = ParallelInitializer(max_workers=3)
            init_par.add_task("user_dirs", init_user_directories)
            init_par.add_task("logging", init_logging_handlers)
            init_par.add_task("gpu", preload_gpu_detection)
            
            start = time.time()
            results_par = init_par.run_parallel()
            parallel_time = time.time() - start
            
            return {
                'sequential': sequential_time,
                'parallel': parallel_time,
                'speedup': (sequential_time - parallel_time) / sequential_time * 100 if sequential_time > 0 else 0
            }
        except ImportError:
            return {'sequential': -1, 'parallel': -1, 'speedup': 0}
    
    def run_full_benchmark(self) -> Dict[str, Any]:
        """Exécuter le benchmark complet."""
        print("[BENCHMARK] Starting CVMatch startup performance benchmark...")
        print("=" * 60)
        
        results = {}
        
        # Test des temps d'import
        print("[IMPORT] Testing import times...")
        results['import_times'] = self.measure_import_time()
        
        # Test du cache des dépendances
        print("[CACHE] Testing dependency cache...")
        results['dependency_cache'] = self.test_dependency_cache()
        
        # Test du cache GPU
        print("[GPU] Testing GPU detection cache...")
        results['gpu_cache'] = self.test_gpu_detection_cache()
        
        # Test du lazy loading
        print("[LAZY] Testing lazy loading...")
        results['lazy_loading'] = self.test_lazy_loading()
        
        # Test de l'initialisation parallèle
        print("[PARALLEL] Testing parallel initialization...")
        results['parallel_init'] = self.test_parallel_init()
        
        return results
    
    def print_results(self, results: Dict[str, Any]):
        """Afficher les résultats du benchmark."""
        print("\n" + "=" * 60)
        print("📊 PERFORMANCE BENCHMARK RESULTS")
        print("=" * 60)
        
        # Import times
        print("\n📦 Import Times:")
        for module, time_val in results['import_times'].items():
            if time_val >= 0:
                print(f"  • {module}: {time_val:.3f}s")
            else:
                print(f"  • {module}: FAILED")
        
        # Dependency cache
        print("\n🔄 Dependency Cache:")
        dep_cache = results['dependency_cache']
        if dep_cache['no_cache'] >= 0:
            print(f"  • Without cache: {dep_cache['no_cache']:.3f}s")
            print(f"  • With cache: {dep_cache['with_cache']:.3f}s")
            print(f"  • Speedup: {dep_cache['cache_speedup']:.1f}%")
        else:
            print("  • FAILED")
        
        # GPU cache
        print("\n🎮 GPU Detection Cache:")
        gpu_cache = results['gpu_cache']
        if gpu_cache['no_cache'] >= 0:
            print(f"  • Without cache: {gpu_cache['no_cache']:.3f}s")
            print(f"  • With cache: {gpu_cache['with_cache']:.3f}s")
            print(f"  • Speedup: {gpu_cache['cache_speedup']:.1f}%")
        else:
            print("  • FAILED")
        
        # Lazy loading
        print("\n⚡ Lazy Loading:")
        lazy = results['lazy_loading']
        if lazy['torch_first_load'] >= 0:
            print(f"  • PyTorch first load: {lazy['torch_first_load']:.3f}s")
            print(f"  • PyTorch cached: {lazy['torch_cached']:.3f}s")
            print(f"  • Lazy stats: {len(lazy['lazy_stats'])} modules registered")
        else:
            print("  • FAILED")
        
        # Parallel init
        print("\n🔄 Parallel Initialization:")
        par_init = results['parallel_init']
        if par_init['sequential'] >= 0:
            print(f"  • Sequential: {par_init['sequential']:.3f}s")
            print(f"  • Parallel: {par_init['parallel']:.3f}s")
            print(f"  • Speedup: {par_init['speedup']:.1f}%")
        else:
            print("  • FAILED")
        
        # Calculate total estimated speedup
        total_speedup = 0
        speedup_count = 0
        
        if dep_cache['cache_speedup'] > 0:
            total_speedup += dep_cache['cache_speedup']
            speedup_count += 1
        
        if gpu_cache['cache_speedup'] > 0:
            total_speedup += gpu_cache['cache_speedup']
            speedup_count += 1
        
        if par_init['speedup'] > 0:
            total_speedup += par_init['speedup']
            speedup_count += 1
        
        if speedup_count > 0:
            avg_speedup = total_speedup / speedup_count
            print(f"\n🎯 ESTIMATED TOTAL SPEEDUP: {avg_speedup:.1f}%")
        
        print("=" * 60)
    
    def save_results(self, results: Dict[str, Any], filename: str = "startup_benchmark_results.json"):
        """Sauvegarder les résultats en JSON."""
        results_file = Path(filename)
        
        # Ajouter metadata
        results['metadata'] = {
            'timestamp': time.time(),
            'python_version': sys.version,
            'platform': sys.platform,
            'project_root': str(self.project_root)
        }
        
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"💾 Results saved to: {results_file}")


def main():
    """Point d'entrée principal."""
    benchmark = StartupBenchmark()
    
    # Arguments de ligne de commande simples
    if len(sys.argv) > 1 and sys.argv[1] == "--clean":
        print("🧹 Cleaning cache files...")
        benchmark.cleanup_cache_files()
        print("✅ Cache cleaned")
        return
    
    # Exécuter le benchmark
    results = benchmark.run_full_benchmark()
    
    # Afficher et sauvegarder les résultats
    benchmark.print_results(results)
    benchmark.save_results(results)


if __name__ == "__main__":
    main()