#!/usr/bin/env python3
"""
Test d'intégration du système de logging de réinitialisation
==========================================================

Teste le système ResetLogger de manière isolée sans effectuer
de réinitialisation réelle, pour vérifier que tous les logs
sont correctement générés et persistés.

Usage:
    python scripts/test_reset_logging_integration.py
"""

from __future__ import annotations

import sys
import json
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from app.utils.reset_logger import ResetLogger, ResetOperationMetrics
    from app.logging.safe_logger import get_safe_logger
    from app.config import DEFAULT_PII_CONFIG
except ImportError as e:
    print(f"ERREUR: Impossible d'importer les modules CVMatch: {e}")
    sys.exit(1)

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


def create_mock_reset_operation(test_dir: Path) -> str:
    """Simule une opération de réinitialisation complète avec logging."""
    
    # Créer un ResetLogger de test
    test_logger = ResetLogger(test_dir)
    
    print("Test 1: Démarrage de l'opération de reset...")
    operation_id = test_logger.start_reset_operation()
    print(f"[OK] Opération démarrée: {operation_id}")
    
    # Simuler les différentes étapes de reset avec leurs logs
    print("Test 2: Simulation reset base de données...")
    test_logger.log_database_reset(success=True)
    print("[OK] Reset BDD loggé")
    
    print("Test 3: Simulation nettoyage fichiers temporaires...")
    test_logger.log_temp_files_cleanup(
        targeted=15,
        deleted=12,
        failed=3,
        errors=["Fichier verrouillé: temp.lock", "Permission refusée: protected.tmp", "Fichier introuvable: missing.tmp"]
    )
    print("[OK] Nettoyage fichiers temp loggé")
    
    print("Test 4: Simulation nettoyage dossiers...")
    test_logger.log_folders_cleanup(
        processed=8,
        protected=2,
        cleaned=6,
        items_deleted=45,
        items_protected=8,
        errors=["Dossier verrouillé: locked_folder"]
    )
    print("[OK] Nettoyage dossiers loggé")
    
    print("Test 5: Simulation vérification fichiers de lancement...")
    test_logger.log_launch_files_verification(
        verified=["cvmatch.bat", "cvmatch.sh"],
        recreated=["main.py"]  # Un fichier a dû être recréé
    )
    print("[OK] Vérification fichiers de lancement loggée")
    
    print("Test 6: Simulation nettoyage cache HF...")
    test_logger.log_hf_cache_cleanup(success=True)
    print("[OK] Nettoyage cache HF loggé")
    
    print("Test 7: Finalisation de l'opération...")
    final_metrics = test_logger.finish_reset_operation(
        success=True,
        restart_attempted=True
    )
    print("[OK] Opération finalisée")
    
    return operation_id, final_metrics


def validate_generated_logs(test_dir: Path, operation_id: str) -> Dict[str, bool]:
    """Valide que tous les logs attendus ont été générés."""
    
    results = {
        'history_file_exists': False,
        'log_file_exists': False,
        'operation_in_history': False,
        'complete_metrics': False,
        'correct_structure': False
    }
    
    # 1. Vérifier le fichier d'historique JSON
    history_file = test_dir / "reset_history.json"
    if history_file.exists():
        results['history_file_exists'] = True
        print("[OK] Fichier reset_history.json créé")
        
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                history_data = json.load(f)
            
            # Vérifier la structure
            if 'operations' in history_data and isinstance(history_data['operations'], list):
                results['correct_structure'] = True
                print("[OK] Structure JSON correcte")
                
                # Chercher notre opération
                for operation in history_data['operations']:
                    if operation.get('operation_id') == operation_id:
                        results['operation_in_history'] = True
                        print(f"[OK] Opération {operation_id} trouvée dans l'historique")
                        
                        # Vérifier les métriques complètes
                        expected_fields = [
                            'start_time', 'end_time', 'duration_seconds', 'success',
                            'database_reset', 'temp_files_targeted', 'temp_files_deleted',
                            'folders_processed', 'folders_cleaned', 'items_deleted'
                        ]
                        
                        all_fields_present = all(field in operation for field in expected_fields)
                        if all_fields_present:
                            results['complete_metrics'] = True
                            print("[OK] Toutes les métriques présentes")
                            
                            # Afficher quelques détails
                            print(f"[INFO] Durée: {operation.get('duration_seconds', 0):.2f}s")
                            print(f"[INFO] Fichiers temp: {operation.get('temp_files_deleted', 0)}/{operation.get('temp_files_targeted', 0)}")
                            print(f"[INFO] Dossiers nettoyés: {operation.get('folders_cleaned', 0)}/{operation.get('folders_processed', 0)}")
                            print(f"[INFO] Éléments supprimés: {operation.get('items_deleted', 0)}")
                        else:
                            missing_fields = [f for f in expected_fields if f not in operation]
                            print(f"[ERREUR] Métriques manquantes: {missing_fields}")
                        break
                else:
                    print(f"[ERREUR] Opération {operation_id} non trouvée dans l'historique")
            else:
                print("[ERREUR] Structure JSON incorrecte")
                
        except json.JSONDecodeError:
            print("[ERREUR] Fichier JSON invalide")
        except Exception as e:
            print(f"[ERREUR] Erreur lecture historique: {e}")
    else:
        print("[ERREUR] Fichier reset_history.json non créé")
    
    # 2. Vérifier le fichier de logs détaillé
    log_file = test_dir / "reset_operations.log"
    if log_file.exists():
        results['log_file_exists'] = True
        print("[OK] Fichier reset_operations.log créé")
        
        # Vérifier le contenu du log
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                log_content = f.read()
            
            # Chercher les marqueurs importants
            expected_markers = [
                f"RESET START [{operation_id}]",
                "DATABASE RESET SUCCESS",
                "TEMP FILES:",
                "FOLDERS:",
                "LAUNCH FILES:",
                "HF CACHE CLEANED",
                f"RESET END [{operation_id}]"
            ]
            
            markers_found = 0
            for marker in expected_markers:
                if marker in log_content:
                    markers_found += 1
                else:
                    print(f"[ATTENTION] Marqueur manquant: {marker}")
            
            print(f"[INFO] Marqueurs trouvés: {markers_found}/{len(expected_markers)}")
            
            if markers_found == len(expected_markers):
                print("[OK] Tous les marqueurs de log présents")
            
        except Exception as e:
            print(f"[ERREUR] Erreur lecture fichier log: {e}")
    else:
        print("[ERREUR] Fichier reset_operations.log non créé")
    
    return results


