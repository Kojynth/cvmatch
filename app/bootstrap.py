"""
Bootstrap module - Critical dependency validation and fail-fast initialization.

Performs upfront validation of required dependencies and system prerequisites
before allowing the application to start. Prevents cascade failures and provides
clear error messages when dependencies are missing.
"""

import sys
import importlib.util
import json
import time
import os
from typing import List, Dict, Any, Tuple
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# Critical dependencies that MUST be available at runtime
REQUIRED_DEPENDENCIES = [
    "dateutil",
    "PySide6", 
    "sqlmodel",
    "pandas",
    "numpy",
    "requests",
    "loguru"
]

# Optional but recommended dependencies (lazy loaded now)
OPTIONAL_DEPENDENCIES = [
    "torch",
    "transformers", 
    "sentence_transformers",
    "faiss",
    "weasyprint"
]

# Heavy modules that should be checked in lazy mode for startup speed
HEAVY_MODULES = {"torch", "transformers", "sentence_transformers", "faiss"}

# Cache settings - OPTIMIZED for fast startup
CACHE_FILE = Path("cache/.cvmatch_deps_cache")
CACHE_VALIDITY_HOURS = 24 * 7  # Cache valide 7 jours (vs 24h)
FAST_CACHE_CHECK = True  # Just check file existence for speed


def check_python_version() -> Tuple[bool, str]:
    """Validate Python version compatibility."""
    major, minor = sys.version_info[:2]
    
    if major < 3 or (major == 3 and minor < 10):
        return False, f"Python 3.10+ required, got {major}.{minor}"
    
    if major == 3 and minor > 12:
        return True, f"Python {major}.{minor} (newer than tested 3.12, may have compatibility issues)"
    
    return True, f"Python {major}.{minor} - OK"


def check_dependency(module_name: str, lazy_mode: bool = False) -> Tuple[bool, str]:
    """Check if a specific dependency is available.
    
    Args:
        module_name: Name of module to check
        lazy_mode: If True, only check spec without importing (faster for heavy modules)
    """
    try:
        spec = importlib.util.find_spec(module_name)
        if spec is None:
            return False, f"Module '{module_name}' not found"
        
        # OPTIMIZATION: For heavy modules, just check spec exists
        if lazy_mode:
            return True, f"{module_name} (available, lazy) - OK"
        
        # Try actual import to catch broken installs
        module = importlib.import_module(module_name)
        version = getattr(module, "__version__", "unknown")
        return True, f"{module_name} v{version} - OK"
        
    except ImportError as e:
        return False, f"Import failed for '{module_name}': {e}"
    except Exception as e:
        return False, f"Unexpected error checking '{module_name}': {e}"


def load_dependency_cache() -> Dict[str, Any]:
    """Charger le cache de validation des dépendances - OPTIMIZED."""
    if not CACHE_FILE.exists():
        return None
    
    # OPTIMIZATION: Fast cache check - just verify file age without parsing
    if FAST_CACHE_CHECK:
        try:
            stat = CACHE_FILE.stat()
            if time.time() - stat.st_mtime > CACHE_VALIDITY_HOURS * 3600:
                return None  # Cache expiré
            # Cache valid by timestamp, parse it
        except OSError:
            return None
    
    try:
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
        
        # Double-check validity if not using fast check
        if not FAST_CACHE_CHECK:
            cache_time = cache_data.get('timestamp', 0)
            if time.time() - cache_time > CACHE_VALIDITY_HOURS * 3600:
                return None  # Cache expiré
        
        return cache_data
    except (json.JSONDecodeError, KeyError, FileNotFoundError):
        return None


def save_dependency_cache(results: Dict[str, Any]):
    """Sauvegarder le cache de validation des dépendances."""
    try:
        cache_data = {
            'timestamp': time.time(),
            'results': results
        }
        
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, indent=2)
    except Exception as e:
        print(f"[WARNING] Cannot save dependency cache: {e}")


