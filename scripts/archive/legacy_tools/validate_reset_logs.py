#!/usr/bin/env python3
"""
Script de validation des logs de réinitialisation
=================================================

Valide que la fonction 'réinitialiser' (reset_profile) génère correctement
tous les logs attendus via le système ResetLogger.

Vérifie:
- La présence du fichier reset_history.json
- La structure des logs de réinitialisation
- La complétude des métriques collectées
- La cohérence des timestamps et durées

Usage:
    python scripts/validate_reset_logs.py [--verbose] [--check-last N]
"""

from __future__ import annotations

import sys
import json
import argparse
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
import traceback

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from app.utils.reset_logger import ResetLogger, ResetOperationMetrics
    from app.logging.safe_logger import get_safe_logger
    from app.config import DEFAULT_PII_CONFIG
except ImportError as e:
    print(f"❌ ERREUR: Impossible d'importer les modules CVMatch: {e}")
    sys.exit(1)

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


class ResetLogValidator:
    """Validateur pour les logs de réinitialisation."""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.reset_history_file = project_root / "reset_history.json"
        self.reset_logs_file = project_root / "reset_operations.log"
        
    def validate_reset_history_structure(self, verbose: bool = False) -> Dict[str, Any]:
        """
        Valide la structure du fichier reset_history.json.
        
        Returns:
            Dict avec les résultats de validation
        """
        results = {
            'file_exists': False,
            'is_valid_json': False,
            'has_operations': False,
            'operations_count': 0,
            'structure_valid': True,
            'errors': []
        }
        
        # Vérifier l'existence du fichier
        if not self.reset_history_file.exists():
            results['errors'].append("Fichier reset_history.json non trouvé")
            return results
        
        results['file_exists'] = True
        
        try:
            # Charger et valider le JSON
            with open(self.reset_history_file, 'r', encoding='utf-8') as f:
                history_data = json.load(f)
            
            results['is_valid_json'] = True
            
            # Vérifier la structure
            if 'operations' not in history_data:
                results['errors'].append("Clé 'operations' manquante dans le JSON")
                results['structure_valid'] = False
                return results
            
            operations = history_data['operations']
            results['operations_count'] = len(operations)
            results['has_operations'] = len(operations) > 0
            
            # Valider chaque opération
            required_fields = [
                'operation_id', 'start_time', 'end_time', 'duration_seconds',
                'success', 'database_reset'
            ]
            
            for i, operation in enumerate(operations):
                for field in required_fields:
                    if field not in operation:
                        results['errors'].append(f"Opération {i}: champ '{field}' manquant")
                        results['structure_valid'] = False
                
                # Valider les timestamps
                try:
                    datetime.fromisoformat(operation.get('start_time', ''))
                except ValueError:
                    results['errors'].append(f"Opération {i}: start_time invalide")
                    results['structure_valid'] = False
                
                if operation.get('end_time'):
                    try:
                        datetime.fromisoformat(operation['end_time'])
                    except ValueError:
                        results['errors'].append(f"Opération {i}: end_time invalide")
                        results['structure_valid'] = False
            
            if verbose and results['has_operations']:
                print(f"📊 Trouvé {results['operations_count']} opération(s) de reset")
                
        except json.JSONDecodeError as e:
            results['errors'].append(f"JSON invalide: {e}")
            results['is_valid_json'] = False
            results['structure_valid'] = False
        except Exception as e:
            results['errors'].append(f"Erreur lors de la validation: {e}")
            results['structure_valid'] = False
            
        return results
    
    def analyze_last_operations(self, count: int = 5, verbose: bool = False) -> Dict[str, Any]:
        """
        Analyse les N dernières opérations de reset.
        
        Args:
            count: Nombre d'opérations à analyser
            verbose: Affichage détaillé
            
        Returns:
            Analyse détaillée des opérations
        """
        analysis = {
            'operations_analyzed': 0,
            'successful_operations': 0,
            'failed_operations': 0,
            'average_duration': 0.0,
            'database_resets': 0,
            'temp_files_cleaned': 0,
            'folders_cleaned': 0,
            'issues_found': [],
            'operations_details': []
        }
        
        if not self.reset_history_file.exists():
            analysis['issues_found'].append("Fichier reset_history.json non trouvé")
            return analysis
        
        try:
            with open(self.reset_history_file, 'r', encoding='utf-8') as f:
                history_data = json.load(f)
            
            operations = history_data.get('operations', [])
            
            # Prendre les N dernières opérations
            recent_operations = operations[-count:] if len(operations) >= count else operations
            analysis['operations_analyzed'] = len(recent_operations)
            
            total_duration = 0
            
            for operation in recent_operations:
                # Métriques basiques
                if operation.get('success', False):
                    analysis['successful_operations'] += 1
                else:
                    analysis['failed_operations'] += 1
                
                if operation.get('database_reset', False):
                    analysis['database_resets'] += 1
                
                # Durée
                duration = operation.get('duration_seconds', 0)
                total_duration += duration
                
                # Fichiers temporaires
                temp_deleted = operation.get('temp_files_deleted', 0)
                analysis['temp_files_cleaned'] += temp_deleted
                
                # Dossiers
                folders_cleaned = operation.get('folders_cleaned', 0)
                analysis['folders_cleaned'] += folders_cleaned
                
                # Détails pour verbose
                if verbose:
                    operation_detail = {
                        'id': operation.get('operation_id', 'unknown'),
                        'success': operation.get('success', False),
                        'duration': duration,
                        'database_reset': operation.get('database_reset', False),
                        'temp_files': temp_deleted,
                        'folders': folders_cleaned,
                        'errors': []
                    }
                    
                    # Collecter les erreurs
                    for error_field in ['database_errors', 'temp_files_errors', 
                                       'folder_errors', 'global_error']:
                        errors = operation.get(error_field)
                        if errors:
                            if isinstance(errors, list):
                                operation_detail['errors'].extend(errors)
                            else:
                                operation_detail['errors'].append(str(errors))
                    
                    analysis['operations_details'].append(operation_detail)
                
                # Validation des données
                if not operation.get('start_time'):
                    analysis['issues_found'].append(f"Opération {operation.get('operation_id', 'unknown')}: start_time manquant")
                
                if duration <= 0:
                    analysis['issues_found'].append(f"Opération {operation.get('operation_id', 'unknown')}: durée invalide ({duration}s)")
            
            # Calculer la durée moyenne
            if analysis['operations_analyzed'] > 0:
                analysis['average_duration'] = total_duration / analysis['operations_analyzed']
                
        except Exception as e:
            analysis['issues_found'].append(f"Erreur lors de l'analyse: {e}")
        
        return analysis
    
    def check_reset_logs_file(self, verbose: bool = False) -> Dict[str, Any]:
        """
        Vérifie le fichier de logs détaillé reset_operations.log.
        
        Returns:
            Résultats de la vérification
        """
        results = {
            'file_exists': False,
            'file_size_bytes': 0,
            'last_modified': None,
            'recent_entries': [],
            'reset_operations_found': 0,
            'success_operations': 0,
            'failed_operations': 0
        }
        
        if not self.reset_logs_file.exists():
            results['issues'] = ["Fichier reset_operations.log non trouvé"]
            return results
        
        results['file_exists'] = True
        results['file_size_bytes'] = self.reset_logs_file.stat().st_size
        results['last_modified'] = datetime.fromtimestamp(
            self.reset_logs_file.stat().st_mtime
        ).isoformat()
        
        try:
            # Lire les dernières lignes du fichier de log
            with open(self.reset_logs_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # Analyser les dernières entrées
            recent_lines = lines[-50:] if len(lines) > 50 else lines
            results['recent_entries'] = [line.strip() for line in recent_lines]
            
            # Compter les opérations de reset
            for line in lines:
                if "RESET START" in line:
                    results['reset_operations_found'] += 1
                elif "RESET END" in line and "✅" in line:
                    results['success_operations'] += 1
                elif "RESET END" in line and "❌" in line:
                    results['failed_operations'] += 1
                    
        except Exception as e:
            results['issues'] = [f"Erreur lors de la lecture du fichier de log: {e}"]
            
        return results
    
    def validate_reset_profile_function(self) -> Dict[str, Any]:
        """
        Vérifie que la fonction reset_profile() utilise correctement ResetLogger.
        
        Returns:
            Résultats de la validation du code
        """
        results = {
            'function_found': False,
            'uses_reset_logger': False,
            'calls_start_operation': False,
            'calls_finish_operation': False,
            'logs_database_reset': False,
            'logs_temp_cleanup': False,
            'logs_folders_cleanup': False,
            'issues': []
        }
        
        settings_dialog_path = self.project_root / "app" / "views" / "settings_dialog.py"
        
        if not settings_dialog_path.exists():
            results['issues'].append("Fichier settings_dialog.py non trouvé")
            return results
        
        try:
            with open(settings_dialog_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Vérifications basiques
            if "def reset_profile(" in content:
                results['function_found'] = True
            else:
                results['issues'].append("Fonction reset_profile() non trouvée")
                return results
            
            # Vérifications d'usage du ResetLogger
            if "ResetLogger" in content:
                results['uses_reset_logger'] = True
            else:
                results['issues'].append("ResetLogger non importé ou utilisé")
            
            if "start_reset_operation" in content:
                results['calls_start_operation'] = True
            else:
                results['issues'].append("start_reset_operation() non appelé")
            
            if "finish_reset_operation" in content:
                results['calls_finish_operation'] = True
            else:
                results['issues'].append("finish_reset_operation() non appelé")
            
            if "log_database_reset" in content:
                results['logs_database_reset'] = True
            else:
                results['issues'].append("log_database_reset() non appelé")
            
            if "log_temp_files_cleanup" in content:
                results['logs_temp_cleanup'] = True
            else:
                results['issues'].append("log_temp_files_cleanup() non appelé")
            
            if "log_folders_cleanup" in content:
                results['logs_folders_cleanup'] = True
            else:
                results['issues'].append("log_folders_cleanup() non appelé")
                
        except Exception as e:
            results['issues'].append(f"Erreur lors de l'analyse du code: {e}")
            
        return results


def main():
    """Point d'entrée principal."""
    parser = argparse.ArgumentParser(description="Validation des logs de réinitialisation")
    parser.add_argument('--verbose', '-v', action='store_true', 
                       help="Affichage détaillé")
    parser.add_argument('--check-last', '-n', type=int, default=5,
                       help="Nombre d'opérations récentes à analyser (défaut: 5)")
    
    args = parser.parse_args()
    
    # Initialiser le validateur
    validator = ResetLogValidator(project_root)
    
    print("VALIDATION DES LOGS DE REINITIALISATION")
    print("=" * 50)
    
    # 1. Valider la structure du fichier d'historique
    print("\n1. Validation structure reset_history.json")
    history_results = validator.validate_reset_history_structure(args.verbose)
    
    if history_results['file_exists']:
        print(f"[OK] Fichier trouvé: {validator.reset_history_file}")
    else:
        print(f"[ERREUR] Fichier manquant: {validator.reset_history_file}")
    
    if history_results['is_valid_json']:
        print("[OK] JSON valide")
    else:
        print("[ERREUR] JSON invalide")
    
    if history_results['structure_valid']:
        print("[OK] Structure valide")
    else:
        print("[ERREUR] Structure invalide")
    
    if history_results['has_operations']:
        print(f"[OK] {history_results['operations_count']} opération(s) trouvée(s)")
    else:
        print("[ATTENTION] Aucune opération trouvée")
    
    if history_results['errors']:
        print("[ERREURS] Erreurs détectées:")
        for error in history_results['errors']:
            print(f"   - {error}")
    
    # 2. Analyser les dernières opérations
    print(f"\n📊 2. Analyse des {args.check_last} dernières opérations")
    analysis = validator.analyze_last_operations(args.check_last, args.verbose)
    
    print(f"📈 Opérations analysées: {analysis['operations_analyzed']}")
    print(f"✅ Succès: {analysis['successful_operations']}")
    print(f"❌ Échecs: {analysis['failed_operations']}")
    print(f"⏱️ Durée moyenne: {analysis['average_duration']:.1f}s")
    print(f"🗄️ Resets BDD: {analysis['database_resets']}")
    print(f"📂 Fichiers temp nettoyés: {analysis['temp_files_cleaned']}")
    print(f"📁 Dossiers nettoyés: {analysis['folders_cleaned']}")
    
    if analysis['issues_found']:
        print("🚨 Problèmes détectés:")
        for issue in analysis['issues_found']:
            print(f"   • {issue}")
    
    if args.verbose and analysis['operations_details']:
        print("\n🔍 Détails des opérations:")
        for detail in analysis['operations_details']:
            print(f"   • {detail['id']}: {'✅' if detail['success'] else '❌'} "
                  f"({detail['duration']:.1f}s)")
            if detail['errors']:
                for error in detail['errors']:
                    print(f"     ⚠️ {error}")
    
    # 3. Vérifier le fichier de logs détaillé
    print(f"\n📝 3. Vérification reset_operations.log")
    logs_results = validator.check_reset_logs_file(args.verbose)
    
    if logs_results['file_exists']:
        print(f"✅ Fichier trouvé: {validator.reset_logs_file}")
        print(f"📊 Taille: {logs_results['file_size_bytes']} bytes")
        print(f"📅 Dernière modification: {logs_results['last_modified']}")
        print(f"🔄 Opérations reset détectées: {logs_results['reset_operations_found']}")
        print(f"✅ Succès: {logs_results['success_operations']}")
        print(f"❌ Échecs: {logs_results['failed_operations']}")
    else:
        print(f"❌ Fichier manquant: {validator.reset_logs_file}")
    
    # 4. Valider la fonction reset_profile()
    print(f"\n🔧 4. Validation fonction reset_profile()")
    code_results = validator.validate_reset_profile_function()
    
    if code_results['function_found']:
        print("✅ Fonction reset_profile() trouvée")
    else:
        print("❌ Fonction reset_profile() non trouvée")
    
    if code_results['uses_reset_logger']:
        print("✅ Utilise ResetLogger")
    else:
        print("❌ N'utilise pas ResetLogger")
    
    checks = [
        ('calls_start_operation', 'Appelle start_reset_operation()'),
        ('calls_finish_operation', 'Appelle finish_reset_operation()'),
        ('logs_database_reset', 'Log reset base de données'),
        ('logs_temp_cleanup', 'Log nettoyage fichiers temporaires'),
        ('logs_folders_cleanup', 'Log nettoyage dossiers')
    ]
    
    for check_key, description in checks:
        if code_results[check_key]:
            print(f"✅ {description}")
        else:
            print(f"❌ {description}")
    
    if code_results['issues']:
        print("🚨 Problèmes dans le code:")
        for issue in code_results['issues']:
            print(f"   • {issue}")
    
    # 5. Résumé final
    print(f"\n📋 RÉSUMÉ FINAL")
    print("=" * 30)
    
    total_checks = 0
    passed_checks = 0
    
    # Compter les vérifications
    basic_checks = [
        history_results['file_exists'],
        history_results['is_valid_json'],
        history_results['structure_valid'],
        logs_results['file_exists'],
        code_results['function_found'],
        code_results['uses_reset_logger'],
        code_results['calls_start_operation'],
        code_results['calls_finish_operation']
    ]
    
    total_checks = len(basic_checks)
    passed_checks = sum(1 for check in basic_checks if check)
    
    print(f"✅ Tests réussis: {passed_checks}/{total_checks}")
    
    if analysis['operations_analyzed'] > 0:
        success_rate = (analysis['successful_operations'] / analysis['operations_analyzed']) * 100
        print(f"📊 Taux de succès des resets: {success_rate:.1f}%")
    
    # Recommandations
    all_issues = (history_results.get('errors', []) + 
                 analysis.get('issues_found', []) + 
                 code_results.get('issues', []))
    
    if all_issues:
        print(f"\n💡 RECOMMANDATIONS:")
        for issue in all_issues[:5]:  # Limiter à 5 recommendations
            print(f"   • Corriger: {issue}")
        
        if len(all_issues) > 5:
            print(f"   • ... et {len(all_issues) - 5} autre(s) problème(s)")
    else:
        print(f"\n🎉 EXCELLENT: Système de logging de réinitialisation complet et fonctionnel!")
    
    # Code de sortie
    return 0 if passed_checks == total_checks and not all_issues else 1


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⏹️ Validation interrompue par l'utilisateur")
        sys.exit(1)
    except Exception as e:
        print(f"\nERREUR FATALE: {e}")
        print(traceback.format_exc())
        sys.exit(1)