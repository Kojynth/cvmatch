"""
Utilitaires pour sauvegarde/chargement/diff de snapshots debug
============================================================

Fonctions pour gérer les snapshots de debug avec comparaison entre runs.
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime
import logging
from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


def save_snapshot(snapshot: Dict[str, Any], path: Path) -> bool:
    """Sauvegarde un snapshot debug en JSON.
    
    Args:
        snapshot: Dict contenant le snapshot debug
        path: Chemin de sauvegarde (avec extension .json)
        
    Returns:
        True si succès, False sinon
    """
    try:
        # Assurer que le répertoire parent existe
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Ajouter métadonnées de sauvegarde
        snapshot_with_meta = {
            **snapshot,
            "save_metadata": {
                "saved_at": datetime.now().isoformat(),
                "saved_path": str(path),
                "version": "1.0"
            }
        }
        
        # Écrire le fichier JSON
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(snapshot_with_meta, f, indent=2, ensure_ascii=False)
        
        logger.info(f"SNAPDBG: exported path={path}")
        return True
        
    except Exception as e:
        logger.error(f"SNAPDBG: save failed path={path} error={e}")
        return False


def load_snapshot(path: Path) -> Optional[Dict[str, Any]]:
    """Charge un snapshot debug depuis un fichier JSON.
    
    Args:
        path: Chemin du fichier snapshot
        
    Returns:
        Dict contenant le snapshot, ou None si erreur
    """
    try:
        if not path.exists():
            logger.warning(f"SNAPDBG: load failed - file not found: {path}")
            return None
        
        with open(path, 'r', encoding='utf-8') as f:
            snapshot = json.load(f)
        
        logger.info(f"SNAPDBG: loaded path={path}")
        return snapshot
        
    except Exception as e:
        logger.error(f"SNAPDBG: load failed path={path} error={e}")
        return None


def diff_snapshots(snapshot_a: Dict[str, Any], snapshot_b: Dict[str, Any]) -> Dict[str, Any]:
    """Compare deux snapshots et retourne les différences.
    
    Args:
        snapshot_a: Premier snapshot (baseline)
        snapshot_b: Deuxième snapshot (comparaison)
        
    Returns:
        Dict contenant les statistiques de différence
    """
    try:
        # Extraire les assignments de chaque snapshot
        assignments_a = snapshot_a.get('line_assignments', {})
        assignments_b = snapshot_b.get('line_assignments', {})
        
        # Convertir les clés en int si elles sont en string (JSON)
        if assignments_a and isinstance(list(assignments_a.keys())[0], str):
            assignments_a = {int(k): v for k, v in assignments_a.items()}
        if assignments_b and isinstance(list(assignments_b.keys())[0], str):
            assignments_b = {int(k): v for k, v in assignments_b.items()}
        
        # Trouver les lignes reclassées
        changed_indices = []
        reassigned_count = 0
        
        # Union de tous les indices de lignes
        all_indices = set(assignments_a.keys()) | set(assignments_b.keys())
        
        for line_idx in all_indices:
            section_a = assignments_a.get(line_idx)
            section_b = assignments_b.get(line_idx)
            
            if section_a != section_b:
                changed_indices.append(line_idx)
                reassigned_count += 1
        
        # Compter les changements par section
        by_section = {}
        for line_idx in changed_indices:
            section_a = assignments_a.get(line_idx, 'unassigned')
            section_b = assignments_b.get(line_idx, 'unassigned')
            
            # Décompte pour section A (perte)
            if section_a and section_a != 'unassigned':
                if section_a not in by_section:
                    by_section[section_a] = 0
                by_section[section_a] -= 1
            
            # Décompte pour section B (gain)
            if section_b and section_b != 'unassigned':
                if section_b not in by_section:
                    by_section[section_b] = 0
                by_section[section_b] += 1
        
        # Analyser les changements ML
        ml_a = snapshot_a.get('ml', {})
        ml_b = snapshot_b.get('ml', {})
        
        ner_diff = _compare_ner_counts(
            ml_a.get('ner_counts', {}),
            ml_b.get('ner_counts', {})
        )
        
        # Métadonnées de comparaison
        meta_a = snapshot_a.get('timestamp', 'unknown')
        meta_b = snapshot_b.get('timestamp', 'unknown')
        
        # Construire le résultat
        diff_result = {
            "reassigned_lines": reassigned_count,
            "by_section": by_section,
            "changed_indices": sorted(changed_indices),
            "ml_changes": {
                "ner_diff": ner_diff
            },
            "metadata": {
                "snapshot_a_timestamp": meta_a,
                "snapshot_b_timestamp": meta_b,
                "diff_timestamp": datetime.now().isoformat(),
                "total_lines_a": len(snapshot_a.get('lines', [])),
                "total_lines_b": len(snapshot_b.get('lines', []))
            }
        }
        
        logger.info(f"SNAPDBG: diff | reassigned={reassigned_count} sections_affected={len(by_section)}")
        
        return diff_result
        
    except Exception as e:
        logger.error(f"SNAPDBG: diff failed error={e}")
        return {
            "reassigned_lines": 0,
            "by_section": {},
            "changed_indices": [],
            "ml_changes": {"ner_diff": {}},
            "metadata": {
                "error": str(e),
                "diff_timestamp": datetime.now().isoformat()
            }
        }


def _compare_ner_counts(ner_a: Dict[str, int], ner_b: Dict[str, int]) -> Dict[str, int]:
    """Compare les compteurs d'entités NER entre deux snapshots.
    
    Args:
        ner_a: Compteurs NER du snapshot A
        ner_b: Compteurs NER du snapshot B
        
    Returns:
        Dict des différences par type d'entité
    """
    diff = {}
    
    # Union de tous les types d'entités
    all_entities = set(ner_a.keys()) | set(ner_b.keys())
    
    for entity_type in all_entities:
        count_a = ner_a.get(entity_type, 0)
        count_b = ner_b.get(entity_type, 0)
        
        if count_a != count_b:
            diff[entity_type] = count_b - count_a
    
    return diff


def format_diff_summary(diff_result: Dict[str, Any]) -> str:
    """Formate un résumé textuel des différences pour l'UI.
    
    Args:
        diff_result: Résultat de diff_snapshots()
        
    Returns:
        String formatée pour affichage
    """
    try:
        reassigned = diff_result.get('reassigned_lines', 0)
        by_section = diff_result.get('by_section', {})
        changed_indices = diff_result.get('changed_indices', [])
        
        lines = []
        
        # Résumé global
        lines.append(f"📊 Lignes reclassées: {reassigned}")
        
        if by_section:
            lines.append("📋 Changements par section:")
            for section, change in sorted(by_section.items()):
                sign = "+" if change > 0 else ""
                lines.append(f"  • {section}: {sign}{change}")
        
        # Top changements
        if changed_indices:
            preview_indices = changed_indices[:10]  # Top 10
            lines.append(f"🔄 Lignes affectées: {', '.join(map(str, preview_indices))}")
            if len(changed_indices) > 10:
                lines.append(f"   ... et {len(changed_indices) - 10} autres")
        
        # Changements ML
        ml_changes = diff_result.get('ml_changes', {})
        ner_diff = ml_changes.get('ner_diff', {})
        if ner_diff:
            lines.append("🤖 Entités NER:")
            for entity, change in sorted(ner_diff.items()):
                sign = "+" if change > 0 else ""
                lines.append(f"  • {entity}: {sign}{change}")
        
        return "\n".join(lines)
        
    except Exception as e:
        return f"Erreur formatage: {e}"


def get_snapshot_stats(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """Calcule les statistiques d'un snapshot pour affichage.
    
    Args:
        snapshot: Le snapshot à analyser
        
    Returns:
        Dict contenant les statistiques
    """
    try:
        lines = snapshot.get('lines', [])
        assignments = snapshot.get('line_assignments', {})
        consumed = snapshot.get('consumed_lines', [])
        ml = snapshot.get('ml', {})
        
        # Compter les sections assignées
        section_counts = {}
        for section in assignments.values():
            if section:
                section_counts[section] = section_counts.get(section, 0) + 1
        
        # Analyser les phases
        phase = snapshot.get('phase', {})
        core_lines = len(phase.get('core', []))
        secondary_lines = len(phase.get('secondary', []))
        
        # Stats ML
        zs_classifications = len(ml.get('zs_top', []))
        ner_entities = sum(ml.get('ner_counts', {}).values())
        
        return {
            "total_lines": len(lines),
            "assigned_lines": len(assignments),
            "consumed_lines": len(consumed),
            "section_counts": section_counts,
            "phase_distribution": {
                "core": core_lines,
                "secondary": secondary_lines
            },
            "ml_stats": {
                "zero_shot_classifications": zs_classifications,
                "ner_entities": ner_entities
            },
            "timestamp": snapshot.get('timestamp', 'unknown')
        }
        
    except Exception as e:
        logger.error(f"SNAPDBG: stats failed error={e}")
        return {
            "total_lines": 0,
            "assigned_lines": 0,
            "consumed_lines": 0,
            "section_counts": {},
            "phase_distribution": {"core": 0, "secondary": 0},
            "ml_stats": {"zero_shot_classifications": 0, "ner_entities": 0},
            "timestamp": "unknown",
            "error": str(e)
        }
