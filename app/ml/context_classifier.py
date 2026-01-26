"""
Classificateur contextuel pour arbitrer les labels sous headers spécifiques.
Gère l'override d'expériences sous headers EXP avec seuils adaptés.
"""

import re
from typing import Dict, Any, Optional
from loguru import logger


class ContextFeatures:
    """Features contextuelles pour la classification."""
    
    def __init__(self, text: str, line_idx: int, headers_info: Dict = None):
        self.text = text.lower()
        self.line_idx = line_idx
        self.headers_info = headers_info or {}
        
        # Calculer les features
        self.in_experience_region = self._is_in_experience_region()
        self.has_school_kw = self._has_school_keywords()
        self.has_degree_kw = self._has_degree_keywords()
        self.has_work_indicators = self._has_work_indicators()
    
    def _is_in_experience_region(self) -> bool:
        """Vérifie si la ligne est dans une région d'expériences."""
        # Chercher le header le plus proche avant cette ligne
        closest_header = None
        closest_distance = float('inf')
        
        for header_idx, header_type in self.headers_info.items():
            if header_idx <= self.line_idx:
                distance = self.line_idx - header_idx
                if distance < closest_distance:
                    closest_distance = distance
                    closest_header = header_type
        
        return closest_header in ['experiences', 'experience', 'work']
    
    def _has_school_keywords(self) -> bool:
        """Détecte les mots-clés d'école/université."""
        school_patterns = [
            r'\b(université|university|école|college|institut|school|lycée|iut)\b',
            r'\b(campus|académie|faculty|department)\b'
        ]
        return any(re.search(pattern, self.text, re.I) for pattern in school_patterns)
    
    def _has_degree_keywords(self) -> bool:
        """Détecte les mots-clés de diplôme."""
        degree_patterns = [
            r'\b(diplôme|degree|bachelor|master|licence|bts|dut|doctorat|phd|mba)\b',
            r'\b(graduation|graduated|diplom[ée]|certifi[ée])\b',
            r'\b(lic\.|mst|ing\.|b\.sc|beng|msc|m\.sc)\b'
        ]
        return any(re.search(pattern, self.text, re.I) for pattern in degree_patterns)
    
    def _has_work_indicators(self) -> bool:
        """Détecte les indicateurs de travail."""
        work_patterns = [
            r'\b(stage|stagiaire|alternance|apprenti|cdi|cdd|freelance|consultant)\b',
            r'\b(employé|salarié|contractuel|mission|projet|équipe)\b',
            r'\b(développeur|ingénieur|manager|directeur|chef|responsable)\b'
        ]
        return any(re.search(pattern, self.text, re.I) for pattern in work_patterns)


def decide_context_classification(label_probs: Dict[str, float], 
                                features: ContextFeatures,
                                config: Optional[Dict] = None) -> str:
    """
    Décide du label final avec override contextuel sous headers EXP.
    
    Args:
        label_probs: Probabilités par label {'education': 0.8, 'experiences': 0.2, ...}
        features: Features contextuelles calculées
        config: Configuration (seuils, flags, etc.)
    
    Returns:
        Label final après arbitrage contextuel
    """
    if not config:
        config = {}
    
    # Seuils configurables
    exp_override_threshold = config.get('exp_override_threshold', 0.35)
    edu_strong_threshold = config.get('edu_strong_threshold', 0.95)
    
    # === OVERRIDE EXPÉRIENCES SOUS HEADER EXP ===
    if features.in_experience_region and label_probs.get("experiences", 0) >= exp_override_threshold:
        # Override sauf si triple preuve EDU forte
        triple_edu_proof = (
            features.has_school_kw and 
            features.has_degree_kw and 
            label_probs.get("education", 0) >= edu_strong_threshold
        )
        
        if not triple_edu_proof:
            logger.debug(f"CONTEXT_OVERRIDE: EXP region override | "
                        f"exp_conf={label_probs.get('experiences', 0):.2f} "
                        f"edu_conf={label_probs.get('education', 0):.2f} "
                        f"triple_proof={triple_edu_proof}")
            return "experiences"
    
    # === CLASSIFICATION STANDARD AVEC SEUILS AJUSTÉS ===
    
    # Éducation avec seuil relevé pour éviter false positives
    if label_probs.get("education", 0) >= edu_strong_threshold:
        return "education"
    
    # Expériences avec boost si indicateurs de travail
    exp_threshold = 0.6
    if features.has_work_indicators:
        exp_threshold = 0.4  # Seuil abaissé si indicateurs travail
    
    if label_probs.get("experiences", 0) >= exp_threshold:
        return "experiences"
    
    # Projets 
    if label_probs.get("projects", 0) >= 0.7:
        return "projects"
    
    # Certifications
    if label_probs.get("certifications", 0) >= 0.6:
        return "certifications"
    
    # Default: prendre le plus probable
    if label_probs:
        return max(label_probs, key=label_probs.get)
    
    return "unknown"


def classify_line_with_context(text: str, 
                              line_idx: int,
                              ml_probs: Dict[str, float],
                              headers_info: Dict[int, str] = None,
                              config: Dict = None) -> Dict[str, Any]:
    """
    Classifie une ligne avec prise en compte du contexte.
    
    Args:
        text: Texte de la ligne
        line_idx: Index de la ligne
        ml_probs: Probabilités ML brutes
        headers_info: Info des headers {line_idx: section_type}
        config: Configuration
    
    Returns:
        Dict avec classification finale et méta-données
    """
    # Calculer les features contextuelles
    features = ContextFeatures(text, line_idx, headers_info)
    
    # Décision finale
    final_label = decide_context_classification(ml_probs, features, config)
    
    # Log de la décision
    if features.in_experience_region and final_label != max(ml_probs, key=ml_probs.get):
        logger.info(f"CONTEXT_DECISION: region=EXP override=1 "
                   f"ml_label={max(ml_probs, key=ml_probs.get)} "
                   f"final_label={final_label} "
                   f"edu_conf={ml_probs.get('education', 0):.2f} "
                   f"exp_conf={ml_probs.get('experiences', 0):.2f}")
    
    return {
        'classification': final_label,
        'confidence': ml_probs.get(final_label, 0.0),
        'original_probs': ml_probs,
        'context_features': {
            'in_experience_region': features.in_experience_region,
            'has_school_kw': features.has_school_kw,
            'has_degree_kw': features.has_degree_kw,
            'has_work_indicators': features.has_work_indicators
        },
        'override_applied': final_label != max(ml_probs, key=ml_probs.get)
    }