def validate_critical_dependencies(use_cache: bool = True, parallel: bool = True) -> Dict[str, Any]:
    """Validate all critical dependencies with optional caching and parallelization.
    
    Args:
        use_cache: Use cached validation results
        parallel: Use ThreadPoolExecutor for parallel validation
    """
    # OPTIMIZATION: Check for fast startup mode
    if os.getenv('CVMATCH_FAST_STARTUP') == '1':
        print("[FAST] Fast startup mode - minimal dependency check [FAST]")
        return _minimal_dependency_check()
    
    # Essayer le cache d'abord
    if use_cache:
        cached_results = load_dependency_cache()
        if cached_results:
            print("[CACHE] Using cached dependency validation [FAST]")
            return cached_results['results']
    
    print("[DEPS] Validating dependencies (no cache)...")
    start_time = time.time()
    
    results = {
        "python": check_python_version(),
        "critical": {},
        "optional": {},
        "missing_critical": [],
        "missing_optional": [],
        "all_critical_ok": True
    }
    
    if parallel:
        _validate_dependencies_parallel(results)
    else:
        _validate_dependencies_sequential(results)
    
    validation_time = time.time() - start_time
    print(f"[DEPS] Validation completed in {validation_time:.2f}s")
    
    # Sauvegarder en cache pour la prochaine fois
    if use_cache:
        save_dependency_cache(results)
    
    return results


def _minimal_dependency_check() -> Dict[str, Any]:
    """Minimal dependency check for fast startup mode."""
    results = {
        "python": check_python_version(),
        "critical": {},
        "optional": {},
        "missing_critical": [],
        "missing_optional": [],
        "all_critical_ok": True
    }
    
    # Only check the most critical ones
    essential_deps = ["dateutil", "PySide6"]
    for dep in essential_deps:
        ok, msg = check_dependency(dep)
        results["critical"][dep] = (ok, msg)
        if not ok:
            results["missing_critical"].append(dep)
            results["all_critical_ok"] = False
    
    # Mark others as "assumed OK"
    for dep in REQUIRED_DEPENDENCIES:
        if dep not in essential_deps:
            results["critical"][dep] = (True, f"{dep} (assumed OK - fast mode)")
    
    for dep in OPTIONAL_DEPENDENCIES:
        results["optional"][dep] = (True, f"{dep} (assumed OK - fast mode)")
    
    return results


def _validate_dependencies_parallel(results: Dict[str, Any]):
    """Validate dependencies using ThreadPoolExecutor for speed."""
    with ThreadPoolExecutor(max_workers=4) as executor:
        # Submit critical dependencies
        critical_futures = {}
        for dep in REQUIRED_DEPENDENCIES:
            future = executor.submit(check_dependency, dep, False)
            critical_futures[future] = dep
        
        # Submit optional dependencies
        optional_futures = {}
        for dep in OPTIONAL_DEPENDENCIES:
            lazy_mode = dep in HEAVY_MODULES
            future = executor.submit(check_dependency, dep, lazy_mode)
            optional_futures[future] = dep
        
        # Process critical dependencies
        for future in as_completed(critical_futures):
            dep = critical_futures[future]
            try:
                ok, msg = future.result()
                results["critical"][dep] = (ok, msg)
                if not ok:
                    results["missing_critical"].append(dep)
                    results["all_critical_ok"] = False
            except Exception as e:
                results["critical"][dep] = (False, f"Error checking {dep}: {e}")
                results["missing_critical"].append(dep)
                results["all_critical_ok"] = False
        
        # Process optional dependencies
        for future in as_completed(optional_futures):
            dep = optional_futures[future]
            try:
                ok, msg = future.result()
                results["optional"][dep] = (ok, msg)
                if not ok:
                    results["missing_optional"].append(dep)
            except Exception as e:
                results["optional"][dep] = (False, f"Error checking {dep}: {e}")
                results["missing_optional"].append(dep)


def _validate_dependencies_sequential(results: Dict[str, Any]):
    """Fallback sequential validation."""
    # Check critical dependencies
    for dep in REQUIRED_DEPENDENCIES:
        ok, msg = check_dependency(dep)
        results["critical"][dep] = (ok, msg)
        if not ok:
            results["missing_critical"].append(dep)
            results["all_critical_ok"] = False
    
    # Check optional dependencies - OPTIMIZED with lazy mode for heavy modules
    for dep in OPTIONAL_DEPENDENCIES:
        lazy_mode = dep in HEAVY_MODULES
        ok, msg = check_dependency(dep, lazy_mode=lazy_mode)
        results["optional"][dep] = (ok, msg)
        if not ok:
            results["missing_optional"].append(dep)


