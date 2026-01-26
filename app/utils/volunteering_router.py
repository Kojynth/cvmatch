"""
Volunteering Router - Détection et routage des activités bénévoles
================================================================

Router intelligent pour identifier les activités de bénévolat, service civique, 
et associations avant qu'elles soient misclassifiées comme éducation ou expérience.
"""

import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


class VolunteeringType(Enum):
    """Types d'activités bénévoles identifiées."""
    VOLUNTEER = "volunteer"           # Bénévolat général
    CIVIC_SERVICE = "civic_service"   # Service civique
    ASSOCIATION = "association"       # Activités associatives  
    NGO = "ngo"                      # ONG/organisations humanitaires
    COMMUNITY = "community"          # Activités communautaires
    AMBIGUOUS = "ambiguous"          # Ambiguë


@dataclass
class VolunteeringDecision:
    """Décision de routage pour une activité bénévole."""
    volunteering_type: VolunteeringType
    confidence: float
    reasoning: str
    indicators: List[str]
    suggested_section: str


class VolunteeringRouter:
    """Router pour détecter et classifier les activités bénévoles."""
    
    def __init__(self):
        self.logger = get_safe_logger(f"{__name__}.VolunteeringRouter", cfg=DEFAULT_PII_CONFIG)
        
        # Indicateurs de bénévolat explicites
        self.volunteer_indicators = {
            # Français
            "explicit_fr": [
                "bénévole", "bénévolat", "volontaire", "volontariat",
                "service civique", "service volontaire", "mission civique",
                "engagement citoyen", "engagement social", "action sociale",
                "solidarité", "humanitaire", "caritatif", "associatif"
            ],
            
            # English  
            "explicit_en": [
                "volunteer", "volunteering", "voluntary", "voluntarily",
                "community service", "civic service", "social service",
                "charity", "charitable", "humanitarian", "non-profit",
                "pro bono", "unpaid", "honorary", "goodwill"
            ],
            
            # Types d'organisations
            "organizations": [
                "association", "ong", "ngo", "asbl", "fondation", "foundation",
                "croix rouge", "red cross", "restos du coeur", "secours populaire",
                "unicef", "médecins sans frontières", "doctors without borders",
                "amnesty", "greenpeace", "oxfam", "care", "world vision"
            ],
            
            # Contexte de service civique
            "civic_service": [
                "service civique", "civic service", "volontariat international",
                "corps européen", "european corps", "erasmus+",
                "coopération internationale", "international cooperation",
                "développement", "development", "mission humanitaire"
            ],
            
            # Activités communautaires
            "community": [
                "communauté", "community", "quartier", "neighborhood",
                "centre social", "community center", "maison des jeunes",
                "foyer", "refuge", "shelter", "soupe populaire", "food bank",
                "accompagnement scolaire", "tutoring", "coaching"
            ]
        }
        
        # Indicateurs négatifs (contexte professionnel)
        self.professional_excluders = [
            "salaire", "salary", "rémunération", "paid", "contract", "contrat",
            "cdi", "cdd", "employé", "employee", "stage rémunéré",
            "indemnité", "allowance", "compensation", "benefits"
        ]
        
        # Patterns de durée (bénévolat souvent de courte durée)
        self.duration_patterns = [
            r"\b(?:quelques|few)\s+(?:heures?|hours?|jours?|days?)\b",
            r"\b(?:week|weekend|fin de semaine)\b",
            r"\b\d{1,2}\s*(?:heures?|hours?)\s*(?:par|per)\s*(?:semaine|week)\b",
            r"\b(?:ponctuel|occasional|one-time|once)\b"
        ]
    
    def route_volunteering(self, text: str, context: Optional[Dict[str, Any]] = None) -> VolunteeringDecision:
        """
        Route le contenu vers les activités de bénévolat appropriées.
        
        Args:
            text: Texte à analyser
            context: Contexte additionnel (section, métadonnées, etc.)
            
        Returns:
            VolunteeringDecision avec le type et la confiance
        """
        if not text or not text.strip():
            return VolunteeringDecision(
                volunteering_type=VolunteeringType.AMBIGUOUS,
                confidence=0.0,
                reasoning="Empty text",
                indicators=[],
                suggested_section="volunteering"
            )
        
        # Analyser les indicateurs textuels
        indicators = self._analyze_volunteering_indicators(text)
        
        # Vérifier les exclusions professionnelles
        has_professional_context = self._has_professional_excluders(text)
        
        # Calculer les scores par type
        volunteer_score = indicators["volunteer_score"]
        civic_service_score = indicators["civic_service_score"] 
        association_score = indicators["association_score"]
        community_score = indicators["community_score"]
        
        # Ajustements contextuels
        if context:
            section_name = context.get("section_name", "").lower()
            section_hint = context.get("section_hint", "").lower()
            
            # Bonus si dans une section associée au bénévolat
            if any(keyword in section_hint for keyword in 
                   ["bénévolat", "volunteer", "association", "engagement", "civic"]):
                volunteer_score += 0.3
                indicators["reasoning"].append("Section context: volunteering section")
            
            # Ajustement si vient d'une section expérience mais avec indicateurs bénévoles
            if (any(keyword in section_hint for keyword in ["expérience", "experience"]) and
                volunteer_score > 0.4):
                volunteer_score += 0.2
                indicators["reasoning"].append("Strong volunteer indicators in experience section")
        
        # Pénalité si contexte professionnel détecté
        if has_professional_context:
            volunteer_score *= 0.3
            civic_service_score *= 0.3
            association_score *= 0.3
            community_score *= 0.3
            indicators["reasoning"].append("Professional context detected, reducing volunteer scores")
        
        # Déterminer le type de bénévolat
        scores = {
            VolunteeringType.CIVIC_SERVICE: civic_service_score,
            VolunteeringType.ASSOCIATION: association_score, 
            VolunteeringType.COMMUNITY: community_score,
            VolunteeringType.VOLUNTEER: volunteer_score
        }
        
        best_type = max(scores, key=scores.get)
        best_score = scores[best_type]
        confidence = min(best_score, 1.0)
        
        # Seuil de détection
        if confidence < 0.4:
            volunteering_type = VolunteeringType.AMBIGUOUS
            suggested_section = "experience"  # Fallback
        else:
            volunteering_type = best_type
            suggested_section = "volunteering"
        
        reasoning = f"Scores: volunteer={volunteer_score:.2f}, civic={civic_service_score:.2f}, " \
                   f"assoc={association_score:.2f}, community={community_score:.2f}"
        
        self.logger.debug(f"VOLUNTEERING_ROUTER: decision | text='{text[:50]}...' "
                         f"type={volunteering_type.value} confidence={confidence:.2f} "
                         f"professional_excluders={has_professional_context}")
        
        return VolunteeringDecision(
            volunteering_type=volunteering_type,
            confidence=confidence,
            reasoning=reasoning,
            indicators=indicators["matched_indicators"][:10],
            suggested_section=suggested_section
        )
    
    def is_volunteering_content(self, text: str, context: Optional[Dict[str, Any]] = None,
                              confidence_threshold: float = 0.5) -> bool:
        """
        Détermine si le contenu est du bénévolat avec seuil de confiance.
        
        Args:
            text: Texte à analyser
            context: Contexte optionnel
            confidence_threshold: Seuil de confiance minimum
            
        Returns:
            True si identifié comme bénévolat
        """
        decision = self.route_volunteering(text, context)
        
        is_volunteering = (decision.volunteering_type != VolunteeringType.AMBIGUOUS and
                          decision.confidence >= confidence_threshold)
        
        if is_volunteering:
            self.logger.info(f"VOLUNTEERING_DETECTED: type={decision.volunteering_type.value} "
                           f"confidence={decision.confidence:.2f} text='{text[:30]}...'")
        
        return is_volunteering
    
    def _analyze_volunteering_indicators(self, text: str) -> Dict[str, Any]:
        """Analyse les indicateurs de bénévolat dans le texte."""
        text_lower = text.lower()
        matched_indicators = []
        reasoning = []
        
        # Scores par type
        volunteer_score = 0.0
        civic_service_score = 0.0
        association_score = 0.0
        community_score = 0.0
        
        # Analyser chaque catégorie d'indicateurs
        for category, indicators in self.volunteer_indicators.items():
            category_matches = []
            
            for indicator in indicators:
                if indicator.lower() in text_lower:
                    category_matches.append(indicator)
                    matched_indicators.append(f"{category}:{indicator}")
            
            # Scoring par catégorie
            if category_matches:
                if category in ["explicit_fr", "explicit_en"]:
                    volunteer_score += len(category_matches) * 0.4
                    reasoning.append(f"Explicit volunteering keywords: {len(category_matches)}")
                
                elif category == "civic_service":
                    civic_service_score += len(category_matches) * 0.5
                    volunteer_score += len(category_matches) * 0.3
                    reasoning.append(f"Civic service keywords: {len(category_matches)}")
                
                elif category == "organizations":
                    association_score += len(category_matches) * 0.4
                    volunteer_score += len(category_matches) * 0.2
                    reasoning.append(f"Organization keywords: {len(category_matches)}")
                
                elif category == "community":
                    community_score += len(category_matches) * 0.4
                    volunteer_score += len(category_matches) * 0.2
                    reasoning.append(f"Community keywords: {len(category_matches)}")
        
        # Patterns de durée (bonus pour bénévolat)
        duration_matches = 0
        for pattern in self.duration_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                duration_matches += 1
                matched_indicators.append(f"duration_pattern:{pattern}")
        
        if duration_matches > 0:
            volunteer_score += duration_matches * 0.2
            reasoning.append(f"Duration patterns: {duration_matches}")
        
        return {
            "volunteer_score": volunteer_score,
            "civic_service_score": civic_service_score,
            "association_score": association_score,
            "community_score": community_score,
            "matched_indicators": matched_indicators,
            "reasoning": reasoning
        }
    
    def _has_professional_excluders(self, text: str) -> bool:
        """Vérifie la présence d'indicateurs professionnels qui excluent le bénévolat."""
        text_lower = text.lower()
        
        excluder_count = sum(1 for excluder in self.professional_excluders 
                           if excluder in text_lower)
        
        has_excluders = excluder_count > 0
        
        if has_excluders:
            self.logger.debug(f"PROFESSIONAL_EXCLUDERS: found {excluder_count} excluders in text")
        
        return has_excluders


# Global instance
_volunteering_router = None


def get_volunteering_router() -> VolunteeringRouter:
    """Récupère l'instance globale du router de bénévolat."""
    global _volunteering_router
    if _volunteering_router is None:
        _volunteering_router = VolunteeringRouter()
    return _volunteering_router


def route_to_volunteering_section(text: str, context: Optional[Dict[str, Any]] = None) -> str:
    """Route vers la section appropriée (volunteering ou fallback)."""
    router = get_volunteering_router()
    decision = router.route_volunteering(text, context)
    return decision.suggested_section


def is_volunteering_activity(text: str, context: Optional[Dict[str, Any]] = None) -> bool:
    """Détermine si une activité est du bénévolat."""
    router = get_volunteering_router()
    return router.is_volunteering_content(text, context)