def test_error_handling(test_dir: Path) -> bool:
    """Teste la gestion d'erreur du ResetLogger."""
    
    print("\nTest gestion d'erreur:")
    
    # Attendre pour avoir un ID différent
    import time
    time.sleep(1)
    
    # Créer un nouveau ResetLogger pour le test d'erreur
    error_logger = ResetLogger(test_dir)
    
    print("Test: Démarrage opération avec erreur...")
    error_operation_id = error_logger.start_reset_operation()
    
    print("Test: Simulation erreur de base de données...")
    error_logger.log_database_reset(success=False, error="Connection timeout")
    
    print("Test: Simulation erreur fichiers temporaires...")
    error_logger.log_temp_files_cleanup(
        targeted=5,
        deleted=2,
        failed=3,
        errors=["Fichier verrouillé", "Accès refusé", "Disque plein"]
    )
    
    print("Test: Finalisation avec erreur globale...")
    error_logger.finish_reset_operation(
        success=False,
        restart_attempted=False,
        global_error="Multiple failures during reset operation"
    )
    
    # Vérifier que l'erreur a été correctement loggée
    history_file = test_dir / "reset_history.json"
    if history_file.exists():
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                history_data = json.load(f)
            
            # Chercher l'opération d'erreur
            print(f"[DEBUG] Recherche opération: {error_operation_id}")
            print(f"[DEBUG] {len(history_data['operations'])} opération(s) dans l'historique")
            
            for i, operation in enumerate(history_data['operations']):
                op_id = operation.get('operation_id', 'unknown')
                op_success = operation.get('success', True)
                print(f"[DEBUG] Op {i}: {op_id} - success={op_success}")
                
                if op_id == error_operation_id:
                    if not op_success:
                        print("[OK] Opération marquée comme échouée")
                        if 'global_error' in operation:
                            print(f"[OK] Erreur globale loggée: {operation['global_error'][:50]}...")
                        if operation.get('database_errors'):
                            print(f"[OK] Erreurs BDD loggées: {len(operation['database_errors'])} erreur(s)")
                        return True
                    else:
                        print(f"[ERREUR] Opération marquée comme réussie malgré les erreurs (success={op_success})")
                        return False
            
            print("[ERREUR] Opération d'erreur non trouvée")
            return False
            
        except Exception as e:
            print(f"[ERREUR] Impossible de vérifier l'opération d'erreur: {e}")
            return False
    else:
        print("[ERREUR] Fichier d'historique non trouvé pour le test d'erreur")
        return False


def main():
    """Point d'entrée principal du test d'intégration."""
    
    print("TEST D'INTEGRATION - LOGGING DE REINITIALISATION")
    print("=" * 52)
    
    # Créer un répertoire temporaire pour les tests
    with tempfile.TemporaryDirectory() as temp_dir:
        test_dir = Path(temp_dir)
        print(f"[INFO] Répertoire de test: {test_dir}")
        
        try:
            # Test principal: simulation d'opération complète
            print("\n=== TEST PRINCIPAL ===")
            operation_id, final_metrics = create_mock_reset_operation(test_dir)
            
            # Validation des logs générés
            print("\n=== VALIDATION DES LOGS ===")
            validation_results = validate_generated_logs(test_dir, operation_id)
            
            # Test de gestion d'erreur
            print("\n=== TEST GESTION D'ERREUR ===")
            error_handling_ok = test_error_handling(test_dir)
            
            # Résumé final
            print("\n=== RESUME FINAL ===")
            total_tests = len(validation_results) + 1  # +1 pour le test d'erreur
            passed_tests = sum(1 for result in validation_results.values() if result) + (1 if error_handling_ok else 0)
            
            print(f"Tests réussis: {passed_tests}/{total_tests}")
            
            if passed_tests == total_tests:
                print("[EXCELLENT] Tous les tests passent!")
                print("[INFO] Le système de logging de réinitialisation fonctionne parfaitement")
                print("[INFO] Les logs sont correctement générés et persistés")
                print("[INFO] La gestion d'erreur est opérationnelle")
                return 0
            else:
                print(f"[ATTENTION] {total_tests - passed_tests} test(s) échoué(s)")
                print("[CONSEIL] Vérifiez les erreurs mentionnées ci-dessus")
                return 1
                
        except Exception as e:
            print(f"\n[ERREUR FATALE] Erreur durant les tests: {e}")
            import traceback
            traceback.print_exc()
            return 1


if __name__ == "__main__":
    try:
        exit_code = main()
        print(f"\n[INFO] Test terminé avec code: {exit_code}")
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n[INFO] Test interrompu par l'utilisateur")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERREUR] Erreur fatale: {e}")
        sys.exit(1)