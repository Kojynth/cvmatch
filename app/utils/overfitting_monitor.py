"""
Moniteur d'overfitting pour l'extraction CV.
Détecte et prévient l'overfitting en surveillant les métriques d'extraction.
"""

import json
import math
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from loguru import logger
import numpy as np


@dataclass
class ExtractionMetrics:
    """Métriques d'une extraction individuelle."""
    cv_id: str
    extraction_timestamp: datetime
    
    # Métriques de contenu
    total_text_blocks: int
    experiences_extracted: int
    education_extracted: int
    skills_extracted: int
    
    # Métriques de qualité
    avg_confidence: float
    low_confidence_ratio: float  # % d'éléments avec confiance < 0.5
    empty_fields_ratio: float    # % de champs requis vides
    
    # Métriques de complexité/overfitting
    extraction_complexity: float  # Score complexité (0-1)
    pattern_diversity: float      # Diversité des patterns utilisés (0-1)
    geometric_coherence: float    # Cohérence géométrique (0-1)
    
    # Métriques temporelles
    extraction_time_ms: float
    
    # Flags de suspicion
    is_suspicious: bool = False
    suspicion_reasons: List[str] = None


@dataclass
class OverfittingAlerts:
    """Alertes d'overfitting."""
    alert_level: str  # 'low', 'medium', 'high', 'critical'
    message: str
    metric_name: str
    current_value: float
    threshold_value: float
    recommendations: List[str]


