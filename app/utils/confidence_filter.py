"""
Filtre de confidence pour les données extraites
=============================================

Module pour filtrer les données extraites selon leur score de confiance.
"""

from typing import Any, Dict, List, Union
from loguru import logger


class ConfidenceFilter:
    """Filtre les données selon leur score de confiance."""
    
    DEFAULT_MIN_CONFIDENCE = 0.9
    
    @staticmethod
    def filter_by_confidence(
        data: Any, 
        min_confidence: float = DEFAULT_MIN_CONFIDENCE,
        keep_structure: bool = True
    ) -> Any:
        """
        Filtre les données selon leur score de confiance.
        
        Args:
            data: Données à filtrer (dict, list, ou autre)
            min_confidence: Score minimum requis (défaut: 0.9)
            keep_structure: Garder la structure même si vide (défaut: True)
            
        Returns:
            Données filtrées selon la confidence
        """
        if not data:
            return data
        
        if isinstance(data, dict):
            return ConfidenceFilter._filter_dict(data, min_confidence, keep_structure)
        elif isinstance(data, list):
            return ConfidenceFilter._filter_list(data, min_confidence, keep_structure)
        else:
            # Pour les types simples, pas de filtrage
            return data
    
    @staticmethod
    def _filter_dict(
        data: Dict[str, Any], 
        min_confidence: float, 
        keep_structure: bool
    ) -> Dict[str, Any]:
        """Filtre un dictionnaire selon la confidence."""
        result = {}
        
        # Vérifier si le dict lui-même a un score de confidence
        confidence_score = data.get('_confidence_score')
        if confidence_score is not None:
            if confidence_score < min_confidence:
                logger.debug(f"Filtrage dict avec confidence {confidence_score} < {min_confidence}")
                return {} if not keep_structure else result
        
        # Filtrer chaque clé
        for key, value in data.items():
            if key.startswith('_confidence'):
                # Garder les métadonnées de confidence
                result[key] = value
                continue
            
            filtered_value = ConfidenceFilter.filter_by_confidence(
                value, min_confidence, keep_structure
            )
            
            # Ajouter seulement si non-vide ou si on garde la structure
            if filtered_value or keep_structure:
                result[key] = filtered_value
        
        return result
    
    @staticmethod
    def _filter_list(
        data: List[Any], 
        min_confidence: float, 
        keep_structure: bool
    ) -> List[Any]:
        """Filtre une liste selon la confidence."""
        result = []
        
        for item in data:
            if isinstance(item, dict):
                # Vérifier la confidence de l'item
                confidence_score = item.get('_confidence_score')
                if confidence_score is not None and confidence_score < min_confidence:
                    logger.debug(f"Filtrage item avec confidence {confidence_score} < {min_confidence}")
                    continue
            
            # Filtrer récursivement
            filtered_item = ConfidenceFilter.filter_by_confidence(
                item, min_confidence, keep_structure
            )
            
            # Ajouter seulement les items non-vides
            if filtered_item:
                result.append(filtered_item)
        
        return result
    
    @staticmethod
    def get_confidence_score(data: Any) -> float:
        """Récupère le score de confidence d'un élément."""
        if isinstance(data, dict):
            return data.get('_confidence_score', 1.0)  # Défaut: confiance maximale
        return 1.0
    
    @staticmethod
    def has_confidence_data(data: Any) -> bool:
        """Vérifie si les données contiennent des scores de confidence."""
        if isinstance(data, dict):
            if '_confidence_score' in data:
                return True
            # Vérifier récursivement
            for value in data.values():
                if ConfidenceFilter.has_confidence_data(value):
                    return True
        elif isinstance(data, list):
            for item in data:
                if ConfidenceFilter.has_confidence_data(item):
                    return True
        
        return False
    
    @staticmethod
    def get_confidence_stats(data: Any) -> Dict[str, float]:
        """Récupère les statistiques de confidence."""
        scores = []
        
        def collect_scores(item):
            if isinstance(item, dict):
                if '_confidence_score' in item:
                    scores.append(item['_confidence_score'])
                for value in item.values():
                    collect_scores(value)
            elif isinstance(item, list):
                for subitem in item:
                    collect_scores(subitem)
        
        collect_scores(data)
        
        if not scores:
            return {
                'count': 0,
                'average': 0.0,
                'min': 0.0,
                'max': 0.0
            }
        
        return {
            'count': len(scores),
            'average': sum(scores) / len(scores),
            'min': min(scores),
            'max': max(scores)
        }


# Fonctions utilitaires pour usage rapide
def filter_high_confidence(data: Any, min_confidence: float = 0.9) -> Any:
    """Raccourci pour filtrer avec haute confidence (>= 0.9)."""
    return ConfidenceFilter.filter_by_confidence(data, min_confidence)


def filter_medium_confidence(data: Any, min_confidence: float = 0.7) -> Any:
    """Raccourci pour filtrer avec confidence moyenne (>= 0.7)."""
    return ConfidenceFilter.filter_by_confidence(data, min_confidence)


def has_confidence_scores(data: Any) -> bool:
    """Raccourci pour vérifier la présence de scores de confidence."""
    return ConfidenceFilter.has_confidence_data(data)


def get_data_quality_stats(data: Any) -> Dict[str, float]:
    """Raccourci pour obtenir les stats de qualité."""
    return ConfidenceFilter.get_confidence_stats(data)