def print_dependency_report(results: Dict[str, Any], verbose: bool = False):
    """Print a formatted dependency validation report."""
    print("=" * 60)
    print("[BOOTSTRAP] CVMatch Bootstrap - Dependency Check")
    print("=" * 60)
    
    # Python version
    python_ok, python_msg = results["python"]
    status_icon = "[OK]" if python_ok else "[FAIL]"
    print(f"{status_icon} {python_msg}")
    
    # Critical dependencies
    print(f"\n[DEPS] Critical Dependencies ({len(REQUIRED_DEPENDENCIES)}):")
    for dep, (ok, msg) in results["critical"].items():
        status_icon = "[OK]" if ok else "[FAIL]"
        print(f"  {status_icon} {msg}")
    
    # Optional dependencies (only if verbose or missing)
    if verbose or results["missing_optional"]:
        print(f"\n[OPTS] Optional Dependencies ({len(OPTIONAL_DEPENDENCIES)}):")
        for dep, (ok, msg) in results["optional"].items():
            status_icon = "[OK]" if ok else "[WARN]"
            if verbose or not ok:
                print(f"  {status_icon} {msg}")
    
    print("=" * 60)
    
    # Summary
    if results["all_critical_ok"] and python_ok:
        print("[SUCCESS] All critical dependencies satisfied - Ready to launch!")
    else:
        print("[CRITICAL] Missing critical dependencies - Cannot start application")
        if results["missing_critical"]:
            print(f"   Missing: {', '.join(results['missing_critical'])}")


def fail_fast_boot_check(verbose: bool = False, exit_on_failure: bool = True, use_cache: bool = True, parallel: bool = True) -> bool:
    """
    Perform fail-fast boot check with clear error reporting.
    
    Args:
        verbose: Show optional dependencies status
        exit_on_failure: Exit process if critical deps missing
        use_cache: Use cached validation results
        parallel: Use parallel validation for speed
    
    Returns:
        True if all critical dependencies satisfied, False otherwise
    """
    results = validate_critical_dependencies(use_cache=use_cache, parallel=parallel)
    print_dependency_report(results, verbose=verbose)
    
    python_ok, _ = results["python"] 
    all_ok = results["all_critical_ok"] and python_ok
    
    if not all_ok and exit_on_failure:
        print("\n💡 Installation commands:")
        if results["missing_critical"]:
            print(f"   poetry add {' '.join(results['missing_critical'])}")
            print(f"   # or: pip install {' '.join(results['missing_critical'])}")
        
        print("\n🔄 After installing missing dependencies, restart the application.")
        sys.exit(1)
    
    return all_ok


def get_feature_flags() -> Dict[str, bool]:
    """Load feature flags from environment variables."""
    import os
    
    flags = {
        "NEW_SPLIT": os.getenv("CVMATCH_NEW_SPLIT", "false").lower() == "true",
        "STAGE_OVERRIDE": os.getenv("CVMATCH_STAGE_OVERRIDE", "false").lower() == "true", 
        "PROJECT_ROUTER": os.getenv("CVMATCH_PROJECT_ROUTER", "false").lower() == "true",
        "CERT_LANG_ROUTER": os.getenv("CVMATCH_CERT_LANG_ROUTER", "false").lower() == "true",
        "ENHANCED_EXTRACTION": os.getenv("CVMATCH_ENHANCED_EXTRACTION", "true").lower() == "true",
        "FALLBACK_DATE_PARSER": os.getenv("CVMATCH_FALLBACK_DATE_PARSER", "true").lower() == "true"
    }
    
    # Log active feature flags
    active_flags = [k for k, v in flags.items() if v]
    if active_flags:
        print(f"[FLAGS] Active feature flags: {', '.join(active_flags)}")
    
    return flags


if __name__ == "__main__":
    # Command-line usage for testing
    import argparse
    
    parser = argparse.ArgumentParser(description="CVMatch Bootstrap Dependency Checker")
    parser.add_argument("-v", "--verbose", action="store_true", 
                       help="Show optional dependencies status")
    parser.add_argument("--no-exit", action="store_true", 
                       help="Don't exit on missing dependencies")
    
    args = parser.parse_args()
    
    success = fail_fast_boot_check(
        verbose=args.verbose, 
        exit_on_failure=not args.no_exit
    )
    
    if success:
        flags = get_feature_flags()
        print(f"\n[FLAGS] Feature flags: {flags}")