class OverfittingMonitor:
    """
    Moniteur d'overfitting pour l'extraction CV.
    
    Surveille en continu les métriques d'extraction et détecte:
    - Surconfiance anormale
    - Patterns d'extraction trop rigides  
    - Dégradation de la généralisation
    - Mémorisation excessive de layouts spécifiques
    """
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or self._default_config()
        self.metrics_history: List[ExtractionMetrics] = []
        self.baseline_stats: Dict[str, float] = {}
        self.pattern_usage_history: Dict[str, List[float]] = defaultdict(list)
        self.alerts_history: List[OverfittingAlerts] = []
        
        logger.info("🔍 Moniteur d'overfitting initialisé")
    
    def _default_config(self) -> Dict:
        """Configuration par défaut des seuils anti-overfitting."""
        return {
            # Seuils de confiance
            "confidence_thresholds": {
                "suspicious_high": 0.95,      # Confiance anormalement élevée
                "suspicious_variance": 0.05,   # Variance trop faible
                "min_healthy": 0.60,          # Confiance minimale saine
                "max_healthy": 0.85           # Confiance maximale saine
            },
            
            # Seuils de complexité
            "complexity_thresholds": {
                "max_extraction_complexity": 0.80,  # Extraction trop complexe
                "min_pattern_diversity": 0.30,      # Patterns trop uniformes
                "min_geometric_coherence": 0.40     # Géométrie incohérente
            },
            
            # Seuils de performance
            "performance_thresholds": {
                "max_extraction_time_ms": 5000,     # Temps trop long
                "max_empty_fields_ratio": 0.40,     # Trop de champs vides
                "min_valid_extractions": 0.70       # Trop d'échecs
            },
            
            # Fenêtres temporelles pour analyse de tendance
            "analysis_windows": {
                "short_term_samples": 10,    # Dernières 10 extractions
                "medium_term_samples": 50,   # Dernières 50 extractions
                "long_term_samples": 200     # Dernières 200 extractions
            },
            
            # Seuils d'alerte
            "alert_thresholds": {
                "pattern_overuse": 0.80,     # Pattern utilisé > 80% du temps
                "confidence_monotony": 0.90, # Confiance trop uniforme
                "extraction_drift": 0.15     # Dérive > 15% par rapport baseline
            }
        }
    
    def record_extraction(self, extraction_data: Dict[str, Any], 
                         extraction_time_ms: float, 
                         cv_metadata: Dict[str, Any] = None) -> ExtractionMetrics:
        """
        Enregistre les métriques d'une extraction et analyse l'overfitting.
        """
        cv_id = cv_metadata.get('cv_id', f"cv_{len(self.metrics_history)}")
        
        # Calculer les métriques
        metrics = self._compute_metrics(extraction_data, extraction_time_ms, cv_id)
        
        # Analyser l'overfitting
        alerts = self._analyze_overfitting(metrics)
        
        # Enregistrer l'historique
        self.metrics_history.append(metrics)
        self.alerts_history.extend(alerts)
        
        # Logger les résultats
        self._log_metrics_and_alerts(metrics, alerts)
        
        # Maintenir la taille de l'historique
        self._trim_history()
        
        return metrics
    
    def _compute_metrics(self, extraction_data: Dict[str, Any], 
                        extraction_time_ms: float, 
                        cv_id: str) -> ExtractionMetrics:
        """Calcule les métriques d'extraction."""
        
        # Métriques de base
        experiences = extraction_data.get('experiences', [])
        education = extraction_data.get('education', [])
        skills = extraction_data.get('skills', [])
        
        total_items = len(experiences) + len(education) + len(skills)
        
        # Calculer la confiance moyenne
        all_confidences = []
        all_items = experiences + education + skills
        
        for item in all_items:
            if isinstance(item, dict):
                conf = item.get('confidence', 0.5)
                if isinstance(conf, str):
                    # Mapper les niveaux textuels vers des scores
                    conf_map = {'high': 0.8, 'medium': 0.5, 'low': 0.2, 'unknown': 0.1}
                    conf = conf_map.get(conf.lower(), 0.5)
                all_confidences.append(conf)
        
        avg_confidence = np.mean(all_confidences) if all_confidences else 0.0
        low_confidence_ratio = sum(1 for c in all_confidences if c < 0.5) / len(all_confidences) if all_confidences else 0.0
        
        # Calculer le ratio de champs vides
        empty_fields_count = 0
        total_fields_count = 0
        
        for item in all_items:
            if isinstance(item, dict):
                for key, value in item.items():
                    if key in ['title', 'company', 'degree', 'institution', 'name']:  # Champs critiques
                        total_fields_count += 1
                        if not value or (isinstance(value, str) and value.strip() == ''):
                            empty_fields_count += 1
        
        empty_fields_ratio = empty_fields_count / total_fields_count if total_fields_count > 0 else 0.0
        
        # Métriques de complexité (simplifiées pour l'instant)
        extraction_complexity = self._estimate_complexity(extraction_data)
        pattern_diversity = self._estimate_pattern_diversity(extraction_data)
        geometric_coherence = self._estimate_geometric_coherence(extraction_data)
        
        return ExtractionMetrics(
            cv_id=cv_id,
            extraction_timestamp=datetime.now(),
            total_text_blocks=extraction_data.get('metadata', {}).get('text_blocks_count', 0),
            experiences_extracted=len(experiences),
            education_extracted=len(education),
            skills_extracted=len(skills),
            avg_confidence=avg_confidence,
            low_confidence_ratio=low_confidence_ratio,
            empty_fields_ratio=empty_fields_ratio,
            extraction_complexity=extraction_complexity,
            pattern_diversity=pattern_diversity,
            geometric_coherence=geometric_coherence,
            extraction_time_ms=extraction_time_ms
        )
    
    def _estimate_complexity(self, extraction_data: Dict[str, Any]) -> float:
        """Estime la complexité de l'extraction (0-1)."""
        # Complexité basée sur le nombre d'éléments extraits et leur diversité
        total_elements = 0
        unique_patterns = set()
        
        for section_name, section_data in extraction_data.items():
            if isinstance(section_data, list):
                total_elements += len(section_data)
                for item in section_data:
                    if isinstance(item, dict):
                        # Utiliser la méthode d'extraction comme proxy de pattern
                        extraction_method = item.get('extraction_method', 'unknown')
                        unique_patterns.add(extraction_method)
        
        # Normaliser la complexité
        element_complexity = min(total_elements / 20.0, 1.0)  # 20+ éléments = complexité max
        pattern_complexity = min(len(unique_patterns) / 10.0, 1.0)  # 10+ patterns = complexité max
        
        return (element_complexity + pattern_complexity) / 2.0
    
    def _estimate_pattern_diversity(self, extraction_data: Dict[str, Any]) -> float:
        """Estime la diversité des patterns utilisés (0-1)."""
        pattern_counter = Counter()
        total_extractions = 0
        
        for section_name, section_data in extraction_data.items():
            if isinstance(section_data, list):
                for item in section_data:
                    if isinstance(item, dict):
                        method = item.get('extraction_method', 'unknown')
                        pattern_counter[method] += 1
                        total_extractions += 1
        
        if total_extractions == 0:
            return 0.0
        
        # Calculer l'entropie de Shannon pour mesurer la diversité
        entropy = 0.0
        for count in pattern_counter.values():
            p = count / total_extractions
            if p > 0:
                entropy -= p * math.log2(p)
        
        # Normaliser par l'entropie maximale possible
        max_entropy = math.log2(len(pattern_counter)) if len(pattern_counter) > 1 else 1.0
        normalized_entropy = entropy / max_entropy if max_entropy > 0 else 0.0
        
        return normalized_entropy
        
    def enforce_pattern_diversity_gate(self, pattern_diversity: float, 
                                     date_hit_count: int = 0) -> Dict[str, Any]:
        """
        Enforce pattern diversity as a hard gate (new requirement).
        
        Args:
            pattern_diversity: Current pattern diversity score (0-1)
            date_hit_count: Number of date hits found for merge calculation
            
        Returns:
            Dict with enforcement decision and parameters
        """
        from ..config import EXPERIENCE_CONF
        
        medium_threshold = EXPERIENCE_CONF.get("pattern_diversity_medium_alert", 0.30)
        hard_threshold = EXPERIENCE_CONF.get("pattern_diversity_hard_block", 0.20)
        enforce_flag = EXPERIENCE_CONF.get("pattern_diversity_enforce", False)
        max_merge_multiplier = EXPERIENCE_CONF.get("max_merge_expansions_multiplier", 2)
        
        enforcement_result = {
            'diversity_score': pattern_diversity,
            'medium_threshold': medium_threshold,
            'hard_threshold': hard_threshold,
            'enforcement_enabled': enforce_flag,
            'action': 'allow',
            'max_merges_allowed': None,
            'alert_level': None,
            'message': ''
        }
        
        if not enforce_flag:
            enforcement_result['action'] = 'allow_no_enforcement'
            enforcement_result['message'] = 'Pattern diversity enforcement disabled'
            return enforcement_result
        
        if pattern_diversity < hard_threshold:
            # HARD BLOCK - only accept date-anchored tri-signal items
            enforcement_result['action'] = 'hard_block'
            enforcement_result['alert_level'] = 'critical'
            enforcement_result['max_merges_allowed'] = 0
            enforcement_result['message'] = (f'HARD BLOCK: pattern diversity {pattern_diversity:.3f} < '
                                           f'threshold {hard_threshold:.3f}. Only date-anchored tri-signal items allowed.')
            
            logger.critical(f"PATTERN_DIVERSITY_GATE: hard_block | diversity={pattern_diversity:.3f} "
                          f"threshold={hard_threshold:.3f}")
                          
        elif pattern_diversity < medium_threshold:
            # MEDIUM alert - cap merges and warn
            max_merges = max_merge_multiplier * date_hit_count
            enforcement_result['action'] = 'cap_merges'
            enforcement_result['alert_level'] = 'medium'
            enforcement_result['max_merges_allowed'] = max_merges
            enforcement_result['message'] = (f'MEDIUM ALERT: pattern diversity {pattern_diversity:.3f} < '
                                           f'threshold {medium_threshold:.3f}. Capping merges to {max_merges}.')
            
            logger.warning(f"PATTERN_DIVERSITY_GATE: cap_merges | diversity={pattern_diversity:.3f} "
                         f"threshold={medium_threshold:.3f} max_merges={max_merges} "
                         f"date_hits={date_hit_count}")
        else:
            enforcement_result['action'] = 'allow'
            enforcement_result['message'] = f'Pattern diversity {pattern_diversity:.3f} above thresholds'
            
        return enforcement_result
    
    def _estimate_geometric_coherence(self, extraction_data: Dict[str, Any]) -> float:
        """Estime la cohérence géométrique des extractions (0-1)."""
        # Simplification : utiliser la présence de coordonnées spatiales
        total_items = 0
        items_with_coords = 0
        
        for section_name, section_data in extraction_data.items():
            if isinstance(section_data, list):
                for item in section_data:
                    if isinstance(item, dict):
                        total_items += 1
                        if any(key in item for key in ['span_start', 'span_end', 'bbox', 'source_lines']):
                            items_with_coords += 1
        
        return items_with_coords / total_items if total_items > 0 else 0.0
    
    def _analyze_overfitting(self, current_metrics: ExtractionMetrics) -> List[OverfittingAlerts]:
        """Analyse les signes d'overfitting et génère des alertes."""
        alerts = []
        
        # Analyser la confiance anormalement élevée
        alerts.extend(self._check_confidence_anomalies(current_metrics))
        
        # Analyser la diversité des patterns
        alerts.extend(self._check_pattern_diversity(current_metrics))
        
        # Analyser les tendances temporelles
        alerts.extend(self._check_temporal_trends(current_metrics))
        
        # Analyser la performance
        alerts.extend(self._check_performance_anomalies(current_metrics))
        
        return alerts
    
    def _check_confidence_anomalies(self, metrics: ExtractionMetrics) -> List[OverfittingAlerts]:
        """Vérifie les anomalies de confiance."""
        alerts = []
        conf_thresholds = self.config['confidence_thresholds']
        
        # Confiance anormalement élevée
        if metrics.avg_confidence > conf_thresholds['suspicious_high']:
            alerts.append(OverfittingAlerts(
                alert_level='medium',
                message='Confiance anormalement élevée détectée',
                metric_name='avg_confidence',
                current_value=metrics.avg_confidence,
                threshold_value=conf_thresholds['suspicious_high'],
                recommendations=[
                    'Vérifier la diversité des CV testés',
                    'Examiner les patterns d\'extraction trop spécifiques',
                    'Augmenter la complexité des cas de test'
                ]
            ))
        
        # Analyser la variance de confiance sur les dernières extractions
        if len(self.metrics_history) >= 5:
            recent_confidences = [m.avg_confidence for m in self.metrics_history[-5:]]
            confidence_variance = np.var(recent_confidences)
            
            if confidence_variance < conf_thresholds['suspicious_variance']:
                alerts.append(OverfittingAlerts(
                    alert_level='low',
                    message='Variance de confiance trop faible (possible mémorisation)',
                    metric_name='confidence_variance',
                    current_value=confidence_variance,
                    threshold_value=conf_thresholds['suspicious_variance'],
                    recommendations=[
                        'Introduire plus de variabilité dans les CV',
                        'Vérifier l\'adaptabilité du modèle',
                        'Tester sur des layouts non vus'
                    ]
                ))
        
        return alerts
    
    def _check_pattern_diversity(self, metrics: ExtractionMetrics) -> List[OverfittingAlerts]:
        """Vérifie la diversité des patterns."""
        alerts = []
        comp_thresholds = self.config['complexity_thresholds']
        
        if metrics.pattern_diversity < comp_thresholds['min_pattern_diversity']:
            alerts.append(OverfittingAlerts(
                alert_level='medium',
                message='Diversité de patterns insuffisante',
                metric_name='pattern_diversity',
                current_value=metrics.pattern_diversity,
                threshold_value=comp_thresholds['min_pattern_diversity'],
                recommendations=[
                    'Enrichir les patterns d\'extraction',
                    'Tester sur des formats de CV plus variés',
                    'Éviter la sur-spécialisation sur certains layouts'
                ]
            ))
        
        return alerts
    
    def _check_temporal_trends(self, metrics: ExtractionMetrics) -> List[OverfittingAlerts]:
        """Vérifie les tendances temporelles inquiétantes."""
        alerts = []
        
        if len(self.metrics_history) < 10:
            return alerts  # Pas assez de données pour analyse de tendance
        
        # Analyser la dérive de performance
        recent_window = self.config['analysis_windows']['short_term_samples']
        recent_metrics = self.metrics_history[-recent_window:]
        
        # Comparer avec baseline si disponible
        if self.baseline_stats:
            current_avg_conf = np.mean([m.avg_confidence for m in recent_metrics])
            baseline_conf = self.baseline_stats.get('avg_confidence', current_avg_conf)
            
            drift = abs(current_avg_conf - baseline_conf) / baseline_conf if baseline_conf > 0 else 0
            drift_threshold = self.config['alert_thresholds']['extraction_drift']
            
            if drift > drift_threshold:
                alerts.append(OverfittingAlerts(
                    alert_level='high',
                    message='Dérive significative par rapport au baseline',
                    metric_name='confidence_drift',
                    current_value=drift,
                    threshold_value=drift_threshold,
                    recommendations=[
                        'Recalibrer le modèle d\'extraction',
                        'Vérifier l\'évolution des données d\'entrée',
                        'Considérer un réentraînement'
                    ]
                ))
        
        return alerts
    
    def _check_performance_anomalies(self, metrics: ExtractionMetrics) -> List[OverfittingAlerts]:
        """Vérifie les anomalies de performance."""
        alerts = []
        perf_thresholds = self.config['performance_thresholds']
        
        # Temps d'extraction anormalement long
        if metrics.extraction_time_ms > perf_thresholds['max_extraction_time_ms']:
            alerts.append(OverfittingAlerts(
                alert_level='low',
                message='Temps d\'extraction anormalement élevé',
                metric_name='extraction_time_ms',
                current_value=metrics.extraction_time_ms,
                threshold_value=perf_thresholds['max_extraction_time_ms'],
                recommendations=[
                    'Optimiser les patterns d\'extraction',
                    'Réduire la complexité des règles',
                    'Profiler les goulots d\'étranglement'
                ]
            ))
        
        # Trop de champs vides
        if metrics.empty_fields_ratio > perf_thresholds['max_empty_fields_ratio']:
            alerts.append(OverfittingAlerts(
                alert_level='medium',
                message='Trop de champs requis restent vides',
                metric_name='empty_fields_ratio',
                current_value=metrics.empty_fields_ratio,
                threshold_value=perf_thresholds['max_empty_fields_ratio'],
                recommendations=[
                    'Améliorer les patterns d\'extraction',
                    'Vérifier la qualité des CV en entrée',
                    'Ajuster les seuils de confiance'
                ]
            ))
        
        return alerts
    
    def _log_metrics_and_alerts(self, metrics: ExtractionMetrics, alerts: List[OverfittingAlerts]):
        """Log les métriques et alertes."""
        # Log des métriques principales
        logger.info(f"OVERFITTING_METRICS: cv_id={metrics.cv_id} "
                   f"avg_confidence={metrics.avg_confidence:.3f} "
                   f"pattern_diversity={metrics.pattern_diversity:.3f} "
                   f"extraction_time_ms={metrics.extraction_time_ms:.0f}")
        
        # Log des alertes
        for alert in alerts:
            level_emoji = {'low': '⚠️', 'medium': '🔶', 'high': '🔴', 'critical': '🚨'}
            emoji = level_emoji.get(alert.alert_level, '❓')
            
            logger.warning(f"OVERFITTING_ALERT: {emoji} {alert.alert_level.upper()} "
                          f"| {alert.message} "
                          f"| {alert.metric_name}={alert.current_value:.3f} "
                          f"(threshold={alert.threshold_value:.3f})")
    
    def _trim_history(self):
        """Maintient la taille de l'historique."""
        max_history = self.config['analysis_windows']['long_term_samples']
        if len(self.metrics_history) > max_history:
            self.metrics_history = self.metrics_history[-max_history:]
        
        # Garder seulement les alertes des dernières 24h
        cutoff_time = datetime.now() - timedelta(hours=24)
        self.alerts_history = [
            alert for alert in self.alerts_history 
            if hasattr(alert, 'timestamp') and alert.timestamp > cutoff_time
        ]
    
    def get_health_report(self) -> Dict[str, Any]:
        """Génère un rapport de santé de l'extraction."""
        if not self.metrics_history:
            return {"status": "no_data", "message": "Aucune donnée d'extraction disponible"}
        
        recent_metrics = self.metrics_history[-10:] if len(self.metrics_history) >= 10 else self.metrics_history
        
        # Calculer les statistiques
        avg_confidence = np.mean([m.avg_confidence for m in recent_metrics])
        avg_extraction_time = np.mean([m.extraction_time_ms for m in recent_metrics])
        avg_pattern_diversity = np.mean([m.pattern_diversity for m in recent_metrics])
        
        # Compter les alertes récentes par niveau
        recent_alerts = [a for a in self.alerts_history if hasattr(a, 'timestamp')]  # Filtre temporaire
        alert_counts = Counter([a.alert_level for a in recent_alerts])
        
        # Déterminer le statut global
        if alert_counts.get('critical', 0) > 0:
            status = "critical"
        elif alert_counts.get('high', 0) > 0:
            status = "warning"
        elif alert_counts.get('medium', 0) > 0:
            status = "caution"
        else:
            status = "healthy"
        
        return {
            "status": status,
            "timestamp": datetime.now().isoformat(),
            "recent_extractions": len(recent_metrics),
            "avg_confidence": round(avg_confidence, 3),
            "avg_extraction_time_ms": round(avg_extraction_time, 0),
            "avg_pattern_diversity": round(avg_pattern_diversity, 3),
            "alert_counts": dict(alert_counts),
            "recommendations": self._generate_recommendations(status, recent_metrics, recent_alerts)
        }
    
    def _generate_recommendations(self, status: str, recent_metrics: List[ExtractionMetrics], 
                                recent_alerts: List[OverfittingAlerts]) -> List[str]:
        """Génère des recommandations basées sur l'état."""
        recommendations = []
        
        if status == "critical":
            recommendations.extend([
                "🚨 Arrêter l'extraction et diagnostiquer les problèmes critiques",
                "Analyser les patterns d'overfitting détectés",
                "Considérer un rollback vers une version stable"
            ])
        elif status == "warning":
            recommendations.extend([
                "🔍 Surveiller de près les prochaines extractions",
                "Diversifier les CV de test",
                "Revoir les seuils de confiance"
            ])
        elif status == "caution":
            recommendations.extend([
                "⚠️ Surveiller les tendances d'extraction",
                "Tester sur des formats de CV variés",
                "Optimiser les patterns les moins performants"
            ])
        else:
            recommendations.extend([
                "✅ Continuer le monitoring régulier",
                "Maintenir la diversité des tests",
                "Documenter les bonnes pratiques actuelles"
            ])
        
        return recommendations
    
    def export_metrics(self, filepath: str):
        """Exporte les métriques vers un fichier JSON."""
        export_data = {
            "export_timestamp": datetime.now().isoformat(),
            "config": self.config,
            "metrics_history": [asdict(m) for m in self.metrics_history],
            "alerts_history": [asdict(a) for a in self.alerts_history],
            "baseline_stats": self.baseline_stats
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False, default=str)
        
        logger.info(f"📊 Métriques exportées vers {filepath}")


# Instance globale du moniteur
overfitting_monitor = OverfittingMonitor()


# Factory function pour la compatibilité avec les imports attendus
def get_overfitting_monitor() -> OverfittingMonitor:
    """
    Factory function pour obtenir l'instance du moniteur d'overfitting.
    
    Returns:
        OverfittingMonitor: Instance globale du moniteur
    """
    return overfitting_monitor


# Alias pour compatibilité avec l'interface "Enhanced" attendue
EnhancedOverfittingMonitor = OverfittingMonitor
