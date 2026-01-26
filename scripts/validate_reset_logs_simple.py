#!/usr/bin/env python3
"""
Script de validation des logs de réinitialisation (Version Windows-safe)
======================================================================

Valide que la fonction 'réinitialiser' (reset_profile) génère correctement
tous les logs attendus via le système ResetLogger.

Usage:
    python scripts/validate_reset_logs_simple.py
"""

from __future__ import annotations

import sys
import json
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from app.utils.reset_logger import ResetLogger
    from app.logging.safe_logger import get_safe_logger
    from app.config import DEFAULT_PII_CONFIG
except ImportError as e:
    print(f"ERREUR: Impossible d'importer les modules CVMatch: {e}")
    sys.exit(1)

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


def validate_reset_history_file(project_root: Path) -> Dict[str, Any]:
    """Valide le fichier reset_history.json."""
    reset_history_file = project_root / "reset_history.json"
    
    results = {
        'file_exists': reset_history_file.exists(),
        'operations_count': 0,
        'last_operation': None,
        'issues': []
    }
    
    if not results['file_exists']:
        results['issues'].append("Fichier reset_history.json non trouvé")
        return results
    
    try:
        with open(reset_history_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        operations = data.get('operations', [])
        results['operations_count'] = len(operations)
        
        if operations:
            results['last_operation'] = operations[-1]
            
            # Vérifier la dernière opération
            last_op = operations[-1]
            required_fields = ['operation_id', 'start_time', 'success', 'database_reset']
            
            for field in required_fields:
                if field not in last_op:
                    results['issues'].append(f"Champ manquant dans la dernière opération: {field}")
                    
        else:
            results['issues'].append("Aucune opération trouvée dans l'historique")
            
    except json.JSONDecodeError:
        results['issues'].append("Fichier JSON invalide")
    except Exception as e:
        results['issues'].append(f"Erreur lors de la lecture: {e}")
    
    return results


def check_reset_logger_in_code(project_root: Path) -> Dict[str, Any]:
    """Vérifie que reset_profile() utilise ResetLogger."""
    settings_dialog_path = project_root / "app" / "views" / "settings_dialog.py"
    
    results = {
        'file_exists': settings_dialog_path.exists(),
        'has_reset_function': False,
        'uses_reset_logger': False,
        'calls_start_operation': False,
        'calls_finish_operation': False,
        'issues': []
    }
    
    if not results['file_exists']:
        results['issues'].append("Fichier settings_dialog.py non trouvé")
        return results
    
    try:
        with open(settings_dialog_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Vérifications
        if "def reset_profile(" in content:
            results['has_reset_function'] = True
        else:
            results['issues'].append("Fonction reset_profile() non trouvée")
        
        if "reset_logger" in content:
            results['uses_reset_logger'] = True
        else:
            results['issues'].append("reset_logger non utilisé")
        
        if "start_reset_operation" in content:
            results['calls_start_operation'] = True
        else:
            results['issues'].append("start_reset_operation() non appelé")
        
        if "finish_reset_operation" in content:
            results['calls_finish_operation'] = True
        else:
            results['issues'].append("finish_reset_operation() non appelé")
            
    except Exception as e:
        results['issues'].append(f"Erreur lors de l'analyse du code: {e}")
    
    return results


def main():
    """Point d'entrée principal."""
    
    print("VALIDATION DES LOGS DE REINITIALISATION")
    print("=" * 45)
    
    # 1. Vérifier le fichier d'historique
    print("\n1. Validation du fichier reset_history.json")
    history_results = validate_reset_history_file(project_root)
    
    if history_results['file_exists']:
        print(f"[OK] Fichier trouvé")
        print(f"[INFO] Nombre d'opérations: {history_results['operations_count']}")
        
        if history_results['last_operation']:
            last_op = history_results['last_operation']
            success = "[SUCCES]" if last_op.get('success', False) else "[ECHEC]"
            print(f"[INFO] Dernière opération: {last_op.get('operation_id', 'unknown')} {success}")
            
            # Afficher les détails de la dernière opération
            if 'duration_seconds' in last_op:
                print(f"[INFO] Durée: {last_op['duration_seconds']:.1f}s")
            if 'database_reset' in last_op:
                db_status = "[OK]" if last_op['database_reset'] else "[ECHEC]"
                print(f"[INFO] Reset BDD: {db_status}")
            if 'temp_files_deleted' in last_op:
                print(f"[INFO] Fichiers temp supprimés: {last_op['temp_files_deleted']}")
            if 'folders_cleaned' in last_op:
                print(f"[INFO] Dossiers nettoyés: {last_op['folders_cleaned']}")
        
    else:
        print("[ATTENTION] Fichier reset_history.json non trouvé")
    
    for issue in history_results['issues']:
        print(f"[PROBLEME] {issue}")
    
    # 2. Vérifier le code de la fonction reset_profile
    print("\n2. Validation du code reset_profile()")
    code_results = check_reset_logger_in_code(project_root)
    
    if code_results['has_reset_function']:
        print("[OK] Fonction reset_profile() trouvée")
    else:
        print("[ERREUR] Fonction reset_profile() non trouvée")
    
    if code_results['uses_reset_logger']:
        print("[OK] Utilise reset_logger")
    else:
        print("[ERREUR] N'utilise pas reset_logger")
    
    if code_results['calls_start_operation']:
        print("[OK] Appelle start_reset_operation()")
    else:
        print("[ERREUR] N'appelle pas start_reset_operation()")
    
    if code_results['calls_finish_operation']:
        print("[OK] Appelle finish_reset_operation()")
    else:
        print("[ERREUR] N'appelle pas finish_reset_operation()")
    
    for issue in code_results['issues']:
        print(f"[PROBLEME] {issue}")
    
    # 3. Vérifier le fichier de logs détaillé
    print("\n3. Validation du fichier reset_operations.log")
    reset_logs_file = project_root / "reset_operations.log"
    
    if reset_logs_file.exists():
        print("[OK] Fichier reset_operations.log trouvé")
        file_size = reset_logs_file.stat().st_size
        print(f"[INFO] Taille: {file_size} bytes")
        
        # Lire les dernières lignes pour détecter des opérations récentes
        try:
            with open(reset_logs_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            reset_starts = sum(1 for line in lines if "RESET START" in line)
            reset_ends = sum(1 for line in lines if "RESET END" in line)
            
            print(f"[INFO] Opérations commencées: {reset_starts}")
            print(f"[INFO] Opérations terminées: {reset_ends}")
            
            if reset_starts != reset_ends:
                print("[ATTENTION] Nombre d'opérations commencées ≠ terminées")
                
        except Exception as e:
            print(f"[PROBLEME] Erreur lecture fichier log: {e}")
            
    else:
        print("[ATTENTION] Fichier reset_operations.log non trouvé")
    
    # 4. Résumé final
    print("\n4. RESUME")
    print("-" * 20)
    
    total_issues = len(history_results['issues']) + len(code_results['issues'])
    
    if total_issues == 0:
        print("[EXCELLENT] Système de logging complet et fonctionnel!")
        print("[INFO] La fonction 'réinitialiser' log correctement toutes ses opérations")
        return 0
    else:
        print(f"[ATTENTION] {total_issues} problème(s) détecté(s)")
        print("[CONSEIL] Vérifiez les points mentionnés ci-dessus")
        return 1


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\nValidation interrompue par l'utilisateur")
        sys.exit(1)
    except Exception as e:
        print(f"\nERREUR FATALE: {e}")
        sys.exit(1)